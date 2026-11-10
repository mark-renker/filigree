# Start here

Two minutes to sound. The full walkthrough — requirements, platform notes,
troubleshooting — is in [README.md](README.md).

## 60 seconds to sound

```bash
git clone https://github.com/mark-renker/filigree.git
cd filigree
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

filigree serve                 # → http://localhost:8787
```

The playground opens with an 8-bar C-minor study already loaded. Hit **play**,
then change a glyph in the source pane and hit **compile** (⌘↵ / Ctrl↵). The
piano roll draws the per-note bend, pressure and timbre curves on top of the
notes, so you can see the expression, not just hear it.

Use the virtual environment rather than your system Python. Many system Pythons
have no `numpy`, and recent macOS and Debian/Ubuntu refuse `pip install` into
them outright.

## Then get it into a DAW

```bash
filigree render examples/nocturne.fil -o nocturne.mid
```

That `.mid` is MPE over MIDI 1.0 with a proper lower-zone configuration message,
so it loads into Bitwig, Ableton 11+, Logic 10.7+ and Cubase without touching
anything. Every note gets its own channel, its own bend, its own CC74 and its own
channel pressure.

To play live instead, you need `python-rtmidi` and a virtual MIDI port:

```bash
pip install -e ".[realtime]"
filigree ports
filigree play examples/nocturne.fil --port "IAC Driver Bus 1"
```

On macOS the IAC Driver is off by default — enable it in **Audio MIDI Setup ▸
Window ▸ Show MIDI Studio ▸ IAC Driver ▸ Device is online**. On Windows use
loopMIDI. If the `pip install` fails with `sem_timedwait`, that is JACK; the
README has the one-line fix.

## What is different about it

The one-line version: **expression is a note-scoped curve that you draw in ASCII
directly under the notes, and its endpoints can be harmonic rather than numeric.**

```
@tempo 84bpm
@key C minor
voicing warm = { range: C3..C5, mode: smooth, size: 4, drop: 2, top: melody }

stave lead {
  harm!voicing=warm | i9       | VI^7     | iv11     | V7alt     |
  notes             | 0 . 2 3  | 4 - - 2  | ~5 4 . 2 | 1 - - -   |
  bend!range=3st    | ___/^^^^ | ^^\_____ | ........ | __/\___>3 |
  press             | /^^^\___ | -----^^^ | __/^^^^^ | ^^^^\___  |
}
```

`>3` at the end of bar 4 does not mean "bend up two semitones". It means *glide
into the third of the next chord* — so when you rewrite the progression, the
gesture follows it. Timing is slot-inferred (the number of items you type in a
bar sets its subdivision), which is what makes the columns line up at all: you
never write durations.

## Try these, in this order

```bash
filigree explain examples/front_page.fil      # see what the compiler decided, and why
filigree explain examples/blue_iron.fil       # harmonic bend targets doing real work
filigree explain examples/gesture_algebra.fil # gestures composed with + - * >> | @window
filigree render examples/nocturne.fil -o out.mid
```

`explain` is the one to reach for when something sounds wrong. It prints the
resolved chord for every bar, then every note with its pitch, velocity, voice and
the actual range each curve covers — including where a `>` target landed.

While you are sketching, add `--lenient`: an unknown chord symbol, a malformed
pitch set or an unknown glyph become warnings with an inert substitution instead
of exit 2, so a half-typed file still plays. Structural mistakes stay hard errors.

## Where things are

| Path | What |
|---|---|
| `README.md` | the argument, the full install walkthrough, the CLI, the scoreboard |
| `docs/SPEC.md` | the language, normatively |
| `docs/ARCH.md` | module boundaries and the frozen contracts between them |
| `examples/` | 8 example pieces |
| `src/filigree/` | the compiler: `lex → parse → theory/voicing → gesture → feel → resolve → mpe/realtime` |
| `web/` | the playground (no build step, no dependencies, plain JS) |
| `tests/` | 859 tests |
| `status/gauntlet-status.html` | the build record — every round, every verdict, with reasons |

Known limits, so you do not discover them the hard way: a lane must be one line
(no continuation), `[: :8]` repeat blocks do not expand bars reliably, note-lane
anchors are `@root`/`@guide`/`@high`/`@low` only, and `>` targets are valid on
`bend` lanes only.

## Running the tests

```bash
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest          # 858 passed, 1 skipped
```

Worth knowing what they cover, because it is not just unit tests: MPE output is
checked against RP-053 by a machine audit (26 of 26 conformance checks), harmony
is checked against music-theory ground truth, the playground's curve overlay is
checked for sub-pixel alignment against the piano roll, and every fenced code
block in the README and the spec is compiled and required to produce zero
warnings — so the documentation cannot drift from the language.
