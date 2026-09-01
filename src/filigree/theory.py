"""Filigree harmony engine — scales, roman numerals, absolute chord symbols.

Piece P2.  Owned by the harmony builder.  Imports the frozen contracts
``ast_nodes`` / ``errors``; never edits them.

Everything in here is derived from music theory first principles.  The
ground-truth table the tests assert against lives in
``refs/specs/harmony_truth.md`` (with source URLs).

Conventions resolved here (see ``NOTES_P2.md`` for the full rationale):

* **Pitch class** is always ``0..11`` with ``C == 0``.
* **MIDI octave** numbering is scientific with ``C4 == 60``, i.e.
  ``midi = 12 * (octave + 1) + pc``.
* ``degree_to_pitch`` uses **0-based** scale degrees (``0`` == tonic) because
  that is what the ``notes`` lane writes (SPEC §5).  Roman numerals and
  ``Chord.degree_pc`` use **1-based** chord/scale degrees (``1`` == root).
* A bare ``7`` in any symbol means a **minor** seventh (10 semitones, the
  lead-sheet "dominant 7th" reading).  A major seventh must be spelled
  ``^7`` / ``maj7``.  This is why the language has a ``^`` marker at all.
* ``x`` forces a dominant-7th colour (major 3rd + minor 7th) regardless of
  the numeral's case, so ``IIx`` in C is D F# A C.
* ``alt`` expands to the full altered dominant ``1 b9 #9 3 #11 b13 b7``.

 Round-2 rulings (see ``refs/specs/harmony_truth.md`` and ``NOTES_P2.md``)
-------------------------------------------------------------------------

* **Modal interchange.**  A trailing mode letter selects a *scale*; the chord
  is then the **diatonic** chord of that scale on that degree.  The written
  case is *validated*, not authoritative: when the borrowed scale disagrees
  with the case a warning is appended to the caller's ``warnings`` list and the
  scale wins.  So ``iiid`` in C minor is Eb G Bb ``[3, 7, 10]`` (dorian's III),
  not Eb Gb Bb.
* **Accidentals are chromatic, i.e. measured from the major scale.**  ``bVI``
  is Ab in C major *and* in C minor; an unaccented numeral takes the key's own
  mode (``VI`` in C minor is Ab as well).  This is the standard chromatic
  roman-numeral convention and removes the double-flat trap.
* **Diagnostics** carry a real ``line``/``col``.  Callers may pass
  ``pos=ast_nodes.Pos(...)``; without one the symbol is treated as its own
  one-line source and the column points at the offending character (1-based),
  so a diagnostic is never ``0:0``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import errors

#: hard cap on a chord symbol, in characters.  The longest legal symbol in
#: SPEC §4 is ``V7#9#11b13/Bb`` (13); anything past this is a typo or an
#: attempt to blow up the parser.
MAX_SYMBOL_LEN = 24

__all__ = [
    "MAX_SYMBOL_LEN",
    "parse_chord",
    "HarmonyWarning",
    "MODES",
    "MODE_ALIASES",
    "MODAL_INTERCHANGE_LETTERS",
    "NOTE_NAMES",
    "PC_NAMES",
    "Chord",
    "parse_roman",
    "parse_absolute",
    "parse_pitchset",
    "scale_pitches",
    "degree_to_pitch",
    "nearest_pc",
    "degree_pc_of_scale",
]

# ---------------------------------------------------------------------------
# scales
# ---------------------------------------------------------------------------

#: mode name -> semitone offsets from the tonic.  Covers every mode named in
#: SPEC §2 plus the aliases the parser may hand us.
MODES: dict[str, tuple[int, ...]] = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "ionian": (0, 2, 4, 5, 7, 9, 11),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "aeolian": (0, 2, 3, 5, 7, 8, 10),
    "locrian": (0, 1, 3, 5, 6, 8, 10),
    "harmonic-minor": (0, 2, 3, 5, 7, 8, 11),
    "melodic-minor": (0, 2, 3, 5, 7, 9, 11),
    "whole-tone": (0, 2, 4, 6, 8, 10),
    "chromatic": tuple(range(12)),
    "blues": (0, 3, 5, 6, 7, 10),
}

#: tolerated spellings for mode names.
MODE_ALIASES: dict[str, str] = {
    "maj": "major",
    "min": "minor",
    "harmonic_minor": "harmonic-minor",
    "harmonicminor": "harmonic-minor",
    "melodic_minor": "melodic-minor",
    "melodicminor": "melodic-minor",
    "whole_tone": "whole-tone",
    "wholetone": "whole-tone",
    "natural-minor": "minor",
}

#: SPEC §4 modal-interchange suffix letters.
MODAL_INTERCHANGE_LETTERS: dict[str, str] = {
    "n": "ionian",
    "d": "dorian",
    "f": "phrygian",
    "y": "lydian",
    "m": "mixolydian",
    "a": "aeolian",
    "l": "locrian",
    "h": "harmonic-minor",
    "e": "melodic-minor",
}

NOTE_NAMES: dict[str, int] = {
    "C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11,
}

#: canonical (flat-preferring) names for pitch classes, used in messages.
PC_NAMES: tuple[str, ...] = (
    "C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B",
)

_ROMAN_VALUES = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7,
}
_ROMAN_ORDER = ("iii", "vii", "ii", "iv", "vi", "i", "v")


#: alias kept for callers who want to type-annotate a warning collector.
HarmonyWarning = str


def _harm_error(message: str, *, symbol: str = "", token: str = "",
                suggestion: str = "", pos=None) -> errors.HarmonyError:
    """Build a ``HarmonyError`` that always carries a position and a hint.

    ``pos`` is an ``ast_nodes.Pos`` (duck-typed: ``.line``/``.col``/``.file``).
    When the caller supplies one, the error points at the symbol's own source
    location, offset by where inside the symbol the offending token starts.
    When it does not, the symbol is treated as a one-line source of its own, so
    the diagnostic is ``<input>:1:<col>`` — never ``0:0``.
    """
    line, col, path = 1, 1, "<input>"
    if pos is not None:
        line = int(getattr(pos, "line", 0) or 1)
        col = int(getattr(pos, "col", 0) or 1)
        path = str(getattr(pos, "file", "<input>") or "<input>")
    if token and symbol:
        off = symbol.find(token)
        if off > 0:
            col += off
    return errors.HarmonyError(
        message, line=line, col=col, token=token or symbol,
        suggestion=suggestion or _suggest(symbol), path=path)


def normalise_mode(mode: str, *, pos=None) -> str:
    """Canonicalise a mode name.  Raises ``HarmonyError`` on nonsense."""
    key = (mode or "major").strip().lower().replace(" ", "-")
    key = MODE_ALIASES.get(key, key)
    key = MODE_ALIASES.get(key.replace("-", "_"), key)
    if key not in MODES:
        raise _harm_error(
            f"unknown mode {mode!r}",
            symbol=str(mode), token=str(mode),
            suggestion="one of: " + ", ".join(sorted(MODES)),
            pos=pos,
        )
    return key


def scale_pitches(tonic_pc: int, mode: str) -> list[int]:
    """Pitch classes of the scale, starting on the tonic."""
    offs = MODES[normalise_mode(mode)]
    return [(tonic_pc + o) % 12 for o in offs]


def _scale_offset(degree0: int, mode: str) -> int:
    """Semitone offset (may exceed an octave / go negative) of a 0-based degree."""
    offs = MODES[normalise_mode(mode)]
    n = len(offs)
    octave, idx = divmod(degree0, n)
    return offs[idx] + 12 * octave


def degree_pc_of_scale(degree: int, tonic_pc: int, mode: str) -> int:
    """Pitch class of a **1-based** scale degree (1 == tonic)."""
    return (tonic_pc + _scale_offset(degree - 1, mode)) % 12


def degree_to_pitch(degree: int, tonic_pc: int, mode: str, octave: int = 4,
                    accidental: int = 0) -> int:
    """MIDI pitch of a **0-based** scale degree (``0`` == tonic).

    ``octave`` is scientific (``C4 == 60``).  Degrees may be negative or
    larger than the scale, wrapping through octaves.
    """
    base = 12 * (octave + 1) + tonic_pc
    return base + _scale_offset(degree, mode) + accidental


def nearest_pc(target_pc: int, from_pitch: int) -> int:
    """The MIDI pitch with pitch class ``target_pc`` nearest ``from_pitch``.

    Ties (a tritone away) resolve **upward**, deterministically.
    """
    target_pc %= 12
    base = from_pitch - (from_pitch % 12) + target_pc
    best = None
    for cand in (base - 12, base, base + 12):
        d = abs(cand - from_pitch)
        if best is None or d < best[0] or (d == best[0] and cand > best[1]):
            best = (d, cand)
    assert best is not None
    return best[1]


# ---------------------------------------------------------------------------
# Chord
# ---------------------------------------------------------------------------


@dataclass
class Chord:
    """A resolved harmonic object.

    ``intervals`` are semitones above ``root_pc`` with the root included as
    ``0``; they are sorted ascending and may exceed an octave (a 13th is 21).
    ``degrees`` maps the analytic chord degree (1,3,5,7,9,11,13 — plus 2/4 for
    sus chords and 6 for sixth chords) onto the interval that realises it; it
    is filled in by the parsers and is what ``degree_pc`` consults first.
    """

    root_pc: int
    quality: str
    intervals: tuple[int, ...]
    bass_pc: int | None = None
    symbol: str = ""
    degrees: tuple[tuple[int, int], ...] = field(default_factory=tuple)

    # -- basics -------------------------------------------------------------
    def pitch_classes(self) -> list[int]:
        """Pitch classes in ascending interval order, de-duplicated."""
        out: list[int] = []
        for iv in self.intervals:
            pc = (self.root_pc + iv) % 12
            if pc not in out:
                out.append(pc)
        return out

    def guide_tones(self) -> list[int]:
        """The chord's guide tones as pitch classes.

        Guide tones are the 3rd and the 7th — the pair that carries the
        chord-quality information (Nettles via Smither, *Guide-Tone Space*,
        MTO 25.2).  Fallbacks, in order, when one is missing:
        3rd → 4th/sus tone → root; 7th → 6th → 5th → root.
        """
        third = self.degree_pc(3)
        if third is None:
            third = self.degree_pc(4)
        if third is None:
            third = self.degree_pc(2)
        seventh = self.degree_pc(7)
        if seventh is None:
            seventh = self.degree_pc(6)
        if seventh is None:
            seventh = self.degree_pc(5)
        out: list[int] = []
        for pc in (third, seventh):
            if pc is not None and pc not in out:
                out.append(pc)
        if not out:
            out = [self.root_pc]
        return out

    # -- degree lookup ------------------------------------------------------
    def degree_pc(self, degree: int) -> int | None:
        """Pitch class of a chord degree, or ``None`` if the chord lacks it.

        ``degree`` in ``{1,2,3,4,5,6,7,9,11,13}``.  Compound degrees fold onto
        their simple partners (9↔2, 11↔4, 13↔6) so ``degree_pc(13)`` finds the
        6th of a plain sixth chord.
        """
        iv = self.degree_interval(degree)
        if iv is None:
            return None
        return (self.root_pc + iv) % 12

    def degree_interval(self, degree: int) -> int | None:
        """Semitone interval realising ``degree``, or ``None``."""
        folded = (degree,) + _FOLD.get(degree, ())
        if self.degrees:
            # first match wins, so `alt`'s b9 answers for the 9th before its #9
            for d in folded:
                for dd, semi in self.degrees:
                    if dd == d:
                        return semi
            return None
        # no analytic map (e.g. a raw pitch set): fall back on interval sizes
        for d in folded:
            for size in _DEGREE_SIZES.get(d, ()):
                if size in self.intervals:
                    return size
                if size + 12 in self.intervals:
                    return size + 12
                if size >= 12 and (size - 12) in self.intervals:
                    return size - 12
        return None

    # -- convenience --------------------------------------------------------
    def with_bass(self, bass_pc: int | None) -> "Chord":
        return Chord(self.root_pc, self.quality, self.intervals, bass_pc,
                     self.symbol, self.degrees)

    def root_name(self) -> str:
        return PC_NAMES[self.root_pc % 12]


#: compound <-> simple degree folding used by ``Chord.degree_interval``.
_FOLD: dict[int, tuple[int, ...]] = {
    1: (8,), 2: (9,), 4: (11,), 6: (13,),
    9: (2,), 11: (4,), 13: (6,),
}

#: fallback interval sizes per degree, canonical first.
_DEGREE_SIZES: dict[int, tuple[int, ...]] = {
    1: (0,),
    2: (2, 1, 3),
    3: (4, 3),
    4: (5, 6),
    5: (7, 6, 8),
    6: (9, 8, 10),
    7: (10, 11, 9),
    9: (14, 13, 15),
    11: (17, 18, 16),
    13: (21, 20, 22),
}


# ---------------------------------------------------------------------------
# suffix (extension / alteration) parsing
# ---------------------------------------------------------------------------


class _Spelling:
    """Mutable accumulator for one chord's interval content."""

    def __init__(self, third: int | None,
                 scale_ext: dict[int, int] | None = None) -> None:
        self.third: int | None = third
        self.fifth: int | None = 7 if scale_ext is None else scale_ext.get(5, 7)
        self.seventh: int | None = None
        self.maj7_flag = False
        self.alt = False
        self.extras: list[tuple[int, int]] = []   # (degree, semitone)
        self.tags: list[str] = []
        #: diatonic interval per degree when the chord is borrowed from a mode
        self.scale_ext: dict[int, int] = dict(scale_ext or {})
        #: explicit slot assignments, for conflict detection
        self.slots: dict[str, tuple[str, int | None]] = {}

    # -- helpers ------------------------------------------------------------
    def nat(self, degree: int, default: int) -> int:
        """Natural interval for ``degree``: diatonic when borrowed, else default."""
        return self.scale_ext.get(degree, default)

    def set_slot(self, name: str, value: int | None, token: str,
                 symbol: str, pos=None) -> None:
        """Record an explicit assignment of a core slot, rejecting conflicts."""
        prev = self.slots.get(name)
        if prev is not None and prev[1] != value:
            raise _harm_error(
                f"{symbol!r} sets the {name} twice: {prev[0]!r} then {token!r}",
                symbol=symbol, token=token, pos=pos,
                suggestion=f"pick one {name}: drop {prev[0]!r} or {token!r}")
        self.slots[name] = (token, value)
        if name == "third":
            self.third = value
        elif name == "fifth":
            self.fifth = value
        elif name == "seventh":
            self.seventh = value

    def add(self, degree: int, semi: int) -> None:
        # a later alteration of the same degree replaces the natural form,
        # unless the pair is already present (alt wants both b9 and #9)
        if (degree, semi) in self.extras:
            return
        self.extras.append((degree, semi))

    def replace(self, degree: int, semi: int) -> None:
        self.extras = [(d, s) for (d, s) in self.extras if d != degree]
        self.extras.append((degree, semi))

    def default_seventh(self) -> int:
        if self.maj7_flag:
            return 11
        return self.nat(7, 10)

    def imply_seventh(self) -> None:
        if self.seventh is None:
            self.seventh = self.default_seventh()

    # -- output -------------------------------------------------------------
    def build(self) -> tuple[tuple[int, ...], tuple[tuple[int, int], ...], str]:
        pairs: list[tuple[int, int]] = [(1, 0)]
        if self.third is not None:
            pairs.append((3, self.third))
        if self.fifth is not None:
            pairs.append((5, self.fifth))
        if self.seventh is not None:
            pairs.append((7, self.seventh))
        pairs.extend(self.extras)
        # sort by semitone, stable on degree
        pairs.sort(key=lambda p: (p[1], p[0]))
        seen: set[int] = set()
        ivs: list[int] = []
        for _d, s in pairs:
            if s not in seen:
                seen.add(s)
                ivs.append(s)
        return tuple(ivs), tuple(pairs), self.quality_name()

    def quality_name(self) -> str:
        if self.alt:
            return "alt"
        third, fifth, seventh = self.third, self.fifth, self.seventh
        exts = dict(self.extras)
        # --- triad / seventh core -----------------------------------------
        if third is None:
            if 4 in exts:
                base = "sus4"
            elif 2 in exts:
                base = "sus2"
            else:
                base = "5"
            if seventh == 10:
                base += "7"
            elif seventh == 11:
                base = "maj7" + base
        elif third == 3 and fifth == 6:
            base = {None: "dim", 9: "dim7", 10: "halfdim7", 11: "dimmaj7"}.get(
                seventh, "dim")
        elif third == 3:
            if seventh is None:
                base = "min6" if 6 in exts else "min"
            elif seventh == 10:
                base = "min7"
            elif seventh == 11:
                base = "minmaj7"
            else:
                base = "min"
        else:  # major third
            if fifth == 8:
                base = "aug7" if seventh == 10 else ("augmaj7" if seventh == 11
                                                    else "aug")
            elif seventh is None:
                if 6 in exts and 9 in exts:
                    base = "6/9"
                elif 6 in exts:
                    base = "6"
                else:
                    base = "maj"
            elif seventh == 10:
                base = "dom7"
            elif seventh == 11:
                base = "maj7"
            else:
                base = "maj"
        # --- highest natural extension ------------------------------------
        if seventh is not None and base not in ("6", "6/9"):
            if 13 in exts and exts[13] == 21:
                base = base.replace("7", "13")
            elif 11 in exts and exts[11] == 17:
                base = base.replace("7", "11")
            elif 9 in exts and exts[9] == 14:
                base = base.replace("7", "9")
        elif seventh is None and 9 in exts and exts[9] == 14 and base == "maj":
            base = "add9"
        elif seventh is None and 9 in exts and exts[9] == 14 and base == "min":
            base = "minadd9"
        # Fifth alterations are only spelled out when the base name does not
        # already encode them (dim/halfdim/aug carry their own fifth).
        tags = [t for t in self.tags
                if not (t in ("b5", "-5", "#5", "+5")
                        and ((third == 3 and fifth == 6)
                             or (third == 4 and fifth == 8)))]
        return base + "".join(tags)


