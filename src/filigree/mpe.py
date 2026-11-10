"""MPE renderer: ir.Score -> MPE-shaped MIDI (SMF type 1 or raw event stream).

Conformance target: MMA/AMEI RP-053 (MIDI Polyphonic Expression), as digested in
``research/mpe_technical.md``.  Every rule implemented here maps to a bullet of
``refs/BAR.md`` section P4:

* MPE Configuration Message (RPN 00 06) on the Lower-Zone master (MIDI ch 1,
  0-based 0) with ``mm = len(members)``, plus ``mm = 0`` on MIDI ch 16 to switch
  the Upper Zone off.
* RPN 0 (pitch-bend sensitivity) on the master (2 st) and on **every** member
  channel (``opts.bend_range``), transmitted **MSB first** (CC101 before CC100)
  and closed with a null RPN (127/127).
* Per note the event order is exactly ``pitch-bend -> CC74 -> pressure(0) ->
  note-on``; ``pressure(0)`` immediately precedes ``note_off``; no per-note
  expression is ever emitted on a channel between a note-off and the next
  note-on on that channel.  **This is unconditional**: a note that reuses a
  channel a previous note just released, and even a note that has to share a
  channel with a sounding note, still gets its full preamble and its own
  pressure-0 teardown (round-2 fix; see NOTES_P4.md).
* Channel allocation: fewest active notes, tie-break oldest release, with
  same-pitch affinity.  A note-end is treated as *exclusive*: a note starting
  exactly where another ends may reuse that channel.
* Expression grid: 5 ms for pitch, 10 ms for pressure/timbre/CC.  Thinning is
  **zero-order-hold** bounded, not interpolation-bounded (round-2 fix):

      RECEIVER MODEL.  MIDI 1.0 pitch bend / channel pressure / CC are
      hold-last-value controls.  A receiver holds the last transmitted value
      until the next message arrives; nothing in RP-053 or in the MIDI 1.0
      spec says a receiver interpolates between them.

      GUARANTEE.  After thinning, for every grid sample time ``t_k`` inside a
      note's lifetime, ``|value_held(t_k) - value_true(t_k)| <= tol``, where
      ``tol`` is ``opts.bend_tol_cents`` (default 3.0 cents, converted to
      pitch-bend LSB for the active member range) for the bend lane and
      ``opts.cc_tol_lsb`` (default 1 LSB ~= 1/127 of full scale) for
      pressure / CC74 / other CC lanes.  Between grid samples the residual is
      bounded by the curve's own motion across one emission interval - the
      sampler's resolution floor, reported by ``tools/audit_mpe.py`` as
      ``grid_floor_cents``; the grid interval is the minimum spacing and is
      never subdivided.

      RATE CEILING.  BAR P4 also caps density at 250 expression
      events/second/channel.  When a channel's thinned demand exceeds
      ``opts.max_expr_per_sec`` the tolerance for that channel is escalated
      until it fits (and a warning is recorded), because at a fixed event
      budget a hold receiver's accuracy is bounded by
      ``max|dv/dt| / rate`` - the two bullets are not jointly satisfiable for
      arbitrarily fast gestures.  A hard governor is applied as a backstop.
* SMF type 1, 960 PPQN, one track per stave plus a conductor track.

Robustness policy (round-2 fix, documented so it can be tested):

* Non-finite curve data (``inf`` / ``-inf`` / ``NaN``) is **dropped**, never
  written.
* ``NaN`` is the **gap sentinel** of ``ir.Curve`` ("write no data from here
  until the next non-NaN point") - normal, expected resolver output, so it is
  handled **silently**: no warning.  The renderer samples each
  ``Curve.spans()`` run separately and emits nothing inside a gap; a hold
  receiver therefore keeps the last value it was sent, which is exactly "no
  data".  A lane is never deleted because part of it is a gap.
* ``+-inf`` (and any other non-finite that is not NaN) is an **anomaly**: it is
  dropped *and* appends a warning to ``Score.warnings``.
* A lane whose every breakpoint is non-finite falls back to the lane default
  (bend -> detune, CC74 -> 64, pressure -> nothing).
* A zero-length (or negative-length) note is given a minimum duration of one
  tick and a warning; it is never silently dropped.
* A bend request outside the member range is clamped (never wrapped) and a
  warning naming the note and the requested value is appended.

Owned by piece P4.  Imports ``ir``/``errors`` read-only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Optional

from . import errors
from .ir import AMP, BEND, PAN, PRESS, TIMBRE, Curve, Note, Score

# --------------------------------------------------------------------------- #
# constants
# --------------------------------------------------------------------------- #

LOWER_MASTER = 0            # 0-based MIDI channel 1
UPPER_MASTER = 15           # 0-based MIDI channel 16
CC_BANK_RPN_MSB = 101
CC_BANK_RPN_LSB = 100
CC_DATA_MSB = 6
CC_DATA_LSB = 38
CC_RESET_ALL = 121
CC_ALL_SOUND_OFF = 120
CC_SUSTAIN = 64
CC_ALL_NOTES_OFF = 123
CC_TIMBRE = 74
CC_AMP = 11
CC_PAN = 10
RPN_NULL = 127

DEFAULT_TIMBRE = 64         # RP-053 "initial-64" convention
MASTER_BEND_RANGE = 2       # semitones, zone bend default

#: CC numbers that are zone/RPN configuration, not per-note expression.  Kept
#: identical to the critic's independent checker so densities are comparable.
CONFIG_CCS = (98, 99, 100, 101, 6, 38, 120, 121, 123)

# stream phases (sort priority *within* one tick)
PH_CONFIG = 0
PH_NOTE_OFF = 1
PH_EXPR = 2
PH_NOTE_ON = 3

# priority inside the note-on group -> the mandated preamble order
_ON_PRIO = {"bend": 0, "cc": 1, "press": 2, "note_on": 3}

#: how many individual warnings of one category are listed before they are
#: collapsed into a single count.
WARN_LIST_LIMIT = 6


@dataclass
class MpeOptions:
    bend_range: float = 48.0
    ppq: int = 960
    grid_ms: float = 10.0
    pitch_grid_ms: float = 5.0
    deadband_lsb: int = 2
    members: tuple[int, ...] = tuple(range(1, 16))   # 0-based ch 1..15 == MIDI 2..16
    emit_config: bool = True
    one_track_per_stave: bool = True
    # --- round 2: hold-error budget + rate ceiling ------------------------- #
    bend_tol_cents: float = 3.0      # hold tolerance for the bend lane
    cc_tol_lsb: int = 1              # hold tolerance for 7-bit lanes (~1/127)
    max_expr_per_sec: float = 240.0  # per-channel ceiling (BAR bullet is 250)


# --------------------------------------------------------------------------- #
# numeric helpers (research/mpe_technical.md §6.1)
# --------------------------------------------------------------------------- #

def _finite(v) -> bool:
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def semitones_to_bend(st: float, bend_range: float = 48.0) -> int:
    """Semitones -> signed 14-bit pitchwheel value (-8192..8191), clamped.

    Non-finite input can never reach the wire: ``NaN`` and ``+-inf`` are mapped
    to centre / the range limits instead of raising ``OverflowError``.
    """
    if bend_range <= 0:
        return 0
    try:
        st = float(st)
    except (TypeError, ValueError):
        return 0
    if math.isnan(st):
        return 0
    if math.isinf(st):
        return 8191 if st > 0 else -8192
    v = int(round(st / float(bend_range) * 8192.0))
    return max(-8192, min(8191, v))


def bend_to_semitones(v: int, bend_range: float = 48.0) -> float:
    """Inverse of :func:`semitones_to_bend` (exact, no clamping)."""
    return v / 8192.0 * float(bend_range)


def bend_bytes(v: int) -> tuple[int, int]:
    """Signed pitchwheel value -> (lsb, msb) wire bytes for status ``En``."""
    u = max(0, min(16383, int(v) + 8192))
    return u & 0x7F, (u >> 7) & 0x7F


def cents_per_bend_lsb(bend_range: float) -> float:
    """Pitch resolution of one pitch-bend LSB, in cents."""
    if bend_range <= 0:
        return 0.0
    return float(bend_range) * 100.0 / 8192.0


def bend_tol_lsb(bend_range: float, tol_cents: float) -> int:
    """Hold tolerance in cents -> tolerance in pitch-bend LSB.

    Half an LSB is reserved for the quantisation of the *true* value onto the
    14-bit pitch-bend grid, so that a stream thinned to this tolerance is within
    ``tol_cents`` of the continuous curve, not merely of its quantised samples.
    """
    cpl = cents_per_bend_lsb(bend_range)
    if cpl <= 0:
        return 0
    return max(0, int(math.floor(float(tol_cents) / cpl - 0.5)))


def _u7(x: float) -> int:
    if not _finite(x):
        return 0
    return max(0, min(127, int(round(x))))


def _unipolar_to_7bit(v: float) -> int:
    return _u7(float(v) * 127.0) if _finite(v) else 0


# --------------------------------------------------------------------------- #
# thinning: zero-order-hold error budget (research/mpe_technical.md §6.3 +
# the round-2 correction note appended to that section)
# --------------------------------------------------------------------------- #

def thin(frames: list[tuple[float, int]], tol: int = 2, min_dt: float = 0.0,
         force_idx: Iterable[int] = ()) -> list[tuple[float, int]]:
    """Greedy hold-error thinning.

    ``frames`` is ``[(time, int_value)]``, monotonic in time, already sampled on
    the emission grid.  The result is the subsequence a *hold-last-value*
    receiver needs so that at every input frame time ``t_k``

        ``|held(t_k) - frames[k].value| <= tol``

    The first frame is always kept (it is the mandated note-on preamble value).
    A frame is emitted as late as possible: when frame ``i`` would break the
    budget, the *last frame still inside the budget* is emitted instead, which
    is what bounds the error by ``tol`` rather than ``tol + one step``.  Local
    extrema are emitted at their own time so peaks are never shaved.
    ``min_dt`` is the minimum spacing (the grid interval); it is never
    subdivided.  ``force_idx`` indices are always emitted at their own time.
    """
    force = set(force_idx)
    n = len(frames)
    if n <= 1:
        return list(frames)
    tol = max(0, int(tol))
    out = [frames[0]]
    held_t, held_v = frames[0]
    prev: Optional[tuple[float, int]] = None   # last frame seen, inside budget
    i = 1
    while i < n:
        t, v = frames[i]
        must = i in force
        if not must and 0 < i < n - 1:
            pv = frames[i - 1][1]
            nv = frames[i + 1][1]
            if (v - pv) * (nv - v) < 0 and abs(v - held_v) * 2 > tol:
                must = True                     # local extremum worth keeping
        if not (must or abs(v - held_v) > tol):
            prev = (t, v)
            i += 1
            continue
        cand: Optional[tuple[float, int]] = None
        if not must and prev is not None and prev[0] - held_t >= min_dt - 1e-12:
            cand = prev
        elif t - held_t >= min_dt - 1e-12:
            cand = (t, v)
        if cand is None:                        # spacing forbids: keep holding
            prev = (t, v)
            i += 1
            continue
        if cand[1] != held_v or must:
            out.append(cand)
        held_t, held_v = cand
        prev = None
        if cand[0] == t:
            i += 1
    return out


def hold_error(frames: list[tuple[float, int]],
               kept: list[tuple[float, int]]) -> int:
    """Max |held - true| over ``frames`` given the emitted subsequence ``kept``."""
    if not frames or not kept:
        return 0
    worst = 0
    j = 0
    held = kept[0][1]
    for t, v in frames:
        while j + 1 < len(kept) and kept[j + 1][0] <= t + 1e-12:
            j += 1
            held = kept[j][1]
        worst = max(worst, abs(v - held))
    return worst


# --------------------------------------------------------------------------- #
# warnings
# --------------------------------------------------------------------------- #

def _warn_once(score: Score, message: str) -> None:
    """Append ``message`` to ``score.warnings`` unless it is already there.

    ``_build_events`` may run several times for one score (``render_stats`` then
    ``write_midi``); the warning list must not grow each time.
    """
    tmp: list[str] = []
    errors.warn(tmp, message, path=score.path, kind="mpe")
    for text in tmp:
        if text not in score.warnings:
            score.warnings.append(text)


class _Warns:
    """Category-bucketed warning collector with a listing budget."""

    def __init__(self, score: Score) -> None:
        self.score = score
        self.counts: dict[str, int] = {}

    def add(self, category: str, message: str) -> None:
        n = self.counts.get(category, 0) + 1
        self.counts[category] = n
        if n <= WARN_LIST_LIMIT:
            _warn_once(self.score, message)

    def finish(self) -> None:
        for cat in sorted(self.counts):
            n = self.counts[cat]
            if n > WARN_LIST_LIMIT:
                _warn_once(self.score,
                           "MPE: %s occurred %d times in total (%d listed above)"
                           % (cat, n, WARN_LIST_LIMIT))


# --------------------------------------------------------------------------- #
# channel allocation (RP-053 §1.5)
# --------------------------------------------------------------------------- #

@dataclass
class _Alloc:
    members: tuple[int, ...]
    active: dict = field(default_factory=dict)     # ch -> {(pitch, end_beat, id)}
    last_off: dict = field(default_factory=dict)   # ch -> beat of last release
    last_note: dict = field(default_factory=dict)  # ch -> last pitch played

    def __post_init__(self) -> None:
        for ch in self.members:
            self.active.setdefault(ch, set())
            self.last_off.setdefault(ch, -1.0)
            self.last_note.setdefault(ch, None)

    def retire(self, now: float) -> None:
        """Release every note that has finished at or before ``now``.

        Note-ends are **exclusive** (round-2 fix): a note that starts exactly
        where another ends may reuse that channel.  Ordering inside the tick
        (note-off teardown before note-on preamble) keeps the two notes'
        messages from interleaving, so nothing is lost by sharing.
        """
        for ch in self.members:
            done = {rec for rec in self.active[ch] if rec[1] <= now + 1e-12}
            if done:
                self.active[ch] -= done
                if not self.active[ch]:
                    self.last_off[ch] = max(rec[1] for rec in done)

    def acquire(self, pitch: int, start: float, end: float, nid: int) -> int:
        self.retire(start)
        free = [c for c in self.members if not self.active[c]]
        if free:
            same = [c for c in free if self.last_note[c] == pitch]
            pool = same or free
            ch = min(pool, key=lambda c: (self.last_off[c], c))
        else:
            ch = min(self.members, key=lambda c: (len(self.active[c]), self.last_off[c], c))
        self.active[ch].add((pitch, end, nid))
        self.last_note[ch] = pitch
        return ch


def _ordered_notes(score: Score) -> list[Note]:
    out: list[tuple[tuple, Note]] = []
    for si, st in enumerate(score.staves):
        for ni, n in enumerate(st.notes):
            out.append(((_safe_beat(n.start), n.pitch, si, ni), n))
    out.sort(key=lambda p: p[0])
    return [n for _, n in out]


def _safe_beat(x) -> float:
    return float(x) if _finite(x) else 0.0


def _note_ticks(n: Note, ppq: int) -> tuple[int, int]:
    """(note-on tick, note-off tick); a zero-length note gets one tick."""
    start = _safe_beat(n.start)
    dur = float(n.dur) if _finite(n.dur) else 0.0
    t_on = int(round(start * ppq))
    t_off = int(round((start + max(0.0, dur)) * ppq))
    if t_off <= t_on:
        t_off = t_on + 1
    return t_on, t_off


def allocate_channels(score: Score, opts: MpeOptions) -> None:
    """Assign ``Note.channel`` (0-based MIDI channel) for every note in place.

    Deterministic: notes are visited in ``(start, pitch, stave index, note
    index)`` order.  Allocation follows RP-053 §1.5 - a free channel wins, with
    same-pitch affinity then oldest-release tie-break; when every member channel
    is occupied the channel with the fewest active notes wins (and a warning is
    recorded, because sharing perturbs per-note expression).  Zero-length notes
    are allocated like any other note (they render as a one-tick note).
    """
    if not opts.members:
        raise errors.RenderError("MpeOptions.members is empty; no MPE member channels")
    for ch in opts.members:
        if not 0 <= ch <= 15:
            raise errors.RenderError(f"member channel {ch} out of range 0..15")
    alloc = _Alloc(members=tuple(opts.members))
    shared = 0
    for n in _ordered_notes(score):
        t_on, t_off = _note_ticks(n, opts.ppq)
        start = t_on / float(opts.ppq)
        end = t_off / float(opts.ppq)
        alloc.retire(start)
        free_before = any(not alloc.active[c] for c in opts.members)
        ch = alloc.acquire(n.pitch, start, end, id(n))
        if not free_before:
            shared += 1
        n.channel = ch
    if shared:
        _warn_once(score,
                   f"MPE: {shared} note(s) had to share a member channel "
                   f"({len(opts.members)} members available); their preambles "
                   f"perturb the note already sounding on that channel")


def _overlap_map(score: Score, opts: MpeOptions) -> set[int]:
    """ids of notes that genuinely *overlap* another note on the same channel.

    Note-ends are exclusive: two notes that merely touch do not overlap
    (round-2 fix; the round-1 inclusive comparison silenced touching notes).
    """
    per_ch: dict[int, list[tuple[float, float, Note]]] = {}
    for n in _ordered_notes(score):
        if n.channel is None:
            continue
        t_on, t_off = _note_ticks(n, opts.ppq)
        per_ch.setdefault(n.channel, []).append(
            (t_on / float(opts.ppq), t_off / float(opts.ppq), n))
    bad: set[int] = set()
    for _ch, notes in per_ch.items():
        for i, (a0, a1, a) in enumerate(notes):
            for b0, b1, b in notes[i + 1:]:
                if b0 >= a1:
                    break
                if b0 < a1 and a0 < b1:
                    bad.add(id(a))
                    bad.add(id(b))
    return bad


# --------------------------------------------------------------------------- #
# event model
# --------------------------------------------------------------------------- #

@dataclass
class _Ev:
    tick: int
    phase: int
    prio: int
    seq: int
    data: list[int]
    track: Optional[str] = None       # stave name; None -> conductor
    channel: int = 0
    kind: str = ""
    val: int = 0                      # dedup key (14-bit for bend, 7-bit else)
    mandatory: bool = False           # spec-mandated: never deduped, never governed

    @property
    def sort_key(self) -> tuple:
        # ``seq`` is the global note ordinal, so every event group belonging to
        # one note stays contiguous inside a tick; ``phase`` guarantees that a
        # note-off teardown precedes any note-on preamble at the same tick.
        return (self.tick, self.phase, self.seq, self.prio)


def _cc(ch: int, num: int, val: int) -> list[int]:
    return [0xB0 | (ch & 0x0F), num & 0x7F, val & 0x7F]


def _bend_msg(ch: int, v: int) -> list[int]:
    lsb, msb = bend_bytes(v)
    return [0xE0 | (ch & 0x0F), lsb, msb]


def _press(ch: int, v: int) -> list[int]:
    return [0xD0 | (ch & 0x0F), _u7(v)]


def _note_on(ch: int, pitch: int, vel: int) -> list[int]:
    return [0x90 | (ch & 0x0F), pitch & 0x7F, max(1, min(127, vel))]


def _note_off(ch: int, pitch: int, vel: int = 64) -> list[int]:
    return [0x80 | (ch & 0x0F), pitch & 0x7F, _u7(vel)]


def _msg_for(kind: str, ch: int, num: Optional[int], v: int) -> list[int]:
    if kind == "bend":
        return _bend_msg(ch, v)
    if kind == "press":
        return _press(ch, v)
    return _cc(ch, num if num is not None else CC_TIMBRE, v)


def _is_expr_ev(e: _Ev) -> bool:
    """Does this event count as per-note expression for density/thinning?"""
    high = e.data[0] & 0xF0
    if high in (0xE0, 0xD0):
        return True
    if high == 0xB0:
        return e.data[1] not in CONFIG_CCS
    return False


def _rpn(ch: int, msb: int, lsb: int, value_msb: int,
         value_lsb: Optional[int] = 0) -> list[list[int]]:
    """RPN write, MSB first (CC101 then CC100), closed with the null RPN."""
    out = [_cc(ch, CC_BANK_RPN_MSB, msb),
           _cc(ch, CC_BANK_RPN_LSB, lsb),
           _cc(ch, CC_DATA_MSB, value_msb)]
    if value_lsb is not None:
        out.append(_cc(ch, CC_DATA_LSB, value_lsb))
    out.append(_cc(ch, CC_BANK_RPN_MSB, RPN_NULL))
    out.append(_cc(ch, CC_BANK_RPN_LSB, RPN_NULL))
    return out


def config_messages(opts: MpeOptions) -> list[list[int]]:
    """The tick-0 MPE zone configuration block, in transmit order."""
    msgs: list[list[int]] = []
    n_members = len(opts.members)
    if n_members > 15:
        raise errors.RenderError(f"MPE zone supports at most 15 member channels, got {n_members}")
    # Reset All Controllers on both zone masters (RP-053 canonical example)
    msgs.append(_cc(LOWER_MASTER, CC_RESET_ALL, 0))
    msgs += _rpn(LOWER_MASTER, 0, 6, n_members, None)      # MCM: lower zone, mm = members
    msgs.append(_cc(UPPER_MASTER, CC_RESET_ALL, 0))
    msgs += _rpn(UPPER_MASTER, 0, 6, 0, None)              # MCM: upper zone off
    # RPN 0 pitch-bend sensitivity: master 2 st, every member opts.bend_range
    msgs += _rpn(LOWER_MASTER, 0, 0, MASTER_BEND_RANGE, 0)
    br = int(round(max(1.0, min(96.0, float(opts.bend_range)))))
    for ch in opts.members:
        msgs += _rpn(ch, 0, 0, br, 0)
    return msgs


# --------------------------------------------------------------------------- #
# curve sampling
# --------------------------------------------------------------------------- #

def clean_points(curve: Optional[Curve]) -> tuple[list[tuple[float, float]], int]:
    """Real breakpoints of a curve.  -> (points, n_anomalous).

    ``NaN`` is ``ir.Curve``'s gap sentinel and is removed **silently** via
    ``Curve.real_points()``.  ``n_anomalous`` counts only the drops worth
    warning about: ``+-inf`` and other non-finite-but-not-NaN values.  Neither
    kind is a reason to delete the lane - the surviving breakpoints still
    define it (robustness policy, above).
    """
    if curve is None or not curve.points:
        return [], 0
    real = curve.real_points()                      # NaN gaps: silent
    pts = [(float(t), float(v)) for t, v in real if _finite(t) and _finite(v)]
    return pts, len(real) - len(pts)                # only +-inf warns


def clean_spans(curve: Optional[Curve]) -> tuple[list[list[tuple[float, float]]], int]:
    """``Curve.spans()`` with anomalies removed.  -> (spans, n_anomalous).

    One span per contiguous run of real data; the NaN gaps between them are
    regions where nothing is emitted at all.
    """
    if curve is None or not curve.points:
        return [], 0
    spans: list[list[tuple[float, float]]] = []
    bad = 0
    for run in curve.spans():
        keep = [(float(t), float(v)) for t, v in run if _finite(t) and _finite(v)]
        bad += len(run) - len(keep)
        if keep:
            spans.append(keep)
    return spans, bad


def _lerp(points: list[tuple[float, float]], beat: float) -> float:
    if not points:
        return 0.0
    if beat <= points[0][0]:
        return points[0][1]
    if beat >= points[-1][0]:
        return points[-1][1]
    lo, hi = 0, len(points) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if points[mid][0] <= beat:
            lo = mid
        else:
            hi = mid
    t0, v0 = points[lo]
    t1, v1 = points[hi]
    if t1 == t0:
        return v1
    return v0 + (beat - t0) / (t1 - t0) * (v1 - v0)


def _sample_lane(points: list[tuple[float, float]], start: float, dur: float,
                 grid: float) -> list[tuple[float, float]]:
    """Sample ``points`` on ``grid`` over ``[start, start+dur)`` -> [(beat, v)]."""
    if not points or grid <= 0:
        return []
    steps = max(1, int(math.floor((dur - 1e-12) / grid)) + 1)
    end = start + dur
    out: list[tuple[float, float]] = []
    for i in range(steps):
        t = start + i * grid
        if t >= end and out:
            break
        out.append((t, _lerp(points, t)))
    return out


def _sample_spans(spans: list[list[tuple[float, float]]], start: float,
                  dur: float, grid: float) -> list[tuple[float, float]]:
    """Sample every span on ``grid``, emitting **nothing inside NaN gaps**.

    The first span reaches back to ``start`` (its first value is the note's
    value at note-on); a later span begins at its own first breakpoint.  A span
    that is followed by a gap stops at its own last breakpoint, so a hold
    receiver simply keeps that value for the length of the gap.
    """
    if not spans or grid <= 0:
        return []
    end = start + dur
    out: list[tuple[float, float]] = []
    for i, span in enumerate(spans):
        last = i == len(spans) - 1
        s0 = start if i == 0 else max(start, span[0][0])
        s1 = end if last else min(end, span[-1][0])
        if s1 < s0 - 1e-12:
            continue
        steps = max(1, int(math.floor((s1 - s0 - 1e-12) / grid)) + 1)
        seg: list[tuple[float, float]] = []
        for k in range(steps):
            t = s0 + k * grid
            if seg and (t >= end or t > s1 + 1e-12):
                break
            seg.append((t, _lerp(span, t)))
        if not last and seg and seg[-1][0] < s1 - 1e-12:
            seg.append((s1, _lerp(span, s1)))
        for t, v in seg:                     # keep the stream monotone in time
            if out and t <= out[-1][0] + 1e-12:
                continue
            out.append((t, v))
    return out


def _lane_frames(n: Note, lane: str, grid_beats: float,
                 to_int, default: Optional[int]) -> list[tuple[float, int]]:
    """Backwards-compatible single-lane sampler (used by tests/tools)."""
    pts, _ = clean_points(n.curves.get(lane))
    t_on, t_off = _note_ticks(n, 960)
    start = t_on / 960.0
    dur = (t_off - t_on) / 960.0
    if not pts:
        return [] if default is None else [(start, default)]
    return [(t, to_int(v)) for t, v in _sample_lane(pts, start, dur, grid_beats)]


def _cc_lanes(n: Note) -> list[tuple[str, int]]:
    """Extra CC lanes on this note -> [(lane, cc number)] in deterministic order."""
    out: list[tuple[str, int]] = []
    for lane in sorted(n.curves):
        if lane in (BEND, PRESS, TIMBRE):
            continue
        if lane == AMP:
            out.append((lane, CC_AMP))
        elif lane == PAN:
            out.append((lane, CC_PAN))
        elif lane.startswith("cc"):
            try:
                num = int(lane[2:])
            except ValueError:
                continue
            if 0 <= num <= 127 and num not in (CC_TIMBRE,):
                out.append((lane, num))
    return out


# --------------------------------------------------------------------------- #
# main renderer
# --------------------------------------------------------------------------- #

@dataclass
class RenderStats:
    raw_frames: int = 0
    emitted_frames: int = 0
    note_count: int = 0
    shared_notes: int = 0
    governed_dropped: int = 0
    escalated_channels: int = 0
    max_expr_per_sec: float = 0.0
    max_hold_error_bend_lsb: int = 0
    max_hold_error_bend_cents: float = 0.0
    max_hold_error_cc_lsb: int = 0
    #: ``"<channel>/<lane>" -> allocated events/second`` (see ``_water_fill``).
    #: Derived from the score + options only, never from the emitted stream.
    lane_alloc: dict = field(default_factory=dict)

    @property
    def thinning_ratio(self) -> float:
        if self.raw_frames <= 0:
            return 0.0
        # Clamped at 0: ``emitted_frames`` also counts the mandated preamble /
        # teardown events, which have no raw-grid counterpart, so a note with no
        # curves at all would otherwise report a negative "ratio".
        return max(0.0, 1.0 - self.emitted_frames / self.raw_frames)


def _tick(beat: float, ppq: int) -> int:
    return int(round(beat * ppq))


@dataclass
class _Job:
    note: Note
    seq: int
    ch: int
    t_on: int
    t_off: int
    track: str
    b0: int
    c0: int
    # [(kind, cc number or None, raw frames, grid beats, base tolerance)]
    lanes: list = field(default_factory=list)
    thinned: dict = field(default_factory=dict)

    def thin_all(self, scale: Optional[dict] = None) -> None:
        """(Re)thin every lane.  ``scale`` maps ``(channel, kind)`` -> tolerance
        multiplier, set by the per-lane rate budget in ``_build_events``."""
        self.thinned = {}
        for kind, _num, raw, grid, base_tol in self.lanes:
            s = 1.0 if not scale else float(scale.get((self.ch, kind), 1.0))
            tol = base_tol
            if s > 1.0:
                tol = max(base_tol, int(math.floor(max(1, base_tol) * s)))
            self.thinned[kind] = thin(raw, tol=tol, min_dt=grid)

    def interior_ticks(self, ppq: int) -> list[int]:
        out = []
        for kind, _num, _raw, _grid, _tol in self.lanes:
            for t, _v in self.thinned.get(kind, ()):
                tk = _tick(t, ppq)
                if self.t_on < tk < self.t_off:
                    out.append(tk)
        return out


#: Relative share of a channel's expression-event budget per lane.  Pitch is
#: the most audible dimension, so the bend lane is served first; a fast timbre
#: wiggle degrades far more gracefully than a mistuned note.
_LANE_WEIGHT = {"bend": 0.68, "press": 0.17, "cc74": 0.10}
_LANE_WEIGHT_OTHER = 0.05


def _lane_weight(kind: str) -> float:
    return _LANE_WEIGHT.get(kind, _LANE_WEIGHT_OTHER)


def _water_fill(demands: dict, avail: float) -> dict:
    """Split ``avail`` events/second between lanes by :data:`_LANE_WEIGHT`.

    Progressive filling: a lane that wants less than its weighted share gets
    exactly what it wants and donates the remainder to the lanes that are still
    hungry.  An idle lane therefore reserves nothing (round-2 fix: the round-2
    first cut let the bend lane reserve 68 % of the ceiling even when the note
    had no bend curve at all, needlessly coarsening pressure).
    """
    alloc: dict = {}
    active = set(demands)
    while active:
        wsum = sum(_lane_weight(k[1] if isinstance(k, tuple) else k) for k in active)
        rem = max(0.0, avail - sum(alloc.values()))
        share = {k: rem * _lane_weight(k[1] if isinstance(k, tuple) else k) / max(1e-9, wsum)
                 for k in active}
        done = [k for k in active if demands[k] <= share[k] + 1e-9]
        if not done:
            alloc.update(share)
            break
        for k in done:
            alloc[k] = demands[k]
            active.discard(k)
    return alloc


def _window_peak(ticks: list[int], ppq: int, spb: float) -> float:
    """Worst count inside a sliding 1-second window (tempo aware)."""
    if not ticks:
        return 0.0
    secs = sorted(t / float(ppq) * spb for t in ticks)
    lo = 0
    worst = 0
    for hi in range(len(secs)):
        while secs[hi] - secs[lo] > 1.0:
            lo += 1
        worst = max(worst, hi - lo + 1)
    return float(worst)


def _lane_peaks(jobs: list[_Job], ppq: int, spb: float
                ) -> tuple[dict[tuple[int, str], float], dict[int, float]]:
    """Per-(channel, lane) and per-channel-mandatory peak rates."""
    per: dict[tuple[int, str], list[int]] = {}
    mand: dict[int, list[int]] = {}
    for job in jobs:
        mand.setdefault(job.ch, []).extend([job.t_on] * 3 + [job.t_off])
        for kind, _num, _raw, _grid, _tol in job.lanes:
            lst = per.setdefault((job.ch, kind), [])
            for t, _v in job.thinned.get(kind, ()):
                tk = _tick(t, ppq)
                if job.t_on < tk < job.t_off:
                    lst.append(tk)
    return ({k: _window_peak(v, ppq, spb) for k, v in per.items()},
            {ch: _window_peak(v, ppq, spb) for ch, v in mand.items()})


def _dedup(evs: list[_Ev]) -> list[_Ev]:
    """Drop expression events that do not change the receiver's held value."""
    last: dict[tuple[int, str], int] = {}
    out: list[_Ev] = []
    for e in evs:
        if not _is_expr_ev(e) or e.mandatory:
            if _is_expr_ev(e):
                last[(e.channel, e.kind)] = e.val
            out.append(e)
            continue
        key = (e.channel, e.kind)
        if last.get(key) == e.val:
            continue
        last[key] = e.val
        out.append(e)
    return out


