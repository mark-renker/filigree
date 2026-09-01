# P5 round 1 — feel / performance realism

**Critic:** fresh context, artifacts only. `NOTES_P5.md` was not read. `refs/midi/stats.json` and
`tools/perf_stats.py` were read *only* to check their method; every number below is recomputed by the
critic with independent code (`/tmp/p5/p5stats.py`, `gt3.py`, `cand.py`, `iso.py`, `det.py`, `adv.py`,
`edge.py`, `acf.py`, `metrical.py`).

**Reference:** 12 MAESTRO v3.0.0 performances in `refs/midi/`
(https://magenta.tensorflow.org/datasets/maestro), read with `mido`.
`tools/smf_parse.py` was verified against `mido` on
`refs/midi/Domenico_Scarlatti__Sonata_K_54.mid`: 7305 voice events, byte-identical
`(tick, bytes)` stream — parser trusted.

**Candidate:** `src/filigree/feel.py` presets `loose / tight / pushed / breath`, applied through
`resolve.py`, rendered with `PYTHONPATH=src python -m filigree.cli render` and re-parsed from the SMF.

---

## 0. Evidence gate: what the examples can and cannot support

`examples/pulse.fil` renders **39 notes / 14 beats**; `examples/nocturne.fil` renders **25 notes /
16 beats**. Neither contains a single isochronous run of ≥ 8 consecutive onsets, and neither yields
more than **4 chord clusters**. No timing-distribution statistic can be estimated from 25–39 notes:
the standard error on a spread estimate is ≈ 15 %, on a kurtosis estimate ≈ 100 %, and there is no
usable grid at all. **Timing rows measured on `pulse.fil`/`nocturne.fil` alone are therefore
NO VERDICT.**

To get statistical power I added two probes of my own, and I label every number by which one it came
from:

* **`probe_*.fil`** — 16 bars of straight 16ths, 4/4, 120 bpm, 256 notes, one stave, rendered
  through the real CLI (`/tmp/p5/fil/probe_*.fil`). Tatum 125 ms, i.e. inside the reference tatum
  range (74–304 ms), so it is a fair comparison ground.
* **isolation** — `feel.apply_feel()` called directly on a synthetic 4000-note list (`/tmp/p5/iso.py`).
  This gives the *exact* perturbation per note (rendered onset − nominal onset) with n = 4000 and no
  estimator noise, which is the only way to test distribution *shape* honestly.

## 1. Grid estimation — method, and where it is unreliable

**All 12 MAESTRO files carry a single `set_tempo` of 500 000 µs (120 bpm) and a default 4/4
`time_signature`.** These are capture defaults, not the music: the files contain no beat, bar or
downbeat information whatsoever. So a "metrical grid" has to be *estimated*, and three different
estimators gave three different answers:

| estimator | result | verdict on the estimator |
|---|---|---|
| per-6 s-window spacing+phase fit minimising squared distance (the method in `tools/perf_stats.py`) | median &#124;dev&#124; **30.5 ms**, IQR 11.7–78.5 ms (aggregate, as in `stats.json`) | **rejected.** In-sample fit, one fixed spacing per window, non-overlapping windows. It cannot track rubato, so tempo drift is charged to the notes. |
| global/local phase-lock resultant, then a phase-locked-loop tatum tracker (`p5stats.grid_track`) | median &#124;dev&#124; 10–80 ms depending on file | **rejected.** The local phase-lock resultant peaks at only R = 0.18–0.37 and for 5/12 files the peak sits on the floor of the search range, i.e. there is no identifiable global tatum in a rubato performance. Deviation scales with whichever τ you pick, so the absolute number is not identifiable. |
| **isochronous-run residuals (adopted)** | see table below | **accepted**, with the caveats named. |

**Adopted method (grid-free).** Cluster onsets within 50 ms (one chord = one onset). Find maximal
runs of ≥ 8 consecutive cluster onsets whose IOIs stay within 0.75–1.34× the running median IOI:
inside such a run the nominal grid is *isochronous by construction*, so no grid guessing is needed.
Fit time-vs-index with a degree-1 least-squares fit (this removes the run's mean tempo and any linear
tempo drift) and take the residual, in ms, as micro-timing. Index within the run gives an
unambiguous tatum index for periodicity tests.

**Where this is unreliable, stated up front:**

1. It measures only the fraction of each performance that is locally isochronous (`runfrac` column:
   0.08–0.76, median 0.34). Free/rubato passages are excluded, so this is micro-timing *within
   even figuration*, not over the whole piece.
2. Linear detrending inside a run removes real agogic *ramps*. The residual is therefore a
   **lower bound** on human timing deviation, and the positive lag-1 residual autocorrelation
   (§4) is partly curvature that the linear fit left behind.
3. **The absolute bar position of any onset is not recoverable.** With no downbeat annotation I can
   test *period-2 / period-4 structure* (label-invariant), but I cannot say "this is beat 1 and that
   is beat 4". The "beat 1 vs beat 4" framing of the grid-position criterion is therefore
   **NO VERDICT on the reference side**; see §5.
4. Sustain pedal (CC 64, 1961–5078 events per file) is ignored, so gate ratios are key-release
   ratios, not acoustic ones — applied identically to both sides.

## 2. Ground truth (12 MAESTRO performances, recomputed)

`|res|` = median absolute isochronous-run residual (ms). `res/tat` = that median divided by the run
tatum (dimensionless). `kurt` = excess kurtosis of the pooled residuals. `velSD`/`velIQR` = median
over phrases (phrase = onset gap ≤ 0.60 s, ≥ 4 notes) of within-phrase velocity sd / IQR.
`r1` = pooled lag-1 velocity Pearson r inside hand-streams (pitch split at 60) within phrases.
`gate` = note duration ÷ IOI to the next note in the same hand-stream, clipped at 4.0.

| performance | tatum ms | runfrac | n res | \|res\| ms | res/tat | kurt | velSD | velIQR | vel r1 | gate q1/med/q3 | chord ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Scriabin 3 Etudes Op 65 | 130 | 0.08 | 158 | 9.8 | 0.075 | +3.3 | 14.2 | 19.5 | +0.45 | 0.31/0.94/4.00 | 22.1 |
| Soler Sonata No 10 | 121 | 0.71 | 1388 | 6.8 | 0.057 | +1.1 | 12.0 | 15.0 | +0.34 | 0.49/0.84/1.62 | 13.0 |
| Debussy Feux d'artifice | 94 | 0.18 | 317 | 7.4 | 0.079 | +7.5 | 11.5 | 11.5 | +0.58 | 0.51/1.00/2.62 | 26.0 |
| Scarlatti K 54 | 304 | 0.34 | 280 | 26.4 | 0.087 | +1.7 | 9.6 | 13.2 | +0.30 | 0.56/1.06/1.67 | 17.6 |
| Mendelssohn Rondo Capriccioso | 92 | 0.34 | 759 | 8.5 | 0.093 | +5.2 | 15.0 | 16.4 | +0.63 | 0.38/1.13/4.00 | 16.9 |
| Chopin 12 Etudes Op 25 | 75 | 0.23 | 764 | 5.9 | 0.080 | +3.9 | 8.4 | 8.8 | +0.35 | 0.60/1.08/2.35 | 21.9 |
| Liszt La Campanella | 129 | 0.43 | 979 | 9.9 | 0.077 | +10.9 | 11.6 | 15.0 | +0.41 | 0.31/0.75/3.83 | 16.9 |
| Schubert Der Müller und der Bach | 194 | 0.17 | 216 | 14.0 | 0.072 | +1.0 | 11.7 | 19.0 | +0.37 | 0.66/1.04/2.98 | 20.8 |
| Kreisler Liebesfreud | 111 | 0.25 | 535 | 8.1 | 0.073 | +6.5 | 15.3 | 20.0 | +0.52 | 0.44/1.55/4.00 | 16.9 |
| Handel Chaconne in G | 111 | 0.76 | 1590 | 11.3 | 0.102 | +6.1 | 10.9 | 14.0 | +0.66 | 0.45/0.78/1.31 | 11.7 |
| Bizet/Moszkowski Chanson Bohème | 100 | 0.34 | 865 | 6.9 | 0.069 | +10.0 | 15.5 | 19.8 | +0.39 | 0.34/0.97/4.00 | 15.6 |
| Albéniz Asturias | 107 | 0.75 | 1321 | 6.3 | 0.059 | +8.7 | 9.2 | 13.5 | +0.45 | 0.34/0.58/4.00 | 7.8 |
| **median [IQR] over files** | 111 | 0.34 | | **8.3 [6.9, 10.3]** | **0.076 [0.072, 0.082]** | **+5.6 [+2.9, +7.8]** | **11.7 [10.6, 14.4]** | **15.0 [13.4, 19.1]** | **+0.43 [+0.37, +0.53]** | **0.45 / 0.99 / 3.41** | **16.9 [15.0, 21.1]** |

Two further reference facts, both used below:

* **Residual shape is heavy-tailed, not gaussian.** D'Agostino K² on pooled residuals is
  7.3–287 (median 105, p < 1e-3 for 11/12 files); excess kurtosis +1.0 … +10.9; skew −0.58 … +0.25.
* **Micro-timing scales with the tatum.** `res/tat` is 0.076 [0.072, 0.082] across performances whose
  tatum spans 75–304 ms (a 4× range). Human deviation is ≈ 7.6 % of the local subdivision, not a
  fixed number of milliseconds.
* **Chord onsets are ordered top-first.** Spearman r(pitch, onset) inside ≥3-note clusters is
  **−0.45** (median over files; negative in 10/12), and the top note precedes the mean of the rest by
  **−5.3 ms** (median). Melody lead is a real, measurable structure.

**Disagreement with `refs/midi/stats.json`.** Two of its four targets do not survive re-derivation.
(a) `timing_dev_ms` median 30.5 ms / IQR 11.7–78.5 ms is an artifact of the fixed-per-window grid fit
described above; my grid-free estimate is 8.3 ms [6.9, 10.3], i.e. **3.7× smaller**, and the published
IQR is so wide that almost any jitter setting "passes" it. (b) `gate_ratio` median 0.49 comes from a
voice-separator that *refuses to pair* a note with its successor when the first is still sounding
(`perf_stats.voice_streams`, `if last.start + last.dur > n.start + 0.060: continue`), which
systematically discards legato pairs; with a plain hand-stream definition the same files give median
**0.99**. `chord_spread_ms` (16.9 ms) reproduces exactly. `velocity_sd` (12.7 vs my 11.7) reproduces
within estimator noise. **The P5 bar as written is partly a mis-measured bar; I judge against my own
numbers and say so.**

## 3. Candidate measurements

Rendered through the CLI, re-parsed from the SMF, identical estimator code as §2.

| render | notes | n res | tatum ms | \|res\| ms | res/tat | kurt | velSD | velIQR | vel r1 | gate q1/med/q3 | chord ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| probe / loose | 256 | 35 | 121 | 11.1 | 0.092 | −0.76 | 14.5 | 18.0 | −0.02 | 0.88/1.07/1.36 | 42.7 |
| probe / tight | 256 | 82 | 125 | 8.1 | 0.065 | −0.24 | 9.6 | 13.0 | −0.01 | 0.88/1.05/1.21 | — |
| probe / pushed | 256 | 218 | 125 | 11.5 | 0.092 | −1.12 | 11.9 | 15.0 | +0.02 | 0.96/1.04/1.13 | — |
| probe / breath | 256 | 82 | 128 | 8.8 | 0.069 | −0.84 | 11.8 | 16.0 | +0.09 | 0.96/1.16/1.40 | 40.9 |
| probe / no feel | 256 | 256 | 125 | 0.0 | 0.000 | — | 0.0 | 0.0 | n/a | 1.00/1.00/1.00 | — |
| pulse / loose | 39 | 0 | — | NO VERDICT | | | 14.8 | 21.5 | −0.24 | 0.92/1.20/4.00 | 17.3 |
| pulse / tight | 39 | 0 | — | NO VERDICT | | | 11.7 | 14.0 | −0.06 | 0.93/1.32/4.00 | 12.1 |
| pulse / pushed | 39 | 0 | — | NO VERDICT | | | 13.5 | 20.0 | −0.08 | 0.97/1.11/4.00 | 6.2 |
| pulse / breath | 39 | 0 | — | NO VERDICT | | | 12.3 | 17.5 | −0.07 | 0.97/1.37/4.00 | 34.6 |
| nocturne / loose | 25 | 0 | — | NO VERDICT | | | 8.1 | 15.5 | −0.26 | 0.98/3.01/4.00 | 30.7 |
| nocturne / tight | 25 | 0 | — | NO VERDICT | | | 7.2 | 9.5 | −0.16 | 1.01/1.50/4.00 | 8.1 |
| nocturne / pushed | 25 | 0 | — | NO VERDICT | | | 6.4 | 7.0 | −0.04 | 0.98/4.00/4.00 | 10.8 |
| nocturne / breath | 25 | 0 | — | NO VERDICT | | | 9.7 | 7.5 | +0.34 | 1.07/4.00/4.00 | 12.9 |

Exact perturbations, isolation, n = 4000 notes each (ms at 120 bpm):

| preset | mean | sd | \|dev\| med [IQR] | min…max | skew | kurt | D'Agostino K² (p) | Shapiro W (p) | KS D (p) | lag-1 r of dev | vel sd | vel IQR | vel lag-1 r | gate med [IQR] | gate lag-1 r |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| loose | +6.56 | 24.33 | 16.8 [7.6, 28.7] | −87.4…+90.3 | −0.017 | +0.058 | 0.82 (0.66) | 0.9996 (0.68) | 0.0096 (0.85) | +0.005 | 13.28 | 18 | −0.010 | 1.097 [0.985, 1.206] | +0.002 |
| tight | +5.46 | 21.07 | 15.0 [6.9, 25.3] | −66.7…+90.3 | −0.049 | +0.050 | 2.05 (0.36) | 0.9993 (0.17) | 0.0107 (0.74) | +0.006 | 10.25 | 14 | +0.000 | 1.030 [0.984, 1.077] | +0.003 |
| pushed | −7.47 | 16.20 | 15.5 [8.1, 23.0] | −31.0…+16.0 | +0.006 | **−1.699** | **17721 (0.0)** | 0.860 (8e−51) | 0.180 (1e−113) | **+0.457** | 11.86 | 16 | +0.013 | 1.039 [0.976, 1.101] | +0.005 |
| breath | +8.73 | 20.85 | 15.2 [7.0, 25.9] | −63.8…+89.0 | +0.027 | +0.080 | 1.59 (0.45) | 0.9997 (0.83) | 0.0086 (0.92) | −0.014 | 12.21 | 17 | −0.012 | 1.161 [1.075, 1.251] | −0.013 |

Chord onset structure, isolation, 300 four-note chords with distinct voices:

| preset | median spearman r(pitch, onset) | median top-note lead | chord spread ms [IQR] |
|---|---|---|---|
| loose | **+0.000** (mean +0.008, sd 0.577) | **−0.24 ms** | 8.8 [6.7, 10.6] |
| tight | ~0 (undefined for ties) | +0.06 ms | 6.1 [4.9, 7.5] |
| breath | ~0 (undefined for ties) | −0.11 ms | 11.1 [8.2, 13.4] |

(reference: r = −0.45, top-note lead −5.3 ms, chord spread 16.9 [15.0, 21.1] ms)

## 4. Forced picks

| statistic | candidate | reference | pick | why, with the number that decided it |
|---|---|---|---|---|
| **timing spread** | \|res\| 8.1–11.5 ms; res/tat 0.065–0.092 (probe, 4 presets) | 8.3 ms [6.9, 10.3]; res/tat 0.076 [0.072, 0.082] | **CANDIDATE** | Same estimator both sides. `tight` 8.1 and `breath` 8.8 sit inside the reference IQR; `loose` 11.1 and `pushed` 11.5 are 8–12 % above q3 = 10.3 — a miss so small it is inside my own estimator's uncertainty. Magnitude is right. |
| **timing shape** | gaussian to the limit of detection: skew −0.017, kurt +0.058, K² = 0.82 (p = 0.66), Shapiro W = 0.9996 (p = 0.68), KS D = 0.0096 (p = 0.85) at n = 4000 (`loose`). `pushed` is not a distribution at all: kurt −1.70, K² = 17721, two spikes at −24 and +8 ms. | kurt +5.6 [+2.9, +7.8], K² 7.3–287 (median 105), p < 1e−3 in 11/12 files | **REFERENCE** | It is not uniform and not quantised — but it is *too perfectly gaussian*. Real residuals are leptokurtic by +5.6 excess kurtosis; Filigree's are +0.06. Human timing has rare large deviations (a 3σ event every ~40 notes in MAESTRO); a pure Box-Muller normal has none of that structure. |
| **velocity spread** | sd 9.6–14.5, IQR 13–18 (probe); sd 6.4–14.8 on pulse/nocturne | sd 11.7 [10.6, 14.4], IQR 15.0 [13.4, 19.1] | **CANDIDATE** | 4/4 presets land inside or at the edge of the reference sd IQR (`tight` 9.6 vs q1 10.6 is the only miss, −9 %). The 8–15 % velocity fractions are correctly calibrated. |
| **velocity autocorrelation** | −0.010 at n = 4000 (95 % CI ±0.031), i.e. **statistically indistinguishable from white noise**; rendered probes −0.02…+0.09; velocity ACF flat at every lag 1–8 (−0.14…+0.17) | **+0.43 [+0.37, +0.53]** at lag 1; ACF stays +0.3…+0.85 out to lag 8, and 4/12 files show a strict *alternating* pattern (Soler odd lags −0.17/−0.22/−0.28 vs even lags +0.77/+0.75/+0.71; Handel +0.49/+0.74; Albéniz +0.69/+0.85) | **REFERENCE** | Decisive, and the largest single gap. Filigree adds independent per-note jitter; a real player's next velocity is predictable from the current one at r ≈ 0.43, with a period-2 accent comb on top. Filigree's velocity is white by construction (key = `(seed, stave, voice, start, pitch, "velocity")`, no neighbour term). |
| **gate ratio** | median 1.04–1.16, IQR **width 0.17–0.48** (probe); on nocturne the median hits the 4.0 clip (`pushed`, `breath`) | median 0.99, but q1 0.45 / q3 3.41 → IQR **width 2.93 [1.59, 3.63]** | **REFERENCE** | Medians agree (1.04–1.16 vs 0.99). The *distribution* does not: the reference spans staccato (q1 ≈ 0.45) to held-over (q3 ≈ 3.4), 6–17× wider than Filigree's. `feel` only jitters duration by ±7–16 % around whatever the notation said, so a Filigree score is uniformly legato and no `feel` setting can create articulation variety. The bar asks for the *distribution*. |
| **grid-position dependence** | **none, provably.** Isolation, n = 4000, position within the beat: Kruskal-Wallis H = 0.78–1.88, p = 0.60–0.85; span of class medians ≤ 1.6 ms. Velocity by position: span ≤ 1.0 velocity unit, p ≥ 0.30 (`breath` p = 0.04, span 1.0 — negligible). Within the bar (16 classes) `loose` H = 14.1, p = 0.51. The only exception is `pushed`, whose `on_beats = (2, 4)` gives a binary ±31 ms on/off (class medians +7.4…+9.1 vs −22.5…−24.0 ms, span 33 ms, H = 3004) — an on/off switch, not a graded metrical profile, and it is keyed to a hard-wired 4-beat bar (see defect D3). | period-2/period-4 velocity structure demonstrated above (alternating ACF, and a within-run permutation test gives a velocity class-median spread 1.37× chance for the reference vs 1.11× for the candidate); melody lead r = −0.45 and −5.3 ms top-note lead in 12/12 files | **REFERENCE** | Filigree's perturbation is a function of `(stave, voice, start, pitch)` only; nothing in `apply_feel` reads the note's metrical position except the coarse `on_beats` gate. Measured: zero dependence at p ≥ 0.60. Real players show period-2 accent structure and systematic melody lead. **Caveat:** the *absolute* "beat 1 vs beat 4" version of this test is **NO VERDICT on the reference side** — MAESTRO ships no downbeat annotation, so only label-invariant periodicity is testable (§1.3). The pick rests on the periodicity and melody-lead evidence, not on labelled bar positions. |
| chord onset spread *(extra, not one of the six)* | 8.8 [6.7, 10.6] ms for a 4-note chord (`loose`), always **late-only** relative to the shared beat shift (the term is `abs(onset_ms) * hash01(...)`, a one-sided uniform) | 16.9 [15.0, 21.1] ms | **REFERENCE** | Below the reference q1 = 15.0 ms for a 4-voice chord, and one-sided: the spread can only delay a note, never anticipate it. |

**Score: CANDIDATE 2 / REFERENCE 4** (+1 extra to REFERENCE). Under the BAR's own "≥ 3 of 4
statistics inside the reference IQR" phrasing the candidate passes on magnitudes (timing spread,
velocity spread, gate median, chord spread is the miss) — but that phrasing only tests *spread*, and
every *structural* statistic loses.

