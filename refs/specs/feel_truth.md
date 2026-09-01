# `feel` ground truth, re-derived (P5 round 2)

This document is the target for `src/filigree/feel.py`. It supersedes the
`targets` block of `refs/midi/stats.json`, which does not survive
re-derivation: `stats.json` reports a timing deviation of 30.5 ms and a gate
ratio of 0.49 for the same twelve files where a grid-free estimator finds
**8.3 ms** and **0.99**. The old measurement quantised the performances onto an
assumed grid (so tempo rubato was counted as note-level deviation) and divided
each note's duration by a nominal, not the actual, inter-onset interval.
Everything below is measured directly from note-on/note-off times, with no
assumed grid and no assumed tempo.

Corpus: the twelve solo-piano performances in `refs/midi/` (MAESTRO v3.0.0,
CC BY-NC-SA 4.0 — see `refs/midi/SOURCES.md`; dataset:
<https://magenta.tensorflow.org/datasets/maestro>). They are human performances
captured on a Disklavier, so the note times *are* the ground truth.

Estimator: `research/p5_round2/p5b_stats.py`; raw output
`research/p5_round2/ground_truth.json`.

## Method

1. **Chords.** Onsets within **50 ms** of the first onset of the cluster are one
   chord; the cluster's onset is its earliest note. Chord statistics are taken
   inside the cluster, timing statistics from the cluster onsets.
2. **Isochronous runs.** Walk the inter-onset intervals and grow a run while the
   next IOI is within **0.75–1.34×** the running median of the run. Keep runs of
   **≥ 8** onsets. Typically 8–76 % of a performance qualifies (median 34 %).
   This is the key step: it finds passages the player intended as an even pulse
   without ever assuming a metronome.
3. **Residuals.** Inside each run, fit a **degree-1** line onto onset index and
   subtract it. This removes the local tempo *and* a linear accelerando, so what
   is left is note-level deviation. The fitted slope is the **local tatum**.
   Residual statistics are pooled across runs and files.
4. **Velocity.** Phrases split at gaps of **> 0.60 s**, phrases of ≥ 4 notes.
   Autocorrelation is computed on the velocity sequence in performance order.
5. **Gate.** `duration ÷ (next onset − this onset)` in the same stream,
   clipped at **4.0** (a pedalled note held over ten others is not informative).
6. **Hands.** Split at pitch **60** for stream-level statistics.
7. Per file one number per statistic; the corpus figure is the **median** across
   the twelve files, with the inter-quartile range as the tolerance band. Gate
   quartiles are pooled across notes, and the IQR *width* is also taken
   per file and then aggregated.

## Corpus targets — median [q1, q3] over 12 files

| statistic | median | q1 | q3 | notes |
|---|---|---|---|---|
| local tatum (ms) | 108.3 | 96.4 | 131.7 | 4× range across the corpus |
| median abs residual (ms) | **8.32** | 6.90 | 10.30 | `stats.json` claimed 30.5 |
| residual ÷ tatum | 0.076 | 0.071 | 0.084 | scale-free version of the above |
| residual excess kurtosis | **+5.64** | +2.87 | +7.79 | strongly leptokurtic |
| residual lag-1 r | +0.55 | +0.45 | +0.68 | timing has memory |
| velocity sd | **11.86** | 10.73 | 14.53 | |
| velocity IQR | 15.0 | 13.4 | 19.1 | |
| velocity lag-1 r | **+0.452** | +0.385 | +0.538 | ACF 1–8: .45 .43 .42 .39 .37 .36 .35 .33 |
| gate ratio (pooled) | **0.986** | 0.447 | 3.408 | IQR *width* 2.93 [1.59, 3.63] |
| chord spread (ms) | 16.93 | 14.97 | 21.09 | |
| chord top-voice lead (ms) | **−5.32** | −11.17 | −3.66 | melody lead |
| chord pitch↔onset r | −0.450 | −0.500 | −0.287 | higher notes earlier |

Two further facts that shaped the model:

* **The leptokurtosis is a scale mixture between passages, not spikes inside
  one.** Measured *within* a single isochronous run the residuals are mildly
  *sub*-gaussian (kurtosis −0.3 … −0.8); pooled across runs they reach +1 … +11.
  A constant-variance per-note distribution cannot produce that, whatever its
  tails are. Isolated single-note spikes do not survive either — they break the
  IOI-ratio test and the run detector excludes them. Only *smooth, large,
  passage-length* excursions both survive the estimator and pool to a heavy
  tail. Hence the piecewise-linear agogic drift with a log-normal amplitude
  (`timing_drift_ms`, `timing_drift_span`, `timing_swell`).
* **Absolute deviations reach a large fraction of the tatum.** The p99 of
  `|residual| ÷ tatum` is 0.28–0.53 per file, with individual notes up to 1.25.
  This is why `max_shift_ratio` defaults to 0.90 rather than to something below
  0.5: a bound at half the gap would clip real playing.

## Per-file numbers

| file | notes | tatum ms | \|res\| ms | res/tatum | kurt | res r1 | vel sd | vel r1 | gate med | gate IQR w | top lead ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Alexander Scriabin — 3 Etudes Op 65 | 4019 | 133 | 9.80 | 0.073 | +3.26 | +0.55 | 14.27 | +0.472 | 0.94 | 3.69 | −10.0 |
| Antonio Soler — Sonata No 10 in B Minor | 3483 | 123 | 6.84 | 0.056 | +1.05 | +0.40 | 12.01 | +0.347 | 0.84 | 1.13 | −3.9 |
| Claude Debussy — Feux d'artifice (Book II) | 3054 | 98 | 7.39 | 0.076 | +7.50 | +0.46 | 11.65 | +0.579 | 1.00 | 2.11 | −1.3 |
| Domenico Scarlatti — Sonata K 54 | 1113 | 319 | 26.39 | 0.083 | +1.71 | +0.69 | 9.77 | +0.431 | 1.06 | 1.11 | −24.7 |
| Felix Mendelssohn — Rondo Capriccioso Op 14 | 4869 | 92 | 8.51 | 0.092 | +5.20 | +0.53 | 15.30 | +0.635 | 1.13 | 3.62 | −5.9 |
| Frédéric Chopin — 12 Etudes Op 25 | 5938 | 77 | 5.95 | 0.077 | +3.91 | +0.55 | 8.41 | +0.349 | 1.08 | 1.74 | −11.5 |
| Franz Liszt — La Campanella | 4249 | 131 | 9.95 | 0.076 | +10.91 | +0.71 | 11.70 | +0.421 | 0.75 | 3.53 | −2.1 |
| Franz Schubert — Der Müller und der Bach | 2048 | 194 | 14.02 | 0.072 | +1.01 | +0.40 | 12.74 | +0.374 | 1.04 | 2.33 | −11.1 |
| Fritz Kreisler — Liebesfreud | 5634 | 91 | 8.13 | 0.089 | +6.49 | +0.67 | 15.42 | +0.525 | 1.55 | 3.56 | −4.8 |
| George Frideric Handel — Chaconne in G | 3220 | 111 | 11.34 | 0.102 | +6.07 | +0.82 | 11.04 | +0.676 | 0.78 | 0.86 | −4.6 |
| Georges Bizet — Chanson Bohème (Carmen) | 5542 | 100 | 6.92 | 0.069 | +9.99 | +0.43 | 15.54 | +0.388 | 0.97 | 3.66 | −2.9 |
| Isaac Albéniz — Asturias | 2725 | 106 | 6.26 | 0.059 | +8.67 | +0.60 | 9.82 | +0.486 | 0.58 | 3.66 | −16.3 |

Scarlatti K 54 is the corpus outlier on every absolute timing statistic simply
because its tatum is 319 ms; on the scale-free `res/tatum` it is unremarkable
(0.083), which is the argument for reporting both.

## What is *not* claimed here

* Per-file `n_res` ranges from 158 to 1590, so the per-file kurtosis and lag-1
  numbers on the low-coverage files (Scriabin, Debussy, Schubert) carry real
  sampling error; the corpus IQR is wide for that reason and is used as the
  tolerance rather than the median.
* `examples/pulse.fil` (39 notes) and `examples/nocturne.fil` (25 notes) are too
  short for this estimator: no isochronous run of ≥ 8 onsets survives the IOI
  test, so their residual statistics are **undefined**, not zero. Candidate
  timing statistics are measured on a rendered 96-bar probe instead; the gate,
  velocity and chord statistics of the two examples are reported in
  `research/p5_round2/candidate.json`.
* `refs/midi/stats.json` and `tools/perf_stats.py` are left untouched (they are
  not mine to edit). The tests in `tests/test_feel.py` carry the numbers of this
  document as constants and assert that the old `timing_dev_ms` target is
  outside the re-derived range, so the discrepancy stays visible rather than
  quietly resolved.