def _govern(evs: list[_Ev], opts: MpeOptions, spb: float) -> tuple[list[_Ev], int, float]:
    """Hard per-channel rate governor.  -> (events, dropped, peak per second).

    Mandated events (the note-on preamble and the pressure-0 teardown) are never
    dropped; they do count against the budget.
    """
    cap = max(1.0, float(opts.max_expr_per_sec))
    kept: dict[int, list[float]] = {}
    out: list[_Ev] = []
    dropped = 0
    peak = 0
    for e in evs:
        if not _is_expr_ev(e):
            out.append(e)
            continue
        t = e.tick / float(opts.ppq) * spb
        times = kept.setdefault(e.channel, [])
        while times and t - times[0] > 1.0:
            times.pop(0)
        if not e.mandatory:
            if len(times) + 1 > cap:
                dropped += 1
                continue
        times.append(t)
        peak = max(peak, len(times))
        out.append(e)
    return out, dropped, float(peak)


def _build_events(score: Score, opts: MpeOptions) -> tuple[list[_Ev], RenderStats]:
    ppq = opts.ppq
    spb = 60.0 / max(1e-9, score.tempo)              # seconds per beat
    pitch_grid = (opts.pitch_grid_ms / 1000.0) / spb  # beats
    slow_grid = (opts.grid_ms / 1000.0) / spb         # beats
    stats = RenderStats()
    warns = _Warns(score)

    if any(n.channel is None for n in score.notes):
        allocate_channels(score, opts)

    stats.shared_notes = len(_overlap_map(score, opts))

    stave_of: dict[int, str] = {}
    for st in score.staves:
        for n in st.notes:
            stave_of[id(n)] = st.name

    br = float(opts.bend_range)
    tol_bend = max(int(opts.deadband_lsb), bend_tol_lsb(br, opts.bend_tol_cents))
    tol_cc = max(0, int(opts.cc_tol_lsb))

    # ---- pass 1: sample every lane of every note ------------------------- #
    jobs: list[_Job] = []
    for nord, n in enumerate(_ordered_notes(score)):
        ch = n.channel
        if ch is None:
            continue
        t_on, t_off = _note_ticks(n, ppq)
        if not _finite(n.start):
            warns.add("non-finite note start",
                      "MPE: note pitch %s has a non-finite start; placed at beat 0"
                      % (n.pitch,))
        if not _finite(n.dur) or float(n.dur) <= 0.0:
            warns.add("zero-length note",
                      "MPE: note pitch %s at beat %g has duration %r; rendered with the "
                      "minimum duration of one tick (%.4f beats)"
                      % (n.pitch, _safe_beat(n.start), n.dur, 1.0 / ppq))
        start = t_on / float(ppq)
        dur = (t_off - t_on) / float(ppq)
        det = float(n.detune) if _finite(n.detune) else 0.0
        if not _finite(n.detune):
            warns.add("non-finite detune",
                      "MPE: note pitch %s at beat %g has non-finite detune %r; dropped"
                      % (n.pitch, start, n.detune))

        lanes: list = []

        # bend -------------------------------------------------------------- #
        bspans, bdrop = clean_spans(n.curves.get(BEND))
        if bdrop:
            warns.add("non-finite bend data",
                      "MPE: note pitch %s at beat %g: dropped %d non-finite bend "
                      "breakpoint(s) (inf is never written)"
                      % (n.pitch, start, bdrop))
        samples = [(t, v + det)
                   for t, v in _sample_spans(bspans, start, dur, pitch_grid)]
        if not samples:
            samples = [(start, det)]
        elif samples[0][0] > start + 1e-9:
            # the lane opens with a gap: hold the static detune until it starts
            samples.insert(0, (start, det))
        extreme = max(samples, key=lambda p: abs(p[1]))[1]
        if abs(extreme) > br + 1e-9:
            warns.add("bend clamped to the member range",
                      "MPE: note pitch %s at beat %g requests %+.3f st of bend, outside "
                      "the member range of +-%g st; clamped (not wrapped)"
                      % (n.pitch, start, extreme, br))
        bend_raw = [(t, semitones_to_bend(v, br)) for t, v in samples]
        lanes.append(("bend", None, bend_raw, pitch_grid, tol_bend))

        # pressure ---------------------------------------------------------- #
        pspans, pdrop = clean_spans(n.curves.get(PRESS))
        if pdrop:
            warns.add("non-finite pressure data",
                      "MPE: note pitch %s at beat %g: dropped %d non-finite pressure "
                      "breakpoint(s)" % (n.pitch, start, pdrop))
        press_raw = [(t, _unipolar_to_7bit(v))
                     for t, v in _sample_spans(pspans, start, dur, slow_grid)]
        if press_raw:
            lanes.append(("press", None, press_raw, slow_grid, tol_cc))

        # CC74 timbre ------------------------------------------------------- #
        tspans, tdrop = clean_spans(n.curves.get(TIMBRE))
        if tdrop:
            warns.add("non-finite timbre data",
                      "MPE: note pitch %s at beat %g: dropped %d non-finite timbre "
                      "breakpoint(s)" % (n.pitch, start, tdrop))
        timbre_raw = [(t, _unipolar_to_7bit(v))
                      for t, v in _sample_spans(tspans, start, dur, slow_grid)]
        if not timbre_raw:
            timbre_raw = [(start, DEFAULT_TIMBRE)]
        elif timbre_raw[0][0] > start + 1e-9:
            timbre_raw.insert(0, (start, DEFAULT_TIMBRE))
        lanes.append(("cc74", CC_TIMBRE, timbre_raw, slow_grid, tol_cc))

        # other CC lanes ---------------------------------------------------- #
        for lane, num in _cc_lanes(n):
            cspans, cdrop = clean_spans(n.curves.get(lane))
            if cdrop:
                warns.add("non-finite CC data",
                          "MPE: note pitch %s at beat %g: dropped %d non-finite %s "
                          "breakpoint(s)" % (n.pitch, start, cdrop, lane))
            cc_raw = [(t, _unipolar_to_7bit(v))
                      for t, v in _sample_spans(cspans, start, dur, slow_grid)]
            if not cc_raw:
                continue
            lanes.append(("cc%d" % num, num, cc_raw, slow_grid, tol_cc))

        stats.raw_frames += sum(len(raw) for _k, _n, raw, _g, _t in lanes)
        stats.note_count += 1
        job = _Job(note=n, seq=nord, ch=ch, t_on=t_on, t_off=t_off,
                   track=stave_of.get(id(n), ""),
                   b0=bend_raw[0][1],
                   c0=timbre_raw[0][1], lanes=lanes)
        job.thin_all()
        jobs.append(job)

    # ---- pass 2: escalate tolerance on over-subscribed channels ---------- #
    cap = max(1.0, float(opts.max_expr_per_sec))
    kinds_by_ch: dict[int, set[str]] = {}
    for job in jobs:
        s = kinds_by_ch.setdefault(job.ch, set())
        for kind, _num, _raw, _grid, _tol in job.lanes:
            s.add(kind)
    scale: dict[tuple[int, str], float] = {}
    alloc: dict[tuple[int, str], float] = {}
    for _round in range(64):
        lane_pk, mand_pk = _lane_peaks(jobs, ppq, spb)
        by_ch_demand: dict[int, dict] = {}
        for key, pk in lane_pk.items():
            by_ch_demand.setdefault(key[0], {})[key] = pk
        alloc = {}
        for ch, demands in by_ch_demand.items():
            avail = max(1.0, cap - mand_pk.get(ch, 0.0))
            alloc.update(_water_fill(demands, avail))
        over: list[tuple[int, str]] = []
        for key, pk in lane_pk.items():
            if pk > max(alloc.get(key, 0.0), 2.0) + 1e-9:
                over.append(key)
        if not over:
            break
        for key in over:
            scale[key] = scale.get(key, 1.0) * 1.25
        chans = {ch for ch, _k in over}
        for job in jobs:
            if job.ch in chans:
                job.thin_all(scale)
    for (ch, kind) in sorted(scale):
        warns.add("expression rate ceiling",
                  "MPE: channel %d lane %s exceeded its share of the %g expression "
                  "events/second/channel ceiling; its hold tolerance was widened "
                  "x%.1f (at a fixed event budget a hold receiver's accuracy is "
                  "bounded by max|dv/dt| / rate)"
                  % (ch + 1, kind, cap, scale[(ch, kind)]))
    stats.escalated_channels = len({ch for ch, _k in scale})
    stats.lane_alloc = {"%d/%s" % (ch, kind): rate
                        for (ch, kind), rate in sorted(alloc.items())}

    # ---- pass 3: assemble the event stream ------------------------------- #
    evs: list[_Ev] = []
    if opts.emit_config:
        for i, data in enumerate(config_messages(opts)):
            evs.append(_Ev(0, PH_CONFIG, i, -1, data, None,
                           channel=data[0] & 0x0F, kind="config"))

    for job in jobs:
        ch, seq, track = job.ch, job.seq, job.track
        t_on, t_off = job.t_on, job.t_off
        n = job.note
        # mandated preamble: bend -> CC74 -> pressure 0 -> note-on.  Emitted for
        # EVERY note, including one that reuses or shares a channel.
        evs.append(_Ev(t_on, PH_NOTE_ON, _ON_PRIO["bend"], seq,
                       _bend_msg(ch, job.b0), track, ch, "bend",
                       val=job.b0, mandatory=True))
        evs.append(_Ev(t_on, PH_NOTE_ON, _ON_PRIO["cc"], seq,
                       _cc(ch, CC_TIMBRE, job.c0), track, ch, "cc74",
                       val=job.c0, mandatory=True))
        evs.append(_Ev(t_on, PH_NOTE_ON, _ON_PRIO["press"], seq,
                       _press(ch, 0), track, ch, "press", val=0, mandatory=True))
        evs.append(_Ev(t_on, PH_NOTE_ON, _ON_PRIO["note_on"], seq,
                       _note_on(ch, n.pitch, n.velocity), track, ch, "note_on"))

        # Lanes whose value at note-on is NOT carried by the mandated preamble
        # (pressure, CC11, CC10, cc<n>...) state it immediately *after* the
        # note-on, so a constant lane is never silently lost and the mandated
        # 3-event preamble stays exactly bend -> CC74 -> pressure(0) -> note-on.
        post_prio = _ON_PRIO["note_on"] + 1
        for kind, num, _raw, _grid, _tol in job.lanes:
            for t, v in job.thinned.get(kind, ()):
                tk = _tick(t, ppq)
                if tk >= t_off:
                    continue
                if tk <= t_on:
                    if kind in ("bend", "cc74") or tk != t_on:
                        continue
                    evs.append(_Ev(t_on, PH_NOTE_ON, post_prio, seq,
                                   _msg_for(kind, ch, num, v), track, ch, kind,
                                   val=v))
                    post_prio += 1
                    continue
                evs.append(_Ev(tk, PH_EXPR, 0, seq, _msg_for(kind, ch, num, v),
                               track, ch, kind, val=v))

        # mandated teardown: pressure 0 immediately before the note-off.
        evs.append(_Ev(t_off, PH_NOTE_OFF, 0, seq, _press(ch, 0), track, ch,
                       "press", val=0, mandatory=True))
        evs.append(_Ev(t_off, PH_NOTE_OFF, 1, seq,
                       _note_off(ch, n.pitch, 64), track, ch, "note_off"))

    evs.sort(key=lambda e: e.sort_key)
    evs = _dedup(evs)
    evs, dropped, peak = _govern(evs, opts, spb)
    evs = _dedup(evs)
    stats.governed_dropped = dropped
    stats.max_expr_per_sec = peak
    stats.emitted_frames = sum(1 for e in evs if _is_expr_ev(e))
    if dropped:
        warns.add("expression rate governor",
                  "MPE: %d expression event(s) dropped by the %g events/second/channel "
                  "governor" % (dropped, cap))

    # ---- measured hold error (reported, not assumed) --------------------- #
    for job in jobs:
        for kind, _num, raw, _grid, _tol in job.lanes:
            err = hold_error(raw, job.thinned.get(kind, []))
            if kind == "bend":
                if err > stats.max_hold_error_bend_lsb:
                    stats.max_hold_error_bend_lsb = err
            elif err > stats.max_hold_error_cc_lsb:
                stats.max_hold_error_cc_lsb = err
    stats.max_hold_error_bend_cents = (stats.max_hold_error_bend_lsb
                                       * cents_per_bend_lsb(br))
    warns.finish()
    return evs, stats