## 5. Determinism and independence

| check | result |
|---|---|
| Same seed, 3 separate interpreter invocations via CLI (`probe_loose`, `nocturne_loose`, `pulse_loose`) | **PASS** — byte-identical, md5 `a74e4abe…` ×3, `c7f378b7…` ×3, `e29d8356…` ×3 |
| No global/salted state | consistent with the above; `feel.py` uses splitmix64/FNV-1a on the key tuple, no `hash()`, no RNG object |
| Different seeds (`@seed` 11/12/13/101, `probe_loose`) | **PASS, genuinely different** — 4 distinct md5s; vs the seed-11 render: median \|Δonset\| 21.9–24.0 ms, RMS Δonset 33.1–35.7 ms, **96.9–99.6 %** of the 256 notes moved by > 1 ms; RMS Δvelocity 18.8–19.3, **96.5–98.4 %** of velocities changed |
| Effect size of a seed change | RMS Δonset 33.1 ms vs per-render timing σ 24.3 ms; ratio 1.36 ≈ √2 = 1.41, exactly what two *independent* draws of the same distribution give. Two seeds are statistically independent, not perturbations of each other. |
| Feel must not change which notes/pitches play | **PASS** — for `probe`/`pulse`/`nocturne` × 4 presets, the `(stave, voice, pitch)` multiset is identical to the no-feel render (256/256, 39/39, 25/25). Isolation: `pitches_preserved = True`, `count_preserved = True`, 0 order inversions, 0 negative starts for all 4 presets. `probe_absurd` also preserves the pitch multiset (256 notes, sorted pitches equal). |
| Side effect on piece length | feel changes `duration_beats` (nocturne 16.00 → 15.64…16.70; pulse 14.00 → 14.07…14.60). Expected from release/gate jitter, but note it is **not** bounded: see D2. |

