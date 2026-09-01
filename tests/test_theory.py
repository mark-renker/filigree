"""P2 harmony tests.

The bulk of the correctness work is data-driven: ``refs/specs/harmony_truth.md``
holds a 90+ row ground-truth table of "symbol in key -> expected pitch classes",
derived from music theory first principles, and this file parses that file and
asserts every row. Any wrong pitch class fails.
"""

from __future__ import annotations

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from filigree import errors  # noqa: E402
from filigree.ast_nodes import Pos  # noqa: E402
from filigree import theory as T  # noqa: E402

TRUTH = os.path.join(os.path.dirname(__file__), "..", "refs", "specs",
                     "harmony_truth.md")

_ROW = re.compile(
    r"^\|\s*(\d+)\s*\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|"
    r"\s*([0-9 ]+?)\s*\|\s*([0-9]+|-)\s*\|\s*$"
)
_GT_ROW = re.compile(
    r"^\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|\s*([0-9 ]+?)\s*\|\s*$"
)


def _read_truth() -> tuple[list[tuple], list[tuple]]:
    chords: list[tuple] = []
    guides: list[tuple] = []
    with open(TRUTH, encoding="utf-8") as fh:
        for line in fh:
            m = _ROW.match(line)
            if m:
                idx, sym, key, _notes, pcs, bass = m.groups()
                chords.append((int(idx), sym, key.strip(),
                               [int(x) for x in pcs.split()],
                               None if bass == "-" else int(bass)))
                continue
            g = _GT_ROW.match(line)
            if g and g.group(1) not in ("Symbol",):
                sym, key, pcs = g.groups()
                guides.append((sym, key.strip(), [int(x) for x in pcs.split()]))
    return chords, guides


TRUTH_ROWS, GUIDE_ROWS = _read_truth()


def _parse(sym: str, key: str) -> T.Chord:
    if key == "-":
        return T.parse_absolute(sym)
    tonic, mode = key.split(" ", 1)
    return T.parse_roman(sym, T.NOTE_NAMES[tonic[0]], mode)


# ---------------------------------------------------------------------------
# the ground-truth table (one assertion per row, 90+ rows)
# ---------------------------------------------------------------------------


def test_truth_table_is_big_enough():
    assert len(TRUTH_ROWS) >= 40, "harmony_truth.md must carry 40+ rows"
    assert len(GUIDE_ROWS) >= 8


@pytest.mark.parametrize("row", TRUTH_ROWS, ids=lambda r: f"{r[0]}-{r[1]}")
def test_truth_table_pitch_classes(row):
    idx, sym, key, expected, bass = row
    chord = _parse(sym, key)
    got = chord.pitch_classes()
    assert sorted(got) == sorted(expected), (
        f"row {idx}: {sym} in {key}: expected {sorted(expected)} got {sorted(got)}")
    assert got[0] == expected[0], (
        f"row {idx}: {sym}: pitch classes must start on the root")
    assert chord.bass_pc == bass, f"row {idx}: {sym}: bass"
    assert chord.symbol == sym


@pytest.mark.parametrize("row", GUIDE_ROWS, ids=lambda r: f"gt-{r[0]}")
def test_truth_table_guide_tones(row):
    sym, key, expected = row
    chord = _parse(sym, key)
    assert chord.guide_tones() == expected, f"{sym} in {key}"


# ---------------------------------------------------------------------------
# scales
# ---------------------------------------------------------------------------


def test_all_spec_modes_present():
    for name in ("major", "ionian", "dorian", "phrygian", "lydian",
                 "mixolydian", "minor", "aeolian", "locrian", "harmonic-minor",
                 "melodic-minor", "whole-tone", "chromatic", "blues"):
        assert name in T.MODES, name


def test_mode_offsets_start_on_zero_and_ascend():
    for name, offs in T.MODES.items():
        assert offs[0] == 0, name
        assert list(offs) == sorted(offs), name
        assert offs[-1] < 12, name


def test_scale_pitches_major_and_minor():
    assert T.scale_pitches(0, "major") == [0, 2, 4, 5, 7, 9, 11]
    assert T.scale_pitches(9, "minor") == [9, 11, 0, 2, 4, 5, 7]
    assert T.scale_pitches(7, "mixolydian") == [7, 9, 11, 0, 2, 4, 5]


