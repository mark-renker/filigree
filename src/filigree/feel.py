"""P5 — deterministic humanisation ("feel"), round 2.

Round 1 produced *noise with the right variance*.  The round-1 critic
(``refs/verdicts/P5_round1.md``) showed that every **structural** statistic of a
real performance was missing: velocity lag-1 autocorrelation −0.01 against a
reference +0.45, gaussian timing (excess kurtosis +0.06) against a reference
+5.6, gate IQR width 0.17–0.48 against 2.93, and provably zero dependence on
metrical position.  This module is the rebuild.  The re-derived ground truth,
its method and its per-file numbers live in ``refs/specs/feel_truth.md``.

What a note's perturbation is now made of
-----------------------------------------

1. **Memory (AR(1) / discrete OU).**  Timing and velocity are no longer
   independent per-note draws.  Each *stream* — one stave, one hand (pitch split
   at ``hand_split``) — carries three latent AR(1) processes::

       x_i = phi * x_{i-1} + sqrt(1 - phi**2) * eps_i

   with ``eps_i`` a counter-based normal keyed on the note's own identity, so
   the process is stationary with unit variance and fully reproducible.  ``phi``
   is ``timing_ar`` / ``velocity_ar`` / ``gate_ar``.  Timing steps once per
   *onset cluster* (a chord pushes or lays back as a unit); velocity and gate
   step once per note.

2. **Heavy tails.**  The timing innovation is multiplied by a log-normal scale
   mixture ``exp(lam * u)`` (a Gaussian scale mixture, i.e. a smooth
   student-t-like law).  ``timing_df`` is the student-t degrees of freedom the
   mixture imitates: ``lam`` is chosen so the excess kurtosis is exactly
   ``6 / (df - 4)``, and the mixture is renormalised so the sd stays
   ``timing_ms``.  ``df`` → ``inf`` gives back a textbook normal.

3. **An explicit metrical profile.**  ``accent_profile`` is a per-beat velocity
   multiplier (normalised to mean 1.0), ``timing_profile_ms`` a per-beat onset
   offset, and ``accent_period2`` / ``timing_period2_ms`` are the period-2 combs
   on the tatum index that the reference shows as alternating velocity ACF.
   These are *parameters*, not hidden constants.

4. **Articulation.**  ``articulation`` blends the notated duration towards a
   gate ratio (duration ÷ IOI to the next note in the same stream) drawn from a
   split log-normal with median ``gate_center`` and log-sd ``gate_spread``
   (below the median) / ``gate_spread * gate_skew`` (above), with AR(1) memory,
   so a Filigree score can be staccato in one bar and held-over in the next.

5. **Melody lead.**  Inside an onset cluster the onsets are ordered top-first:
   ``melody_lead_ms`` times a centred pitch rank, plus a *two-sided*
   ``onset_ms`` scatter (round 1's scatter could only delay).

Contract that round 1 won and round 2 keeps
-------------------------------------------

* No RNG object, no global state, no built-in ``hash()`` (salted per run).  All
  randomness is counter-based mixing (splitmix64 / FNV-1a) of a key tuple, so
  the same seed gives byte-identical output across interpreter invocations.
* A zero spec is a bit-exact no-op.
* The pitch multiset, the note count and the note order are never changed:
  every onset shift is clamped to ``max_shift_ratio`` of the distance to the
  nearer nominal neighbour *and* to the window that starts a minimum separation
  after the previous already-perturbed onset, so notes cannot swap, cannot stack
  at t = 0 and cannot be pushed past the end of the piece.
* Every out-of-range, ambiguous, NaN or infinite parameter produces a warning
  that names the parameter *and* the value, and is then clamped — never guessed.

Units, explicitly (round-1 defect D1: a 47x cliff at exactly 1.0)
-----------------------------------------------------------------

``velocity`` and ``gate`` are **fractions**: ``0.12`` is 12 %.  A string with an
explicit unit is also accepted (``"12%"``, ``"12pct"``, ``"0.12"``).  A bare
number greater than 1.0 is **ambiguous** (is ``4.0`` 400 % or 4 %?): round 1
silently divided by 100, so ``0.99`` gave sd 49.2 and ``1.01`` gave sd 1.04, and
``400%`` silently meant 4 %.  Round 2 never guesses — it warns, names the value,
and clamps to 1.0 (= 100 %), which is continuous at 1.0.

See ``docs/SPEC.md`` §9, ``docs/ARCH.md`` (P5) and ``NOTES_P5.md``.
"""

from __future__ import annotations

import math
import struct
import warnings
from dataclasses import dataclass, field as _dc_field
from typing import Callable, Iterable, Optional, Sequence

from .ir import Note

__all__ = [
    "FeelSpec", "FeelWarning", "hash01", "gauss", "apply_feel", "normalise",
    "LOOSE", "TIGHT", "PUSHED", "BREATH", "PRESETS", "preset", "feel_spec",
]

_MASK64 = (1 << 64) - 1
_GOLDEN = 0x9E3779B97F4A7C15
_INV_2_53 = 1.0 / float(1 << 53)


class FeelWarning(UserWarning):
    """Raised (as a warning) for an out-of-range or ambiguous feel parameter."""


# --------------------------------------------------------------------------- #
# spec
# --------------------------------------------------------------------------- #

#: ``None`` on a structural field means "derive it from the classic magnitudes"
#: (see :func:`normalise`).  Set the field explicitly to override, or to 0 to
#: switch the feature off.
AUTO = None