## 6. Adversarial probes

| probe | result | verdict |
|---|---|---|
| **Single note** (1 note, `loose`/`pushed`/`breath`) | no crash. `loose` +1.37 ms, `pushed` +7.70 ms, `breath` **+0.00 ms** — `breath`'s negative gauss shift was clipped by `max(0.0, …)`. Durations 460–608 ms from a 500 ms note. | PASS (with the clip noted in D4) |
| **200 notes on one beat**, distinct voice names | no crash. 200 distinct onsets, spread 13.8 ms (`loose`) / 17.9 ms (`breath`), all inside `[shared shift, shared shift + onset_ms]`, 0 negative starts, pitches intact. | PASS |
| **200 notes on one beat, identical key** (same stave, same `start`, same pitch, no voice name) | **all 200 collapse to one onset — spread 0.000 ms, 1 unique start.** The key tuple has no note identity, so genuinely doubled notes are perturbed identically. | DEFECT D5 |
| **0 % everything** (`timing 0ms, velocity 0%, gate 0%, onset 0ms, release 0ms`) | **exactly quantised.** Isolation: every `start`, `dur`, `velocity` bit-identical to input. End-to-end: `probe_zero.mid` md5 `3a2a223f…` == `probe_none.mid` md5 `3a2a223f…`. | PASS |
| **Absurd (2000 ms timing, onset 2000 ms, release 2000 ms, "400 %" velocity, "900 %" gate)** on 256 16ths | no crash, no NaN, **no negative start** (all clipped at 0), pitches preserved. But: **124 of 255 adjacent pairs are reordered (48.6 %)**; **3 notes stack exactly on t = 0** (information destroyed, no warning); **12 notes start past the nominal 64-beat end**, max start 72.0 beats, max end 77.1 beats; the rendered file runs 37.3 s against a nominal 32.0 s. Velocity moved only 80…99 — because "400 %" was silently read as 4 % (D1). | DEFECT D2 + D1 |
| **Flat −2000 ms** | 17 notes stack on t = 0, silently. No warning emitted. | DEFECT D2 |
| **NaN timing** | no exception, no NaN in output — instead **every note collapses to start = 0.0**, because `max(0.0, nan)` returns `0.0` in Python. The whole score is destroyed silently. | DEFECT D6 |
| **Inf timing** | no exception; `max_start = inf` is written into the note. | DEFECT D6 |
| **Unknown `timing_dist`** (`"triangular"`) | silently falls back to gauss (σ 19.8 ms for `timing_ms = 20`), no warning. | DEFECT D7 |
| **Negative `gate` / negative `velocity`** | absolute value taken silently; `gate = −0.5` clamps 1 note to the 0.001-beat floor. | minor, folded into D7 |

