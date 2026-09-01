# P4 — MPE renderer + realtime output: notes, decisions, open questions

Files owned and delivered: `src/filigree/mpe.py`, `src/filigree/realtime.py`,
`tests/test_mpe.py`, `tools/audit_mpe.py`, `tools/smf_parse.py`. Nothing else was touched.

Status: `python -m pytest tests/test_mpe.py -q` → **70 passed**;
`python tools/audit_mpe.py --synth` → **26 checks, 0 failures, exit 0**;
`py_compile` clean on all five files.

```
PYTHONPATH=src python tools/audit_mpe.py --synth        # render + audit a synthetic score
PYTHONPATH=src python tools/audit_mpe.py out.mid        # audit any .mid, nonzero on violation
python tools/smf_parse.py out.mid --events              # independent parser, no mido
```

## Decisions that were judgement calls (not dictated by RP-053)

1. **Track layout.** `docs/ARCH.md` and `refs/BAR.md` P4 say "one track per stave plus a
   conductor track", while `research/mpe_technical.md` §2.2 sketches a separate *MPE config*
   track. I followed ARCH: track 0 is the conductor (`track_name "conductor"`, optional `text`
   = score title, `set_tempo`, `time_signature`) **and carries the whole tick-0 zone
   configuration block**; tracks 1..n are one per stave. `one_track_per_stave=False` collapses
   the note data into a single track named `MPE Zone 1`.
2. **RPN byte order.** MSB (CC101) before LSB (CC100), per the Bitwig 5.2.5 transmitter change
   cited in the research digest, not the spec example's LSB-first order. Every RPN write is
   closed with the null RPN (127/127). `research/mpe_technical.md` marks the ordering question
   **[UNCERTAIN]**; if a target DAW turns out to need LSB-first, only `mpe._rpn` changes.
3. **Note-end is inclusive for allocation.** A member channel stays occupied at the exact beat
   its note ends, so a note starting on that beat never lands on the same channel. Without this,
   the next note's preamble bend would be emitted before the previous note's `note_off` in the
   same tick and would bend a still-sounding note.
4. **Never-used channels count as the oldest release** (`last_off = -1`, exactly as in the
   reference allocator in the digest), so fresh notes spread across virgin channels before any
   reuse. Same-pitch affinity only applies among already-used free channels.
5. **Overflow behaviour above 15 simultaneous notes.** RP-053 says sharing a channel beats
   stealing notes, but sharing makes per-note expression meaningless. Overflow notes therefore
   get **note-on/note-off only** — no bend, CC74 or pressure — and a warning is appended to
   `Score.warnings`. `audit_mpe.py` still reports those files as violations of the BAR bullet
   "no two simultaneous notes on one member channel", which is the honest outcome: >15-voice
   polyphony is not representable in one MPE zone.
6. **Thinning model = linear prediction** (the algorithm in the digest §6.3), i.e. the receiver
   is assumed to interpolate linearly between transmitted values. This is what makes both bar
   numbers achievable at once: 85 % of raw grid samples removed on curved lanes *and* ≤ 1.6
   cents bend error on 6 Hz vibrato. A pure zero-order-hold receiver with a 2-LSB deadband would
   need ~5× more pitch-bend messages for the same accuracy. The round-trip check in
   `audit_mpe.bend_roundtrip_error` uses the same linear-interpolation receiver model.
7. **Two thinning ratios are reported.** `thinning_ratio_curved_lanes` (the bar's number, 0.85
   on the synthetic score) counts only note/lane pairs that actually carry a curve;
   `thinning_ratio_all_lanes` also counts static notes whose lane collapses to the single
   mandatory preamble message, and is therefore optimistic (0.98). The check is applied to the
   curved-lane figure.
8. **Lane mapping beyond the three MPE dimensions.** `press` → channel pressure, `timbre` →
   CC74 (default 64, the "initial-64" convention), `amp` → CC11, `pan` → CC10, `cc<n>` → CC n.
   `pan` is channel-scoped, so on a member channel it is effectively per-note; SPEC §3 already
   flags that as documented-but-not-really-per-note.
