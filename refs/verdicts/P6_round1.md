# P6 — Playground UI — Round 1 verdict (independent critic, fresh context)

Judged against `refs/BAR.md` §P6. I did not read `NOTES_P6.md` or any builder note.
Artifacts only.

**Round status: VALID.** All captures painted fully; the header pill reads
`compiler live` in both review captures, i.e. the roll shown is the output of
`POST /api/compile`, not the bundled fixture.

---

## 0. Method / provenance of evidence

**Server.** `cd /home/user/workspace/filigree && PYTHONPATH=src python -m filigree.cli
serve --port 8791`, served from `web/`. `GET /` → 200.

**Browser.** Headless Chromium 1217 driven by Playwright (`/home/user/workspace/shot.py`,
`drive.py`, `p6_break/run_breaks.py`, `p6_break/probes.py`). Every capture is a real
paint of `http://localhost:8791/`.

**What I did to drive it.** Clicked into `#ta`, replaced the document with
`examples/blue_iron.fil`, dispatched `input`, clicked **compile**, waited for the
button to leave the `compiling…` state, then clicked **play** and waited 2.5 s before
shooting. Verified `#apiPill` text = `compiler live`, `#mNotes` = `51`, `#diag` =
"No warnings…", and 0 external network requests. Also clicked 60 points in the roll
to exercise hover/audition, pressed Tab 12× to walk focus order, and drove the
splitter and zoom controls.

**Candidate captures (mine, live compile):**
- `refs/ui/critic_p6_live_1440x900.png`
- `refs/ui/critic_p6_live_900x600.png`
- `refs/ui/critic_p6_1440x900.png` — first load, **default document, pill = `fixture`** (see D1)

**References.**
- Editor bar: `refs/ui/strudel_repl.png` (given).
- Piano roll: **I captured my own.** `pplx-tool screenshot_page` on
  <https://signal.vercel.app/> returns the marketing landing page, and
  <https://signal.vercel.app/edit> loads the real editor but with an **empty**
  project — useless for judging whether expression is readable *inside notes*. I
  therefore drove signal's own editor in Chromium and drew a 24-note two-voice
  passage with its pencil tool, then captured:
  - `refs/ui/signal_pianoroll.png` — signal.vercel.app/edit, 24 notes drawn, Velocity
    lane populated, 1440×900. **This is the roll reference used below.**
  - `refs/ui/signal_pianoroll_empty.png` — the as-loaded empty state, kept for the record.
  - MIDI import into signal (file input, and a synthetic `DataTransfer` drop of
    `refs/midi/Franz_Liszt__La_Campanella.mid`) does **not** work under automation —
    there is no `input[type=file]` in the DOM and the drop handler ignores synthetic
    `DragEvent`s. Drawing notes was the working path. Recorded here per BAR rule 5.

**Blind composites** (two captures stacked, unlabelled, order chosen by a seeded
shuffle; key written to `p6_break/blind_key.json` and only read after the picks):
- `refs/ui/critic_p6_blind_editor.png`
- `refs/ui/critic_p6_blind_roll.png`

Crops used for the pixel citations: `critic_p6_crop_topleft_720x60.png`,
`critic_p6_crop_ref_strudel_topleft.png`, `critic_p6_crop_roll_700x410.png`,
`critic_p6_crop_ref_signal_roll.png`.

---

## 1. Forced picks

Key after the fact: in `critic_p6_blind_editor.png` TOP = candidate, BOTTOM =
strudel. In `critic_p6_blind_roll.png` TOP = signal, BOTTOM = candidate.

### (a) Information density without clutter → **CANDIDATE**

Blind: the bottom pane of `critic_p6_blind_roll.png` puts source, harmony, roll,
diagnostics and a per-note inspector in one 1440×900 frame. The top pane spends its
entire lower half (y 365–560, 1440×195 px) on a **single** controller lane holding 24
identical blue sticks, and its `0–1340 × 90–360` grid region is 90 % empty
background. The candidate's `656–1356 × 90–690` roll region carries three staves,
eight chord cells, a bar ruler and per-note curves in the same area.

Against strudel (`critic_p6_blind_editor.png`): strudel's right half (x 790–1356,
full height) is a static welcome document, and its editor holds **one line of code**
at y 55–72. Candidate wins on density outright; it does not lose on clutter, because
the only genuinely wasted region is the inspector's `656–1356 × 700–848` (see D4).

### (b) Legibility of the code editor → **REFERENCE (strudel)**

