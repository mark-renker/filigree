"""Filigree parser (piece P1): tokens -> ``ast_nodes.Document``.

Responsibilities are fixed by ``docs/ARCH.md`` §"P1":

* directives, normalised (``tempo`` float, ``meter`` (int,int), ``key`` (pc, mode), ...)
* ``gesture`` / ``feel`` / ``voicing`` / ``part`` / ``stave`` blocks
* lane splitting on ``|``, slot tokenisation, ``[...]`` groups, ``<...>``
  alternations, ``x*3``, ``[: ... :4]`` expansion, sticky octave/velocity/gate
  state per lane
* the full gesture-expression grammar with precedence
  ``|`` < ``>>`` < ``+ -`` < ``*`` < unary ``-`` < ``@window`` < postfix call
* decorations (``!gesture`` ``:v90`` ``%50`` ``'`` ``,`` ``?``) on the owning Slot
* curve glyphs -> ``Slot(kind="glyph", ...)`` and ``>`` targets -> ``Target``

The parser never resolves scale degrees to MIDI pitches, never interprets
``@key`` beyond storing it, and never evaluates a gesture.
"""

from __future__ import annotations

import difflib
import re
from typing import Any, Optional

from .ast_nodes import (
    Bar, BinOp, Breakpoints, Call, ChordTok, Document, FeelDef, GestureDef,
    Lane, Num, Part, PitchTok, PlayStmt, Pos, Ref, Slot, Stave, Target, UnOp,
    VoicingDef, Window,
)
from . import gesture as gest
from .errors import ParseError, warn
from .lex import LANE_NAMES, Token, tokenize

__all__ = ["parse", "MODE_NAMES", "DIRECTIVES"]

# --------------------------------------------------------------------------
# tables
# --------------------------------------------------------------------------

#: SPEC §2 ``@key`` modes.
MODE_NAMES: tuple[str, ...] = (
    "major", "ionian", "dorian", "phrygian", "lydian", "mixolydian", "minor",
    "aeolian", "locrian", "harmonic-minor", "melodic-minor", "whole-tone",
    "chromatic", "blues",
)

#: SPEC §2 directives (written without the leading ``@``).
DIRECTIVES: tuple[str, ...] = (
    "tempo", "meter", "key", "ppq", "bend-range", "grid", "seed", "title",
    "voicing", "feel", "lane-range",
)

_DIRECTIVE_KEY = {"bend-range": "bend_range", "lane-range": "lane_range"}

#: Defaults from the SPEC §2 table, pre-populated into ``Document.directives``.
_DEFAULT_DIRECTIVES: dict[str, Any] = {
    "tempo": 120.0,
    "meter": (4, 4),
    "key": (0, "major"),
    "ppq": 960,
    "bend_range": 48.0,
    "grid": 10.0,
    "seed": 0,
}

_LETTER_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Lane options any part of the compiler actually reads (SPEC §4/§7).
_LANE_OPTION_KEYS = frozenset({"range", "shape", "time", "voicing", "gesture"})

_CURVE_GLYPHS = "_v-^/\\x~"


def _ident_ahead(text: str, i: int) -> bool:
    """True if position *i* starts an identifier longer than one character.

    Disambiguates the `v` glyph (lane minimum, SPEC §7) from an inline gesture
    call whose name begins with `v` (`vibr(0.3)`).  A single `v`/`V` is always
    the glyph; `vv` is two glyphs; `vibr(` is a call.
    """
    m = re.match(r"[A-Za-z_][A-Za-z0-9_-]*", text[i:])
    if m is None:
        return False
    word = m.group(0)
    j = i + m.end()
    if j < len(text) and text[j] == "(":
        return True             # `vibr(depth: 0.5st)` — an inline gesture call
    if set(word) <= set(_CURVE_GLYPHS + "0123456789"):
        return False            # `vv__`, `v`, `x_v` — a run of glyphs
    return True                 # `vibr` with no args: let the caller diagnose
_ANCHORS = ("low", "high", "root", "guide")
_SHAPES = ("ease", "linear", "hold", "exp", "snap")
_STRING_KWARGS = ("shape", "dist", "mode", "top", "time", "curve")

_ABS_PITCH_RE = re.compile(r"^([A-G])(#|b|##|bb)?(-?\d+)$")
_ROMAN_RE = re.compile(r"^([b#]*)(i{1,3}|iv|vi{1,3}|v|I{1,3}|IV|VI{1,3}|V)(?![ivIV])")
_NUM_TEXT_RE = re.compile(r"^([+-]?\d+(?:\.\d+)?)(st|hz|ms|bpm|beat|cent|%)?$")

_OPEN = {"[": "]", "(": ")", "{": "}", "<": ">"}
_CLOSE = {"]": "[", ")": "(", "}": "{", ">": "<"}


def _note_name_to_pc(name: str) -> Optional[int]:
    if not name:
        return None
    letter = name[0].upper()
    if letter not in _LETTER_PC:
        return None
    pc = _LETTER_PC[letter]
    for ch in name[1:]:
        if ch == "#":
            pc += 1
        elif ch == "b":
            pc -= 1
        else:
            return None
    return pc % 12


def _note_name_to_midi(name: str) -> Optional[int]:
    """``C4`` -> 60 (middle C = 60).  Returns None when *name* is not a pitch."""
    m = _ABS_PITCH_RE.match(name)
    if not m:
        return None
    letter, acc, octv = m.group(1), m.group(2) or "", int(m.group(3))
    pc = _LETTER_PC[letter]
    pc += acc.count("#") - acc.count("b")
    return (octv + 1) * 12 + pc


def _parse_num_text(text: str) -> tuple[float, Optional[str]]:
    m = _NUM_TEXT_RE.match(text)
    if not m:
        raise ValueError(text)
    val = float(m.group(1))
    unit = m.group(2)
    if unit == "%":
        unit = "pct"
    return val, unit


def _suggest(word: str, options) -> str:
    hits = difflib.get_close_matches(word, list(options), n=2, cutoff=0.5)
    if hits:
        return "did you mean " + " or ".join(repr(h) for h in hits) + "?"
    return "known values: " + ", ".join(sorted(options)[:8]) + " ..."


def _split_ws(text: str) -> list[tuple[str, int]]:
    """Bracket-aware split of *text* on whitespace -> [(substring, offset)]."""
    out: list[tuple[str, int]] = []
    stack: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        start = i
        while i < n:
            c = text[i]
            if c.isspace() and not stack:
                break
            if c in _OPEN:
                stack.append(c)
            elif c in _CLOSE:
                if stack and stack[-1] == _CLOSE[c]:
                    stack.pop()
                elif c != ">":
                    stack.clear()
            i += 1
        out.append((text[start:i], start))
    return out


def _match_bracket(text: str, i: int) -> int:
    """Index of the bracket closing ``text[i]``, or -1."""
    open_c = text[i]
    close_c = _OPEN[open_c]
    depth = 0
    for j in range(i, len(text)):
        c = text[j]
        if c == open_c:
            depth += 1
        elif c == close_c:
            depth -= 1
            if depth == 0:
                return j
    return -1


# --------------------------------------------------------------------------
# per-lane sticky state (SPEC §5 "Sticky state per lane")
# --------------------------------------------------------------------------

class _Sticky:
    __slots__ = ("octave", "velocity", "gate")

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.octave = 0
        self.velocity: Optional[int] = None
        self.gate: Optional[float] = None


# --------------------------------------------------------------------------
# the parser
# --------------------------------------------------------------------------

