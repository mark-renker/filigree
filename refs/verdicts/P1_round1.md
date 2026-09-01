# P1 — Language surface / ergonomics — Round 1 verdict

Critic: fresh-context, independent. I did not build this. No `NOTES_*.md` was read; the authors'
own claims are not evidence here. Everything below is either (a) output I produced from the
compiler in this repo, (b) a character count I computed myself, or (c) a line number in
`docs/SPEC.md` / `examples/*.fil`.

**Round status: VALID.** All six Filigree solutions compile and render; `/tmp/tasks.mid` parses in
`mido` (7 tracks, ppq 960). No evidence-gate failure.

Commands used (all from repo root):
`PYTHONPATH=src python -m filigree.cli explain <file>` /
`... render <file> -o /tmp/x.mid` / `... json <file> -o /tmp/tasks.json`.
Scratch probes live in `/tmp/min/` and `/tmp/min/err/`.

---

## 1. Verification — does each solution musically do the task?

`explain examples/tasks.fil` and `render examples/tasks.fil -o /tmp/tasks.mid`
(`wrote /tmp/tasks.mid (46 notes, 64.00 beats, 6 stave(s), MPE lower zone)`; `warnings: []`).

### T1 — 4-bar minor ii–V–i, exactly four voices, smooth voice leading → **PASS (with a task-fidelity nit)**
Numbers read from `explain`:
```
bar 1.00  ii7b5  halfdim7  pcs[2,5,8,0]    guide[5,0]  voiced[50, 53, 56, 60]
bar 2.00  V7     dom7      pcs[7,11,2,5]   guide[11,5] voiced[50, 53, 55, 59]
bar 3.00  i9     min9      pcs[0,3,7,10,2] guide[3,10] voiced[50, 51, 58, 60]
```
pcs are correct (D F Ab C / G B D F / C Eb G Bb D). Exactly 4 notes sound per chord. Total
absolute voice movement bar1→bar2 = |50-50|+|53-53|+|56-55|+|60-59| = **2 semitones**;
bar2→bar3 = 0+2+3+1 = **6**. No crossings. Voice leading is genuinely solved.
*Nit:* the shipped bar 4 is `-`, which `explain` resolves to one 8-beat chord
(`8.000 8.000`), i.e. **three attacks, not the four the task asks for** (`Cm9 | Cm9`).
Ziffers `i+4 i+4`, Strudel `Cm9!2` and Alda `*2` all re-articulate. Writing `i9 | i9`
fixes it (`/tmp/min/t1b.fil`, 4 attacks confirmed).

### T2 — last note bends into the *next chord's third* → **PASS, verified numerically**
This is the flagship claim, so I checked it three ways.
```
23.000  1.000  74  90  -   bend[+0.00..+1.00×8]
24.000  8.000  75  90  -
bar 7.00  i9  min9  pcs[0,3,7,10,2]  guide[3,10]
```
- Note is pitch **74 = D5**, `bend!range=4st`, and the lane values are printed in **semitones**
  (cross-checked against T3's `depth: 0.35st` → `bend[-0.34..+0.33]` and T6's `0.3st` →
  `bend[-0.30..+0.30]`). So the endpoint is **+1.00 st → sounding pitch 75 = Eb5**.
- Eb is pc 3 = the **third of Cm9** (`pcs[0,3,...]`). Correct target, not a hand-typed number.
- Curve from `/tmp/tasks.json`: `[[23.0,0.0],[23.119,0.039],[23.266,0.175],[23.497,0.496],
  [23.728,0.818],[23.875,0.957],[23.994,0.9999],[24.0,1.0]]` — monotone ease, arriving at
  **exactly beat 24.0 = the bar line**.
- In the rendered SMF (`@bend-range 48st`, so 1 st = 170.67 units) the last pitchwheel before
  note-off is `pitch=167` at tick 22980, note_off at 23040 → **97.8 cents, 2.2 cents short, and
  the peak lands 60 ticks (≈45 ms at 84 bpm) before the bar line.** Musically fine, but the
  claim "arriving exactly at the bar line" is 45 ms optimistic in the MIDI, not the model.
Independently confirmed with `/tmp/min/probe_gt.fil`: on `harm | i | VI |`, `>3` on a sounding
C4 resolved to `bend[-12.00..-0.00]` — 0 semitones, because C already *is* the third of Ab. The
feature is real.

### T3 — vibrato starting 35% in, widening → **PASS, verified from the sample list**
```
32.000  4.000  60  90  -  bend[-0.34..+0.33×96]
```
Curve points: `[32.0, null], [33.4, 0.0], [33.442, 0.114], ...` Note spans 32.0–36.0 (4 beats);
first non-null sample is at **33.4 = exactly 35% in** (32 + 0.35×4). Depth grows: first
excursions ±0.11–0.14 st, final excursions ±0.30–0.34 st → **widens monotonically to ±34 cents**
(task asked ~±35). Peak-to-peak spacing ≈0.224 beat = 0.16 s → **≈6.25 Hz** (task: ~6 Hz).
**Defect found:** the first sample of every windowed gesture is a literal `null`
(`[32.0, null]`). 13 nulls in 400 curve samples across `examples/tasks.fil` — one per T3/T6
note. It does not reach the SMF, but it is in the documented playground JSON schema.