def test_scale_pitches_exotic():
    assert T.scale_pitches(0, "whole-tone") == [0, 2, 4, 6, 8, 10]
    assert T.scale_pitches(0, "blues") == [0, 3, 5, 6, 7, 10]
    assert T.scale_pitches(0, "harmonic-minor") == [0, 2, 3, 5, 7, 8, 11]
    assert T.scale_pitches(0, "melodic-minor") == [0, 2, 3, 5, 7, 9, 11]
    assert len(T.scale_pitches(3, "chromatic")) == 12


def test_mode_aliases_and_unknown_mode():
    assert T.scale_pitches(0, "MAJ") == T.scale_pitches(0, "major")
    assert T.scale_pitches(0, "harmonic minor") == T.scale_pitches(0, "harmonic-minor")
    with pytest.raises(errors.HarmonyError) as e:
        T.scale_pitches(0, "hypolocrian")
    assert e.value.suggestion


def test_note_names():
    assert T.NOTE_NAMES == {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9,
                            "B": 11}


# ---------------------------------------------------------------------------
# degree_to_pitch / nearest_pc
# ---------------------------------------------------------------------------


def test_degree_to_pitch_is_zero_based_with_c4_at_60():
    assert T.degree_to_pitch(0, 0, "major", 4) == 60
    assert T.degree_to_pitch(1, 0, "major", 4) == 62
    assert T.degree_to_pitch(7, 0, "major", 4) == 72
    assert T.degree_to_pitch(-1, 0, "major", 4) == 59
    assert T.degree_to_pitch(-7, 0, "major", 4) == 48


def test_degree_to_pitch_octave_and_accidental():
    assert T.degree_to_pitch(0, 0, "major", 3) == 48
    assert T.degree_to_pitch(0, 0, "major", 5) == 72
    assert T.degree_to_pitch(2, 0, "major", 4, accidental=-1) == 63
    assert T.degree_to_pitch(2, 0, "minor", 4) == 63


def test_degree_to_pitch_short_scales_wrap():
    # whole-tone has six notes: degree 6 is the octave
    assert T.degree_to_pitch(6, 0, "whole-tone", 4) == 72
    assert T.degree_to_pitch(6, 0, "blues", 4) == 72


def test_nearest_pc():
    assert T.nearest_pc(0, 60) == 60
    assert T.nearest_pc(11, 60) == 59
    assert T.nearest_pc(1, 60) == 61
    assert T.nearest_pc(7, 60) == 55
    assert T.nearest_pc(5, 60) == 65
    # a tritone away resolves upward, deterministically
    assert T.nearest_pc(6, 60) == 66
    for pc in range(12):
        p = T.nearest_pc(pc, 64)
        assert p % 12 == pc and abs(p - 64) <= 6


# ---------------------------------------------------------------------------
# Chord behaviour
# ---------------------------------------------------------------------------


def test_intervals_include_root_and_ascend():
    for sym in ("V7", "i9", "iv11", "V7alt", "I6/9", "viio7"):
        c = T.parse_roman(sym, 0, "minor")
        assert c.intervals[0] == 0
        assert list(c.intervals) == sorted(c.intervals)
        assert len(set(c.intervals)) == len(c.intervals)


def test_degree_pc_lookup():
    c = T.parse_roman("V7", 0, "major")          # G B D F
    assert c.degree_pc(1) == 7
    assert c.degree_pc(3) == 11
    assert c.degree_pc(5) == 2
    assert c.degree_pc(7) == 5
    assert c.degree_pc(9) is None
    assert c.degree_pc(13) is None


def test_degree_pc_extensions_and_alterations():
    c = T.parse_roman("iv11", 0, "minor")        # F Ab C Eb G Bb
    assert c.degree_pc(9) == 7
    assert c.degree_pc(11) == 10
    alt = T.parse_absolute("Galt")
    assert alt.degree_pc(9) == 8                 # b9 = Ab
    assert alt.degree_pc(11) == 1                # #11 = C#
    assert alt.degree_pc(13) == 3                # b13 = Eb
    assert alt.degree_pc(5) is None              # alt has no perfect fifth


