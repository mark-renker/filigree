"""Filigree gestures and curves — SPEC §7 (glyph lanes) and §8 (gesture algebra).

This module turns two very different surface syntaxes into the *same* runtime
object, a :class:`Gesture`:

* **drawn curves** — the column-aligned glyph lanes of SPEC §7
  (``bend | ___/^^^ |``) via :func:`glyphs_to_gesture`;
* **first-class gestures** — the parameterised, composable expression language
  of SPEC §8 (``bend(wiggle(rate, depth) @ onset..100%)``) via
  :func:`eval_gesture`.

Everything is expressed in *note-lifetime normalised time*: ``t = 0`` is the
note-on, ``t = 1`` is the note-off.  A :class:`Gesture` is a bag of
:class:`Segment`s, each of which owns one lane and one window of that lifetime.

Sampling returns ``NaN`` wherever a lane has **no data**.  This is
load-bearing: SPEC §7 says an unspecified region must never be written, so the
resolver skips every ``NaN`` sample instead of writing a default value that
would fight the DAW.

Only the standard library plus numpy is used (ARCH rule 3), and all randomness
is a deterministic hash of ``GestureCtx.seed_key`` (ARCH rule 7).
"""

from __future__ import annotations

import hashlib
import math
import re
import struct
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Sequence

import numpy as np

from . import ir
from .ast_nodes import (
    BinOp,
    Breakpoints,
    Call,
    GestureDef,
    Num,
    Pos,
    Ref,
    Slot,
    Target,
    UnOp,
    Window,
)
from .errors import GestureError

__all__ = [
    "Segment",
    "Gesture",
    "Env",
    "GestureCtx",
    "eval_gesture",
    "glyphs_to_gesture",
    "lane_rest_for",
    "LANE_RESTS",
    "GLYPH_HINT",
    "parse_glyph_string",
    "curve_from_string",
    "lane_range_for",
    "hash01",
    "SHAPES",
    "LANE_PRIMITIVES",
    "GENERATORS",
]

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

#: Interpolation shapes available to breakpoints and glyph lanes (SPEC §7).
SHAPES = ("ease", "linear", "hold", "exp", "snap")

#: Lane-typed primitives (SPEC §8).  ``cc<n>`` is matched by regex as well.
LANE_PRIMITIVES = ("bend", "press", "timbre", "amp", "pan")

#: Shape generators (SPEC §8).
GENERATORS = ("wiggle", "drift", "ramp", "pulse", "curve", "const")

_CC_RE = re.compile(r"^cc(\d{1,3})$")

_EXP_K = 3.0  # curvature of the "exp" shape; see SHAPES notes in curves.md

#: default oscillator rate in Hz for ``~`` glyphs and bare ``wiggle()``
DEFAULT_WIGGLE_HZ = 5.0
#: default ``drift`` control-point rate in Hz
DEFAULT_DRIFT_HZ = 1.5
#: default oscillator depth as a fraction of the full lane span
DEFAULT_DEPTH_FRAC = 0.05
#: bare ``~`` glyph depth in ninths of the lane's half span
GLYPH_WIGGLE_DEFAULT = 3.0

_MAX_DEPTH = 64  # recursion guard for user gesture definitions


def lane_range_for(lane: str) -> tuple[float, float]:
    """Default value range of a lane (``ir.LANE_RANGES``, ``cc<n>`` is 0..1)."""
    if lane in ir.LANE_RANGES:
        return ir.LANE_RANGES[lane]
    if _CC_RE.match(lane or ""):
        return (0.0, 1.0)
    return (0.0, 1.0)


#: SPEC §7 (amended): each lane has a **rest value** — the value that means
#: "this lane is doing nothing".  The floor glyph ``_`` is the rest value, NOT
#: the lane minimum; ``v``/``V`` is the explicit lane minimum.  On a bipolar
#: lane the minimum is a large downward bend, so a drawn floor must read as
#: "resting", never as "a minor third flat" (round-2 defect D1).
LANE_RESTS: dict[str, float] = {
    "bend": 0.0,
    "press": 0.0,
    "timbre": 0.5,
    "amp": 0.5,
    "pan": 0.5,
}


def lane_rest_for(lane: str, lane_range: Optional[tuple[float, float]] = None
                  ) -> float:
    """Rest value of ``lane`` (SPEC §7 table), clamped into ``lane_range``.

    ``cc<n>`` lanes rest at 0.  An unknown lane rests at its minimum, which is
    the conservative "write nothing audible" choice for a unipolar lane.
    """
    name = lane or ""
    if name in LANE_RESTS:
        rest = LANE_RESTS[name]
    elif _CC_RE.match(name):
        rest = 0.0
    else:
        rest = lane_range_for(name)[0]
    if lane_range is not None:
        lo, hi = lane_range
        rest = min(max(rest, lo), hi)
    return float(rest)


def is_lane_primitive(name: str) -> bool:
    return name in LANE_PRIMITIVES or bool(_CC_RE.match(name or ""))


# ---------------------------------------------------------------------------
# deterministic noise
# ---------------------------------------------------------------------------


def _hash_bytes(parts: Iterable[Any]) -> bytes:
    h = hashlib.blake2b(digest_size=16)
    for p in parts:
        h.update(repr(p).encode("utf-8"))
        h.update(b"\x1f")
    return h.digest()


def hash01(*parts: Any) -> float:
    """Deterministic uniform value in ``[0, 1)`` from arbitrary hashable parts.

    Independent of Python's hash randomisation (uses blake2b), so output is
    byte-identical across runs and machines.
    """
    (n,) = struct.unpack("<Q", _hash_bytes(parts)[:8])
    return (n >> 11) / float(1 << 53)


def noise_series(n: int, *parts: Any) -> np.ndarray:
    """``n`` deterministic values in ``[-1, 1]`` keyed by ``parts``."""
    n = max(int(n), 2)
    return np.array([hash01(parts, i) * 2.0 - 1.0 for i in range(n)])


# ---------------------------------------------------------------------------
# interpolation
# ---------------------------------------------------------------------------


def _shape_ease(f: np.ndarray, shape: str) -> np.ndarray:
    """Map a normalised 0..1 position within a span to an eased 0..1 weight."""
    if shape == "linear":
        return f
    if shape == "ease":  # smoothstep
        return f * f * (3.0 - 2.0 * f)
    if shape == "hold":  # keep the previous anchor, jump at the *next* anchor
        return np.zeros_like(f)
    if shape == "snap":  # jump to the target the instant the span begins
        return np.ones_like(f)
    if shape == "exp":
        return (np.exp(_EXP_K * f) - 1.0) / (math.exp(_EXP_K) - 1.0)
    raise GestureError(
        f"unknown interpolation shape {shape!r}",
        suggestion="use one of: " + ", ".join(SHAPES),
    )


def _interp(u: np.ndarray, ts: np.ndarray, vs: np.ndarray, shape: str) -> np.ndarray:
    """Piecewise interpolation of anchors ``(ts, vs)`` at positions ``u``."""
    u = np.asarray(u, dtype=float)
    if ts.size == 0:
        return np.full(u.shape, np.nan)
    if ts.size == 1:
        return np.full(u.shape, vs[0])
    idx = np.searchsorted(ts, u, side="right") - 1
    idx = np.clip(idx, 0, ts.size - 2)
    t0 = ts[idx]
    t1 = ts[idx + 1]
    span = np.where(t1 > t0, t1 - t0, 1.0)
    f = np.clip((u - t0) / span, 0.0, 1.0)
    e = _shape_ease(f, shape)
    out = vs[idx] + e * (vs[idx + 1] - vs[idx])
    out = np.where(u <= ts[0], vs[0], out)
    out = np.where(u >= ts[-1], vs[-1], out)
    return out


