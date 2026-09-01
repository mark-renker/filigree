# Filigree — Language Specification v0.1

Filigree is a text language for **fast ideation of intricate musical expression and harmony**.
It compiles to MPE (MIDI Polyphonic Expression) — SMF files or realtime MIDI.

## Design thesis (the five gaps we close)

From `research/landscape.md`, no existing system does these. Filigree does all five:

1. **Expression is a note-scoped, typed, time-normalized curve** — not a channel-wide parallel
   stream (Tidal/Strudel), not a scalar event field (SC/FoxDot/Alda), not a symbolic glyph
   (LilyPond/ABC), not an instrument-side rule (SFZ).
2. **Curves are drawn as text, column-aligned with the notes** that carry them. Diffable,
   greppable, readable at a glance.
3. **Harmony and expression join**: a curve's endpoint can be a *musical* reference
   (`>3` = glide to the next chord's third), so "bend into the next chord's guide tone" is
   one character.
4. **Voices are named and individually expressive** — `bass`, `lead`, `1..n` — one chord can
   carry four independent gestures, which MPE per-note channels can actually deliver.
5. **Gestures are first-class values**: named, parameterized, composed with an algebra, reused
   across a piece.

## 0. Lexical basics

- UTF-8 text, `.fil` extension. Line comments start with `#`.
- Blank lines are insignificant. Indentation is insignificant (blocks use `{ }`).
- Case-sensitive. Identifiers: `[A-Za-z_][A-Za-z0-9_-]*`.
- Units are suffixed literals: `84bpm`, `5.2hz`, `-2st` (semitones), `40ms`, `0.6` (normalized),
  `%` (percent, `35%` == `0.35`).

## 1. Document structure

```
<directive>*        # @tempo, @key, ...
<definition>*       # gesture / feel / voicing / part
<stave>*            # the music
```

Order is free; directives and definitions take effect for staves that follow them.

## 2. Directives

| Directive | Default | Meaning |
|---|---|---|
| `@tempo 84` | `120` | BPM. Accepts `84bpm`. |
| `@meter 7/8` | `4/4` | Time signature. |
| `@key C minor` | `C major` | Tonic + mode. Modes: `major ionian dorian phrygian lydian mixolydian minor aeolian locrian harmonic-minor melodic-minor whole-tone chromatic blues`. |
| `@ppq 960` | `960` | Ticks per quarter in output SMF. |
| `@bend-range 48st` | `48st` | MPE member-channel pitch-bend range. |
| `@grid 10ms` | `10ms` | Expression sample interval (pitch lane uses `@grid/2`). |
| `@seed 7` | `0` | Seed for all stochastic `feel`. Deterministic output. |
| `@title "..."` | — | Metadata. |

## 3. Staves

A stave is a synchronized bundle of **lanes**. Lanes are aligned in time **column-wise by
slot**, which is the core ergonomic idea: you never write a duration.

```
stave lead {
  channelgroup 1              # optional: MPE zone / port routing
  harm   | i9       | VI^7     | iv11         | V7alt    |
  notes  | 0 . 2 3  | 4 - - 2  | [0 2] 3 . 5  | 7 - 6 -  |
  bend   | ___/^^^^ | ^^\_____ | ............ | __/\___>3 |
  press  | /^^^\___ | -----^^^ | __/^^^^^\___ | ^^^^\___ |
  timbre | ---^^^-- | ........ | ............ | ........ |
}
```

### 3.1 Bars, items, slots and anchors

- `|` separates bars. Leading/trailing `|` optional.
- **The item rule, stated once.** A bar is a sequence of **items**, and every item takes an
  equal share of the bar.
- On a **note-bearing lane** (`notes`, `harm`, `voices`) items are separated by whitespace and
  an item is called a **slot**. A bar of 4 slots = 4 quarter-notes in 4/4; 8 slots = 8 eighths.
- On a **curve lane** (§7) whitespace is *only* a separator and yields no item at all. Items
  are called **anchors**, and they are counted — never characters. Exactly one anchor is
  produced by each of: one of the single-character glyphs `_ v V - ^ / \ x`; one digit `0`–`9`;
  `~` with its optional depth (`~5`); `>` with its optional target (`>3`, `>root`, `>|`); `.`
  (an item that carries no data); a bracketed group `[...]`, `(...)` or `<...>`; an inline
  gesture call `name(args)`. So `>3` is two characters and one anchor, and
  `vibr(depth: 0.5st)` is eighteen characters and one anchor. To say "no data here" write `.`
  (as on the `notes` lane); a run of spaces never means silence. `bend | ___/^^^ |` and
  `bend | _ _ _ / ^ ^ ^ |` are therefore the same curve -- the spacing exists only so the
  glyphs can be column-aligned under the notes they belong to.
- `[a b c]` nests: the group is one item, subdivided equally among its children. Nesting is
  arbitrarily deep. `x*3` expands to 3 items. `[: ... :4]` repeats a bar-fragment 4 times.
- Item counts may differ per lane and per bar — each lane subdivides the same bar
  independently, and lane time is bar time (see 7.1). It is a curve lane's **anchor** count,
  never its character count, that has to line up with the bar's `notes` slot count: when the
  anchor count is not an integer multiple or divisor of that slot count, the lane is resampled
  and a warning names both counts (see 12).

### 3.2 Lane kinds

| Lane | Content | Output |
|---|---|---|
| `harm` | chord symbols (§4) | harmonic context; sounds only if the stave has no `notes`/`voices` lane, in which case the voiced chord is played |
| `notes` | monophonic-ish note tokens (§5) | notes |
| `voices` | polyphonic named-voice block (§6) | notes |
| `bend` | curve glyphs (§7) | per-note pitch bend, range `±@lane-range` (default `±2st`) |
| `press` | curve glyphs | per-note channel pressure `0..1` |
| `timbre` | curve glyphs | per-note CC74 `0..1`, center `0.5` |
| `amp` | curve glyphs | note velocity (sampled at note-on) + CC11 during note |
| `pan` | curve glyphs | CC10 (channel-scoped; documented as non-per-note) |
| `cc<n>` | curve glyphs | CC number n, `0..1` mapped to `0..127` |

Lane options are set with a trailing `!` clause on the lane name, chained if there are several:

```
  bend!range=7st!shape=ease  | ___/^^^ |
```

The recognised option names are exactly these:

| Option | Read on | Values | Meaning |
|---|---|---|---|
| `!range=<n>` | curve lanes | number, optional `st` | the lane's value range: `±n` on the bipolar `bend` lane, `0..n` on the unipolar lanes. Default `±2st` on `bend` (`@lane-range`), `0..1` elsewhere. |
| `!shape=<s>` | curve lanes | `ease` (default), `linear`, `hold`, `exp`, `snap` | interpolation between anchors |
| `!time=<m>` | curve lanes | `bar` (default), `note` | lane time mode (§7.1) |
| `!voicing=<name>` | `harm` | a `voicing` name | voicing for this lane's chords (§4.1) |
| `!gesture=<name>` | note-bearing lanes | a `gesture` name | gesture attached to every note of the lane (§8) |
| `!gesture@<voice>=<name>` | note-bearing lanes | a `gesture` name | the same, restricted to one named voice (§6) |

An unknown `shape` or `time` value is a hard error. Any **other** option name -- `!oct=5`, or a
typo -- is a **warning**: nothing in the compiler reads it, so it has no effect, and the warning
names the option, the lane and the recognised set. `!gesture=` is read on note-bearing lanes
only; written on a curve lane it is accepted and has no effect (see §8.1).

### 3.3 Multiple staves

Staves play simultaneously from bar 1. `stave name { ... }` — the name becomes the SMF track
name. A stave may declare `after <stave-name>` to start when that stave ends.

## 4. Harmony (`harm` lane)

Filigree accepts three interchangeable chord spellings; all are converted to the same internal
`Chord`:

1. **Roman numerals** (relative to `@key`), Ziffers/Hookpad-lineage:
   `i ii III iv V vi vii` — case sets quality (lowercase = minor, uppercase = major).
   Extensions: `V7 i9 iv11 II13 v6 IV^7`(maj7) `vii0`(dim) `viio7`(dim7) `IIx`(altered/dominant)
   `V7alt` `bVI` `#iv` `V/x` (secondary dominant of scale degree x, e.g. `V/ii`).
   Modal interchange with a trailing mode letter: `iiid` = iii borrowed from dorian,
   `IVf` = IV from phrygian, `bVIIm` = from mixolydian. Letters:
   `n`(ionian) `d`(dorian) `f`(phrygian) `y`(lydian) `m`(mixolydian) `a`(aeolian) `l`(locrian)
   `h`(harmonic minor) `e`(melodic minor).
2. **Absolute symbols**: `Cm9`, `Ab^7`, `F#7b13`, `Bsus4`, `Dm7/A`, `C6/9`, `Galt`, `E7#9#11`.
3. **Explicit pitch sets**, in braces: `{0 3 7 10 14}` (semitones over the chord root) or
   `{C4 Eb4 G4 Bb4}` (absolute). Braces, not brackets: `[...]` in a `harm` bar is a group that
   subdivides its slot (§3.1), not a pitch set.

**How the three spellings are told apart.** The choice is made from the symbol's opening
characters, *before* any quality suffix is looked at, so a suffix can never turn one spelling
into another:

1. a symbol in `{ }` is a **pitch set**. Whether the set is absolute or relative is decided by
   its first member: if that member is an absolute pitch (`C4`), every member must be one;
   otherwise every member must be an integer semitone offset.
2. otherwise a slash bass is split off, and what remains is **roman** if it begins with an
   optional run of `b`/`#` followed by a roman numeral (`i ii iii iv v vi vii` in either case)
   that is not itself followed by another `i`/`v` character.
3. otherwise it is **absolute** if it begins with `A`–`G`.
4. otherwise it is not a chord symbol at all.

Case is load-bearing, and it is read before the suffix: `iiid` is `iii` borrowed from dorian,
`IIId` is the same degree written major, and `Dm` is an absolute chord — three different
readings of near-identical text. Because rule 2 is tried first, a lowercase `b`/`#` head is a
roman accidental (`bVI`) while an uppercase letter head is a root name (`Bb^7`).

An unrecognised symbol is a **hard error**, never a silent substitution; `--lenient` downgrades
it to a warning and sustains the previous chord (see §12).

Slash bass: `.../E` or `/3` (chord's own 3rd in the bass).
A slot of `-` sustains the previous chord; `.` is harmonic silence (notes keep their last
context for `>`-targets).

### 4.1 Voicing

```
voicing warm { range: C3..C5, mode: smooth, size: 4, drop: 2, spread: 1.1, top: melody }
```

- `mode`: `smooth` (minimal voice-leading movement, default) | `close` | `open` | `drop`
  | `quartal` | `shell` (root+3rd+7th) | `rootless` | `literal` (as spelled).
- `top: melody` forces the top voice to follow the `notes` lane pitch class when possible.
- Applied per stave with `harm!voicing=warm`, or globally with `@voicing warm`.
- `size` clamps voice count; extensions are dropped by a documented priority order
  (`b9/#11/13` kept before `5th`, `root` droppable in `rootless`).

## 5. Note tokens (`notes` lane)

A token is one of:

| Token | Meaning |
|---|---|
| `.` | rest |
| `-` | extend previous note (tie) through this slot |
| `=` | retrigger previous pitch |
| `0 1 2 ... 7 8` | scale degree relative to `@key` (0 = tonic). Negative allowed: `-2`. |
| `^0 _0` | octave shift, sticky per-lane until changed (`^^3` = two octaves up) |
| `+0 -0`? | no — accidentals are `#`/`b` prefixed: `#4`, `b3` |
| `C4 Eb3 F#5` | absolute pitch (letter + optional accidental + octave) |
| `~3` | chord-relative degree: the 3rd of the *current* `harm` chord (`~1 ~3 ~5 ~7 ~9`) |
| `@low @high @root @guide` | anchors: lowest/highest voice, root, nearest guide tone of current chord |
| `<a b c>` | alternation — pick a different member each time the bar repeats |
| `(a b c)` | chord (simultaneous) |
| `token!gesture` | attach a named gesture to just this note |
| `token:v90` | explicit velocity 0–127 |
| `token%50` | gate/articulation: sound 50% of the slot (Alda `quant` lineage) |
| `token'` | accent (velocity +15%); `token,` = soften (−15%) |
| `token?` | probability 50% (`token?25` = 25%) |

Sticky state per lane: octave, velocity, gate. Reset with `!reset`.

**Degrees are not limited to `0`–`8`.** A degree past the octave is legal and wraps by octave:
`7` is the tonic an octave above `0`, `9` is the second an octave up, `14` the tonic two octaves
up. Negative degrees wrap downwards the same way (`-2` is the seventh below the tonic).

**A space changes what `-` means.** `-` is a tie only where it stands as an item of its own;
written immediately before a number it is that number's minus sign. The two bars

```
stave unspaced {
  notes | 0 -2 - 2 |     # 4 slots: degree 0, degree -2, tie, degree 2
}

stave spaced {
  notes | 0 - 2 - 2 |    # 5 slots: degree 0, tie, degree 2, tie, degree 2
}
```

differ in pitch content *and* in slot count, so they also divide the bar differently. Write a
negative degree unspaced. Filigree does not warn about the pair: both readings are legal, the
parser is never in doubt, and a bar that uses both is not in itself a mistake.

### 5.1 Prefixes and postfix modifiers

A token is a **core** with prefixes before it and modifiers after it.

**Prefixes are ordered**, and the order is fixed: octave marks first, then the accidental, then
the degree — `^#3`, `^^b3`, `_2`. The reverse (`#^3`, `b^^3`) is a hard error. Octave marks
repeat and cancel (`^^3` = two octaves up, `^_3` = `3`), and they apply to scale degrees only:
`^C4`, `^~3` and `^@root` are errors, since an absolute pitch already names its octave and a
chord tone is placed by the voicing.

**Postfix modifiers are not ordered.** The recognised modifiers are

| Modifier | Effect |
|---|---|
| `!name`, `!name(args)` | attach a gesture (§8.1) |
| `!reset` | clear the lane's sticky octave, velocity and gate |
| `:v<n>` | velocity 0–127, sticky |
| `%<n>` | gate, percent of the slot, sticky |
| `'` / `,` | accent / soften, ±15% velocity |
| `?` / `?<n>` | probability, 50% / n% |

The parser peels them off the end of the token in any order and applies them left to right, so
`0!scoop:v90'` and `0':v90!scoop` are the same note. The language mandates no canonical order
and no order is an error; a house style may still be worth keeping. Repetition is meaningful
where the modifier accumulates (`0''` is +30% velocity) and last-one-wins where it sets a value
(`0:v80:v100` is velocity 100). Several `!name` attachments are kept in written order, and the
leftmost wins where two of them write the same lane (§8.1).

Two things a modifier is *not*: there is no duration or dotted-duration modifier — timing is
inferred from the slot count (§3.1) — and `~` is not a postfix ornament. In a `notes` lane `~`
is the chord-tone prefix (`~3`) and in a curve lane it is the wiggle glyph (§7); `0!scoop~3` is
a hard error, not an ornamented note.

## 6. Named voices (`voices` lane)

```
  voices | { bass: 0 . 2 -   ;
              mid : ~3 ~5 - - ;
              lead: 7 - 6 5   } | ... |
```

Shorthand: `voices | bass:0 mid:~3 lead:7 |` (one slot).
Voice names are free identifiers; `bass` and `lead` are conventional and are what
`voicing.top`/`@low` refer to. Each voice gets its own MPE member channel and can carry its own
gestures:

```
  press@lead | /^^^\__ |
  bend@bass  | ______  |
```

A lane suffixed `@voicename` applies only to that voice. An unsuffixed expression lane applies
to **all** sounding notes of the stave.

## 7. Curve lanes — expression drawn as text

Each glyph is an **anchor** at its slot boundary; the curve is interpolated between anchors
(default `shape=ease`, i.e. smoothstep; `linear`, `hold`, `exp`, `snap` also available).

Each lane has a **rest value** -- the value meaning "this lane is doing nothing": `bend` 0 st,
`press` 0, `timbre` 0.5, `amp` 0.5, `pan` 0.5, `cc<n>` 0. The floor glyph `_` means the **rest
value**, not the lane minimum. This matters: on a bipolar lane the minimum is a large downward
bend, and a drawn floor must read as "resting", never as "a minor third flat".

| Glyph | Value | Notes |
|---|---|---|
| `_` | lane **rest** value (bend `0st`, press `0`, timbre `0.5`) | the visual floor means at rest |
| `v` | lane **min** (bend `-range`, press `0`, timbre `0`) | the explicit all-the-way-down |
| `-` | lane centre (`0` on a bipolar lane, the midpoint of the range on a unipolar one) | a **level**, never a hold |
| `^` | lane max | |
| `/` | ramp from previous anchor to lane max across this slot | with no previous anchor it departs from **rest**, not centre (§7.2) |
| `\` | ramp from previous anchor to lane min across this slot | same rule at a bar start or after a gap |
| `V` | same as `v` (accepted so a lane may be typed in caps) | |
| `0`–`9` | explicit level, `0` = min, `9` = max | |
| `~` | wiggle: sine around the running value, lane-default rate/depth | `~5` = depth 5/9 |
| `x` | hold previous value flat | holds **rest** when nothing is running yet |
| `.` | no data (lane is *not* written here) | whitespace is a separator and yields no anchor at all |
| `>` | **harmonic resolve**: glide from the current value to the value that puts the sounding note on the target pitch. `>` alone = nearest guide tone of the *next* chord; `>3`/`>5`/`>7`/`>9` = that chord tone (`>root`, `>third`, `>fifth`, `>seventh` are spelled-out aliases for `>1`/`>3`/`>5`/`>7`); `>+` / `>-` = next/previous scale degree; `>|` = next note in this lane. Only valid on `bend`. |
| `(...)`, `[...]`, `*n` | grouping/subdivision/repeat, same as note lanes | |
| `name(args)` | inline gesture call occupying this slot | |

**Per-lane glyph values.** `v`, `_`, `-` and `^` are lane-relative: the same glyph is a
different number on a different lane, and the coincidences between them differ per lane too.
The values are those the implementation uses (`LANE_RANGES` in `ir.py`, `LANE_RESTS` and
`GestureCtx.center` in `gesture.py`):

| Lane | range | min `v` / `V` | rest `_` | centre `-` | max `^` |
|---|---|---|---|---|---|
| `bend` | `-2st .. +2st` (`!range`, `@lane-range`) | `-2st` | `0st` | `0st` | `+2st` |
| `press` | `0 .. 1` | `0` | `0` | `0.5` | `1` |
| `timbre` | `0 .. 1` | `0` | `0.5` | `0.5` | `1` |
| `amp` | `0 .. 1` | `0` | `0.5` | `0.5` | `1` |
| `pan` | `0 .. 1` | `0` | `0.5` | `0.5` | `1` |
| `cc<n>` | `0 .. 1` | `0` | `0` | `0.5` | `1` |

Read off the table:

- `bend` is the only **bipolar** lane. There `_` and `-` are the same value, `0st`, so a drawn
  floor is always in tune, while `v` is a whole tone down at the default range. Write `v` when a
  real downward bend is wanted.
- On `press` and on every `cc<n>` lane `_` and `v` are the same value, `0`, because those lanes
  rest at their minimum.
- On `timbre`, `amp` and `pan` `_` and `-` are also the same value, `0.5`: those lanes rest at
  the midpoint of their range. `_` and `-` differ **only** on `press` and `cc<n>`.
- Widening a `bend` lane with `!range=<n>st` moves `v`, `\`, `^`, `/` and every digit level, but
  not `_`: rest stays at `0st`.
- Digits span the range, not the distance from rest: `0` = min, `9` = max,
  `k` = min + (k/9) × (max − min). On `bend` at the default `±2st` that puts `4` at −0.22 st and
  `5` at +0.22 st, so no digit is exactly rest.

**`-` means three different things**, one per lane kind: a tie in `notes` (§5), "sustain the
previous chord" in `harm` (§4), and the lane centre in a curve lane. `press | -----^^ |` reads
like "sustain five times" and is not: it sits at `0.5` for five anchors and then rises. `-`
never holds in a curve lane; it is a level. The spelling for "hold the running value" is `x`,
and the spelling for "write nothing here" is `.`.

```
@key C minor
stave drawn {
  harm           | i9      | iv11    |
  notes          | 0 2 3 5 | 7 - - - |
  bend!range=8st | _v__    | __x>3   |   # rest, a real dip, rest; hold, then resolve
  press          | _-^-    | ^x__    |   # 0, 0.5, 1, 0.5; max, held, back to 0
}
```

**A `>` with no next chord.** `>` and `>3`/`>5`/`>7`/`>9` look forward for the next `harm`
segment that carries a chord. In the final bar there is none, and the target then falls back to
the **current** chord, silently: in the last bar `bend | __>3 |` bends into the third of the
chord already sounding. Only when the stave has no chord at all is the target dropped, with a
warning and no bend written. `>|` behaves the same way on the last note of a lane: with no next
note to aim at it resolves to the note's own pitch, i.e. no bend. `>+` and `>-` are scale steps
rather than chord lookups, so they never need a fallback.

An empty **bar** (`| |`) writes no data for the whole bar. A lane that is entirely absent
writes no data at all (so an unspecified lane never fights the DAW's own defaults) — see §7.2.

### 7.1 Note-scoped semantics (the load-bearing rule)

Lane time is bar time. When a lane value is emitted, it is written **to every MPE member
channel that currently holds a sounding note of that stave** (or of that voice, for `@voice`
lanes). Because each note owns its channel, the same drawn curve becomes a genuinely
*per-note* curve, and two notes that start at different times inside the same drawn shape each
receive the portion of the shape that overlaps their own lifetime.

Two lane time modes make this explicit:

- `!time=bar` (default) — glyphs are absolute in bar time, as above.
- `!time=note` — the whole lane content is **re-normalized to each note's lifetime**, so
  `press!time=note | /^\ |` gives *every* note its own swell regardless of length.

`!time=note` is what makes a one-line articulation apply to a whole phrase.

### 7.2 Absent, empty, and held

Three things that look alike in a score are three different instructions:

| Written | Meaning | What reaches the output |
|---|---|---|
| the lane does not appear in the stave | the lane is never written | no events for it at all, so it cannot fight the instrument's or DAW's own value |
| `.` on the lane, or an empty bar `\| \|` | an anchor that carries **no data** | a gap: nothing is emitted across it, and the receiver keeps whatever value it last had |
| `x` | hold the running value flat | data *is* emitted: the value is pinned where it was |

Whitespace is neither of these — on a curve lane it is a separator and yields no anchor (§3.1).

A gap also clears the running value. The first anchor of a lane's bar, and the first anchor
after a gap, has nothing to depart from, so `/`, `\`, `x` and `~` there start from the lane's
**rest** value — not its centre and not its minimum. `press | /^^^ |` at the start of a bar
begins at `0`; `bend | /^^^ |` begins at `0st`; `bend | ~~~~ |` wiggles symmetrically about
`0st`.

**The note-on reset.** MPE mandates a preamble on the member channel before every note-on:
pitch bend, then CC74, then channel pressure. Filigree emits it for every note, so for those
three dimensions a lane the bar does not write is reset to its rest value at note-on — bend to
`0st`, `timbre` to CC74 64 (the `0.5` rest, RP-053's initial value), `press` to `0`. No note
inherits another note's bend, brightness or pressure.

The remaining lanes have no mandated preamble: `amp` (CC11), `pan` (CC10) and every `cc<n>` are
emitted only where the lane has data. Where the bar writes nothing, nothing is sent and the
member channel keeps the value it last received, which may have been set by an earlier note on
that channel. Draw those lanes explicitly if you need them neutral at note-on.

## 8. Gestures — first-class expression values

```
gesture cry  = bend(0 -> -0.7st -> 0, shape: ease)
gesture warm = press(0.2 -> 0.9, shape: exp) | timbre(0.4 -> 0.7)
gesture vibr(rate: 5.2hz, depth: 0.3st, onset: 30%) =
          bend(wiggle(rate, depth) @ onset..100%)
gesture cry2 = cry * 1.4 >> vibr(rate: 6hz)
gesture fall = bend(0 -> >3)          # harmonic target inside a gesture
```

Primitives, all note-lifetime-normalized (`0%`..`100%` of the note):

- `bend(...)`, `press(...)`, `timbre(...)`, `amp(...)`, `cc<n>(...)`
- breakpoints: `a -> b -> c` with optional `@ pos` placement (`0 -> -0.7st @ 40% -> 0`)
- `wiggle(rate, depth, phase?)`, `drift(depth, rate?)` (smooth noise), `ramp(a,b)`,
  `pulse(rate, duty)`, `curve("_/^\_")` (glyph string as a gesture)

Algebra:

| Op | Meaning |
|---|---|
| `a + b` | sum, per lane |
| `a * k` | scale amplitude (`k` scalar) |
| `a * b` | multiply/AM per lane |
| `a >> b` | sequence: `a` over the first half of the note lifetime, `b` over the second (`a >>(30%) b` to split elsewhere) |
| `a \| b` | parallel across different lanes |
| `a @ x..y` | restrict to a window of the note lifetime |
| `-a` | invert |

Numeric arguments need a leading zero: `0.5`, `0.3st`. A leading-dot literal (`.5`) is a hard
error — `.` is the no-data glyph, so it is never read as part of a number.

### 8.1 Attachment and precedence

A gesture reaches a note in one of four ways:

1. **note-level** — `3!cry` on a `notes`/`voices` token; several may be chained, `3!cry!vibr`.
2. **inline in a curve lane** — `name(args)` written as an anchor of that lane, which occupies
   its own slot: `bend | __ vibr(depth: 0.4st) |`.
3. **lane-level** — `notes!gesture=cry`, or per voice `voices!gesture@lead=cry`, on a
   note-bearing lane.
4. **stave-level** — `gesture cry` in a `stave` or `part` header: every note of that stave.

There is no `@gesture` directive; a gesture is made document-wide by naming it in each stave
header. `!gesture=` on a *curve* lane parses but attaches nothing (§3.2).

For each lane, the sources of data are consulted in this fixed priority order:

| Priority | Source |
|---|---|
| 1 | glyphs drawn on a voice-suffixed curve lane (`press@lead`) |
| 2 | glyphs drawn on the unsuffixed curve lane (`press`), including its inline `name(args)` calls |
| 3 | note-level `!gesture` on the token — leftmost first when several are chained |
| 4 | lane-level `!gesture=` / `!gesture@<voice>=` scoped to this note's voice |
| 5 | lane-level `!gesture=` with no voice scope |
| 6 | stave-level or `part`-level `gesture <name>` |

Attachments do **not** sum. At every instant of every lane, the highest-priority source that has
data there wins outright, and a lower-priority source is heard only where the ones above it are
silent — a `.`, an empty bar, a window the gesture does not cover. So explicit lane glyphs
always win over an attached gesture on the same lane and window, a note-level `!gesture`
overrides a lane-level one for that note, and a lane-level one overrides the stave header. A gap
in a drawn lane is the way to let a lower-priority gesture through.

A gesture that writes lanes the score does not draw is unaffected by any of this: it simply
supplies those lanes.

## 9. Feel — declarative humanization (deterministic)

```
feel loose  = { timing: 14ms gauss, velocity: 8%, gate: 5%, seed: 3 }
feel pushed = { timing: -8ms flat on: 2,4 }        # laid-back/pushed per beat
feel breath = { onset: 12ms per-voice-spread, release: 20ms }
```

Applied `stave x { feel loose ... }` or `@feel loose`. All randomness is drawn from a
counter-based hash of `(@seed, stave, bar, slot, voice, field)` — so output is bit-identical
across runs and a change in bar 9 does not perturb bar 3.

## 10. Parts and reuse

```
part hook {
  notes | 0 . 2 3  | 4 - - 2  |
  bend  | ___/^^^^ | ^^\_____ |
}

stave lead {
  harm | i9 | VI^7 | iv11 | V7alt |
  play hook
  play hook >> transpose(3) >> retro
}
```

Phrase transforms: `transpose(n)`, `retro`, `invert(axis?)`, `rot(n)`, `stretch(k)`,
`humanize(feel)`, `every(n, f)`, `mask("1 0 1 1")`, `euclid(3,8)`, `voiceswap(a,b)`.

## 11. Output

- `filigree render x.fil -o x.mid` — SMF type 1, MPE lower zone (master ch 1, members 2–16),
  MPE Configuration Message + per-member RPN 0 bend range, one track per stave.
- `filigree play x.fil --port "IAC Driver Bus 1"` — realtime, virtual port by default.
- `filigree watch x.fil` — recompile + replay on save.
- `filigree explain x.fil` — prints the resolved harmony, voicings, and per-note gesture
  summary as a table (the "did I mean that?" pass).

## 12. Errors

Every diagnostic carries `file:line:col`, the offending token, and a suggestion. Lane
misalignment (e.g. a `bend` bar whose anchor count is not a divisor/multiple of the `notes`
bar's slot count) is a **warning**, not an error -- the lane is resampled and the warning names
both counts, saying `anchors` for a curve lane and `slots` for a note-bearing one so the two can
never be confused. The warning fires whenever the ratio is not an integer multiple or divisor;
it is suppressed only when the resampling is exact, and on a curve lane carrying `!time=note`,
whose content is re-normalised per note (§7.1) so bar columns are not what it means.

An **unknown or malformed chord symbol is a hard error**, never a warning: a typo must not
silently delete a bar of music. `filigree render --lenient` downgrades it to a warning and
sustains the previous chord instead, for live-coding sessions where stopping is worse.

`--lenient` is a **parser** mode as well as a resolver mode (round-3 amendment): the
recoverable token-level errors are all detected while parsing, so leniency has to apply
there or the flag does nothing for the cases it exists for. Leniently:

| Mistake | Substitution |
|---|---|
| unknown chord symbol (`Hm7`, `Zqx9`) | that bar sustains the previous chord |
| malformed pitch-set member (`{0 3 zz}`) | the member is dropped from the set |
| unknown curve glyph (`_Q_`) | that slot carries no curve data |

Each substitution emits a warning naming the offending token, what was done instead, and
`(--lenient)` so the log makes clear it was a downgraded error. **Structural** errors -- an
unclosed `{`, a lane with no name, an unbalanced `<` -- remain hard in both modes, because
no inert substitution exists for them.