def hold_budget_cents(score: Score, opts: Optional[MpeOptions] = None
                      ) -> tuple[float, float, str]:
    """The *documented* worst-case bend hold error for ``score``.

    Returns ``(budget_cents, grid_floor_cents, where)``.  The guarantee stated in
    the module docstring has two terms:

    * ``opts.bend_tol_cents`` - the hold tolerance the thinner enforces at grid
      sample times, and
    * ``grid_floor_cents`` - the curve's own motion across one *emission*
      interval, which no zero-order-hold sender can resolve.  That interval is
      ``max(pitch grid, 1 / allocated bend rate)``: the grid is the minimum
      spacing (BAR P4) and the 250 events/s/channel ceiling can force it wider.

    The allocated rate comes from :func:`_water_fill`, i.e. from the score and
    the options alone - never from the emitted file - so a checker can verify
    ``measured <= budget`` and still catch a thinner that emits too few points,
    wrong values, or drops a lane.
    """
    opts = opts or _opts_from_score(score)
    spb = 60.0 / max(1e-9, float(score.tempo))
    pitch_grid = (opts.pitch_grid_ms / 1000.0) / spb
    stats = render_stats(score, opts)
    notes = [n for st in score.staves for n in st.notes]
    worst_budget = float(opts.bend_tol_cents)
    worst_floor = 0.0
    where = ""
    br = float(opts.bend_range)
    for n in notes:
        if n.channel is None:
            continue
        rate = stats.lane_alloc.get("%d/bend" % n.channel, 0.0)
        h = pitch_grid if rate <= 0 else max(pitch_grid, (1.0 / rate) / spb)
        pts, _ = clean_points(n.curves.get(BEND))
        det = float(n.detune) if _finite(n.detune) else 0.0

        def true_at(t, pts=pts, det=det):
            v = det + (_lerp(pts, t) if pts else 0.0)
            if not _finite(v):
                return max(-br, min(br, det))
            return max(-br, min(br, v))

        floor = 0.0
        start, dur = _safe_beat(n.start), max(0.0, _safe_beat(n.dur))
        steps = int(math.floor(dur / max(1e-9, pitch_grid))) + 1
        for i in range(steps + 1):
            t = start + i * pitch_grid
            if t > start + dur:
                break
            floor = max(floor,
                        abs(true_at(min(start + dur, t + h)) - true_at(t)) * 100.0)
        budget = float(opts.bend_tol_cents) + floor
        if budget > worst_budget:
            worst_budget, worst_floor = budget, floor
            where = "(pitch %d, beat %.3f, ch %s, emission interval %.2f ms)" % (
                n.pitch, n.start, (n.channel + 1), h * spb * 1000.0)
    return worst_budget, worst_floor, where


