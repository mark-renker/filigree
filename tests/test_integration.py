"""End-to-end tests: source -> Document -> Score -> MIDI.

These cover the integration layer (`filigree.resolve`) plus the two things only
an end-to-end test can see: that the shipped `examples/` really compile and
render, and that the whole pipeline is deterministic.
"""

from __future__ import annotations

import json
import math
import re
import os
import subprocess
import sys

import pytest

import filigree
from filigree import errors, ir
from filigree.parse import parse
from filigree.resolve import CURVE_LANES, is_curve_lane, resolve

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(REPO, "examples")
EXAMPLE_FILES = sorted(f for f in os.listdir(EXAMPLES) if f.endswith(".fil"))


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def compile_src(src: str, path: str = "t.fil") -> ir.Score:
    return resolve(parse(src, path))


def stave(score: ir.Score, name: str) -> ir.StaveIR:
    for st in score.staves:
        if st.name == name:
            return st
    raise AssertionError(f"no stave {name!r} in {[s.name for s in score.staves]}")


def note_at(st: ir.StaveIR, beat: float, voice=None) -> ir.Note:
    cands = [n for n in st.notes
             if abs(n.start - beat) < 0.35 and (voice is None or n.voice == voice)]
    assert cands, f"no note near beat {beat} (voice={voice})"
    return sorted(cands, key=lambda n: abs(n.start - beat))[0]


def finite(curve: ir.Curve) -> list[tuple[float, float]]:
    return [(t, v) for t, v in curve.points if not math.isnan(v)]


# --------------------------------------------------------------------------- #
# 1. packaging: pyproject + conftest
# --------------------------------------------------------------------------- #

def test_pyproject_declares_console_script_and_src_layout():
    text = open(os.path.join(REPO, "pyproject.toml")).read()
    assert 'filigree = "filigree.cli:main"' in text
    assert 'package-dir = { "" = "src" }' in text
    assert 'requires-python = ">=3.11"' in text
    # pure stdlib + numpy + mido (rtmidi is an extra), per docs/ARCH.md
    assert "numpy" in text and "mido" in text
    assert "scipy" not in text


def test_conftest_puts_src_and_repo_root_on_path():
    assert os.path.join(REPO, "src") in sys.path
    assert REPO in sys.path
    assert filigree.__file__.startswith(os.path.join(REPO, "src"))


def test_cli_module_is_runnable():
    out = subprocess.run([sys.executable, "-m", "filigree.cli", "--help"],
                         cwd=REPO, capture_output=True, text=True,
                         env={**os.environ, "PYTHONPATH": os.path.join(REPO, "src")})
    assert out.returncode == 0
    assert "render" in out.stdout


# --------------------------------------------------------------------------- #
# 2. every shipped example compiles, renders and is MPE-clean
# --------------------------------------------------------------------------- #

def test_examples_directory_has_at_least_six_files():
    assert len(EXAMPLE_FILES) >= 6, EXAMPLE_FILES
    assert "tasks.fil" in EXAMPLE_FILES


@pytest.mark.parametrize("name", EXAMPLE_FILES)
def test_example_compiles_and_is_warning_free(name):
    path = os.path.join(EXAMPLES, name)
    score = filigree.compile_source(open(path).read(), path)
    assert score.staves, name
    assert score.notes, name
    assert score.duration_beats > 0, name
    assert score.warnings == [], (name, score.warnings)


@pytest.mark.parametrize("name", EXAMPLE_FILES)
def test_example_renders_valid_mpe_midi(tmp_path, name):
    audit = pytest.importorskip("tools.audit_mpe")
    path = os.path.join(EXAMPLES, name)
    score = filigree.compile_source(open(path).read(), path)
    out = str(tmp_path / (name + ".mid"))
    filigree.write_midi(score, out)
    assert os.path.getsize(out) > 100
    rep = audit.audit_file(out, expect_ppq=score.ppq)
    assert rep.failures == [], (name, rep.failures)


def test_examples_cover_every_curve_lane_and_the_voices_lane():
    lanes: set[str] = set()
    voices: set[str] = set()
    for name in EXAMPLE_FILES:
        path = os.path.join(EXAMPLES, name)
        score = filigree.compile_source(open(path).read(), path)
        for n in score.notes:
            lanes.update(n.curves)
            if n.voice:
                voices.add(n.voice)
    for lane in ("bend", "press", "timbre"):
        assert lane in lanes, lanes
    assert any(is_curve_lane(l) and l.startswith("cc") for l in lanes), lanes
    assert voices, "no example uses named voices"


# --------------------------------------------------------------------------- #
# 3. determinism
# --------------------------------------------------------------------------- #

def test_compilation_is_deterministic_across_runs():
    path = os.path.join(EXAMPLES, "pulse.fil")
    src = open(path).read()
    a = json.dumps(filigree.compile_source(src, path).to_json(), sort_keys=True)
    b = json.dumps(filigree.compile_source(src, path).to_json(), sort_keys=True)
    assert a == b


