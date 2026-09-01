# P2 — Harmony engine, critic round 1

Critic: fresh context. Did not build this code. Judged `src/filigree/theory.py` and
`src/filigree/voicing.py` only. `NOTES_P2.md` and `refs/specs/harmony_truth.md` were **not**
read (builder-authored); all expected values were derived independently in
`tests/critic_p2_truth.py` (91 chord symbols + 13 hand-written mode spellings + 32 adversarial
inputs + 5 measured progressions + a 400-case randomised probe).

Evidence is valid: the module imports cleanly, the test file runs to completion, no unrelated
crashes. Reproduce with `python tests/critic_p2_truth.py`.

---

## Forced picks

| Criterion | Pick | Deciding citation |
|---|---|---|
| **Correctness** | **REFERENCE** | 7 wrong pitch-class sets out of 12 modal-interchange symbols. `iiid` in C minor = **Eb Gb Bb** `[3,6,10]`; C dorian is C D Eb F G A Bb, so the diatonic triad on its 3rd degree is **Eb G Bb** `[3,7,10]`. Cause: `theory.py:703` `sp = _Spelling(4 if is_upper else 3)` — the borrowed mode is consulted for the root only (`theory.py:692`), never for the quality. BAR P2: "any wrong pitch class is a loss, full stop." |
| **Voice leading** | **REFERENCE** | BAR P2 requires smooth movement ≤ naive close position. `ii7 → I`, C major, `size=4`, range 48..72: **smooth = 11 semitones, close = 9**. Worse in **15/400** randomised progressions; worst margin `['IV^7','iv11','iii','vii0']` in F# mixolydian, range 50..62, size 5: **smooth 68 vs close 58**. Also 0 crossings but notes outside the requested range (below). |
| **Concision** | **CANDIDATE** | A plain diatonic chord is **1 character** (`i`), against Hookpad's 1 digit/chord ([landscape.md:60](../../research/landscape.md)) and the ≤4-char bar. A borrowed chord is 4 characters (`iiid`) where Hookpad needs a menu; a secondary dominant is 4 (`V7/ii`). This is the one criterion the candidate wins outright. |
| **Robustness** | **REFERENCE** | 6 malformed symbols are silently **accepted**: `V/` → plain V `[7,11,2]` (`theory.py:661` sets `bass=""`, `_apply_bass` returns the chord unchanged at `theory.py:600`), `Cmmm` → Cm, `C--` → Cm, `vii0000` → vii°, `V7alt7` → alt, `i13alt` (the 13 is silently discarded). Every `HarmonyError` raised carries `line=0, col=0` (see the `(line:col=0:0)` column in section B output), against SPEC §12 "every diagnostic carries `file:line:col`". |

---

## Defects, ordered by severity

**1. Modal interchange derives only the root from the borrowed mode; quality comes from letter case.** (`theory.py:688-704`)
The mode letter must select the scale and the chord must be the diatonic chord of that scale on
that degree, with the written case validated (mismatch → warning). It is not. 7 of 12 tested
symbols are wrong:

```python
parse_roman("iiid", 0, "minor").pitch_classes()  # -> [3, 6, 10]   expected [3, 7, 10]  (Eb G Bb)
parse_roman("IVf",  0, "major").pitch_classes()  # -> [5, 9, 0]    expected [5, 8, 0]   (F Ab C)
parse_roman("IVy",  0, "major").pitch_classes()  # -> [6, 10, 1]   expected [6, 9, 0]   (F# A C, dim)
parse_roman("iil",  0, "major").pitch_classes()  # -> [1, 4, 8]    expected [1, 5, 8]   (Db F Ab)
parse_roman("iih",  0, "major").pitch_classes()  # -> [2, 5, 9]    expected [2, 5, 8]   (D F Ab, dim)
parse_roman("ive",  0, "major").pitch_classes()  # -> [5, 8, 0]    expected [5, 9, 0]   (F A C)
parse_roman("IIIe", 0, "major").pitch_classes()  # -> [3, 7, 10]   expected [3, 7, 11]  (Eb G B, aug)
```
Only the letters whose diatonic quality happens to match the written case (`n`, `d`, `m`, `a`,
and `h` on V) are right. There is additionally **no warning mechanism at all**: no function in
`theory.py` takes a warning collector, so the required "mismatch → warning, not silent
override" cannot be emitted even in principle.

**2. `mode="smooth"` is not ≤ close position.** (`voicing.py:277` `_layout_smooth`, with
`voicing.py:173-183` padding)
```python
A, B = parse_roman("ii7", 0, "major"), parse_roman("I", 0, "major")
V.voice_progression([A, B], VoicingSpec(48, 72, "smooth", size=4))  # [[50,53,57,60],[52,55,60,64]] cost 11
V.voice_progression([A, B], VoicingSpec(48, 72, "close",  size=4))  # [[50,53,57,60],[48,52,55,64]] cost  9
```
The docstring's "no worse than close position by construction" argument fails because `size`
padding (`voicing.py:176-183`) invents octave doublings that are laid out *before* the
assignment sees them, and `_finish` then folds/de-duplicates the result. `IV^7 → I`, size 5,
48..72: smooth 17 vs close 7 (2.4×).

