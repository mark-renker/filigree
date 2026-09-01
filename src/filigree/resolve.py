"""resolve.py — ``Document`` (ast_nodes) → ``Score`` (ir).

This is the integration piece: the only module that talks to *all* of
``theory``, ``voicing``, ``gesture`` and ``feel``.  It owns every decision that
needs both harmony and time:

1. directives                     → ``Score`` fields
2. bars/slots                     → absolute beats, per lane
3. ``harm`` lane                  → ``theory`` + ``voicing`` → ``ir.ChordEvent``
4. ``notes`` / ``voices`` lanes    → ``ir.Note`` (degrees, chord tones, anchors,
                                    absolutes, ties, retriggers, chords,
                                    alternations, probability, gate, accents)
5. curve lanes + attached gestures → ``ir.Curve`` per note, sampled on the score
                                    grid, with **no points where the gesture is
                                    NaN** (SPEC §7 "no data")
6. ``feel``                        → humanisation, then ids + sort

Design rulings implemented here (see ``NOTES_P7.md`` for the full list):

* Curve lanes DO emit an anchor/slot-count mismatch warning when the ratio is
  inexact (SPEC §12 amended); they are still resampled by
  design.  Only note-bearing lanes warn.
* "No data" reaches the renderer as a single ``NaN`` sentinel point at the start
  of every gap (leading, interior and trailing), which is what makes
  ``ir.Curve.value_at`` return ``NaN`` across the gap so ``mpe`` writes nothing
  there.  A curve with no finite sample at all is not attached at all.
* Sample interval is ``Score.grid_ms``; the pitch (``bend``) lane uses half of
  it.  Points are thinned with a linear-prediction deadband so curves stay
  compact.
"""

from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass, fields as dc_fields
from typing import Any, Callable, Optional

import numpy as np

from . import errors, feel as feel_mod, gesture as gest, ir, theory, voicing
from .ast_nodes import (
    Bar,
    ChordTok,
    Document,
    Lane,
    Num,
    PitchTok,
    Pos,
    Ref,
    Slot,
    Stave,
    Target,
)
from .ir import ChordEvent, Curve, Note, Score, StaveIR

__all__ = ["resolve", "CURVE_LANES", "is_curve_lane"]

# --------------------------------------------------------------------------- #
# lane taxonomy
# --------------------------------------------------------------------------- #

CURVE_LANES = ("bend", "press", "timbre", "amp", "pan")
_CC_RE = re.compile(r"^cc(\d{1,3})$")
_DEFAULT_VELOCITY = 90
_MIN_DUR = 1e-6
#: gestures are defined on the half-open window [0, 1); sampling exactly 1.0
#: falls outside every segment and would read as "no data" at the very last
#: point of a note.
_U_MAX = 1.0 - 1e-9
_EPS_BEAT = 1e-6


#: returned by ``_chord_from_tok`` in ``--lenient`` mode: "this bar failed to
#: parse; sustain whatever chord was in force" (SPEC §12 amended).
_SUSTAIN = object()


def is_curve_lane(name: str) -> bool:
    return name in CURVE_LANES or bool(_CC_RE.match(name or ""))


# thinning deadbands, in lane units (a linear-prediction tolerance).
_TOL_BEND = 0.01          # semitones — ~2 LSB at a 48 st member bend range
_TOL_UNIPOLAR = 0.008     # 0..1 — about one 7-bit MIDI step


_FEEL_KEY = {"timing": "timing_ms", "onset": "onset_ms",
             "release": "release_ms", "on": "on_beats"}
_FEEL_FIELDS = {f.name for f in dc_fields(feel_mod.FeelSpec)}
_VOICING_FIELDS = {f.name for f in dc_fields(voicing.VoicingSpec)}


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