def test_midi_output_is_byte_identical_for_the_same_source(tmp_path):
    path = os.path.join(EXAMPLES, "blue_iron.fil")
    src = open(path).read()
    outs = []
    for i in range(2):
        p = str(tmp_path / f"x{i}.mid")
        filigree.write_midi(filigree.compile_source(src, path), p)
        outs.append(open(p, "rb").read())
    assert outs[0] == outs[1]


def test_seed_changes_the_humanisation_but_not_the_pitches():
    src = ("@seed {s}\nfeel loose = {{ timing: 20ms gauss, velocity: 20% }}\n"
           "stave t {{\n  feel loose\n  notes | 0 2 4 5 | 7 5 4 2 |\n}}\n")
    a = compile_src(src.format(s=1))
    b = compile_src(src.format(s=2))
    assert [n.pitch for n in a.notes] == [n.pitch for n in b.notes]
    assert [round(n.start, 6) for n in a.notes] != [round(n.start, 6) for n in b.notes]


def test_probability_drops_are_deterministic():
    src = "@seed 4\nstave t {\n  notes | 0? 2? 4? 5? 7? 9? 11? 12? |\n}\n"
    first = [n.pitch for n in compile_src(src).notes]
    for _ in range(3):
        assert [n.pitch for n in compile_src(src).notes] == first
    assert 0 < len(first) < 8, first


# --------------------------------------------------------------------------- #
# 4. directives -> Score fields
# --------------------------------------------------------------------------- #

def test_directives_become_score_fields():
    score = compile_src(
        '@title "Hi"\n@tempo 84bpm\n@meter 7/8\n@key F# minor\n@ppq 480\n'
        '@bend-range 24st\n@grid 20ms\n@seed 9\nstave t {\n  notes | 0 |\n}\n')
    assert score.title == "Hi"
    assert score.tempo == 84.0
    assert score.meter == (7, 8)
    assert score.key == (6, "minor")
    assert score.ppq == 480
    assert score.bend_range == 24.0
    assert score.grid_ms == 20.0
    assert score.seed == 9


def test_meter_sets_bar_length_in_beats():
    score = compile_src("@meter 7/8\nstave t {\n  notes | 0 | 0 |\n}\n")
    starts = sorted(n.start for n in score.notes)
    assert starts == [0.0, 3.5]


# --------------------------------------------------------------------------- #
# 5. note tokens
# --------------------------------------------------------------------------- #

def test_absolute_middle_c_is_60_and_degrees_are_key_relative():
    score = compile_src("@key C major\nstave t {\n  notes | C4 0 2 4 |\n}\n")
    assert [n.pitch for n in score.notes[:4]] == [60, 60, 64, 67]


def test_octave_shifts_are_sticky_and_accidentals_apply():
    score = compile_src("stave t {\n  notes | ^0 2 _0 #4 b3 |\n}\n")
    p = [n.pitch for n in score.notes]
    assert p[0] == 72 and p[1] == 76          # ^0 sticky through 2
    assert p[2] == 48                          # _0
    assert p[3] == 56 and p[4] == 52           # #4 raises G3, b3 lowers F3


def test_rest_tie_and_retrigger():
    score = compile_src("stave t {\n  notes | 0 . 2 - | = . . . |\n}\n")
    st = stave(score, "t")
    assert len(st.notes) == 3
    first, held, retrig = st.notes
    assert (first.start, first.pitch) == (0.0, 60)
    assert held.start == 2.0 and held.dur == pytest.approx(2.0)
    assert retrig.start == 4.0 and retrig.pitch == held.pitch


def test_chord_token_sounds_simultaneously():
    score = compile_src("stave t {\n  notes | (0 2 4) . . . |\n}\n")
    st = stave(score, "t")
    assert len(st.notes) == 3
    assert {n.start for n in st.notes} == {0.0}
    assert sorted(n.pitch for n in st.notes) == [60, 64, 67]


def test_group_subdivides_one_slot():
    score = compile_src("stave t {\n  notes | [0 2] 4 . . |\n}\n")
    st = stave(score, "t")
    assert [round(n.start, 3) for n in st.notes] == [0.0, 0.5, 1.0]
    assert st.notes[0].dur == pytest.approx(0.5)


def test_alternation_advances_per_bar_repetition():
    score = compile_src("stave t {\n  notes | <0 2 4> | <0 2 4> | <0 2 4> | <0 2 4> |\n}\n")
    assert [n.pitch for n in stave(score, "t").notes] == [60, 64, 67, 60]


def test_velocity_gate_and_accents():
    score = compile_src("stave t {\n  notes | 0:v40 2:v100' 4:v100, 5:v100%50 |\n}\n")
    st = stave(score, "t")
    assert st.notes[0].velocity == 40
    assert st.notes[1].velocity == 115          # +15%
    assert st.notes[2].velocity == 85           # -15%
    assert st.notes[3].dur == pytest.approx(0.5)  # gate 50%