def test_degree_pc_folds_compound_onto_simple():
    six = T.parse_roman("I6/9", 0, "major")      # C E G A D
    assert six.degree_pc(13) == 9                # the 6th answers for the 13th
    assert six.degree_pc(9) == 2
    sus = T.parse_roman("Isus4", 0, "major")
    assert sus.degree_pc(11) == 5                # the 4th answers for the 11th
    assert sus.degree_pc(3) is None


def test_guide_tones_fallbacks():
    assert T.parse_roman("V7", 0, "major").guide_tones() == [11, 5]
    assert T.parse_roman("I", 0, "major").guide_tones() == [4, 7]     # no 7th -> 5th
    assert T.parse_roman("I6", 0, "major").guide_tones() == [4, 9]    # 6th stands in
    assert T.parse_roman("Isus4", 0, "major").guide_tones() == [5, 7]
    assert len(T.parse_absolute("C5").guide_tones()) >= 1


def test_pitch_classes_deduplicates():
    c = T.parse_absolute("C7#9")   # #9 = D# which is not the minor 3rd here
    assert len(c.pitch_classes()) == len(set(c.pitch_classes()))


# ---------------------------------------------------------------------------
# roman numeral specifics
# ---------------------------------------------------------------------------


def test_case_sets_quality():
    assert T.parse_roman("II", 0, "major").quality == "maj"
    assert T.parse_roman("ii", 0, "major").quality == "min"
    assert T.parse_roman("ii7", 0, "major").quality == "min7"
    assert T.parse_roman("II7", 0, "major").quality == "dom7"
    assert T.parse_roman("II^7", 0, "major").quality == "maj7"
    assert T.parse_roman("ii0", 0, "major").quality == "dim"
    assert T.parse_roman("iio7", 0, "major").quality == "dim7"


def test_bare_seven_is_a_minor_seventh():
    """A bare `7` is the lead-sheet dominant 7th; `^7` is the major 7th."""
    assert 10 in T.parse_roman("I7", 0, "major").intervals
    assert 11 in T.parse_roman("I^7", 0, "major").intervals
    assert 11 not in T.parse_roman("I7", 0, "major").intervals


def test_x_forces_dominant_colour_regardless_of_case():
    a = T.parse_roman("IIx", 0, "major")
    b = T.parse_roman("iix", 0, "major")
    assert a.pitch_classes() == b.pitch_classes() == [2, 6, 9, 0]
    assert a.quality == "dom7"


def test_accidental_prefixes():
    assert T.parse_roman("bVI", 0, "major").root_pc == 8
    assert T.parse_roman("#iv", 0, "major").root_pc == 6
    assert T.parse_roman("bII", 0, "major").root_pc == 1
    # accidentals are chromatic: measured from the MAJOR degree in every mode
    assert T.parse_roman("bVI", 0, "minor").root_pc == 8
    assert T.parse_roman("bIII", 0, "dorian").root_pc == 3
    assert T.parse_roman("VI", 0, "minor").root_pc == 8
    # ... and only one of them is allowed
    with pytest.raises(errors.HarmonyError):
        T.parse_roman("bbVII", 0, "major")
    with pytest.raises(errors.HarmonyError):
        T.parse_roman("bbVI", 0, "major")


def test_extension_set_from_spec():
    """Every extension named in SPEC §4 parses and adds the right interval."""
    expect = {
        "I6": 9, "I7": 10, "I9": 14, "I11": 17, "I13": 21, "I^7": 11,
        "Iadd9": 14, "Isus2": 2, "Isus4": 5,
    }
    for sym, iv in expect.items():
        assert iv in T.parse_roman(sym, 0, "major").intervals, sym
    assert T.parse_roman("I0", 0, "major").intervals == (0, 3, 6)
    assert T.parse_roman("Io7", 0, "major").intervals == (0, 3, 6, 9)
    assert T.parse_roman("I6/9", 0, "major").intervals == (0, 4, 7, 9, 14)
    assert T.parse_roman("Ialt", 0, "major").quality == "alt"
    assert T.parse_roman("Ix", 0, "major").intervals == (0, 4, 7, 10)


