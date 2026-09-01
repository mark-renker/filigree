# Harmony ground truth (P2)

Machine-readable reference table for `src/filigree/theory.py`.
`tests/test_theory.py` parses this file and asserts every row, so **this file is
the spec and the code must follow it** — not the other way round.

Every value here is derived from first principles: build the scale of the key
from its semitone offsets, take the numeral's degree as the root, then stack the
chord's own intervals over that root. Nothing was copied from another program's
output.

## Conventions

* Pitch class `0 = C`, `1 = C#/Db`, … `11 = B`.
* Pitch classes are listed in **ascending interval order over the chord root**
  (so `IV` in C major is `5 9 0`, not `0 5 9`). Tests compare as sets, so the
  order is documentation only.
* MIDI octaves are scientific: `C4 = 60`, `midi = 12 * (octave + 1) + pc`.
* A bare `7` is a **minor** seventh (10 semitones) — the lead-sheet "dominant
  7th" reading. A major seventh is `^7` / `maj7`. This is why the language has a
  `^` marker at all.
* Case sets triad quality: uppercase = major 3rd, lowercase = minor 3rd. `0` =
  diminished triad, `o7` = fully diminished 7th, `x` = force dominant colour
  (major 3rd + minor 7th) regardless of case. **Exception:** when a
  modal-interchange letter is present the borrowed scale sets the quality and the
  case is only validated — see the next bullet.