**3. Voicings leave the requested range.** (`voicing.py:476` `_fold_into`, `voicing.py:458` bass floor)
```python
_fold_into(70, 60, 67)                      # -> 58, i.e. 2 semitones BELOW low
voice_chord(parse_roman("Isus4",5,"minor"), VoicingSpec(55, 67, "close", size=5))
                                            # -> [58, 60, 65, 70, 77]   70 and 77 > high=67
voice_chord(parse_absolute("Dm7/A"), VoicingSpec(48, 72, "smooth", size=4))
                                            # -> [45, 50, 53, 57, 60]   45 < low=48
voice_chord(parse_absolute("C13"),   VoicingSpec(60, 67, "literal"))
                                            # -> [57, 58, 60, 62, 64, 67]  57,58 < low=60
```
Every slash-bass chord breaks the range because `_finish` deliberately uses `floor = spec.low - 12`.
`range: C3..C5` in SPEC §4.1 is then not a guarantee of anything.

**4. `top: melody` deletes the chord's 7th.** (`voicing.py:433-439` — `pitches[-1] = target` overwrites a voice instead of re-selecting)
```python
voice_chord(parse_roman("I^7",0,"major"), VoicingSpec(48,72,"smooth",size=4,top="melody"), None, 4)
# -> [48, 52, 55, 64]  pcs {0,4,7}: the maj7 (B) is gone, E is doubled
voice_chord(parse_roman("V7",0,"major"),  VoicingSpec(48,72,"smooth",size=4,top="melody"), None, 2)
# -> [50, 55, 59, 62]  pcs {2,7,11}: the b7 (F) is gone — V7 no longer sounds dominant
```
4 of 5 trials lose a guide tone, contradicting the engine's own `DROP_RANK` claim
(`voicing.py:113-120`) that "the 3rd and 7th are the guide tones and never leave".

**5. Malformed symbols silently accepted** (list in the Robustness row above). `V/` is the worst:
a truncated secondary dominant compiles to a plain V with no diagnostic.

**6. No position in any diagnostic, and the engine has no call sites.**
`errors.HarmonyError` is always raised with default `line=0, col=0`. `grep -rn "parse_roman\|parse_chord\|voice_chord" src/` matches nothing outside `theory.py`/`voicing.py`, and
`filigree.compile_source("harm | I | V |")` raises `ModuleNotFoundError: No module named
'filigree.resolve'`. So the harmony engine is currently a library nothing calls, and there is
no code path that could attach `file:line:col` to its errors.

**7. `Cb5` is ambiguous and resolved the surprising way.** `parse_absolute("Cb5")` → `[11, 6]`
(a Cb power chord), not C with a flat fifth. Two readings of one token are both defensible —
a BAR P1 fail condition.

**8. `mode="drop"` degenerates to `close`.** `voice_chord(parse_absolute("C13"), VoicingSpec(48,72,"drop",size=4))`
→ `[48,52,58,69]`, byte-identical to `mode="close"`, because `voicing.py:240` only lifts the
stack when `low+12+span <= high` and the drop is then folded back. In the SPEC's own default
range the mode does nothing.

**9. `bVI` in a minor key returns G major.** `parse_roman("bVI", 0, "minor")` → `[7,11,2]`:
the flat is applied on top of aeolian's already-flat 6th. Standard practice writes `bVI` in
minor for Ab. Accidental absorption exists for borrowed modes (`theory.py:696`) but not for the
key's own mode.

**10. `7b13` keeps the natural 5th.** `parse_absolute("F#7b13")` → `[6,10,1,4,2]`, i.e. C# and
D a semitone apart in the same chord. Arguable, but lead-sheet practice reads b13 as the
altered fifth. Low severity.

**11. The measurement helpers flatter the engine.** `crossings()` (`voicing.py:516`) returns 0
whenever the two voicings differ in length, and `voice_leading_cost()` (`voicing.py:501-507`)
uses an ad-hoc proportional pairing for unequal sizes — exactly the case that `size` padding
creates. Zero-crossings claims proven with this helper are not proof.

---

## The single largest gap

**Modal interchange — the feature the language advertises nine letters for — is a root
transposition table with no quality derivation and no validation.** Seven of the twelve borrowed
symbols I tested produce chords that do not exist in the mode they claim to borrow from
(`iiid` in C minor gives Eb **Gb** Bb, a chord from no mode that contains Eb G Bb), and because
no function in `theory.py` can emit a warning, the case/scale conflict is resolved silently in
favour of the typographic case every time. Everything else on this list is a bug; this one is a
missing design.