# ---------------------------------------------------------------------------
# lane functions
#
# A lane function maps LOCAL normalised time (0..1 inside its Segment's window)
# to a lane value.  Rate-bearing functions (wiggle/pulse/drift, and the `~`
# glyph) additionally know how many SECONDS their own domain spans, so that a
# rate written in Hz is Hz of real time no matter what is wrapped around it.
#
# Two time-mapping operations are defined on *every* lane function, so that no
# wrapper can silently swallow them (this was round-1 defect D1):
#
#   ``rescaled(k)``     the function's domain now occupies ``k`` times as many
#                       real seconds; rate-bearing leaves multiply ``span_sec``
#                       by ``k`` so their Hz is unchanged.  Used by the *fitting*
#                       placement :meth:`Gesture.windowed` (glyph slots).
#   ``reoriginned(u0)`` phase 0 of every rate-bearing leaf underneath moves to
#                       domain position ``u0``.  Used by the *restricting*
#                       operator ``@ x..y`` (SPEC §8) so an oscillator starts
#                       when its window opens.
#
# Both are recursive: ``_Scaled``, ``_Combined``, ``_GlyphFn`` and ``_Retimed``
# forward them to whatever they wrap.  ``_reclock_fn`` / ``_reorigin_fn`` are
# the entry points and are total (a shape-only function returns itself).
# ---------------------------------------------------------------------------


class _RateFn:
    """Base class for lane functions whose shape depends on absolute time.

    ``span_sec`` is how many real seconds this function's 0..1 domain covers;
    ``u0`` is the domain position at which its phase is zero.  Absolute seconds
    are therefore ``(u - u0) * span_sec`` — see :meth:`_secs`.
    """

    span_sec: float = 1.0
    u0: float = 0.0

    def rescaled(self, k: float) -> "_RateFn":
        raise NotImplementedError

    def reoriginned(self, u0: float) -> "_RateFn":
        raise NotImplementedError

    @property
    def eff_span(self) -> float:
        """Seconds spanned by the domain, with a fallback for empty notes.

        A zero-length note has no real-time extent at all, which used to make
        every oscillator collapse to a flat line (round-1 defect D5).  When the
        span is degenerate the rate is instead read as *cycles per lifetime*
        over a nominal 1 s, so the shape survives and stays inspectable.
        """
        return self.span_sec if self.span_sec > 1e-12 else 1.0

    def _secs(self, u: np.ndarray) -> np.ndarray:
        return (np.asarray(u, dtype=float) - self.u0) * self.eff_span


def _reclock_fn(fn: Callable, k: float) -> Callable:
    """Stretch a lane function's real-time span by factor ``k`` (Hz survive)."""
    resc = getattr(fn, "rescaled", None)
    return resc(k) if resc is not None else fn


def _reorigin_fn(fn: Callable, u0: float) -> Callable:
    """Move phase 0 of every rate-bearing leaf under ``fn`` to ``u0``."""
    if abs(float(u0)) < 1e-15:
        return fn
    reo = getattr(fn, "reoriginned", None)
    return reo(float(u0)) if reo is not None else fn


#: back-compatible alias for the old (rate-only) helper name
_rescale_fn = _reclock_fn


class _Wiggle(_RateFn):
    """``wiggle(rate, depth, phase)`` — a sine, phase 0 at its time origin."""

    def __init__(self, rate_hz: float, depth: float, phase_turns: float,
                 span_sec: float, u0: float = 0.0):
        self.rate_hz = float(rate_hz)
        self.depth = float(depth)
        self.phase_turns = float(phase_turns)
        self.span_sec = float(span_sec)
        self.u0 = float(u0)

    def rescaled(self, k: float) -> "_Wiggle":
        return _Wiggle(self.rate_hz, self.depth, self.phase_turns,
                       self.span_sec * k, self.u0)

    def reoriginned(self, u0: float) -> "_Wiggle":
        return _Wiggle(self.rate_hz, self.depth, self.phase_turns,
                       self.span_sec, u0)

    def __call__(self, u: np.ndarray) -> np.ndarray:
        secs = self._secs(u)
        return self.depth * np.sin(2.0 * np.pi * (self.rate_hz * secs + self.phase_turns))


class _Pulse(_RateFn):
    """``pulse(rate, duty)`` — unipolar square wave, 1 during the duty part."""

    def __init__(self, rate_hz: float, duty: float, span_sec: float, u0: float = 0.0):
        self.rate_hz = float(rate_hz)
        self.duty = float(min(max(duty, 0.0), 1.0))
        self.span_sec = float(span_sec)
        self.u0 = float(u0)

    def rescaled(self, k: float) -> "_Pulse":
        return _Pulse(self.rate_hz, self.duty, self.span_sec * k, self.u0)

    def reoriginned(self, u0: float) -> "_Pulse":
        return _Pulse(self.rate_hz, self.duty, self.span_sec, u0)

    def __call__(self, u: np.ndarray) -> np.ndarray:
        ph = np.mod(self.rate_hz * self._secs(u), 1.0)
        return np.where(ph < self.duty, 1.0, 0.0)


class _Drift(_RateFn):
    """``drift(depth, rate)`` — deterministic seeded smooth value noise."""

    def __init__(self, depth: float, rate_hz: float, span_sec: float,
                 seed_key: tuple, u0: float = 0.0):
        self.depth = float(depth)
        self.rate_hz = float(rate_hz)
        self.span_sec = float(span_sec)
        self.seed_key = tuple(seed_key)
        self.u0 = float(u0)

    def rescaled(self, k: float) -> "_Drift":
        return _Drift(self.depth, self.rate_hz, self.span_sec * k, self.seed_key,
                      self.u0)

    def reoriginned(self, u0: float) -> "_Drift":
        return _Drift(self.depth, self.rate_hz, self.span_sec, self.seed_key, u0)

    def _controls(self, secs: float) -> np.ndarray:
        n = int(math.ceil(self.rate_hz * max(secs, 1e-9))) + 2
        return noise_series(n, "drift", self.seed_key, round(self.rate_hz, 6))

    def __call__(self, u: np.ndarray) -> np.ndarray:
        # control points run at rate_hz of REAL time, starting at the origin.
        width = max(1.0 - self.u0, 1e-9)
        cps = self._controls(self.eff_span * width)
        ts = self.u0 + np.linspace(0.0, 1.0, cps.size) * width
        return self.depth * _interp(np.asarray(u, dtype=float), ts, cps, "ease")


class _Breakpoints:
    """Interpolated anchor list in local normalised time."""

    def __init__(self, ts: Sequence[float], vs: Sequence[float], shape: str):
        self.ts = np.asarray(ts, dtype=float)
        self.vs = np.asarray(vs, dtype=float)
        self.shape = shape

    def __call__(self, u: np.ndarray) -> np.ndarray:
        return _interp(u, self.ts, self.vs, self.shape)


class _Const:
    def __init__(self, value: float):
        self.value = float(value)

    def __call__(self, u: np.ndarray) -> np.ndarray:
        return np.full(np.asarray(u, dtype=float).shape, self.value)


