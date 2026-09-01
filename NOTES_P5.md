# P5 — `feel` (deterministic humanisation), round 2

Round 1 lost 4 of 6 statistics to the critic. This is the rebuild. The work order
is `refs/verdicts/P5_round1.md`; the target numbers are **not** the `targets`
block of `refs/midi/stats.json` (they do not survive re-derivation) but my own
re-derived ground truth in **`refs/specs/feel_truth.md`** — method, per-file
table, and the two facts about real playing that shaped the model.

Files I own and changed: `src/filigree/feel.py`, `tests/test_feel.py`,
`refs/specs/feel_truth.md` (new), this file, plus the measurement harness under
`research/p5_round2/` (`p5b_stats.py` estimator, `ground_truth.json`,
`measure.py`, `tune.py`, `search.py`, `diag.py`, `candidate.json`).

## Part A — the ground truth, re-derived

`refs/midi/stats.json` says the reference timing deviation is 30.5 ms and the
reference gate ratio 0.49. Measured on the *same twelve files* without assuming
a grid, they are **8.3 ms** and **0.99**. The old estimator quantised onto a
fitted grid, so tempo rubato was counted as note-level deviation, and divided
duration by a nominal rather than the actual inter-onset interval. Round 1 was
therefore aiming at a partly mis-measured bar. Full method, all twelve files and
the corpus IQRs: `refs/specs/feel_truth.md`. `tools/perf_stats.py` and
`refs/midi/**` are not mine to edit and are untouched; `tests/test_feel.py`
carries the re-derived numbers as constants and asserts explicitly that the old
`timing_dev_ms` target lies outside the re-derived range, so the discrepancy
stays visible.

Two findings drove the model design:

1. **The leptokurtosis is a between-passage scale mixture, not per-note spikes.**
   Inside a single isochronous run the reference residuals are mildly *sub*-gaussian
   (kurtosis −0.3 … −0.8); pooled across runs they reach +1 … +11. No
   constant-variance per-note distribution can do that, however heavy its tails.
   Worse, isolated single-note spikes are *removed* by the measurement: they break
   the IOI-ratio test, so the run detector drops them. Only smooth,
   passage-length excursions with a varying amplitude both survive the estimator
   and pool to a heavy tail.
2. **Real deviations reach a large fraction of the tatum** (p99 of |res|/tatum is
   0.28–0.53 per file, individual notes to 1.25). A shift bound below half the
   gap would clip genuine playing — hence `max_shift_ratio` defaults to 0.90.

## Part B — what changed in `feel.py`

| defect (round 1) | round 2 |
|---|---|
| timing and velocity were independent per-note draws, lag-1 r ≈ 0 | **AR(1)/OU processes** for timing (`timing_ar`), velocity (`velocity_ar`) and articulation (`gate_ar`), run over a deterministic per-stream ordering |
| deviations textbook gaussian (kurt +0.058) | **piecewise-linear agogic drift** (`timing_drift_ms`, `timing_drift_span`, `timing_swell`): control points every *n* onsets, each amplitude log-normal, linearly interpolated — a scale mixture, plus a log-normal tail mixture on the per-note term (`timing_df`, excess kurtosis 6/(df−4)) |
| no metrical structure (KW p = 0.60–0.85, span ≤ 1.6 ms) | **`timing_profile_ms`** and **`accent_profile`** per beat of the bar, plus period-2 combs on the tatum (`timing_period2_ms`, `accent_period2`) |
| gate a narrow band around legato (IQR width 0.17–0.48) | **explicit articulation model**: `articulation` blends the notated duration towards a drawn gate ratio that is log-normal around `gate_center` with `gate_spread`, `gate_skew` (wider above the median) and `gate_max` |
| chord scatter one-sided and pitch-blind (lead −0.24 ms) | **melody lead**: `melody_lead_ms` × the note's rank in the cluster (−1 bottom … +1 top) plus two-sided gaussian scatter; `onset_mode="legacy"` keeps round-1 behaviour |
| `velocity 0.99` → sd 49.2 but `1.01` → 1.04; `"400%"` silently meant 4 % | **`_unit_frac`**: `%`/`pct` suffixes are explicit and exact; a bare value > 1.0 warns *ambiguous* and clamps to 1.0; an explicit value above 100 % warns and clamps. No cliff: sd is continuous through 1.0 (a test asserts it) |
| absurd values could reorder notes, stack onsets at 0, or run past the end | the shift window is `[max(0, t−limit, prev_perturbed+min_sep), min(t+limit, piece_end)]` with `limit = max_shift_ratio × min(neighbour gaps)`, evaluated **sequentially against the already-perturbed previous onset**, so order and a minimum separation hold for *any* value |
| NaN silently absorbed by `max(0.0, nan)` | `_finite()` rejects NaN/Inf by name; every warning names the parameter and the value and is raised as a `FeelWarning` as well as delivered to the optional `on_warning` callback |