* **Modal interchange (RULING, round 2).** A mode letter selects a *scale*, and
  the chord is the **diatonic chord of that scale on that degree** — root,
  third, fifth, seventh and any 9/11/13 are all stacked from the borrowed
  scale. The numeral's written case is *validated, not authoritative*: if the
  case disagrees with the borrowed scale's own quality the scale wins and a
  warning is appended to the caller's `warnings` list. So `iiid` in C is
  Eb **G** Bb (`3 7 10`, C dorian's III), not Eb Gb Bb, and `IVf` is F Ab C
  (C phrygian's iv), with a warning about the upper-case numeral.
  Rationale: borrowing is a *scalar* operation. `iv` in a major key already
  means "the iv of the parallel minor"; a letter naming the source scale cannot
  then be overruled by a case marker that carries no information the scale does
  not already supply, and case-as-quality would make half the borrowed symbols
  non-diatonic to the very scale they name (Eb Gb Bb is not a chord of C dorian
  at all). To *force* a quality against the scale use an explicit token (`x`,
  `0`, `o7`, `b5`, `#5`, `sus2`, `sus4`, `alt`, … plus `m`/`-`/`dim`/`aug` in
  absolute symbols); explicit tokens always win and never warn. Roman spelling has no "minor" token (case is its only
  minor marker), so to write a quality the borrowed scale does not contain, use
  the **chromatic numeral** instead: `biii` = Eb minor in C major, whereas
  `iiid` = Eb major (C dorian's own III).
* Accidentals are chromatic: with an accidental the root is measured from the
  **major** scale degree in every mode (`bVI` = Ab in C major *and* C minor,
  `#iv` = F#); without one it is the effective mode's own degree. This is why
  `bVIIm` in C is Bb (not A): `bVII` is Bb chromatically and mixolydian's own
  7th degree agrees. At most **one** accidental is allowed — `bbVI` is an
  error, not a double flat.
* `alt` expands to the full altered dominant `1 b9 #9 3 #11 b13 b7`, with no
  perfect fifth. `alt` names a *complete* chord, so it may not be combined with
  another extension: `i13alt` and `V7alt7` are errors.
* **`b13` is dialect-dependent** (round 2). In an **absolute / lead-sheet**
  symbol, `b13` *is* the altered fifth (b13 == #5 enharmonically, an octave up),
  so the natural 5th is omitted and a warning is emitted: `F#7b13` = F# A# E D
  (`6 10 4 2`). In a **roman numeral**, `b13` is read analytically as an added
  upper tension over an unaltered dominant, so the perfect 5th stays: `V7b13` in
  C = G B D F Eb. Both readings are attested (see the Puget Sound and
  learnmusictheory sources below for the "b13 replaces the 5th" reading, and
  standard functional analysis for the "added tension" one); Filigree splits them
  by notation because the notations are used by different populations — chart
  readers spell voicings, analysts spell functions.

## Diagnostics and rejection rules (round 2)

`parse_roman` / `parse_absolute` / `parse_chord` take two keyword-only extras:

* `warnings: list | None = None` — soft diagnostics are **appended** (formatted
  by `errors.warn`): a case/scale mismatch on a borrowed numeral, and the `b13`
  fifth-omission note. A warning never changes control flow.
* `pos: Pos | None = None` — threaded into every `HarmonyError`, which always
  carries a real `line`/`col` (≥ 1, the column pointing at the offending token
  inside the symbol) and a `suggestion`.

Hard rejections, all with a suggestion:

| Input | Why |
|---|---|
| `''`, `'   '` | empty / whitespace-only symbol |
| symbols longer than 24 characters | runaway repeat (`I7777…`) |
| `bbVI`, `Cbb7` | more than one accidental |
| `V/` | slash with nothing after it (also rejects `V//ii`) |
| `Cmmm`, `C--`, `vii0000`, `V7alt7` | a repeated suffix token |
| `Cmaj7b5#5` | the same core slot (3rd/5th/7th) set twice, differently |
| `i13alt` | `alt` combined with another extension |
| `Cb5` | ambiguous: `Cb`+`5` or `C`+`b5`; write `Cb(5)` or `C(b5)` |
| `Iv`, `VIII`, `iv#`, `Hm7`, `/V`, `V 7`, `I(` | not a well-formed symbol |

A single balanced parenthesis pair may wrap a trailing alteration group
(`C(b5)`, `V7(b9)`); anything else parenthesised is an error.

## Mode offsets used

| Mode | Semitone offsets from tonic |
|---|---|
| major / ionian | 0 2 4 5 7 9 11 |
| dorian | 0 2 3 5 7 9 10 |
| phrygian | 0 1 3 5 7 8 10 |
| lydian | 0 2 4 6 7 9 11 |
| mixolydian | 0 2 4 5 7 9 10 |
| minor / aeolian | 0 2 3 5 7 8 10 |
| locrian | 0 1 3 5 6 8 10 |
| harmonic-minor | 0 2 3 5 7 8 11 |
| melodic-minor | 0 2 3 5 7 9 11 |
| whole-tone | 0 2 4 6 8 10 |
| chromatic | 0 1 2 3 4 5 6 7 8 9 10 11 |
| blues | 0 3 5 6 7 10 |

## Table

Columns: symbol · key (`-` means an absolute symbol, key-independent) ·
spelled notes · expected pitch classes · expected bass pitch class (`-` = none).

| # | Symbol | Key | Notes | Pitch classes | Bass |
|---|---|---|---|---|---|
| 1 | `I` | C major | C E G | 0 4 7 | - |
| 2 | `ii` | C major | D F A | 2 5 9 | - |
| 3 | `iii` | C major | E G B | 4 7 11 | - |
| 4 | `IV` | C major | F A C | 5 9 0 | - |
| 5 | `V` | C major | G B D | 7 11 2 | - |
| 6 | `vi` | C major | A C E | 9 0 4 | - |
| 7 | `vii0` | C major | B D F | 11 2 5 | - |
| 8 | `ii7` | C major | D F A C | 2 5 9 0 | - |
| 9 | `V7` | C major | G B D F | 7 11 2 5 | - |
| 10 | `IV^7` | C major | F A C E | 5 9 0 4 | - |
| 11 | `I^7` | C major | C E G B | 0 4 7 11 | - |
| 12 | `viio7` | C major | B D F Ab | 11 2 5 8 | - |
| 13 | `iii7` | C major | E G B D | 4 7 11 2 | - |
| 14 | `vi9` | C major | A C E G B | 9 0 4 7 11 | - |
| 15 | `i` | C dorian | C Eb G | 0 3 7 | - |
| 16 | `IV` | C dorian | F A C | 5 9 0 | - |
| 17 | `II` | C phrygian | Db F Ab | 1 5 8 | - |
| 18 | `II` | C lydian | D F# A | 2 6 9 | - |
| 19 | `v` | C mixolydian | G Bb D | 7 10 2 | - |
| 20 | `i` | C aeolian | C Eb G | 0 3 7 | - |
| 21 | `i0` | C locrian | C Eb Gb | 0 3 6 | - |
| 22 | `V7` | C harmonic-minor | G B D F | 7 11 2 5 | - |
| 23 | `i^7` | C melodic-minor | C Eb G B | 0 3 7 11 | - |
| 24 | `III` | C whole-tone | E G# B | 4 8 11 | - |
| 25 | `i7` | C blues | C Eb G Bb | 0 3 7 10 | - |
| 26 | `IV` | C blues | F# A# C# | 6 10 1 | - |
| 27 | `ii` | C chromatic | C# E G# | 1 4 8 | - |
| 28 | `i9` | C minor | C Eb G Bb D | 0 3 7 10 2 | - |
| 29 | `iv11` | C minor | F Ab C Eb G Bb | 5 8 0 3 7 10 | - |
| 30 | `VI^7` | C minor | Ab C Eb G | 8 0 3 7 | - |
| 31 | `V7` | C minor | G B D F | 7 11 2 5 | - |
| 32 | `II13` | C major | D F# A C E B | 2 6 9 0 4 11 | - |
| 33 | `v6` | C major | G Bb D E | 7 10 2 4 | - |
| 34 | `Isus4` | C major | C F G | 0 5 7 | - |
| 35 | `Isus2` | C major | C D G | 0 2 7 | - |
| 36 | `Iadd9` | C major | C D E G | 0 4 7 2 | - |
| 37 | `I6/9` | C major | C D E G A | 0 4 7 9 2 | - |
| 38 | `IIx` | C major | D F# A C | 2 6 9 0 | - |
| 39 | `bVI` | C major | Ab C Eb | 8 0 3 | - |
| 40 | `#iv` | C major | F# A C# | 6 9 1 | - |
| 41 | `bIII` | C major | Eb G Bb | 3 7 10 | - |
| 42 | `bVII` | C major | Bb D F | 10 2 5 | - |
| 43 | `bII^7` | C major | Db F Ab C | 1 5 8 0 | - |
| 44 | `V7b9` | C major | G B D F Ab | 7 11 2 5 8 | - |
| 45 | `V7#9` | C major | G B D F A# | 7 11 2 5 10 | - |
| 46 | `V7b5` | C major | G B Db F | 7 11 1 5 | - |
| 47 | `V7#5` | C major | G B D# F | 7 11 3 5 | - |
| 48 | `V7#11` | C major | G B D F C# | 7 11 2 5 1 | - |
| 49 | `V7b13` | C major | G B D F Eb | 7 11 2 5 3 | - |
| 50 | `V7b9b13` | C major | G B D F Ab Eb | 7 11 2 5 8 3 | - |
| 51 | `V7alt` | C major | G B F Ab A# C# Eb | 7 11 5 8 10 1 3 | - |
| 52 | `Valt` | C major | G B F Ab A# C# Eb | 7 11 5 8 10 1 3 | - |
| 53 | `V/ii` | C major | A C# E | 9 1 4 | - |
| 54 | `V7/ii` | C major | A C# E G | 9 1 4 7 | - |
| 55 | `V7/IV` | C major | C E G Bb | 0 4 7 10 | - |
| 56 | `V7/V` | C major | D F# A C | 2 6 9 0 | - |
| 57 | `V7/vi` | C major | E G# B D | 4 8 11 2 | - |
| 58 | `viio7/V` | C major | F# A C Eb | 6 9 0 3 | - |
| 59 | `iiid` | C major | Eb G Bb | 3 7 10 | - |
| 60 | `IIId` | C major | Eb G Bb | 3 7 10 | - |
| 61 | `IVf` | C major | F Ab C | 5 8 0 | - |
| 62 | `ivf` | C major | F Ab C | 5 8 0 | - |
| 63 | `bIIf` | C major | Db F Ab | 1 5 8 | - |
| 64 | `bVIIm` | C major | Bb D F | 10 2 5 | - |
| 65 | `VIa` | C major | Ab C Eb | 8 0 3 | - |
| 66 | `iva` | C major | F Ab C | 5 8 0 | - |
| 67 | `IIy` | C major | D F# A | 2 6 9 | - |
| 68 | `ii0l` | C major | Db E G | 1 4 7 | - |
| 69 | `VIIh` | C major | B D F | 11 2 5 | - |
| 70 | `vie` | C major | A C Eb | 9 0 3 | - |
| 71 | `Vn` | C major | G B D | 7 11 2 | - |
| 72 | `iva` | A minor | D F A | 2 5 9 | - |
| 73 | `bVIIm` | E major | D F# A | 2 6 9 | - |
| 74 | `Cm9` | - | C Eb G Bb D | 0 3 7 10 2 | - |
| 75 | `Ab^7` | - | Ab C Eb G | 8 0 3 7 | - |
| 76 | `F#7b13` | - | F# A# E D | 6 10 4 2 | - |
| 77 | `Bsus4` | - | B E F# | 11 4 6 | - |
| 78 | `Dm7/A` | - | D F A C | 2 5 9 0 | 9 |
| 79 | `C6/9` | - | C D E G A | 0 4 7 9 2 | - |
| 80 | `E7#9#11` | - | E G# B D G A# | 4 8 11 2 7 10 | - |
| 81 | `Galt` | - | G B F Ab A# C# Eb | 7 11 5 8 10 1 3 | - |
| 82 | `Bm7b5` | - | B D F A | 11 2 5 9 | - |
| 83 | `Co7` | - | C Eb Gb A | 0 3 6 9 | - |
| 84 | `Caug` | - | C E G# | 0 4 8 | - |
| 85 | `Cmaj7` | - | C E G B | 0 4 7 11 | - |
| 86 | `Ebm11` | - | Eb Gb Bb Db F Ab | 3 6 10 1 5 8 | - |
| 87 | `Fsus2` | - | F G C | 5 7 0 | - |
| 88 | `Bb13` | - | Bb D F Ab C G | 10 2 5 8 0 7 | - |
| 89 | `i/3` | C minor | C Eb G | 0 3 7 | 3 |
| 90 | `IV/E` | C major | F A C | 5 9 0 | 4 |
| 91 | `V7/5` | C major | G B D F | 7 11 2 5 | 2 |
| 92 | `Ab^7/C` | - | Ab C Eb G | 8 0 3 7 | 0 |

## Guide tones

Guide tones are the chord's **3rd and 7th** — the pair that carries the
chord-quality information; the 3rd fixes major/minor and the 7th fixes
minor/dominant/major seventh. Fallback chain used when one is absent:
3rd → 4th (sus) → 2nd; 7th → 6th → 5th.

| Symbol | Key | Guide tones (pc) |
|---|---|---|
| `V7` | C major | 11 5 |
| `ii7` | C major | 5 0 |
| `IV^7` | C major | 9 4 |
| `i9` | C minor | 3 10 |
| `viio7` | C major | 2 8 |
| `Isus4` | C major | 5 7 |
| `I` | C major | 4 7 |
| `I6/9` | C major | 4 9 |
| `Galt` | - | 11 5 |
| `Bm7b5` | - | 2 9 |

## Voicing conventions asserted by `tests/test_voicing.py`

* **shell** = root + 3rd + 7th.
* **rootless** (type A) = 3rd + 5th + 7th + 9th, root omitted; the 9th is added
  when the symbol did not spell one.
* **drop-N** = close position with the N-th voice from the top moved down an
  octave (drop-2 is the default).
* **size clamp drop order**, first dropped to last: perfect/altered **5th** →
  natural **11th** → natural **9th** / sus substitutes → altered tensions
  (`b9 #9 #11 b13`) and the **13th/6th** → **root** → **3rd and 7th** (never).
  In `rootless` the root moves to the front of the queue. Ties break by
  dropping the larger interval first.
* **smooth** minimises the sum of absolute semitone movement from the previous
  voicing over all in-range octave placements of the target pitch classes, and
  re-pairs the result in ascending order so voices cannot cross.
* **the close-position guard** (round 2): `voice_chord` also builds the naive
  close-position candidate and keeps whichever of the two moves less, and
  `voice_progression` compares the whole smooth chain with the whole close chain
  and returns the cheaper one. So `movement(smooth) <= movement(close)` holds
  for *every* progression, by construction. Measured worst case over 500 random
  progressions: **0 semitones** (i.e. smooth never lost, and the guard was the
  reason).
* **range discipline** (round 2): every voice lies in `[low, high]`. A voice
  that has no octave inside the range is dropped with a warning — never sounded
  outside it, and never re-spelled as a different pitch class. Octave doublings
  added by `size` are the first to go. The single exception is a slash bass:
  it is placed *inside* the range whenever the upper voices can be lifted above
  it without loss, and only otherwise does it drop below `low`, by at most one
  octave. The bass is always the lowest voice and always has the requested
  pitch class.
* **`top: melody`** (round 2) never deletes a guide tone. The melody pitch class
  is placed as high inside the range as leaves an octave for every guide tone
  below it. If it is not a chord tone, room is made by dropping the **5th**
  first, then the **root**, then the 11th / plain colour / tensions; guide tones
  are never in that queue. If only guide tones remain, the melody is added as an
  extra voice and a warning is appended; if the range is too narrow to keep the
  melody on top *and* the guide tones, the guide tones win and a warning says so.
* **`voice_leading_cost`** pairs equal-size voicings by index (optimal for an L1
  cost on sorted lists) and unequal ones by the cheapest monotone (DTW)
  alignment, so the number is a real measurement in both cases. `crossings`
  compares voices index-by-index in the order given; it is zero for anything
  `voice_chord` returns *because* the output is sorted — the provable claims are
  range, pitch-class fidelity and voice count.

## Sources consulted

Music-theory facts above were checked against:

* Tristan Smither, "Guide-Tone Space: Navigating Voice-Leading Syntax in Tonal
  Jazz", *Music Theory Online* 25.2 —
  https://mtosmt.org/issues/mto.19.25.2/mto.19.25.2.smither.html
  (guide tones = chordal 3rd and 7th; Nettles' "essential chord tones").
* *Music Theory for the 21st-Century Classroom*, "Altered Dominant Seventh
  Chords" (University of Puget Sound) —
  https://musictheory.pugetsound.edu/mt21c/AlteredDominantSeventhChords.html
  (root/3rd/7th unchanged; 5th and 9th are what get altered; `b13` implies the
  natural 5th is absent).
* *Music Theory for the 21st-Century Classroom*, "Jazz Chord Voicings" —
  https://musictheory.pugetsound.edu/mt21c/JazzChordVoicings.html
* learnmusictheory.net, "The Altered Dominant" —
  https://learnmusictheory.net/PDFs/pdffiles/04-02-03-TheAlteredDominant.pdf
  ("when you remove duplicate notes, the only alterations that remain are b9,
  #9, #11 and b13").
* Learn Jazz Standards, "The Altered Scale" —
  https://www.learnjazzstandards.com/blog/altered-scale-in-solos/
  (`1 b9 #9 3 #11 b13 b7`).
* oolimo, "Altered dominant 7th chords" —
  https://www.oolimo.com/en/chord-types/V7-altered
  (the 11 is not added to a V7; using the 4th means omitting the 3rd, i.e. sus4).
* Wikipedia, "Borrowed chord" —
  https://en.wikipedia.org/wiki/Borrowed_chord
* The Jazz Piano Site, "Modal Interchange & Borrowed Chords" —
  https://www.thejazzpianosite.com/jazz-piano-lessons/jazz-chords/borrowed-chords/
* StudyBass, "Borrowed Chords" —
  https://www.studybass.com/lessons/harmony/borrowed-chords/
  (parallel-mode borrowing table for C major / C minor).
* piano.org, "Rootless Voicings: Type A and Type B" —
  https://piano.org/theory/rootless-voicings/
  (type A = 3-5-7-9 from the bottom; type B = 7-9-3-5).

Scope/ergonomics comparisons (Hookpad's one-digit-per-chord keystroke model and
Scaler 3's feature surface) are recorded in `research/landscape.md` per
`refs/BAR.md`.