class _GlyphFn:
    """Glyph lane: runs of anchors separated by ``NaN`` (no-data) holes.

    ``extras`` are the rate-bearing decorations (``~``) that ride on top of an
    anchor run; they are slot-anchored, so this wrapper forwards both time-
    mapping operations to them (round-1 defect D1: a windowed ``~`` used to
    change speed because ``_GlyphFn`` had neither method).  ``lane_range``
    clamps the sum of anchor + decoration to the lane, so a drawn curve can
    never demand a value the lane cannot carry (defect D2).
    """

    def __init__(self, runs, holes, extras, shape,
                 lane_range: Optional[tuple[float, float]] = None):
        # runs: list[(ts, vs)] ; holes: list[(a, b)] ; extras: list[(a, b, fn)]
        self.runs = runs
        self.holes = holes
        self.extras = extras
        self.shape = shape
        self.lane_range = lane_range

    def rescaled(self, k: float) -> "_GlyphFn":
        return _GlyphFn(self.runs, self.holes,
                        [(a, b, _reclock_fn(fn, k)) for a, b, fn in self.extras],
                        self.shape, self.lane_range)

    def reoriginned(self, u0: float) -> "_GlyphFn":
        # ``u0`` is in lane-local time; each decoration's own domain is its slot.
        extras = []
        for a, b, fn in self.extras:
            local = (float(u0) - a) / max(b - a, 1e-12)
            extras.append((a, b, _reorigin_fn(fn, local)))
        return _GlyphFn(self.runs, self.holes, extras, self.shape, self.lane_range)

    def __call__(self, u: np.ndarray) -> np.ndarray:
        u = np.asarray(u, dtype=float)
        out = np.full(u.shape, np.nan)
        for ts, vs in self.runs:
            m = (u >= ts[0] - 1e-12) & (u <= ts[-1] + 1e-12)
            if np.any(m):
                out[m] = _interp(u[m], ts, vs, self.shape)
        for a, b in self.holes:
            m = (u > a + 1e-12) & (u < b - 1e-12)
            out[m] = np.nan
        for a, b, fn in self.extras:
            m = (u >= a - 1e-12) & (u <= b + 1e-12)
            if np.any(m):
                local = (u[m] - a) / max(b - a, 1e-12)
                out[m] = out[m] + fn(local)
        if self.lane_range is not None:
            lo, hi = self.lane_range
            out = np.clip(out, lo, hi)
        return out


# ---------------------------------------------------------------------------
# Segment / Gesture
# ---------------------------------------------------------------------------


@dataclass
class Segment:
    """A resolved curve on ONE lane, in note-lifetime space.

    ``fn`` maps local normalised time (0..1 across ``window``) to a lane value;
    ``window`` is the portion of the note lifetime the segment covers.  Outside
    the window the segment contributes no data.
    """

    lane: str
    fn: Callable[[np.ndarray], np.ndarray]
    window: tuple[float, float] = (0.0, 1.0)

    # -- internal helpers ---------------------------------------------------
    def remapped(self, a: float, b: float) -> "Segment":
        """*Fit* this segment into the sub-window ``a..b`` of the lifetime.

        The segment's own 0..1 domain is squeezed into ``a..b``; rate-bearing
        functions underneath are reclocked by the same factor so their Hz stays
        real-time Hz.  Used for glyph-slot placement of inline gestures.
        """
        w0, w1 = self.window
        k = b - a
        nw = (a + w0 * k, a + w1 * k)
        return Segment(self.lane, _reclock_fn(self.fn, k), nw)

    def restricted(self, a: float, b: float) -> Optional["Segment"]:
        """SPEC §8 ``@ x..y`` — *restrict* this segment to ``a..b``.

        The curve keeps its own shape and timing; everything outside ``a..b``
        becomes unwritten.  Rate-bearing functions underneath move their phase
        origin to ``a``, so an oscillator starts when the window opens and
        still runs at its written Hz.
        """
        w0, w1 = self.window
        na, nb = max(w0, a), min(w1, b)
        if nb <= na:
            return None
        span = max(w1 - w0, 1e-12)
        fn = _reorigin_fn(self.fn, (a - w0) / span)
        if abs(na - w0) < 1e-15 and abs(nb - w1) < 1e-15:
            return Segment(self.lane, fn, (na, nb))
        return Segment(self.lane, _Retimed(fn, w0, w1, na, nb), (na, nb))

    def eval_global(self, t: np.ndarray) -> np.ndarray:
        """Evaluate at absolute lifetime positions; ``NaN`` outside the window."""
        t = np.asarray(t, dtype=float)
        w0, w1 = self.window
        out = np.full(t.shape, np.nan)
        m = (t >= w0 - 1e-12) & (t <= w1 + 1e-12)
        if np.any(m):
            span = max(w1 - w0, 1e-12)
            u = np.clip((t[m] - w0) / span, 0.0, 1.0)
            out[m] = np.asarray(self.fn(u), dtype=float)
        return out


@dataclass
class Gesture:
    """A bundle of lane curves covering (part of) one note's lifetime."""

    segments: list[Segment] = field(default_factory=list)

    def lanes(self) -> set[str]:
        return {s.lane for s in self.segments}

    def sample(self, lane: str, t: np.ndarray) -> Optional[np.ndarray]:
        """Sample ``lane`` at note-lifetime positions ``t`` (0..1).

        Returns ``None`` when the gesture writes nothing at all on that lane,
        and an array with ``NaN`` in every region the lane leaves unspecified.
        Later segments overlay earlier ones where they carry data.
        """
        segs = [s for s in self.segments if s.lane == lane]
        if not segs:
            return None
        t = np.asarray(t, dtype=float)
        scalar = t.ndim == 0
        t = np.atleast_1d(t)
        out = np.full(t.shape, np.nan)
        for s in segs:
            vals = s.eval_global(t)
            m = ~np.isnan(vals)
            out[m] = vals[m]
        out[(t < -1e-12) | (t > 1.0 + 1e-12)] = np.nan
        return float(out[0]) if scalar else out  # type: ignore[return-value]

    # -- construction helpers ----------------------------------------------
    def with_segments(self, segs: list[Segment]) -> "Gesture":
        return Gesture(list(segs))

    def windowed(self, a: float, b: float) -> "Gesture":
        """*Fit* the whole gesture into ``a..b`` (glyph-slot placement).

        This is not SPEC §8 ``@`` — see :meth:`restricted`.  It is what a glyph
        slot does to an inline gesture call: the gesture's 0..1 lifetime is
        squeezed into the slot, with every rate-bearing primitive reclocked so
        its Hz survives the squeeze.
        """
        if b < a:
            a, b = b, a
        return Gesture([s.remapped(a, b) for s in self.segments])

    def restricted(self, a: float, b: float) -> "Gesture":
        """SPEC §8 ``a @ x..y`` — restrict to a window of the note lifetime.

        Shape-bearing curves keep their own timing and are merely masked to
        ``a..b``; rate-bearing primitives keep their absolute Hz and take ``a``
        as their phase origin.  Everything outside ``a..b`` is unwritten (NaN).
        """
        if b < a:
            a, b = b, a
        segs = [s.restricted(a, b) for s in self.segments]
        return Gesture([s for s in segs if s is not None])

    def time_scaled(self, k: float) -> "Gesture":
        """Reclock every segment: the lifetime now lasts ``k`` times as long.

        Windows are untouched (they are in normalised time); only the real-time
        span of rate-bearing primitives changes, so Hz stay Hz.
        """
        return Gesture([Segment(s.lane, _reclock_fn(s.fn, k), s.window)
                        for s in self.segments])

    def reoriginned_at(self, t0: float) -> "Gesture":
        """Move the phase origin of every rate-bearing primitive to lifetime ``t0``."""
        out = []
        for s in self.segments:
            w0, w1 = s.window
            local = (float(t0) - w0) / max(w1 - w0, 1e-12)
            out.append(Segment(s.lane, _reorigin_fn(s.fn, local), s.window))
        return Gesture(out)

    def scaled(self, k: float) -> "Gesture":
        """SPEC §8 ``a * k`` — scale amplitude on every lane."""
        return Gesture([Segment(s.lane, _Scaled(s.fn, k), s.window) for s in self.segments])

    def coverage(self, lane: str) -> tuple[float, float]:
        segs = [s for s in self.segments if s.lane == lane]
        if not segs:
            return (0.0, 0.0)
        return (min(s.window[0] for s in segs), max(s.window[1] for s in segs))

    def relane(self, lane: str) -> "Gesture":
        """Re-label every segment onto ``lane`` (used by lane primitives)."""
        return Gesture([Segment(lane, s.fn, s.window) for s in self.segments])


