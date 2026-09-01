# Filigree — architecture contract

Read this before touching any file. Read `docs/SPEC.md` for language semantics,
`research/mpe_technical.md` for MPE facts, `refs/BAR.md` for the quality bar.

## Hard rules for every agent

1. **You may only create/edit the files listed under your own piece.** Someone else is editing
   the others right now. If you need a change in a file you do not own, report it in your
   summary instead of editing it.
2. `src/filigree/ast_nodes.py`, `src/filigree/ir.py`, `src/filigree/errors.py` are **frozen
   contracts** owned by the lead. Import them; never edit them.
3. Pure standard library + `numpy` for compute, `mido` for MIDI file output, `python-rtmidi`
   (optional, import lazily inside a function) for realtime. **No other dependencies.**
   Never run `pip install` of anything else. Python 3.11+ compatible syntax.
4. Every module must import and pass `python -m pytest tests/ -x -q` for its own test file.
   Write your tests in the test file you own. Do not weaken another piece's tests.
5. Run `python -m py_compile` on every file you edit before returning.
6. No network access at runtime in library code.
7. Determinism: given the same source and `@seed`, output must be byte-identical.

## Ownership table

| Piece | Owner files | Tests |
|---|---|---|
| P1 parser | `src/filigree/lex.py`, `src/filigree/parse.py` | `tests/test_parse.py` |
| P2 harmony | `src/filigree/theory.py`, `src/filigree/voicing.py` | `tests/test_theory.py`, `tests/test_voicing.py` |
| P3 gestures | `src/filigree/gesture.py` | `tests/test_gesture.py` |
| P4 MPE render | `src/filigree/mpe.py`, `src/filigree/realtime.py` | `tests/test_mpe.py` |
| P5 feel | `src/filigree/feel.py` | `tests/test_feel.py` |
| P6 playground | `web/**` | `tests/test_web.py` |
| lead | `ast_nodes.py`, `ir.py`, `errors.py`, `resolve.py`, `cli.py`, `server.py`, `examples/**`, docs | `tests/test_integration.py` |

## Data flow

```
source .fil
  → lex.py       tokens
  → parse.py     Document (ast_nodes)
  → resolve.py   Score (ir)          ← calls theory/voicing/gesture/feel
  → mpe.py       MidiFile / event list
  → realtime.py  live MPE output
  → ir.Score.to_json() → web/ playground
```

## Module APIs (exact signatures — do not deviate)

### P1 `lex.py` / `parse.py`

```python
def tokenize(src: str, path: str = "<input>") -> list[Token]        # lex.py
def parse(src: str, path: str = "<input>") -> Document              # parse.py
```

`Token` is a dataclass `(kind: str, text: str, line: int, col: int)` defined in `lex.py`.
`parse` raises `errors.ParseError` for hard errors and appends strings to `Document.warnings`
for soft ones. `parse` is responsible for:

* directives → `Document.directives` with normalised values:
  `tempo: float`, `meter: (int,int)`, `key: (int, str)` (tonic pitch class 0-11, lowercase mode
  name), `ppq: int`, `bend_range: float`(semitones), `grid: float`(ms), `seed: int`,
  `title: str`, `voicing: str`, `feel: str`
* `gesture` / `feel` / `voicing` / `part` / `stave` blocks
* lane splitting on `|`, slot tokenisation, `[...]` groups, `<...>` alternations, `x*3`,
  `[: ... :4]` expansion, sticky octave/velocity/gate state per lane
* full gesture-expression parsing into the `ast_nodes` expression tree, including precedence:
  `|` (lowest) < `>>` < `+ -` < `*` < unary `-` < `@window` < postfix call (highest)
* attaching `!gesture` / `:v90` / `%50` / `'` / `,` / `?` decorations to the owning `Slot`
* mapping curve glyph characters to `Slot(kind="glyph", glyph=..., glyph_arg=...)` and `>`
  targets to `Slot(kind="glyph", target=Target(...))`

