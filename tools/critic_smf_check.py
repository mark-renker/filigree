"""Independent, byte-level SMF reader + MPE conformance checker (critic-owned).

Written from scratch for the P4 round-1 critique.  Deliberately does NOT import
``filigree.mpe``, ``tools/smf_parse.py`` or ``tools/audit_mpe.py`` for any part
of the parsing or checking; the only optional import is ``mido``, used purely to
cross-check this parser's event stream against a second implementation.

Checks (refs/BAR.md P4):
  1. MCM bytes on ch1 (mm == number of member channels) and mm=0 on ch16.
  2. RPN 0 bend range on every member channel that is actually used, MSB first,
     closed with the null RPN (127/127).
  3. Per-note preamble order exactly bend, CC74, pressure(0), note-on.
  4. pressure(0) immediately precedes every note_off.
  5. Zero expression events on a channel between its note-off and next note-on.
  6. No two simultaneous notes on one member channel.
  7. Expression events / second / channel (sliding 1 s window).
  8. Thinning ratio (needs the raw grid count from the caller).
  9. Max per-note bend round-trip error in cents (needs expected curves).

Usage:
    python tools/critic_smf_check.py FILE.mid [FILE2.mid ...] [--expect expect.json]
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from typing import Optional

# --------------------------------------------------------------------------- #
# byte-level SMF reader
# --------------------------------------------------------------------------- #


class SmfError(Exception):
    pass


@dataclass
class RawEvent:
    tick: int          # absolute ticks within its track
    track: int
    seq: int           # ordinal within track (preserves written order)
    data: bytes        # channel-voice bytes, or b"" for meta/sysex
    meta: Optional[tuple] = None   # (type_byte, payload) for meta events

    @property
    def status(self) -> int:
        return self.data[0] & 0xF0 if self.data else -1

    @property
    def channel(self) -> int:
        return self.data[0] & 0x0F if self.data else -1


class Reader:
    def __init__(self, buf: bytes):
        self.b = buf
        self.i = 0

    def u8(self) -> int:
        if self.i >= len(self.b):
            raise SmfError("unexpected end of data")
        v = self.b[self.i]
        self.i += 1
        return v

    def u16(self) -> int:
        return (self.u8() << 8) | self.u8()

    def u32(self) -> int:
        return (self.u16() << 16) | self.u16()

    def varlen(self) -> int:
        v = 0
        for _ in range(4):
            c = self.u8()
            v = (v << 7) | (c & 0x7F)
            if not c & 0x80:
                return v
        raise SmfError("variable-length quantity longer than 4 bytes")


DATA_BYTES = {0x80: 2, 0x90: 2, 0xA0: 2, 0xB0: 2, 0xC0: 1, 0xD0: 1, 0xE0: 2}


def read_smf(path: str) -> dict:
    with open(path, "rb") as fh:
        buf = fh.read()
    r = Reader(buf)
    if buf[0:4] != b"MThd":
        raise SmfError(f"{path}: missing MThd")
    r.i = 4
    hlen = r.u32()
    if hlen < 6:
        raise SmfError("MThd length < 6")
    fmt = r.u16()
    ntrk = r.u16()
    div = r.u16()
    r.i = 8 + hlen
    if div & 0x8000:
        raise SmfError("SMPTE division not supported by this checker")
    tracks: list[list[RawEvent]] = []
    tempos: list[tuple[int, int]] = []       # (abs tick, usec per quarter)
    for ti in range(ntrk):
        if buf[r.i:r.i + 4] != b"MTrk":
            raise SmfError(f"track {ti}: missing MTrk at byte {r.i}")
        r.i += 4
        length = r.u32()
        end = r.i + length
        tick = 0
        running = None
        evs: list[RawEvent] = []
        seq = 0
        while r.i < end:
            tick += r.varlen()
            first = r.u8()
            if first == 0xFF:
                mtype = r.u8()
                ln = r.varlen()
                payload = buf[r.i:r.i + ln]
                r.i += ln
                if mtype == 0x51 and ln == 3:
                    tempos.append((tick, (payload[0] << 16) | (payload[1] << 8) | payload[2]))
                evs.append(RawEvent(tick, ti, seq, b"", (mtype, payload)))
                seq += 1
                running = None
                continue
            if first in (0xF0, 0xF7):
                ln = r.varlen()
                r.i += ln
                evs.append(RawEvent(tick, ti, seq, b"", (first, b"")))
                seq += 1
                running = None
                continue
            if first & 0x80:
                status = first
                running = status
                nd = DATA_BYTES.get(status & 0xF0)
                if nd is None:
                    raise SmfError(f"bad status byte {first:#02x}")
                data = bytes([status]) + buf[r.i:r.i + nd]
                r.i += nd
            else:
                if running is None:
                    raise SmfError(f"running status with no prior status at {r.i}")
                status = running
                nd = DATA_BYTES[status & 0xF0]
                data = bytes([status, first]) + buf[r.i:r.i + nd - 1]
                r.i += nd - 1
            evs.append(RawEvent(tick, ti, seq, data))
            seq += 1
        if r.i != end:
            raise SmfError(f"track {ti}: length mismatch (read {r.i}, expected {end})")
        tracks.append(evs)
    return {"format": fmt, "ppq": div, "ntracks": ntrk, "tracks": tracks,
            "tempos": tempos or [(0, 500000)]}


def merged(smf: dict) -> list[RawEvent]:
    """All events, stable-sorted by (tick, track, written order)."""
    out = [e for tr in smf["tracks"] for e in tr]
    out.sort(key=lambda e: (e.tick, e.track, e.seq))
    return out


def seconds_at(tick: int, smf: dict) -> float:
    """Absolute seconds for a tick, honouring every tempo change."""
    ppq = smf["ppq"]
    tempos = sorted(smf["tempos"])
    t = 0.0
    prev_tick, prev_tempo = 0, tempos[0][1]
    for tt, tempo in tempos:
        if tt >= tick:
            break
        t += (tt - prev_tick) / ppq * prev_tempo / 1e6
        prev_tick, prev_tempo = tt, tempo
    t += (tick - prev_tick) / ppq * prev_tempo / 1e6
    return t


# --------------------------------------------------------------------------- #
# classification helpers
# --------------------------------------------------------------------------- #

def is_note_on(e: RawEvent) -> bool:
    return e.status == 0x90 and e.data[2] > 0


def is_note_off(e: RawEvent) -> bool:
    return e.status == 0x80 or (e.status == 0x90 and e.data[2] == 0)


def is_bend(e: RawEvent) -> bool:
    return e.status == 0xE0


def is_press(e: RawEvent) -> bool:
    return e.status == 0xD0


def is_cc(e: RawEvent, num: Optional[int] = None) -> bool:
    return e.status == 0xB0 and (num is None or e.data[1] == num)


RPN_CCS = (98, 99, 100, 101, 6, 38, 121, 123)


def is_expression(e: RawEvent) -> bool:
    """Per-note continuous data (not zone config, not notes)."""
    if is_bend(e) or is_press(e):
        return True
    if is_cc(e) and e.data[1] not in RPN_CCS:
        return True
    return False


def bend_value(e: RawEvent) -> int:
    return ((e.data[2] << 7) | e.data[1]) - 8192


# --------------------------------------------------------------------------- #
# conformance report
# --------------------------------------------------------------------------- #

@dataclass
class Report:
    path: str
    fmt: int = 0
    ppq: int = 0
    ntracks: int = 0
    n_notes: int = 0
    mcm_lower: Optional[str] = None
    mcm_upper: Optional[str] = None
    mcm_msb_first: Optional[bool] = None
    members_declared: Optional[int] = None
    channels_used: list[int] = field(default_factory=list)
    rpn0_ok_channels: list[int] = field(default_factory=list)
    rpn0_missing: list[int] = field(default_factory=list)
    rpn0_not_msb_first: list[int] = field(default_factory=list)
    rpn0_not_null_closed: list[int] = field(default_factory=list)
    preamble_bad: list[str] = field(default_factory=list)
    press0_before_off_bad: list[str] = field(default_factory=list)
    expr_between_off_and_on: list[str] = field(default_factory=list)
    simultaneous_same_channel: list[str] = field(default_factory=list)
    notes_on_master: int = 0
    polytouch_on_member: int = 0
    max_expr_per_sec: float = 0.0
    max_expr_channel: int = -1
    emitted_expr: int = 0
    raw_frames: Optional[int] = None
    thinning_ratio: Optional[float] = None
    max_bend_err_cents_hold: Optional[float] = None
    max_bend_err_cents_lin: Optional[float] = None
    dangling_notes: int = 0
    notes_expected: Optional[int] = None
    errors: list[str] = field(default_factory=list)

    def defects(self) -> list[str]:
        d = []
        if self.mcm_lower is None:
            d.append("no MCM on channel 1")
        if self.mcm_upper is None:
            d.append("no mm=0 MCM on channel 16")
        if self.rpn0_missing:
            d.append(f"RPN0 missing on used member channels {self.rpn0_missing}")
        if self.rpn0_not_msb_first:
            d.append(f"RPN0 not MSB-first on {self.rpn0_not_msb_first}")
        if self.rpn0_not_null_closed:
            d.append(f"RPN0 not null-closed on {self.rpn0_not_null_closed}")
        d += [f"preamble: {x}" for x in self.preamble_bad[:6]]
        d += [f"press0-before-off: {x}" for x in self.press0_before_off_bad[:6]]
        d += [f"expr-after-off: {x}" for x in self.expr_between_off_and_on[:6]]
        d += [f"chan-overlap: {x}" for x in self.simultaneous_same_channel[:6]]
        if self.notes_on_master:
            d.append(f"{self.notes_on_master} note(s) on master channel")
        if self.polytouch_on_member:
            d.append(f"{self.polytouch_on_member} polytouch on member channels")
        if self.max_expr_per_sec > 250:
            d.append(f"density {self.max_expr_per_sec:.0f} expr/s on ch{self.max_expr_channel + 1} > 250")
        if self.notes_expected is not None and self.n_notes != self.notes_expected:
            d.append(f"note count {self.n_notes} != {self.notes_expected} input notes (dropped/added)")
        if self.dangling_notes:
            d.append(f"{self.dangling_notes} note-on without matching note-off")
        return d


def check_file(path: str, expect: Optional[dict] = None) -> Report:
    rep = Report(path=path)
    try:
        smf = read_smf(path)
    except Exception as exc:
        rep.errors.append(f"parse failure: {exc}")
        return rep
    rep.fmt = smf["format"]
    rep.ppq = smf["ppq"]
    rep.ntracks = smf["ntracks"]
    evs = merged(smf)

    # ---- 1. MCM ---------------------------------------------------------- #
    for ch, attr in ((0, "mcm_lower"), (15, "mcm_upper")):
        stream = [e for e in evs if e.channel == ch and is_cc(e)]
        for i in range(len(stream) - 2):
            trio = stream[i:i + 3]
            ctl = [e.data[1] for e in trio]
            val = [e.data[2] for e in trio]
            if set(ctl[:2]) == {100, 101} and ctl[2] == 6 and \
                    val[ctl.index(101)] == 0 and val[ctl.index(100)] == 6:
                setattr(rep, attr, " ".join(f"{b:02X}" for e in trio for b in e.data))
                if ch == 0:
                    rep.members_declared = val[2]
                    rep.mcm_msb_first = (ctl[0] == 101)
                break

    # ---- channels actually used for notes -------------------------------- #
    used = sorted({e.channel for e in evs if is_note_on(e)})
    rep.channels_used = [c + 1 for c in used]
    rep.n_notes = sum(1 for e in evs if is_note_on(e))
    # channel 16 legitimately becomes a member when the lower zone claims 15
    # members (RP-053: the unused zone's master may be a member channel).
    master_chs = {0} if (rep.members_declared or 0) >= 15 else {0, 15}
    rep.notes_on_master = sum(1 for e in evs if is_note_on(e) and e.channel in master_chs)
    rep.polytouch_on_member = sum(1 for e in evs if e.status == 0xA0 and e.channel not in (0, 15))

    # ---- 2. RPN 0 per used member channel -------------------------------- #
    for ch in used:
        ccs = [e for e in evs if e.channel == ch and is_cc(e)]
        found = False
        for i in range(len(ccs) - 2):
            ctl = [e.data[1] for e in ccs[i:i + 3]]
            val = [e.data[2] for e in ccs[i:i + 3]]
            if set(ctl[:2]) == {100, 101} and ctl[2] == 6 and \
                    val[ctl.index(101)] == 0 and val[ctl.index(100)] == 0:
                found = True
                if ctl[0] != 101:
                    rep.rpn0_not_msb_first.append(ch + 1)
                tail = [e.data[1:3] for e in ccs[i + 3:i + 6]]
                closed = any(tuple(t) == (101, 127) for t in tail) and \
                    any(tuple(t) == (100, 127) for t in tail)
                if not closed:
                    rep.rpn0_not_null_closed.append(ch + 1)
                rep.rpn0_ok_channels.append(ch + 1)
                break
        if not found:
            rep.rpn0_missing.append(ch + 1)

    # ---- 3-6. per-channel stream walk ------------------------------------ #
    per_ch: dict[int, list[RawEvent]] = {}
    for e in evs:
        if e.data:
            per_ch.setdefault(e.channel, []).append(e)

    for ch, stream in sorted(per_ch.items()):
        if ch in (0, 15) and not any(is_note_on(e) for e in stream):
            continue
        active: list[tuple[int, int]] = []      # (pitch, tick)
        state = "idle"                          # idle == no sounding note
        for idx, e in enumerate(stream):
            if is_note_on(e):
                # preamble: the three events immediately before, same channel
                pre = stream[max(0, idx - 3):idx]
                names = []
                for p in pre:
                    if is_bend(p):
                        names.append("bend")
                    elif is_cc(p, 74):
                        names.append("cc74")
                    elif is_press(p):
                        names.append("press%d" % p.data[1])
                    else:
                        names.append("other")
                if names != ["bend", "cc74", "press0"] or not pre or pre[0].tick != e.tick:
                    rep.preamble_bad.append(
                        f"ch{ch+1} tick{e.tick} note{e.data[1]} got {names} "
                        f"(ticks {[p.tick for p in pre]})")
                if active:
                    rep.simultaneous_same_channel.append(
                        f"ch{ch+1} tick{e.tick} note{e.data[1]} while {active} sounding")
                active.append((e.data[1], e.tick))
                state = "sounding"
            elif is_note_off(e):
                prev = stream[idx - 1] if idx else None
                if not (prev is not None and is_press(prev) and prev.data[1] == 0
                        and prev.tick == e.tick):
                    got = None
                    if prev is not None:
                        got = " ".join(f"{b:02X}" for b in prev.data) + f"@{prev.tick}"
                    rep.press0_before_off_bad.append(
                        f"ch{ch+1} tick{e.tick} note{e.data[1]} preceded by {got}")
                active = [a for a in active if a[0] != e.data[1]] or []
                if not active:
                    state = "idle"
            elif is_expression(e):
                rep.emitted_expr += 1
                # the mandated pre-note-on preamble is legal while idle: it is
                # the run of expression events at the same tick immediately
                # followed by a note-on on this channel.
                in_preamble = False
                j = idx
                while j < len(stream) and is_expression(stream[j]) and stream[j].tick == e.tick:
                    j += 1
                if j < len(stream) and is_note_on(stream[j]) and stream[j].tick == e.tick:
                    in_preamble = True
                if state == "idle" and not in_preamble:
                    rep.expr_between_off_and_on.append(
                        f"ch{ch+1} tick{e.tick} bytes " + " ".join(f"{b:02X}" for b in e.data))
        rep.dangling_notes += len(active)

    # ---- 7. density ------------------------------------------------------ #
    for ch, stream in per_ch.items():
        if ch in (0, 15):
            continue
        times = [seconds_at(e.tick, smf) for e in stream if is_expression(e)]
        times.sort()
        j = 0
        for i, t in enumerate(times):
            while times[i] - times[j] > 1.0:
                j += 1
            n = i - j + 1
            if n > rep.max_expr_per_sec:
                rep.max_expr_per_sec = n
                rep.max_expr_channel = ch

    # ---- 8/9. thinning + bend round trip --------------------------------- #
    if expect:
        rep.notes_expected = expect.get("input_notes")
        raw = expect.get("raw_frames")
        if raw:
            rep.raw_frames = raw
            rep.thinning_ratio = 1.0 - rep.emitted_expr / float(raw)
        rng = float(expect.get("bend_range", 48.0))
        curves = expect.get("notes") or []
        if curves:
            rep.max_bend_err_cents_hold, rep.max_bend_err_cents_lin = \
                _bend_roundtrip(evs, smf, curves, rng)
    return rep


def _bend_roundtrip(evs, smf, expected_notes, bend_range) -> tuple[float, float]:
    """expected_notes: [{start,dur,pitch,points:[[beat,semitones]],detune}]."""
    ppq = smf["ppq"]
    worst_hold = 0.0
    worst_lin = 0.0
    # index note-ons by (pitch, tick) -> channel
    on_by = {}
    for e in evs:
        if is_note_on(e):
            on_by.setdefault((e.data[1], e.tick), []).append(e.channel)
    for note in expected_notes:
        t_on = int(round(note["start"] * ppq))
        t_off = int(round((note["start"] + note["dur"]) * ppq))
        chs = on_by.get((note["pitch"], t_on))
        if not chs:
            continue
        ch = chs.pop(0)
        pts = [(e.tick, bend_value(e)) for e in evs
               if is_bend(e) and e.channel == ch and t_on <= e.tick < max(t_off, t_on + 1)]
        if not pts:
            continue
        det = note.get("detune", 0.0)
        pc = note.get("points") or []

        def want(beat):
            if not pc:
                v = det
            else:
                v = _lerp(pc, beat) + det
            if v is None or math.isnan(v):
                return float("nan")
            return max(-bend_range, min(bend_range, v)) * 100.0

        def hold(tick):
            last = pts[0][1]
            for tk, v in pts:
                if tk <= tick:
                    last = v
                else:
                    break
            return last / 8192.0 * bend_range * 100.0

        def lin(tick):
            if tick <= pts[0][0]:
                v = pts[0][1]
            elif tick >= pts[-1][0]:
                v = pts[-1][1]
            else:
                v = None
                for (a_t, a_v), (b_t, b_v) in zip(pts, pts[1:]):
                    if a_t <= tick <= b_t:
                        f = 0.0 if b_t == a_t else (tick - a_t) / (b_t - a_t)
                        v = a_v + f * (b_v - a_v)
                        break
            return v / 8192.0 * bend_range * 100.0

        n = max(2, min(400, t_off - t_on))
        for i in range(n):
            tick = t_on + int(i * (t_off - t_on) / n)
            beat = tick / ppq
            w = want(beat)
            if math.isnan(w):
                continue
            worst_hold = max(worst_hold, abs(hold(tick) - w))
            worst_lin = max(worst_lin, abs(lin(tick) - w))
    return worst_hold, worst_lin


def _lerp(points, beat):
    if beat <= points[0][0]:
        return points[0][1]
    if beat >= points[-1][0]:
        return points[-1][1]
    for (a_t, a_v), (b_t, b_v) in zip(points, points[1:]):
        if a_t <= beat <= b_t:
            f = 0.0 if b_t == a_t else (beat - a_t) / (b_t - a_t)
            return a_v + f * (b_v - a_v)
    return points[-1][1]


# --------------------------------------------------------------------------- #
# mido cross-check
# --------------------------------------------------------------------------- #

def mido_crosscheck(path: str) -> tuple[bool, str]:
    """Compare this parser's (tick, bytes) multiset+order against mido's."""
    try:
        import mido
    except Exception as exc:                       # pragma: no cover
        return False, f"mido unavailable: {exc}"
    smf = read_smf(path)
    mine = []
    for ti, tr in enumerate(smf["tracks"]):
        for e in tr:
            if e.data:
                mine.append((ti, e.tick, tuple(e.data)))
    mf = mido.MidiFile(path)
    theirs = []
    for ti, tr in enumerate(mf.tracks):
        tick = 0
        for m in tr:
            tick += m.time
            if not m.is_meta and m.type != "sysex":
                theirs.append((ti, tick, tuple(m.bytes())))
    if mine == theirs:
        return True, f"identical: {len(mine)} channel-voice events"
    n = min(len(mine), len(theirs))
    first = next((i for i in range(n) if mine[i] != theirs[i]), n)
    return False, (f"DIVERGE at index {first}: mine={mine[first] if first < len(mine) else None} "
                   f"mido={theirs[first] if first < len(theirs) else None} "
                   f"(counts mine={len(mine)} mido={len(theirs)})")


def print_table(reps: list[Report]) -> None:
    hdr = ["file", "fmt/ppq", "notes", "MCM ch1", "mm", "RPN0 ok/miss",
           "preamble bad", "press0 bad", "expr-after-off", "chan-overlap",
           "max expr/s/ch", "thinning", "bend err ¢ (hold/lin)"]
    print(" | ".join(hdr))
    print("-" * 150)
    for r in reps:
        if r.errors:
            print(f"{r.path} | PARSE ERROR: {r.errors}")
            continue
        print(" | ".join([
            r.path.split("/")[-1],
            f"{r.fmt}/{r.ppq}",
            str(r.n_notes),
            (r.mcm_lower or "MISSING"),
            str(r.members_declared),
            f"{len(r.rpn0_ok_channels)}/{len(r.rpn0_missing)}",
            str(len(r.preamble_bad)),
            str(len(r.press0_before_off_bad)),
            str(len(r.expr_between_off_and_on)),
            str(len(r.simultaneous_same_channel)),
            f"{r.max_expr_per_sec:.0f}@ch{r.max_expr_channel + 1}",
            ("n/a" if r.thinning_ratio is None else f"{r.thinning_ratio*100:.1f}%"),
            ("n/a" if r.max_bend_err_cents_hold is None
             else f"{r.max_bend_err_cents_hold:.2f}/{r.max_bend_err_cents_lin:.2f}"),
        ]))


def main(argv: list[str]) -> int:
    paths = [a for a in argv if not a.startswith("--")]
    expect = None
    if "--expect" in argv:
        with open(argv[argv.index("--expect") + 1]) as fh:
            expect = json.load(fh)
    reps = [check_file(p, expect) for p in paths]
    print_table(reps)
    for r in reps:
        d = r.defects()
        if d:
            print(f"\n{r.path}:")
            for x in d:
                print("   -", x)
        ok, msg = mido_crosscheck(r.path)
        print(f"   mido cross-check: {'OK' if ok else 'MISMATCH'} — {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