#: (token, handler-name) pairs.  Scanning is longest-token-first.
_ALTERATIONS = {
    "b5": ("fifth", 6), "#5": ("fifth", 8),
    "-5": ("fifth", 6), "+5": ("fifth", 8),
    "b9": (9, 13), "#9": (9, 15), "-9": (9, 13), "+9": (9, 15),
    "b11": (11, 16), "#11": (11, 18),
    "b13": (13, 20), "#13": (13, 22),
}

_ROMAN_TOKENS = [
    "6/9", "sus2", "sus4", "add9", "add11", "add13", "alt",
    "^13", "^11", "^9", "^7", "^",
    "o7", "0", "x",
    "b13", "#13", "b11", "#11", "b9", "#9", "b5", "#5",
    "13", "11", "9", "7", "6", "5",
]

_ABS_TOKENS = _ROMAN_TOKENS + [
    "maj13", "maj11", "maj9", "maj7", "maj", "M",
    "dim7", "dim", "o", "0", "aug", "+",
    "min", "m", "-",
    "ø", "h",
    "sus",
]


def _order_tokens(toks: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    for i, t in enumerate(toks):
        seen.setdefault(t, i)
    return sorted(seen, key=lambda t: (-len(t), seen[t]))


_ROMAN_TOKENS_ORDERED = _order_tokens(_ROMAN_TOKENS)
_ABS_TOKENS_ORDERED = _order_tokens(_ABS_TOKENS)


def _scan(suffix: str, tokens: list[str]) -> tuple[list[str], str]:
    """Greedy longest-match tokenisation.  Returns (tokens, leftover)."""
    out: list[str] = []
    i = 0
    while i < len(suffix):
        for tok in tokens:
            if suffix.startswith(tok, i):
                out.append(tok)
                i += len(tok)
                break
        else:
            return out, suffix[i:]
    return out, ""


def _validate_tokens(toks: list[str], symbol: str, pos=None) -> None:
    """Reject repeated and mutually exclusive suffix tokens.

    No legal symbol in SPEC §4 repeats a suffix token, so a repeat is always a
    typo or a fuzzing attempt (``Cmmm``, ``C--``, ``vii0000``, ``I7777...``).
    ``alt`` names a complete chord (1 b9 #9 3 #11 b13 b7); it may only be
    preceded by a redundant ``7`` and must be the last token, which rejects
    ``i13alt`` (whose 13 would be silently discarded) and ``V7alt7``.
    """
    seen: set[str] = set()
    for tok in toks:
        if tok in seen:
            raise _harm_error(
                f"repeated chord token {tok!r} in {symbol!r}",
                symbol=symbol, token=tok, pos=pos,
                suggestion=f"write {tok!r} once")
        seen.add(tok)
    if "alt" in toks:
        i = toks.index("alt")
        before = [t for t in toks[:i] if t != "7"]
        after = toks[i + 1:]
        if before or after:
            bad = (before + after)[0]
            raise _harm_error(
                f"'alt' is a complete altered dominant and cannot be combined "
                f"with {bad!r} in {symbol!r}",
                symbol=symbol, token=bad, pos=pos,
                suggestion="write V7alt, or spell the tensions out "
                           "(V7b9#11b13)")


def _apply_tokens(sp: _Spelling, toks: list[str], symbol: str, pos=None) -> None:
    _validate_tokens(toks, symbol, pos)
    for tok in toks:
        if tok in ("m", "min", "-"):
            sp.set_slot("third", 3, tok, symbol, pos)
        elif tok in ("maj", "M"):
            sp.maj7_flag = True
        elif tok in ("maj7", "^7"):
            sp.maj7_flag = True
            sp.set_slot("seventh", 11, tok, symbol, pos)
        elif tok in ("maj9", "^9"):
            sp.maj7_flag = True
            sp.set_slot("seventh", 11, tok, symbol, pos)
            sp.replace(9, sp.nat(9, 14))
        elif tok in ("maj11", "^11"):
            sp.maj7_flag = True
            sp.set_slot("seventh", 11, tok, symbol, pos)
            sp.replace(9, sp.nat(9, 14))
            sp.replace(11, sp.nat(11, 17))
        elif tok in ("maj13", "^13"):
            sp.maj7_flag = True
            sp.set_slot("seventh", 11, tok, symbol, pos)
            sp.replace(9, sp.nat(9, 14))
            sp.replace(13, sp.nat(13, 21))
        elif tok == "^":
            sp.maj7_flag = True
            sp.set_slot("seventh", 11, tok, symbol, pos)
        elif tok in ("dim", "o", "0"):
            sp.set_slot("third", 3, tok, symbol, pos)
            sp.set_slot("fifth", 6, tok, symbol, pos)
        elif tok in ("dim7", "o7"):
            sp.set_slot("third", 3, tok, symbol, pos)
            sp.set_slot("fifth", 6, tok, symbol, pos)
            sp.set_slot("seventh", 9, tok, symbol, pos)
        elif tok in ("ø", "h"):
            sp.set_slot("third", 3, tok, symbol, pos)
            sp.set_slot("fifth", 6, tok, symbol, pos)
            sp.set_slot("seventh", 10, tok, symbol, pos)
        elif tok in ("aug", "+"):
            sp.set_slot("fifth", 8, tok, symbol, pos)
        elif tok == "x":
            sp.set_slot("third", 4, tok, symbol, pos)
            sp.set_slot("seventh", 10, tok, symbol, pos)
        elif tok == "alt":
            sp.alt = True
            sp.set_slot("third", 4, tok, symbol, pos)
            sp.set_slot("fifth", None, tok, symbol, pos)
            sp.set_slot("seventh", 10, tok, symbol, pos)
            sp.extras = [(9, 13), (9, 15), (11, 18), (13, 20)]
        elif tok == "7":
            sp.set_slot("seventh", sp.default_seventh(), tok, symbol, pos)
        elif tok == "9":
            sp.imply_seventh()
            sp.replace(9, sp.nat(9, 14))
        elif tok == "11":
            sp.imply_seventh()
            sp.replace(9, sp.nat(9, 14))
            sp.replace(11, sp.nat(11, 17))
        elif tok == "13":
            sp.imply_seventh()
            sp.replace(9, sp.nat(9, 14))
            sp.replace(13, sp.nat(13, 21))
        elif tok == "6":
            sp.replace(6, sp.nat(6, 9))
        elif tok == "6/9":
            sp.replace(6, sp.nat(6, 9))
            sp.replace(9, sp.nat(9, 14))
        elif tok == "5":
            sp.set_slot("third", None, tok, symbol, pos)
            sp.set_slot("fifth", 7, tok, symbol, pos)
        elif tok == "sus2":
            sp.set_slot("third", None, tok, symbol, pos)
            sp.replace(2, 2)
        elif tok in ("sus4", "sus"):
            sp.set_slot("third", None, tok, symbol, pos)
            sp.replace(4, 5)
        elif tok == "add9":
            sp.replace(9, sp.nat(9, 14))
        elif tok == "add11":
            sp.replace(11, sp.nat(11, 17))
        elif tok == "add13":
            sp.replace(13, sp.nat(13, 21))
        elif tok in _ALTERATIONS:
            slot, semi = _ALTERATIONS[tok]
            if slot == "fifth":
                sp.set_slot("fifth", semi, tok, symbol, pos)
            else:
                sp.imply_seventh()
                sp.replace(int(slot), semi)
            sp.tags.append(tok)
        else:  # pragma: no cover - _scan only yields known tokens
            raise _harm_error(
                f"unhandled chord token {tok!r} in {symbol!r}",
                symbol=symbol, token=tok, pos=pos)


# ---------------------------------------------------------------------------
# bass / slash handling
# ---------------------------------------------------------------------------

_NOTE_RE = re.compile(r"^([A-G])([b#]*)$")
_ROMAN_TAIL_RE = re.compile(r"^([b#]*)(iii|vii|ii|iv|vi|i|v|III|VII|II|IV|VI|I|V)$")


def _note_to_pc(name: str) -> int | None:
    m = _NOTE_RE.match(name)
    if not m:
        return None
    pc = NOTE_NAMES[m.group(1)]
    for ch in m.group(2):
        pc += 1 if ch == "#" else -1
    return pc % 12


_SLASH_SENTINEL = "\x00"


def _split_slash(sym: str) -> tuple[str, str | None]:
    """Split off a trailing ``/tail``, protecting the ``6/9`` token."""
    protected = sym.replace("6/9", "6" + _SLASH_SENTINEL + "9")
    if "/" not in protected:
        return sym, None
    head, _, tail = protected.rpartition("/")
    head = head.replace(_SLASH_SENTINEL, "/")
    return head, tail.replace(_SLASH_SENTINEL, "/")


def _apply_bass(chord: Chord, bass: str | None, symbol: str, pos=None) -> Chord:
    if bass is None:
        return chord
    if not bass.strip():
        # `V/` is a truncated secondary dominant or an empty slash bass; both
        # are mistakes, and silently returning a plain V hides them.
        raise _harm_error(
            f"{symbol!r} ends in a slash with nothing after it",
            symbol=symbol, token="/", pos=pos,
            suggestion="write a target degree (V7/ii), a bass note (V/B) or a "
                       "chord degree (V/3)")
    bass = bass.strip()
    pc = _note_to_pc(bass)
    if pc is None:
        if re.fullmatch(r"\d+", bass):
            deg = int(bass)
            pc = chord.degree_pc(deg)
            if pc is None:
                raise _harm_error(
                    f"chord {symbol!r} has no degree {deg} to put in the bass",
                    symbol=symbol, token=bass, pos=pos,
                    suggestion=f"available degrees: "
                               f"{sorted({d for d, _ in chord.degrees})}",
                )
        else:
            raise _harm_error(
                f"bad slash bass {bass!r} in {symbol!r}",
                symbol=symbol, token=bass, pos=pos,
                suggestion="use a note name (/E) or a chord degree (/3)")
    return chord.with_bass(pc % 12)


# ---------------------------------------------------------------------------
# shared front-door validation
# ---------------------------------------------------------------------------

_PAREN_RE = re.compile(r"^[^()]*\([^()]+\)$")


def _precheck(sym: str, original: str, pos=None) -> str:
    """Trim, reject empty / whitespace-only / over-long symbols."""
    s = (sym or "").strip()
    if not s:
        raise _harm_error(
            "empty chord symbol" if not (sym or "") else
            "chord symbol is only whitespace",
            symbol=original, token=original or "", pos=pos,
            suggestion=_suggest(original))
    if len(s) > MAX_SYMBOL_LEN:
        raise _harm_error(
            f"chord symbol is {len(s)} characters long "
            f"(limit {MAX_SYMBOL_LEN})",
            symbol=original, token=s[:MAX_SYMBOL_LEN], pos=pos,
            suggestion="a chord symbol never needs more than "
                       f"{MAX_SYMBOL_LEN} characters; check for a runaway "
                       "repeat like 'I7777'")
    return s


def _strip_parens(suffix: str, symbol: str, pos=None) -> str:
    """Allow one parenthesised alteration group, e.g. ``C(b5)`` / ``V7(b9)``."""
    if "(" not in suffix and ")" not in suffix:
        return suffix
    if not _PAREN_RE.match(suffix):
        raise _harm_error(
            f"unbalanced parentheses in {symbol!r}",
            symbol=symbol, token="(" if "(" in suffix else ")", pos=pos,
            suggestion="parentheses may only wrap one trailing alteration "
                       "group, as in C(b5) or V7(b9)")
    return suffix.replace("(", "").replace(")", "")


# ---------------------------------------------------------------------------
# roman numerals
# ---------------------------------------------------------------------------

_ROMAN_HEAD_RE = re.compile(r"^([b#]*)(iii|vii|ii|iv|vi|i|v|III|VII|II|IV|VI|I|V)")


def _suggest(sym: str) -> str:
    return ("expected e.g. i ii7 V7 iv11 bVI IV^7 vii0 viio7 V7alt V/ii iiid, "
            "or an absolute symbol like Cm9 / Ab^7 / F#7b13")


def _diatonic_stack(degree: int, mode: str) -> dict[int, int]:
    """Intervals above the root of the diatonic chord on ``degree`` of ``mode``.

    Built by stacking scale thirds: the chord degrees 3, 5, 7, 9, 11, 13 are
    scale degrees ``degree+2, +4, +6, +8, +10, +12`` (0-based indices
    ``degree-1 + 2k``), reduced to semitones above the chord root.  Also
    supplies the diatonic 6th (scale degree ``degree+5``), which is what a
    borrowed ``6`` chord means.
    """
    base = _scale_offset(degree - 1, mode)
    out = {chord_deg: _scale_offset(degree - 1 + step, mode) - base
           for chord_deg, step in ((3, 2), (5, 4), (7, 6), (9, 8), (11, 10),
                                   (13, 12), (6, 5))}
    return out


def parse_roman(sym: str, tonic_pc: int, mode: str, *,
                warnings: list | None = None, pos=None) -> Chord:
    """Parse a roman-numeral chord symbol in the key ``(tonic_pc, mode)``.

    Handles case→quality, ``b``/``#`` prefixes, the extension set
    ``6 7 9 11 13 ^7 0 o7 sus2 sus4 add9 6/9 alt x``, the alterations
    ``b5 #5 b9 #9 #11 b13``, secondary dominants (``V/ii``), slash bass
    (``i/3``, ``IV/E``) and modal-interchange suffix letters
    ``n d f y m a l h e``.

    ``warnings``, when given, collects soft diagnostics (formatted strings, as
    produced by ``errors.warn``) — today: a written case that disagrees with the
    borrowed mode's diatonic quality.  ``pos`` is the source position of the
    symbol, threaded into every ``HarmonyError``.
    """
    original = sym
    sym = _precheck(sym, original, pos)
    mode = normalise_mode(mode, pos=pos)

    head, tail = _split_slash(sym)
    bass: str | None = None
    if tail is not None:
        m = _ROMAN_TAIL_RE.match(tail)
        if m:
            # secondary function: re-root into the key of that degree, major.
            acc = sum(1 if c == "#" else -1 for c in m.group(1))
            if len(m.group(1)) > 1:
                raise _harm_error(
                    f"more than one accidental on the applied degree of "
                    f"{original!r}",
                    symbol=original, token=m.group(1), pos=pos,
                    suggestion="write a single b or # (V7/bIII)")
            deg = _ROMAN_VALUES[m.group(2).lower()]
            new_tonic = (_degree_root_offset(deg, acc, mode) + tonic_pc) % 12
            inner = parse_roman(head, new_tonic, "major",
                                warnings=warnings, pos=pos)
            return Chord(inner.root_pc, inner.quality, inner.intervals,
                         inner.bass_pc, original, inner.degrees)
        bass = tail
        if _split_slash(head)[1] is not None:
            # a slash bass stacked on a secondary function: `V/ii/E`.
            inner = parse_roman(head, tonic_pc, mode,
                                warnings=warnings, pos=pos)
            inner = Chord(inner.root_pc, inner.quality, inner.intervals,
                          inner.bass_pc, original, inner.degrees)
            return _apply_bass(inner, bass, original, pos)

    m = _ROMAN_HEAD_RE.match(head)
    if not m:
        raise _harm_error(
            f"not a roman numeral: {original!r}",
            symbol=original, token=head or original, pos=pos,
            suggestion=_suggest(original))
    if len(m.group(1)) > 1:
        raise _harm_error(
            f"more than one accidental in {original!r}",
            symbol=original, token=m.group(1), pos=pos,
            suggestion="roman numerals take at most one accidental; "
                       "'bbVI' is almost always a typo for 'bVI' or 'V'")
    accidental = sum(1 if c == "#" else -1 for c in m.group(1))
    numeral = m.group(2)
    degree = _ROMAN_VALUES[numeral.lower()]
    is_upper = numeral[0].isupper()
    suffix = _strip_parens(head[m.end():], original, pos)

    toks, leftover = _scan(suffix, _ROMAN_TOKENS_ORDERED)

    borrowed_mode: str | None = None
    if leftover:
        if len(leftover) == 1 and leftover in MODAL_INTERCHANGE_LETTERS:
            borrowed_mode = MODAL_INTERCHANGE_LETTERS[leftover]
        else:
            raise _harm_error(
                f"unknown chord symbol {original!r}",
                symbol=original, token=leftover, pos=pos,
                suggestion=_suggest(original),
            )

    # --- root ---------------------------------------------------------------
    # An unaccented numeral takes the effective mode's own degree; an accidental
    # is chromatic, i.e. measured from the major scale (`bVI` is Ab in C major
    # and in C minor alike).  For a borrowed numeral the effective mode is the
    # borrowed one, which is also what makes `bVIIm` == Bb (no double shift).
    eff_mode = borrowed_mode or mode
    root_off = _degree_root_offset(degree, accidental, eff_mode)
    root_pc = (tonic_pc + root_off) % 12

    # --- quality ------------------------------------------------------------
    if borrowed_mode is None:
        sp = _Spelling(4 if is_upper else 3)
    else:
        # RULING: the mode letter selects the scale, and the chord is the
        # diatonic chord of that scale on that degree.  The written case is
        # validated, not authoritative.
        stack = _diatonic_stack(degree, borrowed_mode)
        sp = _Spelling(stack[3], stack)
        wanted = 4 if is_upper else 3
        if stack[3] != wanted and not any(
                t in ("m", "min", "-", "x", "alt", "dim", "o", "0", "dim7",
                      "o7", "ø", "h", "sus2", "sus4", "sus", "5", "aug", "+")
                for t in toks):
            errors.warn(
                warnings,
                f"{original!r}: {borrowed_mode} spells degree {degree} with a "
                f"{'minor' if stack[3] == 3 else 'major' if stack[3] == 4 else str(stack[3]) + '-semitone'} "
                f"third, but the numeral is written "
                f"{'upper' if is_upper else 'lower'}-case; the borrowed scale "
                f"wins — write "
                f"{(numeral.upper() if stack[3] >= 4 else numeral.lower()) + leftover} "
                f"to silence this",
                line=int(getattr(pos, "line", 0) or 1),
                col=int(getattr(pos, "col", 0) or 1),
                path=str(getattr(pos, "file", "<input>") or "<input>"),
                kind="harmony")
    _apply_tokens(sp, toks, original, pos)
    intervals, degrees, quality = sp.build()

    chord = Chord(root_pc, quality, intervals, None, original, degrees)
    return _apply_bass(chord, bass, original, pos)


def _degree_root_offset(degree: int, accidental: int, mode: str) -> int:
    """Semitone offset of a (possibly accidentalised) roman-numeral degree."""
    if accidental:
        return _scale_offset(degree - 1, "major") + accidental
    return _scale_offset(degree - 1, mode)


# ---------------------------------------------------------------------------
# absolute symbols
# ---------------------------------------------------------------------------

_ABS_ROOT_RE = re.compile(r"^([A-G])([b#]*)")


def parse_absolute(sym: str, *, warnings: list | None = None,
                   pos=None) -> Chord:
    """Parse an absolute chord symbol such as ``Cm9`` / ``Ab^7`` / ``E7#9#11``.

    ``warnings`` collects soft diagnostics; ``pos`` is threaded into errors.
    """
    original = sym
    sym = _precheck(sym, original, pos)

    head, tail = _split_slash(sym)
    bass = tail

    m = _ABS_ROOT_RE.match(head)
    if not m:
        raise _harm_error(
            f"not an absolute chord symbol: {original!r}",
            symbol=original, token=head or original, pos=pos,
            suggestion=_suggest(original))
    if len(m.group(2)) > 1:
        raise _harm_error(
            f"more than one accidental on the root of {original!r}",
            symbol=original, token=m.group(2), pos=pos,
            suggestion="chord roots take at most one b or #")
    root_pc = _note_to_pc(m.group(1) + m.group(2))
    assert root_pc is not None
    raw_suffix = head[m.end():]

    # `Cb5` reads two ways -- a Cb power chord or C with a lowered fifth -- and
    # both are defensible, so it is rejected rather than silently resolved.
    if m.group(2) and raw_suffix.startswith("5"):
        acc = m.group(2)
        raise _harm_error(
            f"{original!r} is ambiguous: "
            f"'{m.group(1)}{acc}' + '5' (a power chord on "
            f"{PC_NAMES[root_pc]}) or '{m.group(1)}' + '{acc}5' "
            f"(a {'lowered' if acc == 'b' else 'raised'} fifth)",
            symbol=original, token=acc + "5", pos=pos,
            suggestion=f"write '{m.group(1)}{acc}(5)' for the power chord or "
                       f"'{m.group(1)}({acc}5)' for the altered fifth")

    suffix = _strip_parens(raw_suffix, original, pos)
    toks, leftover = _scan(suffix, _ABS_TOKENS_ORDERED)
    if leftover:
        raise _harm_error(
            f"unknown chord symbol {original!r}",
            symbol=original, token=leftover, pos=pos,
            suggestion=_suggest(original))

    sp = _Spelling(4)
    _apply_tokens(sp, toks, original, pos)
    # Lead-sheet dialect: in an absolute symbol `b13` *is* the altered fifth
    # (b13 == #5 enharmonically), so the natural 5th is replaced, not doubled a
    # semitone away.  Roman numerals keep the analytic reading (see
    # refs/specs/harmony_truth.md "b13").
    if "b13" in toks and "fifth" not in sp.slots and sp.fifth == 7:
        sp.fifth = None
        errors.warn(warnings,
                    f"{original!r}: b13 read as the altered fifth; the natural "
                    f"5th is omitted (lead-sheet convention)",
                    line=int(getattr(pos, "line", 0) or 1),
                    col=int(getattr(pos, "col", 0) or 1),
                    path=str(getattr(pos, "file", "<input>") or "<input>"),
                    kind="harmony")
    intervals, degrees, quality = sp.build()
    chord = Chord(root_pc, quality, intervals, None, original, degrees)
    return _apply_bass(chord, bass, original, pos)


def parse_pitchset(offsets: list[int], absolute: bool = False,
                   symbol: str = "") -> Chord:
    """Build a Chord from an explicit pitch set (SPEC §4 spelling 3).

    ``absolute=False``: semitones over the chord root (root is the first, or 0).
    ``absolute=True``: MIDI note numbers; the lowest becomes the root.
    """
    if not offsets:
        raise _harm_error("empty pitch set", symbol=symbol, token=symbol,
                          suggestion="e.g. {0 3 7 10} or {C4 Eb4 G4}")
    if absolute:
        base = min(offsets)
        root_pc = base % 12
        ivs = sorted({o - base for o in offsets})
    else:
        root_pc = offsets[0] % 12
        ivs = sorted({o - offsets[0] for o in offsets})
        if 0 not in ivs:
            ivs = [0] + ivs
    return Chord(root_pc, "set", tuple(ivs), None, symbol or "{...}", ())


def parse_chord(sym: str, tonic_pc: int = 0, mode: str = "major", *,
                warnings: list | None = None, pos=None) -> Chord:
    """Best-effort dispatch between roman and absolute spellings."""
    s = _precheck(sym, sym or "", pos)
    if _ROMAN_HEAD_RE.match(s):
        return parse_roman(s, tonic_pc, mode, warnings=warnings, pos=pos)
    return parse_absolute(s, warnings=warnings, pos=pos)
