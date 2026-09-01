"""Tests for piece P1 — ``filigree.lex`` and ``filigree.parse``.

Covers every token form in SPEC.md §§0-11 that is syntactic, the two worked
examples from SPEC §3 and SPEC §8, lane alignment warnings, sticky state, and
the precise-diagnostics requirement (every ``ParseError`` carries
path/line/col + token + suggestion).
"""

from __future__ import annotations

import os
import sys

import pytest

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from filigree.ast_nodes import (  # noqa: E402
    BinOp, Breakpoints, Call, Num, Ref, Target, UnOp, Window,
)
from filigree.errors import ParseError  # noqa: E402
from filigree.lex import Token, tokenize  # noqa: E402
from filigree.parse import parse  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def lane(doc, stave_index=0, name="notes", voice=None):
    for ln in doc.staves[stave_index].lanes:
        if ln.name == name and ln.voice == voice:
            return ln
    raise AssertionError(f"no lane {name!r}@{voice} in stave {stave_index}")


def slots(doc, name="notes", bar=0, stave_index=0, voice=None):
    return lane(doc, stave_index, name, voice).bars[bar].slots


def kinds(sl):
    return [s.kind for s in sl]


def glyphs(sl):
    return "".join(s.glyph or " " for s in sl)


def one_stave(body: str, header: str = "") -> object:
    return parse(header + "stave t {\n" + body + "\n}\n", "t.fil")


# ---------------------------------------------------------------------------
# SPEC §0 / §2 — lexical basics and directives
# ---------------------------------------------------------------------------

def test_tokenize_returns_positions_and_kinds():
    toks = tokenize("@tempo 84\n")
    assert isinstance(toks[0], Token)
    assert (toks[0].kind, toks[0].text, toks[0].line, toks[0].col) == \
        ("directive", "@tempo", 1, 1)
    assert (toks[1].kind, toks[1].text, toks[1].col) == ("number", "84", 8)
    assert toks[-1].kind == "eof"


def test_tokenize_lane_line_splits_bars_and_chunks():
    toks = tokenize("stave t {\n  notes | 0 . [0 2] |\n}\n")
    lane_toks = [t for t in toks if t.kind in ("lane", "bar", "chunk")]
    assert [t.kind for t in lane_toks] == \
        ["lane", "bar", "chunk", "chunk", "chunk", "bar"]
    assert [t.text for t in lane_toks if t.kind == "chunk"] == ["0", ".", "[0 2]"]


def test_comments_are_stripped_but_sharps_survive():
    doc = one_stave("  notes | #4 b3 |   # a comment with | and #\n")
    sl = slots(doc)
    assert len(sl) == 2
    assert sl[0].pitches[0].accidental == 1
    assert sl[1].pitches[0].accidental == -1


def test_directive_defaults_present():
    doc = parse("stave t {\n notes | 0 |\n}\n")
    d = doc.directives
    assert d["tempo"] == 120.0
    assert d["meter"] == (4, 4)
    assert d["key"] == (0, "major")
    assert d["ppq"] == 960
    assert d["bend_range"] == 48.0
    assert d["grid"] == 10.0
    assert d["seed"] == 0


def test_directives_are_normalised():
    doc = parse(
        '@tempo 84bpm\n@meter 7/8\n@key Eb dorian\n@ppq 480\n'
        '@bend-range 12st\n@grid 5ms\n@seed 7\n@title "Study no. 1"\n'
        '@voicing warm\n@feel loose\nstave t {\n notes | 0 |\n}\n')
    d = doc.directives
    assert d["tempo"] == 84.0
    assert d["meter"] == (7, 8)
    assert d["key"] == (3, "dorian")       # Eb -> pitch class 3
    assert d["ppq"] == 480
    assert d["bend_range"] == 12.0
    assert d["grid"] == 5.0
    assert d["seed"] == 7
    assert d["title"] == "Study no. 1"
    assert d["voicing"] == "warm"
    assert d["feel"] == "loose"


@pytest.mark.parametrize("key_src,pc", [
    ("@key C major", 0), ("@key F# lydian", 6), ("@key Bb mixolydian", 10),
    ("@key A minor", 9), ("@key D harmonic-minor", 2),
])
def test_key_tonic_pitch_classes(key_src, pc):
    doc = parse(key_src + "\nstave t {\n notes | 0 |\n}\n")
    assert doc.directives["key"][0] == pc


# ---------------------------------------------------------------------------
# SPEC §3 — the worked stave example, verbatim
# ---------------------------------------------------------------------------

SPEC3 = r"""
stave lead {
  channelgroup 1            # optional: MPE zone / port routing
  harm   | i9      | VI^7    | iv11        | V7alt   |
  notes  | 0 . 2 3 | 4 - - 2 | [0 2] 3 . 5 | 7 - 6 - |
  bend   | ___/^^^ | ^^\____ |             | __/\_>3 |
  press  | /^^^\__ | -----^^ | __/^^^^\_   | ^^^^\__  |
  timbre | ---^^^- |         |             |         |
}
"""


