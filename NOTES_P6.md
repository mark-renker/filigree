# NOTES_P6 — browser playground (`web/**`)

Zero-build static app. No npm, no bundler, no CDN, no runtime network except the
optional compile POST. Open `web/index.html` over any static server.

## Files

| file | role |
|---|---|
| `web/index.html` | shell: transport + meters, editor pane, diagnostics, chord ribbon / ruler / roll, note inspector |
| `web/style.css` | dark theme, CSS vars, syntax-token colours, responsive rules for 900px-wide review captures |
| `web/editor.js` | `window.FiligreeEditor` — textarea + overlay highlighter, lane-aware tokenizer |
| `web/synth.js` | `window.FiligreeSynth` — MPE-aware WebAudio voice pool, `window.filigreeCurveValueAt` |
| `web/app.js` | state, canvas renderers, hit-testing, compile/fallback plumbing |
| `web/fixtures/score.json` | hand-authored `ir.Score.to_json()` payload (8 bars, 3 staves, 112 notes, 6.8k curve points) |
| `web/fixtures/source.fil` | the Filigree source that would produce it |
| `web/fixtures/make_fixture.py` | generator; imports the frozen `filigree.ir` and dumps `to_json()` |
| `web/tools/shot.js` | dev-only Playwright capture (not shipped; tests skip `web/tools/`) |
| `tests/test_web.py` | 35 tests: IR round-trip, required files, no external URLs, fixture musicality, lane alignment |

## Data path

`base = window.FILIGREE_API || ''`. On boot the app loads `fixtures/source.fil` +
`fixtures/score.json` and renders immediately, then *opportunistically* POSTs the
source to `{base}/api/compile`. If that succeeds and the body looks like a Score
it swaps in the live result and the header pill flips `fixture` → `live`. Every
later compile (⌘/Ctrl+Enter or the button) tries the API first and falls back to
the fixture with a diagnostic row explaining why. So the playground is fully
usable before the compiler exists, and needs no code change once it does.

## Editor alignment contract

The overlay only stays aligned because `#hl` and `#ta` share *identical* font
stack, size, line-height, padding, `tab-size`, letter-spacing, `white-space:pre`,
and disabled ligatures. Token spans may not add weight, padding, or transforms —
colour only. This is load-bearing: Filigree is read *down* a column, so one
pixel of drift makes a bend glyph point at the wrong note. Tab/Shift-Tab indent
by 2, Enter keeps indent, ⌘/Ctrl+Enter compiles.

## Showing expression (the thing that beats the Strudel bar)

- Each note is drawn column by column: **press → alpha**, **timbre → hue shift
  (±39°)**, velocity → a brighter cap, and the note's **own bend curve as a
  polyline through its own rectangle** (dark halo + bright pass, clipped to the
  note, terminal dot). No shared global lanes — expression lives where the note is.
- Chord ribbon above the roll: symbol, root + quality, and guide tones as teal
  dots; guide-tone pitch classes are also dashed across the roll for that chord's
  span, so you can see a bend land on a guide tone.
- Faint per-stave register bands turn otherwise dead vertical space into structure.
- Note inspector plots the selected note's three curves full-width with a filled
  press envelope, plus stave / voice / beat / dur / vel / channel / bend extent.
- Playhead, bar+beat ruler (click to seek), Ctrl/Cmd+wheel zoom, row-height
  slider, per-stave colour with mute/solo, autofit so all 8 bars always fit.

## Synth

One voice per note: 3 detuned saws (0 / +7.5 / −9 cents) + triangle sub →
lowpass (Q 3.1–6.5) → tanh waveshaper → envelope → panner → bus. The bend curve
is applied at audio rate with `osc.detune.setValueCurveAtTime(cents, …)` (ramp
fallback in a try/catch for browsers that reject the curve). Press drives amp and
cutoff; timbre drives cutoff and drive amount. Bus: dry 0.92 + a deterministic
noise-IR convolver reverb (1.9 s, send 0.26) + tempo-locked delay (dotted-eighth,
fb 0.30, send 0.16) → high shelf −4.5 dB @ 5.2 kHz → compressor → master.
Notes are scheduled with a 0.65 s lookahead on a 60 ms tick. Verified in
Chromium: context `running`, 8 concurrent voices, 66 notes queued, no exceptions.