## 7. Defects, severity-ordered

**D0 — (highest) velocity and timing are white noise; the model has no memory.**
Lag-1 velocity r = −0.010 ± 0.031 (n = 4000) against a reference +0.43 [0.37, 0.53]; timing
perturbation lag-1 r = +0.005 against a reference residual lag-1 of +0.41…+0.83. Every note's
perturbation is an independent draw keyed on its own identity
(`base_key = (key_seed, stave, voice, start, pitch)`), so by construction no note can know what the
previous note did. This is the tell that separates "jitter" from "performance", and it is
architectural, not a tuning error: no choice of `timing_ms` / `velocity` / `gate` can create it.

**D1 — the percent-vs-fraction heuristic has a 47× discontinuity at 1.0 and silently mangles user
input.** `_velocity_sigma`: `if abs(v) > 1.0: v = v / 100`. Measured velocity sd for
`velocity = 0.99` → **49.2**; for `velocity = 1.01` → **1.04**. A 2 % change in the input changes the
output by 47×. `velocity: 400%` (parsed as 4.0) yields sd 2.0, i.e. 4 %, not 400 %. `_gate_frac` has
the same cliff (gate 1.0 → 0.858, gate 1.01 → 0.010). No warning, no validation, no documented
range.

**D2 — no bound on where a perturbed note may land, and silent collapse at t = 0.** Onsets are only
clipped with `start = max(0.0, …)`: with large timing values 17 distinct notes end up on exactly
t = 0.0 (flat −2000 ms) and 48.6 % of adjacent pairs are reordered (absurd preset), while 12 notes
are pushed past the end of the piece (max end 77.1 beats vs a 64-beat score; rendered 37.3 s vs
32.0 s nominal). No warning is emitted in any case. A humaniser should either bound the shift by a
fraction of the local IOI or warn when it reorders/clips.