# --------------------------------------------------------------------------- #
# 6. harmony
# --------------------------------------------------------------------------- #

def test_harm_lane_produces_voiced_chord_events():
    score = compile_src("@key C minor\nstave t {\n  harm | i9 | iv7 | V7 | - |\n}\n")
    st = stave(score, "t")
    assert [c.symbol for c in st.chords] == ["i9", "iv7", "V7"]
    assert st.chords[-1].dur == pytest.approx(8.0)     # `-` sustains
    for c in st.chords:
        assert c.pitches == sorted(c.pitches)
        assert len(c.pitches) >= 3
        assert all(48 <= p <= 72 for p in c.pitches), c.pitches


def test_stave_with_harm_but_no_notes_sounds_the_voicing():
    score = compile_src("@key C minor\nstave pad {\n  harm | i9 | iv7 |\n}\n")
    st = stave(score, "pad")
    assert st.notes
    assert {n.voice for n in st.notes} == {None}
    for c in st.chords:
        sounding = sorted(n.pitch for n in st.notes
                          if abs(n.start - c.start) < 1e-6)
        assert sounding == c.pitches


def test_voicing_definition_is_honoured():
    src = ("@key C minor\nvoicing three {{ range: C3..C5, mode: shell, size: 3 }}\n"
           "stave t {{\n  harm{opt} | i9 | iv9 |\n}}\n")
    plain = compile_src(src.format(opt=""))
    shell = compile_src(src.format(opt="!voicing=three"))
    assert all(len(c.pitches) == 3 for c in stave(shell, "t").chords)
    assert stave(plain, "t").chords[0].pitches != stave(shell, "t").chords[0].pitches


def test_smooth_voicing_leads_smoothly():
    score = compile_src("@key C minor\nvoicing s { mode: smooth, size: 4 }\n"
                        "stave t {\n  harm!voicing=s | ii7b5 | V7 | i9 |\n}\n")
    chords = stave(score, "t").chords
    for a, b in zip(chords, chords[1:]):
        moves = [abs(x - y) for x, y in zip(a.pitches, b.pitches)]
        assert max(moves) <= 5, (a.symbol, b.symbol, a.pitches, b.pitches)


def test_chord_tones_and_anchors_follow_the_harmony():
    score = compile_src(
        "@key C minor\nstave t {\n  harm  | i9 | IV^7 |\n"
        "  notes | ~1 ~3 ~5 ~7 | @root @guide @low @high |\n}\n")
    st = stave(score, "t")
    i9 = st.chords[0]
    for n in st.notes[:4]:
        assert n.pitch % 12 in i9.pitch_classes, (n.pitch, i9.pitch_classes)
    iv = st.chords[1]
    bar2 = [n for n in st.notes if n.start >= 4.0]
    assert bar2[0].pitch % 12 == iv.root_pc
    assert bar2[1].pitch % 12 in iv.guide_tones
    assert min(n.pitch for n in bar2) >= 0
    assert bar2[2].pitch == min(iv.pitches)
    assert bar2[3].pitch == max(iv.pitches)


def test_modal_interchange_changes_the_chord():
    a = compile_src("@key C minor\nstave t {\n  harm | iv7 |\n}\n")
    b = compile_src("@key C minor\nstave t {\n  harm | IVd |\n}\n")
    assert stave(a, "t").chords[0].pitch_classes != stave(b, "t").chords[0].pitch_classes


def test_harmonic_silence_keeps_the_previous_context_for_targets():
    score = compile_src("@key C minor\nstave t {\n  harm  | i9 | . |\n"
                        "  notes | 0 . . . | ~3 . . . |\n}\n")
    st = stave(score, "t")
    assert len(st.chords) == 1
    late = note_at(st, 4.0)
    assert late.pitch % 12 in st.chords[0].pitch_classes


# --------------------------------------------------------------------------- #
# 7. curve lanes
# --------------------------------------------------------------------------- #

def test_curve_lane_glyph_levels_hit_the_lane_range():
    score = compile_src("stave t {\n  notes | 0 - - - |\n  press | _--^ |\n}\n")
    pts = finite(note_at(stave(score, "t"), 0.0).curves["press"])
    vals = [v for _t, v in pts]
    assert min(vals) == pytest.approx(0.0, abs=1e-6)
    assert max(vals) == pytest.approx(1.0, abs=1e-6)


def test_bend_lane_is_bipolar_and_respects_an_explicit_range():
    score = compile_src("stave t {\n  notes | 0 - |\n  bend!range=6st | v^ |\n}\n")
    vals = [v for _t, v in finite(note_at(stave(score, "t"), 0.0).curves["bend"])]
    assert min(vals) == pytest.approx(-6.0, abs=1e-6)
    assert max(vals) == pytest.approx(6.0, abs=1e-6)