Also this round:

* **One tempo curve per stave, shared by both hands.** The drift is indexed by
  the stave's cluster timeline, not the per-hand one, so a chord that straddles
  `hand_split` no longer splits into two independent rubatos (that bug spread
  such chords by 40–70 ms).
* **`timing_dist="flat"` is a groove template, not humanisation** — it stays a
  constant signed shift, and the automatic structure (drift, profiles) is *not*
  switched on for it. Explicit values still apply.
* **`pushed` is graded, not a switch.** Round 1 used `flat` + `on_beats=(2,4)`,
  a two-spike histogram. It now anticipates through `timing_profile_ms`
  `(−1.0, −9.5, +0.5, −8.0)` with a full distribution around it.
* **AUTO defaults.** Structural fields default to `AUTO` (`None`) and are filled
  from `AUTO_DEFAULTS` only when the corresponding classic magnitude is
  non-zero. So `feel { timing: 16ms }` — all `parse.py` accepts today — still
  gets memory, accents, articulation and lead, while a zero spec stays a
  **bit-exact** no-op.
* Clamp warnings fire only above a floor of `max(3, 2 % of notes)`, one per
  parameter, with a reason specific to that parameter.

## Part C — measured, candidate vs reference

96-bar 16th-note probe at 120 bpm (1536 notes), measured with the *reference*
estimator (`research/p5_round2/p5b_stats.py`), median over 5 seeds
(11, 23, 37, 59, 71). "Before" = the critic's round-1 numbers.

| statistic | round 1 | round 2 (loose / tight / pushed / breath) | reference median [IQR] |
|---|---|---|---|
| median \|residual\| ms | 8.1–11.5 | 8.70 / 8.57 / 8.72 / 8.31 | 8.32 [6.90, 10.30] ✓ |
| residual ÷ tatum | — | 0.070 / 0.068 / 0.070 / 0.066 | 0.076 [0.071, 0.084] — marginally low |
| residual excess kurtosis | +0.058 (pushed −1.70) | **+3.68 / +4.05 / +4.01 / +5.44** | +5.64 [+2.87, +7.79] ✓ |
| velocity sd | 9.6–14.5 | 13.4 / 11.6 / 12.6 / 12.9 | 11.86 [10.73, 14.53] ✓ |
| velocity lag-1 r | **−0.010** | **+0.42 / +0.44 / +0.44 / +0.49** | +0.452 [+0.385, +0.538] ✓ |
| gate IQR width (at median) | 0.17–0.48 (1.04–1.16) | **2.60 / 1.74 / 1.85 / 3.05** (1.09 / 0.97 / 0.91 / 1.09) | 2.93 [1.59, 3.63] at 0.986 ✓ |

Isolation runs (4000 synthetic notes, `research/p5_round2/candidate.json`):
timing lag-1 r **+0.76 … +0.87** against a reference residual lag-1 of
+0.55 [+0.45, +0.68] — **mine runs high**, i.e. my rubato is smoother than a real
player's; it is the one statistic where I overshoot, and I am not claiming it as
a pass. Kruskal–Wallis across beats of the bar: p = 8e-23 / 5e-18 / 7e-97 / 9e-23
with spans 6.4 / 5.5 / 11.0 / 6.2 ms (round 1: p 0.60–0.85, span ≤ 1.6 ms);
across sub-beats p = 7e-5 / 1.5e-2 / 6e-5 / 1.5e-4. Chord spread
17.4 / 14.2 / 16.8 / 18.3 ms (ref 16.93 [14.97, 21.09]); top-voice lead
−6.3 / −6.8 / −5.2 / −7.2 ms (ref −5.32); pitch↔onset r −0.40 / −0.80 / −0.60 / −0.80
(ref −0.450).