def test_alteration_set_from_spec():
    expect = {"V7b5": 6, "V7#5": 8, "V7b9": 13, "V7#9": 15, "V7#11": 18,
              "V7b13": 20}
    for sym, iv in expect.items():
        assert iv in T.parse_roman(sym, 0, "major").intervals, sym


def test_ninths_imply_sevenths():
    for sym in ("V9", "V11", "V13", "V7b9", "V#11"):
        ivs = T.parse_roman(sym, 0, "major").intervals
        assert 10 in ivs or 11 in ivs, sym


def test_thirteenth_omits_the_eleventh():
    """Standard practice: a 13th chord is R 3 5 b7 9 13, no 11."""
    ivs = T.parse_roman("V13", 0, "major").intervals
    assert 17 not in ivs and 21 in ivs and 14 in ivs


def test_sus_replaces_the_third():
    for sym in ("Isus2", "Isus4"):
        c = T.parse_roman(sym, 0, "major")
        assert c.degree_pc(3) is None, sym
        assert 4 not in c.intervals and 3 not in c.intervals, sym


def test_alt_is_the_full_altered_dominant():
    c = T.parse_roman("V7alt", 0, "major")
    assert set(c.intervals) == {0, 4, 10, 13, 15, 18, 20}
    assert 7 not in c.intervals, "alt has no perfect fifth"
    assert T.parse_absolute("Galt").pitch_classes() == c.pitch_classes()


def test_secondary_dominants():
    assert T.parse_roman("V7/ii", 0, "major").pitch_classes() == [9, 1, 4, 7]
    assert T.parse_roman("V7/V", 0, "major").pitch_classes() == [2, 6, 9, 0]
    assert T.parse_roman("V7/IV", 0, "major").pitch_classes() == [0, 4, 7, 10]
    # the applied key is read in the *home* key/mode
    assert T.parse_roman("V/bIII", 0, "major").root_pc == 10
    assert T.parse_roman("V7/ii", 0, "major").symbol == "V7/ii"


def test_secondary_dominant_in_minor_key():
    # in C minor, ii is D (aeolian 2nd), so V7/ii is A7
    assert T.parse_roman("V7/ii", 0, "minor").pitch_classes() == [9, 1, 4, 7]


def test_modal_interchange_letters_all_parse():
    roots = {}
    for letter, mode in T.MODAL_INTERCHANGE_LETTERS.items():
        c = T.parse_roman("III" + letter, 0, "major")
        roots[letter] = c.root_pc
        assert c.root_pc == (T.degree_pc_of_scale(3, 0, mode)), letter
    assert roots["n"] == 4 and roots["d"] == 3 and roots["f"] == 3
    assert roots["y"] == 4 and roots["m"] == 4 and roots["a"] == 3


def test_modal_interchange_is_diatonic_to_the_borrowed_scale():
    """RULING: the mode letter picks the scale; the chord is that scale's own.

    C dorian is C D Eb F G A Bb, so the chord on its third degree is Eb G Bb --
    a major triad -- whichever case the numeral is written in.  The case is
    validated, not obeyed (see refs/specs/harmony_truth.md).
    """
    assert T.parse_roman("iiid", 0, "major").pitch_classes() == [3, 7, 10]
    assert T.parse_roman("IIId", 0, "major").pitch_classes() == [3, 7, 10]
    assert T.parse_roman("iiid", 0, "minor").pitch_classes() == [3, 7, 10]
    # phrygian's iv is minor, so `IVf` is minor too
    assert T.parse_roman("IVf", 0, "major").pitch_classes() == [5, 8, 0]
    assert T.parse_roman("ivf", 0, "major").pitch_classes() == [5, 8, 0]
    # sevenths and extensions are stacked from the same scale
    assert T.parse_roman("ii7d", 0, "major").pitch_classes() == [2, 5, 9, 0]
    assert T.parse_roman("V7h", 0, "major").pitch_classes() == [7, 11, 2, 5]
    assert T.parse_roman("IIIe", 0, "major").pitch_classes() == [3, 7, 11]


