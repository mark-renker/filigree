# NOTES_P3 — gestures + curves

Builder notes for P3. Files owned and delivered:

| File | State |
|---|---|
| `src/filigree/gesture.py` | complete, `py_compile` clean |
| `tests/test_gesture.py` | 120 tests / 258 assertions, green |
| `tools/plot_curves.py` | runs, writes 6 PNGs to `refs/plots/`, all visually checked |
| `refs/syntax/curves.md` | complete |

Nothing outside that list was touched. `ast_nodes.py`, `ir.py`, `errors.py` are
imported and never edited. stdlib + numpy only in `gesture.py`; matplotlib is
confined to `tools/plot_curves.py`.

---

## 1. Cross-file requests (blocking-ish, for the lead / resolver owner)

### 1.1 Inline gesture calls inside a glyph lane are left as holes — the resolver must expand them

`glyphs_to_gesture` handles every SPEC §7 glyph, but a `Slot(kind="gesture")`
(the `name(args)` form appearing inside a lane) is emitted as a **no-data hole**
(NaN over that slot's span). I cannot expand it: resolving a gesture name needs
the `Env` of gesture definitions, which is resolver-owned state, and inventing a
second lookup path here would duplicate scoping rules that belong to P4.

**Request:** the resolver should walk slots, expand `kind="gesture"` slots by
calling `eval_gesture(env[name], args, ctx)` and windowing the result to the
slot's `(start, end)` with `Gesture.window(...)`, then merge with the glyph
gesture using `|`. Merge order matters: later segments overlay earlier ones where
they carry data, so pass the glyph gesture first if explicit glyphs should win,
second if the inline call should win. I have assumed **explicit glyphs win** in
`refs/syntax/curves.md`; say the word if it's the other way and I'll invert the
documented order.

### 1.2 `GestureCtx` has one `lane_range`, but a gesture can touch many lanes

`GestureCtx.lane_range` is a single `(lo, hi)`. A `press(...) | timbre(...)`
gesture needs two. I work around this with `ctx.for_lane(lane)`, which derives a
per-lane range from `ir.LANE_RANGES` plus `cc<n> → (0, 1)`, and only falls back
to the ctx-level `lane_range` for the lane named by `ctx.lane_default`.

**Consequence for the resolver:** a per-lane `!range=7st` option is only honoured
for the default lane. If per-lane ranges are needed generally, the cleanest fix
is adding an optional `lane_ranges: dict[str, tuple[float, float]]` to
`GestureCtx` — that's a frozen-contract change, so I have not made it. Until
then, pass the range of the lane the gesture is attached to as `lane_range`.

### 1.3 No package scaffolding yet

There is no `src/filigree/__init__.py` and no `pyproject.toml` (both lead-owned).
`tests/test_gesture.py` therefore bootstraps `sys.path` with the repo's `src/`
directory at import time. Imports work today via namespace packages; if a real
`__init__.py` lands, the bootstrap is harmless and can stay or go.

### 1.4 `ctx.note_dur_sec` must be real

Absolute positions (`@ 200ms`) and all rate primitives (`wiggle`, `pulse`,
`drift`) convert through `ctx.note_dur_sec`. If the resolver passes a placeholder
duration, gestures will still render but at the wrong rate. Rate primitives are
reclocked on windowing specifically so that Hz stay real-time Hz, which only
works if the duration is truthful.

---

## 2. Ambiguities in SPEC §8 and how I resolved them

Each of these is pinned by a test, so changing one is a visible, cheap edit.

1. **`@window` fits, it does not clip.** `a @ 35%..100%` *rescales* `a` into the
   window rather than sampling `a` and discarding the outside. Decisive argument:
   the spec's own algebra law `a >> b == (a @ 0..50%) | (b @ 50%..100%)` is only
   exactly true under the fit reading. Clipping is still available — window a
   gesture that already spans the region.
2. **Rate primitives reclock rather than stretch under windowing.** `wiggle`,
   `pulse` and `drift` expose `rescaled(k)`, so 5.5 Hz windowed to the last 65 %
   of the note is still 5.5 Hz of wall-clock, and phase 0 lands on the window
   start. Without this, P3.2's fade-in vibrato would change speed.
3. **NaN algebra.** `add`/`sub` treat NaN as the additive identity — the result is
   NaN only where *both* operands are NaN. `mul`, scalar scaling and `neg`
   **propagate** NaN (absorbing). Rationale: summing two partial gestures should
   union their written regions, while multiplying by an undefined thing is
   undefined. Corollary: `mul` over disjoint windows yields no data at all, and
   `sample()` returns `None`.
4. **Glyph run semantics.** A glyph's value is reached by the **end** of its slot,
   and a run opens flat (the first anchor's value is already in force at the run
   start) — *except* `/`, `\` and `>`, which start from the running value (the
   lane centre if nothing is running). So `___/^^^` is hold-min, ramp across the
   `/` slot, hold-max. Alternative readings either make `___` a ramp from centre
   or make `/` instantaneous; both looked wrong when plotted
   (`refs/plots/p3_6_glyph_lane.png`).
5. **`hold` vs `snap`.** `hold` is *post*-hold: it keeps the previous anchor and
   jumps at the next one. `snap` is *pre*-jump: it takes the target value from the
   start of the span. This is the only shape allowed to be discontinuous, and the
   continuity test exempts exactly it.
6. **Shape formulae.** `ease` = smoothstep `f²(3−2f)`; `exp` =
   `(e^{3f}−1)/(e^3−1)` (normalised so `f=0→0`, `f=1→1`); `linear` = `f`.
   The `3` in `exp` is a curvature constant; SPEC doesn't name one.
7. **`~n` depth.** `~n` gives depth `(n/9) × half-span` of the lane, bare `~` is
   `3/9`. Defaults: `DEFAULT_WIGGLE_HZ = 5.0`, `DEFAULT_DRIFT_HZ = 1.5`,
   `DEFAULT_DEPTH_FRAC = 0.05` of the full lane span for a bare `wiggle()` /
   `drift()`.
8. **`-` glyph** is 0 on bipolar lanes (`bend`) and 0.5 on unipolar lanes —
   "middle of the lane", not "zero".
9. **`pulse` is unipolar 0/1**, and its `phase` argument is in **turns** (0..1),
   not radians. SPEC didn't say; turns compose better with `@`.
10. **Targets.** `>` is rejected on non-`bend` lanes (`GestureError`), and a
    missing `resolve_target` callback is an error rather than a silent 0.
    Targets are resolved **once at eval time**, not per sample, so a gesture is a
    pure function of `t` after evaluation — required for determinism.
11. **Empty slots produce NaN, per note-lifetime fraction**, and `sample()`
    returns NaN outside `[0, 1]` and `None` for a lane with no segments at all.
    This is the load-bearing "never write an unspecified region" rule.
12. **`drift` determinism.** Value noise keyed by `ctx.seed_key`; `hash01` uses
    blake2b rather than `hash()` so it is immune to Python hash randomisation.
    Control points = `ceil(rate × span_sec) + 2`, smoothstep-interpolated.
    Same seed_key ⇒ bit-identical output across processes.
13. **Both `Breakpoints.shape` and `Call.kwargs["shape"]` are honoured**, since
    the AST admits either spelling.

---

## 3. Extras beyond the ARCH P3 API

Public but additive; safe to ignore, useful to P4 and to tooling:
`parse_glyph_string`, `curve_from_string`, `lane_range_for`, `hash01`,
`noise_series`, `SHAPES`, `LANE_PRIMITIVES`, `GENERATORS`, `is_lane_primitive`,
and a `const` generator. `Segment.fn` takes **local** normalised time
`u ∈ [0,1]` across `Segment.window`, where `window` is the fraction of the note
lifetime the segment covers.

---

## 4. Verification

```
python -m pytest tests/test_gesture.py -q        # 120 passed
python -m py_compile src/filigree/gesture.py tests/test_gesture.py tools/plot_curves.py
python tools/plot_curves.py                      # PNGs into refs/plots/ (7 after round 2)
```

`tools/plot_curves.py` exits non-zero if any PNG comes out under 4 KB, so a
silently-empty plot fails loudly. All were also inspected by eye.
(Round-2 counts and details are in the Round 2 section below, which supersedes
the test count quoted above.)

Scratch helper for the character counts in `refs/syntax/curves.md` lives outside
the repo at `/home/user/workspace/p3_char_counts.py` (deliberately not in
`tools/`, which I don't own beyond `plot_curves.py`).

---

# Round 2

The blind critic's round-1 verdict (`refs/verdicts/P3_round1.md`) is in every
respect correct and the reference deservedly won. Here is what changed.

## R2.1 Reclocking — rate primitives keep their Hz everywhere (CRITICAL)

Round 1 had **one** time transform, and it was wrong for rates: nesting a
`wiggle` inside `*`, `@window`, `>>` or a glyph lane silently rescaled its
period, so `wiggle(5.5hz, …)` inside a 65 % window ran at 8.46 Hz.

There are now **two** time maps, and every lane function implements both:

| op | meaning | used by |
|---|---|---|
| `rescaled(k)` | the fn's 0..1 domain now spans `k ×` as many real seconds | *fitting*: `Segment.remapped`, `Gesture.windowed` |
| `reoriginned(u0)` | phase 0 moves to domain position `u0`; seconds-per-domain-unit unchanged | *restricting*: `@ x..y`, `>>` |

Rate leaves (`_RateFn`, `_Wiggle`, `_Pulse`, `_Drift`) convert domain time to
seconds through `_secs(u) = (u - u0) * eff_span`, so `rescaled` multiplies
`span_sec` (period follows the note) while `reoriginned` only moves the phase
origin (period stays absolute). Non-rate leaves ignore both. The entry points
`_reclock_fn(fn, k)` / `_reorigin_fn(fn, u0)` are total — anything without the
method is returned unchanged — and the wrappers `_Scaled`, `_Combined` and
`_GlyphFn` **forward into their operands** (`_Combined` via
`Gesture.time_scaled` / `Gesture.reoriginned_at`) instead of wrapping opaquely.
That forwarding was the actual bug: `_Combined` was the wall the transform
never crossed.

Rate measured from rendered descending zero crossings, 5.5 Hz written
(`hz_from_zero_crossings` in `tests/test_gesture.py`):

| nesting configuration | measured |
|---|---|
| `bend(wiggle(5.5hz, 0.4st))` — bare | 5.5000 Hz |
| `wiggle(5.5hz,0.4st) * ramp(0, 1)` | 5.5000 Hz |
| `(wiggle * ramp(0,1)) @ 35%..100%` | 5.5000 Hz |
| `wiggle + ramp(0, 1st)` (linear detrend) | 5.5000 Hz |
| `ramp(0,1st) >> wiggle` (2nd half) | 5.5000 Hz |
| `((wiggle * ramp) @ 20%..90%) @ 50%..100%` | 5.5 Hz (rel 0.02) |
| `pulse` through a window | rate preserved |

Glyph `~`: 5.0 Hz bare on a 4 s note, **5.0 Hz after `windowed(0, 0.5)`**, and
5.0 Hz on a 1 s note. `~` additionally snaps to a whole number of cycles per
slot (`cycles = max(1, round(hz · span))`) so a slot never ends mid-swing and
leaves a step at the slot boundary; on short slots that snapping, not the
window, is what moves the rate, and it is documented in `refs/syntax/curves.md`.

One measurement trap worth recording: my first harness cubic-detrended before
counting crossings, which biases the crossings of an amplitude-modulated sine
and reported 5.38 Hz for a correct 5.5 Hz curve. Crossings are now counted on
the raw signal, with a *linear* detrend only for the `wiggle + ramp` case where
a DC ramp genuinely offsets them.

## R2.2 `@ x..y` restricts, it does not refit

SPEC §8 is explicit — a window is *"a restriction to a window of the note
lifetime"*. Round 1 refit: it squeezed the whole inner gesture into the window.
Now `eval_gesture` sends `Window` to `Segment.restricted(a, b)`, which
intersects each segment's existing window with `a..b`, reoriginates the fn at
the window open, and wraps the result in `_Retimed` so the inner gesture keeps
its own 0..1 domain over the surviving span. Everything outside is **unwritten
(NaN)**, not stretched — visible as the shaded "no data" region in
`p3_2_vibrato.png`. Nested windows now *intersect*, and disjoint nested windows
write nothing at all rather than resurrecting a squeezed copy.

`>>` (`seq`) is now a hand-off too: `lhs.restricted(0, split) | rhs.restricted(split, 1)`.

I do **not** think SPEC is wrong. But restriction leaves a real gap in the
language, so this is a **SPEC amendment request**: there is now no operator that
*fits* a gesture into a span (the old, wrong `@` behaviour), and it is a
genuinely useful thing to want — "play this whole shape in the last 30 %".
`Gesture.windowed()` still does exactly that internally and `resolve.py` uses
it. Request: add an explicit fitting operator, e.g. `gesture @@ 70%..100%` or
`fit(gesture, 70%..100%)`, distinct from restricting `@`.

## R2.3 Lane-range discipline

No gesture output leaves its lane range. Two mechanisms:

1. `_GlyphFn` carries the `lane_range` and `np.clip`s its output, so no glyph
   lane can emit a value outside the lane.
2. `~` **compresses instead of clipping**: available headroom is
   `max(min(hi − value, value − lo), 0)` and the wiggle depth is reduced to fit.
   A wiggle around an extreme anchor therefore gets *quieter*, symmetrically,
   rather than being flattened into a distorted, DC-biased square. That choice
   is deliberate — a clipped vibrato changes the *mean* of the lane, which on a
   pitch lane means the note goes out of tune. Documented in `curves.md`,
   plotted in `p3_7_lane_range.png`, tested by
   `test_glyph_curves_never_leave_the_lane_range`,
   `test_wiggle_at_the_lane_maximum_compresses_to_a_hold`,
   `test_wiggle_near_the_lane_maximum_compresses_symmetrically` and
   `test_glyph_wiggle_does_not_bias_the_slot_average`.

Measured on the ±2 st bend lane: `^~` → min = max = mean = **2.0000** (a flat
hold; the round-1 bug reached 2.667), `8~` → 1.1111 … 2.0000 (mean 1.5556),
`9~` and `_~` → flat at the boundary.

## R2.4 Honesty of the bar

`refs/syntax/curves.md` was rewritten. All four over-claims were independently
re-verified with web search + page fetches, and every claim in the file now
carries a URL:

- **Sonic Pi is not linear-only.** `note_slide_shape` / `note_slide_curve` exist
  with shapes 0 step, 1 linear, 3 sine, 4 welch, 5 custom, 6 squared, 7 cubed.
  The round-1 premise came from the tutorial, which only documents slide *time*.
- **MusicXML `<scoop/>`** is the honest shortest form for row 1 and is now used.
- The MusicXML `<bend>` snippet is now schema-valid (correct child order,
  `<pre-bend>`/`<release>` not mixed).
- Counting rule stated up front and applied mechanically: comment-only, blank
  and no-op lines are dropped, non-whitespace characters are counted, Csound
  score `i`-lines count as data. The padded `kbend = kvib` line and a 55-char
  prose comment are gone.

Rows whose winner **changed** after honest recounting (all three now marked
**REFERENCE** in the file, i.e. a rival wins):

| row | round 1 claim | honest count | winner now |
|---|---|---|---|
| 2 vibrato from 35 % | Filigree shortest | Filigree 58 vs Csound **50** | **Csound — REFERENCE** |
| 3 swell + timbre | Filigree shortest | Filigree 57 vs Csound **54** | **Csound — REFERENCE** |
| 4 land on the third | Filigree shortest | Filigree 23 vs Csound **21** | **Csound — REFERENCE** |

Rows Filigree still leads: 1 scoop (32 vs 34, a 1.06× margin — narrow enough
that the file says so) and 5 reuse (96 vs 193, 2.01×). Row 5 is the only row
where the margin is large, and it is the row about *reuse*, which is the honest
claim to make for this language: Filigree is not competitive on single-gesture
character count, it is competitive on parameterised reuse and on the harmonic
target `>3`, which no rival can express without writing the number.

## R2.5 Naming

`fall` → **`lift`** in `tools/plot_curves.py`, `tests/test_gesture.py` and
`curves.md`; it bends *up* to the third, and the round-1 name said the opposite.

`>3` → **`>third` alias: requested, not implemented.** It belongs in the token
lexer in `src/filigree/parse.py`, which I do not own, and there is a second
problem: inside a drawn glyph lane every slot is one column wide, so a
multi-character `>third` would break column alignment — the alias can only be
legal in expression position, not in a glyph lane. Filed here as a **SPEC
amendment request** with that restriction spelled out rather than half-added.

## R2.6 Plots

All PNGs regenerated and inspected with the read tool, plus a new
`p3_7_lane_range.png`. Captions are now **generated from the rendered samples**
(`measured_hz()` counts zero crossings of the very array that is plotted), so a
caption cannot claim a rate the picture does not show. `p3_2_vibrato.png` prints
"measured 5.50 Hz from zero crossings (written 5.5hz)". Two caption errors
found by eyeballing and fixed: P3.3's `timbre` line called an eased curve
"linear", and P3.2's source string was missing the parentheses that `@`'s
tighter binding requires.

## R2.7 Verification

```
PYTHONPATH=src python -m pytest tests/test_gesture.py tests/critic_p3_curves.py -q
```
→ **183 passed**, including all 47 critic tests (the 6 that failed in round 1).
`tests/critic_p3_curves.py` was not edited.
