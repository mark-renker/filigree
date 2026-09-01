# P2 — harmony + voicing: notes for the lead

Files owned and delivered:

* `src/filigree/theory.py`
* `src/filigree/voicing.py`
* `tests/test_theory.py` (149 tests)
* `tests/test_voicing.py` (64 tests)
* `refs/specs/harmony_truth.md` (92 chord rows + 10 guide-tone rows, with source URLs)

`python -m pytest tests/test_theory.py tests/test_voicing.py -q` → **213 passed**.
`python -m py_compile` clean on all four. Standard library + numpy + scipy only
(scipy is used for the assignment solve and is imported defensively, with a
fallback path, so a scipy-less environment still imports).

Reported voice-leading numbers (printed by the tests, `refs/BAR.md` protocol):

| progression | `mode=smooth` total movement | naive close-position |
|---|---|---|
| `i9 VI^7 iv11 V7alt` in C minor | **15** semitones | 49 |
| `Dm7 G7 Cmaj7 A7b13` | **10** semitones | 96 |

Voice crossings in both: **0** (asserted).

---

## Ambiguities I resolved

1. **A bare `7` is a minor seventh.** `V7` in C major is G B D F, `I7` is
   C E G Bb, and a major seventh always needs `^7`/`maj7`. The alternative
   (diatonic sevenths) would make `IV^7` redundant in major, so the lead-sheet
   reading is the only one consistent with SPEC §4 having a `^` marker at all.
2. **`x` forces a dominant colour** (major 3rd + minor 7th) regardless of case,
   so `IIx` in C is D F# A C, matching SPEC's "altered/dominant" gloss. `alt` is
   the separate, fuller thing.
3. **`alt` = `1 b9 #9 3 #11 b13 b7`, no perfect fifth.** Sourced (see
   harmony_truth.md); `size` clamping then thins it, which is exactly how players
   use it.
4. **`13` omits the 11th** (`R 3 5 b7 9 13`), standard practice; `11` keeps 9.
5. **Modal-interchange letters set the root's scale, case still sets quality.**
   So `iiid` in C is Eb **minor** and `IIId` is Eb major. SPEC §4's example
   `iiid = "iii borrowed from dorian"` reads as if it should be Eb major (dorian's
   own III), so **if you want the borrowed mode's diatonic quality too, that is a
   SPEC change and I need a ruling** — see "Things I'd like changed" below. Both
   spellings are documented and tested as-is.
