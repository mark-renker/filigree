"""Filigree Performance IR — the contract between resolve.py and the renderers.

Owned by the lead agent. This is the single hand-off point: anything that can
render Filigree (SMF writer, realtime player, web playground, piano-roll
plotter) consumes ONLY this.

Units, fixed:
  * time            : beats (quarter notes), float, 0.0 == start of bar 1
  * pitch           : MIDI note number, int
  * detune          : semitones, float (static microtonal offset of a note)
  * velocity        : 1..127 int
  * bend curve      : semitones, float (bipolar, typically -2..+2, clamped to
                      the MPE member bend range at render time)
  * press curve     : 0.0..1.0
  * timbre curve    : 0.0..1.0 (0.5 == centre)
  * amp curve       : 0.0..1.0 (rendered as CC11)
  * pan curve       : 0.0..1.0 (0.5 == centre, channel-scoped)
  * cc<n> curve     : 0.0..1.0
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

BEND = "bend"
PRESS = "press"
TIMBRE = "timbre"
AMP = "amp"
PAN = "pan"

LANE_RANGES: dict[str, tuple[float, float]] = {
    BEND: (-2.0, 2.0),      # overridable per lane via options
    PRESS: (0.0, 1.0),
    TIMBRE: (0.0, 1.0),
    AMP: (0.0, 1.0),
    PAN: (0.0, 1.0),
}

BIPOLAR = {BEND}


@dataclass
class Curve:
    """A sampled expression curve attached to one note, in absolute beats.

    ``points`` is a list of (beat, value) pairs sorted by beat, already
    thinned/deduplicated by the resolver but NOT yet quantised to MIDI
    resolution.  The first point is at or before ``Note.start`` and the last is
    at or before ``Note.start + Note.dur``.

    A NaN value is a **gap sentinel**: it means "write no data from here until the
    next non-NaN point".  Renderers must not emit MIDI for a gap; JSON encodes it
    as ``null``.
    """

    lane: str
    points: list[tuple[float, float]] = field(default_factory=list)

    def spans(self) -> list[list[tuple[float, float]]]:
        """Contiguous runs of real data, split at NaN gap sentinels."""
        out: list[list[tuple[float, float]]] = []
        run: list[tuple[float, float]] = []
        for t, v in self.points:
            if v != v or t != t:  # NaN
                if run:
                    out.append(run)
                    run = []
                continue
            run.append((t, v))
        if run:
            out.append(run)
        return out

    def _starts_with_gap(self) -> bool:
        for _, v in self.points:
            return v != v
        return False

    def _ends_with_gap(self) -> bool:
        for _, v in reversed(self.points):
            return v != v
        return False

    def real_points(self) -> list[tuple[float, float]]:
        return [(t, v) for t, v in self.points if v == v and t == t]

    def value_at(self, beat: float) -> float:
        """Value at ``beat``, or NaN if ``beat`` falls inside a gap.

        Interpolation happens only *within* a contiguous span of real data, so a
        gap sentinel is never bridged.
        """
        spans = self.spans()
        if not spans:
            return 0.0
        # locate the span containing `beat`; NaN if it lies in a hole between spans
        chosen = None
        for i, span in enumerate(spans):
            if beat < span[0][0]:
                # before this span: either before all data, or inside a hole
                if i == 0 and not self._starts_with_gap():
                    chosen = span
                break
            if beat <= span[-1][0]:
                chosen = span
                break
            if i == len(spans) - 1 and not self._ends_with_gap():
                chosen = span
        if chosen is None:
            return float("nan")
        pts = chosen
        if beat <= pts[0][0]:
            return pts[0][1]
        if beat >= pts[-1][0]:
            return pts[-1][1]
        lo, hi = 0, len(pts) - 1
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if pts[mid][0] <= beat:
                lo = mid
            else:
                hi = mid
        t0, v0 = pts[lo]
        t1, v1 = pts[hi]
        if t1 == t0:
            return v1
        f = (beat - t0) / (t1 - t0)
        return v0 + f * (v1 - v0)


@dataclass
class Note:
    start: float                     # beats
    dur: float                       # beats (already gate-scaled)
    pitch: int                       # MIDI note number
    velocity: int = 90
    stave: str = ""
    voice: Optional[str] = None      # named voice, if any
    detune: float = 0.0              # static semitone offset
    curves: dict[str, Curve] = field(default_factory=dict)
    channel: Optional[int] = None    # filled in by the MPE channel allocator
    id: int = 0

    @property
    def end(self) -> float:
        return self.start + self.dur


@dataclass
class ChordEvent:
    """Resolved harmony, for `explain`, the playground display, and targets."""

    start: float
    dur: float
    symbol: str                       # as written
    root_pc: int                      # 0..11
    quality: str                      # "min9", "maj7", "7alt", ...
    pitches: list[int] = field(default_factory=list)   # voiced, MIDI numbers
    pitch_classes: list[int] = field(default_factory=list)
    guide_tones: list[int] = field(default_factory=list)  # pitch classes
    stave: str = ""


@dataclass
class StaveIR:
    name: str
    notes: list[Note] = field(default_factory=list)
    chords: list[ChordEvent] = field(default_factory=list)
    channel_group: int = 1


@dataclass
class Score:
    tempo: float = 120.0
    meter: tuple[int, int] = (4, 4)
    ppq: int = 960
    key: tuple[int, str] = (0, "major")     # (tonic pitch class, mode name)
    bend_range: float = 48.0                # MPE member bend range, semitones
    grid_ms: float = 10.0
    seed: int = 0
    title: str = ""
    staves: list[StaveIR] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def notes(self) -> list[Note]:
        out: list[Note] = []
        for s in self.staves:
            out.extend(s.notes)
        out.sort(key=lambda n: (n.start, n.pitch))
        return out

    @property
    def duration_beats(self) -> float:
        return max((n.end for n in self.notes), default=0.0)

    def to_json(self) -> dict:
        """Schema consumed by the web playground (`web/`) and `filigree json`."""
        return {
            "tempo": self.tempo,
            "meter": list(self.meter),
            "key": {"tonic": self.key[0], "mode": self.key[1]},
            "ppq": self.ppq,
            "bendRange": self.bend_range,
            "title": self.title,
            "durationBeats": self.duration_beats,
            "warnings": list(self.warnings),
            "staves": [
                {
                    "name": s.name,
                    "chords": [
                        {
                            "start": c.start,
                            "dur": c.dur,
                            "symbol": c.symbol,
                            "rootPc": c.root_pc,
                            "quality": c.quality,
                            "pitches": c.pitches,
                            "guideTones": c.guide_tones,
                        }
                        for c in s.chords
                    ],
                    "notes": [
                        {
                            "id": n.id,
                            "start": n.start,
                            "dur": n.dur,
                            "pitch": n.pitch,
                            "velocity": n.velocity,
                            "voice": n.voice,
                            "detune": n.detune,
                            "channel": n.channel,
                            # NaN gaps become JSON null so the payload stays valid
                            # JSON and the playground can break the polyline.
                            "curves": {
                                lane: [
                                    [round(t, 5), None if (v != v or math.isinf(v))
                                     else round(v, 5)]
                                    for t, v in c.points
                                ]
                                for lane, c in n.curves.items()
                            },
                        }
                        for n in s.notes
                    ],
                }
                for s in self.staves
            ],
        }