def test_spec3_example_parses():
    doc = parse(SPEC3, "spec3.fil")
    st = doc.staves[0]
    assert st.name == "lead"
    assert st.options["channelgroup"] == 1
    assert [ln.name for ln in st.lanes] == \
        ["harm", "notes", "bend", "press", "timbre"]
    assert all(len(ln.bars) == 4 for ln in st.lanes)


def test_spec3_harm_lane_symbols():
    doc = parse(SPEC3, "spec3.fil")
    romans = [b.slots[0].chord.roman for b in lane(doc, 0, "harm").bars]
    assert romans == ["i9", "VI^7", "iv11", "V7alt"]


def test_spec3_notes_lane_shapes():
    doc = parse(SPEC3, "spec3.fil")
    nl = lane(doc, 0, "notes")
    assert kinds(nl.bars[0].slots) == ["note", "rest", "note", "note"]
    assert kinds(nl.bars[1].slots) == ["note", "tie", "tie", "note"]
    b2 = nl.bars[2].slots
    assert kinds(b2) == ["group", "note", "rest", "note"]
    assert [p.value for c in b2[0].children for p in c.pitches] == [0, 2]
    assert nl.bars[0].slots[0].pitches[0].kind == "degree"
    assert nl.bars[0].slots[0].pitches[0].value == 0


def test_spec3_curve_lanes_and_target():
    doc = parse(SPEC3, "spec3.fil")
    bend = lane(doc, 0, "bend")
    assert glyphs(bend.bars[0].slots) == "___/^^^"
    assert glyphs(bend.bars[1].slots) == "^^\\____"
    assert bend.bars[2].slots == []            # empty bar writes no data
    last = bend.bars[3].slots
    assert glyphs(last) == "__/\\_>"
    assert last[-1].target == Target(kind="degree", degree=3, chord="next",
                                     pos=last[-1].target.pos)
    assert lane(doc, 0, "timbre").bars[1].slots == []


def test_spec3_slot_mismatch_is_a_warning_naming_both_counts():
    doc = parse(SPEC3, "spec3.fil")
    assert doc.warnings, "misaligned curve lanes must warn"
    msgs = "\n".join(doc.warnings)
    assert "warning:" in msgs
    assert "7 anchors" in msgs and "4 slots" in msgs
    assert all(w.startswith("spec3.fil:") for w in doc.warnings)
    assert "error" not in msgs


def test_glyph_run_of_v_parses_as_glyphs_not_as_an_identifier():
    """`vv__` and friends are glyph runs; only `name(...)` is a gesture call."""
    doc = parse("stave t {\n  notes | 0 - - - |\n"
                "  bend!range=3st | vv__ |\n}\n", "t.fil")
    lane = [ln for ln in doc.staves[0].lanes if ln.name == "bend"][0]
    glyphs = [sl.glyph for sl in lane.bars[0].slots]
    assert glyphs == ["v", "v", "_", "_"], glyphs
    assert doc.warnings == []


def test_an_inline_gesture_call_inside_a_curve_lane_still_parses():
    doc = parse("gesture vibr(depth: 0.3st) = bend(wiggle(5hz, depth))\n"
                "stave t {\n  notes | 0 - - - |\n"
                "  bend!range=3st | __vibr(depth: 0.5st)_ |\n}\n", "t.fil")
    lane = [ln for ln in doc.staves[0].lanes if ln.name == "bend"][0]
    kinds = [sl.kind for sl in lane.bars[0].slots]
    assert kinds.count("gesture") == 1, kinds
    assert doc.warnings == []


def test_curve_lane_exact_anchor_ratios_do_not_warn():
    for run in ("^^^^", "^^^^^^^^", "^^", "^", "^" * 12):
        doc = parse("stave t {\n  notes | 0 2 4 5 |\n  press | %s |\n}\n" % run,
                    "t.fil")
        assert doc.warnings == [], (run, doc.warnings)


def test_curve_lane_misalignment_warning_names_the_lanes_and_the_file():
    doc = parse("stave t {\n  notes | 0 2 4 5 |\n  bend | ___/^^^ |\n}\n",
                "t.fil")
    assert len(doc.warnings) == 1
    w = doc.warnings[0]
    assert w.startswith("t.fil:3:")
    assert "warning:" in w
    assert "lane 'bend' has 7 anchors" in w and "lane 'notes' has 4 slots" in w
    assert "resampled" in w


def test_unknown_lane_option_is_a_warning_not_silence():
    doc = parse("stave t {\n  notes!oct=5 | 0 |\n}\n", "t.fil")
    assert len(doc.warnings) == 1
    assert "'oct'" in doc.warnings[0] and "no effect" in doc.warnings[0]


