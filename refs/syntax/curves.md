# Filigree curves & gestures vs. the rivals

The five reference gestures from `refs/BAR.md` §P3, written side-by-side in
Filigree and in the three notations people actually reach for when they want a
note to *move*: Csound (`transeg`, user-defined opcodes), Sonic Pi `_slide` opts,
and MusicXML `<bend>` / `<scoop>`.

Rendered output of every Filigree column is in `refs/plots/`
(`p3_1_scoop.png` … `p3_5_reuse.png`, plus `p3_6_glyph_lane.png` for the §7 glyph
lane and `p3_7_lane_range.png` for lane-range discipline). Every caption states
the rate, values and shape **measured from the plotted samples**, not from the
source text. Those PNGs are produced by `tools/plot_curves.py` straight out of
`src/filigree/gesture.py`, so the plots are the implementation, not a mock-up.

> **Round 2 honesty pass.** Round 1 of this file over-claimed. Three specific
> errors have been corrected here and they change three of the five rows:
> Sonic Pi's slides are **not** linear-only, MusicXML has a dedicated `<scoop>`
> articulation that is far shorter than the `<bend>` longhand shown before, and
> the Csound columns were padded with a comment and a no-op line. Rows 2, 3 and
> 4 now go to a rival under the counting rule below and are marked
> **REFERENCE**. What Filigree still wins, it wins on expressiveness, not on
> a bad count.

**Reference docs**

- Csound `transeg` (per-segment curve shape): <https://csound.com/manual/opcodes/transeg/>
- Csound user-defined opcodes: <https://csound.com/manual/opcodes/opcode/>
- Sonic Pi tutorial §7.3 "Sliding Opts" (slide *times* only): <https://sonic-pi.net/tutorial.html>
- Sonic Pi synth-opt reference for `*_slide_shape` / `*_slide_curve`: <https://chuletitaspinguino.wordpress.com/wp-content/uploads/2015/12/man_sonic_pi.pdf>
- Sonic Pi synthdef parameter listing showing `note_slide_shape` / `note_slide_curve` per synth: <https://gordonguthrie.github.io/TheManual/chapter4/how_built_in_synths_are_defined_in_Sonic_Pi.html>
- Sonic Pi `degree`: <https://sunderb.me/sonic-pi-docs-test/da/reference/lang/degree.html>
- MusicXML 4.0 `<bend>`: <https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/bend/>
- MusicXML 4.0 `<scoop>`: <https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/scoop/>

**Counting rule** (identical for every column, no exceptions): comment-only
lines, blank lines and no-op lines are removed, then the non-whitespace
characters of what is left are counted. A comment is *never* counted, not even
when it describes work a human must do by hand — that cost is argued in prose
instead. Csound score `i` statements in P3.5 are not comments; they are the data
the score has to carry, so they are printed as score lines and counted. Counts
are re-derivable with `/home/user/workspace/p3_char_counts.py`.

**Verdict key.** ✅ expresses it exactly · ≈ expresses an approximation, losing a
documented property · ✗ cannot express it at all.

---

## Summary

| # | Gesture | Filigree | Csound | Sonic Pi | MusicXML | Shortest | Verdict |
|---|---------|----------|--------|----------|----------|----------|---------|
| 1 | 200 ms scoop up from −1 st | **32** ✅ | 34 ≈ | 76 ✅ | 39 ≈ | Filigree, by 1.06× | CANDIDATE (narrow) |
| 2 | vibrato that fades in from 35 % | 58 ✅ | **50** ✅ | 124 ≈ | ✗ | Csound | **REFERENCE** |
| 3 | pressure swells (exp) while timbre closes | 57 ✅ | **54** ✅ | 145 ✅ | ✗ | Csound | **REFERENCE** |
| 4 | bend landing on the next chord's third | 23 ✅ | **21** ✗ | 87 ≈ | 41 ✗ | Csound | **REFERENCE** |
| 5 | one parameterised gesture on 12 notes, one retuned | **96** ✅ | 193 ≈ | 209 ≈ | ✗ | Filigree, by 2.01× | CANDIDATE |

Read that table honestly:

- **Filigree is only the shortest notation in 2 of 5 rows**, and row 1 is a
  1.06× margin — a rounding error, not a win. Csound is shorter in rows 2, 3
  and 4.