**D3 — `on_beats` assumes a hard-wired 4-beat bar and therefore mis-fires on any other meter.**
`_BEATS_PER_BAR = 4` and `_beat_in_bar(start) = floor(start) % 4 + 1`; `apply_feel` is never given the
meter (`apply_feel(notes, fspec, tempo, seed)`). `examples/pulse.fil` is **7/8** and its own feel says
`on: 1,4`: bar starts fall at beats 0, 3.5, 7.0, 10.5, 14.0, which `_beat_in_bar` labels
**1, 4, 4, 3, 3** — so "beat 1 of the bar" is only correct for bar 1. The `pushed` preset
(`on_beats = (2, 4)`) is wrong on the same file. Also sub-beat positions cannot be addressed at all
(`floor` throws away everything finer than a quarter).

**D4 — timing σ is absolute milliseconds and does not scale with tempo or subdivision,** while the
reference does: `res/tat` = 0.076 [0.072, 0.082] over performances spanning a 4× tatum range. Measured
Filigree σ is 24.41 ms at 58, 120, 132 and 200 bpm alike, i.e. 9.4 % of a 16th at 58 bpm but
**32.5 %** at 200 bpm. At fast tempi the presets will smear across the subdivision; the good timing
score in §4 is partly luck of the 120 bpm test tempo.