# ---------------------------------------------------------------------------
# SPEC §3.1 — slots, groups, alternations, repeats
# ---------------------------------------------------------------------------

def test_leading_and_trailing_bars_are_optional():
    a = one_stave("  notes | 0 2 | 3 5 |")
    b = one_stave("  notes 0 2 | 3 5")
    assert [len(x.slots) for x in lane(a, 0, "notes").bars] == [2, 2]
    assert [len(x.slots) for x in lane(b, 0, "notes").bars] == [2, 2]


def test_nested_groups_are_arbitrarily_deep():
    doc = one_stave("  notes | [0 [2 [3 5]]] |")
    g = slots(doc)[0]
    assert g.kind == "group" and len(g.children) == 2
    inner = g.children[1]
    assert inner.kind == "group"
    assert inner.children[1].kind == "group"
    assert [p.value for p in inner.children[1].children[0].pitches] == [3]


def test_alternation_and_chord_and_star_repeat():
    doc = one_stave("  notes | <0 2 4> (0 2 4) 5*3 |")
    sl = slots(doc)
    assert sl[0].kind == "alt" and len(sl[0].children) == 3
    assert sl[1].kind == "note" and len(sl[1].pitches) == 3
    assert len(sl) == 5                                   # 1 + 1 + 3 repeats
    assert [s.pitches[0].value for s in sl[2:5]] == [5, 5, 5]
    assert sl[2].repeat == 3


def test_bar_fragment_repeat_expands():
    doc = one_stave("  notes | [: 0 2 :4] |")
    g = slots(doc)[0]
    assert g.kind == "group"
    assert len(g.children) == 8
    assert g.repeat == 4
    assert [p.value for c in g.children for p in c.pitches] == \
        [0, 2, 0, 2, 0, 2, 0, 2]


def test_empty_bar_and_empty_slot_write_no_data():
    # LEAD RULING (round 3): whitespace on a curve lane is only a separator; `.` is how
    # you say "no data here", so `^^ .. __` is what used to be written `^^  __`.
    doc = one_stave("  notes | 0 2 3 5 |\n  press | ^^ .. __ |\n  timbre | | ^^^^ |")
    p = slots(doc, "press")
    assert kinds(p) == ["glyph", "glyph", "empty", "empty", "glyph", "glyph"]
    assert slots(doc, "timbre", 0) == []
    assert len(slots(doc, "timbre", 1)) == 4


# ---------------------------------------------------------------------------
# SPEC §3.2 — lane options, §6 — @voice lanes
# ---------------------------------------------------------------------------

def test_lane_options_and_voice_suffix():
    doc = one_stave(
        "  bend!range=7st!shape=ease | ___/^^^ |\n"
        "  press@lead | /^^^\\__ |\n"
        "  timbre!time=note | -^- |")
    b = lane(doc, 0, "bend")
    assert isinstance(b.options["range"], Num)
    assert (b.options["range"].value, b.options["range"].unit) == (7.0, "st")
    assert b.options["shape"] == "ease"
    assert lane(doc, 0, "press", voice="lead").voice == "lead"
    assert lane(doc, 0, "timbre").options["time"] == "note"


def test_cc_lane_and_all_curve_glyph_kinds():
    doc = one_stave("  cc74 | _-^/\\x~ |\n  bend | ~5 3 |")
    sl = slots(doc, "cc74")
    assert glyphs(sl) == "_-^/\\x~"
    assert all(s.kind == "glyph" for s in sl)
    b = slots(doc, "bend")
    assert (b[0].glyph, b[0].glyph_arg) == ("~", 5.0)
    # LEAD RULING (round 3): whitespace on a curve lane is a separator, not an anchor,
    # so `~5 3` is two anchors rather than three.
    assert (b[1].glyph, b[1].glyph_arg) == ("3", 3.0)


def test_all_bend_targets():
    doc = one_stave("  bend | > >3 >5 >7 >9 >+ >- >| |")
    tg = [s.target for s in slots(doc, "bend") if s.target is not None]
    assert [t.kind for t in tg] == \
        ["guide", "degree", "degree", "degree", "degree", "step", "step", "next"]
    assert [t.degree for t in tg[1:5]] == [3, 5, 7, 9]
    assert tg[5].degree == 1 and tg[6].degree == -1
    assert all(t.chord == "next" for t in tg)


def test_inline_gesture_call_in_a_curve_lane():
    doc = parse("gesture vibr(depth: 0.3st) = bend(wiggle(5hz, depth))\n"
                "stave t {\n  bend | _vibr(depth: 0.5st)^ |\n}\n")
    sl = slots(doc, "bend")
    assert kinds(sl) == ["glyph", "gesture", "glyph"]
    assert isinstance(sl[1].expr, Call)
    assert sl[1].expr.name == "vibr"
    assert isinstance(sl[1].expr.kwargs["depth"], Num)


