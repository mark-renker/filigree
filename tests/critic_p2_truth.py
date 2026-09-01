"""CRITIC-OWNED P2 evidence file. Written by the round-1 critic, not the builder.

Contains three independent sections:
  A. ground truth derived from first principles (60+ chord symbols)
  B. adversarial / malformed input
  C. voice-leading measurement

Run directly:  python tests/critic_p2_truth.py
Run as tests:  pytest tests/critic_p2_truth.py

Ground truth is derived here, in this file, from scale spellings written out by
hand.  refs/specs/harmony_truth.md is NOT consulted (builder-authored).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from filigree import errors, theory  # noqa: E402
from filigree.theory import parse_absolute, parse_chord, parse_roman  # noqa: E402
from filigree import voicing as V  # noqa: E402

PC = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
      "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10,
      "B": 11, "Cb": 11}


def S(*names: str) -> set[int]:
    return {PC[n] for n in names}


# ---------------------------------------------------------------------------
# Section A0 — scale spellings, written out by hand from the mode definitions
# ---------------------------------------------------------------------------

SCALES = {
    "major":          "C D E F G A B",
    "ionian":         "C D E F G A B",
    "dorian":         "C D Eb F G A Bb",
    "phrygian":       "C Db Eb F G Ab Bb",
    "lydian":         "C D E F# G A B",
    "mixolydian":     "C D E F G A Bb",
    "minor":          "C D Eb F G Ab Bb",
    "aeolian":        "C D Eb F G Ab Bb",
    "locrian":        "C Db Eb F Gb Ab Bb",
    "harmonic-minor": "C D Eb F G Ab B",
    "melodic-minor":  "C D Eb F G A B",
    "whole-tone":     "C D E F# G# A#",
    "blues":          "C Eb F Gb G Bb",
}


def scale_failures() -> list[str]:
    out = []
    for mode, spelling in SCALES.items():
        want = [PC[n] for n in spelling.split()]
        got = theory.scale_pitches(0, mode)
        if got != want:
            out.append(f"scale {mode}: expected {want} got {got}")
    if theory.scale_pitches(0, "chromatic") != list(range(12)):
        out.append("scale chromatic wrong")
    return out


# ---------------------------------------------------------------------------
# Section A — chord ground truth.  (symbol, tonic, mode, expected pcs, bass)
# ---------------------------------------------------------------------------

CASES: list[tuple[str, int, str, set[int], int | None]] = [
    # --- diatonic triads, C major -----------------------------------------
    ("I",      0, "major", S("C", "E", "G"), None),
    ("ii",     0, "major", S("D", "F", "A"), None),
    ("iii",    0, "major", S("E", "G", "B"), None),
    ("IV",     0, "major", S("F", "A", "C"), None),
    ("V",      0, "major", S("G", "B", "D"), None),
    ("vi",     0, "major", S("A", "C", "E"), None),
    ("vii0",   0, "major", S("B", "D", "F"), None),
    # --- other keys / every mode in SPEC §2 as a key ----------------------
    ("i",      9, "minor", S("A", "C", "E"), None),
    ("iv",     9, "minor", S("D", "F", "A"), None),
    ("V7",     9, "minor", S("E", "G#", "B", "D"), None),
    ("VI",     0, "minor", S("Ab", "C", "Eb"), None),
    ("i",      2, "dorian", S("D", "F", "A"), None),
    ("IV",     2, "dorian", S("G", "B", "D"), None),
    ("VII",    2, "dorian", S("C", "E", "G"), None),
    ("II",     4, "phrygian", S("F", "A", "C"), None),
    ("II",     5, "lydian", S("G", "B", "D"), None),
    ("VII",    7, "mixolydian", S("F", "A", "C"), None),
    ("i0",    11, "locrian", S("B", "D", "F"), None),
    ("V7",     0, "harmonic-minor", S("G", "B", "D", "F"), None),
    ("viio7",  0, "harmonic-minor", S("B", "D", "F", "Ab"), None),
    ("IV7",    0, "melodic-minor", S("F", "A", "C", "Eb"), None),
    # --- extensions / alterations, SPEC §4 --------------------------------
    ("V7",     0, "major", S("G", "B", "D", "F"), None),
    ("i9",     0, "minor", S("C", "Eb", "G", "Bb", "D"), None),
    ("iv11",   0, "minor", S("F", "Ab", "C", "Eb", "G", "Bb"), None),
    ("II13",   0, "major", S("D", "F#", "A", "C", "E", "B"), None),
    ("v6",     0, "major", S("G", "Bb", "D", "E"), None),
    ("IV^7",   0, "major", S("F", "A", "C", "E"), None),
    ("I^9",    0, "major", S("C", "E", "G", "B", "D"), None),
    ("I^13",   0, "major", S("C", "E", "G", "B", "D", "A"), None),
    ("ii11",   0, "major", S("D", "F", "A", "C", "E", "G"), None),
    ("viio7",  0, "major", S("B", "D", "F", "Ab"), None),
    ("IIx",    0, "major", S("D", "F#", "A", "C"), None),
    ("V7alt",  0, "major", S("G", "Ab", "Bb", "B", "C#", "Eb", "F"), None),
    ("bVI",    0, "major", S("Ab", "C", "Eb"), None),
    ("#iv",    0, "major", S("F#", "A", "C#"), None),
    ("Isus4",  0, "major", S("C", "F", "G"), None),
    ("Isus2",  0, "major", S("C", "D", "G"), None),
    ("I6/9",   0, "major", S("C", "E", "G", "A", "D"), None),
    ("Iadd9",  0, "major", S("C", "E", "G", "D"), None),
    ("V7b9",   0, "major", S("G", "B", "D", "F", "Ab"), None),
    ("V7#9",   0, "major", S("G", "B", "D", "F", "Bb"), None),
    ("V7#11",  0, "major", S("G", "B", "D", "F", "C#"), None),
    ("V7b13",  0, "major", S("G", "B", "D", "F", "Eb"), None),
    ("V7b5",   0, "major", S("G", "B", "Db", "F"), None),
    ("V7#5",   0, "major", S("G", "B", "Eb", "F"), None),
    # --- secondary dominants ----------------------------------------------
    ("V/ii",   0, "major", S("A", "C#", "E"), None),
    ("V7/ii",  0, "major", S("A", "C#", "E", "G"), None),
    ("V/V",    0, "major", S("D", "F#", "A"), None),
    ("V7/IV",  0, "major", S("C", "E", "G", "Bb"), None),
    ("V/vi",   0, "major", S("E", "G#", "B"), None),
    ("vii0/V", 0, "major", S("F#", "A", "C"), None),
    # --- modal interchange: all nine letters.  The mode letter selects the
    #     scale; the chord is the DIATONIC chord of that scale on that degree.
    ("In",     0, "major", S("C", "E", "G"), None),
    ("iid",    0, "major", S("D", "F", "A"), None),
    ("iiid",   0, "minor", S("Eb", "G", "Bb"), None),
    ("IVf",    0, "major", S("F", "Ab", "C"), None),
    ("IVy",    0, "major", S("F#", "A", "C"), None),
    ("bVIIm",  0, "major", S("Bb", "D", "F"), None),
    ("bVIa",   0, "major", S("Ab", "C", "Eb"), None),
    ("iil",    0, "major", S("Db", "F", "Ab"), None),
    ("iih",    0, "major", S("D", "F", "Ab"), None),
    ("ive",    0, "major", S("F", "A", "C"), None),
    ("IIIe",   0, "major", S("Eb", "G", "B"), None),
    ("V7h",    0, "major", S("G", "B", "D", "F"), None),
    # --- slash bass by name and by degree ---------------------------------
    ("I/3",    0, "major", S("C", "E", "G"), PC["E"]),
    ("V/3",    0, "major", S("G", "B", "D"), PC["B"]),
    ("i/3",    0, "minor", S("C", "Eb", "G"), PC["Eb"]),
    ("IV/E",   0, "major", S("F", "A", "C"), PC["E"]),
    ("ii7/5",  0, "major", S("D", "F", "A", "C"), PC["A"]),
]

ABS_CASES: list[tuple[str, set[int], int | None]] = [
    ("Cm9",     S("C", "Eb", "G", "Bb", "D"), None),
    ("Ab^7",    S("Ab", "C", "Eb", "G"), None),
    ("Bsus4",   S("B", "E", "F#"), None),
    ("Dm7/A",   S("D", "F", "A", "C"), PC["A"]),
    ("C6/9",    S("C", "E", "G", "A", "D"), None),
    ("Galt",    S("G", "Ab", "Bb", "B", "C#", "Eb", "F"), None),
    ("E7#9#11", S("E", "G#", "B", "D", "G", "A#"), None),
    ("Cmaj7",   S("C", "E", "G", "B"), None),
    ("C7",      S("C", "E", "G", "Bb"), None),
    ("Cdim7",   S("C", "Eb", "Gb", "A"), None),
    ("Cm7b5",   S("C", "Eb", "Gb", "Bb"), None),
    ("Caug",    S("C", "E", "G#"), None),
    ("C6",      S("C", "E", "G", "A"), None),
    ("C13",     S("C", "E", "G", "Bb", "D", "A"), None),
    ("C7b9",    S("C", "E", "G", "Bb", "Db"), None),
    ("Cadd9",   S("C", "E", "G", "D"), None),
    ("C5",      S("C", "G"), None),
    ("Csus2",   S("C", "D", "G"), None),
    ("Cm6",     S("C", "Eb", "G", "A"), None),
    ("F#m7",    S("F#", "A", "C#", "E"), None),
    ("Bb^9",    S("Bb", "D", "F", "A", "C"), None),
    ("Cmaj7/G", S("C", "E", "G", "B"), PC["G"]),
    # 7b13 = altered dominant with a lowered 13th; the natural 5th is
    # replaced (b13 IS the altered fifth in lead-sheet practice).
    ("F#7b13",  S("F#", "A#", "E", "D"), None),
]


def chord_failures() -> list[str]:
    out = []
    for sym, tonic, mode, want, bass in CASES:
        try:
            c = parse_roman(sym, tonic, mode)
        except Exception as e:  # noqa: BLE001
            out.append(f"{sym!r} key={theory.PC_NAMES[tonic]} {mode}: RAISED "
                       f"{type(e).__name__}")
            continue
        got = set(c.pitch_classes())
        if got != want:
            out.append(f"{sym!r} key={theory.PC_NAMES[tonic]} {mode}: expected "
                       f"{sorted(want)} got {sorted(got)}")
        if c.bass_pc != bass:
            out.append(f"{sym!r} bass: expected {bass} got {c.bass_pc}")
    for sym, want, bass in ABS_CASES:
        try:
            c = parse_absolute(sym)
        except Exception as e:  # noqa: BLE001
            out.append(f"{sym!r}: RAISED {type(e).__name__}")
            continue
        got = set(c.pitch_classes())
        if got != want:
            out.append(f"{sym!r}: expected {sorted(want)} got {sorted(got)}")
        if c.bass_pc != bass:
            out.append(f"{sym!r} bass: expected {bass} got {c.bass_pc}")
    return out


# ---------------------------------------------------------------------------
# Section B — adversarial input
# ---------------------------------------------------------------------------

ADVERSARIAL = [
    ("", 0, "major"), ("   ", 0, "major"), ("VIII", 0, "major"),
    ("iv#", 0, "major"), ("Cmmm", 0, "major"), ("V/", 0, "major"),
    ("/V", 0, "major"), ("bbVI", 0, "major"), ("C\u266d7", 0, "major"),
    ("i\u266f", 0, "major"), ("i13alt", 0, "major"), ("Iv", 0, "major"),
    (" V7 ", 0, "major"), ("V 7", 0, "major"), ("I" + "7" * 400, 0, "major"),
    ("i" * 200, 0, "major"), ("V//ii", 0, "major"), ("V/viii", 0, "major"),
    ("I/0", 0, "major"), ("I/99", 0, "major"), ("vii0000", 0, "major"),
    ("V7alt7", 0, "major"), ("i", 0, "bogus-mode"), ("#", 0, "major"),
    ("6/9", 0, "major"), ("Cb5", 0, "major"), ("Hm7", 0, "major"),
    ("C--", 0, "major"), ("Cmaj7b5#5", 0, "major"), ("V/ii/E", 0, "major"),
    ("\t\ni9", 0, "major"), ("I(", 0, "major"),
]


def adversarial_report() -> list[tuple[str, str, str]]:
    rows = []
    for sym, tonic, mode in ADVERSARIAL:
        label = sym if len(sym) < 24 else sym[:20] + "..."
        try:
            c = parse_chord(sym, tonic, mode)
            rows.append((label, "ACCEPTED", f"{c.quality} {c.pitch_classes()}"))
        except errors.HarmonyError as e:
            ok = (e.line > 0 or e.col > 0)
            rows.append((label, "HarmonyError" + ("" if ok else " (line:col=0:0)"),
                         (e.suggestion or "NO SUGGESTION")[:40]))
        except Exception as e:  # noqa: BLE001
            rows.append((label, "CRASH " + type(e).__name__, str(e)[:60]))
    return rows


# ---------------------------------------------------------------------------
# Section C — voice-leading measurement
# ---------------------------------------------------------------------------

PROGRESSIONS = {
    "ii-V-I (C major)": (["ii7", "V7", "I^7"], 0, "major", None),
    "minor 6-2-5-1 (C minor)": (["VI^7", "ii0", "V7", "i9"], 0, "minor", None),
    "tritone sub (bII7 for V7)": (["ii7", "bII7", "I^7"], 0, "major", None),
    "modulating C major -> E major": (["I^7", "V7/vi", "V/vi"], 0, "major", None),
    "melody on top": (["I^7", "vi7", "ii7", "V7"], 0, "major",
                      [PC["E"], PC["C"], PC["A"], PC["B"]]),
}


def total_move(vs: list[list[int]]) -> int:
    return sum(V.voice_leading_cost(vs[i], vs[i + 1]) for i in range(len(vs) - 1))


def voicing_report() -> tuple[list[list[str]], list[str]]:
    rows = []
    defects = []
    for name, (syms, tonic, mode, mel) in PROGRESSIONS.items():
        chords = [parse_roman(s, tonic, mode) for s in syms]
        spec_s = V.VoicingSpec(low=48, high=72, mode="smooth", size=4,
                               top="melody" if mel else None)
        spec_c = V.VoicingSpec(low=48, high=72, mode="close", size=4)
        vs = V.voice_progression(chords, spec_s, mel)
        vc = V.voice_progression(chords, spec_c, None)
        ms, mc = total_move(vs), total_move(vc)
        cross = sum(V.crossings(vs[i], vs[i + 1]) for i in range(len(vs) - 1))
        outside = sum(1 for v in vs for p in v if not 48 <= p <= 72)
        rows.append([name, str(ms), str(mc), str(cross), str(outside),
                     " | ".join(str(v) for v in vs)])
        if ms > mc:
            defects.append(f"{name}: smooth movement {ms} > close {mc}")
        if cross:
            defects.append(f"{name}: {cross} voice crossings")
        if outside:
            defects.append(f"{name}: {outside} notes outside 48..72: {vs}")
        if mel:
            for i, v in enumerate(vs):
                if v[-1] % 12 != mel[i]:
                    defects.append(
                        f"{name}: top:melody failed at chord {i} "
                        f"({syms[i]}): top {v[-1]} pc {v[-1] % 12} != {mel[i]}")
    return rows, defects


def melody_guide_tone_probe() -> list[str]:
    """`top: melody` must not delete the chord's guide tones (3rd / 7th)."""
    out = []
    spec = V.VoicingSpec(low=48, high=72, mode="smooth", size=4, top="melody")
    trials = [("I^7", 0, "major", PC["E"]), ("ii7", 0, "major", PC["A"]),
              ("V7", 0, "major", PC["D"]), ("i9", 0, "minor", PC["G"]),
              ("I^7", 0, "major", PC["F#"])]
    for sym, tonic, mode, mel in trials:
        c = parse_roman(sym, tonic, mode)
        v = V.voice_chord(c, spec, None, mel)
        pcs = {p % 12 for p in v}
        missing = [d for d in (3, 7) if c.degree_pc(d) is not None
                   and c.degree_pc(d) not in pcs]
        if missing:
            out.append(f"{sym} melody={theory.PC_NAMES[mel]}: voicing {v} "
                       f"pcs {sorted(pcs)} lost degree(s) {missing}")
        if v[-1] % 12 != mel:
            out.append(f"{sym} melody={theory.PC_NAMES[mel]}: top {v[-1]} "
                       f"pc {v[-1] % 12} is not the melody pc {mel}")
    return out