### T4 — one chord, four voices, four independent curves → **PASS mechanically, FAIL on the claim**
```
36.000 4.000 60 90 bass  press[+0.00..+1.00×8]     bass  press 0.0→1.0
36.000 4.000 63 90 tenor press[+0.00..+1.00×10]    tenor press 1.0→0.0
36.000 4.000 67 90 alto  timbre[+0.00..+1.00×10]   alto  timbre 0.0→1.0
36.000 4.000 70 90 sop   timbre[+0.00..+1.00×10]   sop   timbre 1.0→0.0
```
(directions read from `/tmp/tasks.json`: tenor `[1.0,1.0,0.94,...,0.0]`, sop
`[1.0,1.0,0.94,...,0.0]`). Pitches 60/63/67/70 = C4 Eb4 G4 Bb4 = Cm7. Four named voices, four
independent per-voice curves, correct lanes (channel pressure and CC74, not `amp`/`cutoff`). ✔
**But** the solution hand-spells four absolute pitches and has **no `harm` lane at all**, so the
file's own comment "The voices are members of one chord, not four parallel patterns" is not
demonstrated by the artifact: nothing links `bass:C4` to a chord. `~1 ~3 ~5 ~7` over
`harm | i7 |` would have demonstrated it. As written, Filigree is doing exactly what it accuses
the rivals of — four hand-typed pitches.

### T5 — modal interchange mid-progression → **PASS on pitch classes, FAIL on voice leading**
```
bar12.00  IVd  maj  pcs[5,9,0]  guide[9,0]  voiced[48, 53, 57, 69]
```
`pcs[5,9,0]` = **F A C** = IV of C dorian. **Correct.** Three characters (`IVd`), matching
Ziffers' `ivd`.
**Defect:** `voiced[48,53,57,69]` = C3 F3 A3 **A4** — the top voice leaps
`60 → 69`, a **9-semitone jump**, under `mode: smooth`. Total movement bar1→bar2 = 2+0+1+**9** =
12, against **2** for the same slot in T1. And the substitution poisons the *next* chord too:
i9 is voiced `[48,51,62,70]` here versus `[50,51,58,60]` in T1 — an 11-semitone hole between
Eb3 and D4. So the one-letter edit that BAR.md calls the highest bar in the set produces a worse
voicing than the chord it replaced. Also `IVd` renders as a bare **triad** (3 pcs) while its
neighbours are 4- and 5-note chords, so the size clamp is inconsistent.

### T6 — one named gesture on 12 notes, one parameter changed on note 7 → **PASS**
```
60.000 0.667 70 90 -  bend[-0.70..+0.70×30]     <- note 7, depth 0.7st
all others            bend[-0.30..+0.30×19]
```
Exactly right: 12 notes, one named parameterised gesture, one local parameter override.
**Defect:** the shipped solution writes `!vibr` **twelve times**
(`0!vibr 1!vibr 2!vibr ... 11!vibr`) when SPEC §8 L254 offers `notes!gesture=vibr`, which I
verified works identically (`/tmp/min/t6.fil`: note 7 `bend[-0.69..+0.70]`, all others
`±0.30`). The showcase artifact costs **192 non-whitespace chars** where the language can do it
in **153**. Filigree's own flagship exhibit is 25% longer than Filigree needs.

**Also:** `explain`'s header prints `key=0 minor` / `key=6 minor` — a raw pitch-class integer in
the tool whose entire purpose (SPEC §11 L297) is the "did I mean that?" pass.

---

## 2. Blind head-to-head

Samples were written out as A/B in an order fixed by `random.seed(4)` before I judged; the
mapping is disclosed only in the "revealed" line under each task. Character counts are
non-whitespace, computed by me (`len(re.sub(r'\s','',s))`), not taken from `tasks.md`. For
Filigree I used the **tightest form I could get to compile**, not the shipped example, so the
candidate is judged at its best.

The 1.3× test from BAR.md P1(a): *"Filigree must not be more than 1.3× the shortest rival."*
Per BAR.md P1(c) a rival that cannot express the task forfeits (a) and (b), so the divisor is the
shortest rival that expresses the task **fully** — I report the unrestricted ratio too.

### T1
- **A** `zplay "w (ii+4 v+4 i+4 i+4)<lead>", key: :c, scale: :minor` — **49**
- **B** `@key C minor / voicing v{size:4} / stave t{harm!voicing=v|ii7b5|V7|i9|i9}` — **63**