def render_stats(score: Score, opts: Optional[MpeOptions] = None) -> RenderStats:
    """Thinning / density statistics for a score (used by tools/audit_mpe.py)."""
    opts = opts or _opts_from_score(score)
    return _build_events(score, opts)[1]


def _opts_from_score(score: Score) -> MpeOptions:
    return MpeOptions(bend_range=score.bend_range, ppq=score.ppq,
                      grid_ms=score.grid_ms, pitch_grid_ms=score.grid_ms / 2.0)


def render_events(score: Score, opts: Optional[MpeOptions] = None) -> list[tuple[float, list[int]]]:
    """Flat, time-sorted MPE stream: ``[(beat, raw midi bytes)]``."""
    opts = opts or _opts_from_score(score)
    evs, _ = _build_events(score, opts)
    return [(e.tick / float(opts.ppq), list(e.data)) for e in evs]


# --------------------------------------------------------------------------- #
# SMF output
# --------------------------------------------------------------------------- #

def _msg_from_bytes(data: list[int], time: int):
    import mido
    return mido.Message.from_bytes(bytes(data), time=time)


def render_midifile(score: Score, opts: Optional[MpeOptions] = None):
    """Build a ``mido.MidiFile`` (SMF type 1, ``opts.ppq`` PPQN).

    Track 0 is the conductor: track name, tempo, time signature and the tick-0
    MPE configuration block.  Then one track per stave (or a single note track
    when ``opts.one_track_per_stave`` is false).
    """
    import mido
    from mido import MetaMessage, MidiFile, MidiTrack

    opts = opts or _opts_from_score(score)
    evs, _ = _build_events(score, opts)

    mid = MidiFile(type=1, ticks_per_beat=opts.ppq)

    conductor = MidiTrack()
    def _smf_text(s: str) -> str:
        """SMF meta text is latin-1; transliterate anything outside it.

        A title containing an em dash used to crash the whole render with a
        UnicodeEncodeError from mido, so text is normalised here rather than
        trusting the source to stay in one byte per character.
        """
        subs = {"\u2014": "--", "\u2013": "-", "\u2018": "'", "\u2019": "'",
                "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u00a0": " "}
        out = "".join(subs.get(ch, ch) for ch in s)
        return out.encode("latin-1", "replace").decode("latin-1")

    conductor.append(MetaMessage("track_name", name="conductor", time=0))
    if score.title:
        conductor.append(MetaMessage("text", text=_smf_text(score.title), time=0))
    conductor.append(MetaMessage("set_tempo", tempo=mido.bpm2tempo(score.tempo), time=0))
    conductor.append(MetaMessage("time_signature", numerator=score.meter[0],
                                 denominator=score.meter[1], time=0))
    for e in (e for e in evs if e.track is None):
        conductor.append(_msg_from_bytes(e.data, 0))
    conductor.append(MetaMessage("end_of_track", time=0))
    mid.tracks.append(conductor)

    names = [st.name for st in score.staves] if opts.one_track_per_stave else ["MPE Zone 1"]
    if not names:
        names = ["MPE Zone 1"]
    buckets: dict[str, list[_Ev]] = {nm: [] for nm in names}
    for e in evs:
        if e.track is None:
            continue
        key = e.track if opts.one_track_per_stave and e.track in buckets else names[0]
        buckets[key].append(e)

    for nm in names:
        tr = MidiTrack()
        tr.append(MetaMessage("track_name", name=_smf_text(nm or "stave"), time=0))
        prev = 0
        for e in buckets[nm]:
            tr.append(_msg_from_bytes(e.data, e.tick - prev))
            prev = e.tick
        tr.append(MetaMessage("end_of_track", time=0))
        mid.tracks.append(tr)
    return mid


