# P4 — MPE renderer — critic verdict, round 1

Critic context: fresh, did not build this, did not read `NOTES_P4.md`, `tests/test_mpe.py`,
`tools/audit_mpe.py` or `tools/smf_parse.py` before writing my own verifier.

Artifacts judged: `src/filigree/mpe.py` (620 lines), `src/filigree/realtime.py` (132 lines),
plus cross-parser comparison against `tools/smf_parse.py` and `mido`.

My evidence (critic-owned, written from scratch):
* `tools/critic_smf_check.py` — byte-level SMF reader (MThd/MTrk, varlen, running status, meta,
  sysex) + MPE conformance checker + mido cross-check. No filigree imports.
* `tests/critic_p4_mpe.py` — 12 adversarial `ir.Score` fixtures, rendered with
  `mpe.write_midi`, all checked byte-level. Artifacts in `/tmp/critic_p4/*.mid`.

Verdict status: **VALID** for the renderer (every rendered file parsed cleanly under three
independent parsers). One evidence gap is recorded under D7 and it limits only the
"thinning on `examples/*.fil`" bullet, not the rest.

---

## 0. Independent verification of the spec digest (`research/mpe_technical.md`)

Five load-bearing claims, checked against primary sources, not against the digest:

| # | Digest claim | Primary source | Result |
|---|---|---|---|
| 1 | MCM = RPN `00 06`; Data Entry MSB = number of Member Channels, LSB unused; `mm=0` = zone off; Lower master ch1/members up from ch2, Upper master ch16/members down from ch15; one active zone may use 15 members; unused zone's master may be a member | [RP-053 spec PDF](https://midimpe.neocities.org/rp53spec.pdf) | **Confirmed verbatim**, incl. the `B0 79 00 / 64 06 / 65 00 / 06 07` example |
| 2 | On MCM receipt: master bend sensitivity ±2 st, every member ±48 st; changed with RPN 0; RPN 0 must be sent to **every member channel individually**; whole semitones 0–96; 14-bit granularity < 1.2 ¢ at ±96 | [MIDI.org, How MIDI MPE pitch bend works](https://midi.org/community/midi-specifications/how-midi-mpe-pitch-bend-works) | **Confirmed verbatim** |
| 3 | "Channel Pressure must be set to zero immediately before a Note On or a Note Off wherever appropriate to the design of the controller"; Poly Key Pressure must **not** be sent on member channels; CC74 initial-64 = `40h` | [RP-053](https://midimpe.neocities.org/rp53spec.pdf) | **Confirmed**, including the conditional clause the digest quotes honestly |
| 4 | Per-note control (bend, pressure, CC74) has no effect after Note Off even under pedal/long release; master bend keeps affecting releasing notes; member state is tracked while idle to seed the next note | [RP-053](https://midimpe.neocities.org/rp53spec.pdf) | **Confirmed** |
| 5 | Bitwig 5.2.5 "now sends MCM messages with the MSB before the LSB" and "the pitch bend range for all channels"; 5.2.4 "Fixed note expression handling after note off"; Bitwig micro-pitch is ±24 st; Live "uses MIDI channel 1 as a global channel and will therefore never send notes on that channel in MPE mode" | [Bitwig 5.2.5 release notes](https://www.bitwig.com/dl/Bitwig%20Studio/5.2.5/release_notes/), [Bitwig user guide — Working with Note Events](https://www.bitwig.com/userguide/latest/working_with_note_events), [Ableton MPE Zone Configuration](https://help.ableton.com/hc/en-us/articles/4409113250322-MPE-Zone-Configuration) | **Confirmed verbatim** (micro-pitch stated as −24.00…24.00 semitones) |

The digest's transcription of RP-053 is accurate, and its MSB-first recommendation is
correctly flagged `[UNCERTAIN]` (the spec's own examples are LSB-first: `[Bn 64 06][Bn 65 00]`).

**One digest claim is unsupported, and the renderer is built on it.** §6.3's event-economy
policy — "drop a frame when the receiver's **linear interpolation** of the previous two emitted
points already lands within tolerance (2 LSB ≈ 1.2 cents)" — carries no primary citation, and
nothing in RP-053 or the MIDI.org pitch-bend page says a receiver interpolates between pitch-bend
messages. MIDI 1.0 pitch bend is a **hold-last-value** control. The only cited numbers nearby
([Wikipedia: MIDI](https://en.wikipedia.org/wiki/MIDI)) are about wire bandwidth, not
interpolation. `mpe.thin()` (`mpe.py:108-137`) implements the unsourced assumption literally,
and every round-trip number below splits in two because of it. See D1 and "largest gap".

---

## 1. Forced picks

### Spec conformance — **REFERENCE**

What the candidate gets right, byte-level (`/tmp/critic_p4/*.mid`, all 12 fixtures):
* MCM on ch1 exactly `B0 65 00 B0 64 06 B0 06 0F` (CC101=0 MSB first, CC100=6, Data MSB=15),
  preceded by `B0 79 00`; upper zone switched off with `BF … 06 00`. `mm` tracks
  `len(members)` (`touching_1ch` with one member emits `B0 65 00 B0 64 06 B0 06 01`).
* RPN 0 present on **15/15** used member channels, MSB-first, value `B1 06 30` = 48 st,
  null-closed `65 7F / 64 7F`; master gets 2 st. `rpn0_missing = []` on every file.
* Zero expression events between a note-off and the next note-on on the same channel across all
  11 rendered files (`expr-after-off = 0`), and no polyphonic key pressure anywhere.
* SMF type 1, 960 PPQN, real `8n` note-offs with release velocity 64.

Why it still loses the pick — BAR P4's preamble bullet is unconditional ("Per note, event order
is exactly `bend, CC74, pressure(0), note-on`; `pressure(0)` immediately precedes `note_off`"),
and the candidate abandons it whenever channels are shared:
* `exhaustion.mid` (20 notes at tick 0, 15 members): **10 notes have no preamble at all** and
  **10 note-offs are not preceded by pressure 0**. Byte-level: ch2 tick0 `91 3F 5A` (note 63)
  arrives with the three preceding events being config CCs, not `E1/B1 4A/D1 00`; at tick 3840
  `81 30 40` is preceded by `91 3F 5A`, not `D1 00`. Cause: `mpe.py:443` `quiet = id(n) in shared`
  then `mpe.py:471,498,506` skip bend/CC74/pressure and the pressure-0 teardown entirely.
* `touching_1ch.mid`: two notes that merely **touch** (0–1, 1–2 beats) on a 1-member zone are
  classified as overlapping by `_overlap_map` (`mpe.py:243`, `b.start <= a.end` inclusive) and
  `_Alloc.retire` (`mpe.py:167`, `rec[1] < now` inclusive), so both go silent: 0 pitch-bend
  messages, 0 CC74, 0 pressure — 28 channel-voice events total, thinning ratio 100 %.
  Two non-simultaneous notes lose all MPE data.
* 5 genuine same-channel simultaneities in `exhaustion.mid` (spec-sanctioned sharing, RP-053
  prefers sharing to note-stealing — but BAR's bullet "No two simultaneous notes share a member
  channel" is absolute, and the note that shares also loses its initial-state preamble, which is
  precisely what RP-053 warns produces "swooping").

### Robustness — **REFERENCE**

* **Hard crash** on a non-finite curve value: `OverflowError: cannot convert float infinity to
  integer` at `mpe.py:85` (`semitones_to_bend`) reached from `mpe.py:354` (`_lane_frames`).
  Repro: `case_inf` in `tests/critic_p4_mpe.py` — one note, `BEND` points
  `[(0,0),(0.5,inf),(1,-inf)]`. No `RenderError`, no warning, no file.
* **NaN silently deletes the whole curve.** `nan.mid` for a note whose bend goes 0 → +1 → −1 st
  contains exactly one bend message, `E1 00 40` (0.0 st), because `Curve.value_at` propagates NaN
  into both neighbouring segments and `_lane_frames` (`mpe.py:349-352`) drops those samples. No
  data is corrupted (good) but the gesture vanishes with no entry in `score.warnings`.
* **Zero-length notes are dropped without warning**: `zero_length.mid` has 2 note-ons for 3 input
  notes (`mpe.py:214,433` skip `dur <= 0`; `allocate_channels` still assigns them a channel).
* **Out-of-range bend clamps silently**: `beyond_range.mid` (±60 st requested, 12 st zone) clamps
  correctly (no 14-bit wrap: worst byte `E1 00 00` = −12.00 st) but records no warning, and the
  thinner loses the clamp knee — 59.3 ¢ error even under the generous linear reconstruction.
* Good: velocity/CC clamping is total, 1000-note and 200-beat scores render, curve points before
  and after the note lifetime never escape the note (`curve_past_end.mid`: first bend at tick 960
  = note-on, last at 1910 < note-off 1920).

### Event economy — **REFERENCE**

Measured (my counts, from the files, not the builder's stats):

| fixture | notes | emitted expr | thinning vs my own raw grid count | max expr/s/channel |
|---|---|---|---|---|
| dense_1000 | 1000 | 8000 / 20000 raw | **60.0 %** | 24 |
| long_200beats | 1 | 5254 / 20000 | 73.7 % | 57 |
| identical_pitch | 4 | 68 / 800 | 91.5 % | 17 |
| exhaustion | 20 | 1090 / 8000 | 86.4 % | 55 |
| curve_past_end | 1 | 6 / 150 | 96.0 % | 6 |
| triple_lane_fast | 1 | 611 / 800 | **23.6 %** | **323 (> 250)** |
| touching_1ch | 2 | 0 / 200 | 100 % (everything lost) | 0 |

(emitted counts include the three mandated preamble events and the pressure-0 teardown per note;
raw counts are my own grid-sample count, computed independently in `tests/critic_p4_mpe.py`.)

Two failures against the BAR bullet "≤ 250 expression events/second/channel":
* `triple_lane_fast.mid` measures **323 expression events/s on ch2** (sliding 1 s window,
  tempo-aware). This is not an exotic option setting: with `Score.grid_ms = 10` (the IR default),
  `_opts_from_score` (`mpe.py:525`) sets `pitch_grid_ms = 5`, so the *design ceiling* is
  200 bend/s + 100 pressure/s + 100 CC74/s = **400 events/s/channel**. There is no zone-wide or
  per-channel rate governor anywhere in `_build_events`; the digest's own "global ceiling ≈ 1000
  msg/s … widen the grid when polyphony is high" is not implemented.
* `dense_1000` lands at exactly **60.0 %** thinning — on the bar, with no margin, and the bar's
  named target (`examples/*.fil`) cannot be measured at all (D7).

### Realtime safety — **CANDIDATE**

* Scheduling is drift-free by construction: `realtime.py:105` takes `t0 = time.monotonic()` once
  per pass, `:107` computes an **absolute** deadline `target = t0 + beat * spb`, and `:108-112`
  spin-sleeps `min(dt, 0.001)` toward that deadline. No sleep accumulation; a late event does not
  push later events.
* Panic on interrupt and on any exception: `:120-123` catch `KeyboardInterrupt` and the `finally`
  always calls `_panic`, which sends channel pressure 0 + CC123 All Notes Off on every member
  channel plus 0 and 15 (`:73-82`), each send individually guarded.
* No expression after note-off in the played stream: `play` sends `render_events` verbatim
  (`:95,106`), and I verified 0 post-off expression events in the same stream serialised to file.

Gaps that keep this from being clean (not enough to flip the pick):
* `_panic` never re-centres pitch bend (`En 00 40`), never sends CC64=0 or CC121, and never sends
  real note-offs. RP-053 requires receivers to keep member-channel bend state while idle, so after
  Ctrl-C the zone is left detuned by up to the full bend range, and synths that ignore All Notes
  Off keep sounding (`realtime.py:76-78`).
* `_panic` calls `_mido()` at `:75` inside a `finally`; if the backend import ever fails there it
  raises `RenderError` and masks the original exception.
* `loop=True` never re-panics between passes (`:118`), so a hung note from pass *n* survives.

---

## 2. Defect list, severity ordered

**D1 (high) — the thinner assumes an interpolating receiver; MIDI receivers hold.**
`mpe.py:108-137`, `mpe.py:460-464`. Reconstructing each note's bend curve from the file and
comparing to the `Score` curve, max error in cents:

| fixture | hold-last-value reconstruction | linear-interpolation reconstruction |
|---|---|---|
| curve_past_end (ramp 0 → +1 st over 1 beat) | **98.75 ¢** | 0.66 ¢ |
| identical_pitch (6 Hz, ±0.1 st) | **19.96 ¢** | 3.00 ¢ |
| long_200beats (5 Hz, ±0.5 st) | **40.43 ¢** | 0.93 ¢ |
| triple_lane_fast (9 Hz, ±1 st) | **80.77 ¢** | **4.14 ¢** |
| exhaustion | 40.94 ¢ | 2.01 ¢ |

Minimal repro: note at beat 1.0, dur 1.0, `bend` points `[(0,-2),(1,0),(2,1),(4,2)]`. The file
contains exactly two bend messages for that note — `tick 960 → 0.0000 st`, `tick 1910 →
+0.9902 st`. A hold receiver plays a flat note then a jump 5 ms before note-off. BAR's "max
deviation ≤ 3 cents" therefore passes **only** under the linear reading, and even then
`triple_lane_fast` fails at 4.14 ¢ and `identical_pitch` sits exactly at 3.00 ¢.

**D2 (high) — channel-sharing / touching-note path drops mandated per-note messages.**
`mpe.py:230-246` (`_overlap_map`, inclusive `<=`), `mpe.py:163-176` (`retire`, inclusive),
`mpe.py:443,471,498,506` (`quiet`). Repro A: 20 notes at beat 0, dur 4 → 10 preamble violations,
10 missing `pressure 0` before note-off. Repro B: `MpeOptions(members=(1,))` with notes
0–1 and 1–2 → both notes rendered with zero bend/CC74/pressure.

**D3 (high) — `OverflowError` crash on `inf` in a curve.** `mpe.py:85` via `mpe.py:354`.
Repro: `ir.Curve(BEND, [(0,0),(0.5,float("inf")),(1,float("-inf"))])` → traceback, no file.

**D4 (medium-high) — density ceiling exceeds BAR.** Measured 323 expr/s on ch2; architectural
ceiling 400/s/channel from `pitch_grid_ms=5` + two 10 ms lanes (`mpe.py:69-70,408-409`); no rate
governor in `_build_events`.

**D5 (medium) — silent data loss with no `score.warnings` entry** in three distinct cases: NaN
curve (whole lane deleted, `nan.mid` has 1 bend message), zero-length notes (2 note-ons for 3
notes in `zero_length.mid`), out-of-range bend clamped (`beyond_range.mid`). Channel sharing does
warn (`mpe.py:222-227`), which shows the mechanism exists and simply is not used here.

**D6 (medium) — panic is incomplete.** `realtime.py:73-82`: no bend re-centre, no note-offs, no
CC121/CC64; `_mido()` inside `finally` can mask exceptions; no panic between loop passes.

**D7 (low, evidence gap) — the bar's own fixture is missing.** BAR P4 requires the thinning ratio
"on `examples/*.fil`"; there is no `examples/` directory in the repo, and the only `.fil` on disk,
`web/fixtures/source.fil`, fails to parse: `filigree.errors.ParseError: <input>:58:43: error:
unknown anchor '@root+5'`. That bullet is unmeasurable this round; I substituted my own fixtures
and reported both numbers. This is a P1/P3 problem surfacing in P4's evidence chain, not a
renderer defect.

**Non-defects I checked and cleared:**
* Cross-parser agreement is perfect. My byte-level reader, `mido`, and `tools/smf_parse.py`
  produce identical `(track, abs_tick, bytes)` streams on all 11 rendered files
  (11/11 MATCH; e.g. `dense_1000.mid` 10 108 events, `exhaustion.mid` 1 238). No parser defect in
  either implementation.
* Notes on MIDI channel 16 are **legal**, not a defect: with `mm=15` the upper zone is
  unallocated, and RP-053 says the unused zone's master may serve as a member channel.
* MSB-first MCM/RPN ordering is a defensible deviation from the spec's LSB-first examples and
  matches what Bitwig 5.2.5 transmits.
* Re-rendering is deterministic in the cases I ran (identical bytes).

---

## 3. The single largest gap

**The renderer buys its event economy with an assumption no primary source supports: that the
receiver linearly interpolates between pitch-bend messages.** A 1-beat 0 → +1 st ramp leaves the
renderer as two pitch-bend messages 950 ticks apart, and a 6 Hz vibrato leaves as two messages
per cycle at the extrema. Under the actual MIDI 1.0 semantics — a receiver holds the last
pitch-bend value until the next one — those become a step at the note's end and a square wave,
measured at **98.75 ¢** and **19.96 ¢** of pitch error, 33× and 6× over BAR's 3-cent budget.
The digest (`research/mpe_technical.md` §6.3) introduced this policy without a citation, and
`mpe.thin()` implements it verbatim, so the "≥ 60 % thinning **and** ≤ 3 ¢ round-trip" pair in
BAR P4 is currently satisfiable only by grading the file with the same interpolating model that
produced it. Fix direction: keep the deadband and dedup, drop linear-prediction dropping in
favour of a value-error budget evaluated against **hold** reconstruction (or emit a shaped
sub-grid that bounds hold error), and add a per-channel rate governor so D4 does not reappear
when the grid tightens.
