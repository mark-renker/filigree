#!/usr/bin/env python3
"""An independent, hand-written Standard MIDI File parser — **no mido**.

Used to cross-check `filigree.mpe` output: refs/BAR.md P4 requires the rendered
file to parse identically under mido and under a second implementation.
Everything here is written straight from the SMF chunk format: a ``MThd`` header
chunk (format, ntrks, division) followed by ``MTrk`` chunks of
``<delta-time varlen><event>``, with running status, meta events (``FF type
len data``) and sysex (``F0``/``F7`` with a varlen length).

Owned by piece P4.  Standard library only.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Optional

META = 0xFF
SYSEX_F0 = 0xF0
SYSEX_F7 = 0xF7

# data byte count for each channel-voice status high nibble
_VOICE_LEN = {0x80: 2, 0x90: 2, 0xA0: 2, 0xB0: 2, 0xC0: 1, 0xD0: 1, 0xE0: 2}


class SmfError(Exception):
    """Malformed MIDI file."""


@dataclass
class Event:
    tick: int                       # absolute tick within its track
    delta: int
    data: bytes                     # raw bytes, status byte included (expanded)
    kind: str                       # 'voice' | 'meta' | 'sysex'
    meta_type: Optional[int] = None
    meta_data: bytes = b""

    # ---- convenience accessors -------------------------------------------- #
    @property
    def status(self) -> int:
        return self.data[0]

    @property
    def channel(self) -> Optional[int]:
        if self.kind != "voice":
            return None
        return self.status & 0x0F

    @property
    def type_nibble(self) -> Optional[int]:
        if self.kind != "voice":
            return None
        return self.status & 0xF0

    @property
    def name(self) -> str:
        if self.kind == "meta":
            return {0x03: "track_name", 0x51: "set_tempo", 0x58: "time_signature",
                    0x2F: "end_of_track"}.get(self.meta_type or -1,
                                              "meta_%02X" % (self.meta_type or 0))
        if self.kind == "sysex":
            return "sysex"
        n = self.type_nibble
        return {0x80: "note_off", 0x90: "note_on", 0xA0: "polytouch",
                0xB0: "control_change", 0xC0: "program_change",
                0xD0: "aftertouch", 0xE0: "pitchwheel"}.get(n or 0, "unknown")

    @property
    def bend_value(self) -> Optional[int]:
        """Signed 14-bit pitchwheel value (-8192..8191)."""
        if self.type_nibble != 0xE0:
            return None
        return ((self.data[2] << 7) | self.data[1]) - 8192


@dataclass
class Track:
    events: list[Event] = field(default_factory=list)

    @property
    def name(self) -> str:
        for e in self.events:
            if e.kind == "meta" and e.meta_type == 0x03:
                return e.meta_data.decode("latin-1")
        return ""


@dataclass
class SmfFile:
    fmt: int
    ntrks: int
    division: int                   # ticks per quarter note (positive division)
    tracks: list[Track] = field(default_factory=list)

    @property
    def ppq(self) -> int:
        if self.division <= 0:
            raise SmfError("SMPTE division is not supported by this parser")
        return self.division

    def tempo(self) -> int:
        """First ``set_tempo`` value in microseconds per quarter (default 500000)."""
        for tr in self.tracks:
            for e in tr.events:
                if e.kind == "meta" and e.meta_type == 0x51 and len(e.meta_data) == 3:
                    return (e.meta_data[0] << 16) | (e.meta_data[1] << 8) | e.meta_data[2]
        return 500000

    def voice_events(self) -> list[tuple[int, bytes]]:
        """All channel-voice events, merged across tracks, stable-sorted by tick.

        Track order is the tie-break, matching how a sequencer reads an SMF-1
        file and how ``mido.merge_tracks`` orders simultaneous events.
        """
        out: list[tuple[int, int, int, bytes]] = []
        for ti, tr in enumerate(self.tracks):
            for i, e in enumerate(tr.events):
                if e.kind == "voice":
                    out.append((e.tick, ti, i, e.data))
        out.sort(key=lambda r: (r[0], r[1], r[2]))
        return [(t, d) for t, _, _, d in out]


# --------------------------------------------------------------------------- #
# byte-level reader
# --------------------------------------------------------------------------- #

class _Reader:
    def __init__(self, buf: bytes, pos: int = 0, end: Optional[int] = None):
        self.buf = buf
        self.pos = pos
        self.end = len(buf) if end is None else end

    def byte(self) -> int:
        if self.pos >= self.end:
            raise SmfError("unexpected end of data")
        b = self.buf[self.pos]
        self.pos += 1
        return b

    def take(self, n: int) -> bytes:
        if self.pos + n > self.end:
            raise SmfError("unexpected end of data")
        out = self.buf[self.pos:self.pos + n]
        self.pos += n
        return out

    def u16(self) -> int:
        b = self.take(2)
        return (b[0] << 8) | b[1]

    def u32(self) -> int:
        b = self.take(4)
        return (b[0] << 24) | (b[1] << 16) | (b[2] << 8) | b[3]

    def varlen(self) -> int:
        value = 0
        for _ in range(4):
            b = self.byte()
            value = (value << 7) | (b & 0x7F)
            if not b & 0x80:
                return value
        raise SmfError("variable-length quantity longer than 4 bytes")

    def eof(self) -> bool:
        return self.pos >= self.end


def _parse_track(buf: bytes, start: int, length: int) -> Track:
    r = _Reader(buf, start, start + length)
    tr = Track()
    tick = 0
    running: Optional[int] = None
    while not r.eof():
        delta = r.varlen()
        tick += delta
        b = r.byte()
        if b == META:
            mtype = r.byte()
            n = r.varlen()
            data = r.take(n)
            tr.events.append(Event(tick, delta, bytes([META, mtype]) + data,
                                   "meta", mtype, data))
            if mtype == 0x2F:                     # end of track
                break
            continue
        if b in (SYSEX_F0, SYSEX_F7):
            n = r.varlen()
            data = r.take(n)
            tr.events.append(Event(tick, delta, bytes([b]) + data, "sysex"))
            continue
        if b & 0x80:
            status = b
            running = status
            first: Optional[int] = None
        else:
            if running is None:
                raise SmfError("running status used before any status byte")
            status = running
            first = b
        high = status & 0xF0
        if high not in _VOICE_LEN:
            raise SmfError("unsupported status byte 0x%02X" % status)
        need = _VOICE_LEN[high]
        vals: list[int] = []
        if first is not None:
            vals.append(first)
        while len(vals) < need:
            vals.append(r.byte())
        for v in vals:
            if v & 0x80:
                raise SmfError("data byte 0x%02X has its high bit set" % v)
        tr.events.append(Event(tick, delta, bytes([status]) + bytes(vals), "voice"))
    return tr


def parse_smf(path: str) -> SmfFile:
    """Parse a Standard MIDI File into an :class:`SmfFile`."""
    with open(path, "rb") as fh:
        buf = fh.read()
    return parse_bytes(buf)


def parse_bytes(buf: bytes) -> SmfFile:
    if len(buf) < 14 or buf[0:4] != b"MThd":
        raise SmfError("missing MThd header chunk")
    r = _Reader(buf)
    r.take(4)
    hlen = r.u32()
    if hlen < 6:
        raise SmfError("MThd length %d < 6" % hlen)
    fmt = r.u16()
    ntrks = r.u16()
    division = r.u16()
    if division & 0x8000:                         # SMPTE
        division = -(((division >> 8) & 0x7F) * (division & 0xFF))
    r.take(hlen - 6)
    smf = SmfFile(fmt=fmt, ntrks=ntrks, division=division)
    while r.pos + 8 <= len(buf):
        cid = r.take(4)
        clen = r.u32()
        if cid == b"MTrk":
            smf.tracks.append(_parse_track(buf, r.pos, clen))
        r.pos += clen
    if len(smf.tracks) != ntrks:
        raise SmfError("header claims %d tracks, found %d" % (ntrks, len(smf.tracks)))
    return smf


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: smf_parse.py FILE.mid [--events]", file=sys.stderr)
        return 2
    smf = parse_smf(argv[1])
    print("format=%d tracks=%d ppq=%d tempo=%dus" %
          (smf.fmt, smf.ntrks, smf.division, smf.tempo()))
    for i, tr in enumerate(smf.tracks):
        print("  track %d %-24r events=%d" % (i, tr.name, len(tr.events)))
    if "--events" in argv:
        for tick, data in smf.voice_events():
            print("%8d  %s" % (tick, " ".join("%02X" % b for b in data)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