class Parser:
    def __init__(self, toks: list[Token], src: str, path: str) -> None:
        self.toks = toks
        self.i = 0
        self.src = src
        self.path = path
        self.doc = Document(source=src, path=path)
        self.doc.directives.update(dict(_DEFAULT_DIRECTIVES))
        self.lenient = False
        self._lane_seen: set[tuple[str, Optional[str]]] = set()

    # -- cursor ----------------------------------------------------------
    def cur(self) -> Token:
        return self.toks[min(self.i, len(self.toks) - 1)]

    def peek(self, k: int = 0) -> Token:
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def eat(self) -> Token:
        t = self.cur()
        if self.i < len(self.toks) - 1:
            self.i += 1
        return t

    def at(self, kind: str, text: Optional[str] = None) -> bool:
        t = self.cur()
        return t.kind == kind and (text is None or t.text == text)

    def skip_nl(self) -> None:
        while self.cur().kind == "newline":
            self.i += 1

    def err(self, msg: str, tok: Optional[Token] = None, suggestion: str = "",
            pos: Optional[Pos] = None) -> ParseError:
        if pos is not None:
            return ParseError(msg, line=pos.line, col=pos.col, token="",
                              suggestion=suggestion, path=self.path)
        t = tok or self.cur()
        return ParseError(msg, line=t.line, col=t.col, token=t.text,
                          suggestion=suggestion, path=self.path)

    def err_at(self, msg: str, line: int, col: int, token: str,
               suggestion: str = "") -> ParseError:
        return ParseError(msg, line=line, col=col, token=token,
                          suggestion=suggestion, path=self.path)

    def soft_at(self, msg: str, line: int, col: int, token: str,
                suggestion: str = "", *, recovery: str = "") -> None:
        """A hard error, unless we are parsing leniently.

        LEAD RULING (round 3): `--lenient` has to reach the *parser*.  It was
        implemented in the resolver only, so a typo'd chord symbol, an unknown glyph
        or a malformed pitch set still exited 2 with nothing rendered -- exactly the
        case leniency exists for, since those are what you type while sketching.
        Leniently, each one becomes a warning that says what was skipped, and the
        caller substitutes a musically inert value.
        """
        if not self.lenient:
            raise self.err_at(msg, line, col, token, suggestion)
        tail = f"; {recovery}" if recovery else ""
        self.warn(f"{msg}{tail} (--lenient)", line, col, kind="lenient")

    def expect(self, kind: str, text: str, what: str) -> Token:
        if not self.at(kind, text):
            raise self.err(f"expected {text!r} {what}",
                           suggestion=f"insert {text!r} here")
        return self.eat()

    def pos(self, tok: Optional[Token] = None) -> Pos:
        t = tok or self.cur()
        return Pos(t.line, t.col, self.path)

    def warn(self, msg: str, line: int = 0, col: int = 0,
             kind: str = "general") -> None:
        warn(self.doc.warnings, msg, line=line, col=col, path=self.path,
             kind=kind)

    # ==================================================================
    # document
    # ==================================================================
    def parse_document(self) -> Document:
        while True:
            self.skip_nl()
            t = self.cur()
            if t.kind == "eof":
                break
            if t.kind == "directive":
                self.parse_directive()
            elif t.kind == "badstring":
                raise self.err("unterminated string literal", suggestion="add a closing '\"'")
            elif t.kind == "ident" and t.text == "gesture":
                self.parse_gesture_def()
            elif t.kind == "ident" and t.text == "feel":
                self.parse_feel_def()
            elif t.kind == "ident" and t.text == "voicing":
                self.parse_voicing_def()
            elif t.kind == "ident" and t.text == "part":
                self.parse_part()
            elif t.kind == "ident" and t.text == "stave":
                self.parse_stave()
            elif t.kind == "lane":
                raise self.err(
                    f"lane {t.text!r} outside a stave or part",
                    suggestion="wrap lanes in 'stave <name> { ... }' or "
                               "'part <name> { ... }'")
            else:
                raise self.err(
                    f"unexpected {t.text!r} at top level",
                    suggestion=_suggest(t.text, ("gesture", "feel", "voicing",
                                                 "part", "stave")))
        return self.doc

    # -- directives ------------------------------------------------------
    def _line_tokens(self) -> list[Token]:
        out: list[Token] = []
        while self.cur().kind not in ("newline", "eof"):
            out.append(self.eat())
        return out

    def parse_directive(self) -> None:
        tok = self.eat()
        name = tok.text[1:]
        if name not in DIRECTIVES:
            raise self.err(f"unknown directive '@{name}'", tok,
                           _suggest(name, DIRECTIVES))
        vals = self._line_tokens()
        if not vals:
            raise self.err(f"directive '@{name}' needs a value", tok,
                           f"e.g. '@{name} ...' — see SPEC §2")
        key = _DIRECTIVE_KEY.get(name, name)
        first = vals[0]

        def as_num(t: Token) -> tuple[float, Optional[str]]:
            try:
                return _parse_num_text(t.text)
            except ValueError:
                raise self.err(f"'@{name}' expects a number", t,
                               "e.g. '@tempo 84' or '@tempo 84bpm'") from None

        if name == "tempo":
            v, unit = as_num(first)
            if unit not in (None, "bpm"):
                raise self.err(f"'@tempo' cannot take unit {unit!r}", first,
                               "use plain BPM, e.g. '@tempo 84' or '84bpm'")
            if v <= 0:
                raise self.err("tempo must be positive", first, "e.g. '@tempo 84'")
            self.doc.directives["tempo"] = float(v)
        elif name == "meter":
            if len(vals) != 3 or vals[1].text != "/":
                raise self.err("'@meter' expects 'N/D'", first,
                               "e.g. '@meter 7/8'")
            try:
                num = int(vals[0].text)
                den = int(vals[2].text)
            except ValueError:
                raise self.err("'@meter' expects integers", first,
                               "e.g. '@meter 7/8'") from None
            if num <= 0 or den <= 0:
                raise self.err("meter parts must be positive", first,
                               "e.g. '@meter 7/8'")
            self.doc.directives["meter"] = (num, den)
        elif name == "key":
            pc = _note_name_to_pc(first.text)
            if pc is None:
                raise self.err(f"{first.text!r} is not a note name", first,
                               "tonic must be A-G with optional # / b, "
                               "e.g. '@key Eb dorian'")
            mode = "major"
            if len(vals) > 1:
                mode = vals[1].text.lower()
                if mode not in MODE_NAMES:
                    raise self.err(f"unknown mode {vals[1].text!r}", vals[1],
                                   _suggest(mode, MODE_NAMES))
            self.doc.directives["key"] = (pc, mode)
        elif name in ("ppq", "seed"):
            v, unit = as_num(first)
            if unit is not None or v != int(v):
                raise self.err(f"'@{name}' expects an integer", first,
                               f"e.g. '@{name} 960'" if name == "ppq" else "e.g. '@seed 7'")
            self.doc.directives[key] = int(v)
        elif name in ("bend-range", "lane-range"):
            v, unit = as_num(first)
            if unit not in (None, "st", "cent"):
                raise self.err(f"'@{name}' expects semitones", first,
                               "e.g. '@bend-range 48st'")
            self.doc.directives[key] = v / 100.0 if unit == "cent" else float(v)
        elif name == "grid":
            v, unit = as_num(first)
            if unit not in (None, "ms"):
                raise self.err("'@grid' expects milliseconds", first,
                               "e.g. '@grid 10ms'")
            if v <= 0:
                raise self.err("'@grid' must be positive", first, "e.g. '@grid 10ms'")
            self.doc.directives["grid"] = float(v)
        elif name == "title":
            if first.kind != "string":
                raise self.err("'@title' expects a quoted string", first,
                               'e.g. \'@title "Filigree study"\'')
            self.doc.directives["title"] = first.text
        else:  # voicing / feel
            if first.kind != "ident":
                raise self.err(f"'@{name}' expects a name", first,
                               f"e.g. '@{name} warm'")
            self.doc.directives[key] = first.text

    # -- gesture / feel / voicing / part / stave -------------------------
    def parse_gesture_def(self) -> GestureDef:
        kw = self.eat()
        if self.cur().kind != "ident":
            raise self.err("gesture needs a name", suggestion="e.g. 'gesture cry = bend(0 -> -0.7st -> 0)'")
        name_tok = self.eat()
        params: list[tuple[str, Optional[Any]]] = []
        if self.at("punct", "("):
            self.eat()
            while not self.at("punct", ")"):
                self.skip_nl()
                if self.cur().kind != "ident":
                    raise self.err("expected a parameter name",
                                   suggestion="e.g. 'gesture vibr(rate: 5.2hz, depth: 0.3st) = ...'")
                pname = self.eat().text
                default = None
                if self.at("punct", ":"):
                    self.eat()
                    default = self.parse_expr()
                params.append((pname, default))
                if self.at("punct", ","):
                    self.eat()
                    continue
                break
            if not self.at("punct", ")"):
                raise self.err("unclosed parameter list", suggestion="add ')'")
            self.eat()
        if not self.at("op", "="):
            raise self.err(f"gesture {name_tok.text!r} needs a body", name_tok,
                           "write 'gesture NAME = <expression>'")
        self.eat()
        body = self.parse_expr()
        gd = GestureDef(name=name_tok.text, params=params, body=body,
                        pos=self.pos(kw))
        if gd.name in self.doc.gestures:
            self.warn(f"gesture {gd.name!r} redefined", kw.line, kw.col,
                      kind="redefinition")
        self.doc.gestures[gd.name] = gd
        return gd

    def _brace_fields(self, what: str) -> dict[str, list[Token]]:
        self.skip_nl()
        if not self.at("punct", "{"):
            raise self.err(f"{what} needs a '{{ ... }}' body",
                           suggestion="e.g. 'feel loose = { timing: 14ms gauss }'")
        self.eat()
        fields: dict[str, list[Token]] = {}
        while True:
            self.skip_nl()
            if self.at("punct", "}"):
                self.eat()
                break
            if self.cur().kind == "eof":
                raise self.err(f"unclosed '{{' in {what}",
                               suggestion="add the matching '}'")
            if self.cur().kind != "ident":
                raise self.err(f"expected a field name in {what}",
                               suggestion="fields look like 'name: value'")
            key = self.eat().text
            if not self.at("punct", ":"):
                raise self.err(f"field {key!r} needs ':'",
                               suggestion=f"write '{key}: <value>'")
            self.eat()
            vals: list[Token] = []
            while True:
                self.skip_nl()
                t = self.cur()
                if t.kind == "eof" or (t.kind == "punct" and t.text == "}"):
                    break
                if t.kind == "punct" and t.text == ",":
                    # a comma inside a value list (``on: 2,4``) vs a separator
                    nxt = self.peek(1)
                    if vals and nxt.kind == "number":
                        self.eat()
                        continue
                    self.eat()
                    break
                if t.kind == "ident" and self.peek(1).kind == "punct" \
                        and self.peek(1).text == ":":
                    break
                vals.append(self.eat())
            if not vals:
                raise self.err(f"field {key!r} has no value",
                               suggestion=f"write '{key}: <value>'")
            fields[key] = vals
        return fields

    def parse_feel_def(self) -> FeelDef:
        kw = self.eat()
        if self.cur().kind != "ident":
            raise self.err("feel needs a name",
                           suggestion="e.g. 'feel loose = { timing: 14ms }'")
        name_tok = self.eat()
        if self.at("op", "="):
            self.eat()
        raw = self._brace_fields("feel")
        fields: dict[str, Any] = {}
        for key, vals in raw.items():
            if key == "timing":
                fields["timing"] = self._ms(vals[0], "timing")
                for extra in vals[1:]:
                    fields["timing_dist"] = extra.text
            elif key in ("velocity", "gate"):
                fields[key] = self._frac(vals[0], key)
            elif key in ("onset", "release"):
                fields[key] = self._ms(vals[0], key)
                for extra in vals[1:]:
                    fields[key + "_mode"] = extra.text
            elif key == "on":
                beats: list[int] = []
                for v in vals:
                    try:
                        beats.append(int(float(v.text)))
                    except ValueError:
                        raise self.err("'on:' expects beat numbers", v,
                                       "e.g. 'on: 2,4'") from None
                fields["on"] = tuple(beats)
            elif key == "seed":
                try:
                    fields["seed"] = int(float(vals[0].text))
                except ValueError:
                    raise self.err("'seed:' expects an integer", vals[0],
                                   "e.g. 'seed: 3'") from None
            else:
                raise self.err(f"unknown feel field {key!r}", vals[0],
                               _suggest(key, ("timing", "velocity", "gate",
                                              "onset", "release", "on", "seed")))
        fd = FeelDef(name=name_tok.text, fields=fields, pos=self.pos(kw))
        self.doc.feels[fd.name] = fd
        return fd

    def _ms(self, tok: Token, field: str) -> float:
        try:
            v, unit = _parse_num_text(tok.text)
        except ValueError:
            raise self.err(f"{field!r} expects a time", tok,
                           f"e.g. '{field}: 14ms'") from None
        if unit not in (None, "ms"):
            raise self.err(f"{field!r} expects milliseconds", tok,
                           f"e.g. '{field}: 14ms'")
        return float(v)

    def _frac(self, tok: Token, field: str) -> float:
        try:
            v, unit = _parse_num_text(tok.text)
        except ValueError:
            raise self.err(f"{field!r} expects a number", tok,
                           f"e.g. '{field}: 8%' or '{field}: 0.08'") from None
        return v / 100.0 if unit == "pct" else float(v)

    def parse_voicing_def(self) -> VoicingDef:
        kw = self.eat()
        if self.cur().kind != "ident":
            raise self.err("voicing needs a name",
                           suggestion="e.g. 'voicing warm { range: C3..C5 }'")
        name_tok = self.eat()
        if self.at("op", "="):
            self.eat()
        raw = self._brace_fields("voicing")
        fields: dict[str, Any] = {}
        for key, vals in raw.items():
            if key == "range":
                if len(vals) != 3 or vals[1].text != "..":
                    raise self.err("'range:' expects 'LOW..HIGH'", vals[0],
                                   "e.g. 'range: C3..C5'")
                lo = _note_name_to_midi(vals[0].text)
                hi = _note_name_to_midi(vals[2].text)
                if lo is None or hi is None:
                    bad = vals[0] if lo is None else vals[2]
                    raise self.err(f"{bad.text!r} is not an absolute pitch", bad,
                                   "write letter + optional accidental + octave, e.g. 'C3'")
                if lo > hi:
                    raise self.err("voicing range is inverted", vals[0],
                                   f"write 'range: {vals[2].text}..{vals[0].text}'")
                fields["range"] = (vals[0].text, vals[2].text)
                fields["low"] = lo
                fields["high"] = hi
            elif key == "mode":
                allowed = ("smooth", "close", "open", "drop", "quartal",
                           "shell", "rootless", "literal")
                if vals[0].text not in allowed:
                    raise self.err(f"unknown voicing mode {vals[0].text!r}",
                                   vals[0], _suggest(vals[0].text, allowed))
                fields["mode"] = vals[0].text
            elif key in ("size", "drop"):
                try:
                    fields[key] = int(float(vals[0].text))
                except ValueError:
                    raise self.err(f"{key!r} expects an integer", vals[0],
                                   f"e.g. '{key}: 4'") from None
            elif key == "spread":
                fields["spread"] = self._frac(vals[0], "spread")
            elif key == "top":
                fields["top"] = vals[0].text
            else:
                raise self.err(f"unknown voicing field {key!r}", vals[0],
                               _suggest(key, ("range", "mode", "size", "drop",
                                              "spread", "top")))
        vd = VoicingDef(name=name_tok.text, fields=fields, pos=self.pos(kw))
        self.doc.voicings[vd.name] = vd
        return vd

    def parse_part(self) -> Part:
        kw = self.eat()
        if self.cur().kind != "ident":
            raise self.err("part needs a name",
                           suggestion="e.g. 'part hook { notes | 0 . 2 3 | }'")
        name_tok = self.eat()
        self.skip_nl()
        self.expect("punct", "{", "to open the part body")
        part = Part(name=name_tok.text, pos=self.pos(kw))
        self._lane_seen = set()
        while True:
            self.skip_nl()
            if self.at("punct", "}"):
                self.eat()
                break
            if self.cur().kind == "eof":
                raise self.err(f"unclosed '{{' in part {part.name!r}", kw,
                               "add the matching '}'")
            if self.cur().kind == "lane":
                self._add_lane(part.lanes, self.parse_lane())
            else:
                raise self.err(f"unexpected {self.cur().text!r} in a part",
                               suggestion="a part contains lanes only "
                                          "(harm/notes/voices/bend/press/...)")
        self._check_alignment(part.lanes, f"part {part.name!r}")
        self.doc.parts[part.name] = part
        return part

    def parse_stave(self) -> Stave:
        kw = self.eat()
        if self.cur().kind != "ident":
            raise self.err("stave needs a name",
                           suggestion="e.g. 'stave lead { notes | 0 2 | }'")
        name_tok = self.eat()
        self.skip_nl()
        self.expect("punct", "{", "to open the stave body")
        st = Stave(name=name_tok.text, pos=self.pos(kw))
        self._lane_seen = set()
        while True:
            self.skip_nl()
            if self.at("punct", "}"):
                self.eat()
                break
            t = self.cur()
            if t.kind == "eof":
                raise self.err(f"unclosed '{{' in stave {st.name!r}", kw,
                               "add the matching '}'")
            if t.kind == "lane":
                self._add_lane(st.lanes, self.parse_lane())
                continue
            if t.kind == "ident":
                self._stave_statement(st)
                continue
            raise self.err(f"unexpected {t.text!r} in stave {st.name!r}",
                           suggestion="expected a lane, 'play', 'feel', "
                                      "'gesture', 'voicing', 'channelgroup' or 'after'")
        self._check_alignment(st.lanes, f"stave {st.name!r}")
        self.doc.staves.append(st)
        return st

    def _stave_statement(self, st: Stave) -> None:
        t = self.eat()
        word = t.text
        if word == "channelgroup":
            if self.cur().kind != "number":
                raise self.err("'channelgroup' expects a number", t,
                               "e.g. 'channelgroup 1'")
            st.options["channelgroup"] = int(float(self.eat().text))
            return
        if word == "after":
            if self.cur().kind != "ident":
                raise self.err("'after' expects a stave name", t,
                               "e.g. 'after intro'")
            st.options["after"] = self.eat().text
            return
        if word in ("feel", "voicing"):
            if self.cur().kind != "ident":
                raise self.err(f"'{word}' expects a name", t,
                               f"e.g. '{word} loose'")
            nm = self.eat().text
            if self.at("op", "=") or self.at("punct", "{"):
                # a definition written inside the stave: rewind and handle it
                self.i -= 2
                (self.parse_feel_def if word == "feel" else self.parse_voicing_def)()
                st.options[word] = nm
                return
            st.options[word] = nm
            return
        if word == "gesture":
            if self.cur().kind != "ident":
                raise self.err("'gesture' expects a name", t,
                               "e.g. 'gesture cry'")
            nm = self.eat().text
            if self.at("op", "=") or self.at("punct", "("):
                self.i -= 2
                self.parse_gesture_def()
                return
            st.options["gesture"] = nm
            return
        if word == "play":
            st.statements.append(self._play_stmt(t))
            return
        if word in LANE_NAMES or re.fullmatch(r"cc\d+", word):
            raise self.err(f"lane {word!r} needs a body", t,
                           f"write '{word} | ... |'")
        raise self.err(f"unknown statement {word!r} in stave {st.name!r}", t,
                       _suggest(word, tuple(LANE_NAMES) + (
                           "play", "feel", "gesture", "voicing",
                           "channelgroup", "after")))

    def _play_stmt(self, kw: Token) -> PlayStmt:
        if self.cur().kind != "ident":
            raise self.err("'play' expects a part name", kw,
                           "e.g. 'play hook'")
        part_tok = self.eat()
        transforms: list[Call] = []
        while self.at("op", ">>"):
            self.eat()
            self.skip_nl()
            if self.cur().kind != "ident":
                raise self.err("expected a phrase transform after '>>'",
                               suggestion="e.g. 'play hook >> transpose(3) >> retro'")
            ntok = self.eat()
            args, kwargs = ([], {})
            if self.at("punct", "("):
                args, kwargs = self.parse_args()
            transforms.append(Call(name=ntok.text, args=args, kwargs=kwargs,
                                   pos=self.pos(ntok)))
        return PlayStmt(part=part_tok.text, transforms=transforms,
                        pos=self.pos(kw))

    # ==================================================================
    # lanes
    # ==================================================================
    def parse_lane(self) -> Lane:
        head = self.eat()
        lane = Lane(name=head.text, pos=self.pos(head))
        while True:
            t = self.cur()
            if t.kind == "laneopt":
                self._lane_option(lane, t)
                self.eat()
                continue
            if t.kind == "lanevoice":
                if not t.text:
                    raise self.err("'@' needs a voice name", t,
                                   "e.g. 'press@lead | /^\\ |'")
                lane.voice = t.text
                self.eat()
                continue
            break
        items: list[Token] = []
        while self.cur().kind in ("bar", "chunk", "gap"):
            items.append(self.eat())
        if self.cur().kind == "newline":
            self.eat()

        segments: list[list[Token]] = [[]]
        for t in items:
            if t.kind == "bar":
                segments.append([])
            else:
                segments[-1].append(t)
        if segments and not [t for t in segments[0] if t.kind == "chunk"] \
                and len(segments) > 1:
            segments.pop(0)
        if len(segments) > 1 and not [t for t in segments[-1] if t.kind == "chunk"] \
                and not segments[-1]:
            segments.pop()
        if not segments:
            raise self.err(f"lane {lane.name!r} has no content", head,
                           f"write '{lane.name} | ... |'")

        kind = self._lane_kind(lane.name, head)
        key = (lane.name, lane.voice)
        # LEAD RULING (round 3): repeating a lane inside a stave is the documented way to
        # write a long piece as readable blocks of bars -- harm/notes/bend/press for bars
        # 1-4, then the same lanes again for bars 5-8, columns still aligned.  It appends
        # bars and is silent.  Genuine misalignment is caught by _check_alignment, which
        # compares bar and anchor counts against the notes lane.
        self._lane_seen.add(key)
        sticky = _Sticky()
        for seg in segments:
            bpos = self.pos(seg[0]) if seg else self.pos(head)
            bar = Bar(pos=bpos)
            bar.slots = self._bar_slots(kind, lane, seg, sticky)
            lane.bars.append(bar)
        return lane

    def _add_lane(self, lanes: list[Lane], lane: Lane) -> None:
        """Add a lane, merging a repeat of the same lane into it.

        LEAD RULING (round 3): writing a lane a second time inside one stave is the
        documented way to lay a long piece out as readable blocks of bars, keeping the
        glyph columns aligned.  It must genuinely *append bars* to the same lane -- the
        old behaviour created a second parallel lane, so the later bars were silently
        stacked on top of bar 1 instead of following it.  Options must match, since two
        different `!range=` values cannot describe one lane; if they differ we keep the
        lanes separate and say so.
        """
        def _opt_key(opts: dict) -> dict:
            # Option values are AST nodes carrying their own source Pos, so two textually
            # identical options never compare equal.  Compare them by value only.
            def strip(v):
                if hasattr(v, "__dataclass_fields__"):
                    return (type(v).__name__,
                            tuple(sorted((f, strip(getattr(v, f)))
                                         for f in v.__dataclass_fields__
                                         if f != "pos")))
                if isinstance(v, (list, tuple)):
                    return tuple(strip(x) for x in v)
                if isinstance(v, dict):
                    return tuple(sorted((k, strip(x)) for k, x in v.items()))
                return v
            return {k: strip(v) for k, v in opts.items()}

        for prev in lanes:
            if prev.name != lane.name or prev.voice != lane.voice:
                continue
            if _opt_key(prev.options) == _opt_key(lane.options):
                prev.bars.extend(lane.bars)
                return
            def show(opts: dict) -> str:
                def one(v):
                    n = getattr(v, "value", v)
                    u = getattr(v, "unit", None) or ""
                    return f"{n:g}{u}" if isinstance(n, float) else f"{n}{u}"
                return ", ".join(f"{k}={one(v)}" for k, v in sorted(opts.items())) \
                    or "no options"

            self.warn(
                f"lane {lane.name!r} is repeated with different options "
                f"({show(lane.options)} vs {show(prev.options)}), so it stays a "
                f"separate lane starting again at bar 1 instead of continuing the "
                f"first; make the options match to join them",
                lane.pos.line, lane.pos.col, kind="duplicate-lane")
            break
        lanes.append(lane)

    def _lane_kind(self, name: str, tok: Token) -> str:
        if name in ("harm", "notes", "voices"):
            return name
        if name in ("bend", "press", "timbre", "amp", "pan") or \
                re.fullmatch(r"cc\d+", name):
            return "curve"
        raise self.err(f"unknown lane {name!r}", tok,
                       _suggest(name, tuple(LANE_NAMES) + ("cc74",)))

    def _lane_option(self, lane: Lane, tok: Token) -> None:
        text = tok.text
        if not text:
            raise self.err("empty lane option", tok,
                           "options look like '!range=7st' or '!shape=ease'")
        if "=" not in text:
            raise self.err(f"lane option {text!r} needs a value", tok,
                           f"write '!{text}=<value>' — e.g. '!shape=ease'")
        key, _, val = text.partition("=")
        if not key:
            raise self.err("lane option has no name", tok,
                           "options look like '!range=7st'")
        if key == "shape" and val not in _SHAPES:
            raise self.err(f"unknown shape {val!r}", tok, _suggest(val, _SHAPES))
        if key == "time" and val not in ("bar", "note"):
            raise self.err(f"unknown lane time mode {val!r}", tok,
                           _suggest(val, ("bar", "note")))
        base = key.split("@", 1)[0]
        if base not in _LANE_OPTION_KEYS:
            # R3 fix 4: an unrecognised lane option used to be silently
            # dropped, so a typo (or `!oct=5`, which nothing reads) changed
            # nothing and said nothing.
            self.warn(
                f"lane option {base!r} on lane {lane.name!r} is not recognised "
                "and has no effect; known options are "
                + ", ".join(sorted(_LANE_OPTION_KEYS)),
                tok.line, tok.col, kind="unknown-lane-option")
        try:
            v, unit = _parse_num_text(val)
            value: Any = Num(v, unit, pos=self.pos(tok))
        except ValueError:
            value = val
        lane.options[key] = value

    # -- bars ------------------------------------------------------------
    def _bar_slots(self, kind: str, lane: Lane, seg: list[Token],
                   sticky: _Sticky) -> list[Slot]:
        chunks = [t for t in seg if t.kind == "chunk"]
        if not chunks:
            return []
        if kind == "voices":
            return self._voices_bar(chunks, sticky)
        slots: list[Slot] = []
        if kind == "curve":
            inner = self._trim_gaps(seg)
            for t in inner:
                # LEAD RULING (round 3): whitespace between curve glyphs is a separator
                # for column alignment, never an anchor.  Emitting one empty slot per
                # space made a lane written under 8 notes count 15 anchors and warn about
                # its own alignment.  Write `.` for "no data here".
                if t.kind != "gap":
                    slots.extend(self._curve_chunk(lane, t))
            return slots
        for t in chunks:
            if kind == "harm":
                slots.extend(self._harm_chunk(t))
            else:
                slots.extend(self._notes_chunk(t, sticky))
        return slots

    @staticmethod
    def _trim_gaps(seg: list[Token]) -> list[Token]:
        a, b = 0, len(seg)
        while a < b and seg[a].kind == "gap":
            a += 1
        while b > a and seg[b - 1].kind == "gap":
            b -= 1
        return seg[a:b]

    # ==================================================================
    # notes lane (SPEC §5)
    # ==================================================================
    def _notes_chunk(self, tok: Token, sticky: _Sticky) -> list[Slot]:
        return self._note_tokens(tok.text, tok.line, tok.col, sticky)

    def _note_tokens(self, text: str, line: int, col: int,
                     sticky: _Sticky) -> list[Slot]:
        out: list[Slot] = []
        for sub, off in _split_ws(text):
            out.extend(self._one_note_token(sub, line, col + off, sticky))
        return out

    def _one_note_token(self, text: str, line: int, col: int,
                        sticky: _Sticky) -> list[Slot]:
        body, rep = self._split_repeat(text, line, col)
        if body == "!reset":
            sticky.reset()
            return []
        slot = self._note_core(body, line, col, sticky)
        if slot is None:
            return []
        if rep > 1:
            slot.repeat = rep
            return [slot] + [self._copy_slot(slot, rep) for _ in range(rep - 1)]
        return [slot]

    def _split_repeat(self, text: str, line: int, col: int) -> tuple[str, int]:
        """``x*3`` -> ("x", 3).  ``*`` inside brackets is left alone."""
        depth = 0
        for i, c in enumerate(text):
            if c in _OPEN:
                depth += 1
            elif c in _CLOSE:
                depth = max(0, depth - 1)
            elif c == "*" and depth == 0 and i > 0:
                num = text[i + 1:]
                if not num.isdigit():
                    raise self.err_at(
                        f"repeat '*' needs a count in {text!r}", line, col + i,
                        text, "write 'token*3' to repeat a token over 3 slots")
                n = int(num)
                if n < 1:
                    raise self.err_at("repeat count must be >= 1", line,
                                      col + i, text, "e.g. 'x*3'")
                return text[:i], n
        return text, 1

    @staticmethod
    def _copy_slot(slot: Slot, rep: int) -> Slot:
        import copy
        c = copy.deepcopy(slot)
        c.repeat = rep
        return c

    def _note_core(self, text: str, line: int, col: int,
                   sticky: _Sticky) -> Optional[Slot]:
        if not text:
            return None
        pos = Pos(line, col, self.path)
        # structural forms first
        if text.startswith("[:"):
            return self._repeat_group(text, line, col, sticky, "notes")
        if text[0] in "[<(":
            close = _match_bracket(text, 0)
            if close == -1:
                raise self.err_at(
                    f"unbalanced {text[0]!r} in {text!r}", line, col, text,
                    f"close it with {_OPEN[text[0]]!r}")
            inner = text[1:close]
            children = self._note_tokens(inner, line, col + 1, sticky)
            if not children:
                raise self.err_at(f"empty group {text!r}", line, col, text,
                                  "put at least one token inside")
            if text[0] == "[":
                slot = Slot(kind="group", children=children, pos=pos)
            elif text[0] == "<":
                slot = Slot(kind="alt", children=children, pos=pos)
            else:
                pitches: list[PitchTok] = []
                for ch in children:
                    if ch.kind != "note":
                        raise self.err_at(
                            "a '( ... )' chord may only contain pitches", line,
                            col, text, "use '[ ... ]' for a subdivided group")
                    pitches.extend(ch.pitches)
                slot = Slot(kind="note", pitches=pitches,
                            velocity=sticky.velocity, gate=sticky.gate, pos=pos)
            tail = text[close + 1:]
            if tail:
                leftover, decos = self._split_decorations(
                    tail, line, col + close + 1, allow_empty_core=True)
                if leftover:
                    raise self.err_at(
                        f"unexpected {leftover!r} after {text[:close+1]!r}",
                        line, col + close + 1, tail,
                        "decorations are !gesture :v90 %50 ' , ?")
                self._apply_decorations(slot, decos, sticky, line, col)
            return slot

        core, decos = self._split_decorations(text, line, col)
        if core == ".":
            slot = Slot(kind="rest", pos=pos)
        elif core == "-":
            slot = Slot(kind="tie", pos=pos)
        elif core == "=":
            slot = Slot(kind="retrig", pos=pos)
        else:
            pitch = self._pitch_tok(core, line, col, sticky)
            slot = Slot(kind="note", pitches=[pitch], pos=pos)
        if slot.kind == "note":
            slot.velocity = sticky.velocity
            slot.gate = sticky.gate
        self._apply_decorations(slot, decos, sticky, line, col)
        if slot.kind == "note":
            slot.velocity = sticky.velocity if slot.velocity is None else slot.velocity
            slot.gate = sticky.gate if slot.gate is None else slot.gate
        return slot

    def _repeat_group(self, text: str, line: int, col: int, sticky: _Sticky,
                      mode: str) -> Slot:
        """``[: a b :4]`` — expand the fragment 4 times (SPEC §3.1)."""
        if not text.endswith("]"):
            raise self.err_at(f"unclosed '[:' in {text!r}", line, col, text,
                              "close the repeat with ':N]', e.g. '[: 0 2 :4]'")
        inner = text[2:-1]
        m = re.search(r":(\d+)$", inner)
        if not m:
            raise self.err_at(f"repeat block {text!r} needs ':N]'", line, col,
                              text, "e.g. '[: 0 2 3 :4]'")
        count = int(m.group(1))
        if count < 1:
            raise self.err_at("repeat count must be >= 1", line, col, text,
                              "e.g. '[: 0 2 :4]'")
        frag = inner[:m.start()]
        children: list[Slot] = []
        for _ in range(count):
            if mode == "notes":
                children.extend(self._note_tokens(frag, line, col + 2, sticky))
            else:
                children.extend(self._curve_text(frag, line, col + 2, mode))
        if not children:
            raise self.err_at(f"empty repeat block {text!r}", line, col, text,
                              "put tokens between '[:' and ':N]'")
        return Slot(kind="group", children=children, repeat=count,
                    pos=Pos(line, col, self.path))

    _DECO_RE = re.compile(r"(!\w[\w-]*(?:\([^)]*\))?|:v-?\d+|%\d+(?:\.\d+)?|'|,|\?\d*)")

    def _split_decorations(self, text: str, line: int, col: int,
                           allow_empty_core: bool = False,
                           ) -> tuple[str, list[tuple[str, int]]]:
        decos: list[tuple[str, int]] = []
        i = len(text)
        while True:
            found = None
            for m in self._DECO_RE.finditer(text[:i]):
                if m.end() == i:
                    found = m
            if found is None or (found.start() == 0 and not allow_empty_core):
                break
            decos.insert(0, (found.group(0), col + found.start()))
            i = found.start()
        return text[:i], decos

    def _apply_decorations(self, slot: Slot, decos: list[tuple[str, int]],
                           sticky: _Sticky, line: int, col: int) -> None:
        for text, dcol in decos:
            if text.startswith(":v"):
                v = int(text[2:])
                if not 0 <= v <= 127:
                    raise self.err_at(
                        f"velocity {v} out of range", line, dcol, text,
                        "velocity is 0-127, e.g. ':v90'")
                sticky.velocity = v
                slot.velocity = v
            elif text.startswith("%"):
                g = float(text[1:]) / 100.0
                if g <= 0:
                    raise self.err_at("gate must be > 0", line, dcol, text,
                                      "e.g. '%50' for half the slot")
                sticky.gate = g
                slot.gate = g
            elif text == "'":
                slot.accent += 0.15
            elif text == ",":
                slot.accent -= 0.15
            elif text.startswith("?"):
                slot.probability = 0.5 if text == "?" else float(text[1:]) / 100.0
                if not 0.0 <= slot.probability <= 1.0:
                    raise self.err_at("probability must be 0-100", line, dcol,
                                      text, "e.g. '?25' for 25%")
            elif text.startswith("!"):
                if text == "!reset":
                    sticky.reset()
                    slot.velocity = None
                    slot.gate = None
                    continue
                slot.gestures.append(
                    self._expr_from_string(text[1:], line, dcol + 1))

    def _pitch_tok(self, text: str, line: int, col: int,
                   sticky: _Sticky) -> PitchTok:
        pos = Pos(line, col, self.path)
        if text.startswith("@"):
            name = text[1:]
            if name not in _ANCHORS:
                raise self.err_at(f"unknown anchor '@{name}'", line, col, text,
                                  _suggest(name, _ANCHORS))
            return PitchTok(kind="anchor", anchor=text, pos=pos)
        if text.startswith("~"):
            rest = text[1:]
            if not rest.isdigit():
                raise self.err_at(f"chord degree {text!r} needs a number", line,
                                  col, text, "e.g. '~3' for the chord's third")
            deg = int(rest)
            if deg not in (1, 3, 5, 7, 9, 11, 13):
                raise self.err_at(f"chord degree {deg} is not a chord tone",
                                  line, col, text,
                                  "use ~1 ~3 ~5 ~7 ~9 ~11 ~13")
            return PitchTok(kind="chordtone", value=deg, pos=pos)
        m = _ABS_PITCH_RE.match(text)
        if m:
            midi = _note_name_to_midi(text)
            assert midi is not None
            if not 0 <= midi <= 127:
                raise self.err_at(f"absolute pitch {text!r} is outside MIDI 0-127",
                                  line, col, text, "use octaves -1..9")
            acc = (m.group(2) or "")
            return PitchTok(kind="absolute", midi=midi,
                            accidental=acc.count("#") - acc.count("b"), pos=pos)
        # degree with sticky octave prefix and accidental
        i = 0
        up = down = 0
        while i < len(text) and text[i] in "^_":
            if text[i] == "^":
                up += 1
            else:
                down += 1
            i += 1
        if up or down:
            sticky.octave = up - down
        acc = 0
        if i < len(text) and text[i] in "#b":
            acc = 1 if text[i] == "#" else -1
            i += 1
        rest = text[i:]
        if not re.fullmatch(r"-?\d+", rest):
            if self._DECO_RE.fullmatch(text):
                raise self.err_at(
                    f"decoration {text!r} is not attached to a note", line, col,
                    text, "write it directly after the note token, "
                          f"e.g. '0{text}'")
            hint = "scale degrees are 0-8 (0 = tonic); absolute pitches look " \
                   "like 'C4'; chord tones like '~3'; rest '.', tie '-'"
            raise self.err_at(f"{text!r} is not a note token", line, col, text,
                              hint)
        return PitchTok(kind="degree", value=int(rest), accidental=acc,
                        octave=sticky.octave, pos=pos)

    # ==================================================================
    # harm lane (SPEC §4)
    # ==================================================================
    def _harm_chunk(self, tok: Token) -> list[Slot]:
        body, rep = self._split_repeat(tok.text, tok.line, tok.col)
        slot = self._harm_core(body, tok.line, tok.col)
        if rep > 1:
            return [slot] + [self._copy_slot(slot, rep) for _ in range(rep - 1)]
        return [slot]

    def _harm_core(self, text: str, line: int, col: int) -> Slot:
        pos = Pos(line, col, self.path)
        if text.startswith("[:"):
            return self._repeat_group(text, line, col, _Sticky(), "harm")
        if text == "-":
            return Slot(kind="chord", chord=ChordTok(sustain=True, pos=pos),
                        pos=pos)
        if text == ".":
            return Slot(kind="chord", chord=ChordTok(silent=True, pos=pos),
                        pos=pos)
        if text.startswith("<"):
            close = _match_bracket(text, 0)
            if close != len(text) - 1:
                raise self.err_at(f"unbalanced '<' in {text!r}", line, col,
                                  text, "close it with '>'")
            children = [self._harm_core(s, line, col + 1 + o)
                        for s, o in _split_ws(text[1:close])]
            return Slot(kind="alt", children=children, pos=pos)
        if text.startswith("["):
            close = _match_bracket(text, 0)
            if close != len(text) - 1:
                raise self.err_at(f"unbalanced '[' in {text!r}", line, col,
                                  text, "close it with ']'")
            children = [self._harm_core(s, line, col + 1 + o)
                        for s, o in _split_ws(text[1:close])]
            return Slot(kind="group", children=children, pos=pos)
        if text.startswith("{"):
            close = _match_bracket(text, 0)
            if close != len(text) - 1:
                raise self.err_at(f"unbalanced '{{' in {text!r}", line, col,
                                  text, "close the pitch set with '}'")
            items = [s for s, _o in _split_ws(text[1:close])]
            if not items:
                raise self.err_at("empty pitch set", line, col, text,
                                  "e.g. '{0 3 7 10}' or '{C4 Eb4 G4}'")
            absolute = _ABS_PITCH_RE.match(items[0]) is not None
            vals: list[int] = []
            for it in items:
                if absolute:
                    midi = _note_name_to_midi(it)
                    if midi is None:
                        raise self.err_at(
                            f"{it!r} is not an absolute pitch", line, col, text,
                            "an absolute pitch set looks like '{C4 Eb4 G4 Bb4}'")
                    vals.append(midi)
                else:
                    if not re.fullmatch(r"-?\d+", it):
                        self.soft_at(
                            f"{it!r} is not a semitone offset", line, col, text,
                            "a relative pitch set looks like '{0 3 7 10 14}'",
                            recovery="dropped from the pitch set")
                        continue
                    vals.append(int(it))
            return Slot(kind="chord",
                        chord=ChordTok(pitchset=vals, pitchset_absolute=absolute,
                                       pos=pos), pos=pos)

        sym, bass = self._split_bass(text, line, col)
        if not sym:
            raise self.err_at(f"chord symbol missing in {text!r}", line, col,
                              text, "e.g. 'i9', 'V7alt', 'Cm9/E'")
        ct = ChordTok(bass=bass, pos=pos)
        if _ROMAN_RE.match(sym):
            ct.roman = sym
        elif re.match(r"^[A-G]", sym):
            ct.absolute = sym
        else:
            self.soft_at(
                f"{sym!r} is not a chord symbol", line, col, text,
                "roman numerals (i ii III iv V), absolute symbols (Cm9, Ab^7) "
                "or a pitch set ({0 3 7}) — see SPEC §4",
                recovery="sustaining the previous chord instead")
            return Slot(kind="chord", chord=ChordTok(sustain=True, pos=pos),
                        pos=pos)
        return Slot(kind="chord", chord=ct, pos=pos)

    def _split_bass(self, text: str, line: int, col: int) -> tuple[str, Optional[str]]:
        """Separate a slash bass from the symbol.

        ``Dm7/A`` -> bass "A"; ``/3`` -> bass "3"; ``V/ii`` (secondary dominant)
        and ``C6/9`` (extension) stay part of the symbol.
        """
        idx = text.rfind("/")
        if idx <= 0:
            return text, None
        head, tail = text[:idx], text[idx + 1:]
        if re.fullmatch(r"[A-G](#|b)?", tail):
            return head, tail
        if re.fullmatch(r"[357]", tail) and not head.endswith("6"):
            return head, tail
        return text, None

    # ==================================================================
    # voices lane (SPEC §6)
    # ==================================================================
    def _voices_bar(self, chunks: list[Token], sticky: _Sticky) -> list[Slot]:
        braced = [t for t in chunks if t.text.startswith("{")]
        if braced:
            return [self._voices_block(t) for t in braced]
        slot = Slot(kind="voices", pos=self.pos(chunks[0]))
        for t in chunks:
            name, sub = self._voice_entry(t.text, t.line, t.col)
            slot.voices[name] = sub
        return [slot]

    def _voices_block(self, tok: Token) -> Slot:
        text = tok.text
        close = _match_bracket(text, 0)
        if close == -1:
            raise self.err_at("unclosed '{' in voices block", tok.line, tok.col,
                              text, "close the block with '}'")
        inner = text[1:close]
        slot = Slot(kind="voices", pos=self.pos(tok))
        offset = 1
        for part in inner.split(";"):
            if not part.strip():
                offset += len(part) + 1
                continue
            name, sub = self._voice_entry(part.strip(), tok.line,
                                          tok.col + offset)
            if name in slot.voices:
                self.warn(f"voice {name!r} appears twice in one voices block",
                          tok.line, tok.col, kind="duplicate-voice")
            slot.voices[name] = sub
            offset += len(part) + 1
        if not slot.voices:
            raise self.err_at("empty voices block", tok.line, tok.col, text,
                              "e.g. '{ bass: 0 . 2 - ; lead: 7 - 6 5 }'")
        return slot

    def _voice_entry(self, text: str, line: int, col: int) -> tuple[str, Slot]:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*", text)
        if not m:
            raise self.err_at(f"{text!r} is not a voice entry", line, col, text,
                              "voice entries look like 'bass: 0 . 2 -'")
        name = m.group(1)
        body = text[m.end():]
        sticky = _Sticky()
        slots = self._note_tokens(body, line, col + m.end(), sticky)
        if not slots:
            raise self.err_at(f"voice {name!r} has no notes", line, col, text,
                              f"write '{name}: 0 . 2 -'")
        if len(slots) == 1:
            return name, slots[0]
        return name, Slot(kind="group", children=slots,
                          pos=Pos(line, col, self.path))

    # ==================================================================
    # curve lanes (SPEC §7)
    # ==================================================================
    def _curve_chunk(self, lane: Lane, tok: Token) -> list[Slot]:
        return self._curve_text(tok.text, tok.line, tok.col, lane.name)

    def _curve_text(self, text: str, line: int, col: int,
                    lane_name: str) -> list[Slot]:
        out: list[Slot] = []
        i = 0
        n = len(text)
        while i < n:
            c = text[i]
            pos = Pos(line, col + i, self.path)
            if c.isspace():
                # LEAD RULING (round 3): on a curve lane whitespace is ONLY a
                # separator.  It used to emit an "empty" slot, which meant a lane
                # written to column-align with 8 notes counted 15 anchors (8
                # glyphs + 7 separators) and warned about its own alignment.  To
                # say "no data here" write `.`, matching the notes lane's rest.
                i += 1
                continue
            if c == ".":
                out.append(Slot(kind="empty", pos=pos))
                i += 1
                continue
            if c in "_-^/\\x" or (c in "vV" and not _ident_ahead(text, i)):
                # `_` is the lane REST value and `v`/`V` the lane minimum
                # (SPEC §7 amended).  A `v` that begins a longer identifier —
                # `vibr(...)` — is an inline gesture call, not a glyph, which is
                # what `_ident_ahead` disambiguates.
                slot = Slot(kind="glyph", glyph=c, pos=pos)
                i += 1
            elif c.isdigit():
                slot = Slot(kind="glyph", glyph=c, glyph_arg=float(c), pos=pos)
                i += 1
            elif c == "~":
                j = i + 1
                while j < n and text[j].isdigit():
                    j += 1
                arg = float(text[i + 1:j]) if j > i + 1 else None
                slot = Slot(kind="glyph", glyph="~", glyph_arg=arg, pos=pos)
                i = j
            elif c == ">":
                if lane_name != "bend":
                    raise self.err_at(
                        f"'>' harmonic target is only valid on 'bend', not "
                        f"{lane_name!r}", line, col + i, ">",
                        "move the '>' to a bend lane (SPEC §7)")
                tgt, i = self._curve_target(text, i, line, col)
                slot = Slot(kind="glyph", glyph=">", target=tgt, pos=pos)
            elif c in "[(<":
                if text.startswith("[:", i):
                    close = _match_bracket(text, i)
                    if close == -1:
                        raise self.err_at(f"unclosed '[:' in {text!r}", line,
                                          col + i, text[i:],
                                          "close the repeat with ':N]'")
                    slot = self._repeat_group(text[i:close + 1], line, col + i,
                                              _Sticky(), lane_name)
                    i = close + 1
                else:
                    close = _match_bracket(text, i)
                    if close == -1:
                        raise self.err_at(
                            f"unbalanced {c!r} in {text!r}", line, col + i,
                            text[i:], f"close it with {_OPEN[c]!r}")
                    children = self._curve_text(text[i + 1:close], line,
                                                col + i + 1, lane_name)
                    if not children:
                        raise self.err_at(f"empty group {text[i:close+1]!r}",
                                          line, col + i, text[i:close + 1],
                                          "put at least one glyph inside")
                    slot = Slot(kind="alt" if c == "<" else "group",
                                children=children, pos=pos)
                    i = close + 1
            elif c.isalpha() or c == "_":
                m = re.match(r"[A-Za-z_][A-Za-z0-9_-]*", text[i:])
                assert m is not None
                name = m.group(0)
                j = i + m.end()
                if j < n and text[j] == "(":
                    close = _match_bracket(text, j)
                    if close == -1:
                        raise self.err_at(
                            f"unclosed '(' in gesture call {name!r}", line,
                            col + j, text[i:], "add the matching ')'")
                    expr = self._expr_from_string(text[i:close + 1], line,
                                                  col + i)
                    slot = Slot(kind="gesture", expr=expr, pos=pos)
                    i = close + 1
                else:
                    self.soft_at(
                        f"{name!r} is not a curve glyph", line, col + i, name,
                        "an inline gesture needs arguments, e.g. "
                        f"'{name}(0.3)'; " + gest.GLYPH_HINT,
                        recovery="skipped, so this slot carries no curve data")
                    i += len(name)
                    continue
            else:
                self.soft_at(
                    f"{c!r} is not a curve glyph", line, col + i, c,
                    gest.GLYPH_HINT,
                    recovery="skipped, so this slot carries no curve data")
                i += 1
                continue
            # optional '*n' repeat
            if i < n and text[i] == "*":
                j = i + 1
                while j < n and text[j].isdigit():
                    j += 1
                if j == i + 1:
                    raise self.err_at("repeat '*' needs a count", line, col + i,
                                      "*", "e.g. 'x*3'")
                rep = int(text[i + 1:j])
                if rep < 1:
                    raise self.err_at("repeat count must be >= 1", line,
                                      col + i, "*", "e.g. 'x*3'")
                slot.repeat = rep
                out.append(slot)
                for _ in range(rep - 1):
                    out.append(self._copy_slot(slot, rep))
                i = j
                continue
            out.append(slot)
        return out

    def _curve_target(self, text: str, i: int, line: int,
                      col: int) -> tuple[Target, int]:
        pos = Pos(line, col + i, self.path)
        j = i + 1
        if j < len(text) and text[j] == "+":
            return Target(kind="step", degree=1, pos=pos), j + 1
        if j < len(text) and text[j] == "-":
            return Target(kind="step", degree=-1, pos=pos), j + 1
        if j < len(text) and text[j] == "|":
            return Target(kind="next", pos=pos), j + 1
        # `>root` is the spelled-out form of `>1`: glide into the next chord's root.
        # It is documented, so it has to parse.
        for word, deg in (("root", 1), ("third", 3), ("fifth", 5), ("seventh", 7)):
            if text[j:j + len(word)] == word:
                return Target(kind="degree", degree=deg, pos=pos), j + len(word)
        k = j
        while k < len(text) and text[k].isdigit():
            k += 1
        if k > j:
            deg = int(text[j:k])
            if deg not in (1, 3, 5, 7, 9, 11, 13):
                raise self.err_at(
                    f"'>{deg}' is not a chord degree", line, col + i,
                    text[i:k], "targets are >3 >5 >7 >9 (or >11 >13)")
            return Target(kind="degree", degree=deg, pos=pos), k
        return Target(kind="guide", pos=pos), j

    # ==================================================================
    # lane alignment (SPEC §12 as amended — warning, never an error)
    #
    # A curve lane's item count is its ANCHOR count for the bar (SPEC §3.1: a
    # contiguous glyph run is one item whose characters are anchors).  When that
    # count is not an integer multiple or divisor of the bar's `notes` slot
    # count, the lane is resampled and we say so, naming both counts.  Exact
    # ratios (2 anchors over 4 notes, 8 over 4) stay silent.
    # ==================================================================
    @staticmethod
    def _slot_count(slots: list[Slot]) -> int:
        return len(slots)

    @staticmethod
    def _is_curve_lane_name(name: str) -> bool:
        return name in ("bend", "press", "timbre", "amp", "pan") \
            or bool(re.fullmatch(r"cc\d+", name or ""))

    def _check_alignment(self, lanes: list[Lane], where: str) -> None:
        if len(lanes) < 2:
            return
        ref = None
        for want in ("notes", "voices", "harm"):
            for ln in lanes:
                if ln.name == want:
                    ref = ln
                    break
            if ref is not None:
                break
        if ref is None:
            ref = lanes[0]
        nbars = max(len(ln.bars) for ln in lanes)
        for ln in lanes:
            # LEAD RULING (round 3): a shorter lane whose bar count divides the reference's
            # cycles over it -- a one-bar `press` figure under an eight-bar progression is
            # an idiom, not a mistake.  Warn only when the counts do not divide, which is
            # the case that really loses bars.
            nb, rb = len(ln.bars), len(ref.bars)
            if ln is not ref and ln.bars and nb != rb \
                    and max(nb, rb) % min(nb, rb) != 0:
                self.warn(
                    f"in {where}, lane {ln.name!r} has {nb} bars but lane "
                    f"{ref.name!r} has {rb}; neither divides the other, so lane "
                    f"{ln.name!r} cannot cycle evenly",
                    ln.pos.line, ln.pos.col, kind="lane-bars")
        for b in range(nbars):
            if b >= len(ref.bars):
                continue
            rc = self._slot_count(ref.bars[b].slots)
            if rc == 0:
                continue
            for ln in lanes:
                if ln is ref or b >= len(ln.bars):
                    continue
                c = self._slot_count(ln.bars[b].slots)
                if c == 0 or c == rc:
                    continue
                hi, lo = max(c, rc), min(c, rc)
                if hi % lo == 0:
                    continue
                bpos = ln.bars[b].pos
                curve = self._is_curve_lane_name(ln.name)
                if curve and str(ln.options.get("time", "bar")) == "note":
                    # `!time=note` re-normalises the whole lane onto each note's
                    # own lifetime (SPEC §7.1), so bar-column alignment is not
                    # what the lane means and a count mismatch is not a defect.
                    continue
                unit = "anchors" if curve else "slots"
                self.warn(
                    f"in {where}, bar {b + 1}: lane {ln.name!r} has {c} {unit} "
                    f"but lane {ref.name!r} has {rc} slots; {c} is not an "
                    f"integer multiple or divisor of {rc}, so lane {ln.name!r} "
                    f"is resampled",
                    bpos.line, bpos.col, kind="lane-align")

    # ==================================================================
    # gesture expressions (SPEC §8)
    # ==================================================================
    def _expr_from_string(self, text: str, line: int, col: int) -> Any:
        from .lex import _lex_generic  # local: same piece
        toks: list[Token] = []
        _lex_generic(text, line, toks)
        # shift columns so diagnostics point at the real source position
        toks = [Token(t.kind, t.text, t.line, t.col + col - 1) for t in toks]
        toks.append(Token("eof", "", line, col + len(text)))
        sub = Parser(toks, self.src, self.path)
        sub.doc = self.doc
        expr = sub.parse_expr()
        if sub.cur().kind != "eof":
            raise sub.err(f"unexpected {sub.cur().text!r} in gesture expression",
                          suggestion="check the parentheses and operators")
        return expr

    # -- precedence ladder ----------------------------------------------
    def parse_expr(self) -> Any:
        return self._parse_par()

    def _op_ahead(self, kind: str, texts: tuple[str, ...]) -> Optional[int]:
        """Index of the next *kind* token in *texts*, skipping newlines."""
        j = self.i
        while j < len(self.toks) and self.toks[j].kind == "newline":
            j += 1
        if j < len(self.toks) and self.toks[j].kind == kind \
                and self.toks[j].text in texts:
            return j
        return None

    def _parse_par(self) -> Any:
        node = self._parse_seq()
        while True:
            j = self._op_ahead("op", ("|",))
            if j is None:
                return node
            self.i = j
            op = self.eat()
            self.skip_nl()
            rhs = self._parse_seq()
            node = BinOp(op="par", lhs=node, rhs=rhs, pos=self.pos(op))

    def _parse_seq(self) -> Any:
        node = self._parse_add()
        while True:
            j = self._op_ahead("op", (">>",))
            if j is None:
                return node
            self.i = j
            op = self.eat()
            split = None
            if self.at("punct", "("):
                self.eat()
                split = self.parse_expr()
                if not self.at("punct", ")"):
                    raise self.err("unclosed '(' after '>>'",
                                   suggestion="write 'a >>(30%) b'")
                self.eat()
            self.skip_nl()
            rhs = self._parse_add()
            node = BinOp(op="seq", lhs=node, rhs=rhs, split=split,
                         pos=self.pos(op))

    def _parse_add(self) -> Any:
        node = self._parse_mul()
        while True:
            j = self._op_ahead("op", ("+", "-"))
            if j is None:
                return node
            self.i = j
            op = self.eat()
            self.skip_nl()
            rhs = self._parse_mul()
            node = BinOp(op="add" if op.text == "+" else "sub", lhs=node,
                         rhs=rhs, pos=self.pos(op))

    def _parse_mul(self) -> Any:
        node = self._parse_unary()
        while True:
            j = self._op_ahead("op", ("*",))
            if j is None:
                return node
            self.i = j
            op = self.eat()
            self.skip_nl()
            rhs = self._parse_unary()
            node = BinOp(op="scale_or_mul", lhs=node, rhs=rhs,
                         pos=self.pos(op))

    def _parse_unary(self) -> Any:
        self.skip_nl()
        if self.at("op", "-"):
            op = self.eat()
            return UnOp(op="neg", operand=self._parse_unary(), pos=self.pos(op))
        return self._parse_window()

    def _parse_window(self, allow_window: bool = True) -> Any:
        node = self._parse_postfix()
        while allow_window and self.at("op", "@"):
            op = self.eat()
            start = self._parse_postfix()
            end = None
            if self.at("op", ".."):
                self.eat()
                end = self._parse_postfix()
            node = Window(inner=node, start=start, end=end, pos=self.pos(op))
        return node

    def _parse_postfix(self) -> Any:
        node = self._parse_atom()
        while self.at("punct", "("):
            args, kwargs = self.parse_args()
            name = node.name if isinstance(node, (Ref, Call)) else None
            if name is None:
                raise self.err("only a name can be called",
                               suggestion="e.g. 'vibr(rate: 6hz)'")
            node = Call(name=name, args=args, kwargs=kwargs,
                        pos=getattr(node, "pos", Pos()))
            # a lane primitive with breakpoints records its shape kwarg
            for a in args:
                if isinstance(a, Breakpoints) and a.shape is None:
                    sh = kwargs.get("shape")
                    if isinstance(sh, str):
                        a.shape = sh
        return node

    def parse_args(self) -> tuple[list[Any], dict[str, Any]]:
        self.expect("punct", "(", "to open an argument list")
        args: list[Any] = []
        kwargs: dict[str, Any] = {}
        self.skip_nl()
        if self.at("punct", ")"):
            self.eat()
            return args, kwargs
        while True:
            self.skip_nl()
            if self.cur().kind == "eof":
                raise self.err("unclosed '(' in argument list",
                               suggestion="add the matching ')'")
            key = None
            if self.cur().kind == "ident" and self.peek(1).kind == "punct" \
                    and self.peek(1).text == ":":
                key = self.eat().text
                self.eat()
            val = self._parse_arg_value(key)
            if key is None:
                args.append(val)
            else:
                kwargs[key] = val
            self.skip_nl()
            if self.at("punct", ","):
                self.eat()
                continue
            if self.at("punct", ")"):
                self.eat()
                break
            raise self.err(f"unexpected {self.cur().text!r} in argument list",
                           suggestion="separate arguments with ',' and close "
                                      "with ')'")
        return args, kwargs

    def _arrow_ahead(self) -> bool:
        depth = 0
        j = self.i
        while j < len(self.toks):
            t = self.toks[j]
            if t.kind == "eof":
                return False
            if t.kind == "punct" and t.text in "([{":
                depth += 1
            elif t.kind == "punct" and t.text in ")]}":
                if depth == 0:
                    return False
                depth -= 1
            elif depth == 0 and t.kind == "punct" and t.text == ",":
                return False
            elif depth == 0 and t.kind == "op" and t.text == "->":
                return True
            j += 1
        return False

    def _parse_arg_value(self, key: Optional[str]) -> Any:
        if key in _STRING_KWARGS and self.cur().kind == "ident":
            tok = self.eat()
            if key == "shape" and tok.text not in _SHAPES:
                raise self.err(f"unknown shape {tok.text!r}", tok,
                               _suggest(tok.text, _SHAPES))
            return tok.text
        if self._arrow_ahead():
            return self._parse_breakpoints()
        return self.parse_expr()

    def _parse_breakpoints(self) -> Breakpoints:
        start = self.cur()
        pts: list[tuple[Any, Optional[Any]]] = []
        while True:
            self.skip_nl()
            val = self._parse_bp_value()
            at = None
            if self.at("op", "@"):
                self.eat()
                at = self._parse_postfix()
            pts.append((val, at))
            if self.at("op", "->"):
                self.eat()
                continue
            break
        if len(pts) < 2:
            raise self.err("a breakpoint list needs at least two points", start,
                           "e.g. 'bend(0 -> -0.7st -> 0)'")
        return Breakpoints(points=pts, pos=self.pos(start))

    def _parse_bp_value(self) -> Any:
        """A breakpoint value: like an expression but ``@`` means placement."""
        saved = self._parse_bp_ladder()
        return saved

    def _parse_bp_ladder(self) -> Any:
        node = self._parse_bp_mul()
        while self._op_ahead("op", ("+", "-")) is not None:
            self.i = self._op_ahead("op", ("+", "-"))  # type: ignore[assignment]
            op = self.eat()
            rhs = self._parse_bp_mul()
            node = BinOp(op="add" if op.text == "+" else "sub", lhs=node,
                         rhs=rhs, pos=self.pos(op))
        return node

    def _parse_bp_mul(self) -> Any:
        node = self._parse_bp_unary()
        while self._op_ahead("op", ("*",)) is not None:
            self.i = self._op_ahead("op", ("*",))  # type: ignore[assignment]
            op = self.eat()
            rhs = self._parse_bp_unary()
            node = BinOp(op="scale_or_mul", lhs=node, rhs=rhs, pos=self.pos(op))
        return node

    def _parse_bp_unary(self) -> Any:
        self.skip_nl()
        if self.at("op", "-"):
            op = self.eat()
            return UnOp(op="neg", operand=self._parse_bp_unary(),
                        pos=self.pos(op))
        return self._parse_window(allow_window=False)

    def _parse_atom(self) -> Any:
        self.skip_nl()
        t = self.cur()
        if t.kind == "number":
            self.eat()
            try:
                v, unit = _parse_num_text(t.text)
            except ValueError:
                raise self.err(f"bad number {t.text!r}", t,
                               "units are st, hz, ms, bpm, beat, cent, %") from None
            return Num(v, unit, pos=self.pos(t))
        if t.kind == "string":
            self.eat()
            return t.text
        if t.kind == "badstring":
            raise self.err("unterminated string literal", t,
                           "add a closing '\"'")
        if t.kind == "ident":
            self.eat()
            return Ref(name=t.text, pos=self.pos(t))
        if t.kind == "op" and t.text == ">":
            self.eat()
            return self._target_from_tokens(t)
        if t.kind == "punct" and t.text == "(":
            self.eat()
            self.skip_nl()
            inner = self.parse_expr()
            self.skip_nl()
            if not self.at("punct", ")"):
                raise self.err("unclosed '(' in expression", t,
                               "add the matching ')'")
            self.eat()
            return inner
        raise self.err(f"unexpected {t.text!r} in a gesture expression", t,
                       "expected a number, a name, '(', '-' or a '>' target")

    def _target_from_tokens(self, gt: Token) -> Target:
        pos = self.pos(gt)
        t = self.cur()
        if t.kind == "op" and t.text in ("+", "-") and t.col == gt.col + 1:
            self.eat()
            return Target(kind="step", degree=1 if t.text == "+" else -1,
                          pos=pos)
        if t.kind == "op" and t.text == "|" and t.col == gt.col + 1:
            self.eat()
            return Target(kind="next", pos=pos)
        if t.kind == "number" and t.col == gt.col + 1:
            self.eat()
            try:
                deg = int(float(t.text))
            except ValueError:
                raise self.err(f"bad target '>{t.text}'", t,
                               "targets are >3 >5 >7 >9") from None
            if deg not in (1, 3, 5, 7, 9, 11, 13):
                raise self.err(f"'>{deg}' is not a chord degree", t,
                               "targets are >3 >5 >7 >9 (or >11 >13)")
            return Target(kind="degree", degree=deg, pos=pos)
        return Target(kind="guide", pos=pos)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def parse(src: str, path: str = "<input>", lenient: bool = False) -> Document:
    """Parse Filigree source into a :class:`~filigree.ast_nodes.Document`.

    Raises :class:`filigree.errors.ParseError` for hard errors; soft problems
    (lane slot-count mismatch, redefinitions) are appended to
    ``Document.warnings``.

    With ``lenient=True`` the recoverable token-level errors -- an unrecognised
    chord symbol, an unknown curve glyph, a malformed pitch set -- are downgraded to
    warnings and the offending item is replaced by something inert (a sustained
    chord, no curve data, a rest), so a half-typed sketch still compiles and plays.
    Structural errors (an unclosed brace, a lane with no name) stay hard: there is
    nothing sensible to substitute for them.
    """
    toks = tokenize(src, path)
    p = Parser(toks, src, path)
    p.lenient = lenient
    return p.parse_document()
