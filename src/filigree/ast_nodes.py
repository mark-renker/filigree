"""Filigree AST — the contract between the parser and everything downstream.

Owned by the lead agent. Builders MUST NOT change field names or semantics here;
if something is missing, report it instead of editing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Union

# ---------------------------------------------------------------------------
# source positions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pos:
    line: int = 0
    col: int = 0
    file: str = "<input>"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.file}:{self.line}:{self.col}"


# ---------------------------------------------------------------------------
# expression / gesture AST
#
# Gesture expressions form a small tree.  gesture.py evaluates them; parse.py
# only builds them.
# ---------------------------------------------------------------------------

LaneName = str  # "bend" | "press" | "timbre" | "amp" | "pan" | "cc74" ...


@dataclass
class Num:
    """A numeric literal with an optional unit.

    unit is one of: None, "st", "hz", "ms", "pct", "beat", "bpm", "cent".
    ``value`` is stored in the unit given; consumers normalise.
    """

    value: float
    unit: Optional[str] = None
    pos: Pos = field(default_factory=Pos)


@dataclass
class Ref:
    """Reference to a named gesture/feel/voicing/part, or a parameter inside a
    gesture definition body."""

    name: str
    pos: Pos = field(default_factory=Pos)


@dataclass
class Target:
    """A harmonic target, e.g. ``>3`` / ``>`` / ``>+``.

    kind:
      "guide"  -> nearest guide tone of the reference chord
      "degree" -> chord degree given by ``degree`` (1,3,5,7,9,11,13)
      "step"   -> next/previous scale step (``degree`` = +1 / -1)
      "next"   -> next note in this lane's own note sequence
    ``chord`` selects which chord: "next" (default) | "current" | "prev".
    """

    kind: Literal["guide", "degree", "step", "next"]
    degree: Optional[int] = None
    chord: Literal["next", "current", "prev"] = "next"
    pos: Pos = field(default_factory=Pos)


@dataclass
class Call:
    """A gesture primitive or user gesture invocation.

    name: "bend" | "press" | "timbre" | "amp" | "cc<n>" | "wiggle" | "drift"
          | "ramp" | "pulse" | "curve" | <user gesture name>
    args: positional arguments (Breakpoints / Num / Ref / Target / Call / str)
    kwargs: keyword arguments by name
    """

    name: str
    args: list[Any] = field(default_factory=list)
    kwargs: dict[str, Any] = field(default_factory=dict)
    pos: Pos = field(default_factory=Pos)


@dataclass
class Breakpoints:
    """``a -> b @ 40% -> c`` inside a lane primitive.

    points: list of (value_expr, position_expr_or_None).  Positions are
    fractions of the note lifetime (Num with unit "pct" or plain 0..1).
    Unpositioned points are spread evenly between their positioned neighbours.
    """

    points: list[tuple[Any, Optional[Any]]] = field(default_factory=list)
    shape: Optional[str] = None  # "ease" | "linear" | "hold" | "exp" | "snap"
    pos: Pos = field(default_factory=Pos)


@dataclass
class BinOp:
    """``+ - * >> |`` over gesture expressions.

    op: "add" | "sub" | "scale_or_mul" | "seq" | "par"
    split: for "seq", the fraction of the lifetime given to lhs (default 0.5).
    """

    op: Literal["add", "sub", "scale_or_mul", "seq", "par"]
    lhs: Any = None
    rhs: Any = None
    split: Optional[Any] = None
    pos: Pos = field(default_factory=Pos)


@dataclass
class UnOp:
    op: Literal["neg"]
    operand: Any = None
    pos: Pos = field(default_factory=Pos)


@dataclass
class Window:
    """``a @ 30%..80%`` — restrict a gesture to a window of the note lifetime."""

    inner: Any
    start: Any = None
    end: Any = None
    pos: Pos = field(default_factory=Pos)


GestureExpr = Union[Num, Ref, Call, BinOp, UnOp, Window, Breakpoints, Target]


# ---------------------------------------------------------------------------
# musical tokens
# ---------------------------------------------------------------------------


@dataclass
class Slot:
    """One time slot in a lane.

    Exactly one of the payload fields is meaningful, selected by ``kind``:

      "rest"     -> silence
      "tie"      -> extend previous note
      "retrig"   -> retrigger previous pitch
      "note"     -> pitches (list, len>1 == chord)
      "group"    -> children subdivide this slot equally  (from ``[a b]``)
      "alt"      -> children alternate between bar repeats (from ``<a b>``)
      "glyph"    -> curve anchor glyph (curve lanes only)
      "chord"    -> harmonic symbol (harm lane only)
      "voices"   -> mapping voice-name -> Slot (voices lane only)
      "gesture"  -> inline gesture call occupying the slot (curve lanes)
      "empty"    -> no data written for this slot
    """

    kind: Literal[
        "rest", "tie", "retrig", "note", "group", "alt",
        "glyph", "chord", "voices", "gesture", "empty",
    ]
    # --- note payload -------------------------------------------------------
    pitches: list["PitchTok"] = field(default_factory=list)
    velocity: Optional[int] = None      # explicit :v90
    accent: float = 0.0                 # ' -> +0.15, , -> -0.15
    gate: Optional[float] = None        # %50 -> 0.5
    probability: float = 1.0            # ? -> 0.5, ?25 -> 0.25
    gestures: list[GestureExpr] = field(default_factory=list)  # !cry
    # --- structural payload -------------------------------------------------
    children: list["Slot"] = field(default_factory=list)
    repeat: int = 1                     # from ``x*3``
    # --- curve payload ------------------------------------------------------
    glyph: Optional[str] = None         # "_", "-", "^", "/", "\\", "x", "~", "0".."9"
    glyph_arg: Optional[float] = None   # "~5" -> 5.0
    target: Optional[Target] = None     # ">3"
    # --- harmony payload ----------------------------------------------------
    chord: Optional["ChordTok"] = None
    # --- voices payload -----------------------------------------------------
    voices: dict[str, "Slot"] = field(default_factory=dict)
    # --- misc ---------------------------------------------------------------
    expr: Optional[GestureExpr] = None
    pos: Pos = field(default_factory=Pos)


@dataclass
class PitchTok:
    """A single pitch inside a note slot.

    kind:
      "degree"    -> scale degree relative to @key; ``value`` may be negative
      "absolute"  -> absolute MIDI note number in ``midi``
      "chordtone" -> degree of the *current* chord (``~3``); value in {1,3,5,7,9,11,13}
      "anchor"    -> "@low" | "@high" | "@root" | "@guide"
    accidental: -1 (b), 0, +1 (#), applied after degree resolution
    octave: sticky octave shift in octaves (already resolved by the parser)
    """

    kind: Literal["degree", "absolute", "chordtone", "anchor"]
    value: int = 0
    midi: Optional[int] = None
    anchor: Optional[str] = None
    accidental: int = 0
    octave: int = 0
    pos: Pos = field(default_factory=Pos)


@dataclass
class ChordTok:
    """An unresolved harmonic symbol.

    Exactly one spelling is populated:
      roman:    e.g. "V7alt", "iiid", "bVI", "V/ii"
      absolute: e.g. "Cm9", "Ab^7", "F#7b13"
      pitchset: explicit semitone offsets or absolute midi notes
    """

    roman: Optional[str] = None
    absolute: Optional[str] = None
    pitchset: Optional[list[int]] = None
    pitchset_absolute: bool = False
    bass: Optional[str] = None  # "E" or "3"
    sustain: bool = False       # from "-"
    silent: bool = False        # from "."
    pos: Pos = field(default_factory=Pos)


# ---------------------------------------------------------------------------
# lanes, staves, document
# ---------------------------------------------------------------------------


@dataclass
class Bar:
    slots: list[Slot] = field(default_factory=list)
    pos: Pos = field(default_factory=Pos)


@dataclass
class Lane:
    """One lane of a stave.

    name: "harm" | "notes" | "voices" | "bend" | "press" | "timbre" | "amp"
          | "pan" | "cc<n>"
    voice: from ``press@lead`` -> "lead"; None means all voices.
    options: from ``bend!range=7st!shape=ease`` -> {"range": Num, "shape": "ease"}
    """

    name: LaneName
    bars: list[Bar] = field(default_factory=list)
    voice: Optional[str] = None
    options: dict[str, Any] = field(default_factory=dict)
    pos: Pos = field(default_factory=Pos)


@dataclass
class PlayStmt:
    """``play hook >> transpose(3) >> retro`` inside a stave."""

    part: str
    transforms: list[Call] = field(default_factory=list)
    pos: Pos = field(default_factory=Pos)


@dataclass
class Stave:
    name: str
    lanes: list[Lane] = field(default_factory=list)
    statements: list[PlayStmt] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)  # feel/gesture/voicing/channelgroup/after
    pos: Pos = field(default_factory=Pos)


@dataclass
class Part:
    name: str
    lanes: list[Lane] = field(default_factory=list)
    pos: Pos = field(default_factory=Pos)


@dataclass
class GestureDef:
    name: str
    params: list[tuple[str, Optional[Any]]]  # (name, default expr)
    body: GestureExpr = None
    pos: Pos = field(default_factory=Pos)


@dataclass
class FeelDef:
    name: str
    fields: dict[str, Any] = field(default_factory=dict)
    pos: Pos = field(default_factory=Pos)


@dataclass
class VoicingDef:
    name: str
    fields: dict[str, Any] = field(default_factory=dict)
    pos: Pos = field(default_factory=Pos)


@dataclass
class Document:
    directives: dict[str, Any] = field(default_factory=dict)
    gestures: dict[str, GestureDef] = field(default_factory=dict)
    feels: dict[str, FeelDef] = field(default_factory=dict)
    voicings: dict[str, VoicingDef] = field(default_factory=dict)
    parts: dict[str, Part] = field(default_factory=dict)
    staves: list[Stave] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source: str = ""
    path: str = "<input>"
