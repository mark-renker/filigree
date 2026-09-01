# NOTES_R3 — round 3 builder notes (drawn curve lane)

Scope: `parse.py`, `gesture.py`, `resolve.py`, `lex.py`, `examples/**`,
`tests/test_parse.py`, `tests/test_gesture.py`, `tests/test_integration.py`.
Work order: `refs/verdicts/P1_round1.md`; SPEC §3.1/§7/§12 as amended by the lead.

---

## 1. What changed

### 1.1 `_` is the lane's REST value; `v`/`V` is the lane minimum (SPEC §7)

`gesture.py` gained `LANE_RESTS` and `lane_rest_for(lane, lane_range=None)`
(bend 0 st, press 0, timbre 0.5, amp 0.5, pan 0.5, `cc<n>` 0; unknown lane →
lane minimum; always clamped into the effective lane range).  `GestureCtx.rest`
exposes it to the glyph evaluator.

* `_glyph_level`: `_` → `ctx.rest`, `v`/`V` → lane minimum.  Digits, `-`, `^`,
  `/`, `\`, `~`, `x`, `>` are unchanged, so `\` still ramps to the minimum and
  `0`–`9` still span min..max.
* The "nothing running yet" fallback for the first anchor of a lane window and
  for the entry value of a ramp/glide run changed from `ctx.center` to
  `ctx.rest`.  This also fixes verdict defect 13: `press | /^^^ |` at bar start
  used to begin at 0.50 (lane centre) and now begins at 0 (rest).
* `~` around `_` on a bend lane wiggles symmetrically about 0
  (`test_wiggle_around_a_drawn_floor_wiggles_around_zero`).
* `curve("...")` shares `parse_glyph_string`, so `v` works there too.

Parser: a run of `v`/`V` used to lex as an identifier because `_` is an
identifier character.  `_ident_ahead()` now treats a word as an identifier only
when it is followed by `(` (an inline gesture call) or contains a character
outside the glyph alphabet.  So `vv__`, `___vv__>3`, `^^^^vvvv` are glyph runs
while `vibr(depth: 0.5st)` inside a bend lane is still an inline gesture.

### 1.2 Curve-lane misalignment warns again (SPEC §3.1/§12)

`parse.py::_check_alignment` no longer exempts curve lanes, and `resolve.py`
no longer filters those warnings out (the round-2 "curve lanes never warn"
ruling is superseded).  Exact ratios (equal, integer multiple, integer divisor)
stay silent; anything else resamples **and** warns:

```
examples/foo.fil:5:19: warning: in stave 't', bar 1: lane 'bend' has 5 anchors
but lane 'notes' has 4 slots; 5 is not an integer multiple or divisor of 4, so
lane 'bend' is resampled
```

Curve lanes report `anchors`, note-bearing lanes still report `slots`, so the
two counts in the message can never be confused.  A curve lane carrying
`!time=note` is exempt: SPEC §7.1 re-normalises it per note, so bar-column
alignment is not what it means (`test_time_note_curve_lane_does_not_warn_about_columns`).

**T2 verification.** `examples/tasks.fil` L48 `bend!range=4st | xxx>3 |` is
`x`,`x`,`x`,`>3` = **4 anchors** against a 4-slot `notes` bar, i.e. exactly
aligned, so it is correctly silent under the amended rule.  The critic's "5
characters against a 4-slot bar" reading is the A1 ambiguity below (characters
≠ anchors), not a missing warning.  The misaligned case the critic actually
compiled silently — 5 anchors over 4 slots, `bend!range=4st | xxxx>3 |` — now
warns; that is the wording quoted above and it is covered by
`test_curve_lane_misalignment_warning_names_the_lanes_and_the_file` and
`test_curve_lane_inexact_anchor_count_warns`.

### 1.3 A bad chord symbol is a hard error (SPEC §12)

`resolve.py` threads `warnings=` and `pos=` into `theory.parse_roman` /
`theory.parse_absolute`, then re-points the resulting `HarmonyError` at the
chord token's own `line:col:path` and appends the recovery hint:

```
bad.fil:3:19: error: unknown chord symbol 'Vsus9alt13'
  at token: 'sus9alt13'
  hint: expected e.g. i ii7 V7 iv11 bVI IV^7 vii0 viio7 V7alt V/ii iiid, or an
        absolute symbol like Cm9 / Ab^7 / F#7b13; fix the chord symbol, or
        compile with --lenient to sustain the previous chord instead
```

`resolve(doc, lenient=False)` gained the `lenient` flag.  With `lenient=True`
the same diagnostic is emitted as a warning ending
`"; --lenient: sustaining the previous chord"`, and the offending bar extends
the *previous* chord segment rather than vanishing — so no bar of music is ever
silently deleted.  `cli.py` is untouched and can pass the flag through.

### 1.4 Unknown lane options no longer vanish

`!oct=5`, and every other option nothing reads, used to be stored and ignored.
`parse.py` now warns (`unknown-lane-option`) naming the option, the lane and
the recognised set (`range`, `shape`, `time`, `voicing`, `gesture`, plus
`gesture@<voice>`).  This flags `web/fixtures/source.fil` L30 `notes!oct=5`,
which really has no effect — `web/**` is not mine to edit; the frozen
`web/fixtures/score.json` is rebuilt from itself by `tests/test_web.py`, so
nothing breaks.

### 1.5 Examples

All seven compile with **zero** warnings (`explain`), render, and pass
`tools/audit_mpe.py` (25 checks, 0 failures each).  Every drawn floor is now in
tune, and `v` is used wherever a real downward bend is wanted:
`nocturne.fil` (`___vv__>3`), `blue_iron.fil` (`_v______`, `_v_>`),
`pulse.fil` (`__v____`), `reference.fil` (`_v-^_v-^`),
`gesture_algebra.fil` (`curve("_v^_")`).

While re-checking, three bends that were *held* a minor/major third sharp or
flat for whole notes (`^` and `/` saturating a wide `!range`) were rewritten
with digit levels so the picture and the pitch agree: `pulse.fil` bass bar 2,
`blue_iron.fil` head bar 2 and answer bar 1.  `reference.fil`'s glyph exhibit
and comments now demonstrate rest vs minimum explicitly.

Three examples still emit a **render-time** MPE diagnostic (channel exceeded
its share of the 240 events/s/channel ceiling, hold tolerance widened).  That
is `mpe.py`'s own budget report on dense `press` lanes, pre-existing and
self-explaining, not a compile warning.

---

## 2. Conflict the lead must resolve: `tests/critic_p3_curves.py`

`python -m pytest` collects `test_*.py` only, so the shipped critic files are
not part of the default suite.  Run explicitly, **four assertions in
`tests/critic_p3_curves.py` encode the pre-amendment `_` = lane-minimum
semantics** and therefore now fail:

| test | asserts |
| --- | --- |
| `test_slash_ramps_from_previous_running_value` | `curve_from_string("_/")` is `BEND_LO` at t=0 |
| `test_documented_glyph_run_shape` | `"___/^^^"` holds `BEND_LO` for the first 3/7 |
| `test_harmonic_target_glyph_ramps_from_previous_and_resolves_once` | `"_>3"` departs from `BEND_LO` |
| `test_sixty_four_anchor_bar` | `("_^" * 32)` alternates `BEND_LO`/`BEND_HI` |

These are exactly the behaviour SPEC §7 (amended) forbids and that the critic's
own defect 1 asked us to remove; they cannot both hold.  I may not edit
`tests/critic_*.py`, and I will not special-case `curve("...")` to keep them
green — that would make the same glyph mean two different things depending on
which surface wrote it.  **Requested:** re-point those four assertions at `v`
(mechanical: `_` → `v` in the four glyph strings), exactly as I did for the
equivalent cases in `tests/test_gesture.py`.  The other 47 critic assertions
pass unchanged.

---

## 3. SPEC amendment requests

Numbered for the lead; line numbers are `docs/SPEC.md` as of round 3.  I did
not edit the SPEC.

**R3-A1 — define "slot" once, and define it in anchors, not characters (L73 vs
L187).**  L73 says a slot is a whitespace-separated token; L187 says a curve
lane slot is a character.  Neither is true: `>3` and `~5` are two characters
and one anchor, `vibr(depth: 0.5st)` is 18 characters and one anchor.  Proposed
wording for §3.1: *"A bar is a sequence of **items**.  In note-bearing lanes
(`notes`, `harm`, `voices`) items are separated by whitespace.  In curve lanes
a contiguous run of glyph characters is one item whose **anchors** are its
glyphs, where a glyph is one of `_ v V - ^ / \ x` (one character), `~[depth]`,
`>[degree]`, a digit, a bracketed group, or `name(args)` — each contributing
exactly one anchor.  Whitespace inside a curve bar produces a no-data anchor.
The anchor count, never the character count, is what must line up with the
`notes` slot count."*  Then delete the L187 sentence.

**R3-A2 — `-` means three things.**  Tie in `notes` (L146), sustain in `harm`
(L123), lane centre in curve lanes (L193).  `press | -----^^ |` reads as
"sustain × 5" and means "sit at 0.5".  Recommendation: keep `-` as the level in
curve lanes but state the collision explicitly in §7 and add `x` (already
"hold") as the documented spelling for "no change here", with a note that `-`
never holds in a curve lane.  A stronger fix — retire `-` from curve lanes in
favour of `x` and `4`/`5` — would be a breaking change; I have not assumed it.

**R3-A3 — glyph meanings are lane-relative and that is now load-bearing.**
After this round `_` = 0 st on `bend` but 0.5 on `timbre`/`amp`/`pan`, `v` = min
on all lanes, `-` = midpoint (identical to `_` on `bend`, *not* on `timbre`).
§7 should carry a small per-lane table (min / rest / centre / max) rather than
one prose sentence, so a reader can see that `_` and `-` coincide on `bend` and
`_` and `v` coincide on `press`.

**R3-A4 — three kinds of "no data", and the note-on preamble is undocumented.**
An absent lane writes no curve at all; a space writes a NaN hole; `x` holds the
running value.  Separately, the resolver emits a NaN sentinel at note start for
lanes the bar does not write, which is what makes an unwritten lane reset at
note-on.  §7 documents none of this.  Recommendation: one subsection "absent,
empty, and held", plus one sentence stating that at note-on every expression
lane not written by the bar returns to its rest value.

**R3-A5 — four ways to attach a gesture, no stated precedence.**
`notes | 0!swell |`, `stave { gesture bloom }`, `press!gesture=dig`, and an
inline `name(args)` in a curve lane can all apply to one note.  The
implementation resolves stave-level last and lets lane-level and note-level
compose, but the SPEC says nothing.  Recommendation: a §8 precedence list
(note-level `!g` > inline call > lane `!gesture=` > stave `gesture` >
`@gesture` directive), and a statement about whether they compose or override
(implementation: compose, later-listed wins on conflict).

**R3-A6 — three chord spellings, one lane.**  Roman (`ii7b5`), absolute
(`Cm9`), and pitch-set are accepted in `harm` with no stated disambiguation
rule.  `iiid` vs `IIId` vs `Dm` are all legal and read very differently.
Recommendation: state that a symbol starting with a lowercase or uppercase roman
numeral (optionally `b`/`#`-prefixed) is roman, anything starting `A`–`G` is
absolute, and `[...]` is a pitch set — and that this is decided before any
quality suffix is parsed.  Also now worth stating: an unrecognised symbol is a
**hard error** (done, §12), and `--lenient` sustains.

**R3-A7 — whitespace changes the meaning of `-` in `notes`.**
`notes | 0 -2 - 2 |` is degree 0, degree −2, tie, degree 2 (4 slots), while
`notes | 0 - 2 - 2 |` is 5 slots with two ties.  One space converts a negative
degree into a tie plus a degree.  Recommendation: document the trap in §5 with
this exact pair, and recommend `_2` or `(-2)` … or, better, mandate that a
negative degree be written without a space and warn when a `notes` bar mixes
both readings.  I did not add such a warning: it would fire on legal existing
files and needs a ruling.

**R3-A8 — postfix modifier precedence is unstated.**
`0!scoop.5~3` — accent, gesture, dotted duration, wiggle — has no stated parse
order, and `~` is both a note-level ornament and a curve glyph.
Recommendation: state the fixed postfix order (`degree`, accidental, octave
marks, `~ornament`, duration/dot, `!gesture`, `:velocity`) and that any other
order is an error rather than silently reordered.

**R3-A9 — small unstated behaviours I confirmed and would like written down.**
(a) A `>` in the final bar has no next chord and falls back to the current one.
(b) `/` (and any ramp) at the start of a bar now departs from the lane's **rest**
value, not its centre.  (c) Degrees above 8 are legal and wrap by octave.
(d) A leading-dot decimal (`.5`) is rejected in gesture args; `0.5` is required.
(e) Unknown lane options now warn (§1.4) — §4 should list the recognised set.

---

## 4. Test coverage added

`tests/test_gesture.py`: `test_floor_glyph_is_the_lane_rest_value_not_the_minimum`,
`test_rest_and_min_differ_on_bend_and_agree_on_press`,
`test_timbre_rests_at_the_half_way_point`,
`test_capital_v_is_accepted_as_the_minimum_glyph`,
`test_wiggle_around_a_drawn_floor_wiggles_around_zero`, plus nine existing
glyph tests re-pointed from `_` to `v` where they meant "minimum".

`tests/test_parse.py`: `test_glyph_run_of_v_parses_as_glyphs_not_as_an_identifier`,
`test_an_inline_gesture_call_inside_a_curve_lane_still_parses`,
`test_curve_lane_exact_anchor_ratios_do_not_warn`,
`test_curve_lane_misalignment_warning_names_the_lanes_and_the_file`,
`test_unknown_lane_option_is_a_warning_not_silence`; the two old "N slots"
assertions updated to "N anchors".

`tests/test_integration.py`: `test_curve_lane_inexact_anchor_count_warns` and
`test_curve_lane_exact_anchor_ratio_stays_silent` (replacing
`test_curve_lane_slot_mismatch_never_warns`, whose premise §12 superseded),
`test_time_note_curve_lane_does_not_warn_about_columns`,
`test_unknown_chord_symbol_is_a_hard_error_with_line_and_col`,
`test_lenient_downgrades_a_chord_typo_and_sustains_the_previous_chord`,
`test_lenient_defaults_to_false`,
`test_unrecognised_lane_option_warns_instead_of_being_ignored`.