def _num(value: Any, default: float = 0.0) -> float:
    if isinstance(value, Num):
        return float(value.value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _opt_str(options: dict, key: str) -> Optional[str]:
    v = options.get(key)
    if v is None:
        return None
    if isinstance(v, Num):
        return str(v.value)
    return str(v)


def _flatten(slots: list[Slot], t0: float, span: float, bar_index: int,
             out: list[tuple[float, float, Slot]]) -> None:
    """Expand one bar's slots into ``(start, end, leaf_slot)`` triples.

    ``group`` subdivides its span equally; ``alt`` picks the member for this
    bar repetition (SPEC §5 ``<a b c>``).  ``Slot.repeat`` is provenance only —
    the parser has already expanded ``x*3`` into sibling slots (NOTES_P1 §1.3).
    """
    n = len(slots)
    if n == 0:
        return
    w = span / n
    for i, s in enumerate(slots):
        _emit(s, t0 + i * w, t0 + (i + 1) * w, bar_index, out)


def _emit(s: Slot, a: float, b: float, bar_index: int,
          out: list[tuple[float, float, Slot]]) -> None:
    if s.kind == "group":
        if s.children:
            _flatten(s.children, a, b - a, bar_index, out)
        return
    if s.kind == "alt":
        if s.children:
            pick = s.children[bar_index % len(s.children)]
            _emit(pick, a, b, bar_index, out)
        return
    out.append((a, b, s))


def _thin(run: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Linear-prediction thinning: drop points a receiver can interpolate."""
    n = len(run)
    if n <= 2:
        return list(run)
    out = [run[0]]
    anchor = 0
    i = 1
    while i < n - 1:
        t1, v1 = run[i + 1]
        t0, v0 = run[anchor]
        span = t1 - t0
        ok = True
        if span <= 0:
            ok = False
        else:
            for k in range(anchor + 1, i + 1):
                tk, vk = run[k]
                pred = v0 + (v1 - v0) * (tk - t0) / span
                if abs(vk - pred) > tol:
                    ok = False
                    break
        if not ok:
            out.append(run[i])
            anchor = i
        i += 1
    out.append(run[-1])
    return out


def _scale_step(pitch: int, step: int, tonic_pc: int, mode: str) -> int:
    """Nearest scale pitch ``step`` scale degrees above/below ``pitch``."""
    pcs = {p % 12 for p in theory.scale_pitches(tonic_pc, mode)}
    direction = 1 if step >= 0 else -1
    remaining = abs(step) or 1
    p = pitch
    for _ in range(remaining):
        for d in range(1, 25):
            cand = p + direction * d
            if cand % 12 in pcs:
                p = cand
                break
        else:  # pragma: no cover - a scale always has members
            break
    return p


# --------------------------------------------------------------------------- #
# harmony segments
# --------------------------------------------------------------------------- #

@dataclass
class _HarmSeg:
    start: float
    end: float
    chord: Optional[theory.Chord]
    symbol: str
    pitches: list[int]


class _Resolver:
    """Resolves one document.  One instance per :func:`resolve` call."""

    def __init__(self, doc: Document, lenient: bool = False) -> None:
        self.doc = doc
        self.lenient = bool(lenient)
        d = doc.directives
        self.score = Score(
            tempo=float(d.get("tempo", 120.0)),
            meter=tuple(d.get("meter", (4, 4))),          # type: ignore[arg-type]
            ppq=int(d.get("ppq", 960)),
            key=tuple(d.get("key", (0, "major"))),        # type: ignore[arg-type]
            bend_range=float(d.get("bend_range", 48.0)),
            grid_ms=float(d.get("grid", 10.0)),
            seed=int(d.get("seed", 0)),
            title=str(d.get("title", "") or ""),
        )
        self.tonic, self.mode = self.score.key
        self.mode = theory.normalise_mode(self.mode)
        self.beats_per_bar = self.score.meter[0] * 4.0 / self.score.meter[1]
        self.warnings: list[str] = []
        self._seen_warnings: set[str] = set()
        self.env = gest.Env(doc.gestures)
        self.default_bend_lane_range = float(d.get("lane_range", 2.0))
        self.stave_end: dict[str, float] = {}
        self._note_gestures: dict[int, list[Any]] = {}

    # -- diagnostics --------------------------------------------------------
    def _harm_hard_error(self, exc: errors.HarmonyError,
                         tok: ChordTok) -> errors.HarmonyError:
        """Re-point a ``HarmonyError`` at the chord token's own source position."""
        pos = tok.pos or Pos()
        line = exc.line or pos.line
        col = exc.col or pos.col
        path = exc.path if exc.path not in ("", "<input>") else \
            (pos.file or self.doc.path)
        token = exc.token or (tok.roman or tok.absolute or "")
        return errors.HarmonyError(
            exc.message, line=line, col=col, token=token,
            suggestion=((exc.suggestion + "; ") if exc.suggestion else "")
            + "fix the chord symbol, or compile with --lenient to sustain the "
              "previous chord instead",
            path=path)

    def warn(self, msg: str, pos: Optional[Pos] = None, kind: str = "resolve") -> None:
        p = pos or Pos()
        # A `>` target is re-resolved for every note that shares the bar, so the
        # same diagnostic can be produced many times.  One copy is informative;
        # ten are noise.
        before = len(self.warnings)
        errors.warn(self.warnings, msg, p.line, p.col,
                    p.file or self.doc.path, kind)
        for w in self.warnings[before:]:
            if w in self._seen_warnings:
                self.warnings.pop()
            else:
                self._seen_warnings.add(w)

    # ================================================================== #
    # entry point
    # ================================================================== #
    def run(self) -> Score:
        # SPEC §12 (amended, round 3): a curve lane whose anchor count is not an
        # integer multiple or divisor of the bar's `notes` slot count IS a
        # warning — the lane is resampled and the warning names both counts.  The
        # round-2 ruling that curve lanes never warn is superseded: column
        # alignment is the language's core ergonomic claim, so an inexact
        # resampling must be visible.  Exact ratios stay silent.
        self.score.warnings.extend(self.doc.warnings)

        for st in self.doc.staves:
            offset = 0.0
            after = st.options.get("after")
            if after is not None:
                if after in self.stave_end:
                    offset = self.stave_end[after]
                else:
                    self.warn(f"stave {st.name!r} follows unknown stave "
                              f"{after!r}; starting at bar 1", st.pos)
            sir = self._stave(st, offset)
            self.score.staves.append(sir)
            end = max((n.end for n in sir.notes), default=offset)
            end = max(end, max((c.start + c.dur for c in sir.chords), default=offset))
            self.stave_end[st.name] = end

        # ids in a stable global order
        allnotes = [n for s in self.score.staves for n in s.notes]
        allnotes.sort(key=lambda n: (round(n.start, 6), n.stave, n.pitch,
                                     n.voice or ""))
        for i, n in enumerate(allnotes, start=1):
            n.id = i
        for s in self.score.staves:
            s.notes.sort(key=lambda n: (round(n.start, 6), n.pitch, n.voice or ""))
            s.chords.sort(key=lambda c: c.start)

        self.score.warnings.extend(self.warnings)
        return self.score

    # ================================================================== #
    # one stave
    # ================================================================== #
    def _stave(self, st: Stave, offset: float) -> StaveIR:
        lanes = self._effective_lanes(st)
        sir = StaveIR(name=st.name,
                      channel_group=int(st.options.get("channelgroup", 1) or 1))

        harm_lanes = [ln for ln in lanes if ln.name == "harm"]
        note_lanes = [ln for ln in lanes if ln.name == "notes"]
        voice_lanes = [ln for ln in lanes if ln.name == "voices"]
        curve_lanes = [ln for ln in lanes if is_curve_lane(ln.name)]

        nbars = max((len(ln.bars) for ln in lanes), default=0)
        bpb = self.beats_per_bar

        # ---- harmony -----------------------------------------------------
        spec = self._voicing_spec(st, harm_lanes)
        segs = self._harm_segments(harm_lanes, offset, bpb)
        self._voice_segments(segs, spec, None)

        # ---- notes -------------------------------------------------------
        streams = self._note_streams(note_lanes, voice_lanes, offset, bpb)
        raw: list[tuple[Note, float]] = []
        for vname, evs in streams.items():
            raw.extend(self._resolve_stream(st, vname, evs, segs))

        if not streams and segs:
            # a stave with harmony but no notes sounds the voiced chord
            for sg in segs:
                if sg.chord is None or not sg.pitches:
                    continue
                for p in sg.pitches:
                    raw.append((Note(start=sg.start, dur=sg.end - sg.start,
                                     pitch=int(p), velocity=_DEFAULT_VELOCITY,
                                     stave=st.name), 1.0))

        # ---- top: melody re-voicing (needs the melody, hence a 2nd pass) --
        if spec.top == "melody" and raw and segs:
            self._voice_segments(segs, spec, [n for n, _g in raw])

        # ---- gate --------------------------------------------------------
        notes: list[Note] = []
        for n, gate in raw:
            n.dur = max(n.dur * gate, _MIN_DUR)
            notes.append(n)

        # ---- feel --------------------------------------------------------
        fspec = self._feel_spec(st)
        if fspec is not None:
            feel_mod.apply_feel(notes, fspec, self.score.tempo, self.score.seed)

        # ---- chord events ------------------------------------------------
        for sg in segs:
            if sg.chord is None:
                continue
            c = sg.chord
            sir.chords.append(ChordEvent(
                start=sg.start, dur=sg.end - sg.start, symbol=sg.symbol,
                root_pc=c.root_pc, quality=c.quality, pitches=list(sg.pitches),
                pitch_classes=c.pitch_classes(), guide_tones=c.guide_tones(),
                stave=st.name))

        # ---- curves ------------------------------------------------------
        attached = self._stave_attached(st, note_lanes, voice_lanes)
        ordered = sorted(notes, key=lambda n: (round(n.start, 6), n.pitch))
        for i, n in enumerate(ordered):
            nxt = ordered[i + 1].pitch if i + 1 < len(ordered) else None
            self._note_curves(n, curve_lanes, attached, segs, offset, bpb, nxt)
            self._apply_amp_velocity(n)

        sir.notes = notes
        return sir

    # ------------------------------------------------------------------ #
    # lanes / parts
    # ------------------------------------------------------------------ #
    def _effective_lanes(self, st: Stave) -> list[Lane]:
        lanes: list[Lane] = [_copy_lane(ln) for ln in st.lanes]
        for stmt in st.statements:
            part = self.doc.parts.get(stmt.part)
            if part is None:
                self.warn(f"unknown part {stmt.part!r}", stmt.pos)
                continue
            plan = [_copy_lane(ln) for ln in part.lanes]
            for tf in stmt.transforms:
                plan = self._transform(plan, tf)
            for pln in plan:
                host = next((l for l in lanes if l.name == pln.name
                             and l.voice == pln.voice), None)
                if host is None:
                    lanes.append(pln)
                else:
                    host.bars.extend(pln.bars)
        return lanes

    def _transform(self, lanes: list[Lane], tf) -> list[Lane]:
        name = tf.name
        if name == "transpose":
            k = int(_num(tf.args[0], 0)) if tf.args else 0
            for ln in lanes:
                if ln.name in ("notes", "voices"):
                    for b in ln.bars:
                        _walk_notes(b.slots, lambda s: _transpose_slot(s, k))
            return lanes
        if name == "retro":
            for ln in lanes:
                ln.bars = [Bar(slots=list(reversed(b.slots)), pos=b.pos)
                           for b in reversed(ln.bars)]
            return lanes
        if name == "rot":
            k = int(_num(tf.args[0], 0)) if tf.args else 0
            for ln in lanes:
                for b in ln.bars:
                    if b.slots:
                        r = k % len(b.slots)
                        b.slots = b.slots[r:] + b.slots[:r]
            return lanes
        if name == "mask":
            pat = [c for c in str(tf.args[0] if tf.args else "").split()
                   if c] or ["1"]
            for ln in lanes:
                if ln.name not in ("notes", "voices"):
                    continue
                k = 0
                for b in ln.bars:
                    for i, s in enumerate(b.slots):
                        keep = pat[k % len(pat)] not in ("0", "false")
                        k += 1
                        if not keep and s.kind == "note":
                            b.slots[i] = Slot(kind="rest", pos=s.pos)
            return lanes
        self.warn(f"phrase transform {name!r} is not implemented yet; "
                  f"the part is played unchanged", getattr(tf, "pos", None))
        return lanes

    # ------------------------------------------------------------------ #
    # harmony
    # ------------------------------------------------------------------ #
    def _voicing_spec(self, st: Stave, harm_lanes: list[Lane]) -> voicing.VoicingSpec:
        name = None
        for ln in harm_lanes:
            name = _opt_str(ln.options, "voicing") or name
        name = name or st.options.get("voicing") or self.doc.directives.get("voicing")
        if not name:
            return voicing.VoicingSpec()
        vd = self.doc.voicings.get(str(name))
        if vd is None:
            self.warn(f"unknown voicing {name!r}; using the default", st.pos)
            return voicing.VoicingSpec()
        kwargs = {k: v for k, v in vd.fields.items() if k in _VOICING_FIELDS}
        try:
            return voicing.VoicingSpec(**kwargs).validate()
        except errors.HarmonyError as exc:
            self.warn(str(exc.message), vd.pos)
            return voicing.VoicingSpec()

    def _feel_spec(self, st: Stave):
        name = st.options.get("feel") or self.doc.directives.get("feel")
        if not name:
            return None
        fd = self.doc.feels.get(str(name))
        if fd is not None:
            kwargs = {}
            for k, v in fd.fields.items():
                key = _FEEL_KEY.get(k, k)
                if key in _FEEL_FIELDS:
                    kwargs[key] = v
            return feel_mod.FeelSpec(**kwargs)
        try:
            return feel_mod.preset(str(name))
        except KeyError:
            self.warn(f"unknown feel {name!r}; no humanisation applied", st.pos)
            return None

    def _chord_from_tok(self, tok: ChordTok) -> Optional[theory.Chord]:
        """Resolve one chord token.

        SPEC §12 (amended): an unknown or malformed chord symbol is a **hard
        error**, never a warning — a typo must not silently delete a bar of
        music.  ``resolve(doc, lenient=True)`` (what ``render --lenient`` will
        pass) downgrades it to a warning and sustains the previous chord, for
        live-coding sessions where stopping is worse than being wrong.

        ``warnings=``/``pos=`` are threaded into ``theory`` so soft diagnostics
        land in the score and every hard error carries real file:line:col plus a
        suggestion.
        """
        try:
            if tok.pitchset is not None:
                ch = theory.parse_pitchset(list(tok.pitchset),
                                           tok.pitchset_absolute)
            elif tok.roman:
                ch = theory.parse_roman(tok.roman, self.tonic, self.mode,
                                        warnings=self.warnings, pos=tok.pos)
            elif tok.absolute:
                ch = theory.parse_absolute(tok.absolute,
                                           warnings=self.warnings,
                                           pos=tok.pos)
            else:
                return None
        except errors.HarmonyError as exc:
            if not self.lenient:
                raise self._harm_hard_error(exc, tok) from None
            self.warn(f"{exc.message}"
                      + (f" ({exc.suggestion})" if exc.suggestion else "")
                      + "; --lenient: sustaining the previous chord",
                      tok.pos, kind="harmony")
            return _SUSTAIN
        if tok.bass:
            pc = None
            if re.fullmatch(r"[A-G](#|b)?", tok.bass):
                pc = theory.NOTE_NAMES.get(tok.bass[0])
                if pc is not None:
                    pc = (pc + tok.bass.count("#") - tok.bass.count("b")) % 12
            elif tok.bass.isdigit():
                pc = ch.degree_pc(int(tok.bass))
                if pc is None:
                    self.warn(f"chord {ch.symbol!r} has no {tok.bass} to put in "
                              f"the bass", tok.pos, kind="harmony")
            if pc is not None:
                ch = ch.with_bass(pc)
        return ch

    def _harm_segments(self, harm_lanes: list[Lane], offset: float,
                       bpb: float) -> list[_HarmSeg]:
        leaves: list[tuple[float, float, Slot]] = []
        for ln in harm_lanes:
            for b, bar in enumerate(ln.bars):
                if not bar.slots:
                    continue
                _flatten(bar.slots, offset + b * bpb, bpb, b, leaves)
        leaves.sort(key=lambda x: x[0])

        segs: list[_HarmSeg] = []
        for a, z, slot in leaves:
            tok = slot.chord
            if tok is None:
                continue
            if tok.sustain:
                if segs:
                    segs[-1].end = z
                continue
            if tok.silent:
                segs.append(_HarmSeg(a, z, None, ".", []))
                continue
            ch = self._chord_from_tok(tok)
            if ch is _SUSTAIN:
                # lenient recovery: the typo'd bar keeps sounding the previous
                # chord rather than falling silent.
                if segs:
                    segs[-1].end = z
                else:
                    segs.append(_HarmSeg(a, z, None, "?", []))
                continue
            if ch is None:
                segs.append(_HarmSeg(a, z, None, "?", []))
                continue
            segs.append(_HarmSeg(a, z, ch, ch.symbol, []))
        return segs

    def _voice_segments(self, segs: list[_HarmSeg], spec: voicing.VoicingSpec,
                        melody: Optional[list[Note]]) -> None:
        previous: Optional[list[int]] = None
        for sg in segs:
            if sg.chord is None:
                continue
            mpc = None
            if melody is not None:
                cands = [n for n in melody
                         if sg.start - 1e-9 <= n.start < sg.end - 1e-9]
                if cands:
                    mpc = min(cands, key=lambda n: n.start).pitch % 12
            try:
                sg.pitches = voicing.voice_chord(sg.chord, spec, previous, mpc)
            except errors.HarmonyError as exc:
                self.warn(str(exc.message))
                sg.pitches = []
            if sg.pitches:
                previous = list(sg.pitches)

    @staticmethod
    def _seg_index(segs: list[_HarmSeg], beat: float) -> int:
        idx = -1
        for i, sg in enumerate(segs):
            if sg.start <= beat + 1e-9:
                idx = i
            else:
                break
        return idx

    def _chord_at(self, segs: list[_HarmSeg], beat: float) -> Optional[_HarmSeg]:
        """Sounding-or-remembered chord at ``beat`` (SPEC §4: `.` keeps context)."""
        i = self._seg_index(segs, beat)
        while i >= 0:
            if segs[i].chord is not None:
                return segs[i]
            i -= 1
        return None

    def _chord_rel(self, segs: list[_HarmSeg], beat: float,
                   which: str) -> Optional[_HarmSeg]:
        i = self._seg_index(segs, beat)
        if which == "current":
            return self._chord_at(segs, beat)
        if which == "next":
            j = i + 1
            while j < len(segs):
                if segs[j].chord is not None:
                    return segs[j]
                j += 1
            return self._chord_at(segs, beat)
        j = i - 1
        while j >= 0:
            if segs[j].chord is not None:
                return segs[j]
            j -= 1
        return None

    # ------------------------------------------------------------------ #
    # notes
    # ------------------------------------------------------------------ #
    def _note_streams(self, note_lanes: list[Lane], voice_lanes: list[Lane],
                      offset: float, bpb: float
                      ) -> dict[Optional[str], list[tuple[float, float, Slot]]]:
        streams: dict[Optional[str], list[tuple[float, float, Slot]]] = {}
        for ln in note_lanes:
            key = ln.voice
            out = streams.setdefault(key, [])
            for b, bar in enumerate(ln.bars):
                if bar.slots:
                    _flatten(bar.slots, offset + b * bpb, bpb, b, out)
        for ln in voice_lanes:
            for b, bar in enumerate(ln.bars):
                if not bar.slots:
                    continue
                blocks: list[tuple[float, float, Slot]] = []
                _flatten(bar.slots, offset + b * bpb, bpb, b, blocks)
                for a, z, slot in blocks:
                    if slot.kind != "voices":
                        continue
                    for vname, sub in slot.voices.items():
                        out = streams.setdefault(vname, [])
                        _emit(sub, a, z, b, out)
        for k in streams:
            streams[k].sort(key=lambda x: x[0])
        return streams

    def _resolve_stream(self, st: Stave, vname: Optional[str],
                        evs: list[tuple[float, float, Slot]],
                        segs: list[_HarmSeg]) -> list[tuple[Note, float]]:
        out: list[tuple[Note, float]] = []
        live: list[Note] = []           # notes a `-` would extend
        last_pitches: list[int] = []    # what `=` retriggers
        ref = theory.degree_to_pitch(0, self.tonic, self.mode, 4)

        for a, z, slot in evs:
            kind = slot.kind
            if kind == "rest":
                live = []
                continue
            if kind == "tie":
                for n in live:
                    n.dur = z - n.start
                continue
            if kind in ("glyph", "chord", "voices", "empty", "gesture"):
                continue
            if kind == "retrig":
                pitches = list(last_pitches)
                if not pitches:
                    self.warn("'=' retrigger with no previous note; ignored",
                              slot.pos)
                    continue
            else:  # "note"
                pitches = []
                for pt in slot.pitches:
                    p = self._pitch(pt, segs, a, ref)
                    if p is not None:
                        pitches.append(p)
                if not pitches:
                    live = []
                    continue
            last_pitches = list(pitches)
            ref = pitches[-1]

            if slot.probability < 1.0:
                roll = feel_mod.hash01(self.score.seed, st.name, vname or "",
                                       round(a, 4), pitches[0], "probability")
                if roll >= slot.probability:
                    live = []
                    continue

            vel = _DEFAULT_VELOCITY if slot.velocity is None else int(slot.velocity)
            vel = int(round(vel * (1.0 + slot.accent)))
            vel = max(1, min(127, vel))
            gate = 1.0 if slot.gate is None else float(slot.gate)

            group: list[Note] = []
            for p in pitches:
                n = Note(start=a, dur=max(z - a, _MIN_DUR), pitch=int(p),
                         velocity=vel, stave=st.name, voice=vname)
                n.curves = {}
                out.append((n, gate))
                group.append(n)
                self._note_gestures[id(n)] = list(slot.gestures)
            live = group
        return out

    def _pitch(self, pt: PitchTok, segs: list[_HarmSeg], beat: float,
               ref: int) -> Optional[int]:
        if pt.kind == "absolute":
            return int(pt.midi if pt.midi is not None else 60)
        if pt.kind == "degree":
            return theory.degree_to_pitch(pt.value, self.tonic, self.mode,
                                          4 + pt.octave, pt.accidental)
        sg = self._chord_at(segs, beat)
        if sg is None or sg.chord is None:
            self.warn(f"{_pitch_label(pt)} needs a chord but this stave has no "
                      f"'harm' lane here; using the tonic", pt.pos)
            return theory.degree_to_pitch(0, self.tonic, self.mode,
                                          4 + pt.octave, pt.accidental)
        chord = sg.chord
        if pt.kind == "chordtone":
            pc = chord.degree_pc(pt.value)
            if pc is None:
                self.warn(f"chord {chord.symbol!r} has no {pt.value}; "
                          f"using its root", pt.pos, kind="harmony")
                pc = chord.root_pc
            return theory.nearest_pc(pc, ref) + 12 * pt.octave + pt.accidental
        # anchors
        anchor = (pt.anchor or "").lstrip("@")
        pitches = sg.pitches
        if anchor == "low":
            p = min(pitches) if pitches else theory.nearest_pc(chord.root_pc, ref)
        elif anchor == "high":
            p = max(pitches) if pitches else theory.nearest_pc(chord.root_pc, ref)
        elif anchor == "root":
            root = [q for q in pitches if q % 12 == chord.root_pc % 12]
            p = min(root) if root else theory.nearest_pc(chord.root_pc, ref)
        else:  # guide
            cands = [theory.nearest_pc(pc, ref) for pc in chord.guide_tones()]
            p = min(cands, key=lambda q: (abs(q - ref), q))
        return int(p) + 12 * pt.octave + pt.accidental

    # ------------------------------------------------------------------ #
    # curves
    # ------------------------------------------------------------------ #
    def _stave_attached(self, st: Stave, note_lanes: list[Lane],
                        voice_lanes: list[Lane]) -> dict[Optional[str], list[Any]]:
        """Attached gestures by voice scope, lowest priority last."""
        out: dict[Optional[str], list[Any]] = {}
        for ln in note_lanes + voice_lanes:
            for key, val in ln.options.items():
                if not key.startswith("gesture"):
                    continue
                voice = key.split("@", 1)[1] if "@" in key else ln.voice
                out.setdefault(voice, []).append(Ref(name=str(val), pos=ln.pos))
        gname = st.options.get("gesture")
        if gname:
            out.setdefault(None, []).append(Ref(name=str(gname), pos=st.pos))
        return out

    def _lane_range(self, ln: Lane) -> tuple[float, float]:
        base = ir.LANE_RANGES.get(ln.name, (0.0, 1.0))
        if ln.name == "bend":
            base = (-self.default_bend_lane_range, self.default_bend_lane_range)
        r = ln.options.get("range")
        if r is not None:
            v = abs(_num(r, base[1]))
            return (-v, v) if base[0] < 0 else (0.0, v)
        return base

    def _ctx(self, lane: str, lane_range: tuple[float, float], span: float,
             note: Note, rt: Callable) -> gest.GestureCtx:
        return gest.GestureCtx(
            lane_default=lane, lane_range=lane_range, tempo=self.score.tempo,
            note_dur_beats=max(span, _MIN_DUR),
            seed_key=(self.score.seed, note.stave, note.voice or "",
                      round(note.start, 4), note.pitch, lane),
            resolve_target=rt)

    def _target_resolver(self, note: Note, segs: list[_HarmSeg],
                         lane_range: tuple[float, float],
                         next_pitch: Optional[int]) -> Callable[[Target], float]:
        def rt(tgt: Target) -> float:
            pitch = note.pitch
            dest: Optional[int] = None
            if tgt.kind == "next":
                dest = next_pitch if next_pitch is not None else pitch
            elif tgt.kind == "step":
                dest = _scale_step(pitch, tgt.degree or 1, self.tonic, self.mode)
            else:
                sg = self._chord_rel(segs, note.start, tgt.chord)
                if sg is None or sg.chord is None:
                    self.warn("harmonic target has no chord to aim at; "
                              "no bend written", tgt.pos, kind="harmony")
                    return 0.0
                chord = sg.chord
                if tgt.kind == "guide":
                    cands = [theory.nearest_pc(pc, pitch)
                             for pc in chord.guide_tones()]
                    dest = min(cands, key=lambda q: (abs(q - pitch), q))
                else:
                    pc = chord.degree_pc(tgt.degree or 3)
                    if pc is None:
                        self.warn(f"chord {chord.symbol!r} has no "
                                  f"{tgt.degree}; target ignored", tgt.pos,
                                  kind="harmony")
                        return 0.0
                    dest = theory.nearest_pc(pc, pitch)
            val = float(dest - pitch)
            lo, hi = lane_range
            if val < lo - 1e-9 or val > hi + 1e-9:
                self.warn(
                    f"bend target needs {val:+.2f}st but the lane range is "
                    f"{lo:+g}..{hi:+g}st, so the note cannot reach it; clamped "
                    f"(widen it with '!range={max(abs(lo), abs(hi), abs(val)):.0f}st')",
                    tgt.pos, kind="target-range")
                val = min(max(val, lo), hi)
            return val
        return rt

    def _note_curves(self, note: Note, curve_lanes: list[Lane],
                     attached: dict[Optional[str], list[Any]],
                     segs: list[_HarmSeg], offset: float, bpb: float,
                     next_pitch: Optional[int]) -> None:
        applicable = [ln for ln in curve_lanes
                      if ln.voice is None or ln.voice == note.voice]
        gest_exprs = list(self._note_gestures.get(id(note), []))
        for scope in (note.voice, None):
            if scope in attached:
                gest_exprs.extend(attached[scope])
        if not applicable and not gest_exprs:
            return

        # lane -> ordered list of samplers (highest priority first)
        sources: dict[str, list[Callable[[np.ndarray], np.ndarray]]] = {}
        ranges: dict[str, tuple[float, float]] = {}

        # 1. explicit lane glyphs (voice-specific lanes win over generic ones)
        for ln in sorted(applicable, key=lambda l: (l.voice is None,)):
            lr = self._lane_range(ln)
            ranges.setdefault(ln.name, lr)
            rt = self._target_resolver(note, segs, lr, next_pitch)
            for s in self._lane_samplers(ln, note, offset, bpb, lr, rt):
                sources.setdefault(ln.name, []).append(s)

        # 2. attached gestures, note-level first
        for expr in gest_exprs:
            g = self._eval_attached(expr, note, segs, next_pitch)
            if g is None:
                continue
            for lane in sorted(g.lanes()):
                ranges.setdefault(lane, gest.lane_range_for(lane))
                sources.setdefault(lane, []).append(
                    _gesture_sampler(g, lane, note.start, note.dur))

        for lane, srcs in sources.items():
            pts = self._sample_lane(lane, srcs, note, ranges.get(lane))
            if pts:
                note.curves[lane] = Curve(lane=lane, points=pts)

    def _eval_attached(self, expr: Any, note: Note, segs: list[_HarmSeg],
                       next_pitch: Optional[int]):
        lr = (-self.default_bend_lane_range, self.default_bend_lane_range)
        rt = self._target_resolver(note, segs, lr, next_pitch)
        ctx = gest.GestureCtx(
            lane_default=None, lane_range=lr, tempo=self.score.tempo,
            note_dur_beats=max(note.dur, _MIN_DUR),
            seed_key=(self.score.seed, note.stave, note.voice or "",
                      round(note.start, 4), note.pitch),
            resolve_target=rt)
        try:
            return gest.eval_gesture(expr, self.env, ctx)
        except errors.FiligreeError as exc:
            self.warn(str(exc.message)
                      + (f" ({exc.suggestion})" if exc.suggestion else ""),
                      getattr(expr, "pos", None), kind="gesture")
            return None

    def _lane_samplers(self, ln: Lane, note: Note, offset: float, bpb: float,
                       lr: tuple[float, float], rt: Callable
                       ) -> list[Callable[[np.ndarray], np.ndarray]]:
        shape = _opt_str(ln.options, "shape") or "ease"
        mode = _opt_str(ln.options, "time") or "bar"
        cache: dict[int, tuple[Any, list[Any]]] = {}

        def build(bar_idx: int, span: float):
            if bar_idx in cache:
                return cache[bar_idx]
            if bar_idx < 0 or bar_idx >= len(ln.bars):
                cache[bar_idx] = (None, [])
                return cache[bar_idx]
            bar = ln.bars[bar_idx]
            leaves: list[tuple[float, float, Slot]] = []
            _flatten(bar.slots, 0.0, 1.0, bar_idx, leaves)
            ctx = self._ctx(ln.name, lr, span, note, rt)
            glyph_g = None
            inline: list[Any] = []
            if leaves:
                try:
                    glyph_g = gest.glyphs_to_gesture(leaves, ln.name, ctx,
                                                     shape=shape)
                except errors.FiligreeError as exc:
                    self.warn(str(exc.message), bar.pos, kind="gesture")
                for a, z, s in leaves:
                    if s.kind == "gesture" and s.expr is not None:
                        try:
                            gg = gest.eval_gesture(s.expr, self.env, ctx)
                        except errors.FiligreeError as exc:
                            self.warn(str(exc.message), s.pos, kind="gesture")
                            continue
                        inline.append(gg.windowed(a, z))
            cache[bar_idx] = (glyph_g, inline)
            return cache[bar_idx]

        def sample(which: int):
            def fn(beats: np.ndarray) -> np.ndarray:
                out = np.full(beats.shape, np.nan)
                if mode == "note":
                    bar_idx = int(math.floor((note.start - offset) / bpb + 1e-9))
                    g, inline = build(bar_idx, note.dur)
                    src = g if which < 0 else (inline[which]
                                               if which < len(inline) else None)
                    if src is None:
                        return out
                    u = np.clip((beats - note.start) / max(note.dur, _MIN_DUR),
                                0.0, _U_MAX)
                    v = src.sample(ln.name, u)
                    if v is not None:
                        out = np.asarray(v, dtype=float)
                    return out
                bars = np.floor((beats - offset) / bpb + 1e-9).astype(int)
                for bi in sorted(set(int(b) for b in bars)):
                    m = bars == bi
                    g, inline = build(bi, bpb)
                    src = g if which < 0 else (inline[which]
                                               if which < len(inline) else None)
                    if src is None:
                        continue
                    u = (beats[m] - offset - bi * bpb) / bpb
                    v = src.sample(ln.name, np.clip(u, 0.0, _U_MAX))
                    if v is not None:
                        out[m] = np.asarray(v, dtype=float)
                return out
            return fn

        # How many inline `name(args)` gesture slots might we need to read?
        # Counted structurally, *without* building any gesture: building one
        # resolves `>` targets, and doing that for a bar the note does not touch
        # would emit bogus range warnings.
        n_inline = 0
        for bi in range(len(ln.bars)):
            leaves: list[tuple[float, float, Slot]] = []
            _flatten(ln.bars[bi].slots, 0.0, 1.0, bi, leaves)
            n_inline = max(n_inline, sum(1 for _a, _z, s in leaves
                                         if s.kind == "gesture" and s.expr))
        return [sample(-1)] + [sample(i) for i in range(n_inline)]

    def _sample_lane(self, lane: str,
                     srcs: list[Callable[[np.ndarray], np.ndarray]],
                     note: Note, lr: Optional[tuple[float, float]]
                     ) -> list[tuple[float, float]]:
        dt = self.score.grid_ms / 1000.0 * self.score.tempo / 60.0
        if lane == "bend":
            dt *= 0.5
        dt = max(dt, 1e-4)
        # Sample the half-open lifetime [start, start+dur): a sample sitting
        # exactly on start+dur belongs to the *next* bar (or is past the end of
        # a !time=note window) and would read as "no data".
        end = note.start + max(note.dur - _EPS_BEAT, 0.0)
        steps = max(2, int(math.floor((end - note.start) / dt)) + 1)
        beats = note.start + dt * np.arange(steps, dtype=float)
        beats = beats[beats <= end]
        if beats.size == 0:
            beats = np.array([note.start])
        if beats[-1] < end - 1e-9:
            beats = np.append(beats, end)

        values = np.full(beats.shape, np.nan)
        for src in srcs:
            try:
                v = np.asarray(src(beats), dtype=float)
            except errors.FiligreeError as exc:
                self.warn(str(exc.message), kind="gesture")
                continue
            if v.shape != values.shape:
                continue
            fill = np.isnan(values) & ~np.isnan(v)
            values[fill] = v[fill]
            if not np.any(np.isnan(values)):
                break
        if not np.any(~np.isnan(values)):
            return []
        if lr is not None:
            lo, hi = lr
            finite = ~np.isnan(values)
            values[finite] = np.clip(values[finite], lo, hi)

        tol = _TOL_BEND if lane == "bend" else _TOL_UNIPOLAR
        pts: list[tuple[float, float]] = []
        i = 0
        n = values.size
        while i < n:
            if math.isnan(values[i]):
                start = i
                while i < n and math.isnan(values[i]):
                    i += 1
                pts.append((float(beats[start]), float("nan")))
            else:
                start = i
                while i < n and not math.isnan(values[i]):
                    i += 1
                run = [(float(beats[k]), float(values[k]))
                       for k in range(start, i)]
                pts.extend(_thin(run, tol))
        return pts

    def _apply_amp_velocity(self, note: Note) -> None:
        """SPEC §3.2: the ``amp`` lane sets velocity at note-on (and CC11 after)."""
        c = note.curves.get("amp")
        if c is None or not c.points:
            return
        v = c.value_at(note.start)
        if v is None or math.isnan(v):
            return
        note.velocity = max(1, min(127, int(round(float(v) * 127.0))))


# --------------------------------------------------------------------------- #
# helpers that need no resolver state
# --------------------------------------------------------------------------- #

def _gesture_sampler(g, lane: str, start: float, dur: float):
    def fn(beats: np.ndarray) -> np.ndarray:
        u = (beats - start) / max(dur, _MIN_DUR)
        v = g.sample(lane, np.clip(u, 0.0, _U_MAX))
        if v is None:
            return np.full(beats.shape, np.nan)
        return np.asarray(v, dtype=float)
    return fn


def _pitch_label(pt: PitchTok) -> str:
    if pt.kind == "chordtone":
        return f"chord tone '~{pt.value}'"
    return f"anchor '{pt.anchor}'"


def _copy_lane(ln: Lane) -> Lane:
    """Deep copy: phrase transforms rewrite pitch tokens in place, and a part
    may be `play`ed more than once with different transforms."""
    return Lane(name=ln.name,
                bars=[Bar(slots=copy.deepcopy(b.slots), pos=b.pos)
                      for b in ln.bars],
                voice=ln.voice, options=dict(ln.options), pos=ln.pos)


def _walk_notes(slots: list[Slot], fn) -> None:
    for s in slots:
        if s.children:
            _walk_notes(s.children, fn)
        if s.voices:
            _walk_notes(list(s.voices.values()), fn)
        if s.kind == "note":
            fn(s)


def _transpose_slot(s: Slot, k: int) -> None:
    for pt in s.pitches:
        if pt.kind == "degree":
            pt.value += k
        elif pt.kind == "absolute" and pt.midi is not None:
            pt.midi = max(0, min(127, pt.midi + k))


# --------------------------------------------------------------------------- #
# public entry point
# --------------------------------------------------------------------------- #

def resolve(doc: Document, lenient: bool = False) -> Score:
    """Resolve a parsed :class:`Document` into a performance :class:`Score`.

    ``lenient=False`` (the default, SPEC §12 amended): an unknown or malformed
    chord symbol raises :class:`errors.HarmonyError`.  ``lenient=True`` (what
    ``filigree render --lenient`` passes) downgrades it to a warning and
    sustains the previous chord, so a live-coding session never stops.
    """
    return _Resolver(doc, lenient=lenient).run()