@dataclass
class FeelSpec:
    """Declarative humanisation parameters.

    Timing
      ``timing_ms``          sd (or, for ``flat``, the constant offset) of the
                             onset perturbation, in milliseconds.
      ``timing_dist``        ``"gauss"``/``"human"`` (default: AR(1) + heavy
                             tails), ``"t"``/``"t5"``/``"student-t"`` (same, with
                             the df spelled in the name), ``"normal"``/``"iid"``
                             (textbook independent gaussian, no memory, no
                             tails), ``"uniform"`` (±``timing_ms``, iid) or
                             ``"flat"`` (a constant signed shift — a groove
                             template, not humanisation; see NOTES_P5 D10).
      ``timing_df``          degrees of freedom the tail mixture imitates;
                             excess kurtosis is ``6/(df-4)``.  ``inf`` = normal.
      ``timing_ar``          AR(1) coefficient of the timing process (0..0.95).
      ``timing_rel``         if > 0, sd is this fraction of the local tatum
                             instead of ``timing_ms`` (the reference is 0.076 of
                             the tatum across a 4x tatum range).
      ``timing_profile_ms``  per-beat-of-bar onset offsets, ms.
      ``timing_period2_ms``  period-2 comb on the tatum index, ms.

    Velocity
      ``velocity``           jitter as a *fraction* of the note's velocity
                             (0.12 == 12 %; ``"12%"`` also accepted).
      ``velocity_ar``        AR(1) coefficient of the velocity process.
      ``accent_profile``     per-beat-of-bar velocity multipliers (normalised
                             to mean 1.0).
      ``accent_period2``     period-2 velocity comb depth on the tatum index.

    Articulation / length
      ``gate``               classic note-length jitter, a fraction of duration.
      ``articulation``       0..1 blend of the notated duration towards a drawn
                             gate ratio (0 = notated only, round-1 behaviour).
      ``gate_center``        median target gate ratio (duration ÷ IOI).
      ``gate_spread``        log-sd of the gate ratio below the median.
      ``gate_skew``          multiplier on ``gate_spread`` above the median.
      ``gate_ar``            AR(1) coefficient of the articulation process.
      ``gate_max``           hard clip on the gate ratio (default 4.0).
      ``release_ms``         extra release time added to each note, ms,
                             jittered ±50 %.

    Chord / voicing
      ``onset_ms``           sd of the two-sided onset scatter inside a cluster.
      ``melody_lead_ms``     signed lead of the top voice (negative = early).
      ``onset_mode``         ``"lead"`` (default) or ``"legacy"`` (round-1
                             one-sided, pitch-blind scatter).

    Metre / structure
      ``beats_per_bar``      metre used by the beat profiles (``apply_feel`` is
                             not given the metre — amendment request A2).
      ``tatum_beats``        subdivision the period-2 combs count in.
      ``hand_split``         pitch that separates the two streams of a stave.
      ``on_beats``           if non-empty, the timing term applies only on these
                             1-based beats of the bar.

    Bounds
      ``max_shift_ratio``    an onset may move at most this fraction of the
                             distance to its nearer nominal neighbour; the
                             window is additionally clipped to sit strictly
                             after the previous *perturbed* onset, so the note
                             order and a minimum separation hold for any value.
      ``seed``               per-feel seed, mixed with the score ``@seed``.
    """

    # --- classic (round 1) ------------------------------------------------ #
    timing_ms: float = 0.0
    timing_dist: str = "gauss"
    velocity: float = 0.0
    gate: float = 0.0
    onset_ms: float = 0.0
    release_ms: float = 0.0
    on_beats: tuple[int, ...] = ()
    seed: int = 0
    # --- timing shape / memory ------------------------------------------- #
    timing_df: float = 5.0
    timing_ar: Optional[float] = AUTO
    timing_rel: float = 0.0
    timing_profile_ms: Optional[tuple[float, ...]] = AUTO
    timing_period2_ms: Optional[float] = AUTO
    timing_drift_ms: Optional[float] = AUTO
    timing_drift_span: Optional[float] = AUTO
    timing_swell: Optional[float] = AUTO
    # --- velocity memory / accents --------------------------------------- #
    velocity_ar: Optional[float] = AUTO
    accent_profile: Optional[tuple[float, ...]] = AUTO
    accent_period2: Optional[float] = AUTO
    # --- articulation ----------------------------------------------------- #
    articulation: Optional[float] = AUTO
    gate_center: float = 0.95
    gate_spread: float = 1.10
    gate_skew: float = 1.55
    gate_ar: Optional[float] = AUTO
    gate_max: float = 4.0
    # --- chord ------------------------------------------------------------ #
    melody_lead_ms: Optional[float] = AUTO
    onset_mode: str = "lead"
    release_mode: str = "jitter"
    # --- metre / bounds --------------------------------------------------- #
    beats_per_bar: int = 4
    tatum_beats: float = 0.25
    hand_split: int = 60
    max_shift_ratio: float = 0.90

    def __post_init__(self) -> None:
        self.on_beats = tuple(int(b) for b in self.on_beats)
        self.timing_dist = str(self.timing_dist).lower().strip()
        self.onset_mode = str(self.onset_mode).lower().strip()
        self.release_mode = str(self.release_mode).lower().strip()


# --------------------------------------------------------------------------- #
# counter-based randomness (unchanged from round 1 — it passed)
# --------------------------------------------------------------------------- #

def _splitmix64(x: int) -> int:
    x = (x + _GOLDEN) & _MASK64
    z = x
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
    return (z ^ (z >> 31)) & _MASK64


def _fnv1a64(data: bytes) -> int:
    h = 0xCBF29CE484222325
    for b in data:
        h = ((h ^ b) * 0x100000001B3) & _MASK64
    return h


def _part_to_int(part) -> int:
    """Stable, salt-free integer image of a key part."""
    if part is None:
        return 0x5EED_0000_0000_0001
    if isinstance(part, bool):
        return 0x11 if part else 0x22
    if isinstance(part, int):
        return part & _MASK64
    if isinstance(part, float):
        if part == int(part) and abs(part) < (1 << 52):
            return int(part) & _MASK64          # 3.0 keys like 3
        return _fnv1a64(struct.pack("<d", part))
    if isinstance(part, str):
        return _fnv1a64(part.encode("utf-8"))
    if isinstance(part, bytes):
        return _fnv1a64(part)
    if isinstance(part, (tuple, list)):
        h = 0xA5A5_5A5A_A5A5_5A5A
        for p in part:
            h = _splitmix64(h ^ _part_to_int(p))
        return h
    return _fnv1a64(repr(part).encode("utf-8"))