def test_curve_group_and_repeat():
    doc = one_stave("  bend | [_^]x*3 |")
    sl = slots(doc, "bend")
    assert sl[0].kind == "group" and glyphs(sl[0].children) == "_^"
    assert kinds(sl[1:]) == ["glyph", "glyph", "glyph"]
    assert sl[1].repeat == 3


# ---------------------------------------------------------------------------
# SPEC §4 — harmony tokens are passed through unresolved
# ---------------------------------------------------------------------------

def test_harm_roman_absolute_pitchset_and_bass():
    doc = parse(
        "stave a { harm | i9 iiid bVI #iv V/ii V7alt vii0 IIx | }\n"
        "stave b { harm | Cm9 Ab^7 F#7b13 Bsus4 C6/9 Galt E7#9#11 | }\n"
        "stave c { harm | {0 3 7 10 14} {C4 Eb4 G4 Bb4} Dm7/A Cm9/E i9/3 - . | }\n",
        "h.fil")
    a = [s.chord for s in slots(doc, "harm", 0, 0)]
    assert [c.roman for c in a] == \
        ["i9", "iiid", "bVI", "#iv", "V/ii", "V7alt", "vii0", "IIx"]
    assert all(c.absolute is None for c in a)
    b = [s.chord for s in slots(doc, "harm", 0, 1)]
    assert [c.absolute for c in b] == \
        ["Cm9", "Ab^7", "F#7b13", "Bsus4", "C6/9", "Galt", "E7#9#11"]
    c = [s.chord for s in slots(doc, "harm", 0, 2)]
    assert c[0].pitchset == [0, 3, 7, 10, 14] and c[0].pitchset_absolute is False
    assert c[1].pitchset == [60, 63, 67, 70] and c[1].pitchset_absolute is True
    assert (c[2].absolute, c[2].bass) == ("Dm7", "A")
    assert (c[3].absolute, c[3].bass) == ("Cm9", "E")
    assert (c[4].roman, c[4].bass) == ("i9", "3")
    assert c[5].sustain is True
    assert c[6].silent is True


def test_harm_alternation_and_group():
    doc = one_stave("  harm | <i V> [i iv] |")
    sl = slots(doc, "harm")
    assert sl[0].kind == "alt" and [c.chord.roman for c in sl[0].children] == ["i", "V"]
    assert sl[1].kind == "group" and len(sl[1].children) == 2


# ---------------------------------------------------------------------------
# SPEC §5 — note tokens and decorations
# ---------------------------------------------------------------------------

def test_note_token_kinds():
    doc = one_stave("  notes | . - = 0 -2 8 ^3 _3 #4 b3 C4 Eb3 F#5 ~3 ~9 "
                    "@low @high @root @guide |")
    sl = slots(doc)
    assert kinds(sl[:3]) == ["rest", "tie", "retrig"]
    assert [sl[3].pitches[0].value, sl[4].pitches[0].value,
            sl[5].pitches[0].value] == [0, -2, 8]
    assert sl[6].pitches[0].octave == 1
    assert sl[7].pitches[0].octave == -1
    assert sl[8].pitches[0].accidental == 1
    assert sl[9].pitches[0].accidental == -1
    assert [sl[10].pitches[0].kind, sl[10].pitches[0].midi] == ["absolute", 60]
    assert sl[11].pitches[0].midi == 51        # Eb3
    assert sl[12].pitches[0].midi == 78        # F#5
    assert [sl[13].pitches[0].kind, sl[13].pitches[0].value] == ["chordtone", 3]
    assert sl[14].pitches[0].value == 9
    assert [s.pitches[0].anchor for s in sl[15:]] == \
        ["@low", "@high", "@root", "@guide"]
    assert all(s.pitches[0].kind == "anchor" for s in sl[15:])


def test_decorations_attach_to_the_owning_slot():
    doc = parse("gesture cry = bend(0 -> -1st)\n"
                "stave t {\n  notes | 0!cry 1:v90 2%50 3' 4, 5? 6?25 |\n}\n")
    sl = slots(doc)
    assert isinstance(sl[0].gestures[0], Ref) and sl[0].gestures[0].name == "cry"
    assert sl[1].velocity == 90
    assert sl[2].gate == 0.5
    assert sl[3].accent == pytest.approx(0.15)
    assert sl[4].accent == pytest.approx(-0.15)
    assert sl[5].probability == 0.5
    assert sl[6].probability == 0.25


def test_parametrised_gesture_attachment_on_a_note():
    doc = parse("gesture vibr(rate: 5hz) = bend(wiggle(rate, 0.2st))\n"
                "stave t {\n  notes | 3!vibr(rate: 6hz) |\n}\n")
    g = slots(doc)[0].gestures[0]
    assert isinstance(g, Call) and g.name == "vibr"
    assert g.kwargs["rate"].value == 6.0 and g.kwargs["rate"].unit == "hz"