def random_probe(n: int = 400) -> list[str]:
    """Randomised search for smooth>close and out-of-range voicings."""
    import random
    rng = random.Random(20260830)
    syms = ["I", "ii7", "iii", "IV^7", "V7", "vi7", "vii0", "bVI", "V7alt",
            "i9", "iv11", "II13", "IIx", "I6/9", "v6", "viio7", "Isus4"]
    worse = 0
    worst = None
    out_of_range = []
    for _ in range(n):
        prog = [rng.choice(syms) for _ in range(4)]
        tonic = rng.randrange(12)
        mode = rng.choice(["major", "minor", "dorian", "mixolydian"])
        low = rng.choice([48, 50, 55, 60])
        high = low + rng.choice([12, 17, 24])
        size = rng.choice([3, 4, 5])
        chords = [parse_roman(s, tonic, mode) for s in prog]
        ss = V.VoicingSpec(low=low, high=high, mode="smooth", size=size)
        sc = V.VoicingSpec(low=low, high=high, mode="close", size=size)
        vs = V.voice_progression(chords, ss)
        vc = V.voice_progression(chords, sc)
        ms, mc = total_move(vs), total_move(vc)
        if ms > mc:
            worse += 1
            if worst is None or ms - mc > worst[0]:
                worst = (ms - mc, prog, tonic, mode, low, high, size, ms, mc)
        for v in vs:
            bad = [p for p in v if not low <= p <= high]
            if bad and len(out_of_range) < 4:
                out_of_range.append(
                    f"{prog} key={theory.PC_NAMES[tonic]} {mode} "
                    f"range={low}..{high} size={size}: {v} -> {bad}")
    res = [f"smooth worse than close in {worse}/{n} random progressions"]
    if worst:
        res.append(f"  worst: {worst[1]} key={theory.PC_NAMES[worst[2]]} "
                   f"{worst[3]} range={worst[4]}..{worst[5]} size={worst[6]} "
                   f"smooth={worst[7]} close={worst[8]}")
    res += ["  out-of-range: " + o for o in out_of_range]
    return res