def test_bend_lane_is_sampled_at_half_the_grid_of_other_lanes():
    src = ("@grid 40ms\nstave t {\n  notes | 0 - - - |\n"
           "  bend  | 0246 |\n  press | 0246 |\n}\n")
    n = note_at(stave(compile_src(src), "t"), 0.0)
    bend_t = [t for t, _v in finite(n.curves["bend"])]
    press_t = [t for t, _v in finite(n.curves["press"])]
    assert len(bend_t) > len(press_t)


def test_absent_lane_writes_no_curve_at_all():
    score = compile_src("stave t {\n  notes | 0 |\n  press | ^ |\n}\n")
    n = note_at(stave(score, "t"), 0.0)
    assert set(n.curves) == {"press"}


def test_empty_bar_in_a_curve_lane_writes_no_data():
    score = compile_src("stave t {\n  notes  | 0 | 0 |\n  timbre | ^ | |\n}\n")
    st = stave(score, "t")
    assert finite(note_at(st, 0.0).curves["timbre"])
    assert "timbre" not in note_at(st, 4.0).curves


def test_one_drawn_bar_is_sliced_across_notes_of_different_lengths():
    score = compile_src("stave t {\n  notes | 0 - 2 3 |\n  press | ____^^^^ |\n}\n")
    st = stave(score, "t")
    held = note_at(st, 0.0)
    late = note_at(st, 3.0)
    assert held.dur == pytest.approx(2.0)
    assert max(v for _t, v in finite(held.curves["press"])) < 0.6
    assert min(v for _t, v in finite(late.curves["press"])) > 0.9


def test_time_note_gives_every_note_the_whole_shape():
    score = compile_src(
        "stave t {\n  notes           | 0 - 2 3 |\n  press!time=note | _^ |\n}\n")
    for n in stave(score, "t").notes:
        vals = [v for _t, v in finite(n.curves["press"])]
        assert min(vals) == pytest.approx(0.0, abs=1e-6)
        assert max(vals) == pytest.approx(1.0, abs=1e-6)


def test_at_voice_lane_targets_only_that_voice():
    score = compile_src(
        "@key C minor\nstave t {\n"
        "  voices     | { bass: 0 ; lead: ^0 } |\n"
        "  press@lead | _^ |\n}\n")
    st = stave(score, "t")
    assert "press" in note_at(st, 0.0, voice="lead").curves
    assert "press" not in note_at(st, 0.0, voice="bass").curves


def test_named_voices_are_recorded_on_the_notes():
    score = compile_src("stave t {\n  voices | { bass: 0 ; mid: 2 ; lead: 4 } |\n}\n")
    st = stave(score, "t")
    assert {n.voice for n in st.notes} == {"bass", "mid", "lead"}


def test_cc_lane_is_a_curve_lane():
    score = compile_src("stave t {\n  notes | 0 - |\n  cc74 | _^ |\n}\n")
    assert "cc74" in note_at(stave(score, "t"), 0.0).curves
    assert is_curve_lane("cc74") and not is_curve_lane("notes")


# --------------------------------------------------------------------------- #
# 8. harmonic targets (`>`), the load-bearing feature
# --------------------------------------------------------------------------- #

def test_target_third_lands_exactly_on_the_next_chords_third():
    # T2 from refs/syntax/tasks.md: D5 bends up into Eb5, the 3rd of Cm9.
    score = compile_src(
        "@key C minor\nstave t {\n"
        "  harm           | V7 | i9 |\n"
        "  notes          | . . . D5 | ~3 - - - |\n"
        "  bend!range=4st | xxx>3 | |\n}\n")
    st = stave(score, "t")
    bent = note_at(st, 3.0)
    assert bent.pitch == 74
    end = bent.curves["bend"].points[-1][1]
    assert end == pytest.approx(1.0, abs=1e-6)
    assert round(bent.pitch + end) == 75               # Eb5
    assert 75 % 12 == st.chords[1].pitch_classes[1]    # ...the 3rd of Cm9


def test_bare_target_aims_at_a_guide_tone():
    score = compile_src(
        "@key C minor\nstave t {\n  harm | i9 | V7 |\n"
        "  notes | . . . 0 | 0 - - - |\n  bend!range=12st | xxx> | |\n}\n")
    st = stave(score, "t")
    n = note_at(st, 3.0)
    dest = round(n.pitch + n.curves["bend"].points[-1][1])
    assert dest % 12 in st.chords[1].guide_tones


def test_step_targets_move_one_scale_degree():
    score = compile_src(
        "@key C major\nstave t {\n  notes | 0 - | 0 - |\n"
        "  bend!range=4st | xx>+ | xx>- |\n}\n")
    st = stave(score, "t")
    up = note_at(st, 0.0).curves["bend"].points[-1][1]
    down = note_at(st, 4.0).curves["bend"].points[-1][1]
    assert up == pytest.approx(2.0, abs=1e-6)     # C -> D
    assert down == pytest.approx(-1.0, abs=1e-6)  # C -> B


def test_next_note_target_lands_on_the_following_pitch():
    score = compile_src(
        "@key C major\nstave t {\n  notes | 0 4 |\n  bend!range=12st | >|x |\n}\n")
    st = stave(score, "t")
    a, b = st.notes[0], st.notes[1]
    reached = a.pitch + finite(a.curves["bend"])[-1][1]
    assert reached == pytest.approx(float(b.pitch), abs=1e-4)