Parse must never resolve pitches to MIDI numbers, never look at `@key` semantics beyond
storing it, and never evaluate gestures.

### P2 `theory.py`

```python
MODES: dict[str, tuple[int, ...]]                 # mode name -> semitone offsets from tonic
NOTE_NAMES: dict[str, int]                        # "C"->0 ... "B"->11

@dataclass
class Chord:
    root_pc: int                  # 0..11
    quality: str                  # canonical: "maj","min","dom7","min7","maj7","min9",...
    intervals: tuple[int, ...]    # semitones above root, root included as 0
    bass_pc: int | None
    symbol: str                   # as written
    def pitch_classes(self) -> list[int]
    def guide_tones(self) -> list[int]   # pitch classes: 3rd & 7th (or 3rd & 6th/5th fallback)
    def degree_pc(self, degree: int) -> int | None   # degree in {1,3,5,7,9,11,13}

def parse_roman(sym: str, tonic_pc: int, mode: str) -> Chord
def parse_absolute(sym: str) -> Chord
def scale_pitches(tonic_pc: int, mode: str) -> list[int]
def degree_to_pitch(degree: int, tonic_pc: int, mode: str, octave: int = 4,
                    accidental: int = 0) -> int
def nearest_pc(target_pc: int, from_pitch: int) -> int   # nearest MIDI pitch with that pc
```

`parse_roman` must handle: case→quality, `b`/`#` prefixes, extensions
`6 7 9 11 13 ^7 0 o7 sus2 sus4 add9 6/9 alt x`, alterations `b5 #5 b9 #9 #11 b13`,
secondary dominants `V/ii`, and modal-interchange suffix letters
`n d f y m a l h e` (see SPEC §4). Unknown symbol → `errors.HarmonyError` with a suggestion.

### P2 `voicing.py`

```python
@dataclass
class VoicingSpec:
    low: int = 48; high: int = 72; mode: str = "smooth"; size: int | None = None
    drop: int = 0; spread: float = 1.0; top: str | None = None

def voice_chord(chord: Chord, spec: VoicingSpec,
                previous: list[int] | None = None,
                melody_pc: int | None = None) -> list[int]
```

`mode="smooth"` must minimise total voice movement from `previous` (assignment problem over
candidate octave placements; document the cost function). Result is sorted ascending, all
pitches within `[low, high]` where possible, bass note honoured if `chord.bass_pc` is set
(bass may go below `low` by up to an octave).

### P3 `gesture.py`

```python
@dataclass
class Segment:            # a resolved curve on ONE lane, in note-lifetime space
    lane: str
    fn: Callable[[np.ndarray], np.ndarray]   # t in 0..1 -> lane value
    window: tuple[float, float] = (0.0, 1.0)

@dataclass
class Gesture:
    segments: list[Segment]
    def lanes(self) -> set[str]
    def sample(self, lane: str, t: np.ndarray) -> np.ndarray | None

class Env:                # gesture definitions + parameter bindings
    def __init__(self, defs: dict[str, GestureDef], params: dict | None = None)
    def child(self, params: dict) -> "Env"

def eval_gesture(expr: GestureExpr, env: Env, ctx: "GestureCtx") -> Gesture

@dataclass
class GestureCtx:
    """Everything a gesture needs that comes from the score."""
    lane_default: str | None = None      # lane implied by the enclosing lane
    lane_range: tuple[float, float] = (-2.0, 2.0)
    tempo: float = 120.0
    note_dur_beats: float = 1.0
    seed_key: tuple = ()
    resolve_target: Callable[["Target"], float] | None = None   # -> lane value

def glyphs_to_gesture(glyphs: list[tuple[float, float, "Slot"]], lane: str,
                      ctx: GestureCtx, shape: str = "ease") -> Gesture
```