def bass_range_probe() -> list[str]:
    """Slash-bass chords must still respect the requested range."""
    out = []
    spec = V.VoicingSpec(low=48, high=72, mode="smooth", size=4)
    for sym in ("Dm7/A", "C/3", "Cmaj7/G", "Ab^7/Eb"):
        c = parse_absolute(sym)
        v = V.voice_chord(c, spec)
        bad = [p for p in v if not 48 <= p <= 72]
        if bad:
            out.append(f"{sym}: {v} -> {bad} outside requested 48..72 (C3..C5)")
        if v and v[0] % 12 != c.bass_pc:
            out.append(f"{sym}: lowest voice {v[0]} pc {v[0] % 12} is not the "
                       f"requested bass pc {c.bass_pc}")
    return out


# ---------------------------------------------------------------------------
# pytest entry points
# ---------------------------------------------------------------------------

def test_scales():
    assert scale_failures() == []


def test_chords():
    assert chord_failures() == []


def test_voicing():
    _rows, defects = voicing_report()
    assert defects == []


def test_bass_range():
    assert bass_range_probe() == []


def main() -> None:
    print("== A0 scales ==")
    sf = scale_failures()
    print("\n".join(sf) if sf else "all %d mode spellings OK" % len(SCALES))

    print(f"\n== A chord ground truth ({len(CASES) + len(ABS_CASES)} symbols) ==")
    cf = chord_failures()
    for line in cf:
        print("  MISMATCH", line)
    print(f"  {len(cf)} mismatches")

    print("\n== B adversarial ==")
    for label, kind, extra in adversarial_report():
        print(f"  {label!r:28} {kind:28} {extra}")

    print("\n== C voice leading ==")
    rows, defects = voicing_report()
    print(f"  {'progression':32} {'smooth':>7} {'close':>7} {'cross':>6} {'out':>4}")
    for r in rows:
        print(f"  {r[0]:32} {r[1]:>7} {r[2]:>7} {r[3]:>6} {r[4]:>4}")
        print(f"      {r[5]}")
    for d in defects:
        print("  DEFECT", d)

    print("\n== C2 slash bass vs range ==")
    for line in bass_range_probe():
        print("  DEFECT", line)

    print("\n== C3 top:melody vs guide tones ==")
    for line in melody_guide_tone_probe():
        print("  DEFECT", line)

    print("\n== C4 randomised probe ==")
    for line in random_probe():
        print(" ", line)

    print("\n== D concision ==")
    print("  plain diatonic chord in Filigree harm lane: 'i' = %d char(s); "
          "Hookpad = 1 keystroke" % len("i"))


if __name__ == "__main__":
    main()