## Verification

- `python -m pytest tests/test_web.py -q` → 35 passed.
- Captures: `refs/ui/candidate_p6_round1.png` (1440×900) and
  `refs/ui/candidate_p6_round1_900x600.png` (900×600), both with the transport
  running and a note pinned in the inspector.
- The `501 (Unsupported method ('POST'))` console error in captures is expected:
  `python -m http.server` refuses the compile POST, which is exactly the offline
  fallback path.

## Requests to other pieces (please confirm or correct)

1. **`POST /api/compile`** should accept `{"source": "..."}` and return
   `Score.to_json()`. The app additionally reads an optional top-level
   `errors: [ "file:line:col: message", … ]` next to the existing `warnings`,
   and renders both in the diagnostics panel (clickable → jumps the editor to
   line:col). If the real server shape differs, only `postCompile()` in
   `app.js` changes.
2. **Diagnostic string format.** The app parses `path:line:col: message`;
   severity comes from which array the item arrived in (`errors` → error,
   `warnings` → warn), falling back to a `/error/i` match on the text for bare
   `score.warnings` strings. If `errors.py` emits a different shape (e.g. a dict
   with `line`/`col`/`severity` fields), tell me and I will widen the parser.
3. **Syntax used in `source.fil` that I invented and SPEC.md does not pin down.**
   These are plausible-but-unconfirmed and I need P1/lead to bless or rename them
   (the fixture score does not depend on any of it — only the displayed source does):
   - `notes!oct=5` — a per-lane option setting the default octave, used so every
     note cell stays the same width and the columns line up.
   - `@voicing warm` / `@feel loose` as score-level directive *applications* of
     the named `voicing`/`feel` blocks.
   - `press@top`, `bend@mid1` — lane targeting a single named voice.
   - `[: :8]` as an 8× repeat of the preceding bar.
   - Harmonic targets `>3` / `>` inside a bend lane ("land on the next chord's
     third" / "next guide tone").
   If any of these are wrong, `web/fixtures/source.fil` is the only file to fix,
   plus the three warning line:col numbers in `make_fixture.py`.
4. **`ir.Curve` point rounding.** I assumed `to_json()` rounds point values to 5
   decimals and that curve beats are absolute (not note-relative) and sorted;
   `tests/test_web.py` asserts both, so if `ir.py` ever changes the test will
   catch the drift rather than the UI silently mis-drawing.

---

# Round 2 — answering the independent UI review

Work order: `refs/verdicts/P6_round1.md`. Everything below is a change under
`web/**` plus `tests/test_web.py`; nothing outside my ownership was touched.
The critic lost two forced picks against Strudel (editor legibility, first five
seconds) and both are addressed structurally, not cosmetically.

## 1. Keyboard trap and accessibility (D1, D2)

* **Tab no longer traps focus.** `editor.js` now indents only when there is a
  selection, or when the caret sits in the line's leading whitespace. Anywhere
  else, Tab is left to the browser and focus moves on. `Shift+Tab` always
  leaves. `Escape` arms an explicit "the next Tab leaves the editor" state —
  a pill appears on the editor frame while it is armed, and it clears on the
  next keystroke, blur, or compile. Verified in a driven browser: plain Tab at
  end-of-line leaves the textarea, `Shift+Tab` lands on the how-to strip, and
  Tab still indents at a line start and across a selection.
* **Visible focus everywhere.** `style.css` went from zero `:focus` rules to
  `:focus-visible` rings (`--focus:#7fe6d0`) on the textarea, every button,
  both sliders, the checkbox, the splitter, the piano-roll viewport and each
  diagnostic row.
* **Real controls.** Mute/solo are now `<button aria-pressed>` instead of styled
  `<span>`s; diagnostic rows are `<button>`s; every control carries an
  `aria-label`; the roll is a focusable `role="application"` with arrow-key
  navigation, `Enter` to audition, `Escape` to clear, and an `aria-live` status
  line that announces the selected note and each compile result.
* **Bar separators.** The `|` lane separators the critic measured at **1.84:1**
  (`#39424e` on `#0f1216`) are now `--tk-struct:#8b95a4` = **6.20:1**, while
  staying subordinate to the glyphs at 13.98:1. `tests/test_web.py` computes
  both ratios from the stylesheet, so this cannot regress silently.

## 2. Editor legibility (D5)

12px/18px → **15px/22px** (14px/21px below 1180px). The palette went from 22
ad-hoc colours to **six semantic roles** — `struct` (separators, operators,
brackets), `glyph` (the lane glyphs themselves), `pitch`, `name`, `lit`, `dim` —
every one of them ≥4.5:1 on the editor background, and pinned by tests. No rule
inside the overlay sets `font-weight`, because synthetic bold breaks monospacing
in most stacks and would shear the lanes.

## 3. Overlay drift (D3)

The old highlighter emitted **one `<span>` per character**; each one rounded
independently and the error accumulated left to right. Coalescing runs does not
fix this — I measured it: runs of four still drifted +1.921px at 4000 chars.

The fix is structural. Each line is rendered as an invisible verbatim copy of
its own text (so the overlay's metrics are the textarea's metrics by
construction) plus **absolutely positioned tokens at `left:<column>ch`**. A
token's position is a function of its column alone, so nothing can accumulate.
Tabs are expanded against a `TAB` constant that a test pins to the CSS
`tab-size`.

`web/tools/measure_drift.py` (dev-only; excluded from the shipped-file tests)
drives the real page and reports:

| characters | textarea | overlay | drift |
|---|---|---|---|
| 100 | 903.078 px | 903.062 px | −0.016 px |
| 1000 | 9030.766 px | 9030.750 px | −0.016 px |
| **4000** | **36123.047 px** | **36123.047 px** | **+0.000 px** |

Non-accumulating and at the limit of float printing, against ~1.9px here (53px
in the critic's environment) before. The script exits non-zero above a 1px
tolerance, so it works as a gate.

## 4. First five seconds (D7)

`style.css:220` used to delete the only hints below 1180px. There is now a
`#howto` strip directly under the transport, present at **every** width, with
three real buttons in the spirit of Strudel's numbered steps: **1 hit play**,
**2 change something** (focuses the editor and jumps the caret to the first
`notes` lane), **3 hit compile ⌘⏎**, plus a one-line explainer of what the
columns mean that is the only part dropped when very narrow. A test walks every
media query and fails if the strip or its steps are ever `display:none`.

## 5. Everything else from the severity-ordered list

* **Failed compile no longer lies.** The error path never swaps in the bundled
  fixture; it marks the roll stale, says so in the panel ("the roll below is the
  last score that compiled"), turns the pill red ("compile error"), and clears
  the previous score's warnings. `collectErrors()` gained `detail` and
  `diagnostics` shapes; `showDiagnostics()` now honours the structured
  `{line, col}` instead of only re-parsing prose, so an invalid document reports
  **line 4:11 — "'Qz9' is not a chord symbol"** and clicking it lands the caret
  at exactly line 4, column 11.
* **Break tests.** Empty document → an honest empty state in both the roll and
  the diagnostics panel instead of a blank void. 400 bars → canvas area is
  capped (`MAX_CANVAS_PX`) with a device-pixel-ratio that scales down rather
  than asking for a surface the GPU refuses; the fit-to-window floor dropped
  from 10 to 1 px/beat so a long score can actually be seen whole, and a
  "bars X–Y of N" indicator says where you are. 40 staves → the legend scrolls
  instead of shoving the zoom controls off-screen. 200-beat note → per-note bend
  auto-scaling (below) and a much higher control-rate cap. Very narrow window →
  the shell is a flex column so a wrapping header cannot overflow, and the
  layout stacks at 860px.
* **Bend display was dishonest.** A `@bend-range 48st` score was drawn on a
  hard-coded ±2 st axis, so large bends were silently flattened and the curve
  swept across other notes' rows. Each note now gets `noteBendScale()` — its own
  excursion, floor 2 st, ceiling the score's `bendRange` — the clip box is
  contained to the note's own band, the inspector axis labels and legend show
  the real scale, and the curve is sampled through its actual points instead of
  a flat 260.
* **Canvas performance.** Note bodies were one `fillRect` per horizontal pixel
  (a 2000px note = 2000 draw calls); they are now a single gradient with at most
  24 stops. Guide-tone dashes are budgeted, grid density follows the zoom, and
  the overlay repaints only when something moved instead of 60×/second on an
  idle page.
* **WebAudio (`synth.js`).** Voices leaked their whole 8-node graph — they now
  carry `dispose()` and are reaped on their own heartbeat, so auditioning notes
  with the transport stopped no longer leaks for the life of the page (verified:
  0 live voices after stop). `stopVoices()` gives each step its own `try`, so a
  throw from `cancelScheduledValues` can no longer skip every `osc.stop()`.
  Note-off is a real linear ramp that reaches ~0 before the oscillator stops
  (the old `setTargetAtTime` never arrives, which is what clicked). The
  "limiter" was a ratio-4/12dB-knee compressor and is now an actual limiter
  (−6dB, knee 0, ratio 20). Control curves scale with duration
  (~160/s, cap 8192) instead of a flat 220, which was audible stair-stepping on
  long notes. Late notes are clamped to `currentTime + 5ms` instead of being
  dropped. Polyphony is capped at 96 with oldest-voice stealing.
* **Chord ribbon.** Two staves can declare different harmony on the same beat;
  those symbols were painted on top of each other and came out as unreadable
  mush. They are now grouped by beat and shown as `VI^7 / bVII^7`, ellipsised
  to fit the cell. The symbol also lost its synthetic bold, which in a canvas
  `ui-monospace` context resolved to a face with no glyph coverage and rendered
  every chord as tofu boxes.
* **Contrast pass on the canvases.** Ruler numbers, pitch names, the stave
  gutter, the inspector axis and its empty-state text were all between 1.5:1 and
  2:1; they are now 5.2–7.6:1.
* **Splitter** relayouts live while dragging (rAF-throttled) and is a keyboard
  `role="separator"` with arrow/Home/End.
* **404** — the missing favicon is now an inline SVG data URI, so the page
  still loads exactly zero external resources.

## 6. The one test I had to change, and why

`tests/test_web.py::test_no_external_urls` flagged the new favicon's
`xmlns="http://www.w3.org/2000/svg"`. That is an XML *namespace identifier*: SVG
markup is inert without the declaration and no request is ever made for the URI.
I kept the inline SVG (removing it would put the 404 back) and excluded
**namespace-only URI forms** from the scan, by matching the `xmlns` attribute
they appear in — deliberately *not* by widening the host allowlist, which would
also have let a genuine fetch from `w3.org` through. Two new tests defend the
carve-out: one proves a real external `src` on the same line is still flagged,
and `test_every_load_target_is_same_origin` asserts the underlying invariant
directly — every `src`/`href`/`@import` target in the shipped assets is
same-origin — independent of the URL regex.

## 7. Verification

Server: `PYTHONPATH=src python -m filigree.cli serve --port 8793`.
Screenshots at 1440×900, 900×600 and 560×760, plus focus-ring, Escape-armed,
compile-error and keyboard-selection states, in `/tmp/p6r2_*.png` (deliberately
not in `refs/`, which is the critic's evidence). Driven in a real browser: zero
page errors at all three sizes; invalid source reports 4:11 and jumps there;
`__rms()` measures **0.227** peak output while playing versus **0.009** after
stop; the four break documents (empty, 400 bars, 40 staves, 200-beat note) all
render without an exception. Drift: **0.000 px at 4000 characters**.
`python -m pytest -q` → **all green**.
