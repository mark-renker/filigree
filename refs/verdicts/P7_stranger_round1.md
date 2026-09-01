# P7 — Stranger Critic, Round 1

**Critic stance.** Experienced programmer, working musician, has never seen this
language or this repository. Read `README.md`, then `docs/SPEC.md`, then
`examples/`. Did **not** read `NOTES_*.md`, any other file in `refs/verdicts/`,
anything under `tests/`, or any `src/**/*.py`. Two files were written from
scratch during the session: `/tmp/stranger_first.fil` (README-only) and
`/tmp/stranger_second.fil` (post-SPEC).

Timestamps below are my own step counter (`S<n>`), one increment per shell
command batch, not wall-clock.

---

## Part 1 — Following README.md literally, top to bottom

### S1 — read `README.md`

Nothing to run yet. Two things I flagged before typing a command:

- README:60 — *"Dependencies are `numpy`, `scipy` and `mido` — nothing else."*
- README:11–18 — the headline example. It shows `harm!voicing=warm` but never
  shows a `voicing warm { ... }` declaration, and it shows bend/press lanes
  drawn with 7 glyphs against a 4-token `notes` lane.

### S2 — install, exactly as written (README:62–66)

```
cd filigree
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

**Result: worked.** Network was available, so the documented fallback
(`PYTHONPATH=src python -m filigree.cli --help`, README:71) was not needed.
Interpreter was Python 3.14.3 against a `requires-python = ">=3.11"`; no
problem.

> **DEFECT.** `pip` installed `packaging`, `numpy`, `mido`, `filigree`. It did
> **not** install `scipy`, because `pyproject.toml` does not list it.
> README:60 names a dependency the project does not have. Harmless to run,
> but it is the first factual claim in the install section and it is false.

### S3 — "First sound, in three commands" (README:76–86)

`filigree explain examples/nocturne.fil` — **worked**, and this is the best
thing in the repo. Resolved roman numerals to pitch sets, showed guide tones,
showed the chosen voicing, then a per-note table with pitch, velocity and a
compact per-lane curve summary including *where each bend lands*:

```
Nocturne for a small room   58 bpm  4/4  key=F# minor  mpe-bend=±48st  seed=11
    bar 1.00  i9         min9       [F# A C# E Ab]  guide[A E]  voiced[F#3 A3 E4 Ab4]
     12.020  3.904    68 Ab4    92 -   bend[-3.00..+0.00×30]→F4(-2.81st) ...
```

`filigree render examples/nocturne.fil -o /tmp/nocturne.mid` — **worked**:
`wrote /tmp/nocturne.mid  (25 notes, 16.00 beats, 2 stave(s), MPE lower zone)`.

`filigree ports` — **worked**, and the failure message is genuinely helpful:
```
no MIDI output ports found. On macOS enable the IAC Driver in
Audio MIDI Setup → Window → Show MIDI Studio → IAC Driver → 'Device is online'.
```
It exits 0 on "no ports", which is arguably wrong for scripting but is the
friendlier choice for a human.

`filigree new /tmp/starter.fil` — **worked**, and the starter it writes is a
better teaching artifact than the README's own headline example, because it is
complete and it compiles. The README never mentions that `new` exists until
the command table on line 121, i.e. *after* the section where a newcomer needs
it most.

### S4 — the README's own headline example, run verbatim

I pasted README:11–18 into `/tmp/readme_snippet.fil` and compiled it.

```
$ filigree explain /tmp/readme_snippet.fil
  /tmp/readme_snippet.fil:6:22: warning: in stave 'lead', bar 1: lane 'bend' has 7 anchors but lane 'notes' has 4 slots; 7 is not an integer multiple or divisor of 4, so lane 'bend' is resampled
  /tmp/readme_snippet.fil:7:22: warning: ... lane 'press' has 7 anchors but lane 'notes' has 4 slots ...
  /tmp/readme_snippet.fil:6:32: warning: ... bar 2: lane 'bend' has 7 anchors ...
  /tmp/readme_snippet.fil:7:32: warning: ... bar 2: lane 'press' has 7 anchors ...
  /tmp/readme_snippet.fil:7:42: warning: ... bar 3: lane 'press' has 7 anchors ...
  /tmp/readme_snippet.fil:6:52: warning: ... bar 4: lane 'bend' has 6 anchors ...
  /tmp/readme_snippet.fil:7:52: warning: ... bar 4: lane 'press' has 7 anchors ...
  /tmp/readme_snippet.fil:3:1: warning: unknown voicing 'warm'; using the default
```

**Eight warnings from the eight-line snippet on the front page of the README.**
This is the single most damaging thing I found, because it is the first
Filigree a stranger ever compiles. Seven of the eight are the lane-resample
warning, and they exist *because* the README's own drawn curves do not line up
with its own note lane — which is precisely the property README:52–54 claims is
guaranteed by construction. The eighth is `!voicing=warm` with no `voicing warm`
block, which the README shows nowhere in that snippet.

Compare: **all seven files in `examples/` compile with zero warnings** (S16).
The examples are clean; the README is not. Someone edited the front page
without recompiling it.

### S5 — read `examples/nocturne.fil`

The real example uses a *different glyph vocabulary* from the README front page:
digits (`______56`, `66______`) and `v` (`___vv__>3`) rather than the README's
`/` and `\`. Both work, but a newcomer comparing the two documents cannot tell
which is idiomatic. `nocturne.fil:27–28` carries a comment explaining that `_`
is the lane *rest* value and `v` is the explicit minimum — a rule the README
never states anywhere, and which matters enormously on a bipolar lane. I only
learned it because that one example happens to have a comment in it.

`nocturne.fil:37` uses `press!time=note`. Nothing in the README mentions a
`!time=` option or what "note time" means, so at this point I had no idea it
existed.

---

## Part 2 — The five-minute test (README + one example only, no SPEC)

Goal I set myself before typing: four bars in A minor, `i | iv | VI | V`, a
melody that rises and falls, one drawn upward bend in bar 1, a dip in bar 4,
and a pressure swell under the whole thing. Target file
`/tmp/stranger_first.fil`.

### Guesses I had to make, in the order I made them

1. That a `harm` lane accepts bare roman numerals with no `voicing` declared.
   (The README only ever shows `harm!voicing=warm`.) — correct.
2. That scale degree `0` means the tonic. The README never says. — correct.
3. That the default octave is 4. The README never says. `0` in A minor gave
   me `A4`. — correct but unstated.
4. That `-` extends the previous note. Inferred purely from the shape of
   `| 4 - - 2 |` in README:15. — correct.
5. That `.` is a rest. Same inference. — correct.
6. That a lane may be left blank between two `|` (README:16 bar 3 is empty). —
   correct.
7. That `stave` needs no `channelgroup` line (nocturne's second stave has one,
   its first does not). — correct.
8. That the bend lane has a *default depth* and that I would have to set it.
   I did **not** guess this; I found out from an error message. The README
   never mentions a default bend range for a lane, and `@bend-range 48st`
   (which *is* in the README, line 105, as the MPE member range) is a
   completely different number from the `±2st` a `bend` lane actually defaults
   to. I lost a cycle to this.
9. That drawn glyph counts and note-slot counts interact at all. Not in the
   README. Cost me two cycles.
10. That `v` is a legal glyph. Learned from a comment in nocturne, not the docs.

### The cycles, verbatim

**Cycle 1.** Wrote the file using the README's front-page glyph style
(`___/^^^`, `^^\____`, `__/\_>3`) over 4-token note bars.

```
  /tmp/stranger_first.fil:10:11: warning: in stave 'tune', bar 1: lane 'bend' has 7 anchors but lane 'notes' has 4 slots; ... resampled
  /tmp/stranger_first.fil:11:11: warning: ... lane 'press' has 7 anchors ...
  [5 more of the same]
  /tmp/stranger_first.fil:10:46: warning: bend target needs -4.00st but the lane range is -2..+2st, so the note cannot reach it; clamped (widen it with '!range=4st')
```
7 resample warnings + 1 clamp. It *ran*, and the harmony table was exactly what
I intended, which is a real credit to the design. But nothing about the
expression was what I meant: bar 1's little rise had become a full-range
`+0.00 → +2.00st` climb landing on `F#5`, a note not in the chord.

**Cycle 2.** Padded every glyph run to 8 characters (guessing that 8 divides 4)
and widened to `!range=4st`.

```
  /tmp/stranger_first.fil:10:54: warning: in stave 'tune', bar 4: lane 'bend' has 6 anchors but lane 'notes' has 4 slots; ... resampled
```
Down to one warning. `_____v_>3` — I had not realised `>3` counts as **one**
anchor, so my arithmetic was off by one. Also the widened range made bar 1's
rise *worse*: `bend[+0.00..+4.00×14]→Ab5(+4.00st)`. Widening the range to
silence a clamp warning silently rescaled every other drawn shape in the same
lane. That coupling is not documented anywhere and it is a genuine ergonomic
trap: `!range` is simultaneously "how far `>3` may reach" and "what `^` means".

**Cycle 3.** Tried `| ____vv_> 3 |`, having convinced myself the `3` in `>3`
was a separate token.

```
  /tmp/stranger_first.fil:13:53: warning: in stave 'tune', bar 4: lane 'bend' has 10 anchors but lane 'notes' has 4 slots; ... resampled
```
**No error.** A single space inside `>3` silently changes the music: `>` is
parsed as a bare harmonic target and `3` as an unrelated level anchor. The only
diagnostic is an anchor-count warning that tells me nothing about the real
mistake. Reproduced minimally later (S14):

```
$ filigree explain /tmp/sp.fil     # bend | __> 3 | ____ |
  warning: ... lane 'bend' has 5 anchors but lane 'notes' has 4 slots ...
      0.000  4.000    60 C4  90 -  bend[-1.00..+0.00×10 2span]→B3(-0.67st)
```

**Cycle 4.** Fixed to `_____v_>3`. One warning left, the `>3` clamp.

**Cycle 5.** `!range=4st`. **Zero warnings.** Rendered:
`wrote /tmp/stranger_first.mid  (12 notes, 16.00 beats, 1 stave(s), MPE lower zone)`.

### Cycle count and the honest caveat

**5 edit-run cycles to a warning-free file.**

But I have to be straight about this: I never got the thing I actually meant.
My `>3` sits in the last bar, and there `explain` reports
`bend[-4.00..+0.00×38]→Ab4(-4.00st)` — it resolved to `Ab`, the third of the
*current* chord (V = E Ab B), not the third of anything following. Neither the
README nor the SPEC says what a harmonic target does when there is no next
chord, so for a full cycle I believed the flagship feature was simply broken.
It is not (see Promise 1), but I could not have known that from the docs, and a
newcomer's most likely place to write a resolving gesture is the last bar of
the phrase they just typed.

`explain` was the thing that saved this session. It is the only reason I could
tell that my curves were wrong rather than merely inaudible.

---

## Part 3 — Second piece, after reading `docs/SPEC.md`

`/tmp/stranger_second.fil` — D minor, named voices (`bass`/`lead`), a gesture
built with the algebra, a `>3` endpoint, modal interchange (`IVd`, `bVIIm`), a
`feel`, and a second stave using `after`.

**Cycle 1. Zero warnings, zero errors, first try.**

```
Second Attempt, Dorian   72 bpm  4/4  key=D minor  mpe-bend=±48st  seed=5
    bar 2.00  IVd        maj        [G B D]  guide[B D]  voiced[G3 B3 D4 B4]
      0.000  1.062    62 D4    104 bass     timbre[+0.50..+0.50×2]
      0.000  1.948    74 D5     81 lead     bend[+0.00..+0.00×2]→D5(+0.00st) press[+0.00..+1.00×9]
     12.012  3.914    65 F4    101 lead     bend[-3.86..+0.00×12]→C#4(-3.86st) press[+0.00..+1.00×10]
```

**1 edit-run cycle.** That is a real result and it should be said plainly: the
SPEC is good enough that a stranger can write a five-feature piece correctly on
the first attempt. `IVd` giving G major in D minor (dorian's natural 6) and
`bVIIm` giving C major are both musically right, and the per-voice channel
assignment in the `voice` column is exactly what point 4 of the README promises.

### SPEC sections I had to re-read

- **§6, three times** (SPEC:173–192). The multi-line `voices | { bass: ... ;
  lead: ... }` form and the `press@lead` lane-suffix form are shown as two
  separate snippets, and it is not stated whether the suffix form needs the
  block form, whether `@voice` composes with `!options` (it does:
  `bend@lead!range=4st` works, but only because I tried it), or what happens to
  an unsuffixed lane when a `voices` lane exists. SPEC:191–192 answers the last
  one in one sentence that is easy to miss.
- **§8, twice** (SPEC:240–272). The algebra table gives no **precedence**. Is
  `cry * 1.4 >> vibr | swell` `((cry*1.4) >> vibr) | swell` or
  `(cry*1.4) >> (vibr | swell)`? I parenthesised defensively rather than find
  out. For a section whose whole selling point is an algebra, omitting
  precedence is a real gap.
- **§7.1** (SPEC:224–238), to understand `!time=bar` vs `!time=note`. This
  section is excellent — the clearest paragraph in either document.
- **§9** (SPEC:274–284), because of a syntax collision (below).

### Wrong or missing in the SPEC

- **SPEC:159 is a garbled table row that shipped:**
  `| +0 -0`? | no — accidentals are `#`/`b` prefixed: `#4`, `b3` |`
  That is an author's note to themselves left inside the normative token table.
- **SPEC:96** specifies the bend lane range as `±@lane-range` (default `±2st`).
  There is no `@lane-range` directive anywhere in the §2 directive table
  (SPEC:43–52), and no such directive is accepted. The default `±2st` is
  correct; the name of the knob is fiction. The real knob is `!range=`.
- **SPEC:277 writes `feel loose = { ... }`** with an `=`; `SPEC:138` writes
  `voicing warm { ... }` without one; `examples/nocturne.fil:15–16` writes both
  without one. The compiler accepts both spellings for both, so nothing breaks,
  but the spec is inconsistent with itself and with its own examples.
- **SPEC:217 lists `>3`/`>5`/`>7`/`>9`, `>+`, `>-`, `>|`** — and no `>root`,
  even though README:45 promises `>root`. See Promise 1.
- **`>7` against a chord with no seventh is a silent no-op.** `harm | I | V |`
  with `>7` gives `bend[+0.00..+0.00×2]→C4(+0.00st)` — no warning, no error, no
  movement. Given that SPEC:321 makes an unknown *chord* a hard error precisely
  so a typo cannot silently delete music, silently deleting a *gesture* is
  inconsistent.
- **Missing entirely: the MPE event-rate governor.** Rendering
  `/tmp/stranger_second.fil` prints:
  ```
    <input>:0:0: warning: MPE: channel 2 lane press exceeded its share of the 240 expression
    events/second/channel ceiling; its hold tolerance was widened x2.4 (at a fixed event
    budget a hold receiver's accuracy is bounded by max|dv/dt| / rate)
  ```
  `grep -niE "240|events?.per.second|ceiling|thinn" README.md docs/SPEC.md`
  returns **nothing**. So the compiler will quietly degrade the fidelity of the
  curves I drew, tell me about it in a message referencing a concept that
  appears in no document, and point me at `<input>:0:0` — which also flatly
  contradicts SPEC:315, *"Every diagnostic carries `file:line:col`, the
  offending token, and a suggestion."*
- **Divergence from the lineage the SPEC claims.** SPEC:119 calls the roman
  numerals *"Ziffers/Hookpad-lineage"* and SPEC:124–126 assigns the modal
  interchange letters `n d f y m a l h e`. This repo's own
  `refs/syntax/tasks.md:151` quotes the Ziffers wiki mapping as
  `a` aeolian, `b` locrian, `c` ionian, `d` dorian, `e` phrygian, `f` lydian,
  `g` mixolydian. Only `d` and `a` agree. In Filigree `f` is phrygian; in
  Ziffers `f` is lydian. In Filigree `e` is melodic minor; in Ziffers `e` is
  phrygian. Anyone arriving from the language the SPEC names as its ancestor
  will write `IVf` meaning lydian and get phrygian, with no diagnostic. Claiming
  a lineage and then silently redefining its symbols is worse than not claiming
  one.

---

## Part 4 — The five promises

### Promise 1 — "`>3` glides into the next chord's third; `>5`, `>7`, `>root` likewise. Re-harmonise and the gestures follow." (README:44–45; also README:23–25, SPEC:15–17, SPEC:217)

**Split verdict: the headline behaviour is KEPT; `>root` is BROKEN.**

The re-harmonisation claim is the real one, and it holds. Same file twice, one
chord symbol changed:

```
$ cat /tmp/p1_a.fil
@key C major
stave t {
  harm  | I       | V       |
  notes | C4 - - - | 0 - - - |
  bend  | ____>3  | ____    |
}
$ filigree explain /tmp/p1_a.fil
    bar 2.00  V          maj        [G B D]  guide[B D]  voiced[D3 G3 B3]
      0.000  4.000    60 C4     90 -        bend[-1.00..+0.00×8]→B3(-1.00st)

# same file, bar 2 changed from V to bVI, nothing else touched:
$ filigree explain /tmp/p1_b.fil
    bar 2.00  bVI        maj        [Ab C Eb]  guide[C Eb]  voiced[C3 Eb3 Ab3]
      0.000  4.000    60 C4     90 -        bend[+0.00..+0.00×2]→C4(+0.00st)
```

Third of V is B, so `C4` bends `-1.00st` to `B3`. Third of bVI is C, so the
same drawn glyph now correctly bends *nothing*. That is the feature working
exactly as advertised, and it is the best idea in the language. `>5` and `>9`
also behave (`>5` on V9 → `+2.00st` to `D4`; `>9` → `-3.00st` to `A3`).

`>root`, however, promised by name in README:45:
```
$ filigree explain /tmp/groot.fil     # bend | ___>root | ____ |
/tmp/groot.fil:5:15: error: 'root' is not a curve glyph
  at token: 'root'
  hint: an inline gesture needs arguments, e.g. 'root(0.3)'; glyphs are '_' rest, 'v' min, ...
EXIT=2
```
A hard error, and the SPEC does not list it either. **BROKEN.**

Undocumented fallback: in the last bar, `>3` silently targets the current
chord's third (S13: `harm | V |` alone, `>3` → `B3`). Reasonable behaviour,
zero documentation.

### Promise 2 — "you never write durations, so lanes line up by construction" (README:52–54, SPEC:56–57)

**First half KEPT. Second half BROKEN.**

You genuinely never write a duration. There is no escape hatch:
```
$ filigree explain /tmp/p2.fil        # notes | C4:2 D4 |
/tmp/p2.fil:2:11: error: 'C4:2' is not a note token
  hint: scale degrees are 0-8 (0 = tonic); absolute pitches look like 'C4'; chord tones like '~3'; rest '.', tie '-'
```
Slot inference is real and it is pleasant. Credit where due.

But "lanes line up by construction" is false, and the project knows it: the
whole point of SPEC:78–81 and SPEC:316–319 is a warning for the case where they
*don't*. Curve lanes are free-running glyph runs subdivided independently of
the note lane (SPEC:73–81), so alignment is a thing you achieve by counting
characters, not a thing the construction gives you. My evidence is the README's
own headline example emitting seven resample warnings (S4), my own first attempt
emitting seven (Cycle 1), and the playground's shipped demo emitting a large
share of its 38 (Part 5). Three for three: every piece of Filigree written by a
human in this session, including two written by the authors, failed the property
the README says holds by construction.

### Promise 3 — `--lenient` "downgrades an unknown chord symbol from an error to a warning and sustains the previous chord" (README:123–124, SPEC:322–323)

**BROKEN as stated.** It works for *some* unknown symbols and hard-errors on
others, and the class it fails on is the mid-session typo the feature exists to
survive.

```
$ filigree explain --lenient /tmp/p3.fil       # harm | I | Zqx9 | V |
/tmp/p3.fil:3:15: error: 'Zqx9' is not a chord symbol
EXIT=2
```
`--lenient` is in `filigree explain --help`, is accepted by the parser, and is
ignored. Not a flag-ordering issue — I tried both `explain --lenient FILE` and
`explain FILE --lenient`, both exit 2. Same on `render` and `json`.

Sweeping five malformed symbols shows where the line is:

| symbol | `--lenient` result |
|---|---|
| `viii` | warning + sustains previous chord, exit 0 — **works** |
| `Cm9zz` | warning + sustains previous chord, exit 0 — **works** |
| `Hm7` | `error: 'Hm7' is not a chord symbol`, **exit 2** |
| `Zqx9` | `error: 'Zqx9' is not a chord symbol`, **exit 2** |
| `{0 3 zz}` | `error: 'zz' is not a semitone offset`, **exit 2** |

So a symbol that gets far enough to be recognised as chord-shaped is
downgraded; one whose first character is not a valid note letter or numeral
dies before the lenient path is reached. Musically, `Hm7` — the German/typo
`H` for `B`, or any fat-fingered leading character — is *the* live-coding typo.
README:123–124 makes no distinction and promises the downgrade for "an unknown
chord symbol". `Hm7` is an unknown chord symbol. The promise is not kept.

Related, and worse in kind: `I^^7` is accepted **silently** with no warning at
all and produces a chord. A grammar that hard-errors on `Hm7` while waving
through `I^^7` is not enforcing the "a typo must not silently delete a bar of
music" principle of SPEC:321 — it is enforcing it unevenly.

### Promise 4 — MPE zone configuration: "master channel 1, members 2–16, ±48 semitone member bend range, per MIDI Association RP-053" (README:103–105)

**KEPT, emphatically.** This is the strongest part of the project. Using the
repo's own audit tool, as README:163 instructs:

```
$ python tools/audit_mpe.py /tmp/nocturne.mid
  [PASS] MCM (RPN 00 06) present on channel 1  -- found 1
  [PASS] MCM mm == 15 (lower zone, 15 members)  -- mm=15
  [PASS] MCM at tick 0  -- tick=0
  [PASS] MCM sent MSB (CC101) before LSB (CC100)
  [PASS] MCM closed with null RPN
  [PASS] upper-zone-off MCM (mm=0) on channel 16  -- found 1
  [PASS] RPN 0 bend range on every used member channel  -- missing on channels []
  [PASS] all member channels share one bend range  -- ranges=[48]
  [PASS] no notes on the zone master channel
  [PASS] no polyphonic key pressure on member channels
  [PASS] per-note order is bend -> CC74 -> pressure(0) -> note-on
  [PASS] pressure(0) immediately precedes every note_off
  [PASS] zero expression events between note-off and next note-on
  [PASS] no two simultaneous notes on one member channel
  [PASS] <= 250 expression events/second/channel  -- peak=207 on channel 6
```
26 checks, 26 PASS. MSB-before-LSB ordering, null-RPN termination, explicit
upper-zone-off, pressure(0) before note-off, no expression in the gaps — these
are details you only get right on purpose. I am rating this on the project's own
instrument, which is a weakness of the evidence, but the checks are specific
enough and the ordering constraints obscure enough that I believe them.

One cosmetic snag: the same report prints
`member_channels_used [1, 2, ..., 12]` while also passing "no notes on the zone
master channel". The list is evidently 0-indexed (so MIDI channels 2–13) while
README:104 speaks 1-indexed. A newcomer reading both will think notes are being
written to the master channel.

### Promise 5 — "`refs/syntax/tasks.md` — the six benchmark tasks solved in Filigree **and** in TidalCycles, Strudel, Sonic Pi, Alda, Ziffers and LilyPond, with character counts. Filigree wins four of six on concision and loses two; the losses are printed there." (README:154–157)

**BROKEN. The document does not contain what the README says it contains.**

```
$ grep -cE '^\| *Filigree' refs/syntax/tasks.md
0
$ grep -niE 'stave |\.fil|harm *\|' refs/syntax/tasks.md
[no output]
$ grep -niE "filigree" refs/syntax/build_tasks.py
[no output]
```

There is **not one Filigree solution, not one Filigree character count, and no
concision scoreboard** in `refs/syntax/tasks.md`. Every per-task table
(T1 at :32–39, T2 at :58–65, T3 at :84–91, T4 at :110–117, T5 at :136–143)
lists exactly six languages, and Filigree is not among them. There is no
"four of six" tally anywhere in the file. The `chars` column is defined at
:7 as being computed by `build_tasks.py`, which has no notion of Filigree at
all.

Worse, the repo's own record contradicts the direction of the claim.
`refs/syntax/curves.md:21` states *"**REFERENCE**. What Filigree still wins, it
wins on expressiveness, not on concision"*, and `:289` says a rival is
*"**shorter than Filigree here** and this row is a REFERENCE win on concision."*
So the honest internal finding is that Filigree tends to *lose* on concision,
while the README's front matter advertises winning four of six.

To be fair to the document that does exist: `tasks.md` is excellent as a
rivals-only survey. Its `IMPOSSIBLE:`/`UNVERIFIED` discipline, its per-claim
primary-doc citations, and its "diff cost" measure are more rigorous than most
published comparisons. The defect is entirely in the README's description of it.
Given that README:138–157 sells the adversarial process as "part of the
deliverable", a false claim about the contents of the evidence file is the worst
possible place to be sloppy.

---

## Part 5 — The playground, judged cold

```
$ filigree serve
filigree playground → http://localhost:8787/
  serving /home/user/workspace/filigree/web
```

Driven with headless Chromium (the sandbox has no audio device, so *audible*
sound could not be verified — see the caveat below).

**Could I understand what I was seeing without reading anything else? Yes.**
This is the best-executed component in the repo. The top strip reads
`START HERE  ① hit play  ② change something  ③ hit compile ⌘⏎`, followed by the
one sentence a newcomer most needs: *"lanes line up in columns — read down a
bar. Click a note to inspect it."* The layout is source on the left, a chord
ribbon over a piano roll on the right, per-lane curves drawn **inside** each
note rectangle in three distinguishable encodings (bend as a line, press as
opacity, timbre as hue — and there is a legend saying exactly that), a moving
playhead with a `bar.beat.tick` readout, per-stave M/S buttons, a note inspector,
and a diagnostics panel whose rows jump to `line:col`. I understood the language's
central conceit faster from this screen than from either document.

**The edit loop works.** I changed `@key C minor` to `@key E minor` and pressed
`Ctrl+Enter`: the header went to `E min 4/4`, the chord ribbon re-labelled from
`i9 C min9 • Eb Bb / VI^7 Bb maj7 / iv11 / V7alt B alt` to
`i9 E min9 • G D / VI^7 D maj7 / ... / V7alt B alt`, and the piano-roll pitch
axis shifted. Re-harmonisation propagating visibly through a live view is a
genuinely persuasive demo of Promise 1.
Screenshots: `/tmp/pg_01_load.png`, `/tmp/pg_02_playing.png`,
`/tmp/pg_03_playing2.png`, `/tmp/pg_04_edited.png`.

**And then: `DIAGNOSTICS 38`.**

The file the playground opens with — `web/fixtures/source.fil`, "Cinder Study
(8 bars)", described in its own header comment as *"The example that ships with
the playground"* — greets every first-time visitor with a wall of 38 warning
chips. Confirmed from the CLI:

```
$ filigree explain web/fixtures/source.fil 2>&1 | grep -c warning
38
$ filigree explain web/fixtures/source.fil 2>&1 | grep warning | sed 's/.*warning: //' | sort -u | head -8
bend target needs +3.00st but the lane range is -2..+2st, so the note cannot reach it; clamped (widen it with '!range=3st')
bend target needs +4.00st but the lane range is -2..+2st, so the note cannot reach it; clamped (widen it with '!range=4st')
bend target needs +6.00st but the lane range is -2..+2st, so the note cannot reach it; clamped (widen it with '!range=6st')
bend target needs -3.00st but the lane range is -2..+2st, so the note cannot reach it; clamped (widen it with '!range=5st')
in stave 'bass', bar 4: lane 'bend' has 5 anchors but lane 'notes' has 4 slots; ... resampled
in stave 'bass', lane 'harm' has 8 bars but lane 'notes' has 4
in stave 'keys', lane 'harm' has 8 bars but lane 'voices' has 1
```

Read the first four. **Every harmonic bend target in the flagship demo is
clamped and does not reach its chord tone.** Line 24 of that very fixture reads
`gesture fall = bend(0 -> >3)   # land on the next chord's third` — and it does
not land, because the lane range defaults to `±2st` and the fixture never widens
it. The demo of the language's signature feature is audibly broken in the demo
of the language. Whatever sound the playground makes on load, it is not the
sound the file describes.

Two more from the same 38:
- `30:8 warning: lane option 'oct' on lane 'notes' is not recognised and has no
  effect; known options are gesture, range, shape, time, voicing` — the shipped
  fixture uses `notes!oct=5`, which is not a real option. So the demo also
  silently ignores its own octave setting.
- `35:3 warning: lane 'harm' appears twice in the same block; the second one
  adds bars rather than replacing the first` — the fixture is written in a
  style the compiler warns about.

The window title is also doubled: `Filigree — Filigree — Cinder Study (8 bars)`.

**Audio caveat, stated honestly.** Clicking play flipped the transport to
`stop` and advanced the playhead; `window.FiligreeSynth` exists; no page errors
or console errors were emitted. But no `AudioContext` was instantiated in the
headless container (`ctx: 'no ctx'`), so I **cannot** report whether a sound
actually comes out. I am recording this as a limitation of my environment, not
as a defect. Everything visual worked.

---

## Part 6 — Other README commands

```
$ PYTHONPATH=src python -m pytest -q        # README:162, in the venv README:64 told me to make
/home/user/workspace/filigree/.venv/bin/python: No module named pytest
```
**DEFECT.** `pytest` lives in the `dev` optional-dependency group, and the
README never tells you to `pip install -e ".[dev]"`. The documented install path
cannot run the documented test command. After `pip install pytest` by hand, the
suite is green (approximately 490 tests, 0 failures) — so this is purely a
documentation gap, but it is on the one command a stranger runs to decide
whether to trust the project.

`python tools/gauntlet_status.py` (README:164) — worked,
`wrote .../status/gauntlet-status.html`.

`filigree explain examples/*.fil` — **all seven examples, zero warnings, exit 0.**
`blue_iron`, `dorian_drift`, `gesture_algebra`, `nocturne`, `pulse`,
`reference`, `tasks`. Credit: the curated examples are immaculate. The rot is
confined to the two files a newcomer meets first — the README's front page and
the playground fixture.

---

## Severity-ordered defect list

| # | Sev | Where | Defect |
|---|---|---|---|
| 1 | **Critical** | `README.md:154–157` | Claims `refs/syntax/tasks.md` contains Filigree solutions with character counts and a "wins four of six on concision" record. It contains **zero** Filigree rows, zero Filigree character counts, and no scoreboard (`grep -cE '^\| *Filigree'` → `0`). `refs/syntax/curves.md:21,289` says the opposite about concision. A false claim about the project's own evidence file, in the section that sells the evidence as the deliverable. |
| 2 | **Critical** | `web/fixtures/source.fil` (playground default, seen before any doc) | 38 warnings on load, including **every** `>3`/`>5`/`>6` bend target clamped and unreachable at the default `±2st`. The flagship feature is broken in the flagship demo. Also `notes!oct=5` (unrecognised option, ignored) and duplicated `harm`/`notes` lanes. |
| 3 | **Critical** | `README.md:11–18` | The front-page example produces 8 warnings when compiled verbatim: 7 lane-resample, plus `unknown voicing 'warm'` because `!voicing=warm` is used with no `voicing warm { }` block shown. First Filigree a stranger compiles; all `examples/` are clean, so this is stale. |
| 4 | **High** | `README.md:123–124`, `docs/SPEC.md:322–323` | `--lenient` does not do what it says for a large class of unknown chord symbols. `Hm7`, `Zqx9`, `{0 3 zz}` → hard error, exit 2, with the flag present and accepted. `viii`, `Cm9zz` → correctly downgraded. The failing class is exactly the leading-character typo the feature exists for. |
| 5 | **High** | `README.md:52–54` | "you never write durations, **so lanes line up by construction**." The second clause is false; `SPEC:78–81` and `:316–319` document the warning for when they don't. Observed in the README's own example, my first attempt, and the shipped playground fixture. |
| 6 | **High** | `README.md:45` | `>root` is promised by name; it is a hard error (`'root' is not a curve glyph`) and is absent from `SPEC:217`. |
| 7 | **High** | undocumented; contradicts `docs/SPEC.md:315` | The MPE 240-events/second/channel governor silently widens hold tolerance and degrades drawn curves. The concept appears **nowhere** in README or SPEC (grep for `240`/`ceiling`/`thinn` → nothing), and its warning is emitted at `<input>:0:0`, violating "Every diagnostic carries `file:line:col`". |
| 8 | **High** | `docs/SPEC.md:119,124–126` vs `refs/syntax/tasks.md:151` | SPEC claims "Ziffers/Hookpad-lineage" then redefines the borrowed-mode letters. Filigree `f` = phrygian, Ziffers `f` = lydian; Filigree `e` = melodic minor, Ziffers `e` = phrygian. Silent wrong chords for anyone arriving from the named ancestor. |
| 9 | **Medium** | parser | A space inside `>3` (`bend \| __> 3 \|`) silently changes the music — `>` becomes a bare guide-tone target and `3` a level anchor — reported only as an anchor-count warning. A whitespace typo alters pitch with no relevant diagnostic. |
| 10 | **Medium** | `README.md:162` | The documented test command fails from the documented install: `No module named pytest`. `[dev]` extras are never mentioned. |
| 11 | **Medium** | `!range=` semantics, undocumented | `!range` is both "how far `>N` may reach" and "what `^`/`v` mean". Widening it to silence a clamp warning silently rescales every other drawn shape in the lane. Cost me a cycle; not stated anywhere. |
| 12 | **Medium** | `README.md`, whole document | The bend-lane default of `±2st` is never mentioned, and the README's only bend number is `@bend-range 48st` (line 105), a different quantity. A newcomer's first `>3` gets clamped and they cannot tell why. |
| 13 | **Medium** | harmonic targets, undocumented | `>N` in the final bar silently falls back to the current chord. Sensible, unstated, and the most likely place to write one. |
| 14 | **Low** | harmonic targets | `>7` on a chord with no seventh is a silent no-op — no warning — while an unknown chord symbol is a hard error "so a typo must not silently delete music" (`SPEC:321`). Inconsistent. |
| 15 | **Low** | `docs/SPEC.md:159` | Garbled authoring note shipped inside the normative token table: `` | +0 -0`? | no — accidentals are ... `` |
| 16 | **Low** | `docs/SPEC.md:96` | Specifies the bend range as `±@lane-range`; no such directive exists in the §2 table or the parser. The real knob is `!range=`. |
| 17 | **Low** | `docs/SPEC.md:240–272` | The gesture algebra defines no operator precedence, so `cry * 1.4 >> vibr \| swell` has no documented reading. |
| 18 | **Low** | `README.md:60` | Lists `scipy` as a dependency; `pyproject.toml` does not, and pip does not install it. |
| 19 | **Low** | `docs/SPEC.md:277` vs `:138` vs `examples/nocturne.fil:15–16` | `feel x = { }` with `=` in the spec, `voicing x { }` without, examples without for both. Both accepted; docs inconsistent with themselves. |
| 20 | **Low** | `tools/audit_mpe.py` | Reports `member_channels_used [1..12]` (0-indexed) alongside "no notes on the zone master channel", while `README:104` counts channels from 1. Reads as a contradiction. |
| 21 | **Low** | playground | Window title doubled: `Filigree — Filigree — Cinder Study (8 bars)`. |
| 22 | **Low** | `README.md:74–86` vs `:121` | `filigree new` — the one command that hands a newcomer a *compiling* file — is not mentioned until after the section where it is needed. The README's own snippet is used for teaching instead, and it does not compile cleanly. |

---

## Forced pick: would I keep using this tomorrow?

**Yes** — and I am annoyed about how close it came to no. What decides it is
that the two hard parts are actually done. `>3` really does re-resolve when I
change a chord symbol: `C4` bends `-1.00st` to `B3` under `V` and `0.00st`
under `bVI`, from the same drawn glyph, and I verified that myself in two
three-line files. That is a musical idea I have wanted for fifteen years and no
sequencer or live-coding language gives me. Underneath it the MPE output is
scrupulous — 26 of 26 conformance checks, MSB-before-LSB, null-RPN termination,
upper-zone-off, pressure(0) before note-off — the sort of thing that decides
whether a file actually behaves in Bitwig, and it is the part nobody bothers to
get right. `explain` is the best debugging affordance I have seen in a music
language and is the only reason my first hour converged at all; after reading
the SPEC I wrote a five-feature piece with named voices, gesture algebra, modal
interchange and a `feel` correctly on the **first** attempt, which is a stronger
statement about the design than anything in the README. Against that: the
documentation is not trustworthy. The front-page example throws eight warnings,
the playground opens on a demo with thirty-eight — including *every* harmonic
bend clamped and silently not landing, which means the shipped demo of the
signature feature is broken — `--lenient` hard-errors on the exact typo class it
was built for, `>root` is promised and does not exist, an undocumented event-rate
governor quietly degrades my curves at `<input>:0:0`, and the README asserts a
concision record that the cited file does not contain and that the project's own
notes contradict. Every one of those is a fifteen-minute fix, and none of them
is in the compiler; the compiler is fine, and all seven curated examples are
immaculate. So I would keep using it — but I would work from `examples/` and
`explain`, treat the README as marketing rather than reference, and I would not
recommend it to another musician until the front page and the playground fixture
compile clean, because a tool whose own demo warns thirty-eight times is asking
me to distrust exactly the diagnostics I need to distrust nothing else.

---

### Artifacts

- `/tmp/stranger_first.fil` — README-only piece, 5 edit-run cycles.
  Rendered `/tmp/stranger_first.mid` (12 notes, 16 beats, 1 stave).
- `/tmp/stranger_second.fil` — post-SPEC piece: named voices, gesture algebra,
  `>3`, `IVd`/`bVIIm` modal interchange, `feel`, `after`. 1 cycle.
  Rendered `/tmp/stranger_second.mid` (19 notes, 24 beats, 2 staves).
- `/tmp/readme_snippet.fil` — README:11–18 verbatim (8 warnings).
- `/tmp/p1_a.fil`, `/tmp/p1_b.fil`, `/tmp/p1_c.fil` — Promise 1 re-harmonisation.
- `/tmp/p2.fil` — Promise 2 duration probe.
- `/tmp/p3.fil`, `/tmp/p3b.fil` — Promise 3 `--lenient` sweep.
- `/tmp/groot.fil` — `>root` probe.
- `/tmp/sp.fil` — `> 3` whitespace misparse.
- `/tmp/pg_01_load.png` … `/tmp/pg_04_edited.png` — playground, load / playing /
  after re-keying and recompiling.

**Sources cited by the documentation and checked against it:**
MPE RP-053 <https://midimpe.neocities.org/rp53spec.pdf>;
MIDI Association MPE overview <https://midi.org/mpe-midi-polyphonic-expression>;
Ableton MPE zone configuration
<https://help.ableton.com/hc/en-us/articles/4409113250322-MPE-Zone-Configuration>;
Ziffers chords / borrowed-chord letters
<https://github.com/amiika/ziffers/wiki/Chords> (the mapping `SPEC:124–126`
diverges from, as quoted in `refs/syntax/tasks.md:151`).