`glyphs_to_gesture` receives `(start_frac, end_frac, slot)` triples in **lane-local
normalised time** and returns a `Gesture` with one segment covering `0..1`. It implements the
glyph table in SPEC §7 including `/ \ ~ x` semantics that depend on the running value, and
calls `ctx.resolve_target` for `>` targets. Unspecified (`empty`) regions must produce `NaN`
so the resolver can skip writing data there — this is load-bearing (SPEC §7 "no data").

Interpolation shapes: `ease` = smoothstep, `linear`, `hold` = step, `exp`, `snap` = jump at
the anchor. `wiggle` is `sin`, phase 0 at window start; `drift` is seeded value-noise
(deterministic from `ctx.seed_key`).

### P5 `feel.py`

```python
@dataclass
class FeelSpec:
    timing_ms: float = 0.0; timing_dist: str = "gauss"; velocity: float = 0.0
    gate: float = 0.0; onset_ms: float = 0.0; release_ms: float = 0.0
    on_beats: tuple[int, ...] = (); seed: int = 0

def hash01(*parts) -> float        # counter-based, deterministic, uniform 0..1
def gauss(*parts) -> float         # deterministic standard normal
def apply_feel(notes: list[Note], spec: FeelSpec, tempo: float, seed: int) -> None
```

`apply_feel` mutates `Note.start/dur/velocity` in place. Randomness must come only from
`hash01`/`gauss` keyed by `(seed, note.stave, note.voice, round(note.start,4), note.pitch,
field)` so a change in one bar cannot perturb another.

### P4 `mpe.py`

```python
@dataclass
class MpeOptions:
    bend_range: float = 48.0; ppq: int = 960; grid_ms: float = 10.0
    pitch_grid_ms: float = 5.0; deadband_lsb: int = 2
    members: tuple[int, ...] = tuple(range(1, 16))    # 0-based channels 1..15 == MIDI 2..16
    emit_config: bool = True; one_track_per_stave: bool = True

def allocate_channels(score: Score, opts: MpeOptions) -> None
def render_midifile(score: Score, opts: MpeOptions | None = None) -> "mido.MidiFile"
def render_events(score: Score, opts: MpeOptions | None = None) -> list[tuple[float, list[int]]]
    # (beat, raw midi bytes) — used by realtime.py and tests
def write_midi(score: Score, path: str, opts: MpeOptions | None = None) -> None
```

Must follow `research/mpe_technical.md` exactly: MCM on channel 1 (RPN 00 06 = 15), member
RPN 0 bend range on every member channel, null-RPN close, per-note order
`bend → CC74 → pressure 0 → note-on`, `pressure 0` before `note_off`, no expression data after
note-off, channel allocation by fewest-active-notes with oldest-release tie-break and
same-pitch affinity, 2-LSB deadband + dedup thinning.

### P4 `realtime.py`

```python
def list_ports() -> list[str]
def play(score: Score, port: str | None = None, opts: MpeOptions | None = None,
         loop: bool = False, on_event: Callable | None = None) -> None
```

Lazy-import `rtmidi`/`mido`; open a virtual port named `"Filigree"` when `port is None`;
schedule with a monotonic clock; flush all-notes-off + pressure 0 on exit/KeyboardInterrupt.

### P6 `web/`

A zero-build static app: `web/index.html`, `web/app.js`, `web/style.css`, `web/synth.js`,
optional `web/editor.js`. It fetches `POST /api/compile {source: string}` → `Score.to_json()`
(schema in `ir.py:Score.to_json`) and `POST /api/midi` → binary SMF. During local dev the
backend is `server.py` (lead-owned, stdlib only) on port 8787; the front end must read its
base URL from `window.FILIGREE_API || ''` so it works behind a proxy.

Front end responsibilities: code editor with Filigree syntax highlighting and lane-aware
monospace alignment, transport, a piano-roll that draws **the actual bend/press/timbre curves
inside each note rectangle**, chord ribbon above the roll, an MPE-aware WebAudio synth
(one voice per note, per-note detune/pressure/timbre applied), keyboard shortcut to recompile
(Cmd/Ctrl+Enter), and error/warning display with line numbers. Dark, precise, low-chrome.
