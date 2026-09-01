# P3 round 1 — critic verdict (gesture / curve system)

Judged against `refs/BAR.md` §P3, `docs/SPEC.md` §7–§8, and the public claims in
`refs/syntax/curves.md`. Artifacts judged: `src/filigree/gesture.py`,
`refs/plots/p3_*.png`, `refs/syntax/curves.md`. `NOTES_P3.md` and
`tests/test_gesture.py` were **not** read or relied on. Behavioural evidence:
`tests/critic_p3_curves.py` (47 tests, 99 assertions, **41 pass / 6 fail**).

Round status: **VALID** (evidence gate passed — every plot painted, the suite ran
to completion, no unrelated crashes).

---

## Forced picks

| Criterion | Winner | One-line reason |
|---|---|---|
| Expressiveness | **CANDIDATE** | `>3` (harmony-resolved bend target) and `NaN = unwritten` have no counterpart in any rival. |
| Concision | **REFERENCE** | On honestly-chosen idiomatic rival forms Csound is equal or shorter on 3 of the 5 gestures; the candidate's table wins only by counting padding. |
| Honesty of the bar | **REFERENCE** | Three rival capability claims are false against the cited primary docs, one rival snippet is schema-invalid, and one rival's char count is inflated 4×. |
| Correctness | **REFERENCE** | The flagship P3.2 snippet renders at 8.46 Hz instead of the written 5.5 Hz; `^~` leaves the lane range; `@` contradicts SPEC §8's own wording. |

### Expressiveness → CANDIDATE