- **Filigree is the only column with no ✗ and no ≈** — every gesture is written
  once, in real units, and adapts to note duration and harmony without being
  recomputed. That is the claim this piece actually stakes.
- **Sonic Pi is not the linear-only notation round 1 said it was.** Every
  `_slide` opt has a matching `_slide_shape` (0 step, 1 linear, 3 sine, 4 welch,
  5 custom via `_slide_curve`, 6 squared, 7 cubed), so it can shape a slide
  ([Sonic Pi synth-opt reference](https://chuletitaspinguino.wordpress.com/wp-content/uploads/2015/12/man_sonic_pi.pdf),
  [synthdef parameter listing](https://gordonguthrie.github.io/TheManual/chapter4/how_built_in_synths_are_defined_in_Sonic_Pi.html)).
  That upgrades it to ✅ in rows 1 and 3. Only the Sonic Pi *tutorial* talks
  about slide time alone ([tutorial §7.3](https://sonic-pi.net/tutorial.html)),
  which is where the round-1 error came from.
- **Csound wins the concision argument outright** wherever the gesture is a
  shaped envelope on a numbered variable. Filigree's answer is not "fewer
  characters", it is that `press`, `timbre` and `bend` are lanes a renderer
  knows how to emit, and that `>3`, `@ 200ms` and `depth:` mean something to the
  language.

---

## P3.1 — 200 ms scoop up from −1 semitone

Plot: `refs/plots/p3_1_scoop.png`

**Filigree** — 32 chars — ✅

```filigree
gesture scoop = bend(-1st -> 0 @ 200ms)
```

Absolute-time placement (`@ 200ms`), the default `ease` (smoothstep) shape, and
an implicit hold at `0` for the rest of the note. Everything after 200 ms is
*written*, not left undefined, because the last breakpoint extends to note-off.

**Csound** — 34 chars — ≈

```csound
kbend transeg -1, 0.2, -2, 0, p3-0.2, 0, 0
```

Round 1 showed a GEN07 f-table plus two wiring lines (69 chars) and called it
2.2× longer than Filigree. That was unfair: `transeg` is the idiomatic way to
write this and it is 34 chars, i.e. **1.06× Filigree** — effectively a tie. It is
duration-independent (`p3-0.2`) and genuinely curved; `itype = -2` is an
exponential-family segment, not smoothstep, so the S-curve shape differs
([Csound `transeg`](https://csound.com/manual/opcodes/transeg/)). That, plus the
fact that `kbend` is a bare k-rate variable you must still wire into a synth's
pitch input yourself, is the whole of the ≈.

**Sonic Pi** — 76 chars — ✅

```ruby
s = play 60, note: 59, sustain: 1, note_slide: 0.2, note_slide_shape: 3
control s, note: 60
```

Round 1 claimed "`_slide` opts interpolate linearly and expose only a slide
*time* — there is no shape parameter". **That was wrong.** `note_slide_shape: 3`
selects a sine-shaped slide, and shapes 0/1/3/4/5/6/7 are step, linear, sine,
welch, custom, squared and cubed
([Sonic Pi synth-opt reference](https://chuletitaspinguino.wordpress.com/wp-content/uploads/2015/12/man_sonic_pi.pdf)).
Sonic Pi therefore expresses this gesture exactly, at 2.4× the characters. The
only remaining awkwardness is stylistic: the pitch is spelled twice, absolutely
(59, then 60) rather than once as an offset from the note.

**MusicXML** — 39 chars — ≈

```xml
<articulations><scoop/></articulations>
```

Round 1 printed a 159-char `<bend>` block here. That was not the shortest honest
form: MusicXML has a dedicated `<scoop/>` articulation, "an indeterminate slide
attached to a single note … appears before the main note and comes from below the
main pitch"
([MusicXML `<scoop>`](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/scoop/)).
At 39 chars it is within 1.22× of Filigree. It stays ≈ for a precise reason and
not a length one: `<scoop/>` is *always empty*, so there is no way to say −1
semitone and no way to say 200 ms — the depth and duration are left to the
player. The `<bend>` longhand can name the interval and duration-percentages but
not the contour: shape is only `accelerate="yes|no"`, the bend is discretised
into `beats` steps, and the `shape` attribute picks an engraved symbol, not a
playback contour ([MusicXML `<bend>`](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/bend/)).

---

## P3.2 — vibrato that fades in from 35 % of the note — **REFERENCE (Csound)**

Plot: `refs/plots/p3_2_vibrato.png`

**Filigree** — 58 chars — ✅

```filigree
gesture vib = bend((wiggle(5.5hz, 0.4st) * ramp(0, 1)) @ 35%..100%)
```

Three orthogonal ideas — an oscillator, a depth envelope, a window — composed
with `*` and `@`. Two things a reader must know:

- **`@` binds tighter than `*`.** The parentheses are load-bearing: without them
  the window would apply to `ramp(0, 1)` alone. Round 1 printed the
  un-parenthesised form (56 chars) while describing the parenthesised behaviour.
- **`@ x..y` restricts; it does not refit** (SPEC §8). Before 35 % the lane is
  **NaN**, genuinely unwritten, so a vibrato from another layer is not stomped.
  Inside the window the wiggle keeps its **absolute 5.5 Hz** and takes the window
  open as phase 0 — measured 5.500 Hz from the rendered curve's zero crossings —
  while the depth envelope keeps its own note-lifetime domain, so the vibrato
  enters at 35 % of full depth (0.14 st) and reaches 0.4 st at note-off.

**Csound** — 50 chars — ✅ — **shortest**

```csound
kd    linseg 0, p3*0.35, 0, p3*0.65, 1
kbend oscili kd*0.4, 5.5
```

Round 1 counted 59 chars because it printed a third line, `kbend = kvib`, that
did nothing but rename the previous line's output. Removed, Csound is 50 chars
and **wins this row**: signal-rate composition of an envelope and an oscillator
is exactly what the language is for, and `p3`-relative timing makes it
duration-independent too. Filigree's remaining advantage is narrow and specific:
`kbend` is *always* defined (it is 0 before 35 %), so Csound has no way to say
"this region is not mine".

**Sonic Pi** — 124 chars — ≈

```ruby
s = play 60, sustain: 2
t = 0.0
while t < 2.0
  d = t < 0.7 ? 0.0 : (t - 0.7) / 1.3
  control s, note: 60 + 0.4 * d * Math.sin(2 * Math::PI * 5.5 * t)
  sleep 0.02
  t += 0.02
end
```

Slide shapes do not help here: a shape is a one-shot contour between two values,
not an LFO, so vibrato on a `play`ed note becomes a hand-written control loop at
a hand-chosen 50 Hz update rate. Sliding is also "sticky" — once set, a `_slide`
is reused by every later `control` on that node
([tutorial §7.3](https://sonic-pi.net/tutorial.html)).

**MusicXML** — ✗

No vibrato depth, rate or ramp exists. `<wavy-line>` and `<other-ornament>` are
engraver's symbols, and `<bend>` is a single-target pitch change that cannot
oscillate. **Inexpressible.**

---

## P3.3 — pressure swells (exponential) while timbre closes — **REFERENCE (Csound)**

Plot: `refs/plots/p3_3_swell.png`

**Filigree** — 57 chars — ✅

```filigree
gesture warm = press(0.15 -> 0.95, shape: exp) | timbre(0.7 -> 0.25)
```

`|` is the parallel/merge operator: two independent lanes, one gesture, one name.
`shape: exp` is per-breakpoint-list; `exp` is `(e^{3f}−1)/(e^3−1)`.

**Csound** — 54 chars — ✅ — **shortest**

```csound
kpress  transeg 0.15, p3, 3, 0.95
ktimbre transeg 0.7,  p3, 0, 0.25
```

Round 1 printed 54 for Csound and 57 for Filigree and then bolded Filigree
anyway. Csound **wins this row**: `transeg`'s `itype` gives real per-segment
curvature ([Csound `transeg`](https://csound.com/manual/opcodes/transeg/)) and
two parallel envelopes are two lines. The exact curve family differs from
Filigree's `exp`, and `kpress`/`ktimbre` are variables you must wire into a
synth yourself rather than lanes a renderer already knows how to emit — but
neither of those is a length argument.

**Sonic Pi** — 145 chars — ✅

```ruby
s = synth :prophet, note: 60, sustain: 4, amp: 0.15, amp_slide: 4,
  amp_slide_shape: 6, cutoff: 90, cutoff_slide: 4, cutoff_slide_shape: 1
control s, amp: 0.95, cutoff: 60
```

Also upgraded from round 1's ≈: `amp_slide_shape: 6` is a squared (curved) swell
and `cutoff_slide_shape: 1` keeps the timbre close linear, so the "one curved,
one straight, in parallel" intent is expressible
([Sonic Pi synth-opt reference](https://chuletitaspinguino.wordpress.com/wp-content/uploads/2015/12/man_sonic_pi.pdf)).
The remaining objection is portability, not shape: `amp` and `cutoff` are
synth-specific opts, not general expressive lanes, and the curve family is a
fixed menu rather than a named function.

**MusicXML** — ✗

No per-note continuous pressure or timbre lane exists. Dynamics are symbols and
wedges attached to the part, not a sampled curve on one note, and there is no
MPE-style timbre axis. **Inexpressible.**

---

## P3.4 — bend landing on the next chord's third — **REFERENCE (Csound)**

Plot: `refs/plots/p3_4_target.png`

**Filigree** — 23 chars — ✅

```filigree
gesture lift = bend(0 -> >3)
```

(Round 1 called this gesture `fall` while it bends *up* to the third. Renamed.)
`>3` is a *harmonic Target*, not a number: at eval time `ctx.resolve_target`
turns it into semitones against the harmony in force — here **+1.6 st**, the
distance from the sounding pitch to the third of the chord under the next note.
Reharmonise the piece and the bend follows.

**Csound** — 21 chars — ✗ (symbolically) — **shortest**

```csound
kbend transeg 0, p3, 0, p5
```

Round 1 scored this 76 by counting a 55-char comment that explained the manual
work. Under the counting rule the code alone is 21 chars, so Csound is
**shorter than Filigree here** and this row is a REFERENCE win on concision. The
symbolic gap is unchanged and is the honest point: `p5` is a number somebody
computed outside the score, per note, because Csound has no model of harmony. It
expresses the *result*, never the intent — and if the harmony changes, all
twelve `p5` values are wrong and nothing tells you.

**Sonic Pi** — 87 chars — ≈

```ruby
s = play 60, sustain: 2, note_slide: 2, note_slide_shape: 3
control s, note: degree(:iii, :c4, :major)
```

The closest rival symbolically: `degree(:iii, :c4, :major)` really does resolve a
scale degree to a note ([Sonic Pi `degree`](https://sunderb.me/sonic-pi-docs-test/da/reference/lang/degree.html)).
It stays ≈ because `:c4, :major` is the key written out at the call site, not
"whatever chord is under the *next* note", so it does not follow a
reharmonisation. The slide itself can now be shaped (`note_slide_shape: 3`), so
that is no longer part of the complaint.

**MusicXML** — 41 chars — ✗ (symbolically)

```xml
<bend><bend-alter>1.6</bend-alter></bend>
```

`<bend-alter>` is a number of semitones, so it must carry the *rendered* answer:
1.6 st, matching `p3_4_target.png`. (Round 1 wrote `3` here, silently confusing
"the third of the chord" with "three semitones", while its own plot landed on
+1.6 st.) Nothing in the document ties the number to the harmony.
**Cannot express the intent.**

---

## P3.5 — one parameterised gesture on 12 notes, one note retuned

Plot: `refs/plots/p3_5_reuse.png` (all twelve notes in bar time, note 7 highlighted)

**Filigree** — 96 chars — ✅

```filigree
gesture cry(depth: 0.5st) = bend(0 -> -depth @ 45% -> 0)
notes!gesture=cry | 0 1 2 3 4 5 6!cry(depth: 1.2st) 7 8 9 ^0 ^1 |
```

Definition with a typed default, lane-wide attachment via `!gesture=`, and a
per-note override that names only the parameter that changed. The gesture is
expressed in note-lifetime fractions, so it adapts to each note's duration with
no rewriting.

**Csound** — 193 chars — ≈

```csound
opcode Cry, k, i
  idepth xin
  kb transeg 0, p3*0.45, 0, -idepth, p3*0.55, 0, 0
  xout kb
endop
i1 0 .5 60 0.5
i1 + .5 61 0.5
i1 + .5 62 0.5
i1 + .5 63 0.5
i1 + .5 64 0.5
i1 + .5 65 0.5
i1 + .5 66 1.2
i1 + .5 67 0.5
i1 + .5 68 0.5
i1 + .5 69 0.5
i1 + .5 72 0.5
i1 + .5 73 0.5
```

Recount: round 1 said 237 by including a prose comment and by commenting out the
score lines. The score lines are real data and are counted; the prose is not.
193 chars, still 2.01× Filigree. A user-defined opcode
([Csound `opcode`](https://csound.com/manual/opcodes/opcode/)) gives real
abstraction and `p3`-relative timing gives real duration independence, so this is
the closest rival on this row. What it lacks is a default: `0.5` is repeated on
all eleven unchanged notes, which is exactly the edit cost the override syntax
exists to remove.

**Sonic Pi** — 209 chars — ≈

```ruby
define :cry do |n, depth = 0.5|
  s = play n, sustain: 0.5
  t = 0.0
  while t < 0.5
    u = t / 0.5
    v = u < 0.45 ? u / 0.45 : (1 - u) / 0.55
    control s, note: n - depth * v
    sleep 0.01
    t += 0.01
  end
end
[60, 61, 62, 63, 64, 65].each { |n| cry n }
cry 66, 1.2
[67, 68, 69, 72, 73].each { |n| cry n }
```

`define` with a default parameter is genuine reuse and the override is one extra
argument — the abstraction story is good. The curve is the problem: a two-segment
dip cannot be expressed as one slide, so this is a hand-rolled sample loop,
blocking, tied to a hard-coded 0.5 s note length. (A `note_slide_shape` pair
could shape each half, at the cost of splitting the gesture into two `control`
calls and still hard-coding the note length.)

**MusicXML** — ✗

No macro, function, or default-parameter mechanism. Each of the twelve notes
carries its own longhand `<bend>` with its own literal `<bend-alter>`, and "the
same gesture, one parameter changed" is not something the document can say.
**Inexpressible.**

---

## Semantic decisions this file relies on

Recorded here because they are the things a reader will otherwise guess wrong,
and they are what `tests/test_gesture.py` pins down. Fuller list in
`NOTES_P3.md`.

- **`@ x..y` restricts, it does not refit** (SPEC §8, corrected in round 2). The
  inner gesture keeps its own note-lifetime timing; the window only decides which
  part of it is written. Outside the window the lane is NaN. Nested windows
  intersect, and disjoint ones write nothing.
- **Rate primitives keep their Hz everywhere.** `wiggle`, `pulse`, `drift` and
  the glyph `~` carry an absolute real-time rate through `*`, `+`, `>>`,
  `@ x..y`, glyph lanes and glyph-slot placement. Measured from rendered zero
  crossings, a written 5.5 Hz is 5.500 Hz in all of those nestings. A window
  additionally moves phase 0 to the window open.
- **`>>` is a hand-off, not a time compressor.** `a >> b` is exactly
  `(a @ 0..split) | (b @ split..100%)`, and since `@` restricts, each side keeps
  its own timing and only its share of the lifetime is written.
- **Unwritten is NaN, and NaN is load-bearing.** Outside every segment a lane
  samples as NaN, meaning "not mine — do not emit". `add`/`sub` treat NaN as the
  additive identity; `mul`, scalar scaling, and `neg` propagate it.
- **No gesture output leaves the lane range.** Glyph curves clamp to the lane,
  and a `~` next to a lane boundary *compresses* to the available headroom rather
  than clipping, so its mean stays on the anchor the writer asked for: on the
  ±2 st bend lane, `8~` swings 1.111 … 2.000 st around 1.556, and `^~` — at the
  exact top — has no headroom and renders as a flat hold at 2 st. Write `8~` for
  vibrato near the top of a lane.
- **The glyph `~` snaps to a whole number of cycles** in its slot, so it never
  ends mid-swing and never biases the slot's average away from the value it
  decorates.
- **Glyph values land at the end of their slot**, and a run opens flat — except
  `/`, `\` and `>`, which start from the running value. So `___/^^^` is
  hold-min, ramp across the `/`, hold-max (see `p3_6_glyph_lane.png`).
- **`hold` is post-hold, `snap` is pre-jump.** `ease` is smoothstep
  `f²(3−2f)`; `exp` is `(e^{3f}−1)/(e^3−1)`.
- **`drift` is deterministic**: seeded value noise keyed by `ctx.seed_key`, via
  blake2b so it survives Python hash randomisation.
- **Targets resolve once at eval time**, not per sample, and only on `bend`.