def write_midi(score: Score, path: str, opts: Optional[MpeOptions] = None) -> None:
    """Render ``score`` and save it as a Standard MIDI File at ``path``."""
    render_midifile(score, opts).save(path)


# --------------------------------------------------------------------------- #
# analysis helpers shared with the tests and the auditor
# --------------------------------------------------------------------------- #

def channel_streams(events: list[tuple[float, list[int]]]) -> dict[int, list[tuple[float, list[int]]]]:
    """Split a flat event stream into per-channel streams (order preserved)."""
    out: dict[int, list[tuple[float, list[int]]]] = {}
    for beat, data in events:
        if not data or data[0] < 0x80 or data[0] >= 0xF0:
            continue
        out.setdefault(data[0] & 0x0F, []).append((beat, data))
    return out


def bend_curve_from_events(events: list[tuple[float, list[int]]], channel: int,
                           bend_range: float) -> list[tuple[float, float]]:
    """Reconstruct ``[(beat, semitones)]`` for one channel from a raw stream."""
    out: list[tuple[float, float]] = []
    for beat, data in events:
        if data and (data[0] & 0xF0) == 0xE0 and (data[0] & 0x0F) == channel:
            u = (data[2] << 7) | data[1]
            out.append((beat, bend_to_semitones(u - 8192, bend_range)))
    return out