class _Retimed:
    """Re-express a lane function on a narrower slice of its own domain.

    Used by :meth:`Segment.restricted`: the new segment covers ``na..nb`` of the
    lifetime while the wrapped function still believes its domain is ``w0..w1``,
    so the underlying curve is masked rather than stretched.
    """

    def __init__(self, fn: Callable, w0: float, w1: float, na: float, nb: float):
        self.fn = fn
        self.w0 = float(w0)
        self.w1 = float(w1)
        self.na = float(na)
        self.nb = float(nb)

    def _inner(self, u: np.ndarray) -> np.ndarray:
        t = self.na + np.asarray(u, dtype=float) * (self.nb - self.na)
        return (t - self.w0) / max(self.w1 - self.w0, 1e-12)

    def rescaled(self, k: float) -> "_Retimed":
        return _Retimed(_reclock_fn(self.fn, k), self.w0, self.w1, self.na, self.nb)

    def reoriginned(self, u0: float) -> "_Retimed":
        inner = float(self._inner(np.asarray(float(u0))))
        return _Retimed(_reorigin_fn(self.fn, inner), self.w0, self.w1,
                        self.na, self.nb)

    def __call__(self, u: np.ndarray) -> np.ndarray:
        return np.asarray(self.fn(self._inner(u)), dtype=float)


class _Scaled:
    def __init__(self, fn: Callable, k: float):
        self.fn = fn
        self.k = float(k)

    def rescaled(self, k: float) -> "_Scaled":
        return _Scaled(_reclock_fn(self.fn, k), self.k)

    def reoriginned(self, u0: float) -> "_Scaled":
        return _Scaled(_reorigin_fn(self.fn, u0), self.k)

    def __call__(self, u: np.ndarray) -> np.ndarray:
        return np.asarray(self.fn(u), dtype=float) * self.k


class _Combined:
    """Pointwise combination of two gestures on one lane, in global time."""

    def __init__(self, lhs: Gesture, rhs: Gesture, lane: str, op: str,
                 w0: float, w1: float):
        self.lhs = lhs
        self.rhs = rhs
        self.lane = lane
        self.op = op
        self.w0 = float(w0)
        self.w1 = float(w1)

    # Time mapping is forwarded into BOTH operands (round-1 defect D1: `*`
    # produced a `_Combined` with no time mapping at all, so windowing a
    # `wiggle * ramp` compressed the wiggle's phase instead of reclocking it).
    def rescaled(self, k: float) -> "_Combined":
        return _Combined(self.lhs.time_scaled(k), self.rhs.time_scaled(k),
                         self.lane, self.op, self.w0, self.w1)

    def reoriginned(self, u0: float) -> "_Combined":
        t0 = self.w0 + float(u0) * (self.w1 - self.w0)
        return _Combined(self.lhs.reoriginned_at(t0), self.rhs.reoriginned_at(t0),
                         self.lane, self.op, self.w0, self.w1)

    def __call__(self, u: np.ndarray) -> np.ndarray:
        u = np.asarray(u, dtype=float)
        t = self.w0 + u * (self.w1 - self.w0)
        a = self.lhs.sample(self.lane, t)
        b = self.rhs.sample(self.lane, t)
        if a is None and b is None:  # pragma: no cover - guarded by caller
            return np.full(u.shape, np.nan)
        if a is None:
            a = np.full(u.shape, np.nan)
        if b is None:
            b = np.full(u.shape, np.nan)
        a = np.asarray(a, dtype=float)
        b = np.asarray(b, dtype=float)
        na, nb = np.isnan(a), np.isnan(b)
        if self.op in ("add", "sub"):
            # "no data" is the additive identity: a lane that says nothing must
            # not blank out a lane that does.  NaN only survives if BOTH say
            # nothing there.
            av = np.where(na, 0.0, a)
            bv = np.where(nb, 0.0, b)
            out = av + bv if self.op == "add" else av - bv
            return np.where(na & nb, np.nan, out)
        if self.op == "mul":
            # multiplication is masking: NaN absorbs, because scaling nothing
            # still yields nothing.
            return np.where(na | nb, np.nan, a * b)
        raise GestureError(f"unknown gesture operator {self.op!r}")


# ---------------------------------------------------------------------------
# context and environment
# ---------------------------------------------------------------------------


@dataclass
class GestureCtx:
    """Everything a gesture needs that comes from the score."""

    lane_default: Optional[str] = None      # lane implied by the enclosing lane
    lane_range: tuple[float, float] = (-2.0, 2.0)
    tempo: float = 120.0
    note_dur_beats: float = 1.0
    seed_key: tuple = ()
    resolve_target: Optional[Callable[["Target"], float]] = None   # -> lane value

    # -- derived ------------------------------------------------------------
    @property
    def note_dur_sec(self) -> float:
        tempo = self.tempo if self.tempo else 120.0
        return float(self.note_dur_beats) * 60.0 / float(tempo)

    @property
    def center(self) -> float:
        lo, hi = self.lane_range
        return 0.0 if lo < 0.0 else (lo + hi) / 2.0

    @property
    def rest(self) -> float:
        """The lane's rest value — what the floor glyph ``_`` means (SPEC §7)."""
        return lane_rest_for(self.lane_default or "", self.lane_range)

    @property
    def span(self) -> float:
        lo, hi = self.lane_range
        return hi - lo

    def for_lane(self, lane: str) -> "GestureCtx":
        """Child context whose default lane and range are those of ``lane``."""
        return GestureCtx(
            lane_default=lane,
            lane_range=lane_range_for(lane),
            tempo=self.tempo,
            note_dur_beats=self.note_dur_beats,
            seed_key=tuple(self.seed_key) + (lane,),
            resolve_target=self.resolve_target,
        )

    def target(self, tgt: "Target") -> float:
        if self.resolve_target is None:
            raise GestureError(
                "harmonic target used with no harmonic context",
                token=">",
                line=getattr(tgt, "pos", Pos()).line,
                col=getattr(tgt, "pos", Pos()).col,
                suggestion="targets like `>3` are only valid where a chord is known",
            )
        return float(self.resolve_target(tgt))


