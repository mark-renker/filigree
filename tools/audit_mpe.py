#!/usr/bin/env python3
"""MPE conformance auditor.

Reads a Standard MIDI File and checks it against every bullet of
``refs/BAR.md`` section P4 (which transcribes MMA/AMEI RP-053 as digested in
``research/mpe_technical.md``).  Prints a report and exits **nonzero** on any
violation.

    python tools/audit_mpe.py out.mid
    python tools/audit_mpe.py --synth          # render a synthetic score first
    python tools/audit_mpe.py out.mid --json

Checks performed
  1. parses under the hand-written parser (tools/smf_parse.py) *and* under mido,
     with byte-identical channel-voice event streams
  2. SMF type 1, 960 PPQN, conductor track carrying set_tempo
  3. MCM on channel 1: RPN 00 06, MSB (CC101) before LSB (CC100), mm = 15,
     closed with a null RPN; mm = 0 MCM on channel 16
  4. RPN 0 pitch-bend sensitivity on every used member channel, MSB first,
     null-RPN closed
  5. no notes on the zone master channel; no polyphonic key pressure on members
  6. per note the order is exactly bend -> CC74 -> pressure(0) -> note-on
  7. pressure(0) immediately precedes every note_off
  8. zero expression events on a channel between a note-off and its next note-on
  9. no two simultaneous notes on one member channel
 10. <= 250 expression events per second per channel (worst 1 s window)
 11. thinning ratio, reported as a *metric* (round-2 amendment: a fixed >= 60%
     floor is not a correctness criterion -- a fast ramp legitimately needs a
     point per grid step under hold semantics, see NOTES_P4.md)
 12. bend round-trip under a **zero-order-hold** receiver model: for every grid
     sample in a note's lifetime the held value must be within
     ``bend_tol_cents + grid_floor_cents`` of the true curve, where the floor is
     the curve's motion across one emission interval (``--synth`` only)

Owned by piece P4.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, os.path.join(_ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import smf_parse  # noqa: E402

from filigree import ir  # noqa: E402
from filigree.mpe import (CC_BANK_RPN_LSB, CC_BANK_RPN_MSB, CC_DATA_LSB,  # noqa: E402
                          CC_DATA_MSB, CC_TIMBRE, MpeOptions, bend_to_semitones,
                          hold_budget_cents, render_stats, write_midi)

EXPR_LIMIT_PER_SEC = 250
#: Reported, not enforced (round-2 amendment; see NOTES_P4.md fix 1).
THINNING_REPORT_ONLY = True
CENTS_TOLERANCE = 3.0
PITCH_GRID_S = 0.005
SLOW_GRID_S = 0.010


# --------------------------------------------------------------------------- #
# report plumbing
# --------------------------------------------------------------------------- #

class Report:
    def __init__(self) -> None:
        self.checks: list[tuple[str, bool, str]] = []
        self.metrics: dict[str, float] = {}

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append((name, bool(ok), detail))
        return bool(ok)

    def metric(self, name: str, value) -> None:
        self.metrics[name] = value

    @property
    def failures(self) -> list[tuple[str, bool, str]]:
        return [c for c in self.checks if not c[1]]

    def render(self) -> str:
        lines = ["MPE conformance report", "=" * 64]
        for name, ok, detail in self.checks:
            lines.append("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                                          ("  -- " + detail) if detail else ""))
        if self.metrics:
            lines.append("-" * 64)
            for k, v in self.metrics.items():
                if isinstance(v, float):
                    lines.append("  %-34s %.4f" % (k, v))
                else:
                    lines.append("  %-34s %s" % (k, v))
        lines.append("=" * 64)
        lines.append("%d checks, %d failures" % (len(self.checks), len(self.failures)))
        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps({
            "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in self.checks],
            "metrics": self.metrics,
            "failures": len(self.failures),
        }, indent=2, sort_keys=True)


# --------------------------------------------------------------------------- #
# stream helpers
# --------------------------------------------------------------------------- #

def mido_voice_events(path: str) -> list[tuple[int, bytes]]:
    """(tick, raw bytes) for every channel-voice event, read with mido."""
    import mido
    out: list[tuple[int, int, int, bytes]] = []
    mid = mido.MidiFile(path)
    for ti, track in enumerate(mid.tracks):
        tick = 0
        for i, msg in enumerate(track):
            tick += msg.time
            if msg.is_meta or msg.type == "sysex":
                continue
            out.append((tick, ti, i, bytes(msg.bytes())))
    out.sort(key=lambda r: (r[0], r[1], r[2]))
    return [(t, d) for t, _, _, d in out]


def is_expr(data: bytes) -> bool:
    """Per-note expression message: pitch bend, channel pressure or a CC."""
    high = data[0] & 0xF0
    if high in (0xE0, 0xD0):
        return True
    if high == 0xB0:
        return data[1] not in (CC_BANK_RPN_MSB, CC_BANK_RPN_LSB, CC_DATA_MSB,
                               CC_DATA_LSB, 121, 123, 120)
    return False


def kind_of(data: bytes) -> str:
    high = data[0] & 0xF0
    if high == 0xE0:
        return "bend"
    if high == 0xD0:
        return "press"
    if high == 0xB0:
        return "cc%d" % data[1]
    if high == 0x90:
        return "note_off" if data[2] == 0 else "note_on"
    if high == 0x80:
        return "note_off"
    if high == 0xA0:
        return "polytouch"
    return "other"


def per_channel(events: list[tuple[int, bytes]]) -> dict[int, list[tuple[int, bytes]]]:
    out: dict[int, list[tuple[int, bytes]]] = {}
    for tick, data in events:
        if 0x80 <= data[0] < 0xF0:
            out.setdefault(data[0] & 0x0F, []).append((tick, data))
    return out


def rpn_writes(events: list[tuple[int, bytes]]) -> list[dict]:
    """Decode RPN transactions: [{channel, msb, lsb, data_msb, data_lsb,
    msb_first, closed, tick}]."""
    state: dict[int, dict] = {}
    out: list[dict] = []
    for tick, data in events:
        if (data[0] & 0xF0) != 0xB0:
            continue
        ch = data[0] & 0x0F
        num, val = data[1], data[2]
        st = state.setdefault(ch, {"msb": None, "lsb": None, "order": [],
                                   "open": None})
        if num == CC_BANK_RPN_MSB:
            if st["open"] is not None and val == 127:
                st["open"]["closed_msb"] = True
                continue
            st["msb"] = val
            st["order"] = ["msb"]
            st["open"] = None
        elif num == CC_BANK_RPN_LSB:
            if st["open"] is not None and val == 127:
                st["open"]["closed_lsb"] = True
                st["open"] = None
                continue
            st["lsb"] = val
            st["order"] = st["order"] + ["lsb"]
        elif num == CC_DATA_MSB:
            if st["msb"] is None or st["lsb"] is None:
                continue
            rec = {"channel": ch, "msb": st["msb"], "lsb": st["lsb"],
                   "data_msb": val, "data_lsb": None, "tick": tick,
                   "msb_first": st["order"][:2] == ["msb", "lsb"],
                   "closed_msb": False, "closed_lsb": False}
            out.append(rec)
            st["open"] = rec
        elif num == CC_DATA_LSB:
            if st["open"] is not None:
                st["open"]["data_lsb"] = val
    for rec in out:
        rec["closed"] = bool(rec["closed_msb"] and rec["closed_lsb"])
    return out


def note_spans(chan_events: list[tuple[int, bytes]]) -> list[tuple[int, int, int]]:
    """[(note_on tick, note_off tick, pitch)] for one channel, in stream order."""
    open_notes: dict[int, int] = {}
    spans: list[tuple[int, int, int]] = []
    for tick, data in chan_events:
        k = kind_of(data)
        if k == "note_on":
            open_notes[data[1]] = tick
        elif k == "note_off" and data[1] in open_notes:
            spans.append((open_notes.pop(data[1]), tick, data[1]))
    for pitch, on in open_notes.items():
        spans.append((on, -1, pitch))
    spans.sort()
    return spans


# --------------------------------------------------------------------------- #
# the audit
# --------------------------------------------------------------------------- #

def audit_file(path: str, rep: Report | None = None, expect_ppq: int = 960,
               score: "ir.Score | None" = None,
               opts: MpeOptions | None = None) -> Report:
    rep = rep or Report()

    smf = smf_parse.parse_smf(path)
    own = smf.voice_events()
    try:
        theirs = mido_voice_events(path)
        mido_ok, mido_detail = True, ""
    except Exception as exc:                                # pragma: no cover
        theirs, mido_ok, mido_detail = [], False, "mido failed: %r" % (exc,)
    rep.check("file opens in mido", mido_ok, mido_detail)
    same = own == theirs
    detail = ""
    if not same:
        detail = "own=%d mido=%d events" % (len(own), len(theirs))
        for i, (a, b) in enumerate(zip(own, theirs)):
            if a != b:
                detail += "; first diff at %d: %s vs %s" % (i, a, b)
                break
    rep.check("independent parser stream == mido stream", same, detail)

    rep.check("SMF type 1", smf.fmt == 1, "format=%d" % smf.fmt)
    rep.check("%d PPQN" % expect_ppq, smf.division == expect_ppq,
              "division=%d" % smf.division)
    rep.check("conductor track carries set_tempo",
              any(e.kind == "meta" and e.meta_type == 0x51 for e in smf.tracks[0].events)
              if smf.tracks else False)
    rep.check(">= 2 tracks (conductor + >=1 stave)", len(smf.tracks) >= 2,
              "tracks=%d" % len(smf.tracks))
    rep.metric("tracks", len(smf.tracks))
    rep.metric("track_names", [tr.name for tr in smf.tracks])

    tempo_us = smf.tempo()
    sec_per_tick = (tempo_us / 1e6) / max(1, smf.division)
    rep.metric("tempo_bpm", round(60e6 / tempo_us, 4))

    chans = per_channel(own)
    used_members = sorted(ch for ch, evs in chans.items()
                          if any(kind_of(d) in ("note_on",) for _, d in evs))
    rep.metric("member_channels_used", used_members)

    # ---- 3. MCM ----------------------------------------------------------- #
    rpns = rpn_writes(own)
    mcms = [r for r in rpns if (r["msb"], r["lsb"]) == (0, 6)]
    lower = [r for r in mcms if r["channel"] == 0]
    upper = [r for r in mcms if r["channel"] == 15]
    rep.check("MCM (RPN 00 06) present on channel 1", bool(lower),
              "found %d" % len(lower))
    if lower:
        r = lower[0]
        rep.check("MCM mm == 15 (lower zone, 15 members)", r["data_msb"] == 15,
                  "mm=%d" % r["data_msb"])
        rep.check("MCM at tick 0", r["tick"] == 0, "tick=%d" % r["tick"])
        rep.check("MCM sent MSB (CC101) before LSB (CC100)", r["msb_first"])
        rep.check("MCM closed with null RPN", r["closed"])
    rep.check("upper-zone-off MCM (mm=0) on channel 16",
              bool(upper) and upper[0]["data_msb"] == 0,
              "found %d" % len(upper))

    # ---- 4. RPN 0 bend range --------------------------------------------- #
    br_writes = {r["channel"]: r for r in rpns if (r["msb"], r["lsb"]) == (0, 0)}
    missing = [ch for ch in used_members if ch not in br_writes]
    rep.check("RPN 0 bend range on every used member channel", not missing,
              "missing on channels %s" % missing)
    bad_order = [ch for ch in used_members if ch in br_writes and not br_writes[ch]["msb_first"]]
    rep.check("RPN 0 sent MSB-first on every member channel", not bad_order,
              "LSB-first on %s" % bad_order)
    unclosed = [ch for ch in used_members if ch in br_writes and not br_writes[ch]["closed"]]
    rep.check("RPN 0 closed with null RPN on every member channel", not unclosed,
              "unclosed on %s" % unclosed)
    rep.check("RPN 0 present on zone master (channel 1)", 0 in br_writes)
    ranges = sorted({br_writes[ch]["data_msb"] for ch in used_members if ch in br_writes})
    rep.metric("member_bend_range_st", ranges)
    rep.check("all member channels share one bend range", len(ranges) <= 1,
              "ranges=%s" % ranges)
    bend_range = float(ranges[0]) if ranges else 48.0

    # ---- 5. master-channel / polytouch hygiene --------------------------- #
    rep.check("no notes on the zone master channel",
              not any(kind_of(d) in ("note_on", "note_off") for _, d in chans.get(0, [])))
    rep.check("no polyphonic key pressure on member channels",
              not any(kind_of(d) == "polytouch"
                      for ch, evs in chans.items() if ch != 0 for _, d in evs))

    # ---- 6/7/8/9 per-channel structure ----------------------------------- #
    order_bad: list[str] = []
    off_bad: list[str] = []
    after_off_bad: list[str] = []
    overlap_bad: list[str] = []
    total_notes = 0
    expr_counts: dict[int, list[int]] = {}

    for ch in sorted(chans):
        evs = chans[ch]
        expr_counts[ch] = [tick for tick, d in evs if is_expr(d)]
        depth = 0
        for idx, (tick, data) in enumerate(evs):
            k = kind_of(data)
            if k == "note_on":
                total_notes += 1
                if depth > 0:
                    overlap_bad.append("ch%d tick%d note%d" % (ch + 1, tick, data[1]))
                depth += 1
                pre = [d for _, d in evs[max(0, idx - 3):idx]]
                want = ["bend", "cc%d" % CC_TIMBRE, "press"]
                got = [kind_of(d) for d in pre]
                if got != want:
                    order_bad.append("ch%d tick%d: %s" % (ch + 1, tick, got))
                elif pre[2][1] != 0:
                    order_bad.append("ch%d tick%d: pressure=%d before note-on"
                                     % (ch + 1, tick, pre[2][1]))
            elif k == "note_off":
                depth = max(0, depth - 1)
                prev = evs[idx - 1][1] if idx else None
                if prev is None or kind_of(prev) != "press" or prev[1] != 0:
                    off_bad.append("ch%d tick%d: prev=%s"
                                   % (ch + 1, tick, kind_of(prev) if prev is not None else None))
                if depth == 0:
                    # everything up to the next note-on must be silent, except
                    # that note's own mandated 3-event preamble (check 6).
                    nxt = None
                    for j in range(idx + 1, len(evs)):
                        if kind_of(evs[j][1]) == "note_on":
                            nxt = j
                            break
                    stop = len(evs) if nxt is None else nxt
                    allowed = set() if nxt is None else {nxt - 3, nxt - 2, nxt - 1}
                    for j in range(idx + 1, stop):
                        if j in allowed:
                            continue
                        if is_expr(evs[j][1]):
                            after_off_bad.append("ch%d tick%d %s"
                                                 % (ch + 1, evs[j][0], kind_of(evs[j][1])))
                            break

    rep.metric("notes", total_notes)
    rep.check("per-note order is bend -> CC74 -> pressure(0) -> note-on",
              not order_bad, "; ".join(order_bad[:4]))
    rep.check("pressure(0) immediately precedes every note_off",
              not off_bad, "; ".join(off_bad[:4]))
    rep.check("zero expression events between note-off and next note-on",
              not after_off_bad, "; ".join(after_off_bad[:4]))
    rep.check("no two simultaneous notes on one member channel",
              not overlap_bad, "; ".join(overlap_bad[:4]))

    # ---- 10. density ------------------------------------------------------ #
    worst = 0.0
    worst_ch = None
    for ch, ticks in expr_counts.items():
        if not ticks:
            continue
        window = int(round(1.0 / sec_per_tick)) if sec_per_tick > 0 else 0
        lo = 0
        for hi in range(len(ticks)):
            while ticks[hi] - ticks[lo] > window:
                lo += 1
            if hi - lo + 1 > worst:
                worst = hi - lo + 1
                worst_ch = ch
    rep.metric("max_expr_events_per_sec_per_channel", worst)
    rep.metric("busiest_channel", (worst_ch + 1) if worst_ch is not None else None)
    rep.check("<= %d expression events/second/channel" % EXPR_LIMIT_PER_SEC,
              worst <= EXPR_LIMIT_PER_SEC, "peak=%d on channel %s"
              % (worst, (worst_ch + 1) if worst_ch is not None else "-"))

    # ---- 11. thinning ratio ---------------------------------------------- #
    raw = emitted = 0
    raw_curved = emitted_curved = 0
    for ch in sorted(chans):
        evs = chans[ch]
        for on, off, pitch in note_spans(evs):
            if off < 0:
                continue
            dur_s = (off - on) * sec_per_tick
            for kinds, grid in ((("bend",), PITCH_GRID_S),
                                (("cc%d" % CC_TIMBRE,), SLOW_GRID_S),
                                (("press",), SLOW_GRID_S)):
                n_emit = sum(1 for t, d in evs if on <= t <= off and kind_of(d) in kinds)
                if n_emit == 0:
                    continue
                n_raw = int(math.floor(dur_s / grid)) + 1
                raw += n_raw
                emitted += n_emit
                if n_emit > 2:
                    raw_curved += n_raw
                    emitted_curved += n_emit
    ratio = 1.0 - (emitted / raw) if raw else 0.0
    ratio_curved = 1.0 - (emitted_curved / raw_curved) if raw_curved else 0.0
    rep.metric("raw_grid_samples", raw)
    rep.metric("emitted_expression_events", emitted)
    rep.metric("thinning_ratio_all_lanes", round(ratio, 4))
    rep.metric("thinning_ratio_curved_lanes", round(ratio_curved, 4))
    # Round-2 amendment: reported, never asserted.  Under hold semantics the
    # achievable ratio is a property of the *music* (flat/slow lanes thin to
    # almost nothing, a fast ramp cannot thin at all), so a fixed floor would
    # only be satisfiable by violating the hold-error bound checked below.
    rep.check("thinning ratio is a reported metric, not a floor",
              0.0 <= ratio_curved <= 1.0, "ratio=%.3f" % ratio_curved)

    # ---- 12. bend round-trip against the Score --------------------------- #
    if score is not None:
        o = opts or MpeOptions()
        worst_cents, where = bend_roundtrip_error(score, path, bend_range, o)
        lin_cents, _lin_where = bend_roundtrip_error(score, path, bend_range, o,
                                                     model="linear")
        budget, floor, budget_where = hold_budget_cents(score, o)
        rep.metric("max_bend_hold_error_cents", round(worst_cents, 4))
        rep.metric("max_bend_error_cents", round(worst_cents, 4))  # legacy name
        rep.metric("max_bend_linear_error_cents", round(lin_cents, 4))
        rep.metric("grid_floor_cents", round(floor, 4))
        rep.metric("hold_error_budget_cents", round(budget, 4))
        rep.check("bend hold error within tolerance (%.1f cents) at grid samples"
                  % CENTS_TOLERANCE,
                  worst_cents <= budget,
                  "worst=%.2f cents %s vs budget %.2f = %.1f tol + %.2f grid floor %s"
                  % (worst_cents, where, budget, CENTS_TOLERANCE, floor, budget_where))
    return rep


def bend_roundtrip_error(score: "ir.Score", path: str, bend_range: float,
                         opts: MpeOptions, model: str = "hold") -> tuple[float, str]:
    """Max |cents| deviation between the file's bend curve and ``score``.

    ``model="hold"`` (the default, and the only correct one) reconstructs what a
    MIDI 1.0 receiver actually does: it **holds the last transmitted value**
    until the next pitch-bend message arrives.  Nothing in RP-053 or in the MIDI
    1.0 spec licenses interpolation, so a sender that budgets its error against
    an interpolating model understates the error a real synth hears.
    ``model="linear"`` is kept only to report the old, optimistic number
    side by side (round-2 fix; see NOTES_P4.md).
    """
    smf = smf_parse.parse_smf(path)
    ppq = smf.division
    evs = smf.voice_events()
    per_ch: dict[int, list[tuple[float, float]]] = {}
    for tick, data in evs:
        if (data[0] & 0xF0) == 0xE0:
            ch = data[0] & 0x0F
            u = ((data[2] << 7) | data[1]) - 8192
            per_ch.setdefault(ch, []).append((tick / ppq, bend_to_semitones(u, bend_range)))

    def sample(pts: list[tuple[float, float]], beat: float) -> float:
        if not pts:
            return 0.0
        if beat <= pts[0][0]:
            return pts[0][1]
        held = pts[0][1]
        for t, v in pts:
            if t > beat + 1e-12:
                break
            held = v
        if model == "hold":
            return held
        for i in range(1, len(pts)):          # legacy interpolating model
            if pts[i][0] >= beat:
                t0, v0 = pts[i - 1]
                t1, v1 = pts[i]
                if t1 == t0:
                    return v1
                f = (beat - t0) / (t1 - t0)
                return v0 + f * (v1 - v0)
        return pts[-1][1]

    worst = 0.0
    where = ""
    spb = 60.0 / max(1e-9, score.tempo)
    grid_beats = (opts.pitch_grid_ms / 1000.0) / spb
    for st in score.staves:
        for n in st.notes:
            if n.channel is None or n.dur <= 0:
                continue
            pts = per_ch.get(n.channel, [])
            pts = [p for p in pts if n.start - 1e-9 <= p[0] <= n.end + 1e-9]
            steps = max(1, int(n.dur / grid_beats))
            for i in range(steps):
                t = n.start + i * grid_beats
                if t >= n.end:
                    break
                want = n.detune
                c = n.curves.get(ir.BEND)
                if c is not None and c.points:
                    v = c.value_at(t)
                    if v is None or math.isnan(v):
                        continue
                    want += v
                want = max(-bend_range, min(bend_range, want))
                got = sample(pts, t)
                cents = abs(got - want) * 100.0
                if cents > worst:
                    worst = cents
                    where = "(pitch %d, beat %.3f, ch %d)" % (n.pitch, t, n.channel + 1)
    return worst, where


# --------------------------------------------------------------------------- #
# synthetic score (also imported by tests/test_mpe.py)
# --------------------------------------------------------------------------- #

def curve(lane: str, fn, start: float, dur: float, n: int = 65) -> ir.Curve:
    pts = [(start + dur * i / (n - 1), float(fn(i / (n - 1)))) for i in range(n)]
    return ir.Curve(lane=lane, points=pts)


def synthetic_score(tempo: float = 120.0) -> ir.Score:
    """A deterministic score exercising bend/press/timbre/cc lanes and chords."""
    lead = ir.StaveIR(name="lead")
    nid = 0
    # 1) plain note, no curves
    lead.notes.append(ir.Note(start=0.0, dur=1.0, pitch=60, velocity=90,
                              stave="lead", id=nid)); nid += 1
    # 2) vibrato: 6 Hz, +-0.25 st  (dur 2 beats == 1 s at 120 bpm)
    lead.notes.append(ir.Note(
        start=1.0, dur=2.0, pitch=64, velocity=100, stave="lead", id=nid,
        curves={ir.BEND: curve(ir.BEND,
                               lambda t: 0.25 * math.sin(2 * math.pi * 6.0 * t),
                               1.0, 2.0, 401)})); nid += 1
    # 3) scoop up + pressure swell + timbre close, plus CC11
    lead.notes.append(ir.Note(
        start=3.0, dur=2.0, pitch=67, velocity=80, stave="lead", id=nid,
        detune=0.0,
        curves={
            ir.BEND: curve(ir.BEND, lambda t: -1.0 * max(0.0, 1.0 - t / 0.2), 3.0, 2.0, 201),
            ir.PRESS: curve(ir.PRESS, lambda t: t, 3.0, 2.0, 201),
            ir.TIMBRE: curve(ir.TIMBRE, lambda t: 1.0 - 0.6 * t, 3.0, 2.0, 201),
            ir.AMP: curve(ir.AMP, lambda t: 0.5 + 0.5 * t, 3.0, 2.0, 201),
        })); nid += 1
    # 4) microtonal static detune
    lead.notes.append(ir.Note(start=5.0, dur=1.0, pitch=69, velocity=70,
                              stave="lead", detune=0.5, id=nid)); nid += 1

    pad = ir.StaveIR(name="pad")
    # a 4-note chord (channel spread) plus a repeated pitch for same-pitch affinity
    for i, p in enumerate((48, 52, 55, 59)):
        pad.notes.append(ir.Note(start=0.0, dur=4.0, pitch=p, velocity=64,
                                 stave="pad", id=nid)); nid += 1
    for i in range(3):
        pad.notes.append(ir.Note(start=4.0 + i, dur=0.9, pitch=50, velocity=60,
                                 stave="pad", id=nid)); nid += 1
    pad.chords.append(ir.ChordEvent(start=0.0, dur=4.0, symbol="Cmaj7", root_pc=0,
                                    quality="maj7", pitches=[48, 52, 55, 59],
                                    pitch_classes=[0, 4, 7, 11], guide_tones=[4, 11],
                                    stave="pad"))
    return ir.Score(tempo=tempo, meter=(4, 4), ppq=960, bend_range=48.0,
                    grid_ms=10.0, title="synthetic", staves=[lead, pad])


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit a .mid for MPE conformance")
    ap.add_argument("midi", nargs="?", help="path to a .mid file")
    ap.add_argument("--synth", action="store_true",
                    help="render the built-in synthetic score and audit that")
    ap.add_argument("--ppq", type=int, default=960)
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = ap.parse_args(argv)

    score = None
    opts = None
    path = args.midi
    tmpdir = None
    if args.synth or not path:
        score = synthetic_score()
        opts = MpeOptions(ppq=args.ppq)
        tmpdir = tempfile.mkdtemp(prefix="filigree-audit-")
        path = os.path.join(tmpdir, "synthetic.mid")
        write_midi(score, path, opts)
        st = render_stats(score, opts)
        print("rendered %s (%d notes, thinning %.1f%%)"
              % (path, st.note_count, st.thinning_ratio * 100.0))
    elif not os.path.exists(path):
        print("no such file: %s" % path, file=sys.stderr)
        return 2

    rep = audit_file(path, expect_ppq=args.ppq, score=score, opts=opts)
    print(rep.to_json() if args.json else rep.render())
    return 1 if rep.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