def test_unreachable_target_is_clamped_with_one_warning():
    score = compile_src(
        "@key C minor\nstave t {\n  harm | i9 | V7 |\n"
        "  notes | 0 - - - | 0 - - - |\n  bend!range=0.5st | >3 | |\n}\n")
    n = note_at(stave(score, "t"), 0.0)
    assert all(abs(v) <= 0.5 + 1e-9 for _t, v in finite(n.curves["bend"]))
    clamps = [w for w in score.warnings if "cannot reach" in w]
    assert len(clamps) == 1, score.warnings


def test_target_on_a_non_bend_lane_is_a_parse_error():
    from filigree import errors
    with pytest.raises(errors.FiligreeError):
        compile_src("stave t {\n  notes | 0 |\n  press | > |\n}\n")


# --------------------------------------------------------------------------- #
# 9. gestures
# --------------------------------------------------------------------------- #

def test_attached_gesture_writes_its_own_lanes():
    score = compile_src(
        "gesture warm = press(0.2 -> 0.9) | timbre(0.4 -> 0.7)\n"
        "stave t {\n  notes | 0!warm - - - |\n}\n")
    n = note_at(stave(score, "t"), 0.0)
    assert set(n.curves) == {"press", "timbre"}
    assert finite(n.curves["press"])[-1][1] == pytest.approx(0.9, abs=0.02)


def test_gesture_parameter_override_on_one_note_only():
    score = compile_src(
        "gesture vib(depth: 0.2st) = bend(wiggle(6hz, depth))\n"
        "stave t {\n  notes | 0!vib 2!vib(depth: 0.9st) 4!vib 5!vib |\n}\n")
    st = stave(score, "t")
    spans = [max(abs(v) for _t, v in finite(n.curves["bend"])) for n in st.notes]
    assert spans[1] > 3 * spans[0]
    assert spans[0] == pytest.approx(spans[2], rel=0.5)


def test_lane_level_and_stave_level_gesture_attachment():
    lane = compile_src("gesture g = press(0 -> 1)\n"
                       "stave t {\n  notes!gesture=g | 0 2 |\n}\n")
    st_lvl = compile_src("gesture g = press(0 -> 1)\n"
                         "stave t {\n  gesture g\n  notes | 0 2 |\n}\n")
    for score in (lane, st_lvl):
        for n in stave(score, "t").notes:
            assert "press" in n.curves


def test_explicit_lane_glyphs_beat_an_attached_gesture():
    score = compile_src(
        "gesture flat = press(const(0.1))\n"
        "stave t {\n  notes!gesture=flat | 0 - |\n  press | ^^ |\n}\n")
    vals = [v for _t, v in finite(note_at(stave(score, "t"), 0.0).curves["press"])]
    assert min(vals) > 0.9, vals


def test_attached_gesture_fills_lanes_the_glyphs_do_not_cover():
    score = compile_src(
        "gesture warm = press(const(0.3)) | timbre(const(0.8))\n"
        "stave t {\n  notes!gesture=warm | 0 - |\n  press | ^^ |\n}\n")
    n = note_at(stave(score, "t"), 0.0)
    assert min(v for _t, v in finite(n.curves["press"])) > 0.9
    assert finite(n.curves["timbre"])[0][1] == pytest.approx(0.8, abs=0.02)


def test_inline_gesture_call_inside_a_curve_lane():
    score = compile_src(
        "gesture vib(depth: 0.6st) = bend(wiggle(8hz, depth))\n"
        "stave t {\n  notes | 0 - - - |\n  bend!range=2st | __vib()__ |\n}\n")
    pts = finite(note_at(stave(score, "t"), 0.0).curves["bend"])
    mid = [v for t, v in pts if 1.4 < t < 2.4]
    assert mid and max(abs(v) for v in mid) > 0.2


def test_gesture_algebra_scale_and_window():
    plain = compile_src("gesture c = bend(0 -> -1st -> 0)\n"
                        "stave t {\n  notes | 0!c - - - |\n}\n")
    scaled = compile_src("gesture c = bend(0 -> -1st -> 0)\ngesture d = c * 2\n"
                         "stave t {\n  notes | 0!d - - - |\n}\n")
    win = compile_src("gesture c = bend(0 -> -1st -> 0)\ngesture d = c @ 50%..100%\n"
                      "stave t {\n  notes | 0!d - - - |\n}\n")
    depth = lambda s: max(abs(v) for _t, v in finite(  # noqa: E731
        note_at(stave(s, "t"), 0.0).curves["bend"]))
    assert depth(scaled) == pytest.approx(2 * depth(plain), rel=0.05)
    first = finite(note_at(stave(win, "t"), 0.0).curves["bend"])[0][0]
    assert first >= 1.9


