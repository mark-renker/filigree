# NOTES — P1 (lexer + parser)

Owner files: `src/filigree/lex.py`, `src/filigree/parse.py`, `tests/test_parse.py`.
`python -m pytest tests/test_parse.py -q` → **78 passed**, 257 assertions,
22 error-case tests. `python -m py_compile` clean on all three files.

---

## 1. SPEC ambiguities / contradictions and how I resolved them

### 1.1 Whitespace inside a curve lane (SPEC §7, glyph table row "` `")

SPEC lists a literal space as a glyph meaning "no data", but SPEC §3.1 also makes
whitespace the **slot separator**. Both readings are defensible for
`bend | __  ^^ |`.

**Resolved:** in curve lanes whitespace is *structural* — each space character
inside a bar is exactly one `Slot(kind="empty")`. This is the reading that makes
the "curves are drawn as text, column-aligned with the notes" thesis work, and it
is the only one under which `press | __  ^^ |` can express "no data on slots 3-4".
Leading/trailing whitespace inside a bar (i.e. next to `|`) is padding and is
trimmed, so `| ___/^^^ |` is 7 slots, not 9.

**Consequence:** multi-character curve items (`~5`, `>3`, `[_^]`, `x*3`,
`vibr(0.3)`) must be written *adjacent* to their neighbours, e.g.
`bend | _vibr(depth: 0.5st)^ |` and `bend | [_^]x*3 |`. Spaces around them create
empty slots. This is consistent but worth a sentence in SPEC §7.

### 1.2 The SPEC §3 showcase example emits 8 alignment warnings

SPEC §12 says a lane bar whose slot count is not a divisor/multiple of the `notes`
bar is a warning. In the flagship example of SPEC §3 the curve rows are 7 or 9
glyphs wide against a 4-slot `notes` row (`___/^^^` is 7 characters, not 8), so a
literal implementation warns on nearly every lane.

**Resolved:** I implemented SPEC §12 literally (warning, never an error, naming
both counts and the lane names, with `file:line:col`). I only warn when the counts
are *neither equal nor in a divisor/multiple relationship* — warning on every
inequality would flag the perfectly ordinary `notes | 0 2 3 5 | / bend | ________ |`.

**Recommended docs change (lead-owned):** pad the glyph rows in the SPEC §3
example to 8 characters (e.g. `___/^^^^`, `/^^^\\___`, `---^^^--`) so the language's
showcase snippet is warning-free. `tests/test_parse.py::test_spec3_example_parses`
and friends parse the example verbatim as it stands today and assert that it
warns rather than errors, so the change is safe either way.

### 1.3 `x*3` — expand or keep a `repeat` count?

ARCH lists `x*3` under parse's responsibilities next to "`[: ... :4]` expansion",
while `Slot.repeat` is documented as "from ``x*3``".

**Resolved:** both. `x*3` expands to 3 sibling slots (so slot counts are correct
for every consumer that just walks the list) **and** every one of those slots
carries `repeat=3` as provenance. Consumers must therefore *not* re-multiply by
`Slot.repeat`. `[: a b :4]` expands into a single `Slot(kind="group")` whose
children are the fragment repeated 4 times, with `repeat=4` recorded.

### 1.4 `.../E` and `/3` in SPEC §4

`.../E` is prose ("any symbol, slashed"), not syntax; a bare `/3` slot has no
symbol to take a third from. **Resolved:** slash bass is parsed off the end of a
symbol — `Dm7/A` → `bass="A"`, `i9/3` → `bass="3"`. `V/ii` (secondary dominant)
and `C6/9` (extension) are left inside the symbol string for `theory.py`.
A bare `/3` is a parse error with a suggestion.

### 1.5 Roman vs absolute chord spelling

`iiid` (modal interchange) and `Bb7` both start with letters that could be read
either way. **Resolved:** a symbol is roman iff, after optional `b`/`#`
prefixes, it starts with a maximal roman numeral (`i ii iii iv v vi vii` in either
case) *not* followed by another `i`/`v`/`I`/`V`. So `iiid` → roman `iiid`,
`Bb7` → absolute, `IV^7` → roman, `Bsus4` → absolute.

### 1.6 `#` as comment vs accidental

SPEC §0 says comments start with `#`; SPEC §4/§5 use `#4`, `#iv`, `#11`, `F#7`.
**Resolved:** `#` opens a comment only when it is at line start or preceded by
whitespace **and** followed by whitespace/end-of-line. Never inside a string.

### 1.7 Octave prefixes are absolute, not relative

SPEC §5: "`^0 _0` octave shift, sticky per-lane until changed (`^^3` = two octaves
up)". **Resolved:** the prefix count *sets* the lane's sticky octave (`^^3` → +2,
`_3` → −1, and a following bare `5` keeps the last value). Only `!reset` returns
it to 0 — there is no "shift by one more" form.

### 1.8 `!reset` placement

SPEC §5 only says "Reset with `!reset`". **Resolved:** accepted both as a
standalone lane token (consumes no slot) and as a decoration (`3!reset`, which
clears sticky velocity/gate for that note onward).

### 1.9 `>` targets vs `<...>` alternation

