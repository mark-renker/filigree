# NOTES_P7 — resolver / integration (`resolve.py`, `examples/`, `tests/test_integration.py`)

Owned files: `src/filigree/resolve.py`, `tests/test_integration.py`, `examples/**`,
`conftest.py`, `pyproject.toml`. Nothing else was touched.

## Status

`resolve(doc) -> Score` is complete: directives, bar/slot expansion to absolute
beats, `harm` → `theory` + `voicing` (running previous-voicing state) →
`ir.ChordEvent`, all note-token kinds (degrees, chord tones, anchors, absolutes,
ties, retriggers, rests, chords, groups, alternations, probability, gate,
velocity, accents), named voices, curve lanes in lane-local normalised time with
`!time=bar|note`, `@voice` lane targeting, attached gestures at note/lane/stave
level, `ctx.resolve_target` for `>`, `>3`, `>+`, `>-`, `>|`, feel, ids, sorting
and warning collection.

7 example files (`examples/*.fil`) all compile with **zero warnings**, render,
and pass `tools/audit_mpe.py` with **0 failures**. `tests/test_integration.py`
has 75 tests / 153 assertions and is green.

---

## Bug list / cross-file requests

Each item is a file + function + symptom + minimal repro. None of these are in
files I own, so none were fixed here.

### 1. `ir.Score.to_json()` serialises NaN sentinels as bare `NaN` (invalid JSON)

* **File / function**: `src/filigree/ir.py`, `Score.to_json()` (frozen contract)
  — the curve-point branch does `round(v, 5)` with no finite check.
* **Symptom**: a "no data" NaN breakpoint round-trips into the JSON payload as
  the bare token `NaN`. `json.dumps` emits it, but `JSON.parse` in the browser
  rejects it, so `web/` cannot load any score whose curves have holes.
* **Repro**:
  ```
  $ PYTHONPATH=src python -m filigree.cli json examples/tasks.fil | grep -c NaN
  13
  ```
  Also `blue_iron.fil` 7, `gesture_algebra.fil` 5, `pulse.fil` 3,
  `nocturne.fil` 1, `dorian_drift.fil` 1.
* **Request**: map non-finite curve values to `null` in `to_json()` (and have
  `web/` treat `null` as "no data"). The resolver cannot avoid producing them:
  a NaN sentinel at the start of every gap is the contract for
  "write nothing here", which `mpe._lane_frames` relies on.

### 2. `cli.py cmd_explain` prints `nan` in the per-lane min/max summary

* **File / function**: `src/filigree/cli.py`, `cmd_explain` — takes
  `min()`/`max()` over raw curve point values.
* **Symptom**: lanes with a hole print `bend[nan..nan×N]`.
* **Repro**: `PYTHONPATH=src python -m filigree.cli explain examples/tasks.fil | grep -c nan` → `13`.
* **Request**: filter non-finite values before `min`/`max`, and show the hole
  count instead (e.g. `bend[-1.00..+1.00×18, 2 holes]`).

### 3. `gesture.GestureCtx.lane_range` is a single range, not per-lane

* **File / function**: `src/filigree/gesture.py`, `GestureCtx` /
  `lane_range_for`.
* **Symptom**: a multi-lane gesture (e.g. `press(...) | bend(...)`) is clamped
  against one range — the one for `ctx.lane_default`. A per-lane `!range=` on a
  *different* lane than the context lane is not honoured.
* **Workaround in resolve.py**: every lane is evaluated in its own pass, with a
  fresh `GestureCtx` whose `lane_default`/`lane_range` are that lane's, so in
  practice each lane does get its own range. The limitation only bites if one
  gesture expression is meant to be clamped differently per lane in a single
  evaluation.
* **Request** (low priority): make `lane_range` a `dict[str, tuple]` with a
  fallback.

### 4. `tools/audit_mpe.py` thinning check changed semantics mid-flight

* **Symptom**: the check was a hard floor (`thinning removes >= 60% ...`,
  `ratio=0.571` FAIL on `examples/pulse.fil`) in one revision and a reported
  metric (`thinning ratio is a reported metric, not a floor`) in the next. Not a
  bug to fix — recorded so nobody is surprised that an earlier "PASS on
  pulse.fil" claim in my own status notes was made against the metric version.
* **Consequence**: `examples/pulse.fil` was rewritten to use `shape: linear`
  (`gesture snap`, `press!shape=linear` in `part riff`) because ease-shaped
  ramps on 0.23 s notes emit an event at essentially every grid step. That is
  driven by `mpe`'s own resampling, **not** by the resolver's point count:
  raising `resolve._TOL_UNIPOLAR` from 0.004 → 0.02 moved the audited ratio by
  less than 0.01, because `mpe` re-samples `Curve.value_at` on its own grid and
  thins with its own tolerance. If a real thinning floor is wanted, the fix
  belongs in `mpe.thin` (hold-semantics tolerance for short notes), not here.