# --------------------------------------------------------------------------- #
# 10. "no data": NaN must never become a written value
# --------------------------------------------------------------------------- #

def test_windowed_gesture_leaves_a_nan_hole_before_its_onset():
    score = compile_src(
        "gesture late = bend(wiggle(6hz, 0.4st) @ 50%..100%)\n"
        "stave t {\n  notes | 0!late - - - |\n}\n")
    curve = note_at(stave(score, "t"), 0.0).curves["bend"]
    assert math.isnan(curve.points[0][1]), curve.points[:3]
    assert curve.points[0][0] == pytest.approx(0.0)
    assert finite(curve)[0][0] >= 1.9


def test_nan_regions_emit_no_midi_frames(tmp_path):
    mido = pytest.importorskip("mido")
    score = compile_src(
        "@tempo 60\ngesture late = bend(wiggle(6hz, 0.4st) @ 50%..100%)\n"
        "stave t {\n  notes | 0!late - - - |\n}\n")
    out = str(tmp_path / "hole.mid")
    filigree.write_midi(score, out)
    mf = mido.MidiFile(out)
    moved = []
    for track in mf.tracks:
        t = 0
        for m in track:
            t += m.time
            if m.type == "pitchwheel" and m.pitch != 0:
                moved.append(t / mf.ticks_per_beat)
    assert moved, "the second half of the note should bend"
    # the note is 4 beats long; the gesture window opens halfway through it
    assert min(moved) >= 1.9, moved[:5]


def test_curve_value_at_returns_nan_inside_a_hole():
    score = compile_src(
        "gesture late = bend(wiggle(6hz, 0.4st) @ 50%..100%)\n"
        "stave t {\n  notes | 0!late - - - |\n}\n")
    c = score.notes[0].curves["bend"]
    assert math.isnan(c.value_at(0.1))
    assert not math.isnan(c.value_at(3.5))


def test_a_gesture_that_is_nan_everywhere_attaches_no_curve():
    score = compile_src(
        "gesture nothing = press(const(0.5)) * bend(const(1))\n"
        "stave t {\n  notes | 0!nothing - |\n}\n")
    assert score.notes[0].curves == {} or "press" not in score.notes[0].curves


# --------------------------------------------------------------------------- #
# 11. warnings policy (lead's ruling 7)
# --------------------------------------------------------------------------- #

def test_curve_lane_inexact_anchor_count_warns():
    """SPEC §12 (amended): an inexact curve-lane resampling is a warning."""
    score = compile_src(
        "stave t {\n  notes | 0 2 4 5 |\n  bend  | ___/^^^ |\n"
        "  press | ^^^^^ |\n  timbre | ___ |\n}\n")
    msgs = "\n".join(score.warnings)
    assert "lane 'bend' has 7 anchors but lane 'notes' has 4 slots" in msgs
    assert "lane 'press' has 5 anchors but lane 'notes' has 4 slots" in msgs
    assert "lane 'timbre' has 3 anchors but lane 'notes' has 4 slots" in msgs
    for w in score.warnings:
        assert re.match(r"^[^\s:]+:\d+:\d+: warning: ", w), w
        assert "resampled" in w


def test_curve_lane_exact_anchor_ratio_stays_silent():
    for run in ("^^^^", "^^^^^^^^", "^^", "^"):
        score = compile_src(
            "stave t {\n  notes | 0 2 4 5 |\n  bend | %s |\n}\n" % run)
        assert score.warnings == [], (run, score.warnings)


def test_time_note_curve_lane_does_not_warn_about_columns():
    score = compile_src(
        "stave t {\n  notes | 0 2 4 5 |\n  press!time=note | _/^\\ |\n"
        "  timbre!time=note | _/^^^ |\n}\n")
    assert score.warnings == [], score.warnings


def test_unknown_chord_symbol_is_a_hard_error_with_line_and_col():
    """SPEC §12 (amended): a chord typo must never silently delete a bar."""
    src = ("@key C minor\nstave t {\n"
           "  harm | ii7b5 | Vsus9alt13 | i9 |\n  notes | 0 | 0 | 0 |\n}\n")
    with pytest.raises(errors.HarmonyError) as e:
        resolve(parse(src, "bad.fil"))
    msg = str(e.value)
    assert "Vsus9alt13" in msg
    text = e.value.render() if hasattr(e.value, "render") else msg
    assert re.search(r"bad\.fil:3:\d+: error: ", text), text
    assert "lenient" in text


def test_lenient_downgrades_a_chord_typo_and_sustains_the_previous_chord():
    src = ("@key C minor\nstave t {\n"
           "  harm | ii7b5 | Vsus9alt13 | i9 |\n  notes | 0 | 0 | 0 |\n}\n")
    score = resolve(parse(src, "bad.fil"), lenient=True)
    msgs = "\n".join(score.warnings)
    assert "Vsus9alt13" in msgs and "sustaining the previous chord" in msgs
    ch = stave(score, "t").chords
    syms = [(c.symbol, c.start, c.start + c.dur) for c in ch]
    assert [s for s, _a, _b in syms] == ["ii7b5", "i9"], syms
    # the typo'd bar keeps sounding bar 1's chord instead of vanishing
    assert syms[0][2] == pytest.approx(8.0)
    assert syms[1][1] == pytest.approx(8.0)
    # and no bar of music disappears
    assert len(stave(score, "t").notes) == 3