def _mix(parts: Iterable) -> int:
    """Counter-based mixing of an arbitrary key tuple into 64 bits."""
    h = 0x243F_6A88_85A3_08D3           # pi digits, arbitrary non-zero IV
    for p in parts:
        h = _splitmix64(h ^ _part_to_int(p))
    return _splitmix64(h)


def hash01(*parts) -> float:
    """Deterministic uniform value in [0, 1) from the key ``parts``."""
    return (_mix(parts) >> 11) * _INV_2_53


def gauss(*parts) -> float:
    """Deterministic standard-normal value from the key ``parts``.

    Box-Muller on two independent counter streams derived from the same key, so
    it is as reproducible as :func:`hash01` and needs no state.
    """
    u1 = hash01(*parts, "\x00gauss-u1")
    u2 = hash01(*parts, "\x00gauss-u2")
    u1 = min(max(u1, 1e-12), 1.0 - 1e-12)
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


# --------------------------------------------------------------------------- #
# presets — tuned against refs/specs/feel_truth.md (the re-derived ground truth)
# --------------------------------------------------------------------------- #

#: A relaxed soloist: wide agogic swing, strong accent comb, mixed articulation.
LOOSE: dict = {
    "timing_ms": 10.0, "timing_dist": "t", "timing_df": 4.6, "timing_ar": 0.35,
    "timing_drift_ms": 18.0, "timing_drift_span": 5, "timing_swell": 1.30,
    "velocity": 0.125, "velocity_ar": 0.70,
    "accent_profile": (1.085, 0.945, 1.015, 0.930), "accent_period2": 0.055,
    "timing_profile_ms": (-3.2, 1.8, -0.6, 3.6), "timing_period2_ms": 1.1,
    "gate": 0.10, "articulation": 0.92, "gate_center": 0.98,
    "gate_spread": 1.18, "gate_skew": 1.55, "gate_ar": 0.55,
    "onset_ms": 7.4, "melody_lead_ms": -5.0, "release_ms": 8.0, "seed": 3,
}
#: Tight ensemble playing: the same structure, smaller magnitudes.
TIGHT: dict = {
    "timing_ms": 10.5, "timing_dist": "t", "timing_df": 4.8, "timing_ar": 0.30,
    "timing_drift_ms": 15.0, "timing_drift_span": 5, "timing_swell": 1.30,
    "velocity": 0.108, "velocity_ar": 0.68,
    "accent_profile": (1.070, 0.955, 1.010, 0.945), "accent_period2": 0.045,
    "timing_profile_ms": (-2.2, 1.2, -0.4, 2.4), "timing_period2_ms": 0.8,
    "gate": 0.07, "articulation": 0.88, "gate_center": 0.92,
    "gate_spread": 1.05, "gate_skew": 1.50, "gate_ar": 0.50,
    "onset_ms": 5.8, "melody_lead_ms": -4.6, "release_ms": 4.0, "seed": 11,
}
#: Ahead of the beat: a *graded* metrical anticipation (round 1's ``flat``
#: on/off switch was a two-spike histogram, not a distribution — defect D10).
PUSHED: dict = {
    "timing_ms": 9.0, "timing_dist": "t", "timing_df": 4.6, "timing_ar": 0.35,
    "timing_drift_ms": 16.0, "timing_drift_span": 5, "timing_swell": 1.35,
    "velocity": 0.120, "velocity_ar": 0.76,
    "accent_profile": (1.020, 1.075, 0.955, 1.045), "accent_period2": 0.060,
    "timing_profile_ms": (-1.0, -9.5, 0.5, -8.0), "timing_period2_ms": 1.0,
    "gate": 0.09, "articulation": 0.90, "gate_center": 0.88,
    "gate_spread": 1.12, "gate_skew": 1.45, "gate_ar": 0.52,
    "onset_ms": 6.8, "melody_lead_ms": -4.8, "release_ms": 5.0,
    "on_beats": (), "seed": 7,
}
#: Slow, breathing, pedalled: long releases and a wide held-over tail.
BREATH: dict = {
    "timing_ms": 9.0, "timing_dist": "t", "timing_df": 5.0, "timing_ar": 0.35,
    "timing_drift_ms": 17.0, "timing_drift_span": 6, "timing_swell": 1.40,
    "velocity": 0.124, "velocity_ar": 0.74,
    "accent_profile": (1.075, 0.950, 1.020, 0.940), "accent_period2": 0.050,
    "timing_profile_ms": (-2.8, 2.2, -0.5, 3.2), "timing_period2_ms": 1.0,
    "gate": 0.12, "articulation": 0.94, "gate_center": 1.02,
    "gate_spread": 1.22, "gate_skew": 1.60, "gate_ar": 0.58,
    "onset_ms": 7.8, "melody_lead_ms": -5.4, "release_ms": 14.0, "seed": 5,
}

PRESETS: dict[str, dict] = {
    "loose": LOOSE,
    "tight": TIGHT,
    "pushed": PUSHED,
    "breath": BREATH,
}

#: Values used when a structural field is left at :data:`AUTO`.  They are only
#: reached when the corresponding classic magnitude is non-zero, so a zero spec
#: stays a bit-exact no-op, and a hand-written ``feel { timing: 16ms }`` block
#: (the only syntax ``parse.py`` accepts today — amendment request A1) still
#: gets memory, accents, articulation and melody lead.
AUTO_DEFAULTS: dict = {
    "timing_ar": 0.35,
    "velocity_ar": 0.68,
    "gate_ar": 0.55,
    "accent_profile": (1.075, 0.950, 1.015, 0.940),
    "accent_period2": 0.050,
    "timing_profile_ms": (-2.8, 1.8, -0.5, 3.2),
    "timing_period2_ms": 1.0,
    "timing_drift_ms": 18.0,
    "timing_drift_span": 5,
    "timing_swell": 1.25,
    "articulation": 0.90,
    "melody_lead_ms": -4.2,
}