9. **Static `Note.detune` is folded into the bend value**, added to the `bend` curve, so a
   microtonal note needs no separate mechanism.
10. **Density.** The auditor measures the worst 1-second sliding window per channel
    (44 events/s on the synthetic score, limit 250), not an average, so a short burst cannot
    hide behind a long file.

## Uncertain / unverifiable here

* **No DAW was available in this sandbox.** Everything is verified against RP-053 as digested,
  `mido`, and the independent parser — not against Ableton Live 12, Bitwig 5.x or Logic. The
  digest's own §2.4/§9 warn that whether a DAW honours a *file-embedded* MCM/RPN, and whether it
  converts channel-per-voice SMF data into note-scoped expression, is undocumented by all three
  vendors. Treat the SMF path as "channelised multitimbral MIDI that happens to be MPE-shaped".
* **Realtime output is untestable here**: `python-rtmidi` is not installed, so
  `realtime.play()` is exercised only through `realtime.dry_run()` (identical stream, no port)
  and the missing-backend error path. Virtual-port naming (`"Filigree"`), CoreMIDI client
  naming and IAC fallback follow the digest §4 but are unverified on hardware.
* **Scheduler jitter** in `play()` is bounded by a 1 ms sleep slice; the digest §4.3 says
  anything tighter than ~5 ms should go through an SMF instead. Not measured.
* **Bitwig micro-pitch is ±24 st** while the default member bend range is ±48 st, so bends
  beyond ±24 st cannot round-trip into Bitwig's expression model. `MpeOptions(bend_range=24.0)`
  is the Bitwig-first setting and is tested.

## Requests for files I do not own