def test_lenient_defaults_to_false():
    import inspect
    sig = inspect.signature(resolve)
    assert sig.parameters["lenient"].default is False


def test_unrecognised_lane_option_warns_instead_of_being_ignored():
    score = compile_src("stave t {\n  notes!oct=5 | 0 |\n  press | ^ |\n}\n")
    msgs = "\n".join(score.warnings)
    assert "'oct'" in msgs and "no effect" in msgs


def test_note_bearing_lane_slot_mismatch_still_warns():
    score = compile_src("stave t {\n  notes | 0 2 4 5 |\n  notes@b | 0 2 4 |\n}\n")
    assert any("slots" in w for w in score.warnings), score.warnings


def test_bar_count_mismatch_still_warns():
    # LEAD RULING (round 3): a one-bar figure under a two-bar phrase cycles silently;
    # only a bar count that cannot cycle evenly warns.
    score = compile_src("stave t {\n  notes | 0 | 2 |\n  press | ^ |\n}\n")
    assert not any("bars" in w for w in score.warnings), score.warnings
    score = compile_src("stave t {\n  notes | 0 | 2 | 4 | 6 |\n  press | ^ | _ | ^ |\n}\n")
    assert any("bars" in w for w in score.warnings), score.warnings


def test_every_curve_lane_name_is_recognised():
    for lane in CURVE_LANES:
        assert is_curve_lane(lane)
    assert is_curve_lane("cc1") and is_curve_lane("cc127")
    assert not is_curve_lane("harm") and not is_curve_lane("voices")


# --------------------------------------------------------------------------- #
# 12. feel, ids, ordering, amp
# --------------------------------------------------------------------------- #

def test_feel_moves_notes_off_the_grid_without_changing_pitch():
    tight = compile_src("stave t {\n  notes | 0 2 4 5 |\n}\n")
    loose = compile_src("@seed 3\nfeel l = { timing: 25ms gauss }\n"
                        "stave t {\n  feel l\n  notes | 0 2 4 5 |\n}\n")
    assert [n.pitch for n in tight.notes] == [n.pitch for n in loose.notes]
    offsets = [abs(a.start - b.start) for a, b in zip(tight.notes, loose.notes)]
    assert max(offsets) > 1e-4
    assert max(offsets) < 0.5


def test_feel_presets_are_available_by_name():
    score = compile_src("stave t {\n  feel loose\n  notes | 0 2 4 5 |\n}\n")
    assert score.notes and score.warnings == []


def test_unknown_feel_warns_and_does_not_raise():
    score = compile_src("stave t {\n  feel nope\n  notes | 0 |\n}\n")
    assert any("unknown feel" in w for w in score.warnings)


def test_note_ids_are_unique_and_sequential():
    path = os.path.join(EXAMPLES, "reference.fil")
    score = filigree.compile_source(open(path).read(), path)
    ids = sorted(n.id for n in score.notes)
    assert ids == list(range(1, len(ids) + 1))


def test_score_notes_are_sorted_by_start_then_pitch():
    path = os.path.join(EXAMPLES, "pulse.fil")
    score = filigree.compile_source(open(path).read(), path)
    keys = [(round(n.start, 6), n.pitch) for n in score.notes]
    assert keys == sorted(keys)


def test_amp_lane_sets_note_on_velocity():
    quiet = compile_src("stave t {\n  notes | 0 - |\n  amp | 11 |\n}\n")
    loud = compile_src("stave t {\n  notes | 0 - |\n  amp | 99 |\n}\n")
    assert quiet.notes[0].velocity < loud.notes[0].velocity
    assert loud.notes[0].velocity > 120


def test_after_offsets_a_stave_to_the_end_of_another():
    score = compile_src("stave a {\n  notes | 0 | 2 |\n}\n"
                        "stave b {\n  after a\n  notes | 4 |\n}\n")
    assert min(n.start for n in stave(score, "b").notes) == pytest.approx(8.0)


def test_unknown_after_target_warns():
    score = compile_src("stave b {\n  after ghost\n  notes | 0 |\n}\n")
    assert any("unknown stave" in w for w in score.warnings)


# --------------------------------------------------------------------------- #
# 13. parts and transforms
# --------------------------------------------------------------------------- #

def test_play_appends_a_part_and_transpose_does_not_mutate_it():
    score = compile_src(
        "@key C major\npart hook {\n  notes | 0 2 |\n}\n"
        "stave t {\n  play hook\n  play hook >> transpose(2)\n}\n")
    pitches = [n.pitch for n in stave(score, "t").notes]
    assert pitches[:2] == [60, 64]
    assert pitches[2:] == [64, 67]