(a) **chars → A.** 63/49 = **1.29** vs the strongest rival; but three rivals express T1 fully,
and the shortest is Alda at **39** (`piano: o3 d1/f/a-/>c <g/b/>d/f <c/e-/g/b- *2`), giving
63/39 = **1.62 → the 1.3× test FAILS on T1.** Strudel 40 → 1.58.
(b) **predict-the-sound → A.** `w (ii+4 v+4 i+4 i+4)` is one line and reads as "whole notes,
ii–V–i–i, sevenths". B costs a separate `voicing` definition and an option syntax
(`harm!voicing=v`) whose punctuation (`!`, `=`) carries no musical meaning, before you reach the
chords. B *is* better than A at telling you the key is real rather than implied.
(c) **diff cost to change one note's vibrato depth → B.** A has no vibrato: ∞.
*Revealed: A = REFERENCE (Ziffers), B = CANDIDATE.*
**Forced picks: (a) REFERENCE. (b) REFERENCE. (c) CANDIDATE.**

### T2
- **A** `@key C minor / stave t{harm|ii7b5|V7|i9 / notes|.|C5 Eb5 D5 D5|~3 / bend!range=4st||xxx>3}` — **75**
- **B** `play :c5; sleep 1; play :eb5; sleep 1 / s=play :d5,sustain: 1.8,note_slide: 0.5 / sleep 1.5 / control s,note: :eb5` — **92**

(a) **chars → A.** 75 vs 92 = **0.82×**. Passes. No rival expresses the harmonic target at all
(B types `:eb5` by hand), so per P1(c) every rival forfeits here.
(b) **predict-the-sound → A.** B's four lines are unrolled clock arithmetic: you must add
`sleep 1 + sleep 1 + sleep 1.5` to work out *when* the glide happens and read `sustain: 1.8`
against `note_slide: 0.5` to work out that it finishes early. A puts the melody and the bend on
two vertically aligned lines and the target is the single token `>3`. This is the clearest win
in the whole set. Caveat charged against A: `xxx>3` is 5 characters against a 4-slot `notes`
bar, and nothing warns (§4 below).
(c) **diff cost → A**, narrowly: in A you edit the glyph run; in B you edit `note_slide: 0.5`
(3 chars) but it is a *slide time*, not a depth.
*Revealed: A = CANDIDATE, B = REFERENCE (Sonic Pi).*
**Forced picks: (a) CANDIDATE. (b) CANDIDATE. (c) CANDIDATE.**

### T3
- **A** `s=play 60,sustain: 4,note_slide: 0.06 / sleep 1.4 / 6.times{|i| control s,note: 60+0.08*(i+1); sleep 0.13; control s,note: 60-0.08*(i+1); sleep 0.13}` — **129**
- **B** `gesture sw(rate: 6hz, depth: 0.35st, onset: 35%) = bend((wiggle(rate,depth)*ramp(0,1)) @ onset..100%) / stave t{notes|C4!sw - - -|}` — **114**