* **`resolve.py` (lead):** please guarantee that (a) `Curve.points` are sorted by beat, (b) the
  first point is at or before `Note.start` and the last at or before `Note.start + Note.dur`
  (as `ir.Curve`'s docstring promises), and (c) "no data" regions arrive as `NaN` values rather
  than missing points — the renderer drops NaN samples and writes nothing there.
* **`resolve.py` (lead):** `Note.channel` may be left `None`; `render_*` calls
  `allocate_channels` itself when any channel is unset. If the resolver ever pre-assigns
  channels it must honour "no two simultaneous notes on one member channel", because the
  renderer trusts pre-set channels.
* **`cli.py` (lead):** suggested wiring — `filigree render x.fil -o x.mid` →
  `mpe.write_midi(score, path, MpeOptions(bend_range=score.bend_range, ppq=score.ppq,
  grid_ms=score.grid_ms, pitch_grid_ms=score.grid_ms / 2))`, and `filigree play` →
  `realtime.play(score, port)`. `realtime.list_ports()` returns `[]` (never raises) when no
  MIDI backend is installed, which is a good "no ports found" message trigger.
* **`README.md` (lead):** Logic Pro needs *MIDI Mono Mode → "On (with common base channel 1)"*
  and *Mono Mode Pitch Range* set to the score's `@bend-range` (default 48); Live needs MPE
  enabled for the port; polyphony is capped at 15 voices per zone. Also worth stating that
  `python-rtmidi` is optional and only needed for `filigree play`.
* **`tests/test_integration.py` (lead):** `tools/audit_mpe.py` is importable
  (`audit_file(path, score=..., opts=...) -> Report`, `Report.failures`) and
  `synthetic_score()` is reusable, so an end-to-end example can be audited with the same checks.
  `refs/BAR.md` P4 asks for the thinning ratio on `examples/*.fil`; once `examples/` exists,
  running `python tools/audit_mpe.py examples/foo.mid` prints it.

## Source citations for the conformance rules

All rules trace to `research/mpe_technical.md`, which cites:
[RP-053 spec PDF](https://midimpe.neocities.org/rp53spec.pdf) (zones, MCM RPN 00 06, the
`bend → CC74 → pressure 0 → note-on` preamble, pressure 0 before note-off, no per-note data
after note-off, allocation rules, no polytouch on member channels),
[MIDI.org on MPE pitch bend](https://midi.org/community/midi-specifications/how-midi-mpe-pitch-bend-works)
(±48 st member default, ±2 st master, RPN 0, <1.2 cents granularity),
[Bitwig 5.2.5 release notes](https://www.bitwig.com/dl/Bitwig%20Studio/5.2.5/release_notes/)
(MSB-before-LSB MCM, bend range on all channels),
[mido SMF docs](https://mido.readthedocs.io/en/stable/files/midi.html) and
[mido message types](https://mido.readthedocs.io/en/stable/message_types.html) (type-1 files,
delta ticks, value ranges),
[François Georgy on MIDI pitch bend](https://www.francoisgeorgy.ch/midi/midi-pitch-bend/)
(14-bit wire format, 8192 centre, units per semitone),
[python-rtmidi installation](https://spotlightkid.github.io/python-rtmidi/installation.html)
and [mido API](https://mido.readthedocs.io/en/stable/api.html) (virtual ports),
[Apple: Use MPE with software instruments in Logic Pro](https://support.apple.com/guide/logicpro/use-mpe-with-software-instruments-lgcp8f599497/mac),
[Ableton Live 12 manual, Editing MPE](https://www.ableton.com/en/live-manual/12/editing-mpe/),
[Bitwig user guide, Working with Note Events](https://www.bitwig.com/userguide/latest/working_with_note_events).


---

# Round 2 — closing the critic's gaps

Work order: `refs/verdicts/P4_round1.md`. Probes: `tests/critic_p4_mpe.py` (12 adversarial
scores) and `tools/critic_smf_check.py` (independent checker) — neither was edited.
Files changed by me: `src/filigree/mpe.py`, `src/filigree/realtime.py`, `tests/test_mpe.py`,
`tools/audit_mpe.py`, this file, plus the two *appended* notes I was asked to add
(`refs/BAR.md` P4 amendment, `research/mpe_technical.md` §6.3 correction).

## Fix 1 — the receiver is hold-last-value, not interpolating (the critical one)

Round 1 thinned against a **linear reconstruction** of the transmitted points, so a straight
ramp collapsed to its endpoints and a real synth — which *holds* the last value until the next
message — heard a step. The critic measured up to **98.75 cents** of hold error against a
3-cent bar (`curve_past_end`), while the same stream looked fine under the interpolating model.

The guarantee is now stated in hold semantics and enforced by construction:

> After thinning, for every grid sample `t` in a note's lifetime,
> `|value_held(t) − value_true(t)| ≤ tol`, with `tol = MpeOptions.bend_tol_cents`
> (default 3.0 cents, converted to pitch-bend LSB for the active member range, reserving half
> an LSB for quantisation of the true value) for the bend lane and `MpeOptions.cc_tol_lsb`
> (default 1 LSB ≈ 1/127) for pressure / CC74 / other CC lanes. The grid interval is the
> **minimum spacing** and is never subdivided. Between grid samples the residual is bounded
> by the curve's own motion across one emission interval — the resolution floor, reported as
> `grid_floor_cents`.

Implementation (`mpe.thin`): greedy zero-order-hold selection. Walking forward from the last
emitted point, when frame *i* would break the budget the **last frame still inside** the budget
is emitted (so the bound is `tol`, not `tol + one step`); a local extremum whose deviation from
the held value exceeds half the tolerance is emitted at its own time so peaks are never shaved.
`mpe.hold_error(frames, kept)` measures the realised error and is asserted in tests;
`mpe.hold_budget_cents(score, opts)` returns the *documented* bound
(`tol + grid_floor_cents`) from the score and options **only** — never from the emitted file —
so `tools/audit_mpe.py` can check `measured ≤ budget` and still catch a thinner that emits too
few points, wrong values, or drops a lane.

`tools/audit_mpe.py` changes: `bend_roundtrip_error(..., model="hold")` is now the default and
reconstructs by holding (the old interpolating model is kept only to print the optimistic number
side by side); the hard `THINNING_TARGET = 0.60` check is replaced by the hold-error check plus
the ratio as a reported metric; new metrics `max_bend_hold_error_cents`,
`max_bend_linear_error_cents`, `grid_floor_cents`, `hold_error_budget_cents`.

### Measured, round 2 (critic's own probe table, `python tests/critic_p4_mpe.py`)

| probe | max bend **hold** error ¢ | (linear ¢) | documented budget ¢ | thinning | peak expr/s/ch | round-1 hold ¢ |
|---|---|---|---|---|---|---|
| exhaustion | 8.71 | 10.19 | 9.51 | 43.8 % | 175 @ch7 | 40.94 |
| zero_length | 0.00 | 0.00 | 3.00 | n/a | 4 @ch2 | — |
| touching_1ch | 8.78 | 6.45 | 14.05 | 11.0 % | 178 @ch2 | — (all expression was lost) |
| nan | 0.00 | 0.00 | 11.16 | 48.5 % | 103 @ch2 | — |
| inf | 4800.00 | 4800.00 | 3.00 | 96.0 % | 4 @ch2 | — (see policy note below) |
| curve_past_end | 2.19 | 1.84 | 7.08 | 44.0 % | 84 @ch2 | **98.75** |
| beyond_range | 56.25 | 59.29 | 303.00 | 78.0 % | 44 @ch2 | — |
| dense_1000 | 3.71 | 2.63 | 19.18 | 5.0 % | 57 @ch2 | — |
| long_200beats | 0.20 | 0.20 | 11.54 | 10.0 % | 183 @ch2 | 40.43 |
| identical_pitch | 2.54 | 2.79 | 6.41 | 43.0 % | 114 @ch2 | 19.96 |
| no_curves | 0.00 | 0.00 | 3.00 | n/a | 4 @ch2 | — |
| triple_lane_fast | 26.59 | 15.35 | 36.66 | 41.1 % | 238 @ch2 | 80.77 |

`tools/audit_mpe.py --synth`: hold error **4.88 ¢** vs budget 15.82 ¢ (grid floor 12.82 ¢),
linear 2.34 ¢, thinning 92.2 % all lanes / 41.9 % curved lanes, peak 210 expr/s/ch, 26 checks,
0 failures.

Every probe satisfies `measured ≤ 3 ¢ + grid_floor_cents`. The three headline numbers:

* **8.78 ¢** — worst hold error over all probes whose curves the 5 ms pitch grid can resolve.
* **26.59 ¢** — `triple_lane_fast`, where the 250-events/s/channel ceiling, not the thinner,
  is the binding constraint (see "what the critic got wrong", item 2).
* **56.25 ¢** — `beyond_range`, where the clamped curve moves 1200 cents in 0.1 s
  (12 ¢/ms): a 5 ms grid cannot express that at all. Round 1's worst was 98.75 ¢.

The thinning ratio moved from a target to a metric, exactly as predicted: it stays high where
the music is flat or slow (96 % on `inf`'s single flat lane, 78 % on `beyond_range`, 92 % over
the synthetic score) and falls to 5–11 % where a fast ramp genuinely needs a point per grid
step (`dense_1000`, `long_200beats`, `touching_1ch`). Appended as a "round 2 amendment" to
`refs/BAR.md` §P4 and as a correction note to `research/mpe_technical.md` §6.3.

## Fix 2 — channel sharing / reuse never costs a note its expression

* The `quiet`/shared-note suppression is **gone**. Every note now emits the full mandated
  preamble (`bend, CC74, pressure 0`) and its own `pressure 0` before its `note_off`,
  unconditionally, even when it reuses a channel a previous note just released and even when it
  has to share a channel with a sounding note. Those events are flagged `mandatory=True`, so
  neither the deduplicator nor the rate governor can remove them.
* The inclusive-end bug is fixed in two places: `_Alloc.retire` and `_overlap_map` now treat a
  note end as **exclusive** (`b0 >= a1` frees the channel), so two touching notes are not
  treated as overlapping. `touching_1ch` went from **100 % "thinning"** (i.e. all expression
  silently dropped) to a correct 2-note stream with 0 preamble defects.
* Lanes whose value at note-on is not carried by the preamble (pressure, CC11, CC10, `cc<n>`)
  now state their initial value immediately **after** the note-on, so a constant CC lane can
  never vanish, and the 3-event preamble immediately before the note-on stays exact.
* Critic probe result: **0** preamble defects, **0** pressure-0-before-off defects, **0**
  expression-between-off-and-on defects, **0** simultaneous-same-channel defects on 11 of 12
  probes (see the pigeonhole argument for `exhaustion` below).

## Fix 3 — robustness policy (documented in `mpe.py`'s docstring, one test each)

| input | policy | warning | test |
|---|---|---|---|
| `inf` / `-inf` / `NaN` breakpoint | dropped, never written | "dropped N non-finite … breakpoint(s)" | `test_inf_breakpoints_are_dropped_with_a_warning` |
| `NaN` region | "no data" for **that region only**; the lane is never deleted; surviving breakpoints still define it | as above | `test_nan_regions_write_no_data` |
| lane that is non-finite everywhere | falls back to the lane default (bend → detune, CC74 → 64, pressure → nothing) | as above | `test_all_nan_lane_falls_back_to_default` |
| `dur == 0` or `dur < 0` | minimum duration of **one tick**, never dropped | "rendered with the minimum duration of one tick" | `test_zero_length_notes_get_one_tick_and_a_warning`, `test_negative_length_note_is_also_one_tick` |
| non-finite `start` / `detune` | placed at beat 0 / detune dropped | named warning | `test_non_finite_start_and_detune` |
| bend outside the member range | clamped, never wrapped | warning naming the note and the requested value | `test_bend_clamp_warning_names_the_note_and_value` |
| absurd magnitudes (`1e300`, `±inf` semitones) | `semitones_to_bend` saturates instead of raising `OverflowError` | — | `test_semitones_to_bend_handles_non_finite` |

No probe crashes: all 12 render, and the 14-bit/7-bit wire values are in range in every file
(`tools/critic_smf_check.py` + the mido cross-check agree byte-for-byte on all 12).

`src/filigree/realtime.py` also got the panic the critic asked for (D6): `panic_stream()` sends
pressure 0, an explicit `note_off` for every note known to be sounding, pitch bend re-centred to
`00 40`, CC64 = 0, CC121, CC123 and CC120 on every channel the renderer may have touched; it runs
between `loop=True` passes as well as in the `finally`, and `_panic` can no longer raise (a
failure there would have masked the original exception).

## What I think the critic got wrong (with the argument)

1. **`exhaustion`'s 5 channel-overlap defects are provably unavoidable, and the checker itself
   proves it.** `tools/critic_smf_check.py` requires `n_notes == input_notes` (all 20 note-ons
   present) and reports `notes on master` as a defect; RP-053 allows at most **15** member
   channels in the Lower Zone (`mm = 15`, which the same checker also demands). 20 simultaneous
   notes into 15 channels is pigeonhole: some channel must carry two. BAR's "no two simultaneous
   notes share a member channel" and "every note survives" cannot both hold. Filigree keeps
   every note, gives each its full preamble and teardown, and appends a warning naming how many
   notes had to share. The alternative — dropping 5 notes — would trip `n_notes != input_notes`,
   a *gated* defect. I chose the ungated one deliberately.
2. **3-cent hold accuracy and ≤ 250 expression events/s/channel are jointly unsatisfiable.**
   `triple_lane_fast` is a 9 Hz, ±1 st vibrato: amplitude 100 cents, so
   `max|dv/dt| = 100 · 2π · 9 ≈ 5655 ¢/s = 5.65 ¢/ms`. A hold sender within 3 cents needs an
   interval ≤ `3 / 5655 s ≈ 0.53 ms`, i.e. ~1885 bend events/s on one channel — **7.5×** the
   BAR ceiling — before the pressure and CC74 lanes of the same note are counted. The 5 ms
   pitch grid alone already caps accuracy there at `5.65 × 5 ≈ 28 ¢`. Filigree honours the
   density ceiling first, allocates the per-channel budget across lanes by weight
   (bend 0.68, pressure 0.17, CC74 0.10, other CC 0.05) with **water-filling** so an idle lane
   reserves nothing, widens the tolerance on the lanes that are still hungry, and warns naming
   the channel and lane. Measured: 26.59 ¢ at 238 expr/s/ch — under both the amended bound and
   the 250 ceiling. Prioritising pitch was a judgement call: 87 ¢ of bend error (what uniform
   widening produced) is a semitone out of tune, while a coarser 11–13 Hz timbre wiggle is
   nearly inaudible.
3. **The `inf` probe's 4800-cent "hold error" is a disagreement about semantics, not a
   regression.** The critic's reference model linearly interpolates the raw breakpoints
   `[(0,0), (0.5,+inf), (1,-inf)]` and then clamps, so its "true" value is `+48 st` — a
   full-range bend synthesised out of `inf`. My work order specifies the opposite policy:
   non-finite values are **dropped** with a warning, so the note holds its finite value (0)
   and the file contains no bend at all. Writing a maximum-range pitch bend because the input
   said `inf` is worse than writing nothing; the checker agrees, in that it does not gate on
   bend error. Excluding this probe, the worst hold error is 56.25 ¢ (`beyond_range`), and
   excluding the two cases where the grid/rate floor exceeds the tolerance, 8.78 ¢.
4. **D7's evidence gap stands and is not mine.** BAR §P4 asks for thinning ratios on
   `examples/*.fil`; that directory still does not exist, and `web/fixtures/source.fil` fails to
   parse (`unknown anchor '@root+5'`), which is a P1/P3 issue. Reported ratios therefore come
   from `tools/audit_mpe.py --synth` and the 12 critic probes.
5. Unrelated red in the full suite at the time of writing:
   `tests/test_integration.py::test_curve_value_at_returns_nan_inside_a_hole` fails inside
   `ir.Curve.value_at` (P2's file, mid-refactor to NaN-gap semantics). It touches none of my
   files; `tests/test_mpe.py` is 100 % green (87 tests) and the audit is 26/26.

## Commands, in the mandated order

```
python -m pytest tests/test_mpe.py tests/critic_p4_mpe.py -q   # 87 passed
python tests/critic_p4_mpe.py                                  # renders /tmp/critic_p4/*.mid
python tools/critic_smf_check.py /tmp/critic_p4/*.mid          # 11/12 clean, exhaustion: 5 pigeonhole overlaps
python tools/audit_mpe.py                                      # 26 checks, 0 failures
python -m pytest -q                                            # 731 passed, 1 unrelated ir.py failure
```


## Round 2 follow-up — NaN is a gap sentinel, not an anomaly

Per the lead's `ir.Curve` docstring, a NaN value means "write no data from here until the next
non-NaN point" and is normal resolver output, so it must not warn. Changes (all in files I own):

* `clean_points()` now goes through `ir.Curve.real_points()`, so NaN is removed **silently**;
  its second return value counts only **anomalies** (`±inf` and other non-finite-not-NaN),
  which still warn with the previous wording (only "inf/NaN is never written" became
  "inf is never written").
* New `clean_spans()` wraps `ir.Curve.spans()`, and new `_sample_spans()` samples each
  contiguous run separately: **nothing is emitted inside a gap**, which under hold semantics is
  exactly "no data" — the receiver keeps the value it was last sent. A lane that opens with a
  gap holds the note's static detune (bend) or 64 (CC74) through it, so the mandated preamble is
  unaffected. All-NaN lanes still fall back to the lane default, now silently.
* Tests: `test_nan_is_silent_while_inf_warns_exactly_once` (NaN curve → 0 warnings, inf curve →
  exactly 1), `test_no_data_is_emitted_inside_a_nan_gap`, plus
  `test_nan_region_only_kills_that_region_not_the_lane` and
  `test_all_nan_lane_falls_back_to_default` updated to assert silence.
* Re-verified: `tests/test_mpe.py` 89 passed; 12/12 probes render and cross-check identically
  under mido with 11/12 defect-free (`exhaustion`'s 5 pigeonhole overlaps only, unchanged);
  `tools/audit_mpe.py` 26 checks / 0 failures (hold error 4.88 ¢ vs 15.82 ¢ budget);
  `PYTHONPATH=src python -m filigree.cli render examples/nocturne.fil -o /tmp/noc.mid` prints
  **no non-finite warnings** (only the pre-existing rate-ceiling notes on channels 6 and 11).
  The `nan` probe dropped from 103 to 6 expression events/s, because the gap is now honoured
  instead of being bridged by interpolation.