def test_retro_reverses_a_part():
    score = compile_src("@key C major\npart hook {\n  notes | 0 2 4 5 |\n}\n"
                        "stave t {\n  play hook >> retro\n}\n")
    assert [n.pitch for n in stave(score, "t").notes] == [69, 67, 64, 60]


def test_unknown_transform_warns_but_still_plays():
    score = compile_src("part hook {\n  notes | 0 2 |\n}\n"
                        "stave t {\n  play hook >> euclid(3, 8)\n}\n")
    assert len(score.notes) == 2
    assert any("not implemented" in w for w in score.warnings)


def test_unknown_part_warns():
    score = compile_src("stave t {\n  notes | 0 |\n  play ghost\n}\n")
    assert any("unknown part" in w for w in score.warnings)


# --------------------------------------------------------------------------- #
# 14. MIDI round trip details
# --------------------------------------------------------------------------- #

def test_rendered_midi_has_one_track_per_stave(tmp_path):
    mido = pytest.importorskip("mido")
    score = compile_src("stave a {\n  notes | 0 |\n}\nstave b {\n  notes | 4 |\n}\n")
    out = str(tmp_path / "two.mid")
    filigree.write_midi(score, out)
    mf = mido.MidiFile(out)
    names = [t.name for t in mf.tracks]
    assert "a" in names and "b" in names


def test_rendered_midi_contains_expression_for_a_drawn_curve(tmp_path):
    mido = pytest.importorskip("mido")
    score = compile_src("stave t {\n  notes | 0 - - - |\n"
                        "  bend!range=2st | _/^\\_ |\n  press | __/^^ |\n}\n")
    out = str(tmp_path / "e.mid")
    filigree.write_midi(score, out)
    msgs = [m for t in mido.MidiFile(out).tracks for m in t]
    assert any(m.type == "pitchwheel" for m in msgs)
    assert any(m.type == "control_change" and m.control == 74 for m in msgs) or \
        any(m.type == "aftertouch" for m in msgs)


def test_cli_render_writes_a_file(tmp_path):
    out = str(tmp_path / "cli.mid")
    from filigree import cli
    rc = cli.main(["render", os.path.join(EXAMPLES, "nocturne.fil"), "-o", out])
    assert rc == 0
    assert os.path.getsize(out) > 100


def test_cli_json_round_trips_through_the_score():
    from filigree import cli
    rc = cli.main(["json", os.path.join(EXAMPLES, "reference.fil")])
    assert rc == 0
    path = os.path.join(EXAMPLES, "reference.fil")
    score = filigree.compile_source(open(path).read(), path)
    blob = json.dumps(score.to_json())
    assert '"staves"' in blob and "NaN" not in blob


def test_cli_explain_runs_on_every_example():
    from filigree import cli
    for name in EXAMPLE_FILES:
        assert cli.main(["explain", os.path.join(EXAMPLES, name)]) == 0


# --------------------------------------------------------------------------- #
# diagnostics plumbing: every stage reports through score.warnings
# --------------------------------------------------------------------------- #

def test_feel_warnings_land_in_score_warnings_not_stderr():
    import warnings as _w
    src = ("@tempo 120\n@key C major\nfeel wild { timing: 900ms }\n"
           "stave a {\n  feel wild\n"
           "  notes | 0 2 4 5 | 7 5 4 2 | 0 2 4 5 | 7 5 4 2 |\n}\n")
    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        score = compile_src(src, "wild.fil")
    feel_warns = [w for w in score.warnings if "feel:" in w]
    assert feel_warns, score.warnings
    # named like every other diagnostic: file, line of the stave, 'warning:'
    assert all(w.startswith("wild.fil:") and ": warning: " in w for w in feel_warns)
    assert all(":0:0:" not in w for w in feel_warns), feel_warns
    # ...and not duplicated onto the Python warnings channel
    assert not [w for w in caught if "feel" in str(w.message)]


def test_mpe_warnings_name_the_source_file(tmp_path):
    path = os.path.join(EXAMPLES, "reference.fil")
    score = filigree.compile_source(open(path).read(), path)
    filigree.write_midi(score, str(tmp_path / "ref.mid"))
    mpe = [w for w in score.warnings if "MPE:" in w]
    assert mpe, "reference.fil is expected to trip the expression-rate advisory"
    assert all(w.startswith(path + ":") for w in mpe), mpe
    assert not any(w.startswith("<input>") for w in score.warnings)


def test_cli_new_template_compiles_without_warnings(tmp_path):
    from filigree import cli
    path = str(tmp_path / "starter.fil")
    assert cli.main(["new", path]) == 0
    score = filigree.compile_source(open(path).read(), path)
    assert score.notes
    assert score.warnings == [], score.warnings
    # the template must not define things it does not use
    src = open(path).read()
    for m in re.finditer(r"^gesture\s+(\w+)", src, re.M):
        assert src.count(m.group(1)) > 1, f"gesture {m.group(1)!r} is defined but unused"