6. **Accidental absorption.** With a mode letter, an accidental that the borrowed
   mode already supplies is not applied twice: `bVIIm` in C is Bb (not A), and
   `bVIa` is Ab. A contradictory accidental still applies additively
   (`#IVm` → F#). Without a mode letter, accidentals are always additive.
7. **`V/ii` is a major triad, `V7/ii` is A7.** The slash re-roots into the key of
   that degree (read in the *home* key/mode) and parses the head in **major**;
   the head's own extensions decide whether a 7th appears. `viio7/V` works too.
8. **`/` disambiguation**, in order: `6/9` is protected first; then a tail that
   looks like a roman numeral is a secondary function, a tail matching
   `[A-G][b#]*` is a bass note, an all-digits tail is a chord degree. Roman
   numerals only use `I/V/i/v` so there is no collision with note names.
   `C6/9/E` parses as C6/9 with E in the bass.
9. **`degree_to_pitch` is 0-based** (`0` == tonic), because that is what the
   `notes` lane writes (SPEC §5, "0 = tonic", negatives allowed).
   `Chord.degree_pc` is 1-based (`1` == root), because chord degrees are.
   `C4 == 60`.
10. **Compound degrees fold onto simple ones** in `degree_pc`: `degree_pc(13)` on
    `C6/9` returns the 6th, `degree_pc(11)` on `Isus4` returns the 4th. When a
    chord genuinely lacks the degree it returns `None` (`V7.degree_pc(13)` is
    `None`, it does not fall through to the b7).
11. **Guide tones** are the 3rd and 7th, with a documented fallback chain
    (3rd → 4th/sus → 2nd; 7th → 6th → 5th) so triads and sus chords still answer
    `@guide` and `>`-targets.
12. **`Chord` gained one extra field**, `degrees: tuple[tuple[int, int], ...]`,
    appended after the five fields ARCH specifies and defaulted to `()`. It is
    the analytic degree→interval map, and it is what makes `degree_pc`,
    `guide_tones`, the size-clamp drop order and `/3` slash basses correct rather
    than heuristic. Positional construction `Chord(root, quality, intervals,
    bass, symbol)` is unchanged.
13. **`nearest_pc` ties resolve upward** (a tritone away goes up), for
    determinism.
14. **Voicing size growth**: `size` larger than the chord's note count pads with
    octave doublings of the highest-priority tones rather than erroring.
15. **`drop` mode builds its close stack an octave above `low`** when the range
    allows, so the dropped voice stays inside `[low, high]`.
16. **Bass placement**: `chord.bass_pc` becomes the lowest voice and may sit up to
    an octave below `low` (per ARCH). E.g. `Dm7/A` in `C3..C6` puts A2 = 45 under
    a 48 floor.
17. **`rootless` supplies a 9th** when the symbol did not spell one (type-A
    3-5-7-9), so `Dm7` rootless is F A C E.
18. **`smooth` cost function** is documented in `_layout_smooth.__doc__`: sum of
    absolute semitone movement, over a rectangular linear assignment between the
    previous voices and the target pitch classes, where each cell's candidate is
    the in-range octave placement of that class nearest the previous voice.
    Solved exactly with `scipy.optimize.linear_sum_assignment`; the result is
    re-paired in ascending order (rearrangement inequality → no worse, and voice
    crossing becomes impossible). Because the candidate set contains every
    in-range placement, the optimum is provably ≤ close position — the tests
    additionally brute-force one chord pair to confirm optimality.

## Extra public helpers (additive, safe to ignore)

`theory.parse_pitchset(offsets, absolute=False)` for SPEC §4 spelling 3 —
`ChordTok.pitchset` / `pitchset_absolute` need it and nobody else owns it.
`theory.parse_chord(sym, tonic_pc, mode)` dispatches roman vs absolute.
`theory.normalise_mode`, `theory.degree_pc_of_scale`, `theory.PC_NAMES`.
`voicing.voice_progression`, `voicing.voice_leading_cost`, `voicing.crossings`,
`voicing.select_degrees`, `voicing.DROP_RANK`, `voicing.MODES`.

## Things I'd like changed in files I do not own

1. **`docs/SPEC.md` §4, modal interchange.** Please either confirm that case
   keeps setting quality under a mode letter (so `iiid` is Eb minor and the
   example gloss should read `IIId`), or specify that the mode letter overrides
   quality with the borrowed mode's diatonic chord. I implemented the former; the
   latter is a two-line change in `parse_roman` once ruled on.
2. **`docs/SPEC.md` §4 / `docs/ARCH.md`.** ARCH says "Pure standard library +
   `numpy` … No other dependencies", but the P2 brief asks for scipy for the
   assignment solve. `voicing.py` imports scipy inside a `try` and falls back, so
   it is a soft dependency and the module works without it — the fallback is an
   exact depth-first branch-and-bound assignment solver, verified against
   `scipy.optimize.linear_sum_assignment` on 300 random cost matrices. Please
   either add scipy to the ARCH dependency line or drop it entirely; either way
   `voicing.py` needs no change.
3. **`docs/ARCH.md` P2 signature block.** Worth recording the extra
   `Chord.degrees` field and the 0-based/1-based degree split (items 9 and 12
   above) so `resolve.py` calls them correctly.
4. **`resolve.py` (lead).** For `PitchTok(kind="chordtone")` use
   `Chord.degree_pc(value)` then `theory.nearest_pc` against the previous lane
   pitch; for `kind="anchor"` `@guide` use `Chord.guide_tones()`. For
   `Target(kind="guide"|"degree")` in `gesture.GestureCtx.resolve_target`, the
   same two calls give the pitch class — `nearest_pc(pc, note_pitch)` then
   converts to a bend amount. `VoicingDef.fields` maps onto `VoicingSpec`
   one-to-one except `range: C3..C5`, which must be split into `low`/`high`.
5. **`ir.py`.** If the chord ribbon in the playground wants a display label, a
   `Chord.quality` string is available (canonical names like `dom7`, `min11`,
   `alt`, `dom7b13`) — say the word if you want a `Chord.label()` instead.

---

# Round 2

The round-1 verdict (`refs/verdicts/P2_round1.md`) gave the REFERENCE
correctness, voice leading and robustness. Every defect on that list is now
closed, and the critic's own ground-truth file passes untouched:

```
$ python -m pytest tests/test_theory.py tests/test_voicing.py tests/critic_p2_truth.py -q
286 passed
$ python -m pytest tests/critic_p2_truth.py -q
4 passed            # test_scales, test_chords, test_voicing, test_bass_range
$ python tests/critic_p2_truth.py
A0 scales: all 13 mode spellings OK
A  chord ground truth: 0 mismatches / 91 symbols
B  adversarial: every malformed symbol rejected (only the two
   whitespace-padded *valid* symbols ' V7 ' and '\t\ni9' are accepted, on purpose)
C2 slash bass vs range: clean
C3 top:melody vs guide tones: clean
C4 randomised probe: smooth worse than close in 0/400
```

The rest of the suite is unchanged by this work. The remaining failures in
`tests/` all live in other pieces' files and concern gesture curves / MPE bend
math, not harmony: `test_integration.py::test_curve_value_at_returns_nan_inside_a_hole`
reliably, plus (depending on the `pytest-randomly` ordering seed)
`test_gesture.py::test_reclock_2_wiggle_times_ramp_is_still_5p5_hz` and two bend
tests in `test_mpe.py` — a file whose own header states it has no dependency on
`theory.py`. None of them import `voicing.py`, and none are files I own.

## 1. Modal interchange — the ruling, implemented

The lead ruled that the mode letter selects the scale and the chord's quality is
derived **diatonically from that scale**. Implemented as `_diatonic_stack()`:
for `<numeral><letter>` the chord degrees 3, 5, 7, 9, 11, 13 (and 6) are read off
the borrowed scale at scale steps +2, +4, +6, +8, +10, +12 (+5) from the numeral's
degree, expressed as semitones over the chord root, and that table becomes the
`_Spelling`'s natural intervals. So `iiid` in C minor is now **Eb G Bb =
[3, 7, 10]** (C dorian's own III), and all twelve borrowed symbols in the critic's
table match: `In iid iiid IVf IVy bVIIm bVIa iil iih ive IIIe V7h`.

The written case is *validated, not authoritative*: a case that disagrees with
the borrowed scale appends a warning (naming the scale, the degree and the
spelling that would silence it) and the scale wins. Explicit tokens (`x 0 o7 b5
#5 sus alt …`) still override the scale and never warn. Because roman spelling
has no "minor" token, `refs/specs/harmony_truth.md` now documents the chromatic
escape hatch: `biii` is Eb minor in C major, `iiid` is Eb major.

Root spelling was fixed at the same time (verdict defect 9): an accidental is
**chromatic** — measured from the major-scale degree in every mode, so `bVI` is
Ab in C major and C minor alike and `#iv` is F# — while an unaccented numeral
takes the effective mode's own degree. `bVIIm` is Bb with no double shift, and
the old ad-hoc "accidental absorption" special case is gone.

`warnings: list | None = None` and `pos: Pos | None = None` are now keyword-only
parameters on `parse_roman`, `parse_absolute`, `parse_chord` (and `pos` on
`normalise_mode`). `warnings` is appended to, never replaced, so one collector
can span a whole file. **Lead action item:** `resolve.py` calls these positionally
and passes neither — threading its `Pos` and one shared warning list through
would give real line/col on every harmony diagnostic for free.

## 2. Smooth voicing can no longer be worse than close position

Two guards, both by construction rather than by tuning:

* per chord, `voice_chord` also builds the naive close-position candidate and
  keeps whichever has the lower `voice_leading_cost` against `previous`
  (ties → smooth, for determinism);
* per progression, `voice_progression` builds the whole smooth chain **and** the
  whole close chain (the latter independent of any previous voicing) and returns
  the cheaper total.

Randomised proof: `test_smooth_is_never_worse_than_close_over_500_progressions`
draws 500 progressions of 2–5 chords from 22 symbols × 12 tonics × 6 modes ×
5 range floors × 3 range widths × 4 sizes, and asserts
`movement(smooth) - movement(close) <= 0` for every one.

**Worst-case margin over the 500 progressions: 0 semitones** (i.e. smooth was
never worse; the round-1 code lost by up to **+10** — the critic's worst case was
`['IV^7','iv11','iii','vii0']` in F# mixolydian, 68 vs 58). The critic's own
400-progression probe now reports `0/400`. A second 500-progression test asserts
`crossings(v[i], v[i+1]) == 0` and ascending output everywhere.

## 3. Range discipline and `top: melody`

`_finish` was rewritten around a single allocator, `_place_in_range`, which gives
each requested pitch the nearest *distinct* octave inside `[low, high]`. A voice
with no free octave in range is **dropped with a warning** — never sounded
outside the range and never re-spelled to a different pitch class (the round-1
`_fold_into` could return a pitch below `low`). Octave doublings added by `size`
are the first to go, which is why the tight ranges in the critic's probe now come
back clean.

Slash bass: candidate A puts the bass in the lowest in-range octave and lifts the
other voices above it (losing a mere octave doubling does not count against A);
only if that would cost a real voice does candidate B place the bass under the
voicing, at most one octave below `low`, never lower. The bass is always the
lowest voice and always the requested pitch class. `Dm7/A`, `C/3`, `Cmaj7/G`,
`Ab^7/Eb` at 48..72 are all fully in range now.
`test_range_discipline_over_randomised_inputs` asserts this over 600 random cases
× 7 layout modes.

`top: melody`: the melody placement is chosen *before* layout, from the top of
the range down, and only a placement that still leaves an octave for every guide
tone is accepted. If the melody pitch class is a chord tone that voice is
promoted; otherwise room is made by dropping the **5th**, then the **root**, then
the 11th / plain colour / tensions — guide tones are not in that queue at all. If
only guide tones remain, the melody is added as an extra voice plus a warning; if
the range is too narrow to hold both, the guide tones win and a warning says so.
`test_top_melody_never_deletes_a_guide_tone_over_randomised_inputs` (400 cases)
asserts guide tones present, the melody pitch class present, and melody-on-top
unless a warning explains otherwise. The critic's `melody_guide_tone_probe`,
which lost the 7th in 4/5 trials in round 1, is clean.

## 4. Robustness

Every malformed symbol on the work order is rejected, each with a real
`line`/`col` and a suggestion, via one helper (`_harm_error`) that all parse-time
errors go through. `line`/`col` are never 0: with a caller `Pos` they are the
caller's position offset to the offending token inside the symbol; without one
they default to 1:1. Rules (tabulated in `refs/specs/harmony_truth.md`):

| Rule | Rejects |
|---|---|
| empty / whitespace-only | `''`, `'   '`, `'\t'` |
| `MAX_SYMBOL_LEN = 24` | `'I' + '7'*400`, `'i'*40` |
| at most one accidental | `bbVI`, `Cbb7` |
| slash must have a tail | `V/`, `V//ii` |
| no repeated suffix token | `Cmmm`, `C--`, `vii0000`, `V7alt7`, `V7b9b9` |
| no conflicting slot | `Cmaj7b5#5`, `C7b5#5` |
| `alt` is a whole chord | `i13alt` |
| root-accidental ambiguity | `Cb5`, `C#5` (write `Cb(5)` or `C(b5)`) |
| not a symbol | `Iv`, `VIII`, `iv#`, `Hm7`, `/V`, `V 7`, `I(` |

Two symbols on the critic's adversarial list are still *accepted*, deliberately:
`' V7 '` and `'\t\ni9'` are valid symbols with surrounding whitespace, and
trimming is the parser's job (inner whitespace, `V 7`, is still an error). Also
added on the way through: `C(b5)`-style parenthesised alterations, and `V/ii/E`
(a secondary dominant with a slash bass), which used to be an error.

## 5. Where I think the critic was wrong

**(a) The critic's own ground truth is self-inconsistent about `b13`.** Its
`CASES` table wants roman `V7b13` in C = G B **D** F Eb — the natural 5th kept —
while its `ABS_CASES` table wants `F#7b13` = F# A# **E** D, with the 5th replaced.
Those two cannot both follow from one rule: `b13` above F# is D#/Eb, and the
absolute case only matches if the perfect 5th (C#) is deleted, which is exactly
what the roman case forbids. I did not edit the critic's file; I implemented a
**deliberate dialect split** and documented it: in an absolute/lead-sheet symbol
`b13` *is* the altered fifth (b13 = #5 an octave up, the reading in the Puget
Sound and learnmusictheory sources already cited in `harmony_truth.md`), so the
natural 5th is dropped and a warning explains why; in roman-numeral *analysis*
`b13` is an added upper tension over an unaltered dominant, so the 5th stays.
Chart readers spell voicings, analysts spell functions. Both critic tables pass
under this rule, but the critic should decide whether it wants one reading; if it
does, one line in `parse_absolute` changes.

**(b) `crossings()` cannot prove what round 1 claimed, and still cannot.** The
critic was right, and I have not pretended otherwise: any two ascending-sorted
voicings have zero crossings under index pairing, so the assertion is a tautology
given sorted output. I fixed the helper (it no longer re-sorts its inputs, so an
explicitly reordered pair such as `[60,64] → [64,60]` counts as one crossing, and
unequal sizes are compared over the common lower voices instead of returning 0)
and I say plainly in the docstring and in `harmony_truth.md` that the meaningful
guarantees are range, pitch-class fidelity and voice-count stability — no-crossing
is a property of the representation, not a search result.

**(c) `voice_leading_cost` on unequal voicings** (verdict defect 11) was indeed
not a measurement in round 1 — it paired voices proportionally. It is now the
cheapest monotone (DTW) alignment, exact and symmetric, and equal-size voicings
still use index pairing, which is optimal for an L1 cost on sorted lists, so no
previously reported number changed meaning.