def test_sticky_octave_velocity_gate_and_reset():
    doc = one_stave("  notes | ^^3 4 5 | 0 1 |")
    b0 = slots(doc, "notes", 0)
    assert [s.pitches[0].octave for s in b0] == [2, 2, 2]
    # sticky octave survives the bar line until '!reset'
    assert [s.pitches[0].octave for s in slots(doc, "notes", 1)] == [2, 2]
    doc2 = one_stave("  notes | 0:v100 1 2%25 3 | !reset 4 |")
    a = slots(doc2, "notes", 0)
    assert [s.velocity for s in a] == [100, 100, 100, 100]
    assert [s.gate for s in a] == [None, None, 0.25, 0.25]
    after = slots(doc2, "notes", 1)
    assert after[0].velocity is None and after[0].gate is None


def test_sticky_state_is_per_lane():
    doc = one_stave("  notes | 0:v70 1 |\n  notes@b | 2 3 |")
    assert [s.velocity for s in slots(doc, "notes")] == [70, 70]
    assert [s.velocity for s in slots(doc, "notes", voice="b")] == [None, None]


def test_group_can_carry_decorations():
    doc = one_stave("  notes | [0 2]:v80' |")
    g = slots(doc)[0]
    assert g.kind == "group"
    assert g.velocity == 80
    assert g.accent == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# SPEC §6 — voices
# ---------------------------------------------------------------------------

VOICES_SRC = """
stave lead {
  voices | { bass: 0 . 2 -   ;
              mid : ~3 ~5 - - ;
              lead: 7 - 6 5   } | bass:0 mid:~3 lead:7 |
  press@lead | /^^^\\__ |
  bend@bass  | ______  |
}
"""


def test_voices_block_multiline():
    doc = parse(VOICES_SRC, "v.fil")
    vl = lane(doc, 0, "voices")
    assert len(vl.bars) == 2
    blk = vl.bars[0].slots
    assert len(blk) == 1 and blk[0].kind == "voices"
    assert list(blk[0].voices) == ["bass", "mid", "lead"]
    assert blk[0].voices["bass"].kind == "group"
    assert kinds(blk[0].voices["bass"].children) == ["note", "rest", "note", "tie"]
    assert blk[0].voices["mid"].children[0].pitches[0].kind == "chordtone"


def test_voices_shorthand_is_one_slot():
    doc = parse(VOICES_SRC, "v.fil")
    sh = lane(doc, 0, "voices").bars[1].slots
    assert len(sh) == 1
    assert list(sh[0].voices) == ["bass", "mid", "lead"]
    assert sh[0].voices["lead"].pitches[0].value == 7


def test_per_voice_expression_lanes():
    doc = parse(VOICES_SRC, "v.fil")
    assert lane(doc, 0, "press", voice="lead").voice == "lead"
    assert lane(doc, 0, "bend", voice="bass").voice == "bass"


# ---------------------------------------------------------------------------
# SPEC §8 — the gesture examples, verbatim
# ---------------------------------------------------------------------------

SPEC8 = r"""
gesture cry  = bend(0 -> -0.7st -> 0, shape: ease)
gesture warm = press(0.2 -> 0.9, shape: exp) | timbre(0.4 -> 0.7)
gesture vibr(rate: 5.2hz, depth: 0.3st, onset: 30%) =
          bend(wiggle(rate, depth) @ onset..100%)
gesture cry2 = cry * 1.4 >> vibr(rate: 6hz)
gesture fall = bend(0 -> >3)
"""


def test_spec8_gesture_definitions_parse():
    doc = parse(SPEC8, "spec8.fil")
    assert set(doc.gestures) == {"cry", "warm", "vibr", "cry2", "fall"}


def test_spec8_cry_breakpoints():
    doc = parse(SPEC8, "spec8.fil")
    body = doc.gestures["cry"].body
    assert isinstance(body, Call) and body.name == "bend"
    bp = body.args[0]
    assert isinstance(bp, Breakpoints) and len(bp.points) == 3
    assert bp.points[1][0].value == -0.7 and bp.points[1][0].unit == "st"
    assert bp.shape == "ease"
    assert body.kwargs["shape"] == "ease"


def test_spec8_warm_is_parallel_across_lanes():
    doc = parse(SPEC8, "spec8.fil")
    body = doc.gestures["warm"].body
    assert isinstance(body, BinOp) and body.op == "par"
    assert body.lhs.name == "press" and body.rhs.name == "timbre"