class Env:
    """Gesture definitions plus the parameter bindings of the current scope."""

    def __init__(self, defs: dict[str, GestureDef], params: Optional[dict] = None):
        self.defs: dict[str, GestureDef] = dict(defs or {})
        self.params: dict = dict(params or {})
        self.depth: int = 0

    def child(self, params: dict) -> "Env":
        e = Env(self.defs, params)
        e.depth = self.depth + 1
        if e.depth > _MAX_DEPTH:
            raise GestureError(
                "gesture definition recurses too deeply",
                suggestion="a gesture may not (indirectly) reference itself",
            )
        return e

    # -- lookups ------------------------------------------------------------
    def has_param(self, name: str) -> bool:
        return name in self.params

    def param(self, name: str) -> Any:
        return self.params[name]

    def gesture_def(self, name: str) -> Optional[GestureDef]:
        return self.defs.get(name)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Env(defs={sorted(self.defs)}, params={sorted(self.params)})"


# ---------------------------------------------------------------------------
# scalar evaluation
# ---------------------------------------------------------------------------


def _unit_value(n: Num, ctx: GestureCtx) -> float:
    v = float(n.value)
    u = (n.unit or "").lower()
    if u in ("", "none"):
        return v
    if u == "pct":
        return v / 100.0
    if u == "st":
        return v            # ir: bend curves are in semitones already
    if u == "cent":
        return v / 100.0
    if u == "hz":
        return v
    if u == "ms":
        return v
    if u == "beat":
        return v
    if u == "bpm":
        return v
    return v


def _as_scalar(expr: Any, env: Env, ctx: GestureCtx) -> float:
    """Evaluate an expression that must be a number (parameter, unit, target)."""
    if expr is None:
        raise GestureError("missing numeric argument")
    if isinstance(expr, (int, float)) and not isinstance(expr, bool):
        return float(expr)
    if isinstance(expr, Num):
        return _unit_value(expr, ctx)
    if isinstance(expr, Target):
        return ctx.target(expr)
    if isinstance(expr, Ref):
        if env.has_param(expr.name):
            return _as_scalar(env.param(expr.name), env, ctx)
        d = env.gesture_def(expr.name)
        if d is not None:
            raise GestureError(
                f"gesture {expr.name!r} used where a number is required",
                token=expr.name,
                line=expr.pos.line, col=expr.pos.col,
            )
        raise GestureError(
            f"unknown parameter {expr.name!r}",
            token=expr.name, line=expr.pos.line, col=expr.pos.col,
            suggestion="declare it in the gesture's parameter list",
        )
    if isinstance(expr, UnOp) and expr.op == "neg":
        return -_as_scalar(expr.operand, env, ctx)
    if isinstance(expr, BinOp) and expr.op in ("add", "sub", "scale_or_mul"):
        a = _as_scalar(expr.lhs, env, ctx)
        b = _as_scalar(expr.rhs, env, ctx)
        return a + b if expr.op == "add" else (a - b if expr.op == "sub" else a * b)
    if isinstance(expr, str):
        return float(expr)
    raise GestureError(f"expected a number, got {type(expr).__name__}")


def _maybe_scalar(expr: Any, env: Env, ctx: GestureCtx) -> Optional[float]:
    """Scalar value of ``expr`` if it *is* a scalar, else ``None``."""
    try:
        if isinstance(expr, (Num, Target)) or (
            isinstance(expr, (int, float)) and not isinstance(expr, bool)
        ):
            return _as_scalar(expr, env, ctx)
        if isinstance(expr, Ref) and env.has_param(expr.name):
            return _maybe_scalar(env.param(expr.name), env, ctx)
        if isinstance(expr, UnOp) and expr.op == "neg":
            inner = _maybe_scalar(expr.operand, env, ctx)
            return None if inner is None else -inner
    except GestureError:
        return None
    return None


def _pos_value(expr: Any, env: Env, ctx: GestureCtx, default: float) -> float:
    """A position inside the note lifetime: ``40%`` / ``0.4`` / ``120ms``."""
    if expr is None:
        return default
    if isinstance(expr, Num) and (expr.unit or "").lower() == "ms":
        dur_ms = ctx.note_dur_sec * 1000.0
        return float(expr.value) / dur_ms if dur_ms > 0 else default
    v = _as_scalar(expr, env, ctx)
    return v


def _arg(call: Call, index: int, name: str, default: Any = None) -> Any:
    if name in call.kwargs:
        return call.kwargs[name]
    if index < len(call.args):
        return call.args[index]
    return default


def _shape_of(obj: Any, env: Env, ctx: GestureCtx, default: str = "ease") -> str:
    """Extract a ``shape:`` keyword (string or Ref-to-string)."""
    if obj is None:
        return default
    if isinstance(obj, str):
        s = obj
    elif isinstance(obj, Ref):
        if env.has_param(obj.name):
            return _shape_of(env.param(obj.name), env, ctx, default)
        s = obj.name
    else:
        raise GestureError(f"shape must be a name, got {type(obj).__name__}")
    s = s.strip().lower()
    if s not in SHAPES:
        raise GestureError(
            f"unknown interpolation shape {s!r}", token=s,
            suggestion="use one of: " + ", ".join(SHAPES),
        )
    return s


# ---------------------------------------------------------------------------
# breakpoints
# ---------------------------------------------------------------------------


def _breakpoint_positions(raw: list[Optional[float]]) -> list[float]:
    """Spread unpositioned breakpoints evenly between positioned neighbours.

    The first point defaults to 0.0 and the last to 1.0 (SPEC §8: breakpoints
    span the note lifetime).  Runs of unpositioned points between two known
    positions are spaced evenly.
    """
    n = len(raw)
    pos: list[Optional[float]] = list(raw)
    if n == 0:
        return []
    if pos[0] is None:
        pos[0] = 0.0
    if n > 1 and pos[-1] is None:
        pos[-1] = 1.0
    i = 0
    while i < n:
        if pos[i] is not None:
            i += 1
            continue
        j = i
        while j < n and pos[j] is None:
            j += 1
        left = pos[i - 1] if i > 0 else 0.0
        right = pos[j] if j < n else 1.0
        gap = (right - left) / (j - i + 1)
        for k in range(i, j):
            pos[k] = left + gap * (k - i + 1)
        i = j
    out = [float(p) for p in pos]  # type: ignore[arg-type]
    # positions must be monotone non-decreasing
    for k in range(1, len(out)):
        if out[k] < out[k - 1]:
            out[k] = out[k - 1]
    return out


def _eval_breakpoints(bp: Breakpoints, env: Env, ctx: GestureCtx,
                      shape: Optional[str] = None) -> Gesture:
    lane = ctx.lane_default
    if lane is None:
        raise GestureError(
            "breakpoints outside a lane primitive",
            suggestion="wrap them, e.g. bend(0 -> -0.7st -> 0)",
        )
    if not bp.points:
        raise GestureError("empty breakpoint list", line=bp.pos.line, col=bp.pos.col)
    vals = [_as_scalar(v, env, ctx) for v, _ in bp.points]
    raw_pos: list[Optional[float]] = []
    for _, p in bp.points:
        raw_pos.append(None if p is None else _pos_value(p, env, ctx, 0.0))
    ts = _breakpoint_positions(raw_pos)
    sh = _shape_of(bp.shape, env, ctx, shape or "ease") if bp.shape else (shape or "ease")
    fn = _Breakpoints(ts, vals, sh)
    return Gesture([Segment(lane, fn, (0.0, 1.0))])


