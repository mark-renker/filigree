# The Bar — what Filigree must beat, and how a critic decides

Gauntlet Loop rules in force (from the method: named + fetchable + comparable bar, blind
comparison, forced pick, ratchet, evidence gate).

## Global rules for critics

1. **Fresh context.** You did not build this. You may not read the builder's reasoning, its
   commit messages, or its self-assessment. Judge artifacts only.
2. **Forced pick, not a score.** For each criterion, name a winner: `CANDIDATE` or `REFERENCE`.
   No ties, no "both are good", no 1–10 scores.
3. **Blind where possible.** When comparing text/notation, the two samples are presented as
   `A` and `B` in randomised order without naming the system.
4. **Specific verdicts only.** A verdict must cite the exact token, line, number, or pixel
   region that decided it. Non-specific verdicts are discarded.
5. **Evidence gate.** If the evidence is broken (a screenshot failed to paint, a test crashed
   for an unrelated reason, a MIDI file wouldn't parse), the round is **invalid**: report that,
   do not declare a loss, and the previous best stands.
6. **Ratchet.** The previous best artifact is kept unless a challenger wins head-to-head.

## P1 — Language surface / ergonomics

**Bar:** the actual documented syntax of **Ziffers**, **Strudel (tonal + MIDI)**, **Alda**, and
**TidalCycles MIDI**, as recorded in `refs/syntax/tasks.md` (verified snippets with doc URLs)
and `research/landscape.md`.

**Comparison protocol:** for each of the 6 canonical tasks in `refs/syntax/tasks.md`, put the
Filigree solution next to the best rival solution, unlabelled, and pick a winner on:
- (a) **Tokens to express it** — count non-whitespace characters. Filigree must not be more
  than 1.3× the shortest rival.
- (b) **Readability at a glance** — can a reader who knows neither system predict what it
  sounds like? Pick a winner.
- (c) **Does it actually express the task at all?** A rival that cannot express per-note
  expression loses (a) and (b) automatically for those tasks — say so explicitly.
- (d) **Diffability** — change one note's vibrato depth. Count changed lines/characters.

**Fail conditions:** any canonical task Filigree cannot express; any ambiguity where two
readings of the same line are both defensible; error messages without line:col.

## P2 — Harmony engine

**Bar:** music-theory ground truth, not another program's output. Reference facts on disk in
`refs/specs/harmony_truth.md` (roman-numeral tables, modal-interchange spellings,
guide-tone definitions, standard jazz voicing conventions), plus **Hookpad's keystroke model**
(one digit per chord) and **Scaler 3's** feature surface for scope, both cited in
`research/landscape.md`.

**Comparison protocol:**
- Correctness: 40+ assertions of the form "symbol X in key Y must contain pitch classes Z".
  Any wrong pitch class is a loss, full stop.
- Voice leading: for a given progression, total absolute voice movement must be ≤ the movement
  of a naive close-position voicing, and no voice may cross another. Report the two numbers.
- Concision: chords per keystroke vs Hookpad's 1 digit/chord. Filigree must be ≤ 4 chars for a
  plain diatonic chord.

## P3 — Gesture / curve system

**Bar:** the two best existing continuous-expression text idioms, on disk in
`refs/syntax/curves.md`: **Csound f-tables / `transeg` breakpoints**
(https://csound.com/manual/scoregens/f/) and **Sonic Pi `_slide`**
(https://sonic-pi.net/tutorial.html), plus **MusicXML `<bend>`'s** 4-step model
(https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/bend/).

**Comparison protocol:** express these five gestures in Filigree and in each rival:
1. a 200 ms scoop up into the note from −1 semitone
2. vibrato that starts 35 % into the note and widens
3. a swell in pressure while timbre closes
4. a bend that lands exactly on the next chord's third
5. the same gesture reused on 12 notes with one parameter changed on note 7

Pick a winner per gesture on character count and on whether the rival can do it at all.
Additionally, plot the rendered curve (`refs/plots/`) and check by eye: no discontinuities at
anchors unless `snap`, no NaN leaking into written data, no data outside note lifetimes.

## P4 — MPE renderer

**Bar:** **RP-053 / MPE 1.1 spec conformance**, transcribed with clause references in
`research/mpe_technical.md`. This bar has a number as well as taste.

**Comparison protocol (all machine-checked, `tests/test_mpe.py` + `tools/audit_mpe.py`):**
- MCM present and correct on channel 1; `mm=15` lower zone; `mm=0` on channel 16.
- RPN 0 bend range present on **every** member channel used, MSB-first, closed with null RPN.
- Per note, event order is exactly `bend, CC74, pressure(0), note-on`; `pressure(0)` immediately
  precedes `note_off`; **zero** expression events on a channel between its note-off and the
  next note-on.
- No two simultaneous notes share a member channel.
- Event density: ≤ 250 expression events/second/channel, and thinning must remove ≥ 60 % of
  raw grid samples on `examples/*.fil` (report the ratio).
- Round-trip: re-read the file with `mido`, reconstruct each note's bend curve, and assert
  max deviation from `Score` curves ≤ 3 cents.
- The file must open in `mido` and in a second independent parser (`tools/smf_parse.py`,
  hand-written, no mido) with identical event streams.

**Round 2 amendment (appended; nothing above is deleted).** Two bullets above are
restated, because as written they are not satisfiable and not the right criterion:

1. *"thinning must remove ≥ 60 % of raw grid samples"* — this presumes an
   **interpolating** receiver. MIDI 1.0 pitch bend / channel pressure / CC are
   **hold-last-value**, so the criterion is now the **hold error**: after
   thinning, for every grid sample `t` in a note's lifetime,
   `|value_held(t) − value_true(t)| ≤ tol` (default **3 cents** for bend, 1 LSB
   ≈ 1/127 for pressure/CC), with the grid interval as the minimum spacing.
   Between grid samples the residual is bounded by the curve's own motion across
   one emission interval — the sampler's resolution floor, reported as
   `grid_floor_cents`. The thinning ratio is still **reported** (it stays high on
   flat/slow lanes, e.g. 96 % on a slow ramp and 92 % over the synthetic score,
   and legitimately falls to ~5–10 % where a fast ramp needs a point per grid
   step) but it is no longer a pass/fail floor: a fixed 60 % floor can only be
   met on a fast gesture by violating the hold bound. `examples/*.fil` does not
   exist yet, so the reported ratios come from `tools/audit_mpe.py --synth` and
   from the critic's 12 probe scores.
2. *"max deviation from `Score` curves ≤ 3 cents"* — measured under the **hold**
   model, the bound is `3 cents + grid_floor_cents`. The 3-cent number alone is
   only achievable where the pitch grid can resolve the curve; a 9 Hz ±1 st
   vibrato moves 5.65 cents per millisecond, so holding within 3 cents would need
   ~1900 events/s on that channel, 7.6× over this section's own
   250-events/s/channel ceiling. The two bullets are jointly unsatisfiable for
   arbitrarily fast gestures; the renderer honours the density ceiling first,
   widens the tolerance, and records a warning naming the channel and lane.

Also noted for the record: *"no two simultaneous notes share a member channel"*
cannot hold together with note preservation when a score has more simultaneous
notes than the 15 member channels RP-053 allows in one zone (the critic's own
`exhaustion` probe asserts all 20 note-ons survive and forbids notes on the
master channel — pigeonhole). Filigree keeps every note, gives each its full
preamble, and warns. See `NOTES_P4.md` "round 2".

## P5 — Feel / performance realism

**Bar:** real expressive performance MIDI on disk in `refs/midi/` (permissively licensed
human performances) and the statistics computed from them in `refs/midi/stats.json`.

**Comparison protocol:** compute the same statistics on Filigree output with a `feel` applied
(inter-onset deviation distribution, velocity σ within a phrase, note-length/gate ratio
distribution, chord-onset spread in ms). Filigree's numbers must fall inside the reference
interquartile range for at least 3 of 4 statistics. Report all numbers. Determinism check:
render twice, files must be byte-identical.

## P6 — Playground UI

**Bar:** `refs/ui/strudel_repl.png` (strudel.cc, the live-coding editor bar) and
`refs/ui/signal_pianoroll.png` (signal, an open-source web piano roll — the roll bar).

**Comparison protocol:** screenshot the candidate at 1440×900 and at 900×600, place it beside
the reference **unlabelled and in random order**, and pick a winner on: information density
without clutter; legibility of the code editor; whether the curves are actually readable inside
the notes; whether a stranger can tell what to do within 5 seconds. Cite pixel regions.
Reject rounds where the capture is visibly incomplete.

## P7 — The whole thing

**Bar:** a stranger with a Mac, a DAW, and 10 minutes. From `README.md` alone: install, render
`examples/`, hear it in their DAW.

**Comparison protocol:** a fresh-context critic follows the README literally in a clean shell,
records every command and its exit code, and reports the first step that fails or is ambiguous.
Any failure is a loss. Pick a winner against the **Alda install/first-score experience**
(https://alda.io/tutorial/) for time-to-first-sound.