def test_spec8_vibr_params_and_window():
    doc = parse(SPEC8, "spec8.fil")
    gd = doc.gestures["vibr"]
    assert [p[0] for p in gd.params] == ["rate", "depth", "onset"]
    assert gd.params[0][1].value == 5.2 and gd.params[0][1].unit == "hz"
    assert gd.params[2][1].unit == "pct" and gd.params[2][1].value == 30.0
    win = gd.body.args[0]
    assert isinstance(win, Window)
    assert isinstance(win.inner, Call) and win.inner.name == "wiggle"
    assert isinstance(win.start, Ref) and win.start.name == "onset"
    assert win.end.value == 100.0 and win.end.unit == "pct"


def test_spec8_cry2_precedence_seq_lower_than_mul():
    doc = parse(SPEC8, "spec8.fil")
    body = doc.gestures["cry2"].body
    assert isinstance(body, BinOp) and body.op == "seq"
    assert isinstance(body.lhs, BinOp) and body.lhs.op == "scale_or_mul"
    assert body.lhs.lhs.name == "cry" and body.lhs.rhs.value == 1.4
    assert isinstance(body.rhs, Call) and body.rhs.name == "vibr"


def test_spec8_harmonic_target_inside_a_gesture():
    doc = parse(SPEC8, "spec8.fil")
    bp = doc.gestures["fall"].body.args[0]
    assert isinstance(bp.points[1][0], Target)
    assert bp.points[1][0].kind == "degree" and bp.points[1][0].degree == 3


def test_gesture_precedence_ladder():
    doc = parse("gesture g = a | b >> c + d * -e @ 10%..90%\n", "g.fil")
    top = doc.gestures["g"].body
    assert top.op == "par"                       # '|' lowest
    seq = top.rhs
    assert seq.op == "seq"                       # then '>>'
    add = seq.rhs
    assert add.op == "add"                       # then '+'
    mul = add.rhs
    assert mul.op == "scale_or_mul"              # then '*'
    neg = mul.rhs
    assert isinstance(neg, UnOp) and neg.op == "neg"
    assert isinstance(neg.operand, Window)       # '@window' tighter than unary
    assert neg.operand.start.value == 10.0 and neg.operand.end.value == 90.0


def test_sequence_with_explicit_split_and_primitives():
    doc = parse(
        'gesture a = ramp(0, 1) >>(30%) pulse(4hz, 0.5)\n'
        'gesture b = drift(0.2) + curve("_/^\\\\_")\n'
        'gesture c = cc11(0 -> 1 @ 40% -> 0.2)\n', "p.fil")
    a = doc.gestures["a"].body
    assert a.op == "seq" and a.split.value == 30.0 and a.split.unit == "pct"
    assert a.lhs.name == "ramp" and a.rhs.name == "pulse"
    b = doc.gestures["b"].body
    assert b.op == "add" and b.lhs.name == "drift"
    assert b.rhs.name == "curve" and b.rhs.args[0] == "_/^\\_"
    bp = doc.gestures["c"].body.args[0]
    assert doc.gestures["c"].body.name == "cc11"
    assert bp.points[1][1].value == 40.0 and bp.points[1][1].unit == "pct"
    assert bp.points[0][1] is None


def test_unary_minus_and_subtraction():
    doc = parse("gesture g = -cry\ngesture h = cry - warm\n", "u.fil")
    assert isinstance(doc.gestures["g"].body, UnOp)
    assert doc.gestures["h"].body.op == "sub"


# ---------------------------------------------------------------------------
# SPEC §9 / §4.1 / §10 — feel, voicing, parts
# ---------------------------------------------------------------------------

def test_feel_definitions():
    doc = parse(
        "feel loose  = { timing: 14ms gauss, velocity: 8%, gate: 5%, seed: 3 }\n"
        "feel pushed = { timing: -8ms flat on: 2,4 }\n"
        "feel breath = { onset: 12ms per-voice-spread, release: 20ms }\n", "f.fil")
    lo = doc.feels["loose"].fields
    assert lo["timing"] == 14.0 and lo["timing_dist"] == "gauss"
    assert lo["velocity"] == pytest.approx(0.08) and lo["gate"] == pytest.approx(0.05)
    assert lo["seed"] == 3
    pu = doc.feels["pushed"].fields
    assert pu["timing"] == -8.0 and pu["timing_dist"] == "flat" and pu["on"] == (2, 4)
    br = doc.feels["breath"].fields
    assert br["onset"] == 12.0 and br["release"] == 20.0
    assert br["onset_mode"] == "per-voice-spread"


def test_voicing_definition():
    doc = parse("voicing warm { range: C3..C5, mode: smooth, size: 4, "
                "drop: 2, spread: 1.1, top: melody }\n", "vo.fil")
    f = doc.voicings["warm"].fields
    assert f["range"] == ("C3", "C5") and (f["low"], f["high"]) == (48, 72)
    assert f["mode"] == "smooth" and f["size"] == 4 and f["drop"] == 2
    assert f["spread"] == pytest.approx(1.1) and f["top"] == "melody"