(a) **chars → B.** 114 vs 129 = **0.88×**. Passes. (Strudel is 58 but cannot gate the first 35%,
so it forfeits under P1(c) — and I confirmed Filigree's onset lands at exactly 35%.)
(b) **predict-the-sound → B.** `rate: 6hz, depth: 0.35st, onset: 35%` states all three task
parameters in the words of the task. A hides the onset in `sleep 1.4` (you must compute
1.4/4 = 35% yourself), the rate in `sleep 0.13` (you must compute 1/(2×0.13) ≈ 3.8 Hz — which is
*not* 6 Hz), and the depth in `0.08*(i+1)` semitones. Decisive.
(c) **diff cost → B.** `0.35st` → `0.5st`: 2 chars on a **named** parameter; A's `0.08` appears
twice and is entangled with the loop count.
*Revealed: A = REFERENCE (Sonic Pi), B = CANDIDATE.*
**Forced picks: (a) CANDIDATE. (b) CANDIDATE. (c) CANDIDATE.**

### T4
- **A** Filigree `voices | { bass: C4 - - - ; ten: … }` + 4 suffixed lanes — **139**
- **B** `stack(note("c4").midichan(2).miditouch(saw), note("eb4").midichan(3).miditouch(saw.range(1,0)), note("g4").midichan(4).ccn(74).ccv(sine), note("bb4").midichan(5).ccn(74).ccv(saw.mul(.6))).midi()` — **191**

(a) **chars → A.** 139 vs 191 = **0.73×**. Passes.
(b) **predict-the-sound → A.** The four glyph runs `___/^^^^` / `^^^^\___` / `__/^^^^^` /
`^^^^^\__` are drawn pictures of the four curves, one per line, vertically aligned; B requires
knowing that `saw` rises, that `saw.range(1,0)` falls (which its own docs do not show), and that
`midichan(2..5)` is manual MPE bookkeeping. A also names the voices; B's notes are anonymous.
(c) **diff cost → A.** Adding per-voice vibrato in A is `bend@alto | ~5 |` or `!gesture`; in B it
is a new `.midibend(...)` chain per pattern.
*Revealed: A = CANDIDATE, B = REFERENCE (Strudel).*
**Forced picks: (a) CANDIDATE. (b) CANDIDATE. (c) CANDIDATE.**

### T5
- **A** `@key C minor / voicing v{size:4} / stave t{harm!voicing=v|ii7b5|IVd|i9|i9}` — **64**
- **B** `zplay "w (ii+4 ivd+4 i+4 i+4)<lead>", key: :c, scale: :minor` — **51**

(a) **chars → B.** 64/51 = **1.25× — passes 1.3×**, but only because every other rival forfeits
(they can respell notes but not state the borrowing). Against the unrestricted shortest
(Strudel 40) the ratio is 1.60.
(b) **predict-the-sound → B.** Both encode the borrowing in one letter (`IVd` / `ivd`); B is one
line with the key in it, A needs a `voicing` definition and the `harm!voicing=v` option syntax.
Nothing in A's surface is easier to read than `w (ii+4 ivd+4 i+4 i+4)<lead>` — and A's
`IVd` produced the 9-semitone top-voice leap documented in §1, which B's `<lead>` explicitly
re-solves.
(c) **diff cost → A.** B: ∞, no expression exists.
*Revealed: A = CANDIDATE, B = REFERENCE (Ziffers).*
**Forced picks: (a) REFERENCE. (b) REFERENCE. (c) CANDIDATE.**

### T6
- **A** `define :vib do |p,d| / play p,sustain: 0.4,note_slide: 0.1 / 3.times{control note: p+d; sleep 0.06; control note: p-d; sleep 0.06} / end / 12.times{|i| vib 60+i,(i==6 ? 0.5 : 0.15); sleep 0.5}` — **157**
- **B** `@key C minor / gesture vibr(rate: 5.2hz, depth: 0.3st, onset: 30%) = bend(wiggle(rate,depth) @ onset..100%) / stave t{notes!gesture=vibr|0 1 2 3 4 5|6!vibr(depth: 0.7st) 7 8 9 10 11}` — **153**

(a) **chars → B**, by 4 characters: 153 vs 157 = **0.97×**. Passes — barely, and only against
the one rival that satisfies "named, parameterized gesture". Against Strudel's
`vibmod("0.3!6 0.7 0.3!5")` (58) the ratio is **2.64×**, and **against Filigree's own shipped
solution (192 chars) the ratio is 1.22× — the shipped exhibit is the weakest form of the
candidate's own syntax.**
(b) **predict-the-sound → B.** `notes!gesture=vibr | 0 1 2 3 4 5 | 6!vibr(depth: 0.7st) …`
says "same gesture on all of them, note 7 is wider" in one glance. A requires simulating a loop
and a ternary.
(c) **diff cost → B.** `0.7st` → `0.9st`: **1 character changed, 1 line**, and the changed thing
is spelled `depth:`, so it is greppable. A's `0.5` is 1 char too but sits inside
`(i==6 ? 0.5 : 0.15)`, where the note index is `6` and the note is the 7th — an off-by-one trap.
*Revealed: A = REFERENCE (Sonic Pi), B = CANDIDATE.*
**Forced picks: (a) CANDIDATE. (b) CANDIDATE. (c) CANDIDATE.**

### 1.3× character-ratio test — explicit result

| task | Filigree (tightest) | shortest rival that expresses it fully | ratio | 1.3× | shortest rival of any kind | ratio |
|---|---|---|---|---|---|---|
| T1 | 63 | Alda 39 | **1.62** | **FAIL** | Alda 39 | 1.62 |
| T2 | 75 | *(none — all forfeit)* Sonic Pi 92 | 0.82 | PASS | Alda 17 (cannot bend) | 4.41 |
| T3 | 114 | Sonic Pi 129 | 0.88 | PASS | Alda 19 (cannot) | 6.00 |
| T4 | 139 | Strudel 191 | 0.73 | PASS | Ziffers 53 (cannot) | 2.62 |
| T5 | 64 | Ziffers 51 | **1.25** | PASS | Strudel 40 | 1.60 |
| T6 | 153 | Sonic Pi 157 | 0.97 | PASS | Strudel 58 | 2.64 |

**5 of 6 pass; T1 fails.** As shipped in `examples/tasks.fil`, T6 is 192 chars (1.22× Sonic Pi)
and T1/T5 additionally under-articulate bar 4. The honest summary: **Filigree wins the
expression tasks on characters and loses both pure-harmony tasks to Ziffers/Alda/Strudel.** It
does not "beat Ziffers on the harmony tasks and Sonic Pi on the gesture tasks simultaneously"
(the criterion `refs/syntax/tasks.md` sets for itself in cross-task observation 3) — it beats
Sonic Pi and loses to Ziffers.

### Overall forced picks

| criterion | winner | deciding citation |
|---|---|---|
| **Concision** | **REFERENCE** | T1 63 vs 39 = 1.62× (fails BAR.md P1(a)); T5 64 vs Ziffers 51; shipped T6 192 vs Strudel 58. Two of six tasks lose on the metric BAR.md makes a hard threshold. |
| **Readability (predict the sound)** | **CANDIDATE** | 4 of 6 tasks. Decided by T3 (`onset: 35%` vs deriving 35% from `sleep 1.4`) and T4 (four aligned glyph pictures vs four `midichan` numbers). Lost T1/T5 to `w (ii+4 ivd+4 i+4 i+4)<lead>`. |
| **Diffability** | **CANDIDATE** | 6 of 6. `6!vibr(depth: 0.7st)` → 1 char on a named parameter, verified `bend[-0.69..+0.70]` vs `±0.30`. Four rivals score ∞. |
| **Expressive power** | **CANDIDATE** | Only system in the comparison that hit a *harmonic* bend target: T2 `>3` → `+1.00 st` on pitch 74 landing on pc 3 of `i9`, verified again in `/tmp/min/probe_gt.fil` where the same glyph correctly produced **0** semitones. No rival can name the target. |
| **Error quality** | **REFERENCE** | See §5: 6 of 8 messages are good, but the two highest-frequency beginner mistakes — misaligned lanes and a typo'd chord — produce **no diagnostic** and **a silently deleted bar** respectively, and SPEC §12 L299–301 promises the first of these explicitly. BAR.md P1 lists "error messages without line:col" as a fail condition; the worse failure here is messages that do not exist. |

---

## 3. Cold-read test — `examples/nocturne.fil`

Prediction written before running anything: `/tmp/coldread_prediction.md`. Nine numbered claims.
Then `explain examples/nocturne.fil`.

**Right:** the two-stave split (lead's `harm` is context only because it has a `notes` lane,
SPEC §3.2 L138; `pad` sounds the chords — confirmed, lead 9 notes / pad 16); all nine melody
pitches and octaves (66, 69, 71, 73, 69, 66, 73, 69, 68 = F#4 A4 B4 C#5 A4 F#4 C#5 A4 G#4,
including `~5` of `iv11` = pc 6 = F#); `timbre | 3333 |` = 0.33 → 0.44 → 0.56 → 0.67; the
`gesture bloom` interaction (bar 2's empty `timbre` bar lets bloom through — confirmed
`timbre[+0.35..+0.62]`, exactly bloom's numbers); `press!time=note` swelling every pad note.

**Wrong — four ergonomics defects, with the exact misleading token:**

1. **Token `_` (nocturne L27).** I predicted, and `explain` confirms, that `bend | ___/^^^ |`
   makes bar 1's melody sound **3 semitones flat** (`bend[-3.00..-3.00]` on pitch 66 → sounding
   Eb4) and then 3 semitones sharp (`bend[+3.00..+3.00]` on pitch 71 → sounding D5). I was right
   about the mechanism and wrong about the file: I assumed a curated example would not do this.
   It is the defect, not my misreading. `_` is drawn as a *baseline* — the visual language of
   `___/^^^` is "flat, then rise" — but §7 L192 defines `_` as **lane minimum**, so the flat part
   is maximum downward detune. A shape that looks like a tasteful contour destroys the tuning of
   the notes it sits over. Compare `press | /^^^\__ |` on the very next line, where `_` = 0
   pressure and is harmless. **Same glyph, benign on one lane and catastrophic on the one above
   it.**
2. **Token: the empty bend bar `|         |` (nocturne L27, bar 3).** SPEC §7 L200/L205 says an
   empty bar "writes no data". Under MIDI's hold-last-value semantics I predicted the stale
   −3.00 st from bar 2 would persist and bar 3 would sound a minor third flat. It does not: the
   renderer emits a `pitchwheel pitch=0` immediately before every note-on (seen in
   `/tmp/tasks.mid`, `t2_target`), so bar 3 is in tune. Correct behaviour, **undocumented** — the
   spec never says a note-on preamble resets unwritten lanes, and it is the difference between an
   in-tune and an out-of-tune bar.
3. **Token `>3` (nocturne L27, last bar).** I predicted a no-op, an error, or a wrap to bar 1.
   All wrong: `bend[-3.00..+2.99×32]` on pitch 68. I then had to build three probe staves
   (`/tmp/min/probe_noct.fil`) to find out what actually happened: with `bend!range=24st` and
   `| _____>3 |` the endpoint is **−3.00 st** — G#4 → F, pc 5, the third of V7alt. Correct. The
   `+2.99` I saw is the `/` glyph saturating the ±3 st range, not the target. So `__/\_>3`
   drags the note through the full range twice before resolving, and the printed maximum tells
   you nothing about where `>` went. Two undocumented facts fall out: `>` in the **final** bar
   silently falls back to the *current* chord (there is no next one), and the `explain` summary
   `bend[min..max]` **cannot show you the `>` endpoint** — the one number a user most wants to
   check about the language's headline feature.
4. **Token `/` at the start of a lane (nocturne L28).** I predicted `press | /^^^\__ |` starts at
   0. It starts at **0.50**: `explain` gives `press[+0.50..+1.00]` for note 1. §7 L195 defines
   `/` as "ramp from previous anchor to lane max" and there is no previous anchor at a bar start,
   so it silently begins at lane centre. A swell that starts half-open is a different
   articulation from one that starts closed.

Four wrong predictions out of nine, all four on the **expression** lanes — the part of the
language that is supposed to be self-evident from its picture. The harmony and note lanes I read
correctly on the first pass; that asymmetry is the finding.

---

## 4. Ambiguity hunt

BAR.md P1 lists "any ambiguity where two readings of the same line are both defensible" as a
**fail condition**. Seven, with line numbers in `docs/SPEC.md` unless stated.

**A1. A slot is a whitespace-separated token (L73) except in curve lanes, where it is a
character (L187).** `bend | ___/^^^ |` is one whitespace-delimited token by L73–74 and seven
anchors by L187. Both readings are literally supported by the document. Worse, the glyph is not a
character either: `>3` is two characters and one anchor, so `bend!range=4st | xxx>3 |`
(`examples/tasks.fil` L60) is 5 characters, 4 anchors, against a 4-slot `notes` bar — and I can
only know that by running it. This is the single most load-bearing rule in the language and it is
stated twice, incompatibly.

**A2. `-` means three different things and one of them is not what it looks like.** L146: in
`notes`, tie/extend. L123: in `harm`, sustain previous chord. **L193: in a curve lane, lane
centre — a value, not a hold.** So `press | -----^^ |` (nocturne L28) reads as "sustain, sustain,
sustain… then max" and means "sit at exactly 0.5 then jump to max". The glyph that *does* mean
hold is `x` (L199). Both readings of that line are defensible from the same document.

**A3. `_`, `^` and `~` are all overloaded across lane kinds with unrelated meanings.** L149:
`^0`/`_0` are octave shifts in `notes`. L192/L194: `_`/`^` are min/max in curve lanes. L152: `~3`
is the chord's third in `notes`; L196: `~5` is a wiggle of depth 5/9 in a curve lane. `~5` is a
legal, meaningful, and completely different token in two lanes of the same stave — and per §6
L172–175 both lanes can be `@lead`-suffixed and sit adjacent.

**A4. Three distinct kinds of "no data" and no statement of what sounds.** L200 (empty slot),
L205 (empty bar), L205–206 (absent lane). None of the three says what value is in force *during*
a note that overlaps the gap, which under MIDI is a musical question, not a bookkeeping one. My
cold read got bar 3 of the nocturne wrong on exactly this. Also L206's claim that an unspecified
lane "never fights the DAW's own defaults" is contradicted by the renderer, which writes
`pitchwheel pitch=0` before every note-on.

**A5. Four syntaxes for attaching a gesture, no rule for choosing.** L254–256: `3!cry`,
`notes!gesture=cry`, `voices!gesture@lead=cry`, and a bare `gesture cry` in the stave header,
plus L203's inline `name(args)` in a curve slot and §7's drawn glyphs as a fifth way to say the
same swell. The spec's only tie-break is L256 ("explicit lane glyphs always win"), which does not
order the other four. The consequence is measurable: the shipped `examples/tasks.fil` T6 picks
the most verbose of the five and costs **39 extra characters** (192 vs 153) in the language's own
showcase.

**A6. Harmony has three interchangeable spellings (L112–121) with no guidance,** and they
overlap: `iv`, `Fm`, and `{5 8 0}` are the same chord in C minor, as are `IVd` and `F`. The same
document says they are "all converted to the same internal `Chord`" — so the choice is pure
style, in a language whose pitch to a reader is that the text tells you the function. In
`examples/tasks.fil` T4 (L79) the author abandons the harmony layer entirely and types
`C4 Eb4 G4 Bb4`, in the very exhibit whose comment claims the voices are members of one chord.

**A7. Whitespace is the slot separator, so a single space changes pitch *and* rhythm silently.**
L148 permits negative degrees (`-2`) and L146 makes `-` a tie. Verified:
`notes | 0 -2 - 2 |` → C4, **Ab3** (pitch 56), tied, Eb4, in 1.0-beat slots; `notes | 0 - 2 - 2 |`
→ C4 tied, Eb4, tied, Eb4, in **0.8-beat** slots (`/tmp/min/a7.fil`, `/tmp/min/a7b.fil`). One
inserted space changed a pitch by 7 semitones and re-timed the whole bar into quintuplets, with
no diagnostic. "You never write a duration" (L69) means you also never *see* a duration, so this
class of typo is invisible on the page.

**A8 (bonus). Postfix note modifiers have no stated precedence or composition rule.** L157–161:
`token:v90`, `token%50`, `token'`, `token,`, `token?25`, `token!gesture`. Whether `0'?25`,
`0!cry%50` or `0%50:v90` is legal, and in what order they apply, is not specified — and `,` as
"soften" collides with `,` as the separator inside `voicing { … }` (L129) and `;`/`,` inside
`voices { … }` (L165–167).

---

## 5. Error-message quality

Eight realistic beginner mistakes, verbatim output. Files in `/tmp/min/err/`.

**1. Misaligned lanes** — `notes | 0 1 2 3 |` with `bend | ___/^ |` (5 anchors vs 4 slots):
```
/tmp/min/err/e1_misaligned.fil   120 bpm  4/4  key=0 minor  seed=0
stave 's'  (4 notes)
      0.000  1.000    60   90 -        bend[-2.00..-2.00×2]
```
**Verdict: FAIL, and a direct contradiction of the spec.** SPEC §12 L299–301 promises: "Lane
misalignment … is a **warning** … the lane is resampled and the warning names both slot counts."
No warning is emitted. I tried four variants to provoke it — `bend | ___ |` vs 4 notes,
`bend | _ _ _ |` (3 vs 4), `press | ^ ^ ^ ^ |` vs `notes | 0 1 2 |` (4 vs 3) — **none** warns,
while the beginner's first two notes are silently pitched 2 semitones flat. The only lane
diagnostic that does fire is a bar-*count* mismatch:
`/tmp/min/err/e1d.fil:4:3: warning: in stave 's', lane 'bend' has 1 bars but lane 'notes' has 2`.
The slot-count warning text exists in `src/filigree/parse.py:1426–1431` and is unreachable for
the case the spec uses as its own example. Given that lane alignment *is* the language's core
ergonomic idea (L67–68), this is the worst error-quality result in the set.

**2. Wrong glyph** — `bend | __?/^^^ |`:
```
/tmp/min/err/e2_glyph.fil:4:13: error: '?' is not a curve glyph
  at token: '?'
  hint: glyphs are '_' min, '-' center, '^' max, '/' ramp up, '\' ramp down, '0'-'9' level, '~' wiggle, 'x' hold, '>' harmonic target
```
**Verdict: PASS, best message in the set.** line:col, offending token, and the complete legal
alphabet inline — a beginner needs nothing else.

**3. Unknown chord** — `harm | ii7b5 | Vsus9alt13 | i9 |`:
```
  /tmp/min/err/e3_chord.fil:2:26: warning: unknown chord symbol 'Vsus9alt13' (expected e.g. i ii7 V7 iv11 bVI IV^7 vii0 viio7 V7alt V/ii iiid, or an absolute symbol like Cm9 / Ab^7 / F#7b13)
```
**Verdict: FAIL on severity, PASS on wording.** The wording is genuinely helpful. But it is a
**warning**, and the chord is **silently deleted**: `explain` then lists `bar 1.00` and
`bar 3.00` only, and bar 2 produces **no notes at all**. A one-character chord typo silently
removes a bar of music from the output while the compiler exits 0. That is the failure mode a
beginner is least equipped to notice. Cosmetic: the message is printed with two leading spaces
and interleaved with the report, unlike every other diagnostic.

**4. Missing brace** — `stave s {` never closed:
```
/tmp/min/err/e4_brace.fil:2:1: error: unclosed '{' in stave 's'
  at token: 'stave'
  hint: add the matching '}'
```
**Verdict: PASS.** Points at the opening `{`, which is the right place, and names the stave.

**5. Wrong lane name** — `pressure | /^^^\__ |`:
```
/tmp/min/err/e5_lane.fil:4:3: error: unknown statement 'pressure' in stave 's'
  at token: 'pressure'
  hint: did you mean 'press' or 'gesture'?
```
**Verdict: PASS.** Did-you-mean with the correct candidate.

**6. Bad unit** — `@grid 10hz`:
```
/tmp/min/err/e6_unit.fil:2:7: error: '@grid' expects milliseconds
  at token: '10hz'
  hint: e.g. '@grid 10ms'
```
**Verdict: PASS.** States the expected unit and shows a correct line.

**7. `>` on a non-bend lane** — `press | ___>3 |`:
```
/tmp/min/err/e7_gt.fil:5:14: error: '>' harmonic target is only valid on 'bend', not 'press'
  at token: '>'
  hint: move the '>' to a bend lane (SPEC §7)
```
**Verdict: PASS, and it cites the spec section.** Best-practice message.

**8. Unbalanced bracket** — `notes | [0 2 3 1 2 3 | 4 - - - | }`:
```
/tmp/min/err/e8_bracket.fil:2:19: error: unbalanced '[' in '[0 2 3 1 2 3 | 4 - - - | }'
  at token: '[0 2 3 1 2 3 | 4 - - - | }'
  hint: close it with ']'
```
**Verdict: PASS on content, MARGINAL on presentation.** The "at token" is the entire remainder of
the line including the closing brace, so the caret information is useless; and col 19 does not
point at the `[` (col 17) or at the bar line.

**Score: 6 clean passes, 2 failures.** Every message that exists has `file:line:col`, the token
and a suggestion — BAR.md P1's stated fail condition ("error messages without line:col") is not
triggered. The failures are of a different and worse kind: **the two mistakes a beginner is most
likely to make produce no error at all, and both corrupt the music silently** — misaligned lanes
detune notes, an unknown chord deletes a bar.

---

## 6. Defect list, severity-ordered

1. **`_` on a bend lane means maximum downward detune, and it is drawn as a baseline.** The
   language's showcase piece (`examples/nocturne.fil` L27) is audibly out of tune for three bars
   because of it: `bend[-3.00..-3.00]` on pitch 66, `bend[+3.00..+3.00]` on pitch 71. The whole
   pitch of "curves drawn as text" is that the picture is the sound; here the picture reads
   "resting" and means "a minor third flat". Ergonomically this is worse than a hand-typed
   number, because a wrong number looks wrong.
2. **The slot rule is specified twice, incompatibly (SPEC L73 vs L187), and the promised
   misalignment warning does not exist.** A 5-anchor bend bar over a 4-slot notes bar compiles
   silently and detunes notes (`/tmp/min/err/e1_misaligned.fil`), including in the shipped T2
   exhibit (`xxx>3`). Column alignment is the core idea and the compiler does not check it.
3. **A typo'd chord symbol is a warning and silently deletes a bar of music**
   (`/tmp/min/err/e3_chord.fil`: bar 2 absent from the harmony table, zero notes, exit 0).
4. **`explain` cannot show you where `>` went.** `bend[-3.00..+2.99×32]` for nocturne's
   `__/\_>3`: the printed maximum is the `/` glyph saturating, and the actual harmonic endpoint
   (−3.00 st → F, the third of V7alt) took three probe staves to establish. The verification tool
   omits the one number that verifies the flagship feature. Related: the header prints
   `key=6 minor` instead of `F# minor`.
5. **`mode: smooth` degrades badly on the modal-interchange task it is showcased with.** T5's
   `IVd` → `voiced[48,53,57,69]`, a **9-semitone** top-voice leap and total movement **12** where
   the unsubstituted T1 slot moved **2**; the following i9 comes out `[48,51,62,70]` with an
   11-semitone gap. `IVd` also renders as a bare triad among 4- and 5-note neighbours.
6. **Filigree loses the 1.3× character test on T1** (63 vs Alda 39 = 1.62×; vs Ziffers 49 =
   1.29×) and does not clear Ziffers on either harmony task. BAR.md P1(a) makes this a threshold,
   not a preference.
7. **The shipped exhibits are not written in the best available Filigree.** T6 costs 192 chars
   using `!vibr` twelve times where `notes!gesture=vibr` costs 153 and behaves identically
   (verified). T1/T5 use `-` for bar 4 and produce 3 attacks where the task asks for 4. T4 has no
   `harm` lane at all yet its comment claims the voices are chord members.
8. **One inserted space changes pitch by 7 semitones and re-times the bar into quintuplets**
   (`0 -2 - 2` vs `0 - 2 - 2`), with no diagnostic, in a language that deliberately never shows
   durations.
9. **Glyph overloading across lanes:** `-` = tie / sustain / *centre value*; `_` `^` = octave
   shift / min-max; `~5` = chord fifth / wiggle depth 5. All disambiguated only by the lane name
   at the left margin, which may be 60 columns away.
10. **`null` as the first sample of every windowed gesture** — 13 nulls in 400 samples of
    `examples/tasks.fil` in the documented playground JSON.
11. **Unknown lane options are silently ignored.** `harm!size=4` (`/tmp/min/t1c.fil`) compiles,
    warns nothing, and produces 5-voice chords — a beginner's plausible guess at the voicing
    syntax fails invisibly.
12. **T2's bend peak arrives ~45 ms early and 2.2 cents short in the SMF** (last pitchwheel
    `pitch=167` at tick 22980, note_off 23040, 1 st = 170.67 units).
13. **Undocumented behaviours a user must discover by experiment:** `>` in the final bar falls
    back to the current chord; a note-on resets unwritten lanes to 0; `/` at a bar start begins
    from lane centre; degrees above 8 (`10`, `11`) are legal though L148 documents `0…8`;
    leading-dot decimals (`.3st`) are rejected.

---

## The single largest gap

**The curve lane's glyphs are a picture of the wrong thing.** Filigree's entire ergonomic
argument is design-thesis point 2: "curves are drawn as text, column-aligned with the notes …
readable at a glance." Everything downstream of that claim fails on inspection:

- the picture and the sound disagree, because `_` looks like *rest* and means *−3 semitones*
  (nocturne L27, `bend[-3.00..-3.00]` on pitch 66);
- the alignment the picture depends on is unspecified (L73 vs L187) and unchecked (no warning
  for 5 anchors over 4 slots), so the columns can lie;
- the one thing the picture *cannot* draw is the feature the language was built for — `>3` is not
  a shape, it is a musical reference, and neither the glyph run nor `explain`'s
  `bend[min..max]` reveals where it lands;
- and on a cold read, the four things I got wrong out of nine were all on curve lanes, while the
  harmony and note lanes I read correctly first time.

That asymmetry is the verdict. The typed, named, parameterised half of the language — `gesture
vibr(rate:, depth:, onset:)`, `>3`, `IVd`, `voices`/`@voice` — genuinely beats every rival in
`refs/syntax/tasks.md` on readability, diffability and expressive power, and wins T2, T3, T4 and
T6 outright. The *drawn* half is the liability: it is where the ambiguities are (A1–A4), where
the missing diagnostics are (§5.1), where the shipped example is out of tune, and where a fresh
reader mispredicts the sound. Fixing the picture is not a syntax tweak — it means deciding
whether a curve lane's baseline is zero or minimum, whether an anchor is a character or a token,
and making `explain` print the resolved endpoint of every `>`. Until then the language's best
argument is its *typed* expression, not its drawn expression, and BAR.md P1 is being contested on
the weaker of the two.