**Invariants preserved.** Byte-identical MIDI over 3 invocations for the probe,
`examples/pulse.fil` and `examples/nocturne.fil`; four different seeds give four
different renders; `0 %` feel renders md5-identical to no feel at all
(`d69d0769…`) — bit-exact; across 14 edge probes (including `timing 2000ms`,
`timing 1e9`, `flat −2000ms`, NaN, ±Inf, `velocity 0.99/1.0/1.01/"400%"/"12%"`,
negative gate, a single note, 200 notes on one key): 0 inversions, at most 1 note
at t = 0, no NaN/Inf, pitch multiset unchanged, every warning naming its
parameter and value.

**Honest limits.** `examples/pulse.fil` (39 notes) and `examples/nocturne.fil`
(25 notes) are too short for this estimator — no isochronous run of ≥ 8 onsets
survives, so their residual statistics are *undefined*, not zero, and their
velocity lag-1 over 25–39 notes is meaningless (it comes out anywhere from −0.28
to +0.42). That is why the timing statistics above are measured on a rendered
probe; the two examples' gate, velocity and chord numbers are in
`candidate.json`. `residual ÷ tatum` sits just under the reference q1 for all
four presets: raising it means either raising |residual| out of its own IQR or
lowering the probe's tatum, so I left it low rather than gaming one statistic
into another's failure.

## Tests

`PYTHONPATH=src python -m pytest -q` → **853 passed, 0 failed** (whole repo).
`tests/test_feel.py` alone is **85 tests**. It was rewritten: the round-1 tests
that asserted the superseded `stats.json` targets, `PUSHED["timing_dist"] ==
"flat"`, the narrow gate band, and strict per-note locality are gone, because
each of them now encodes a defect.

Notably replaced: `test_locality_pitch_change_does_not_move_other_notes` →
`test_memory_decays_forward_only`. With AR memory, editing a note *may* move
later notes; the test now requires that nothing **earlier** ever moves and that
the influence **decays** forward. That is the honest contract of a model with
memory, and it is the one round-1 property I deliberately gave up.

New coverage: per-preset velocity lag-1 r, residual spread, leptokurtosis, gate
IQR width and velocity sd against the re-derived IQRs; an explicit memoryless /
gaussian mode (`timing_dist="iid"`) as a control; the metrical profile in
isolation and pooled over seeds; melody lead; the unit cliff at 1.0; `"400%"`;
NaN/Inf by name; four absurd-parameter probes checking order, t = 0, tail bound,
pitch multiset; determinism over 3 invocations; seeds differing; `0 %` bit-exact;
and a self-check of the miniature estimator the tests use against a known
answer.

## Amendment requests (files I must not edit)

1. **`parse.py` — extend the `feel { … }` field whitelist.** It accepts only
   `timing, velocity, gate, onset, release, on, seed` plus bare tokens mapped to
   `timing_dist`/`onset_mode`/`release_mode`. Every round-2 field is therefore
   unreachable from `.fil` source, and presets are the only way to get at them.
   Requested: pass through `timing_df, timing_ar, timing_rel, timing_profile_ms,
   timing_period2_ms, timing_drift_ms, timing_drift_span, timing_swell,
   velocity_ar, accent_profile, accent_period2, articulation, gate_center,
   gate_spread, gate_skew, gate_ar, gate_max, melody_lead_ms, beats_per_bar,
   tatum_beats, hand_split, max_shift_ratio` (all already validated in
   `normalise()`, all named, none of them hidden constants). Until then the
   `AUTO` defaults are what a hand-written `feel` block gets.
2. **`resolve.py` — pass the metre into `apply_feel`.** It calls
   `feel_mod.apply_feel(notes, fspec, tempo, seed)`, so the metrical profiles and
   `on_beats` must assume `beats_per_bar = 4` (a `FeelSpec` field, but the
   resolver never sets it). Requested: `apply_feel(..., spec=dataclasses.replace(
   fspec, beats_per_bar=score.meter_numerator))`, or an extra keyword. Anything
   in 3/4, 5/4 or 6/8 currently gets a 4/4 accent pattern.
3. **`resolve.py` — forward feel warnings into the diagnostics stream.**
   `apply_feel` takes an `on_warning` callback and otherwise raises
   `FeelWarning` through `warnings`, which is invisible in the CLI. One shipped
   example already triggers a legitimate clamp warning (`timing=−6 …clamped on 3
   of 12 notes`) that a user cannot see. Requested: route `on_warning` into the
   same reporter the parser uses.
4. **A repo-level `conftest.py` putting `src/` and `tools/` on `sys.path`** —
   `tests/test_feel.py` still does it itself, as in round 1.