# ---------------------------------------------------------------------------
# generators
# ---------------------------------------------------------------------------


def _eval_generator(call: Call, env: Env, ctx: GestureCtx) -> Gesture:
    lane = ctx.lane_default
    name = call.name
    if lane is None:
        raise GestureError(
            f"{name}() used outside a lane",
            token=name, line=call.pos.line, col=call.pos.col,
            suggestion=f"write bend({name}(...)) or use it inside a curve lane",
        )
    dur = ctx.note_dur_sec

    if name == "wiggle":
        rate = _arg(call, 0, "rate")
        depth = _arg(call, 1, "depth")
        phase = _arg(call, 2, "phase")
        r = DEFAULT_WIGGLE_HZ if rate is None else _as_scalar(rate, env, ctx)
        d = (DEFAULT_DEPTH_FRAC * ctx.span) if depth is None else _as_scalar(depth, env, ctx)
        p = 0.0 if phase is None else _as_scalar(phase, env, ctx)
        return Gesture([Segment(lane, _Wiggle(r, d, p, dur), (0.0, 1.0))])

    if name == "drift":
        depth = _arg(call, 0, "depth")
        rate = _arg(call, 1, "rate")
        d = (DEFAULT_DEPTH_FRAC * ctx.span) if depth is None else _as_scalar(depth, env, ctx)
        r = DEFAULT_DRIFT_HZ if rate is None else _as_scalar(rate, env, ctx)
        return Gesture([Segment(lane, _Drift(d, r, dur, tuple(ctx.seed_key)), (0.0, 1.0))])

    if name == "pulse":
        rate = _arg(call, 0, "rate")
        duty = _arg(call, 1, "duty")
        r = DEFAULT_WIGGLE_HZ if rate is None else _as_scalar(rate, env, ctx)
        dc = 0.5 if duty is None else _as_scalar(duty, env, ctx)
        return Gesture([Segment(lane, _Pulse(r, dc, dur), (0.0, 1.0))])

    if name == "ramp":
        a = _arg(call, 0, "a", _arg(call, 0, "from"))
        b = _arg(call, 1, "b", _arg(call, 1, "to"))
        if a is None or b is None:
            raise GestureError(
                "ramp() needs two values", token="ramp",
                line=call.pos.line, col=call.pos.col,
                suggestion="ramp(0, 1)",
            )
        av = _as_scalar(a, env, ctx)
        bv = _as_scalar(b, env, ctx)
        sh = _shape_of(call.kwargs.get("shape"), env, ctx, "linear")
        return Gesture([Segment(lane, _Breakpoints([0.0, 1.0], [av, bv], sh), (0.0, 1.0))])

    if name == "const":
        v = _arg(call, 0, "value")
        return Gesture([Segment(lane, _Const(_as_scalar(v, env, ctx)), (0.0, 1.0))])

    if name == "curve":
        s = _arg(call, 0, "glyphs")
        if isinstance(s, Ref) and env.has_param(s.name):
            s = env.param(s.name)
        if not isinstance(s, str):
            raise GestureError(
                'curve() takes a glyph string, e.g. curve("_/^\\_")',
                token="curve", line=call.pos.line, col=call.pos.col,
            )
        sh = _shape_of(call.kwargs.get("shape"), env, ctx, "ease")
        return curve_from_string(s, lane, ctx, shape=sh)

    raise GestureError(f"unknown generator {name!r}", token=name)  # pragma: no cover


# ---------------------------------------------------------------------------
# eval_gesture
# ---------------------------------------------------------------------------


def _combine(lhs: Gesture, rhs: Gesture, op: str) -> Gesture:
    """``+ - *`` over gestures: per lane, union of lanes."""
    lanes = sorted(lhs.lanes() | rhs.lanes())
    segs: list[Segment] = []
    for lane in lanes:
        in_l = lane in lhs.lanes()
        in_r = lane in rhs.lanes()
        if in_l and not in_r:
            if op == "mul":
                continue   # nothing to multiply against -> no data
            segs.extend(s for s in lhs.segments if s.lane == lane)
            continue
        if in_r and not in_l:
            if op == "mul":
                continue
            if op == "sub":
                segs.extend(
                    Segment(lane, _Scaled(s.fn, -1.0), s.window)
                    for s in rhs.segments if s.lane == lane
                )
            else:
                segs.extend(s for s in rhs.segments if s.lane == lane)
            continue
        a0, a1 = lhs.coverage(lane)
        b0, b1 = rhs.coverage(lane)
        if op == "mul":
            w0, w1 = max(a0, b0), min(a1, b1)
            if w1 <= w0:
                continue
        else:
            w0, w1 = min(a0, b0), max(a1, b1)
        segs.append(Segment(lane, _Combined(lhs, rhs, lane, op, w0, w1), (w0, w1)))
    return Gesture(segs)


