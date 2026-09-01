# P2 round 2 — result summary (builder)

Files changed (all owned by P2): `src/filigree/theory.py`, `src/filigree/voicing.py`,
`tests/test_theory.py`, `tests/test_voicing.py`, `refs/specs/harmony_truth.md`,
`NOTES_P2.md`. `tests/critic_p2_truth.py` untouched.

## Verification
- `python -m pytest tests/test_theory.py tests/test_voicing.py tests/critic_p2_truth.py -q`
  → **286 passed** (both with and without `-p no:randomly`).
- `python -m pytest tests/critic_p2_truth.py -q` → **4/4 passed**
  (`test_scales`, `test_chords`, `test_voicing`, `test_bass_range`).
- `python tests/critic_p2_truth.py` → 13/13 scales OK, **0 mismatches / 91 chord
  symbols**, all malformed adversarial symbols rejected, slash-bass and
  top:melody probes clean, randomised probe **smooth worse than close in 0/400**.
- Determinism: two consecutive full evidence runs are byte-identical.
- `python -m py_compile` clean on all four edited Python files.
- Full suite: only unrelated failures remain, in other pieces' files
  (`test_integration.py::test_curve_value_at_returns_nan_inside_a_hole` always;
  `test_gesture.py`/`test_mpe.py` bend tests depending on the random ordering
  seed). No harmony/voicing test fails.

## Headline numbers
- Worst-case smooth-minus-close movement margin over **500** random progressions:
  **0 semitones** (round 1 lost by up to +10).
- 0 crossings and ascending output over 500 progressions; range discipline
  asserted over 600 cases × 7 layout modes; guide-tone preservation over 400
  `top: melody` cases.

## New API (keyword-only, back-compatible)
`parse_roman/parse_absolute/parse_chord(..., *, warnings: list | None = None,
pos: Pos | None = None)`, `normalise_mode(mode, *, pos=None)`,
`voice_chord(..., *, warnings=None)`, `voice_progression(..., *, warnings=None)`,
`theory.MAX_SYMBOL_LEN = 24`, `voicing.progression_movement()`.

**Lead action item:** `resolve.py` calls the parsers positionally and passes
neither `pos` nor `warnings`; threading its `Pos` and one shared warnings list
would give real line/col and modal-interchange diagnostics for free.

Open disagreement with the critic (argued in `NOTES_P2.md` §5): the critic's own
`CASES`/`ABS_CASES` tables demand contradictory `b13` semantics; Filigree resolves
it as a documented roman-vs-lead-sheet dialect split.