### 5. Pre-existing failures in other modules' tests (not caused by, and not
fixable from, P7's files)

At the time of writing, `python -m pytest -q` is green except:

```
FAILED tests/test_gesture.py::test_reclock_2_wiggle_times_ramp_is_still_5p5_hz
FAILED tests/test_gesture.py::test_reclock_4_wiggle_added_to_a_ramp_is_still_5p5_hz
FAILED tests/test_mpe.py::test_linear_ramp_needs_interior_points_under_hold_semantics
FAILED tests/test_mpe.py::test_slow_bend_holds_within_three_cents
```

These are `gesture.py` (frequency preservation under time-scaling of a
`wiggle` composed with a `ramp`) and `mpe.py` (hold-semantics thinning)
issues. `tests/test_integration.py` is fully green and every example renders
and audits clean, so nothing in the integration layer depends on them.
Earlier in the session `tests/test_theory.py` had 8 failures
(`iiid`/`IVf`/`VIIh`/`vie` modal-interchange pitch classes, `bbVII` double
accidental, `F#7b13`); those have since been fixed by another agent.

---

## Design decisions worth knowing (resolver behaviour that is a choice, not a bug)

1. **Ruling 7 scope.** Only *slot-count* mismatch warnings are suppressed for
   curve lanes (they are resampled by design). Parse warnings matching
   `lane '<name>' has N slots` are dropped when `<name>` is a curve lane
   (`bend|press|timbre|amp|pan|cc\d+`). **Bar-count** (`lane-bars`) mismatches
   are still reported for curve lanes, since a missing bar is a real mistake.
2. **"No data" representation.** One NaN sentinel is written at the start of
   every gap (leading, interior, trailing). A lane with no finite sample at all
   gets no `Curve` object. See bug 1 for the JSON consequence.
3. **Half-open sampling.** Curves are sampled over `[start, start+dur-1e-6]` and
   gesture `u` is clipped to `1-1e-9`, because gesture windows and harmonic
   segments are half-open at 1.0 and a beat landing exactly on a bar line
   otherwise maps into the next bar.
4. **Priority merge per `(note, lane)`**, first non-NaN sample wins:
   voice-specific explicit lane → generic explicit lane → inline gesture call
   in the lane → note-attached `!gesture` → lane `!gesture=` → stave `gesture`.
   So explicit glyphs beat attached gestures on the same lane and window, while
   an attached gesture still fills lanes the glyphs do not cover.
5. **Sample grid.** `dt = grid_ms/1000 * tempo/60` beats, halved for `bend`.
   Points are thinned with a linear-prediction deadband
   (`_TOL_BEND = 0.01` st ≈ 2 LSB at a 48 st member range,
   `_TOL_UNIPOLAR = 0.008` ≈ one 7-bit step).
6. **`amp` lane overrides velocity after feel.** The `amp` value at note start
   becomes the note-on velocity, and this runs *after* `feel.apply_feel`, so a
   feel's velocity jitter is discarded on notes that have an `amp` curve. This
   is deliberate (an explicitly drawn amplitude should win) but it does mean
   `feel` + `amp` on the same note do not compose.
7. **`top: melody` is a two-pass approximation**: voice once with
   `melody_pc=None`, resolve the note stream, then re-voice each chord with the
   melody pitch class sounding at its start.
8. **Inline gesture counting is structural.** The number of inline gesture
   leaves in a curve lane is counted from the AST, never by building the
   gesture, because building it would resolve `>` targets for bars the note
   does not touch and emit bogus range warnings.
9. **Phrase transforms implemented**: `transpose(n)`, `retro`, `rot(n)`,
   `mask("...")`. Anything else warns
   `phrase transform 'x' is not implemented yet` and plays the part unchanged.
10. **`_copy_lane` deep-copies slots**, because transforms mutate `PitchTok` in
    place and one `part` may be `play`ed twice with different transforms.
11. **Duplicate warnings are de-duplicated** by exact string, since a `>` target
    is re-resolved for every note sharing a bar.

## Ergonomics observations on the surface syntax (not bugs)

* A lane body must fit on one physical line; a continuation line starting with
  `|` is a parse error. Long `voices` lanes get wide.
* A stave cannot be written on one line — `after`, `feel`, `gesture` and each
  lane need their own line.
* An inline gesture inside a curve lane needs call parentheses (`cry()`, not
  `cry`), while a note attachment does not (`0!cry`).
* Octave prefixes do not combine with chord tones (`_~3` is a parse error), so
  registering a chord-tone line requires anchors (`@low`) or absolutes.