def eval_gesture(expr: Any, env: Env, ctx: "GestureCtx") -> Gesture:
    """Evaluate a gesture expression (SPEC §8) into a :class:`Gesture`."""
    if expr is None:
        return Gesture([])

    # ---- literals -------------------------------------------------------
    if isinstance(expr, Num):
        lane = ctx.lane_default
        if lane is None:
            raise GestureError(
                "bare number used as a gesture",
                line=expr.pos.line, col=expr.pos.col,
                suggestion="wrap it in a lane, e.g. press(0.5)",
            )
        return Gesture([Segment(lane, _Const(_unit_value(expr, ctx)), (0.0, 1.0))])

    if isinstance(expr, Target):
        lane = ctx.lane_default or "bend"
        return Gesture([Segment(lane, _Const(ctx.target(expr)), (0.0, 1.0))])

    if isinstance(expr, Breakpoints):
        return _eval_breakpoints(expr, env, ctx)

    # ---- references -----------------------------------------------------
    if isinstance(expr, Ref):
        if env.has_param(expr.name):
            bound = env.param(expr.name)
            if isinstance(bound, Gesture):
                return bound
            return eval_gesture(bound, env, ctx)
        d = env.gesture_def(expr.name)
        if d is None:
            raise GestureError(
                f"unknown gesture {expr.name!r}",
                token=expr.name, line=expr.pos.line, col=expr.pos.col,
                suggestion=_suggest(expr.name, sorted(env.defs)),
            )
        return _apply_def(d, [], {}, env, ctx, expr.pos)

    # ---- calls ----------------------------------------------------------
    if isinstance(expr, Call):
        name = expr.name
        if is_lane_primitive(name):
            child = ctx.for_lane(name)
            shape = _shape_of(expr.kwargs.get("shape"), env, ctx, "ease") \
                if "shape" in expr.kwargs else None
            inner_args = [a for a in expr.args]
            if not inner_args:
                raise GestureError(
                    f"{name}() needs a curve argument",
                    token=name, line=expr.pos.line, col=expr.pos.col,
                    suggestion=f"{name}(0 -> 1) or {name}(wiggle(5hz, 0.3st))",
                )
            parts: list[Gesture] = []
            for a in inner_args:
                if isinstance(a, Breakpoints):
                    parts.append(_eval_breakpoints(a, env, child, shape))
                elif isinstance(a, (Num, Target)) or (
                    isinstance(a, Ref) and env.has_param(a.name)
                    and isinstance(env.param(a.name), (Num, int, float))
                ):
                    v = _as_scalar(a, env, child)
                    parts.append(Gesture([Segment(name, _Const(v), (0.0, 1.0))]))
                else:
                    parts.append(eval_gesture(a, env, child))
            g = Gesture([s for p in parts for s in p.segments])
            return g.relane(name)

        if name in GENERATORS:
            return _eval_generator(expr, env, ctx)

        d = env.gesture_def(name)
        if d is None:
            raise GestureError(
                f"unknown gesture {name!r}",
                token=name, line=expr.pos.line, col=expr.pos.col,
                suggestion=_suggest(name, sorted(env.defs) + list(GENERATORS)
                                    + list(LANE_PRIMITIVES)),
            )
        return _apply_def(d, expr.args, expr.kwargs, env, ctx, expr.pos)

    # ---- unary ----------------------------------------------------------
    if isinstance(expr, UnOp):
        if expr.op != "neg":
            raise GestureError(f"unknown unary operator {expr.op!r}")
        return eval_gesture(expr.operand, env, ctx).scaled(-1.0)

    # ---- window ---------------------------------------------------------
    if isinstance(expr, Window):
        a = _pos_value(expr.start, env, ctx, 0.0)
        b = _pos_value(expr.end, env, ctx, 1.0)
        a = min(max(a, 0.0), 1.0)
        b = min(max(b, 0.0), 1.0)
        inner = eval_gesture(expr.inner, env, ctx)
        if b <= a:
            return Gesture([])
        # SPEC §8: `@ x..y` RESTRICTS to a window of the note lifetime.
        return inner.restricted(a, b)

    # ---- binary ---------------------------------------------------------
    if isinstance(expr, BinOp):
        op = expr.op
        if op == "par":
            lhs = eval_gesture(expr.lhs, env, ctx)
            rhs = eval_gesture(expr.rhs, env, ctx)
            return Gesture(list(lhs.segments) + list(rhs.segments))
        if op == "seq":
            split = 0.5 if expr.split is None else _pos_value(expr.split, env, ctx, 0.5)
            split = min(max(split, 0.0), 1.0)
            lhs = eval_gesture(expr.lhs, env, ctx)
            rhs = eval_gesture(expr.rhs, env, ctx)
            out: list[Segment] = []
            # The published law `a >> b == (a @ 0..50%) | (b @ 50%..100%)` ties
            # `>>` to `@`, and `@` restricts (SPEC §8), so `>>` is a hand-off at
            # the split point, not a time compressor.  See NOTES_P3.md.
            if split > 0.0:
                out += lhs.restricted(0.0, split).segments
            if split < 1.0:
                out += rhs.restricted(split, 1.0).segments
            return Gesture(out)
        if op in ("add", "sub"):
            lhs = eval_gesture(expr.lhs, env, ctx)
            rhs = eval_gesture(expr.rhs, env, ctx)
            return _combine(lhs, rhs, op)
        if op == "scale_or_mul":
            k = _maybe_scalar(expr.rhs, env, ctx)
            if k is not None:
                return eval_gesture(expr.lhs, env, ctx).scaled(k)
            k = _maybe_scalar(expr.lhs, env, ctx)
            if k is not None:
                return eval_gesture(expr.rhs, env, ctx).scaled(k)
            lhs = eval_gesture(expr.lhs, env, ctx)
            rhs = eval_gesture(expr.rhs, env, ctx)
            return _combine(lhs, rhs, "mul")
        raise GestureError(f"unknown gesture operator {op!r}")

    if isinstance(expr, Gesture):
        return expr

    raise GestureError(f"cannot evaluate {type(expr).__name__} as a gesture")


def _suggest(name: str, known: Sequence[str]) -> str:
    import difflib

    close = difflib.get_close_matches(name, list(known), n=1)
    if close:
        return f"did you mean {close[0]!r}?"
    return "known gestures: " + ", ".join(sorted(set(known))[:8])


def _apply_def(d: GestureDef, args: list, kwargs: dict, env: Env,
               ctx: GestureCtx, pos: Pos) -> Gesture:
    """Bind arguments to a user gesture definition and evaluate its body."""
    names = [p[0] for p in d.params]
    if len(args) > len(names):
        raise GestureError(
            f"gesture {d.name!r} takes {len(names)} argument(s), got {len(args)}",
            token=d.name, line=pos.line, col=pos.col,
        )
    bound: dict[str, Any] = {}
    for i, a in enumerate(args):
        bound[names[i]] = a
    for k, v in kwargs.items():
        if k == "shape" and k not in names:
            continue
        if k not in names:
            raise GestureError(
                f"gesture {d.name!r} has no parameter {k!r}",
                token=k, line=pos.line, col=pos.col,
                suggestion="parameters: " + (", ".join(names) or "(none)"),
            )
        bound[k] = v
    for pname, pdefault in d.params:
        if pname not in bound:
            if pdefault is None:
                raise GestureError(
                    f"gesture {d.name!r} needs a value for {pname!r}",
                    token=pname, line=pos.line, col=pos.col,
                    suggestion=f"call it as {d.name}({pname}: ...)",
                )
            bound[pname] = pdefault
    # Arguments are evaluated in the CALLER's scope (so `vibr(rate: r)` works
    # inside another definition); defaults belong to the definition's scope,
    # which has no other bindings anyway.
    resolved: dict[str, Any] = {}
    for k, v in bound.items():
        if isinstance(v, Ref) and env.has_param(v.name):
            resolved[k] = env.param(v.name)
        else:
            resolved[k] = v
    inner = env.child(resolved)
    return eval_gesture(d.body, inner, ctx)


# ---------------------------------------------------------------------------
# glyph lanes (SPEC §7)
# ---------------------------------------------------------------------------

GLYPH_CHARS = set("_vV-^/\\~x0123456789>")

#: the glyph alphabet, quoted in every curve-glyph diagnostic
GLYPH_HINT = ("glyphs are '_' rest, 'v' min, '-' centre, '^' max, "
              "'/' ramp up, '\\' ramp down, '0'-'9' level, '~' wiggle, "
              "'x' hold, '>' harmonic target")


def _glyph_level(glyph: str, arg: Optional[float], ctx: GestureCtx,
                 prev: float) -> Optional[float]:
    """Value an anchor glyph reaches by the END of its slot (SPEC §7 table)."""
    lo, hi = ctx.lane_range
    if glyph == "_":
        # SPEC §7 (amended): the drawn floor is the lane's REST value.
        return ctx.rest
    if glyph in ("v", "V"):
        # the explicit all-the-way-down; on `bend` this is -range.
        return lo
    if glyph == "-":
        return ctx.center
    if glyph == "^":
        return hi
    if glyph == "/":
        return hi
    if glyph == "\\":
        return lo
    if glyph == "x":
        return prev
    if glyph == "~":
        return prev
    if glyph is not None and len(glyph) == 1 and glyph.isdigit():
        return lo + (int(glyph) / 9.0) * (hi - lo)
    return None