- `gesture fall = bend(0 -> >3)` resolves against the harmony at eval time
  (`gesture.py` `GestureCtx.target`, called exactly once per gesture —
  `test_harmonic_target_glyph_ramps_from_previous_and_resolves_once`). Csound
  has no harmony model (the cited `transeg` page defines only `ia/idur/itype/ib`
  — [Csound transeg](https://csound.com/manual/opcodes/transeg/)); MusicXML
  `<bend-alter>` is "a number of semitones"
  ([MusicXML `<bend>`](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/bend/));
  Sonic Pi's `degree(:iii, :c4, :major)` is real but writes the key at the call
  site ([Sonic Pi degree/chord_degree reference](https://sunderb.me/sonic-pi-docs-test/da/reference/lang/chord_degree.html)).
- "Unwritten is NaN" is genuinely implemented and is a capability no rival has:
  `test_empty_slot_is_no_data_and_neighbours_stay_written`,
  `test_window_leaves_the_rest_of_the_lifetime_unwritten`,
  `test_mul_absorbs_no_data`, `test_add_treats_no_data_as_the_additive_identity`
  all pass. Csound's `kbend` is always defined; curves.md concedes this and is
  right to.
- Composition is real, not cosmetic: the published algebra law
  `a >> b == (a @ 0..50%) | (b @ 50%..100%)` holds to floating-point equality
  (`test_seq_rescales_each_half_and_matches_the_published_law`), and
  `>>(30%)` splits where it says (`test_seq_explicit_split_point`).

### Concision → REFERENCE

My own recount (non-whitespace characters, same rule as curves.md) reproduces
every number in the candidate's summary table exactly — so the arithmetic is
honest. The *snippet selection* is not. Replacing each rival with the shortest
idiomatic form the candidate's own prose already admits exists:

| # | Filigree | curves.md rival | Shortest honest rival | Winner |
|---|---|---|---|---|
| 1 | 32 | Csound 69 (GEN07, 3 lines) | `kbend transeg -1, 0.2, -2, 0, p3-0.2, 0, 0` = **34** | CANDIDATE (1.06×, not 2.2×) |
| 2 | 56 | Csound 59 | drop the do-nothing alias line `kbend = kvib` → **50** | REFERENCE |
| 3 | 57 | Csound 54 | 54 (as printed) | REFERENCE |
| 4 | 23 | Csound 76 | the code is `kbend transeg 0, p3, 0, p5` = **21**; the other 55 chars are a prose comment | REFERENCE |
| 5 | 96 | Csound 237 | 237 | CANDIDATE |

Gesture 2's flip is the sharpest: curves.md prints a third Csound line,
`kbend =      kvib`, which assigns a variable to itself under a new name and
does nothing. Deleting it takes Csound from 59 to 50 and reverses the only
margin (56 vs 59) that row ever had. Row 3 is worse: the table bolds
Filigree's **57** next to Csound's 54, i.e. the bolding marks the loser as the
winner.

### Honesty of the bar → REFERENCE

Every item below is an over-claim **in the candidate's favour**, which BAR.md
§P3 makes a serious defect.

1. **"`_slide` … interpolate linearly … there is no shape parameter" (P3.1) is
   false**, and the same false premise carries P3.3 ("both are linear: the
   exponential swell is lost") and P3.4 ("the slide is still linear"). Every
   Sonic Pi slidable opt also has `<opt>_slide_shape` (0 step, 1 linear,
   3 sine, 4 welch, 5 custom, 6 squared, 7 cubed) and `<opt>_slide_curve`
   (curvature, honoured when shape is 5) — see the
   [Sonic Pi synth opt reference](https://chuletitaspinguino.wordpress.com/wp-content/uploads/2015/12/man_sonic_pi.pdf)
   and the per-synth definitions listing `note_slide_shape` / `note_slide_curve`
   in [the synthdef parameter list](https://gordonguthrie.github.io/TheManual/chapter4/how_built_in_synths_are_defined_in_Sonic_Pi.html).
   `amp_slide_shape: 5, amp_slide_curve: 3` gives P3.3 a genuinely exponential
   swell, so P3.3's Sonic Pi "≈ (the exponential swell is lost)" should be ✅,
   and P3.1's and P3.4's stated reason for ≈ evaporates.
2. **The MusicXML snippet in P3.1 is not valid MusicXML.** The cited reference
   page states the child order as "`<bend-alter>` — required; **Zero or one of**:
   `<pre-bend>` / `<release>`"
   ([MusicXML `<bend>`](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/bend/)),
   yet curves.md writes `<bend-alter>-1</bend-alter><pre-bend/><release/>` —
   both children at once — and calls it "MusicXML at its best". The invalid
   `<release/>` is 10 of the 159 counted characters.
3. **MusicXML's actual idiom for gesture 1 is ignored.** `<scoop>` is a real
   MusicXML 4.0 articulation, documented as "an indeterminate slide attached to
   a single note … comes from below the main pitch"
   ([MusicXML `<scoop>`](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/scoop/)) —
   i.e. literally "a scoop up into the note". `<articulations><scoop/></articulations>`
   is **39** characters, not 159. The rival's cost for the headline gesture is
   overstated 4×.
4. **`transeg` is quietly excluded from the count it would win.** The P3.1 prose
   admits "`transeg -1, 0.2, -2, 0, …` fixes the duration-independence and buys
   a curve shape" — then leaves the 69-char GEN07 form in the table. The stated
   reason for still calling it ≈ is that the curve family "is an exponential
   family, not smoothstep": the gesture asked for a 200 ms scoop, not for a
   smoothstep, so this downgrade grades the rival against Filigree's
   implementation choice rather than against the task.
5. **Prose counted as code.** P3.4 gives Csound 76 chars, of which 55 are the
   comment `; p5 = interval to the next chord's third, computed by hand per note`.
   The ✗ judgement there is defensible; inflating the character count with the
   sentence that justifies the ✗ is not. (The doc also says "the code is 20
   chars"; it is 21.)
6. **P3.4's two columns solve different instances.** MusicXML is given
   `<bend-alter>3</bend-alter>` ("it happens to be 3 here"), while the
   candidate's own render of the same gesture lands on **+1.6 st**
   (`refs/plots/p3_4_target.png`, right edge). Whatever the harmony was, the
   rival was handed a different answer than the candidate produced.

### Correctness → REFERENCE

Six of my 47 tests fail; three are contradictions of published claims, and one
of those is visible in a shipped plot. Details and repros below.

---

## Blind readability test

Samples written unlabelled, order fixed by a seeded coin before I looked at
them; winner picked first, labels revealed afterwards.

**Gesture 1** — A: `gesture scoop = bend(-1st -> 0 @ 200ms)` · B: `kbend transeg -1, 0.2, -2, 0, p3-0.2, 0, 0`
→ **A**. A names its lane and its endpoints; B's `-2` is a curve *type* sitting
between two values and `p3-0.2` requires knowing what `p3` is.
*(A = Filigree.)*

**Gesture 2** — A: `gesture vib = bend(wiggle(5.5hz, 0.4st) * ramp(0, 1) @ 35%..100%)` · B: `kd linseg 0, p3*0.35, 0, p3*0.65, 1` / `kbend oscili kd*0.4, 5.5`
→ **A**. "wiggle × ramp, from 35 %" is three nouns; B spreads the 35 % across
two multiplications and hides the depth inside `kd*0.4`. *(A = Filigree.)*

**Gesture 3** — A: `gesture warm = press(0.15 -> 0.95, shape: exp) | timbre(0.7 -> 0.25)` · B: `kpress transeg 0.15, p3, 3, 0.95` / `ktimbre transeg 0.7, p3, 0, 0.25`
→ **A**. B's `3` and `0` in the same column mean "exponential" and "linear",
unguessable; A says `shape: exp`. *(A = Filigree.)*

**Gesture 4** — A: `control s, note: degree(:iii, :c4, :major)` · B: `gesture fall = bend(0 -> >3)`
→ **A**. This one goes to the rival: `degree(:iii, …)` says "the third degree"
in words, whereas B's `>3` is an unreadable digraph and B is additionally
mis-named (`fall` renders as a rise). *(A = Sonic Pi — REFERENCE wins gesture 4.)*

**Gesture 5** — A: Sonic Pi `define :cry do |n, depth = 0.5| … 12-line control loop … end` + three call sites · B: `gesture cry(depth: 0.5st) = bend(0 -> -depth @ 45% -> 0)` + `notes!gesture=cry | 0 1 2 3 4 5 6!cry(depth: 1.2st) 7 8 9 ^0 ^1 |`
→ **B**. In B the twelve notes and the single override are on one visible line;
in A the shape, the timing and the note list are interleaved with `sleep` and
`t += 0.01`. *(B = Filigree.)*

**Blind result: CANDIDATE 4 – 1.** The single loss is `>3`.

---

## Defects, severity-ordered

### D1 — CRITICAL. Rate primitives do **not** reclock inside composed gestures; the flagship vibrato renders 54 % sharp in rate, and the shipped plot shows it

`refs/syntax/curves.md` §"Semantic decisions": *"Rate primitives reclock, they do
not stretch. `wiggle`, `pulse` and `drift` are re-derived when windowed so Hz
stay real-time Hz"*, and §P3.2: *"The window reclocks the wiggle so 5.5 Hz stays
5.5 Hz of real time."*

Only a **bare** generator reclocks. `Segment.remapped` calls `_rescale_fn`, which
returns the function unchanged unless it is a `_RateFn` — and `_Combined`
(produced by `*`, `+`, `-`) and `_GlyphFn` (produced by `curve()` / drawn lanes)
have no `rescaled`. So the moment a wiggle is multiplied by anything — which is
exactly what P3.2 does — windowing compresses its phase instead of reclocking
it: effective rate becomes 5.5 / 0.65 = **8.46 Hz**.

Repro (`test_published_vibrato_snippet_keeps_its_documented_rate`):

```python
c = GestureCtx(note_dur_beats=4.0, tempo=120.0)          # 2 s note, as plotted
g = bend( wiggle(5.5hz, 0.4st) * ramp(0,1) @ 35%..100% ) # curves.md P3.2 verbatim
# first descending zero crossing after the window opens:
#   expected 0.35 + (1/11)/2 s = 0.3955   actual 0.37955  -> 8.46 Hz, not 5.5 Hz
```

Same failure for drawn `~`: `curve("~").windowed(0.0, 0.5)` halves the wiggle's
real-time period (`test_glyph_wiggle_reclocks_when_the_curve_is_windowed`: first
zero at 0.0500 instead of 0.1000), so any `~` inside a `>>` or `@` is off-rate
too. `test_bare_wiggle_reclocks_under_a_window` passes, which is why the bug
survived: the only reclocking that works is the case with no operator in it.

**This is visible in `refs/plots/p3_2_vibrato.png`.** Between x = 0.35 and
x = 1.00 (1.3 s of real time on the 2 s note the plot was rendered with) the
trace completes ~11 cycles; 5.5 Hz would be 7.15. The plot is a faithful render
of the code and therefore ships the wrong gesture under a caption that says
`5.5hz`.

### D2 — HIGH. Drawn curves leave the lane range: `^~` demands ±2.67 st on a ±2 st lane

`test_glyph_curves_stay_inside_the_lane_range` fails on `"^~"`: max = **2.6667**
where SPEC §3.2 fixes the bend lane at ±2 st by default.

```python
curve_from_string("^~", "bend", GestureCtx(note_dur_beats=2.0))
# sampled max = 2.6666666666666665   (lane max = 2.0)
```

Cause: `glyphs_to_gesture` adds the `~` excursion (`GLYPH_WIGGLE_DEFAULT/9 × half
span` = 0.667 st) on top of the running anchor with no clamp, so `^~` / `9~`
(and `_~`, symmetrically) ask for 33 % more than the lane can carry. Either the
renderer clips — and the drawn shape is then not what sounds, breaking BAR.md
P3's eyeball check — or it wraps. Nothing in `gesture.py` decides which.

### D3 — HIGH. `@ x..y` contradicts SPEC §8

SPEC §8's operator table: `a @ x..y` = "**restrict** to a window of the note
lifetime". The implementation *refits*: `Gesture.windowed` remaps the whole
curve into `a..b`.

```python
bend(0 -> 1, shape: linear) @ 0..50%
# SPEC "restrict": value 0.25 at t=0.25, 0.50 at t=0.50
# actual:          value 0.50 at t=0.25, 1.00 at t=0.50
```

(`test_window_restricts_rather_than_rescales_per_SPEC_8`.) `curves.md` declares
the fitting behaviour, so the two shipped documents disagree with each other and
the spec — the normative document — is the one that is wrong or ignored. A
reader following SPEC §8 will mis-predict every windowed gesture, and the
"`@ 45%`"-style examples in §8 itself become ambiguous.

### D4 — MEDIUM. `~` biases the value it is supposed to decorate

`test_tilde_does_not_bias_the_running_value` fails: over the `~` slot of
`curve("5~")` the mean is **0.3071** against a running value of 0.2222 — the
average pitch of the slot is 8.5 cents sharp, because the slot holds 2.5 sine
cycles and the half-cycle remainder is unbalanced. `~` is documented as
"sine around the running value" (SPEC §7); a vibrato that moves the mean is a
tuning bug, and its size depends on slot length, so it is not even consistent
across bars. The symmetry of the excursion itself is fine
(`(min+max)/2` = 0.2222, first assertion of
`test_tilde_wiggles_around_the_running_value_not_instead_of_it` passes).

### D5 — MEDIUM. Zero-duration notes silently delete all oscillator content

`test_zero_length_note_wiggle_is_not_a_dead_flat_line`: with
`note_dur_beats=0`, `ctx.note_dur_sec == 0` → `_Wiggle.span_sec == 0` → every
sample is `sin(0) = 0`. No error, no warning; `wiggle`, `pulse` and `drift`
all collapse to a flat line, and `@ 200ms` positions silently fall back to their
default (`_pos_value` returns `default` when `dur_ms <= 0`). Breakpoint curves
survive intact (`test_zero_length_note_does_not_crash_or_emit_nan` passes), so
the failure is silent and partial — the worst kind.

### D6 — LOW. Plots omit the note duration, which is what hides D1

None of the six PNGs state tempo or note length. `p3_1_scoop.png`,
`p3_3_swell.png` and `p3_4_target.png` are rendered with a 1 s note while
`p3_2_vibrato.png` is rendered with a **2 s** note (`tools/plot_curves.py`
line 99, `note_dur_beats=4.0`, against the module default of 2.0). A reader
therefore cannot check "200 ms" on plot 1 or "5.5 hz" on plot 2 from the plot at
all — the x axis is normalised lifetime in every case. Adding "note = 1.0 s @
120 bpm" to each subtitle would have caught D1 immediately.

### D7 — LOW. `p3_4_target.png` mis-labels its own gesture

The gesture is named `fall` and the curve **rises** monotonically from 0 to
+1.6 st (`refs/plots/p3_4_target.png`, whole trace). Same name in
`curves.md` §P3.4. Nothing is numerically wrong; the label contradicts the
picture.

### D8 — LOW. Plots bypass the parser they claim to demonstrate

`curves.md` says the PNGs "are produced by `tools/plot_curves.py` straight out
of `src/filigree/gesture.py`, so the plots are the implementation, not a
mock-up". They are produced from **hand-written AST trees**
(`tools/plot_curves.py`, "helpers for building expression trees by hand"), not
from the Filigree source printed in each title. I checked the parser separately
and all five snippets do parse (`filigree.parse.parse`), including the P3.5
block once wrapped in `stave lead { … }`, so the claim happens to be true — but
the plots are not evidence for it.

### Passing checks worth recording (no defect)

Exact values at t = 0 / 0.5 / 1 for breakpoints under all five shapes, the
documented `exp` formula `(e^{3f}−1)/(e^3−1)`, `ease` = `f²(3−2f)`, `hold` as
post-hold and `snap` as pre-jump, `ramp` linear by default, `pulse` duty,
`/` and `\` ramping from the previous running value (including from the lane
centre when nothing is running), `x` holding, `___/^^^` = hold-min / ramp /
hold-max, `>` glides from the running value and resolves **once**, targets
rejected off the bend lane, `>>` split points, `*` scalar vs elementwise,
NaN absorbed by `*` and identity under `+`, no data outside `0..1`,
single-glyph bars, a 64-anchor bar (anchors land on slot ends, values in range),
`drift` byte-identical in-process, across `PYTHONHASHSEED` values **and** in a
spawned subprocess, and seed-key sensitivity. 41 of 47 tests pass.

---

## The single largest gap

**The candidate's central claim — that a gesture is a *composable* value —
is only true of its shape, not of its clock.** Compose a rate primitive with
anything (`*`, `+`, `>>`, a drawn `~`, a windowed `curve()`) and the vibrato
silently changes speed, because `_rescale_fn` only knows how to reclock the two
leaf classes and returns `_Combined` and `_GlyphFn` untouched. That is not a
rounding error: the one snippet the project chose as its showcase for
composition, `bend(wiggle(5.5hz, 0.4st) * ramp(0, 1) @ 35%..100%)`, plays at
8.46 Hz, and the plot shipped to prove it is the proof of the bug. Until
`_Combined` and `_GlyphFn` implement `rescaled`, every claim in
`refs/syntax/curves.md` about real-time rates should be read as false, and the
honesty defects (D1 plus items 1–6 above) mean the bar is currently drawn in the
candidate's favour rather than measured.