def test_case_scale_mismatch_appends_a_warning_and_the_scale_wins():
    warns: list = []
    c = T.parse_roman("iiid", 0, "major", warnings=warns)
    assert c.pitch_classes() == [3, 7, 10]
    assert len(warns) == 1 and "dorian" in warns[0] and "iiid" in warns[0]
    # matching case is silent
    quiet: list = []
    T.parse_roman("IIId", 0, "major", warnings=quiet)
    assert quiet == []
    # and no collector is still fine
    assert T.parse_roman("iiid", 0, "major").pitch_classes() == [3, 7, 10]


def test_explicit_quality_token_overrides_the_borrowed_scale_silently():
    """An explicit token always wins over the borrowed scale, without warning."""
    warns: list = []
    # locrian's ii is a major triad on Db; `0` forces the diminished reading
    c = T.parse_roman("ii0l", 0, "major", warnings=warns)
    assert c.pitch_classes() == [1, 4, 7]
    assert warns == []
    # dorian's II is minor; `x` forces dominant colour
    warns.clear()
    assert T.parse_roman("IIxd", 0, "major").pitch_classes() == [2, 6, 9, 0]
    assert T.parse_roman("IIxd", 0, "major", warnings=warns) is not None
    assert warns == []


def test_forcing_a_quality_the_borrowed_scale_lacks_uses_a_chromatic_numeral():
    """There is no "minor" token in roman spelling -- case is the only marker,
    and under the round-2 ruling a mode letter overrides it.  The documented way
    to write Eb minor in C major is therefore the chromatic numeral `biii`, not
    `iiid`."""
    assert T.parse_roman("biii", 0, "major").pitch_classes() == [3, 6, 10]
    assert T.parse_roman("iiid", 0, "major").pitch_classes() == [3, 7, 10]


def test_accidental_absorption_with_mode_letter():
    """`bVIIm` in C is Bb: mixolydian already flats the 7th, so no double shift."""
    assert T.parse_roman("bVIIm", 0, "major").root_pc == 10
    assert T.parse_roman("VIIm", 0, "major").root_pc == 10
    assert T.parse_roman("bVIa", 0, "major").root_pc == 8
    # a contradictory accidental still applies
    assert T.parse_roman("#IVm", 0, "major").root_pc == 6


def test_modal_interchange_with_extensions():
    c = T.parse_roman("iv7f", 0, "major")   # phrygian iv = F, min7
    assert c.pitch_classes() == [5, 8, 0, 3]
    c = T.parse_roman("bVII^7m", 0, "major")
    assert c.root_pc == 10 and 11 in c.intervals


def test_slash_bass_by_note_name_and_by_degree():
    assert T.parse_roman("i/3", 0, "minor").bass_pc == 3
    assert T.parse_roman("i/5", 0, "minor").bass_pc == 7
    assert T.parse_roman("IV/E", 0, "major").bass_pc == 4
    assert T.parse_roman("IV/Bb", 0, "major").bass_pc == 10
    assert T.parse_absolute("Dm7/A").bass_pc == 9
    assert T.parse_absolute("Ab^7/C").bass_pc == 0


def test_slash_bass_missing_degree_errors():
    with pytest.raises(errors.HarmonyError):
        T.parse_roman("I/7", 0, "major")     # plain triad has no 7th
    with pytest.raises(errors.HarmonyError):
        T.parse_absolute("C/Q")


def test_six_nine_is_not_a_slash_bass():
    c = T.parse_absolute("C6/9")
    assert c.bass_pc is None
    assert set(c.intervals) == {0, 4, 7, 9, 14}
    c2 = T.parse_absolute("C6/9/E")
    assert c2.bass_pc == 4 and set(c2.intervals) == {0, 4, 7, 9, 14}


# ---------------------------------------------------------------------------
# absolute symbols
# ---------------------------------------------------------------------------


def test_absolute_roots_and_accidentals():
    assert T.parse_absolute("C").root_pc == 0
    assert T.parse_absolute("F#7").root_pc == 6
    assert T.parse_absolute("Ab^7").root_pc == 8
    assert T.parse_absolute("Bbm7").root_pc == 10
    assert T.parse_absolute("B").root_pc == 11


def test_absolute_quality_spellings_are_synonyms():
    for a, b in (("Cm7", "C-7"), ("Cmaj7", "C^7"), ("Cdim7", "Co7"),
                 ("Caug", "C+"), ("Cm7b5", "Cø")):
        assert T.parse_absolute(a).pitch_classes() == \
            T.parse_absolute(b).pitch_classes(), (a, b)