`>` is both a harmonic target and the closer of `<a b c>`. **Resolved:** a `>`
closes the innermost open `<`; otherwise it is a target. `>|` ("next note in this
lane") is lexed as part of its chunk so it is not mistaken for a bar separator.
`>` on a non-`bend` lane is a hard error (SPEC §7: "Only valid on `bend`").

### 1.10 `@` overloading

`@` is a directive marker, the window operator, an anchor prefix (`@low`) and the
lane voice suffix (`press@lead`). **Resolved** contextually: line-initial `@ident`
is a directive; inside a lane header it is the voice; inside a note token it is an
anchor; inside an expression it is the window operator. `!gesture@lead=cry` keeps
the `@lead` inside the option key (key = `"gesture@lead"`) because the `@`
precedes the `=`.

### 1.11 Breakpoint `@ pos` vs the window operator

`bend(0 -> -0.7st @ 40% -> 0)` and `bend(wiggle(r,d) @ 30%..100%)` both use `@`.
**Resolved:** an argument is parsed as `Breakpoints` iff it contains a top-level
`->`; inside a breakpoint value the window operator is disabled, so `@` there is
always a placement. Otherwise `@ a..b` is a `Window`.

### 1.12 One-line blocks

`stave a { notes | 0 | }` is natural but mixes generic and lane lexing on one
line. **Resolved:** the lexer splits a `stave`/`part` line at `{` when the
remainder starts with a lane name, and emits the trailing `}` separately.
Multi-line `voices | { ... ; ... }` blocks are joined while brackets are open.

---

## 2. Choices worth recording (not ambiguities)

* **Directive defaults are pre-populated** into `Document.directives` from the
  SPEC §2 table (`tempo` 120.0, `meter` (4,4), `key` (0,"major"), `ppq` 960,
  `bend_range` 48.0, `grid` 10.0, `seed` 0), so downstream never needs `.get`
  with a duplicated default. `@bend-range` → key `bend_range`, `@lane-range` →
  `lane_range`, `@title`/`@voicing`/`@feel` as written.
* **Middle C = 60.** `C4` → 60, so `voicing warm { range: C3..C5 }` yields
  `low=48, high=72`. Absolute pitch literals *are* converted (the contract's
  `PitchTok.midi` and `VoicingSpec.low/high` are ints); scale degrees, chord tones
  and anchors are never resolved, per ARCH.
* **`FeelDef.fields` normalisation** (for `feel.py`): `timing` → float ms,
  `timing_dist` → `"gauss"`/`"flat"`, `velocity`/`gate` → fractions (`8%` → 0.08),
  `onset`/`release` → float ms plus `onset_mode`/`release_mode` for a trailing word
  such as `per-voice-spread`, `on` → `tuple[int, ...]`, `seed` → int.
* **`VoicingDef.fields`** carries both `range=("C3","C5")` and `low`/`high` ints,
  plus `mode`, `size`, `drop`, `spread`, `top` — a direct kwargs match for
  `voicing.VoicingSpec`.
* **String-valued kwargs.** `shape`, `dist`, `mode`, `top`, `time` are stored as
  plain `str`; every other bare identifier in an expression becomes a `Ref` (so
  `wiggle(rate, depth)` inside a `gesture` body refers to its parameters).
* **Soft diagnostics** appended to `Document.warnings`: slot-count mismatch,
  bar-count mismatch between lanes of one block, duplicate lane in one block,
  duplicate voice in one `voices` block, gesture redefinition. Everything else is
  a `ParseError` carrying `path`, `line`, `col`, `token` and a `suggestion`
  (suggestions use `difflib` against the real vocabulary, e.g. `@tmepo` →
  "did you mean 'tempo'?").

---

## 3. Changes I need in files I do not own

1. **`src/filigree/__init__.py` does not exist.** `filigree` currently works only
   as an implicit namespace package. `tests/test_parse.py` prepends `src/` to
   `sys.path` itself, but a `src/filigree/__init__.py` plus a root
   `pyproject.toml`/`conftest.py` (lead-owned) would make `import filigree` work
   for the CLI, the server and every other piece without path juggling.
2. **`docs/SPEC.md` §3 example glyph widths** — see §1.2 above: pad the `bend`,
   `press` and `timbre` rows to 8 glyphs so the showcase parses warning-free.
3. **`docs/SPEC.md` §7** — please state the whitespace rule chosen in §1.1
   ("one space = one empty slot; multi-character curve items are written
   adjacent") and add an explicit note that `>` is bend-only.
4. **`docs/ARCH.md`** — clarify the `Slot.repeat` contract (§1.3 above):
   consumers receive already-expanded sibling slots and must treat `repeat` as
   provenance only, not as a multiplier.
5. **`docs/SPEC.md` §4** — `.../E` reads as literal syntax; suggest rewriting as
   "`<symbol>/E`" and dropping the bare `/3` form or giving it an example
   (`i9/3`).
6. **`ast_nodes.py` (frozen, not edited):** two fields would remove guesswork
   downstream — a `Lane.time` (or documented `options["time"]`) for
   `!time=bar|note`, and a place for a lane's `@voice`-scoped option keys, which
   I currently encode as the literal option key `"gesture@lead"`. Also
   `Slot.probability` is a float while SPEC writes `?25` as a percentage; I store
   0.25.