**D5 — the perturbation key has no note identity, so genuinely doubled notes are perturbed
identically.** 200 notes sharing `(stave, voice=None, start, pitch)` all receive the same shift:
spread 0.000 ms, 1 unique onset. Two staves' worth of unisons, or any voice-less doubling, will not
decorrelate.

**D6 — no input validation: NaN silently zeroes the whole score, Inf propagates.**
`timing_ms = nan` → *every* note's start becomes 0.0 (because `max(0.0, nan) == 0.0`), no exception,
no warning, no NaN visible in the output to signal that anything went wrong. `timing_ms = inf` →
`start = inf` written into the note.

**D7 — silent fallbacks.** An unrecognised `timing_dist` ("triangular") is treated as gauss with no
warning; negative `gate`/`velocity` are silently `abs()`-ed. Compare `resolve._feel_spec`, which
*does* warn on an unknown feel *name* — the same courtesy is not extended to field values.

**D8 — chord spread is one-sided and pitch-blind.** `shift_ms += abs(onset_ms) * hash01(...)` can only
*delay*. Consequences: a 4-note chord spreads 8.8 [6.7, 10.6] ms against a reference 16.9 [15.0, 21.1];
r(pitch, onset) = 0.000 (mean +0.008, sd 0.577 over 300 chords) and top-note lead −0.24 ms against a
reference r = −0.45 and −5.3 ms; and the `onset_ms` term adds a systematic positive bias to the whole
piece (mean onset shift +6.6 ms `loose`, +8.7 ms `breath`), which is why `probe_tight` starts 49 ms
late.