Blind, `critic_p6_blind_editor.png`. Strudel's code line at `0–460 × 55–72` renders
at ~15 px with a ~6:1 body contrast and only four token colours; every glyph is
resolvable at 100 %. The candidate's editor at `0–655 × 60–720` runs 12 px/18 px
line-height (`style.css:23-24`) with **22 distinct token colours**
(`style.css:134-162`), several of which are below any usable threshold on `--bg1`:
`.t-bar` (the `|` bar separators that define every lane's columns) is **1.84:1**,
`.t-rest` 2.53:1, `.t-com` 2.60:1, the gutter line numbers 2.01:1. In the
`0–655 × 570–620` region the bar separators in the `bend`/`press`/`timbre` lanes are
effectively invisible, so the reader cannot see where a bar starts — in a
column-aligned language that is the one thing the editor must never lose. Strudel
wins.

### (c) Are per-note expression curves actually readable → **CANDIDATE**

Blind. In the top (signal) pane, `Pitch Bend` is a *tab* at `112–150 × 368–384`; the
visible lane at `60–950 × 390–560` is Velocity only, one stick per note-on, and
nothing at all is drawn inside the note rectangles at `60–950 × 90–290`. Per-note
expression is structurally absent: it lives in a channel-wide lane you must switch
to.

In the bottom (candidate) pane, `critic_p6_crop_roll_700x410.png` shows a bend
polyline drawn *through each note's own rectangle*: the wiggle at crop
`510–590 × 95–155` is unmistakably vibrato, the ramp at crop `150–175 × 155–200` is
unmistakably a scoop, and the green `bed` notes at crop `85–700 × 205–400` carry a
left-to-right press gradient inside the body. That is genuinely more information per
note than the reference can express. Candidate wins — with the qualification in D5
that the curves are not *contained*.

### (d) Does a stranger know what to do within 5 seconds → **REFERENCE (strudel)**

Blind, `critic_p6_blind_editor.png`. Strudel's `806–1160 × 200–220` region literally
reads "**1. hit play – 2. change something – 3. hit update**", three numbered links,
next to a labelled `play` control at `1085–1140 × 10–28`. Five seconds is enough.

The candidate's top-left `0–300 × 0–38` region gives a wordmark, `▶ play`, `■`, and
`compile ⌘⏎`. There is no first instruction anywhere on screen. The two hint strings
that exist — `⌘⏎ compile · tab indents` at `530–650 × 38–52` and
`hover or click a note in the roll` at `1030–1350 × 700–716` — are 10 px `--fg3`
text at **3.56:1**, right-aligned into pane headers where nobody looks first, and
`style.css:220` **deletes both of them** (`.ph-hint{display:none}`) below 1180 px, so
the 900×600 capture has zero instructions on screen. Reference wins.

**Score: candidate 2, reference 2.** Under BAR rule 6 (ratchet) that is not a
head-to-head win; the two losses are (b) legibility and (d) first-five-seconds, and
both are cheap to fix.

---

## 2. Code read (critical)

### 2.1 Monospace alignment in the highlight overlay — **BROKEN, cumulatively**

`editor.js:5-7` states the contract: "Nothing in the overlay may change advance
width — no bold on glyph tokens, no padding, no transforms — or the lanes stop
lining up with the notes above them."

Two violations, one cosmetic and one real.

**Cosmetic-but-declared:** `style.css:148` `.t-chord{font-weight:500}` and
`style.css:157` `.t-tgt{font-weight:600}`. `.t-tgt` is applied by `editor.js:49-52`
to `>3` resolve targets **inside curve lanes** — precisely the load-bearing glyph
region. Measured on this Chromium the synthetic-bold advance delta is 0.06 px over a
38-char line (`p6_break/probes.py`, `align_probe`: styled 260.148 px vs unstyled
260.086 px), so it does not break here — but it is one font fallback away from doing
so, and it contradicts the file's own stated invariant.

**Real and measurable:** `tokCurve` (`editor.js:43-68`) emits **one `<span>` per
character** for glyph lanes. Each span's advance is rounded independently, and the
error accumulates. Measured `#hl.scrollWidth − #ta.scrollWidth` for a single lane
line as it grows (`p6_break/probes.py`, drift table):

| line length (chars) | single-span comment line | `bend` lane (span/char) | `harm` lane (`.t-chord`) |
|---|---|---|---|
| 100  | 14 px | 15 px | 14 px |
| 500  | 14 px | 19 px | 17 px |
| 1000 | 14 px | 24 px | 21 px |
| 2000 | 14 px | 34 px | 28 px |
| 4000 | 14 px | **53 px** | 40 px |

The 14 px is a constant padding/scrollbar baseline (it is *flat* for a one-span
line — the mechanism is proven to be span fragmentation, not padding). Net drift on
the glyph lane is **≈0.0098 px/char ≈ 1 px per 100 characters**, unbounded. On the
shipped 8-bar fixture (~60-char lanes) it is 0.6 px and invisible — which is why it
looks perfect in `critic_p6_live_1440x900.png`. On the 400-bar document
(`critic_p6_break_bars400_1440x900.png`, 4009-char `notes` line) the coloured overlay
sits **53 px ≈ 7.4 characters** to the right of the characters the user is actually
typing. For a language whose premise is "read DOWN a column", that is a defect in the
one place the code says it must not be.

### 2.2 External network URLs — **none. Pass.**

`grep -nEo "https?://…" web/*.js web/*.css web/index.html` → empty. Only three
`fetch()` calls exist, all same-origin: `app.js:632` (`/api/compile`), `app.js:738-739`
(`fixtures/source.fil`, `fixtures/score.json`). No webfont, no CDN, no analytics.
`style.css:2` claims this and the claim holds. The only console error on every load
is a 404 for `/favicon.ico` (no `<link rel=icon>` in `index.html`) — cosmetic.

### 2.3 Blocking main-thread work on large scores — **confirmed, quantified**

- **Editor.** `Editor.prototype.render` (`editor.js:225-229`) re-highlights the
  *entire* document and `renderGutter` (`editor.js:236-245`) rebuilds *every* line-number
  `<div>` via `innerHTML` on **every `input` event**. The cache field `this._nLines`
  is initialised at `editor.js:204` and then never read or written again — the
  intended optimisation is dead code. Measured cost per keystroke:
  **11.8 ms on the 8-bar fixture, 61.3 ms on the 400-bar document** (10 synthetic
  input events, `p6_break` timing run). 61 ms/keystroke is ~16 fps typing.
- **Roll.** `renderRoll` (`app.js:304-377`) redraws the whole score at full width with
  **no viewport culling**. Worst offender is `app.js:346-361`: for every chord it
  loops every visible pitch row and strokes a dashed guide-tone line across the full
  canvas width. At 400 bars × 1 chord/bar × ~30 rows that is ~12 000 dashed strokes
  per redraw; `drawNote` (`app.js:390-401`) additionally issues **one `fillRect` per
  horizontal pixel** of every note. Every zoom-slider tick calls `layout()` →
  `renderRoll()` (`app.js:764-765`), so dragging zoom on a large score re-runs all of it.
- **Compile is synchronous from the user's point of view.** `compile()` (`app.js:657`)
  sets `compiling…` and blocks the UI on one round trip: measured 2.06 s for 400 bars,
  1.18 s for the 200-beat note. No spinner beyond the button text, no cancel.

### 2.4 Piano-roll redraw efficiency — **inefficient**

`frame()` (`app.js:718-732`) calls `renderOverlay()` **on every animation frame,
unconditionally**, whether or not anything is playing, hovered or selected.
`renderOverlay` (`app.js:460-466`) `clearRect`s the entire `#cOver` canvas, which is
sized to the whole score. Measured backing stores on the 400-bar document at
`devicePixelRatio = 2` (`p6_break/probes.py`, `dpr2`):
`cRoll 32064×1008`, `cOver 32064×1120`, `cRibbon 32064×76` → **≈283 MB of canvas
backing store**, of which the 144 MB `#cOver` is cleared 60×/s while the page sits
idle. The canvas is *not* blank (I checked `getImageData`, 90 000/90 000 non-zero
pixels in the first 300×300), so it does not exceed Chromium's limits — it is simply
gratuitous. `#cRoll`, `#cRibbon`, `#cRuler` are only redrawn on `layout()`, which is
correct; the fault is confined to the overlay.

### 2.5 WebAudio voice-pool leak — **confirmed, two distinct leaks**

- **No node is ever disconnected.** `grep -n "disconnect\|close()" web/synth.js
  web/app.js` → **zero hits**. Each `_voice()` call builds 7 nodes
  (`mix`, `filt`, `pre`, `shaper`, `post`, `env`, `pan`; `synth.js:254-267`) and
  connects `pan → this.bus` (`synth.js:270`). Oscillators self-release on `stop()`
  (`synth.js:296`), but the 7-node chain remains wired into a bus that reaches
  `ctx.destination`, for the lifetime of the page. `this.loop = true`
  (`synth.js:86`) means playback never ends, so this grows without bound: one
  press of ▶ on the 400-bar score schedules 1600 notes = ~11 200 orphaned nodes per
  pass, forever.
- **`_live` is never reaped unless playing.** The only reaper is inside `_tick()`,
  guarded by `if (!this.playing) return;` (`synth.js:341-342`, reaper at
  `synth.js:356-361`). `audition()` (`synth.js:408-413`) pushes into `_live` and is
  called on every roll click (`app.js:795`). Measured via the page's own
  `window.__dbgVoices()`: `live: 0` at load → **`live: 10` after 60 roll clicks →
  still `live: 10` after 4 s idle**. The array never shrinks while stopped.

### 2.6 Accessibility — **fails the basics**

- **Keyboard trap (WCAG 2.1.2).** `editor.js:282-283` calls `e.preventDefault()` on
  `Tab` *unconditionally*, with no Escape-then-Tab affordance. Measured tab order
  from `document.body`: `#btnPlay → #btnStop → #btnCompile → #vol → #ta → #ta → #ta
  → #ta → #ta → #ta → #ta → #ta` (12 presses). Once focus enters the editor it
  **never leaves**. Everything downstream of `#ta` in the DOM — the zoom slider, the
  rows slider, the `curves` checkbox, all mute/solo controls, all diagnostics rows —
  is permanently unreachable by keyboard.
- **No focus indicator anywhere (WCAG 2.4.7).** Enumerating every CSS rule at
  runtime returns **0 rules matching `:focus`**. `style.css:125` sets
  `#ta{outline:none}` and `style.css:70` sets `input[type=range]{outline:none}`,
  actively removing the UA ring without replacement.
- **Interactive elements are non-semantic `<span>`s.** `app.js:118-131` builds
  mute/solo as `<span class="mm">M</span>` / `<span class="ss">S</span>` with
  `.onclick` and no `role`, `tabindex` or pressed state; `app.js:176-183` builds
  diagnostics rows as clickable `<div>`s. None are focusable, none announce.
- **The whole roll is an unlabelled canvas.** Four `<canvas>` elements
  (`index.html:82-89`) with no `role="img"`, no `aria-label`, no text alternative
  and no keyboard path to a note; note selection is mouse-only
  (`app.js:771-796`). `Escape` clears selection (`app.js:812`) but nothing can create
  one from the keyboard.
- **Contrast.** Computed against the actual backgrounds: `.t-bar` **1.84:1**,
  gutter numbers **2.01:1**, inspector axis labels (`app.js:544-545`, `#39424e` on
  `#0a0c0f`) **1.92:1**, inspector empty-state text (`app.js:513`, `#2b333d`)
  **1.53:1**, ruler beat numbers **2.35:1**, `.t-rest` 2.53:1, `.t-com` 2.60:1,
  `.t-tie` 3.25:1, `--fg3` hints 3.56:1. Nine values below 3:1, i.e. below even the
  non-text minimum. Body text (14.53:1) and the pill (9.55:1) are fine.
- Only one `:hover` cue distinguishes clickable diagnostics rows; `#gutter`,
  `#hl` are correctly `aria-hidden` (`index.html:52,54`) and `#ta` has an
  `aria-label` — those two things are right.

### 2.7 Compiler-error contract — **mismatched; this is D1 below**

`server.py:34-58` (`_diag`) returns `{"ok":false,"error":{message,line,col,token,
suggestion,kind}}` — an **object** under the key `error`. `app.js:661` tests
`j.errors` — an **array** under a different key. The two halves of the playground do
not agree, so no compiler error can ever be displayed.

---

## 3. Break tests

Inputs in `/home/user/workspace/p6_break/`. Server-side compile of each input was
verified from the CLI first, so any UI failure is a UI failure.

| # | input | screenshot | result |
|---|---|---|---|
| 1 | `invalid.fil` (bad chord `Qz9`, bad token `@root+5`, junk `@@@`, unclosed brace) | `critic_p6_break_invalid_1440x900.png` | **Broken.** See below. |
| 2 | `empty.fil` (0 bytes) | `critic_p6_break_empty_1440x900.png` | Survives, degenerate. |
| 3 | `b400.fil` (400 bars, 1600 notes, 1600 beats) | `critic_p6_break_bars400_1440x900.png` | Survives, unusable. |
| 4 | `s40.fil` (40 staves, 520 notes) | `critic_p6_break_staves40_1440x900.png` | **Broken.** |
| 5 | `long200.fil` (one note, 200 beats, 17 002 bend points) | `critic_p6_break_note200_1440x900.png` | Survives, mislabelled. |
| 6 | narrow window, 420×800 | `critic_p6_break_narrow_420x800.png` | **Broken.** |
| 7 | 400 bars at `devicePixelRatio = 2` | `critic_p6_break_dpr2_400bars_1440x900.png` | Survives; 283 MB canvas. |

**1 — invalid source (worst result of the whole review).** CLI (`filigree json`):
`/tmp/playground.fil:4:11: error: 'Qz9' is not a chord symbol` / `at token: 'Qz9'` /
`hint: roman numerals (i ii III iv V), absolute symbols (Cm9, Ab^7) or a pitch set…`. The UI instead
shows, in `0–655 × 750–785`:

> `NOTE  —  compiler backend unreachable (response is not a Score.to_json() object) — showing the bundled fixture, which is a full Score.to_json() payload`

and the pill at `1290–1350 × 10–26` flips from `compiler live` to amber `fixture`.
Consequences visible in the capture:
- the compiler's `line:col`, token and suggestion are **discarded entirely**
  (`app.js:661` reads `j.errors`, `server.py:38` sends `j.error`); the diagnostics
  chip reads `3`, none of them the actual error;
- the error is **misattributed to the network** when the backend answered HTTP 200
  in 40 ms;
- the roll at `656–1356 × 90–690` reverts to the **unrelated 8-bar fixture, 112
  notes**, while the editor at `0–655 × 60–200` shows the user's 7-line document —
  code and picture now disagree with nothing saying so;
- the three diagnostics rows are the *fixture's* warnings at lines **31, 39, 47** of a
  document that has **7 lines** (gutter at `0–36 × 60–180` stops at 7). Clicking them
  calls `ed.gotoLine(31)` on a 7-line buffer.

This is the P1 fail condition ("error messages without line:col") reproduced inside
the P6 artifact.

**2 — empty document.** No crash. `#cRoll` collapses to 32×522 px; the roll area
`656–1356 × 60–690` is empty dark grey with a `bar 1` ruler tick and nothing else;
diagnostics say "No warnings. Harmony, lanes and gestures resolved cleanly." for a
document with no content, which is a lie of omission. `#mNotes` = 0. Tolerable, but
there is no empty-state affordance — no "paste a score", no example picker.

**3 — 400 bars.** Compiles (2.06 s). Renders bars **1–18 of 400**; the remaining 382
bars are reachable only through `#rollScroll`'s 9 px `#242c36` scrollbar
(`style.css:129-131`), which is invisible in the capture. `autofit`
(`app.js:592-596`) clamps `ppb ≥ 10`, so *fit-to-window is impossible by
construction* for any score over ~130 beats: the zoom slider bottoms out at 8
(`index.html:78`) and there is no minimap or overview. Nothing on screen says "you
are seeing 4.5 % of this score". Typing in the editor drops to 61 ms/keystroke.

**4 — 40 staves.** Two hard failures in one frame:
- The stave legend at `750–1356 × 36–56` shows **s0…s6 only**. `.staves` is
  `display:flex` with `gap:5px` and **no wrap, no overflow, no scroll**
  (`style.css:189`), so 33 staves' mute/solo controls are permanently unreachable,
  and the overflow shoves the **`zoom`, `rows` and `curves` controls completely off
  the right edge** — the pane header's own controls are gone.
- `HUES` has 5 entries and `staveHue(i) = HUES[i % 5]` (`app.js:22, 68`), so 40
  staves share 5 colours, 8 per colour. Combined with the per-stave register bands
  (`app.js:324-343`) drawn on top of each other, the roll at `700–1356 × 275–415`
  collapses into a single flat mauve slab with indistinguishable pink notes. Stave
  identity — the only thing the colour encodes — is destroyed.

**5 — one 200-beat note.** Compiles (1.18 s), 17 002 bend points. The note draws as a
2000 px bar at `700–1356 × 336–352`, and its vibrato is drawn **outside its own
rectangle**, sweeping `y 310–365` across the `Db`–`Bb` rows that belong to other
pitches (`app.js:414-419`: the clip box is `h + span*1.2`, i.e. ±1.14 rows beyond the
note). It is then *silently truncated* by that clip, so the flattened peaks
misrepresent the real excursion. Worse, the roll is sampled at
`steps = min(260, ceil(w*1.5))` (`app.js:428`) — 260 samples for 17 002 points. And
both the inspector axis (`app.js:545`: `+2st` / `0` / `-2st`) and the two on-screen
legends (`index.html:100,104`) hard-code **±2 st** while this document — and the
shipped fixture, `@bend-range 48st` — are nothing of the kind. The single most
important number in the expression readout is a literal.

**6 — 420×800.** `#left{min-width:320px}` (`style.css:82`) plus a 4 px splitter with
no responsive stacking, and `body{overflow:hidden}` (`style.css:33`), so everything
past x≈420 is **permanently unreachable**: the meter readouts are cut mid-label
(`340–420 × 8–30` shows `1.1.0 8`/`BAR BP`), and the volume slider **and the
compiler-status pill are entirely off-screen** — the user cannot tell whether they
are looking at a live compile or the fixture. The right pane is reduced to ~96 px of
visible roll; the stave legend reads `lead M`; zoom/rows/curves are gone; the
inspector's meta line is cut to "no note selected —". There is no breakpoint below
1180 px (`style.css:217`), and the one that exists *removes* the only instructions.

**7 — 400 bars at dpr 2.** No crash, canvas limits not exceeded, but
`cRoll 32064×1008` + `cOver 32064×1120` + `cRibbon 32064×76` ≈ **283 MB** of backing
store, with the 144 MB overlay cleared every frame (see 2.4).

---

## 4. Sound judgement (`synth.js`)

**Do bend / pressure / timbre really reach the audio graph per voice? — Yes, all
three, per voice.** This is the strongest part of the build.

- **bend →** sampled per note into a cents array (`synth.js:214, 222-223`) and
  applied to **every** oscillator of the unison stack via
  `o.detune.setValueCurveAtTime(cents, when, dur)` (`synth.js:288`), with a
  `linearRampToValueAtTime` fallback (`synth.js:290-293`). Genuinely per-voice pitch.
- **press →** three destinations: amplitude (`synth.js:232`
  `body = 0.3 + 0.7*press[i]` into `env.gain` via `curveOn` at `synth.js:310`),
  filter cutoff (`synth.js:244`, applied `synth.js:311`), and drive into the
  saturator (`synth.js:251`, applied `synth.js:312`).
- **timbre →** filter cutoff (`synth.js:244`, exponent 1.7), resonance
  (`synth.js:257` `filt.Q = 3.1 + 3.4*timb[0]`) and drive (`synth.js:251`).
- Curve interpolation mirrors `ir.Curve.value_at` (`synth.js:19-33`) — same binary
  search, same clamping at the ends, so the ear and the piano roll agree.
- Per-note stereo spread keyed to pitch (`synth.js:267`) and per-stave pan
  (`synth.js:178`) — a nice touch.

**What would sound obviously wrong:**

1. **Voices never released (worst).** No `disconnect()` anywhere; `loop = true`
   (`synth.js:86`). See 2.5. Audible consequence on a long session: rising CPU, then
   glitching, then dropouts — not a wrong note, but a synth that degrades.
2. **Stop can fail to stop.** `stopVoices` (`synth.js:380-392`) wraps
   `cancelScheduledValues` **and** the `osc.stop()` loop in a single `try`
   (`synth.js:385-389`). Calling `cancelScheduledValues` in the middle of an active
   `setValueCurveAtTime` is the classic throw case; if it throws, the `for` loop that
   stops the oscillators is **skipped**, and those voices ring on to their originally
   scheduled `when + dur + rel + 0.05` (`synth.js:296`). Split the try, or stop the
   oscillators first.
3. **Long notes are control-rate aliased.** `N = max(24, min(220, round(dur*140)))`
   (`synth.js:213`) caps the control curve at **220 points for the whole note**. Above
   ~1.6 s that is under 140 pts/s; a 10 s note gets 22 pts/s, and the 200-beat test
   note (100 s at 120 bpm) gets 2.2 pts/s for a curve that has 17 002 points. Any
   vibrato faster than ~1 Hz on a long note aliases into a slow warble. The visible
   `~5.2hz`/`6.2hz` vibratos in `examples/` are safe only because those notes are short.
4. **Note-off is a `setTargetAtTime`, not a ramp to zero.** `synth.js:316` starts an
   exponential approach with `τ = rel*0.34` at `tEnd`, while the oscillators are hard
   `stop()`ped at `when + dur + rel + 0.05` (`synth.js:296`) — i.e. ~2.9 τ later, so
   the envelope is still at ~5 % of peak when the oscillator is cut. That is a small
   but real click on every note. `stopVoices` is worse: `τ = 0.015` with
   `osc.stop(t+0.12)` is 8 τ, fine, *if* the try didn't throw first (see 2).
5. **The floor is a DC-free constant, so no denormal/DC problem.** `amp[i] += 1e-5`
   (`synth.js:236`) is far above denormal range, and the saturator is odd-symmetric
   (`tanh`, `synth.js:72`) so a zero input maps to zero output — no DC offset. The
   even 1024-point curve straddles zero symmetrically; interpolation at 0 gives ~0.
   Clean.
6. **Attack has a real ramp from ~0** (`synth.js:231`), so no onset click. Good.
7. **The "limiter" is not one.** `ratio 4`, `knee 12`, `threshold −10 dB`
   (`synth.js:107-112`) with `release 0.18` will pump audibly on dense chords rather
   than limit. Cosmetic.
8. **Loop restart overlaps.** On wrap (`synth.js:364-372`) `startBeat`/`_qi` reset
   without `stopVoices()`, so the tail of bar N rings over bar 1. Arguably intended.
9. **Notes can be silently dropped.** `_tick` skips any note whose `when` is already
   in the past (`synth.js:352`) rather than clamping it to `currentTime`; on a slow
   first tick with a large score, the first notes simply never sound.

---

## 5. Defects, severity-ordered

| # | Sev | Defect | Evidence |
|---|---|---|---|
| **D1** | **Critical** | Compiler errors can never be shown. Server sends `{error:{…}}` (`server.py:38`), client reads `j.errors` (`app.js:661`), so every syntax error becomes `setApi(false)` + "compiler backend unreachable" + a silent revert to the bundled fixture, with the fixture's warnings displayed against line numbers that don't exist in the user's document. Line/col/token/suggestion all discarded. | `critic_p6_break_invalid_1440x900.png` (`0–655 × 750–850`); `app.js:657-682`; `server.py:34-58` |
| **D2** | **Critical** | The playground's own default document does not compile. `POST /api/compile` on `web/fixtures/source.fil` returns `{"message":"unknown anchor '@root+5'","line":58,"col":43,"suggestion":"did you mean 'root'?"}`, so a first-time visitor lands on the amber `fixture` pill (D1 path) and is told the backend is unreachable on a correctly running server. | `critic_p6_1440x900.png` pill at `1290–1350 × 10–26`; `web/fixtures/source.fil:58`; POST to `/api/compile` |
| **D3** | High | Keyboard trap + no focus indicators. `Tab` is unconditionally swallowed (`editor.js:282`); measured focus order dead-ends on `#ta` for 8 consecutive presses. **0** `:focus` rules exist; `outline:none` on `#ta` and all sliders. Mute/solo/diag rows are non-semantic `<span>`/`<div>` with no `tabindex`. | `probes.py` `tab_order`, `focus_css`; `editor.js:282-283`; `style.css:70,125`; `app.js:118-131,176-183` |
| **D4** | High | Overlay drifts from the textarea at ~1 px per 100 characters because `tokCurve` emits one `<span>` per character (`editor.js:43-68`); 53 px ≈ 7.4 characters at a 4000-char lane. Also violates the file's own no-bold rule (`style.css:148,157` vs `editor.js:5-7`). | drift table in 2.1; `probes.py` |
| **D5** | High | 40 staves destroys the header and the roll: `.staves` never wraps or scrolls (`style.css:189`) so 33 staves' M/S **and** the zoom/rows/curves controls are pushed off-screen; only 5 hues exist for 40 staves (`app.js:22,68`). | `critic_p6_break_staves40_1440x900.png` (`750–1356 × 36–56`; `700–1356 × 275–415`) |
| **D6** | High | No usable layout below ~1180 px. `#left{min-width:320px}` + `body{overflow:hidden}` clip the volume control and the compile-status pill off-screen at 420 px with no way to scroll to them; the sole breakpoint *removes* the only on-screen instructions (`style.css:220`). | `critic_p6_break_narrow_420x800.png`; `style.css:33,82,217-225` |
| **D7** | High | WebAudio leak: zero `disconnect()`/`close()` in the codebase; `_live` is only reaped while `playing` (`synth.js:341,356`). Measured `live: 10` after 60 roll clicks, unchanged after 4 s idle. With `loop=true`, one ▶ on a 400-bar score orphans ~11 200 nodes per pass. | `probes.py` `voice_leak`; `synth.js:86,254-270,341-361,408-413` |
| **D8** | Medium | Typing on a large score is 61.3 ms/keystroke (vs 11.8 ms on the fixture): full re-highlight + full gutter `innerHTML` rebuild per input, with the `_nLines` cache dead (`editor.js:204,225-245`). | timing run |
| **D9** | Medium | Contrast: nine token/label colours below 3:1, including the `|` bar separators at **1.84:1** — the glyphs that define lane columns — plus 2.01:1 gutter numbers and a 1.53:1 inspector empty state. | computed ratios in 2.6; `style.css:134-162`; `app.js:513,544-545` |
| **D10** | Medium | Bend readouts are hard-coded to ±2 st (`app.js:545`, `index.html:100,104`) and ignore `@bend-range`, which is `48st` in the shipped fixture. The roll's own bend curve is clipped to ±1.14 rows (`app.js:414-419`) so large excursions are silently flattened, and is sampled at ≤260 steps regardless of curve size (`app.js:428`). | `critic_p6_break_note200_1440x900.png` (`700–1356 × 300–370`) |
| **D11** | Medium | Long scores cannot be fitted or navigated: `autofit` clamps `ppb ≥ 10` (`app.js:594`), slider floor 8, no minimap, no "18 of 400 bars" indicator, 9 px near-invisible scrollbar. 400 bars shows 4.5 % of the score with no cue. | `critic_p6_break_bars400_1440x900.png` |
| **D12** | Medium | Stop can leave voices ringing: `cancelScheduledValues` and the `osc.stop()` loop share one `try` (`synth.js:385-389`). Long notes are control-rate aliased at ≤220 points (`synth.js:213`). Small release click (`synth.js:296` vs `316`). | 4.2–4.4 |
| **D13** | Low | `renderOverlay()` runs every rAF while idle over a whole-score canvas (144 MB at dpr 2, 400 bars); ~283 MB total backing store. | `app.js:460-466,718-732`; `probes.py` `dpr2` |
| **D14** | Low | Roll is a bare unlabelled canvas: no `role`/`aria-label`, no text alternative, no keyboard path to select a note (`index.html:82-89`, `app.js:771-796`). | 2.6 |
| **D15** | Low | Inspector reserves a fixed 136 px (`style.css:206`) that reads "no note selected" until you hover — 23 % of viewport height at 900×600, and it is the only place expression numbers appear. Also: `favicon.ico` 404 on every load; splitter drag doesn't reflow the roll until `mouseup` (`app.js:817-825`); `setInterval(…, 400)` rewrites the legend forever (`app.js:828-831`). | `critic_p6_live_900x600.png` (`656–900 × 440–600`) |

---

## 6. The single largest gap

**The playground cannot show you a compiler error, and it lies about why.**

Everything else is a matter of degree; this one inverts the product. Filigree's whole
pitch is a *text* language, and the P1 bar explicitly fails "error messages without
line:col". The compiler already produces exactly the right thing —
`playground.fil:4:11: error: 'Qz9' is not a chord symbol`, with a token and a
suggestion — and the playground throws it away because two files disagree on one key
name (`error` vs `errors`, `server.py:38` vs `app.js:661`). What the user sees instead
is an amber `fixture` pill, "compiler backend unreachable" on a backend that answered
in 40 ms, an unrelated 8-bar score in the roll that has nothing to do with the code on
the left, and three phantom warnings pointing at lines 31/39/47 of a seven-line
document.

Its severity is doubled by D2: `web/fixtures/source.fil` **does not itself compile**
(`unknown anchor '@root+5'`, 58:43), so this is not an edge case reached by a curious
user typing something wrong — it is the **first screen every visitor sees**. The
demo's own demo file trips the demo's worst bug, and the resulting message blames the
user's network. Until a compiler error renders with its line, column and caret in the
gutter, the "legibility of the code editor" and "a stranger knows what to do in 5
seconds" losses in §1 cannot be recovered, because the editor's most important job —
telling you what you got wrong and where — is not wired up at all.

---

## 7. Sources

- `refs/BAR.md` §P6 (the bar; on disk)
- strudel.cc REPL — <https://strudel.cc/> (reference capture `refs/ui/strudel_repl.png`, supplied)
- signal, open-source web MIDI editor — <https://signal.vercel.app/edit> (reference capture
  `refs/ui/signal_pianoroll.png`, taken by me for this round; project source
  <https://github.com/ryohey/signal>)
- WCAG 2.1 SC 2.1.2 No Keyboard Trap — <https://www.w3.org/WAI/WCAG21/Understanding/no-keyboard-trap.html>
- WCAG 2.1 SC 2.4.7 Focus Visible — <https://www.w3.org/WAI/WCAG21/Understanding/focus-visible.html>
- WCAG 2.1 SC 1.4.3 Contrast (Minimum) — <https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html>
- Web Audio API, `AudioParam.setValueCurveAtTime` and `cancelScheduledValues` —
  <https://www.w3.org/TR/webaudio/#dom-audioparam-setvaluecurveattime>