def test_absolute_examples_from_spec():
    cases = {
        "Cm9": [0, 3, 7, 10, 2],
        "Ab^7": [8, 0, 3, 7],
        # lead-sheet dialect: b13 *is* the altered fifth, so no natural 5th
        "F#7b13": [6, 10, 4, 2],
        "Bsus4": [11, 4, 6],
        "Dm7/A": [2, 5, 9, 0],
        "C6/9": [0, 4, 7, 9, 2],
        "Galt": [7, 11, 5, 8, 10, 1, 3],
        "E7#9#11": [4, 8, 11, 2, 7, 10],
    }
    for sym, pcs in cases.items():
        assert T.parse_absolute(sym).pitch_classes() == pcs, sym


def test_transposition_invariance():
    """The same symbol in every key is the same interval set."""
    for sym in ("Cm9", "C^7", "C7alt", "C13", "Csus4"):
        base = T.parse_absolute(sym).intervals
        for pc in range(12):
            name = T.PC_NAMES[pc]
            assert T.parse_absolute(name + sym[1:]).intervals == base, (sym, pc)


def test_roman_and_absolute_agree():
    """V7 in C major must be exactly G7; iv11 in C minor exactly Fm11."""
    assert T.parse_roman("V7", 0, "major").pitch_classes() == \
        T.parse_absolute("G7").pitch_classes()
    assert T.parse_roman("iv11", 0, "minor").pitch_classes() == \
        T.parse_absolute("Fm11").pitch_classes()
    assert T.parse_roman("VI^7", 0, "minor").pitch_classes() == \
        T.parse_absolute("Ab^7").pitch_classes()
    assert T.parse_roman("V7alt", 0, "major").pitch_classes() == \
        T.parse_absolute("Galt").pitch_classes()


# ---------------------------------------------------------------------------
# pitch sets and errors
# ---------------------------------------------------------------------------


def test_pitch_set_relative_and_absolute():
    c = T.parse_pitchset([0, 3, 7, 10, 14])
    assert c.intervals == (0, 3, 7, 10, 14)
    assert c.degree_pc(3) == 3 and c.degree_pc(7) == 10
    a = T.parse_pitchset([60, 63, 67, 70], absolute=True)
    assert a.root_pc == 0 and a.intervals == (0, 3, 7, 10)
    assert a.guide_tones() == [3, 10]


def test_unknown_symbols_raise_with_a_suggestion():
    for bad in ("Q7", "viiiq", "", "Hm7", "V7zz"):
        with pytest.raises(errors.HarmonyError) as e:
            T.parse_chord(bad, 0, "major")
        assert e.value.suggestion, bad


def test_error_is_a_filigree_error():
    with pytest.raises(errors.FiligreeError):
        T.parse_roman("nope", 0, "major")


def test_parse_chord_dispatch():
    assert T.parse_chord("V7", 0, "major").root_pc == 7
    assert T.parse_chord("Cm9", 0, "major").root_pc == 0
    # 'i' is a roman numeral, 'C' is a note: no ambiguity
    assert T.parse_chord("i", 2, "minor").root_pc == 2


def test_determinism():
    a = [T.parse_chord(s, 0, "minor").pitch_classes()
         for s in ("i9", "VI^7", "iv11", "V7alt")]
    b = [T.parse_chord(s, 0, "minor").pitch_classes()
         for s in ("i9", "VI^7", "iv11", "V7alt")]
    assert a == b


def test_concision_bar_diatonic_chord_is_at_most_four_chars():
    """refs/BAR.md: a plain diatonic chord must cost <= 4 characters."""
    for sym in ("i", "ii", "iii", "IV", "V", "vi", "vii0", "V7", "IV^7", "i9"):
        assert len(sym) <= 4, sym
        assert T.parse_roman(sym, 0, "major") is not None


# ---------------------------------------------------------------------------
# round 2: robustness and diagnostics
# ---------------------------------------------------------------------------