def test_part_and_play_with_transforms():
    doc = parse(
        "part hook {\n  notes | 0 . 2 3 | 4 - - 2 |\n  bend  | ___/^^^ | ^^\\____ |\n}\n"
        "stave lead {\n  harm | i9 | VI^7 |\n  play hook\n"
        "  play hook >> transpose(3) >> retro\n"
        '  play hook >> mask("1 0 1 1") >> euclid(3,8)\n}\n', "pt.fil")
    assert list(doc.parts) == ["hook"]
    assert [ln.name for ln in doc.parts["hook"].lanes] == ["notes", "bend"]
    sts = doc.staves[0].statements
    assert [s.part for s in sts] == ["hook", "hook", "hook"]
    assert sts[0].transforms == []
    assert [c.name for c in sts[1].transforms] == ["transpose", "retro"]
    assert sts[1].transforms[0].args[0].value == 3.0
    assert sts[2].transforms[0].args[0] == "1 0 1 1"
    assert [a.value for a in sts[2].transforms[1].args] == [3.0, 8.0]


def test_stave_options_and_after():
    doc = parse(
        "feel loose = { timing: 5ms }\nvoicing warm { mode: close }\n"
        "gesture cry = bend(0 -> -1st)\n"
        "stave a { notes | 0 | }\n"
        "stave b {\n  after a\n  channelgroup 2\n  feel loose\n"
        "  voicing warm\n  gesture cry\n  notes | 0 |\n}\n", "s.fil")
    o = doc.staves[1].options
    assert o["after"] == "a" and o["channelgroup"] == 2
    assert o["feel"] == "loose" and o["voicing"] == "warm" and o["gesture"] == "cry"


def test_multiple_staves_and_document_metadata():
    src = "stave a { notes | 0 | }\nstave b { notes | 2 | }\n"
    doc = parse(src, "m.fil")
    assert [s.name for s in doc.staves] == ["a", "b"]
    assert doc.path == "m.fil" and doc.source == src


# ---------------------------------------------------------------------------
# warnings (never errors)
# ---------------------------------------------------------------------------

def test_divisor_and_multiple_slot_counts_do_not_warn():
    doc = one_stave("  notes | 0 2 3 5 |\n  press | ^^^^^^^^ |\n  bend | __ |")
    assert doc.warnings == []


def test_mismatched_slot_counts_warn_with_both_numbers():
    doc = one_stave("  notes | 0 2 3 5 |\n  press | ^^^ |")
    assert len(doc.warnings) == 1
    w = doc.warnings[0]
    assert "3 anchors" in w and "4 slots" in w
    assert "'press'" in w and "'notes'" in w
    assert w.startswith("t.fil:") and "warning:" in w


def test_bar_count_mismatch_warns():
    # LEAD RULING (round 3): a short lane whose bar count DIVIDES the reference cycles
    # over it and stays silent (a one-bar figure under an eight-bar progression is an
    # idiom); only a count that cannot cycle evenly warns.
    doc = one_stave("  notes | 0 | 2 |\n  press | ^ |")
    assert not any("bars" in w for w in doc.warnings), doc.warnings
    doc = one_stave("  notes | 0 | 2 | 4 | 6 |\n  press | ^ | _ | ^ |")
    assert any("neither divides the other" in w for w in doc.warnings), doc.warnings


def test_duplicate_lane_appends_bars_silently():
    # LEAD RULING (round 3): repeating a lane inside a stave is the documented way to
    # write a long piece as readable blocks of bars, so it no longer warns.
    doc = one_stave("  notes | 0 |\n  notes | 2 |")
    assert not any("twice" in w for w in doc.warnings), doc.warnings


# ---------------------------------------------------------------------------
# errors — every diagnostic carries path:line:col, the token and a suggestion
# ---------------------------------------------------------------------------

def _fails(src, path="e.fil"):
    with pytest.raises(ParseError) as ei:
        parse(src, path)
    e = ei.value
    assert e.path == path, f"missing path: {e}"
    assert e.line > 0, f"missing line: {e}"
    assert e.col > 0, f"missing col: {e}"
    assert e.token, f"missing token: {e}"
    assert e.suggestion, f"missing suggestion: {e}"
    assert str(e).startswith(f"{path}:{e.line}:{e.col}: error: ")
    return e


def test_error_unknown_directive():
    e = _fails("@tmepo 84\nstave t { notes | 0 | }\n")
    assert e.token == "@tmepo"
    assert "tempo" in e.suggestion
    assert (e.line, e.col) == (1, 1)


def test_error_unknown_mode():
    e = _fails("@key C dorain\nstave t { notes | 0 | }\n")
    assert "dorian" in e.suggestion
    assert (e.line, e.col) == (1, 8)