def preset(name: str) -> FeelSpec:
    """Build a :class:`FeelSpec` from a built-in preset name."""
    try:
        params = PRESETS[str(name).lower()]
    except KeyError:
        opts = ", ".join(sorted(PRESETS))
        raise KeyError(f"unknown feel preset {name!r}; known presets: {opts}") from None
    return FeelSpec(**params)


def feel_spec(spec: "FeelSpec | str | dict | None") -> FeelSpec:
    """Coerce a preset name / dict / spec / None into a :class:`FeelSpec`."""
    if spec is None:
        return FeelSpec()
    if isinstance(spec, FeelSpec):
        return spec
    if isinstance(spec, str):
        return preset(spec)
    return FeelSpec(**spec)


# --------------------------------------------------------------------------- #
# parameter normalisation, validation and warnings  (defects D1, D6, D7)
# --------------------------------------------------------------------------- #

_MIN_DUR_BEATS = 1e-3
_TIMING_MAX_MS = 500.0          # beyond this a "humaniser" is a scrambler
_RELEASE_MAX_MS = 500.0
_ONSET_MAX_MS = 250.0
_AR_MAX = 0.95
_KNOWN_DISTS = ("gauss", "human", "t", "student-t", "studentt", "normal", "iid",
                "gauss-iid", "uniform", "flat", "flat_rand", "rand")


@dataclass
class _P:
    """Normalised, validated parameters — plain finite numbers only."""
    sigma_ms: float = 0.0
    dist: str = "gauss"
    lam: float = 0.0                # log-normal tail-mixture width
    timing_ar: float = 0.0
    timing_rel: float = 0.0
    timing_profile: tuple[float, ...] = ()
    timing_period2: float = 0.0
    drift_ms: float = 0.0
    drift_span: int = 8
    swell: float = 0.0
    vel_frac: float = 0.0
    vel_ar: float = 0.0
    accent: tuple[float, ...] = ()
    accent_period2: float = 0.0
    gate_frac: float = 0.0
    articulation: float = 0.0
    gate_center: float = 0.95
    gate_spread: float = 1.1
    gate_skew: float = 1.55
    gate_ar: float = 0.0
    gate_max: float = 4.0
    release_ms: float = 0.0
    onset_ms: float = 0.0
    lead_ms: float = 0.0
    onset_mode: str = "lead"
    bpb: int = 4
    tatum: float = 0.25
    hand_split: int = 60
    max_shift_ratio: float = 0.90
    on_beats: tuple[int, ...] = ()
    seed: int = 0

    @property
    def active(self) -> bool:
        return bool(self.sigma_ms or self.vel_frac or self.gate_frac
                    or self.articulation or self.release_ms or self.onset_ms
                    or self.lead_ms or self.timing_profile or self.timing_period2
                    or self.drift_ms
                    or self.accent_period2
                    or (self.accent and any(a != 1.0 for a in self.accent)))