def glyphs_to_gesture(glyphs: list[tuple[float, float, "Slot"]], lane: str,
                      ctx: GestureCtx, shape: str = "ease") -> Gesture:
    """Turn drawn glyph slots into one :class:`Gesture` segment over 0..1.

    ``glyphs`` are ``(start_frac, end_frac, slot)`` triples in lane-local
    normalised time.  Semantics (SPEC §7):

    * a glyph is an **anchor reached by the end of its slot**, so ``___/^^^``
      holds the minimum, ramps across the ``/`` slot, then holds the maximum;
    * ``/`` and ``\\`` ramp *from the running value* to lane max / min;
    * ``x`` holds the running value flat, ``~`` wiggles around it;
    * ``>`` glides to ``ctx.resolve_target(slot.target)``;
    * an **empty** slot writes nothing — the sampled value there is ``NaN``.
    """
    if lane is None:
        raise GestureError("glyphs_to_gesture needs a lane name")
    ctx = ctx if ctx.lane_default == lane else GestureCtx(
        lane_default=lane,
        lane_range=ctx.lane_range if ctx.lane_default == lane else lane_range_for(lane),
        tempo=ctx.tempo,
        note_dur_beats=ctx.note_dur_beats,
        seed_key=tuple(ctx.seed_key) + (lane,),
        resolve_target=ctx.resolve_target,
    )
    if shape not in SHAPES:
        raise GestureError(
            f"unknown interpolation shape {shape!r}",
            suggestion="use one of: " + ", ".join(SHAPES),
        )

    items = sorted(glyphs, key=lambda g: (g[0], g[1]))
    runs: list[tuple[np.ndarray, np.ndarray]] = []
    holes: list[tuple[float, float]] = []
    extras: list[tuple[float, float, Callable]] = []

    cur_t: list[float] = []
    cur_v: list[float] = []
    prev: Optional[float] = None
    run_start: Optional[float] = None

    def flush() -> None:
        nonlocal cur_t, cur_v, run_start
        if len(cur_t) >= 1:
            ts = np.asarray(cur_t, dtype=float)
            vs = np.asarray(cur_v, dtype=float)
            runs.append((ts, vs))
        cur_t, cur_v = [], []
        run_start = None

    lo, hi = ctx.lane_range
    half = (hi - lo) / 2.0

    for (s, e, slot) in items:
        kind = getattr(slot, "kind", None)
        glyph = getattr(slot, "glyph", None)
        target = getattr(slot, "target", None)

        if kind in (None, "empty", "rest") and target is None and glyph is None:
            # no data for this slot
            flush()
            holes.append((float(s), float(e)))
            prev = None
            continue

        if kind == "gesture" or (kind not in ("glyph", "empty", None) and glyph is None
                                 and target is None):
            # Inline gesture calls must be expanded by the resolver (it owns the
            # Env); we refuse to invent data here.  See NOTES_P3.md.
            flush()
            holes.append((float(s), float(e)))
            prev = None
            continue

        # ---- resolve the anchor value ----------------------------------
        if target is not None:
            if lane != "bend":
                raise GestureError(
                    "harmonic targets ('>') are only valid on the bend lane",
                    token=">", line=slot.pos.line, col=slot.pos.col,
                    suggestion="move the target to a bend lane",
                )
            value = ctx.target(target)
        else:
            value = _glyph_level(glyph, slot.glyph_arg, ctx,
                                 ctx.rest if prev is None else prev)
            if value is None:
                raise GestureError(
                    f"unknown curve glyph {glyph!r}",
                    token=str(glyph), line=slot.pos.line, col=slot.pos.col,
                    suggestion=GLYPH_HINT + " (or a space for no data)",
                )

        if not cur_t:
            # a run opens flat: the first anchor's value is already in force at
            # the run's start, so nothing ramps in out of nowhere.
            entry = value
            if glyph in ("/", "\\") or target is not None:
                # Ramps and glides start from the running value and arrive by
                # the slot's end.  With nothing running yet the run opens at the
                # lane's REST value (SPEC §7 amended): `press | /^^^\\__ |` now
                # swells from closed, not from half-open (round-2 defect D4).
                entry = ctx.rest if prev is None else prev
            run_start = float(s)
            cur_t.append(float(s))
            cur_v.append(float(entry))
        cur_t.append(float(e))
        cur_v.append(float(value))

        if glyph == "~":
            # `~5` == depth 5/9 of the lane's half span; bare `~` == 3/9.
            depth_units = slot.glyph_arg if slot.glyph_arg is not None \
                else GLYPH_WIGGLE_DEFAULT
            depth = (float(depth_units) / 9.0) * half
            # LANE-RANGE DISCIPLINE (round-1 defect D2): a wiggle around an
            # anchor near a lane boundary COMPRESSES to the available headroom
            # rather than clipping, so the drawn shape is still a sine and the
            # mean pitch is still the anchor.  At an exact extreme (`^~`) there
            # is no headroom and the slot is a flat hold; write `8~` for vibrato
            # near the top of the lane.
            headroom = max(min(hi - value, value - lo), 0.0)
            depth = min(depth, headroom)
            span_sec = ctx.note_dur_sec * (float(e) - float(s))
            # WHOLE-CYCLE RATE (round-1 defect D4): the lane-default rate is
            # rounded to a whole number of cycles inside the slot, so `~` never
            # ends mid-swing and never biases the average value of its slot.
            # An explicit `wiggle(rate, depth)` is never rounded.
            rate = DEFAULT_WIGGLE_HZ
            if span_sec > 1e-12:
                cycles = max(1, int(round(DEFAULT_WIGGLE_HZ * span_sec)))
                rate = cycles / span_sec
            extras.append((float(s), float(e),
                           _Wiggle(rate, depth, 0.0, span_sec)))
        prev = value

    flush()

    if not runs and not holes:
        return Gesture([])

    fn = _GlyphFn(runs, holes, extras, shape, lane_range=(lo, hi))
    return Gesture([Segment(lane, fn, (0.0, 1.0))])


def parse_glyph_string(s: str) -> list[tuple[float, float, Slot]]:
    """Tokenise a glyph string (as in ``curve("_/^\\_")``) into slot triples.

    ``~`` may take a digit suffix (``~5``); a space is an empty slot; ``.`` is
    accepted as a visible synonym for an empty slot.
    """
    toks: list[Slot] = []
    i = 0
    while i < len(s):
        c = s[i]
        if c in " \t":
            toks.append(Slot(kind="empty"))
            i += 1
            continue
        if c == ".":
            toks.append(Slot(kind="empty"))
            i += 1
            continue
        if c == "~":
            arg = None
            if i + 1 < len(s) and s[i + 1].isdigit():
                arg = float(s[i + 1])
                i += 1
            toks.append(Slot(kind="glyph", glyph="~", glyph_arg=arg))
            i += 1
            continue
        if c == ">":
            deg = None
            if i + 1 < len(s) and s[i + 1].isdigit():
                deg = int(s[i + 1])
                i += 1
            tgt = Target(kind="degree", degree=deg) if deg is not None \
                else Target(kind="guide")
            toks.append(Slot(kind="glyph", target=tgt))
            i += 1
            continue
        if c in GLYPH_CHARS:
            toks.append(Slot(kind="glyph", glyph=c))
            i += 1
            continue
        raise GestureError(
            f"unknown curve glyph {c!r} in curve string",
            token=c, suggestion=GLYPH_HINT + " (or a space for no data)",
        )
    n = len(toks)
    if n == 0:
        return []
    return [(k / n, (k + 1) / n, tok) for k, tok in enumerate(toks)]


def curve_from_string(s: str, lane: str, ctx: GestureCtx,
                      shape: str = "ease") -> Gesture:
    """``curve("_/^\\_")`` — a glyph string used as a gesture (SPEC §8)."""
    return glyphs_to_gesture(parse_glyph_string(s), lane, ctx, shape=shape)