def test_error_bad_meter():
    e = _fails("@meter 7\nstave t { notes | 0 | }\n")
    assert "7/8" in e.suggestion


def test_error_unknown_lane_name():
    e = _fails("stave t {\n  bendd | ___ |\n}\n")
    assert e.token == "bendd"
    assert "bend" in e.suggestion
    assert e.line == 2 and e.col == 3


def test_error_bad_note_token():
    e = _fails("stave t {\n  notes | 0 H4 |\n}\n")
    assert e.token == "H4"
    assert "C4" in e.suggestion
    assert (e.line, e.col) == (2, 13)


def test_error_bad_curve_glyph():
    e = _fails("stave t {\n  press | ^^q^ |\n}\n")
    assert e.token == "q"
    assert "glyph" in e.suggestion
    assert (e.line, e.col) == (2, 13)


def test_error_target_only_valid_on_bend():
    e = _fails("stave t {\n  press | __>3 |\n}\n")
    assert e.token == ">"
    assert "bend" in e.suggestion
    assert "press" in e.message


def test_error_unbalanced_group():
    e = _fails("stave t {\n  notes | [0 2 |\n}\n")
    assert "]" in e.suggestion


def test_error_unclosed_stave_brace():
    e = _fails("stave t {\n  notes | 0 |\n")
    assert "}" in e.suggestion


def test_error_gesture_without_body():
    e = _fails("gesture cry\nstave t { notes | 0 | }\n")
    assert e.token == "cry"
    assert "=" in e.suggestion


def test_error_velocity_out_of_range():
    e = _fails("stave t {\n  notes | 0:v200 |\n}\n")
    assert "0-127" in e.suggestion


def test_error_bad_target_degree():
    e = _fails("stave t {\n  bend | >4 |\n}\n")
    assert ">3" in e.suggestion


def test_error_unknown_shape_option():
    e = _fails("stave t {\n  bend!shape=eaze | ___ |\n}\n")
    assert "ease" in e.suggestion


def test_error_unknown_anchor():
    e = _fails("stave t {\n  notes | @lowest |\n}\n")
    assert "low" in e.suggestion


def test_error_unknown_feel_field():
    e = _fails("feel x = { timming: 4ms }\nstave t { notes | 0 | }\n")
    assert "timing" in e.suggestion


def test_error_lane_outside_stave():
    e = _fails("notes | 0 2 |\n")
    assert "stave" in e.suggestion


def test_error_unknown_stave_statement():
    e = _fails("stave t {\n  playy hook\n  notes | 0 |\n}\n")
    assert "play" in e.suggestion


def test_error_chord_symbol_not_recognised():
    e = _fails("stave t {\n  harm | Zm9 |\n}\n")
    assert "SPEC" in e.suggestion or "roman" in e.suggestion


def test_error_repeat_without_count():
    e = _fails("stave t {\n  notes | 0* |\n}\n")
    assert "*3" in e.suggestion


def test_error_message_renders_all_three_parts():
    e = _fails("@tmepo 84\nstave t { notes | 0 | }\n")
    text = str(e)
    assert "e.fil:1:1: error:" in text
    assert "at token: '@tmepo'" in text
    assert "hint:" in text


# ---------------------------------------------------------------------------
# determinism / idempotence
# ---------------------------------------------------------------------------

def test_parsing_is_deterministic():
    a = parse(SPEC3, "spec3.fil")
    b = parse(SPEC3, "spec3.fil")
    assert a.warnings == b.warnings
    assert repr(a.staves) == repr(b.staves)
    assert repr(parse(SPEC8, "spec8.fil").gestures) == \
        repr(parse(SPEC8, "spec8.fil").gestures)


# ---------------------------------------------------------------------------
# SPEC §8 attachment forms, §7 lane time modes, §3.3 stave ordering
# ---------------------------------------------------------------------------

def test_lane_wide_and_per_voice_gesture_attachment():
    doc = parse(
        "gesture cry = bend(0 -> -1st)\n"
        "stave t {\n"
        "  notes!gesture=cry | 0 2 |\n"
        "  voices!gesture@lead=cry | lead:7 |\n"
        "  amp!time=note | /^\\ |\n"
        "  pan | ---- |\n"
        "}\n", "att.fil")
    assert lane(doc, 0, "notes").options["gesture"] == "cry"
    assert lane(doc, 0, "voices").options["gesture@lead"] == "cry"
    assert lane(doc, 0, "amp").options["time"] == "note"
    assert [ln.name for ln in doc.staves[0].lanes][-1] == "pan"


def test_error_bare_decoration_has_actionable_hint():
    e = _fails("stave t {\n  notes | 0 :v90 |\n}\n")
    assert "not attached" in e.message
    assert "0:v90" in e.suggestion


def test_error_unbalanced_voices_block():
    e = _fails("stave t {\n  voices | { bass: 0 |\n}\n")
    assert e.suggestion