def _finite(name: str, value, default: float, warn) -> float:
    """Reject NaN / Inf loudly instead of letting ``max(0.0, nan)`` eat a score."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        warn(f"feel: {name}={value!r} is not a number; using {default}")
        return default
    if math.isnan(v):
        warn(f"feel: {name}=nan is not a usable value; using {default}")
        return default
    if math.isinf(v):
        warn(f"feel: {name}={v} is infinite; using {default}")
        return default
    return v


def _clamp(name: str, v: float, lo: float, hi: float, warn) -> float:
    if v < lo:
        warn(f"feel: {name}={v:g} is below the minimum {lo:g}; clamped to {lo:g}")
        return lo
    if v > hi:
        warn(f"feel: {name}={v:g} is above the maximum {hi:g}; clamped to {hi:g}")
        return hi
    return v


def _unit_frac(name: str, value, warn) -> float:
    """A fraction, with **explicit** units and no cliff at 1.0 (defect D1).

    Accepts ``0.12``, ``"12%"``, ``"12pct"``, ``"0.12"``.  A bare number above
    1.0 is ambiguous (400 % or 4 %?) and is reported, not guessed.
    """
    if isinstance(value, str):
        txt = value.strip().lower().replace(" ", "")
        pct = txt.endswith("%") or txt.endswith("pct")
        txt = txt.rstrip("%").removesuffix("pct")
        v = _finite(name, txt, 0.0, warn)
        if pct:
            v = v / 100.0
        elif v > 1.0:
            warn(f"feel: {name}={value!r} is ambiguous — write '{v:g}%' for "
                 f"{v:g} per cent or {v / 100.0:g} for the fraction; "
                 f"clamped to 1.0 (100%)")
            v = 1.0
    else:
        v = _finite(name, value, 0.0, warn)
        if v > 1.0:
            warn(f"feel: {name}={v:g} is ambiguous — a fraction must be <= 1.0; "
                 f"write '{v:g}%' if you meant {v:g} per cent, or "
                 f"{v / 100.0:g}; clamped to 1.0 (100%)")
            v = 1.0
    if v < 0.0:
        warn(f"feel: {name}={v:g} is negative; the sign of a jitter width is "
             f"meaningless, using {abs(v):g}")
        v = abs(v)
    if v > 1.0:                     # an *explicit* over-100 % unit: not
        warn(f"feel: {name}={value!r} is above the maximum 100%; "  # ambiguous,
             f"clamped to 1.0 (100%)")                             # just wrong
        v = 1.0
    return v


def _lam_for_df(df: float) -> float:
    """Log-normal scale-mixture width whose excess kurtosis is 6/(df-4)."""
    if not math.isfinite(df) or df >= 400.0:
        return 0.0
    target = 6.0 / (df - 4.0)
    return math.sqrt(math.log1p(target / 3.0) / 4.0)


def _profile(name: str, value, warn) -> tuple[float, ...]:
    if value is None:
        return ()
    try:
        vals = [_finite(f"{name}[{i}]", v, 1.0, warn) for i, v in enumerate(value)]
    except TypeError:
        warn(f"feel: {name}={value!r} must be a sequence of numbers; ignored")
        return ()
    return tuple(vals)


def normalise(spec: "FeelSpec | str | dict | None",
              warn: Optional[Callable[[str], None]] = None) -> tuple[_P, list[str]]:
    """Validate and resolve a spec into plain finite numbers.

    Returns ``(_P, warnings)``.  Every message names the offending parameter and
    its value.  Nothing is silently guessed: unknown distributions, ambiguous
    percentages, NaN, Inf, negative widths and absurd magnitudes all warn.
    """
    msgs: list[str] = []

    def _warn(msg: str) -> None:
        msgs.append(msg)
        if warn is not None:
            warn(msg)

    sp = feel_spec(spec)
    p = _P()

    # --- distribution name (defect D7: no more silent fallback) ---------- #
    dist = sp.timing_dist
    df = _finite("timing_df", sp.timing_df, 5.0, _warn)
    if dist.startswith("t") and dist not in ("t", "student-t", "studentt"):
        tail = dist[1:].lstrip("-_")
        try:
            df = float(tail)
            dist = "t"
        except ValueError:
            pass
    if dist not in _KNOWN_DISTS:
        _warn(f"feel: timing_dist={sp.timing_dist!r} is not a known distribution "
              f"({', '.join(_KNOWN_DISTS)}); using 'gauss'")
        dist = "gauss"
    if dist in ("student-t", "studentt"):
        dist = "t"
    if dist in ("flat_rand", "rand"):
        dist = "uniform"
    if dist in ("normal", "iid", "gauss-iid"):
        p.dist, p.lam = "normal", 0.0
    elif dist in ("gauss", "human", "t"):
        p.dist = "human"
        if df <= 4.0:
            _warn(f"feel: timing_df={df:g} is below the minimum 4.2 (the excess "
                  f"kurtosis 6/(df-4) would not exist); clamped to 4.2")
            df = 4.2
        p.lam = _lam_for_df(df)
    else:
        p.dist = dist                       # uniform | flat

    # --- magnitudes ------------------------------------------------------ #
    t_ms = _finite("timing", sp.timing_ms, 0.0, _warn)
    t_ms = _clamp("timing", t_ms, -_TIMING_MAX_MS, _TIMING_MAX_MS, _warn)
    p.sigma_ms = t_ms
    p.timing_rel = max(0.0, _finite("timing_rel", sp.timing_rel, 0.0, _warn))
    p.vel_frac = _unit_frac("velocity", sp.velocity, _warn)
    p.gate_frac = _unit_frac("gate", sp.gate, _warn)
    p.release_ms = _clamp("release", _finite("release", sp.release_ms, 0.0, _warn),
                          0.0, _RELEASE_MAX_MS, _warn)
    p.onset_ms = _clamp("onset", abs(_finite("onset", sp.onset_ms, 0.0, _warn)),
                        0.0, _ONSET_MAX_MS, _warn)
    p.onset_mode = sp.onset_mode if sp.onset_mode in ("lead", "legacy") else "lead"
    if sp.onset_mode not in ("lead", "legacy", "spread", "per-voice-spread"):
        _warn(f"feel: onset_mode={sp.onset_mode!r} is unknown "
              f"(lead | legacy); using 'lead'")

    def _auto(name: str, value):
        return AUTO_DEFAULTS[name] if value is AUTO else value

    # --- memory ---------------------------------------------------------- #
    timing_live = bool(p.sigma_ms) and p.dist != "flat"
    p.timing_ar = _clamp("timing_ar",
                         _finite("timing_ar", _auto("timing_ar", sp.timing_ar), 0.0, _warn),
                         0.0, _AR_MAX, _warn) if timing_live and p.dist == "human" else 0.0
    p.vel_ar = _clamp("velocity_ar",
                      _finite("velocity_ar", _auto("velocity_ar", sp.velocity_ar),
                              0.0, _warn), 0.0, _AR_MAX, _warn) if p.vel_frac else 0.0

    # --- metrical profiles ----------------------------------------------- #
    def _auto_timing(name: str, value):
        """``flat`` is a groove template, not humanisation: it stays a constant
        signed shift, so the *automatic* structure is not switched on for it.
        Explicit values are still honoured."""
        if value is AUTO and p.dist == "flat":
            return () if isinstance(AUTO_DEFAULTS[name], tuple) else 0.0
        return _auto(name, value)

    if p.sigma_ms or p.vel_frac:
        p.timing_profile = _profile("timing_profile_ms",
                                    _auto_timing("timing_profile_ms",
                                                 sp.timing_profile_ms), _warn)
        p.timing_profile = tuple(
            _clamp("timing_profile_ms", v, -_TIMING_MAX_MS, _TIMING_MAX_MS, _warn)
            for v in p.timing_profile)
        p.timing_period2 = _clamp(
            "timing_period2_ms",
            _finite("timing_period2_ms", _auto_timing("timing_period2_ms",
                                                      sp.timing_period2_ms), 0.0, _warn),
            -_TIMING_MAX_MS, _TIMING_MAX_MS, _warn)
    if timing_live and p.dist == "human":
        p.drift_ms = _clamp("timing_drift_ms",
                            abs(_finite("timing_drift_ms",
                                        _auto("timing_drift_ms", sp.timing_drift_ms),
                                        0.0, _warn)),
                            0.0, _TIMING_MAX_MS, _warn)
        p.drift_span = int(round(_clamp(
            "timing_drift_span",
            _finite("timing_drift_span", _auto("timing_drift_span",
                                               sp.timing_drift_span), 8.0, _warn),
            2.0, 64.0, _warn)))
        p.swell = _clamp("timing_swell",
                         abs(_finite("timing_swell",
                                     _auto("timing_swell", sp.timing_swell), 0.0, _warn)),
                         0.0, 3.0, _warn)
    if p.vel_frac:
        prof = _profile("accent_profile", _auto("accent_profile", sp.accent_profile), _warn)
        prof = tuple(_clamp("accent_profile", v, 0.1, 4.0, _warn) for v in prof)
        if prof:
            mean = sum(prof) / len(prof)
            prof = tuple(v / mean for v in prof) if mean > 0 else ()
        p.accent = prof
        p.accent_period2 = _clamp(
            "accent_period2",
            _finite("accent_period2", _auto("accent_period2", sp.accent_period2),
                    0.0, _warn), -0.5, 0.5, _warn)

    # --- articulation ----------------------------------------------------- #
    art_src = _auto("articulation", sp.articulation) if (p.gate_frac or
                                                         sp.articulation is not AUTO) else 0.0
    p.articulation = _clamp("articulation",
                            _finite("articulation", art_src, 0.0, _warn), 0.0, 1.0, _warn)
    p.gate_center = _clamp("gate_center",
                           _finite("gate_center", sp.gate_center, 0.95, _warn),
                           0.05, 4.0, _warn)
    p.gate_spread = _clamp("gate_spread",
                           abs(_finite("gate_spread", sp.gate_spread, 1.1, _warn)),
                           0.0, 3.0, _warn)
    p.gate_skew = _clamp("gate_skew",
                         abs(_finite("gate_skew", sp.gate_skew, 1.55, _warn)),
                         0.1, 5.0, _warn)
    p.gate_max = _clamp("gate_max", _finite("gate_max", sp.gate_max, 4.0, _warn),
                        1.0, 16.0, _warn)
    p.gate_ar = _clamp("gate_ar",
                       _finite("gate_ar", _auto("gate_ar", sp.gate_ar), 0.0, _warn),
                       0.0, _AR_MAX, _warn) if p.articulation or p.gate_frac else 0.0

    # --- chord / melody lead ---------------------------------------------- #
    if p.onset_ms and p.onset_mode == "lead":
        p.lead_ms = _clamp("melody_lead_ms",
                           _finite("melody_lead_ms",
                                   _auto("melody_lead_ms", sp.melody_lead_ms), 0.0, _warn),
                           -_TIMING_MAX_MS, _TIMING_MAX_MS, _warn)

    # --- metre / bounds ---------------------------------------------------- #
    p.bpb = int(_clamp("beats_per_bar",
                       _finite("beats_per_bar", sp.beats_per_bar, 4, _warn),
                       1, 64, _warn))
    p.tatum = _clamp("tatum_beats", _finite("tatum_beats", sp.tatum_beats, 0.25, _warn),
                     1e-3, 8.0, _warn)
    p.hand_split = int(_clamp("hand_split",
                              _finite("hand_split", sp.hand_split, 60, _warn),
                              0, 127, _warn))
    p.max_shift_ratio = _clamp("max_shift_ratio",
                               _finite("max_shift_ratio", sp.max_shift_ratio, 0.90, _warn),
                               0.0, 4.0, _warn)
    p.on_beats = tuple(sp.on_beats)
    p.seed = int(_finite("seed", sp.seed, 0, _warn))
    return p, msgs


# --------------------------------------------------------------------------- #
# application
# --------------------------------------------------------------------------- #

def _hand(pitch: int, split: int) -> str:
    return "hi" if pitch >= split else "lo"


def _positions(start: float, bpb: int, tatum: float) -> tuple[int, int]:
    """(1-based beat of the bar, tatum index) of a nominal onset."""
    b = int(math.floor(start + 1e-9))
    beat = b % bpb + 1
    tat = int(round(start / tatum)) if tatum > 0 else 0
    return beat, tat


def _drift_ctl(key_seed: int, skey, k: int, amp_ms: float, swell: float) -> float:
    """One control point of the agogic tempo curve (deterministic in the key)."""
    a = amp_ms
    if swell:
        a *= math.exp(swell * gauss(key_seed, skey, k, "drift-swell")
                      - 0.5 * swell * swell)
    return a * gauss(key_seed, skey, k, "drift-ctl")


def _drift_at(key_seed: int, skey, ci: int, span: int,
              amp_ms: float, swell: float) -> float:
    k, f = divmod(ci, span)
    if f == 0:
        return _drift_ctl(key_seed, skey, k, amp_ms, swell)
    w = f / float(span)
    return ((1.0 - w) * _drift_ctl(key_seed, skey, k, amp_ms, swell)
            + w * _drift_ctl(key_seed, skey, k + 1, amp_ms, swell))


def _ar_step(prev: float, phi: float, eps: float) -> float:
    """One stationary AR(1)/discrete-OU step with unit marginal variance."""
    if phi <= 0.0:
        return eps
    return phi * prev + math.sqrt(max(0.0, 1.0 - phi * phi)) * eps


def apply_feel(notes: list[Note], spec: FeelSpec, tempo: float, seed: int,
               on_warning: Optional[Callable[[str], None]] = None) -> None:
    """Humanise ``notes`` in place (``start`` / ``dur`` / ``velocity``).

    Deterministic: every innovation is a pure function of
    ``(seed, spec.seed, stave, hand, voice, start, pitch, occurrence, field)``,
    and the AR(1) recursions run over a deterministic ordering, so the same seed
    gives byte-identical output across interpreter invocations.

    ``on_warning`` (optional) receives each parameter warning as a string; every
    warning is also raised through :mod:`warnings` as a :class:`FeelWarning`.
    """
    if not notes:
        return
    p, msgs = normalise(spec)
    for m in msgs:
        if on_warning is not None:
            on_warning(m)
        warnings.warn(m, FeelWarning, stacklevel=2)
    if not p.active:
        return                              # bit-exact no-op

    tempo = float(tempo) if tempo else 120.0
    ms_to_beats = tempo / 60000.0
    beats_to_ms = 1.0 / ms_to_beats
    key_seed = (int(seed) & _MASK64) ^ _splitmix64(p.seed & _MASK64)

    # ---- deterministic geometry snapshot (nominal, pre-perturbation) ---- #
    nominal = [(float(n.start), float(n.dur)) for n in notes]
    last_start = max(s for s, _d in nominal)
    piece_end = max(s + d for s, d in nominal)

    order = sorted(range(len(notes)),
                   key=lambda i: (str(notes[i].stave), _hand(int(notes[i].pitch),
                                                             p.hand_split),
                                  round(nominal[i][0], 6), int(notes[i].pitch),
                                  str(notes[i].voice), i))
    streams: dict[tuple, list[int]] = {}
    for i in order:
        streams.setdefault((str(notes[i].stave),
                            _hand(int(notes[i].pitch), p.hand_split)), []).append(i)

    # ---- one agogic tempo curve per stave, shared by both hands --------- #
    # The two hands of a player are not two independent tempos: they follow a
    # common rubato.  Indexing the drift by the *stave's* cluster timeline (not
    # the per-hand one) keeps a chord that straddles ``hand_split`` together.
    stave_ci: dict[tuple, int] = {}
    _by_stave: dict[str, set] = {}
    for i in range(len(notes)):
        _by_stave.setdefault(str(notes[i].stave), set()).add(round(nominal[i][0], 6))
    for stave, times in _by_stave.items():
        for k, t in enumerate(sorted(times)):
            stave_ci[(stave, t)] = k

    # ---- per-note key with an occurrence counter (defect D5) ------------ #
    seen: dict[tuple, int] = {}
    nkey: dict[int, tuple] = {}
    for skey, idxs in streams.items():
        for i in idxs:
            n = notes[i]
            base = (key_seed, skey, str(n.voice), round(nominal[i][0], 4), int(n.pitch))
            occ = seen.get(base, 0)
            seen[base] = occ + 1
            nkey[i] = base + (occ,)

    clipped: dict[str, int] = {}

    def _note_clip(param: str) -> None:
        clipped[param] = clipped.get(param, 0) + 1

    # ---- chord terms: melody lead + two-sided scatter (defect D8) -------- #
    chord_ms = [0.0] * len(notes)
    if p.onset_ms:
        groups: dict[tuple, list[int]] = {}
        for i in order:
            groups.setdefault((str(notes[i].stave), round(nominal[i][0], 4)),
                              []).append(i)
        for gkey, members in groups.items():
            if len(members) < 2:
                continue                    # a single note has no chord spread
            if p.onset_mode == "legacy":
                for i in members:
                    chord_ms[i] = p.onset_ms * hash01(*nkey[i], "onset")
                continue
            ranks = sorted(members, key=lambda i: (int(notes[i].pitch), i))
            k = len(ranks)
            for r, i in enumerate(ranks):
                c = (2.0 * r / (k - 1)) - 1.0          # -1 bottom .. +1 top
                chord_ms[i] = (p.lead_ms * c
                               + p.onset_ms * gauss(*nkey[i], "onset"))

    # ---- pass 1: onsets ------------------------------------------------- #
    new_start = [s for s, _d in nominal]
    for skey, idxs in streams.items():
        # cluster the stream by nominal onset: a chord moves as a unit
        cl_order: list[float] = []
        cl_members: dict[float, list[int]] = {}
        for i in idxs:
            t = round(nominal[i][0], 6)
            if t not in cl_members:
                cl_members[t] = []
                cl_order.append(t)
            cl_members[t].append(i)
        iois = [b - a for a, b in zip(cl_order, cl_order[1:]) if b > a]
        tatum_ms = ((sorted(iois)[len(iois) // 2] * beats_to_ms) if iois
                    else p.tatum * beats_to_ms)
        sigma = (p.timing_rel * tatum_ms) if p.timing_rel > 0 else p.sigma_ms

        state = 0.0
        prev_new: Optional[float] = None
        for ci, t in enumerate(cl_order):
            beat, tat = _positions(t, p.bpb, p.tatum)
            dev = 0.0
            gate_on = (not p.on_beats) or (beat in p.on_beats)
            # A passage-length "swell" scales the whole random part.  Real
            # playing is a scale mixture: calm bars and turbulent bars.  Measured
            # with the reference estimator it is *sub*-gaussian inside a single
            # isochronous run (kurtosis -0.3 .. -0.8) and strongly leptokurtic
            # once runs are pooled (+2.9 .. +7.8).  A constant variance cannot
            # produce that, whatever the per-note distribution is.
            if gate_on and (sigma or p.drift_ms):
                rnd = 0.0
                if sigma:
                    if p.dist == "flat":
                        rnd += sigma
                        scale = 1.0
                    elif p.dist == "uniform":
                        rnd += sigma * (2.0 * hash01(key_seed, skey, t, "timing") - 1.0)
                    else:
                        eps = gauss(key_seed, skey, t, "timing-eps")
                        state = _ar_step(state, p.timing_ar, eps)
                        z = state
                        if p.lam:
                            u = gauss(key_seed, skey, t, "timing-scale")
                            z *= math.exp(p.lam * u - p.lam * p.lam)
                        rnd += sigma * z
                if p.drift_ms:
                    # Agogic drift as a piecewise-linear tempo curve: control
                    # points every ``drift_span`` onsets, each with its own
                    # log-normally distributed amplitude (``timing_swell`` is the
                    # log sd, so some passages are three times freer than
                    # others).  Because the curve is linear between controls the
                    # inter-onset intervals stay stable, so a free passage still
                    # reads as a pulse; the amplitude mixture is what makes the
                    # deviations leptokurtic.
                    rnd += _drift_at(key_seed, skey[0],
                                     stave_ci[(skey[0], t)], p.drift_span,
                                     p.drift_ms, p.swell)
                dev += rnd
            if p.timing_profile:
                dev += p.timing_profile[(beat - 1) % len(p.timing_profile)]
            if p.timing_period2:
                dev += p.timing_period2 * (1.0 if tat % 2 == 0 else -1.0)

            # ---- bound the shift (defect D2) ---------------------------- #
            # The window is [t - limit, t + limit] intersected with "strictly
            # after the previous perturbed onset" and "not past the end of the
            # piece".  Because the previous bound uses the *already perturbed*
            # neighbour, the note order and a minimum separation are guaranteed
            # for any parameter value, however absurd, without needing the shift
            # to be smaller than half the gap.
            prev_gap = (t - cl_order[ci - 1]) if ci > 0 else None
            next_gap = (cl_order[ci + 1] - t) if ci + 1 < len(cl_order) else None
            gaps = [g for g in (prev_gap, next_gap) if g is not None and g > 0]
            gap = min(gaps) if gaps else 1.0
            limit_beats = p.max_shift_ratio * gap
            min_sep = max(1e-4, 0.02 * gap)
            lo = max(0.0, t - limit_beats)
            if prev_new is not None:
                lo = max(lo, prev_new + min_sep)
            hi = min(t + limit_beats, max(last_start, piece_end))
            hi = max(hi, lo)
            latest = lo
            for i in cl_members[t]:
                shift = dev + chord_ms[i]
                s = t + shift * ms_to_beats
                if s < lo or s > hi:
                    _note_clip("timing" if abs(dev) >= abs(chord_ms[i]) else "onset")
                    s = min(hi, max(lo, s))
                new_start[i] = s
                latest = max(latest, s)
            prev_new = latest

    # ---- pass 2: velocity, articulation, release ------------------------ #
    tail_allow = float(p.bpb)
    for skey, idxs in streams.items():
        seq = sorted(idxs, key=lambda i: (new_start[i], int(notes[i].pitch), i))
        v_state = 0.0
        g_state = 0.0
        for pos, i in enumerate(seq):
            n = notes[i]
            key = nkey[i]
            beat, tat = _positions(nominal[i][0], p.bpb, p.tatum)

            # --- velocity: AR(1) jitter x metrical accent ---------------- #
            if p.vel_frac or p.accent or p.accent_period2:
                v_state = _ar_step(v_state, p.vel_ar, gauss(*key, "velocity-eps"))
                acc = 1.0
                if p.accent:
                    acc *= p.accent[(beat - 1) % len(p.accent)]
                if p.accent_period2:
                    acc *= 1.0 + p.accent_period2 * (1.0 if tat % 2 == 0 else -1.0)
                v = float(n.velocity) * acc * (1.0 + p.vel_frac * v_state)
                iv = int(round(v))
                if iv < 1 or iv > 127:
                    _note_clip("velocity")
                n.velocity = min(127, max(1, iv))

            # --- articulation: gate ratio with memory -------------------- #
            dur = nominal[i][1]
            nxt = seq[pos + 1] if pos + 1 < len(seq) else None
            ioi = (new_start[nxt] - new_start[i]) if nxt is not None else None
            if p.articulation or p.gate_frac:
                g_state = _ar_step(g_state, p.gate_ar, gauss(*key, "gate-eps"))
            if p.articulation and ioi is not None and ioi > 1e-9:
                side = p.gate_spread * (p.gate_skew if g_state > 0 else 1.0)
                target = p.gate_center * math.exp(side * g_state)
                r0 = max(dur / ioi, 1e-6)
                w = p.articulation
                ratio = math.exp((1.0 - w) * math.log(r0) + w * math.log(target))
                if p.gate_frac:
                    ratio *= max(0.05, 1.0 + p.gate_frac * gauss(*key, "gate"))
                ratio = min(ratio, p.gate_max)
                if nxt is not None and int(notes[nxt].pitch) == int(n.pitch):
                    ratio = min(ratio, 0.97)      # never overlap the same key
                dur = ratio * ioi
            elif p.gate_frac:
                dur *= 1.0 + p.gate_frac * gauss(*key, "gate")

            if p.release_ms:
                jitter = 1.0 + 0.5 * (2.0 * hash01(*key, "release") - 1.0)
                dur += p.release_ms * jitter * ms_to_beats
            if nxt is not None and int(notes[nxt].pitch) == int(n.pitch) \
                    and ioi is not None and ioi > 1e-9:
                dur = min(dur, 0.97 * ioi)
            end_cap = piece_end + tail_allow
            if new_start[i] + dur > end_cap:
                _note_clip("gate")
                dur = max(_MIN_DUR_BEATS, end_cap - new_start[i])
            n.dur = max(_MIN_DUR_BEATS, dur)

    for i, n in enumerate(notes):
        n.start = new_start[i]

    # ---- one warning per clamped parameter, naming the value ------------- #
    floor = max(3, int(0.02 * len(notes)))      # a handful of clipped notes is
    _why = {                                    # normal; a systematic clip is not
        "timing": "to keep the note order and the piece length intact",
        "onset": "to keep the chord inside the gap to its neighbours",
        "velocity": "to stay inside the MIDI velocity range 1..127",
        "gate": f"at the gate_max ratio {p.gate_max:g}",
    }
    for param, count in sorted(clipped.items()):
        value = {"timing": p.sigma_ms, "onset": p.onset_ms,
                 "velocity": p.vel_frac, "gate": p.gate_max}.get(param, 0.0)
        if count < floor or not value:
            continue
        msg = (f"feel: {param}={value:g} is too large for this music — it was "
               f"clamped on {count} of {len(notes)} notes "
               f"{_why.get(param, 'to keep the score valid')}")
        if on_warning is not None:
            on_warning(msg)
        warnings.warn(msg, FeelWarning, stacklevel=2)