#: every one of these was silently ACCEPTED before round 2, or rejected with a
#: 0:0 position and no hint.
BAD_SYMBOLS = [
    "", "   ", "\t", "V/", "V//ii", "Cmmm", "C--", "vii0000", "i13alt",
    "V7alt7", "bbVI", "Iv", "VIII", "iv#", "Hm7", "/V", "V 7", "I(", "I)",
    "Cb5", "C#5", "Cmaj7b5#5", "C7b5#5", "I" + "7" * 400,
    "i" * 40, "V7b9b9",
]


@pytest.mark.parametrize("sym", BAD_SYMBOLS)
def test_bad_symbols_are_rejected_with_position_and_suggestion(sym):
    pos = Pos(line=7, col=13, file="song.fil")
    with pytest.raises(errors.HarmonyError) as ei:
        T.parse_chord(sym, 0, "major", pos=pos)
    err = ei.value
    assert err.line == 7 and err.col >= 13, (sym, err.line, err.col)
    assert err.path == "song.fil", sym
    assert err.suggestion, sym
    # and the rendered message carries them
    text = str(err)
    assert "song.fil:7:" in text and "hint:" in text, text


@pytest.mark.parametrize("sym", BAD_SYMBOLS)
def test_bad_symbols_without_a_pos_still_get_a_real_position(sym):
    """No caller position available: line/col must still be >= 1, never 0."""
    with pytest.raises(errors.HarmonyError) as ei:
        T.parse_chord(sym, 0, "major")
    assert ei.value.line >= 1 and ei.value.col >= 1
    assert ei.value.suggestion


def test_error_column_points_inside_the_symbol():
    pos = Pos(line=3, col=10, file="x.fil")
    with pytest.raises(errors.HarmonyError) as ei:
        T.parse_roman("V7alt7", 0, "major", pos=pos)
    # the column points at the offending token inside the symbol
    assert ei.value.col == 10 + "V7alt7".index("7") == 11


def test_over_long_symbols_are_capped():
    assert T.MAX_SYMBOL_LEN == 24
    ok = "V7b9#11b13/ii"
    assert len(ok) <= T.MAX_SYMBOL_LEN
    assert T.parse_roman(ok, 0, "major") is not None
    with pytest.raises(errors.HarmonyError) as ei:
        T.parse_roman("V" + "7" * T.MAX_SYMBOL_LEN, 0, "major")
    assert "24" in str(ei.value)


def test_whitespace_padding_is_tolerated_but_inner_space_is_not():
    assert T.parse_roman(" V7 ", 0, "major").pitch_classes() == [7, 11, 2, 5]
    with pytest.raises(errors.HarmonyError):
        T.parse_roman("V 7", 0, "major")


def test_parenthesised_alterations_disambiguate_the_root_accidental():
    assert T.parse_absolute("Cb(5)").pitch_classes() == [11, 6]
    assert T.parse_absolute("C(b5)").pitch_classes() == [0, 4, 6]
    assert T.parse_absolute("V7(b9)".replace("V7", "G7")).pitch_classes() == \
        T.parse_absolute("G7b9").pitch_classes()


def test_normalise_mode_error_carries_position_and_suggestion():
    pos = Pos(line=2, col=5, file="y.fil")
    with pytest.raises(errors.HarmonyError) as ei:
        T.normalise_mode("lydianish", pos=pos)
    assert (ei.value.line, ei.value.col) == (2, 5)
    assert "lydian" in ei.value.suggestion


def test_warnings_collector_is_appended_not_replaced():
    warns = ["pre-existing"]
    T.parse_roman("iiid", 0, "major", warnings=warns)
    T.parse_absolute("F#7b13", warnings=warns)
    assert warns[0] == "pre-existing"
    assert len(warns) == 3


def test_b13_dialect_split_is_deliberate():
    """Roman numerals keep the 5th; lead-sheet symbols do not (see truth spec)."""
    assert T.parse_roman("V7b13", 0, "major").pitch_classes() == \
        [7, 11, 2, 5, 3]
    assert T.parse_absolute("G7b13").pitch_classes() == [7, 11, 5, 3]


def test_secondary_dominant_with_a_slash_bass():
    c = T.parse_roman("V/ii/E", 0, "major")
    assert c.pitch_classes() == [9, 1, 4] and c.bass_pc == 4