**D9 — the presets cannot produce articulation variety.** Gate IQR width 0.17–0.48 against a reference
2.93 [1.59, 3.63]. `feel` multiplies the notated duration by `1 + gate·N(0,1)`; it cannot make a note
staccato. Conversely `release_ms` is absolute, so at `@tempo 58` (`nocturne`) `breath`'s 20 ms release
plus a legato notation pushes the median gate to the 4.0 clip.

**D10 — `pushed` is mislabelled as a distribution.** `timing_dist: "flat"` is a *constant* shift, so
`pushed` produces a two-spike histogram (class medians +7.4…+9.1 and −22.5…−24.0 ms, kurt −1.70,
K² = 17721, lag-1 r = +0.457 purely from the on/off pattern). It is a groove template, not
humanisation, and it is the one preset whose timing distribution is unambiguously non-human.

## 8. The single largest gap

**Filigree's `feel` has no memory and no metrical awareness: every note is perturbed independently of
every other note.** The one number that says it: **lag-1 velocity autocorrelation −0.010 ± 0.031
(n = 4000) against +0.43 [+0.37, +0.53] in 12 human performances** — with the same white-noise
signature in timing (+0.005 vs +0.41…+0.83), zero dependence on position in the beat
(Kruskal-Wallis p = 0.60–0.85, class-median span ≤ 1.6 ms) and zero melody lead
(r(pitch, onset) = 0.000 vs −0.45). The magnitudes are well tuned — timing spread 8.1–11.5 ms and
velocity sd 9.6–14.5 both land in the reference IQR — so this is not a calibration problem. It is
that `apply_feel` is a per-note function of `(seed, stave, voice, start, pitch, field)` with no term
for the previous note and no term for metrical position, and therefore produces *noise with the right
variance* rather than *performance*. Everything a listener recognises as human — accent patterns,
agogic phrasing, chord voicing order, articulation contrast — is in the correlations, and all of them
are zero.

---

### Artifacts

Scratch (not part of the repo): `/tmp/p5/p5stats.py` (statistics library), `gt3.py` + `gt_runs.json` +
`gt_agg.json` (ground truth), `mkfil.py` + `fil/` + `mid/` (renders), `cand.py` + `cand.json`,
`iso.py` + `iso.json` (exact perturbations), `det.py` + `det.json` (determinism/independence),
`adv.py` + `adv.json` (adversarial), `edge.py` + `edge.json` (parameter edges), `acf.py` + `acf.json`
(autocorrelation), `metrical.py` + `metrical.json` (permutation test), `tau_probe.py`,
`gt.py`/`gt2.py` (the two rejected grid estimators, kept for the record).
