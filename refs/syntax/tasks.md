# Syntax bar: six canonical composition tasks, solved in six rival languages

Reference corpus for **P1 — Language surface / ergonomics** in [`refs/BAR.md`](../BAR.md). Each task below is posed language-neutrally, then solved as idiomatically and concisely as the rival's *documented* syntax allows. Every function name, argument and operator is checked against primary docs; the fetched doc extracts are in [`refs/syntax/rival_docs/`](rival_docs/) with their source URLs at the top of each file.

**Rules used here.** `IMPOSSIBLE:` marks a task a language genuinely cannot express, followed by the closest achievable approximation and a one-sentence reason with a doc citation. `UNVERIFIED` marks anything I could not confirm in primary documentation. No syntax is invented: where a rival's docs do not show a construct, the snippet does not use it.

**`chars`** = non-whitespace character count of the snippet, computed by [`build_tasks.py`](build_tasks.py), never typed by hand.
**`diff cost`** = how many characters must change, *starting from that snippet*, to alter one note's vibrato depth. `∞` means the language has no vibrato depth to alter, so the edit is not a character edit but a redesign. This is the P1(d) diffability measure.
**`expresses it fully?`** = `yes` / `partial` / `no` against the task statement as written, including its harmonic or per-note-scoping requirements.

Common musical ground for all tasks: **key C minor**, ii–V–i as `Dm7b5 – G7 – Cm9`, tempo irrelevant.

## Summary: shortest rival that expresses each task

| Task | Strongest rival | chars | Rivals that cannot express it at all |
|---|---|---|---|
| **T1** 4-bar minor-key ii–V–i with smooth 4-voice voicings | Ziffers | 49 | — (all six can voice the chords; four cannot voice-lead automatically) |
| **T2** Melody over the progression; one note bends up into the next chord's third | Sonic Pi | 92 | Alda, Ziffers, LilyPond (and Tidal/Strudel cannot target the chord's third) |
| **T3** Vibrato that starts 35% into a held note and widens toward the end | Sonic Pi | 129 | Alda, Ziffers, LilyPond |
| **T4** One chord, four voices, four different pressure/timbre movements | Strudel | 191 | Alda, Ziffers, LilyPond |
| **T5** Modal-interchange substitution in the middle of the progression | Ziffers | 51 | Tidal, Strudel, Alda, LilyPond (sound only, no function) |
| **T6** Reuse one named expressive gesture across 12 notes, changing one parameter on the 7th | Strudel | 58 | Alda, Ziffers, LilyPond |

"Strongest" here means *strongest bar for a candidate to clear*: the rival that expresses the task most completely, with character count as the tiebreak. Three places where a shorter rival does **not** hold the bar: T1 — Strudel is 40 chars vs Ziffers' 49, but its chords are absolute symbols with no key context; T4 — Sonic Pi is 160 chars vs Strudel's 191, but its four curves are internal-synth `amp`/`cutoff`, not pressure/CC74; T6 — Strudel is 58 chars vs Sonic Pi's 157, but only Sonic Pi has a *named, parameterized* gesture as the task requires. Per-task verdicts below give the full reasoning.

---

## T1. 4-bar minor-key ii–V–i with smooth 4-voice voicings

**Task statement.** In C minor, write four bars, one chord per bar: **Dm7b5 | G7 | Cm9 | Cm9** (iiø7 – V7 – i9 – i9). Each chord must sound as exactly four voices, and successive chords must be voiced so that total voice movement is small (no voice leaps an octave, no crossing).

| language | snippet | chars | diff cost | expresses it fully? |
|---|---|---|---|---|
| TidalCycles | `d1 $ n "<d4'm7f5'4 g4'dom7'4 c4'min9'4!2>" # s "superpiano"` | 51 | ∞ | partial |
| Strudel | `chord("<Dm7b5 G7 Cm9!2>").voicing().midi()` | 40 | ∞ | yes |
| Sonic Pi | `[:ii,:v,:i,:i].each{\|d\| play chord_degree(d,:c4,:minor,4),sustain: 3.5; sleep 4}` | 75 | ∞ | partial |
| Alda | `piano: o3 d1/f/a-/>c <g/b/>d/f <c/e-/g/b- *2` | 39 | ∞ | yes |
| Ziffers | `zplay "w (ii+4 v+4 i+4 i+4)<lead>", key: :c, scale: :minor` | 49 | ∞ | yes |
| LilyPond+articulate.ly | `{ <d' f' af' c''>1 <g' b' d'' f''> <c' es' g' bes'> <c' es' g' bes'> }` | 53 | ∞ | yes |

**Per-language notes, with sources.**

- **TidalCycles** — Chord names `m7f5`, `dom7`, `min9` and the voice-count modifier `'4` are documented ([Tidal harmony & melody](https://tidalcycles.org/docs/reference/harmony_melody)); `!2` repeats a step ([mini-notation](https://tidalcycles.org/docs/reference/mini_notation/)). Voicing control is limited to `'o` (open), `'dN` (drop N), `'iN` (inversion) and tone count — there is **no** voice-leading function, so smoothness must be hand-chosen per chord. *Diff cost ∞:* no vibrato exists in this snippet; adding one means a second parallel `midibend`/`ccv` pattern (~45 chars), and it lands on the whole channel, not one note.
- **Strudel** — `chord`, `voicing`, `dict`, `anchor`, `mode` are documented; the default dictionary lists `Dm7b5`, `G7`, `Cm9` verbatim and “the `voicing` function tries to minimize jumps” ([understanding voicings](https://strudel.cc/understand/voicings/), [tonal API](https://strudel.cc/learn/tonal/)). UNVERIFIED: the docs do not promise a fixed voice count, so “exactly four voices” depends on the dictionary entry chosen (`.dict('lefthand')` is shown in the tonal docs as a 4-note left-hand dictionary but its size is not stated). *Diff cost ∞:* no per-note vibrato: `.vib()` is a synth-side effect on Strudel's own oscillator and is one value per event; over MIDI, depth would be a channel-wide `ccv`.
- **Sonic Pi** — `chord_degree degree, tonic, scale, number_of_notes` with degrees `:i`…`:vii` is documented and yields the diatonic 7th chords of C minor (so `:ii` is automatically m7b5) ([chord_degree](https://sunderb.me/sonic-pi-docs-test/en/reference/lang/chord_degree.html)); `chord_invert` / the `invert:` opt is the only voicing control ([chord_invert](https://sunderb.me/sonic-pi-docs-test/en/reference/lang/chord_invert.html)) — no voice-leading, so the voicings are close-position and the ii→V motion is not minimised. *Diff cost ∞:* `play` takes no vibrato opt; vibrato requires re-writing the chord as separate handles plus a `control`/`note_slide` loop per voice (T3 pattern, ~90 chars per voice).
- **Alda** — Chords `c1/e-/g/b`, sticky note length, octave `<`/`>`, accidentals `+`/`-` and chord repeat `*2` are all in the [cheat sheet](https://alda.io/cheat-sheet/). Voice leading is whatever you type — fully expressible, zero help ([attributes](https://alda.readthedocs.io/en/latest/attributes/)). *Diff cost ∞:* Alda's whole attribute set is `duration, key-signature, octave, panning, quantization, tempo, track-volume, volume` — there is no bend, vibrato, pressure or CC attribute at all.
- **Ziffers** — `i`…`vii` build chords from the given scale, `+4` makes it a 7th chord (4 notes), and the `<lead>` transformation is documented as voice leading using “the taxi cab metric algorithm described in *The Geometry of Music*” ([Ziffers wiki: Chords](https://github.com/amiika/ziffers/wiki/Chords)); duration char `w` = whole ([README cheatsheet](https://github.com/amiika/ziffers)). This is the only rival that gets correct minor-key ii–V–i **and** algorithmic voice leading in one line. *Diff cost ∞:* Ziffers has no expression syntax; the only lever is passing a Sonic Pi opt (e.g. `release:`) per degree as an array/ring, which cannot shape one note's pitch over time.
- **LilyPond+articulate.ly** — Chords `<...>`, absolute octaves and durations are core notation; MIDI comes from a `\midi { }` block, optionally through `\articulate` ([MIDI articulation](https://lilypond.org/doc/v2.25/Documentation/usage/midi-articulation), [enhancing MIDI output](https://lilypond.org/doc/v2.25/Documentation/notation/enhancing-midi-output)). Voicing is manual; engraving is the point. *Diff cost ∞:* `articulate.ly` works purely by “adjusting note lengths … according to the articulation markings” — there is no vibrato depth to edit.

**Which rival is the bar for T1.** **Strongest bar: Ziffers.** It is the only rival where the harmony is stated functionally (`ii+4 v+4 i+4`) *and* the voicing is solved for you by a documented voice-leading transformation `<lead>`. Strudel is a close second and is shorter, but its chords are absolute symbols (`Dm7b5`), so the key is implicit and re-keying means retyping every symbol. Tidal, Sonic Pi, Alda and LilyPond all require the composer to do the voice leading by hand.

---

## T2. Melody over the progression; one note bends up into the next chord's third

**Task statement.** Over the T1 progression, play a four-note melody `C5 Eb5 D5 D5`. The last `D5` must bend **up one semitone** during its own lifetime so that it arrives on `Eb5` — the third of the following `Cm9` — exactly at the bar line. The bend target must be the *chord's third*, not a hand-typed number, for the language to “express it fully”.

| language | snippet | chars | diff cost | expresses it fully? |
|---|---|---|---|---|
| TidalCycles | **IMPOSSIBLE:** closest achievable — <br>`d1 $ stack [note "c5 ef5 d5 d5", midibend (compress (0.75,1) $ segment 64 $ range 8192 12288 saw)] # s "m" # midichan 1` | 95 | 4 | no |
| Strudel | **IMPOSSIBLE:** closest achievable — <br>`$: note("c5 eb5 d5 d5").midi()`<br>`$: midibend(saw.range(0,.5).segment(32)).struct("~@3 x").midi()` | 87 | 2 | no |
| Sonic Pi | `play :c5; sleep 1; play :eb5; sleep 1`<br>`s=play :d5,sustain: 1.8,note_slide: 0.5`<br>`sleep 1.5`<br>`control s,note: :eb5` | 92 | 3 | partial |
| Alda | **IMPOSSIBLE:** closest achievable — <br>`piano: o5 c4 e- d~ e-8` | 17 | ∞ | no |
| Ziffers | **IMPOSSIBLE:** closest achievable — <br>`zplay "q 4 6 5 5", key: :c, scale: :minor` | 32 | ∞ | no |
| LilyPond+articulate.ly | **IMPOSSIBLE:** closest achievable — <br>`{ c''4 es'' d''\glissando es''4 }` | 28 | ∞ | no |

**Per-language notes, with sources.**

- **TidalCycles** — IMPOSSIBLE as specified. `midibend` is documented as a channel-scoped control pattern over the raw 14-bit range `0–16383`, `8192` neutral ([Tidal MIDI](https://tidalcycles.org/docs/configuration/MIDIOSC/midi/)), so (a) the target must be hand-computed — `12288` is +1 semitone only if the device's bend range is ±2 semitones, which Tidal does not set — and (b) the bend hits every note on channel 1, not just the last `D5`. Closest achievable: the snippet above, where `compress (0.75,1)` confines the ramp to the 4th beat ([compress](https://tidalcycles.org/docs/reference/time/)) and `segment 64` sets the message rate. *Diff cost 4:* `12288` → e.g. `13000`: 4 digits changed, but the edit is on a *parallel* pattern, not on the note token.
- **Strudel** — IMPOSSIBLE as specified. `midibend` “sets MIDI pitch bend (-1 - 1)” ([Strudel MIDI I/O](https://strudel.cc/learn/input-output/)), so “+1 semitone” is `0.5` *only* if the synth's bend range is ±2 semitones — a number you compute, not a musical reference. Bend is also per-channel (`midichan` defaults to 1). `saw`/`range` are documented ([signals](https://strudel.cc/learn/signals/), [value modifiers](https://strudel.cc/functions/value-modifiers/)); the docs also warn that in one chained pattern “structure comes from the left”, which is why the bend is written as its own `$:` lane. *Diff cost 2:* `.5` → `.8` in the `range`, 2 chars — again on a separate lane.
- **Sonic Pi** — The closest any rival gets: `note_slide:` plus `control` genuinely bends one voice's pitch over its own lifetime, with an audible glide, and the destination is written as a pitch name (`:eb5`) ([Sonic Pi tutorial §7.3 Sliding Opts](https://sonic-pi.net/tutorial.html), [control](https://sunderb.me/sonic-pi-docs-test/en/reference/lang/control.html)). Still not “the next chord's third”: you type the pitch. Internal synths only — the MIDI path is `midi_pitch_bend`, which sends “to *all* connected devices on *all* channels” unless restricted ([midi_pitch_bend](https://sunderb.me/sonic-pi-docs-test/en/reference/lang/midi_pitch_bend.html)). *Diff cost 3:* edit the slide target/`note_slide:` value, e.g. `0.5`→`0.25`: 3 chars.
- **Alda** — IMPOSSIBLE. The documented attribute set is duration, key-signature, octave, panning, quantization, tempo, track-volume, volume ([Alda attributes](https://alda.readthedocs.io/en/latest/attributes/)) — no pitch bend, no CC. Closest achievable: a slur/legato step up to the target third (`d~ e-8`), i.e. two discrete notes instead of one bent note ([cheat sheet: slurs](https://alda.io/cheat-sheet/)). *Diff cost ∞:* no bend/vibrato attribute exists.
- **Ziffers** — IMPOSSIBLE. Ziffers' notation covers pitch, rhythm, chords, generative operations — nothing continuous ([README cheatsheet](https://github.com/amiika/ziffers), [Effects](https://github.com/amiika/ziffers/wiki/Effects) which varies opts *per degree*, not *within* a note). Closest achievable: play the target third as the next degree. *Diff cost ∞:* no bend syntax; Sonic Pi opts passed by Ziffers are set at note start and never `control`led afterwards.
- **LilyPond+articulate.ly** — IMPOSSIBLE. `\glissando` and `\bendAfter #+4` are engraving marks; `\bendAfter`'s number “indicates the pitch interval that the fall or doit will extend *beyond* the main note” and is drawn, not performed ([falls and doits](https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks-as-curves), [expressive marks as lines](https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks-as-lines)); `articulate.ly` only “adjust[s] note lengths” ([MIDI articulation](https://lilypond.org/doc/v2.25/Documentation/usage/midi-articulation)), so no pitch curve reaches the MIDI file. *Diff cost ∞:* nothing to edit — no bend depth parameter in the language.

**Which rival is the bar for T2.** **Strongest bar: Sonic Pi.** It is the only rival that actually bends a single voice into a named destination pitch inside that note's lifetime (`note_slide:` + `control s,note: :eb5`), and it is the shortest thing that makes an audible glide. Tidal and Strudel can draw a bend curve but only channel-wide and only in hand-computed bend units; Alda, Ziffers and LilyPond cannot bend at all. **No rival can name the target harmonically** — every one of them makes you type the pitch of the next chord's third yourself.

---

## T3. Vibrato that starts 35% into a held note and widens toward the end

**Task statement.** One held note (4 beats, C4). Nothing for the first 35% of its duration; then vibrato begins and its depth grows monotonically from ~0 to about ±35 cents by the note's end. Rate roughly 6 Hz. Delay + depth-envelope must both be expressible for the language to “express it fully”.

| language | snippet | chars | diff cost | expresses it fully? |
|---|---|---|---|---|
| TidalCycles | `d1 $ stack [note "c", midibend (smooth "8192@35 8500 7900 8800 7600 9200 7200 9600")] # s "m" # midichan 1` | 86 | 4 | partial |
| Strudel | `note("c4").midibend(sine2.fast(6).mul(saw).mul(.3)).midi()` | 58 | 2 | partial |
| Sonic Pi | `s=play 60,sustain: 4,note_slide: 0.06`<br>`sleep 1.4`<br>`6.times{\|i\| control s,note: 60+0.08*(i+1); sleep 0.13; control s,note: 60-0.08*(i+1); sleep 0.13}` | 129 | 4 | yes |
| Alda | **IMPOSSIBLE:** closest achievable — <br>`piano: (quant 99) o4 c1` | 19 | ∞ | no |
| Ziffers | **IMPOSSIBLE:** closest achievable — <br>`zplay "w 0", key: :c, scale: :minor, synth: :piano` | 42 | ∞ | no |
| LilyPond+articulate.ly | **IMPOSSIBLE:** closest achievable — <br>`{ c''1\startTrillSpan c''1\stopTrillSpan }` | 39 | ∞ | no |

**Per-language notes, with sources.**

- **TidalCycles** — `smooth` “receives a pattern of numbers and linearly goes from one to the next” ([oscillators](https://tidalcycles.org/docs/reference/oscillators/)) and `@` elongates a step ([mini-notation](https://tidalcycles.org/docs/reference/mini_notation/)), so `8192@35` buys the 35% delay and the widening is hand-drawn as literal 14-bit breakpoints ([Tidal MIDI](https://tidalcycles.org/docs/configuration/MIDIOSC/midi/)). Partial: the shape is anonymous, per-channel, and the depth is in bend units, not cents. *Diff cost 4:* each wiggle is its own literal, so changing the *depth* means editing 6 numbers (~24 chars); changing only the last excursion is 4 chars.
- **Strudel** — `sine2` (−1..1) and `saw` are documented signals ([signals](https://strudel.cc/learn/signals/)) and `.mul()` is a documented value modifier ([value modifiers](https://strudel.cc/functions/value-modifiers/)); multiplying the oscillator by a rising `saw` gives the widening. The 35% delay is what fails: no documented signal gates the first 35% of an event, so the vibrato starts at zero depth *at onset* instead. On Strudel's own synth the shorter `note("c4").vib("6:0.3")` exists but is constant-depth and undelayed — `vib` is “vibrato … in hertz”, `vibmod` “vibrato depth in semitones” ([synths](https://strudel.cc/learn/synths/)). *Diff cost 2:* `.3` → `.6`: 2 chars — the best diff cost of any rival, because depth is one named factor.
- **Sonic Pi** — Fully expressible on Sonic Pi's own synths: `sleep 1.4` is the 35% delay, `note_slide: 0.06` makes each step a glide rather than a jump (“sliding is sticky”), and `i+1` is the widening envelope ([tutorial §7.3](https://sonic-pi.net/tutorial.html), [control](https://sunderb.me/sonic-pi-docs-test/en/reference/lang/control.html)). Caveats: this is hand-unrolled time, one target per `control` call, and there is no MIDI equivalent — `midi_pitch_bend` is all-devices/all-channels by default ([midi_pitch_bend](https://sunderb.me/sonic-pi-docs-test/en/reference/lang/midi_pitch_bend.html)). *Diff cost 4:* `0.08` → `0.15`: 4 chars, one occurrence, because depth is a single multiplier in the loop.
- **Alda** — IMPOSSIBLE. Alda's only articulation lever is `quantization`, “the percentage of a note's full duration that is heard”, 0–100, default 90 ([attributes](https://alda.readthedocs.io/en/latest/attributes/)). Closest achievable: hold the note nearly its full length — a length change, not a pitch modulation. *Diff cost ∞:* no vibrato, no depth, nothing to edit.
- **Ziffers** — IMPOSSIBLE. Ziffers can vary Sonic Pi opts *between* events (rings, arrays, `tweak`, lambdas) but exposes no intra-note curve and no synth handle to `control` ([Effects](https://github.com/amiika/ziffers/wiki/Effects)). Closest achievable: a plain held degree. *Diff cost ∞:* no continuous-expression syntax at any depth.
- **LilyPond+articulate.ly** — IMPOSSIBLE. The nearest vocabulary items are `\startTrillSpan`/`\stopTrillSpan` and `\espressivo` ([expressive marks as lines](https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks-as-lines), [attached to notes](https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks-attached-to-notes)); `\articulate` renders “abbreviatures (such as trills and turns)” as *note sequences* and otherwise only scales note lengths ([enhancing MIDI output](https://lilypond.org/doc/v2.25/Documentation/notation/enhancing-midi-output)) — a semitone trill, not a widening vibrato. *Diff cost ∞:* a trill span has no depth, rate, or onset parameter.

**Which rival is the bar for T3.** **Strongest bar: Sonic Pi** — the only rival that can actually state both halves of the gesture (delay *and* widening) and hear them, via `sleep` + `note_slide:` + a `control` loop. But it costs ~130 non-whitespace characters of unrolled time and works only on internal synths. **On diffability the strongest bar is Strudel**: 2 characters (`.3`→`.6`) change the depth, because depth is a single named factor; its failure is the 35% onset.

---

## T4. One chord, four voices, four different pressure/timbre movements

**Task statement.** Sound Cm7 (C4 Eb4 G4 Bb4) as one chord for 4 beats. Each of the four voices must carry its own independent continuous movement over its own lifetime: e.g. bass pressure swelling up, tenor pressure fading, alto timbre (CC74) opening, soprano timbre closing. Four independent curves, four voices, one chord.

| language | snippet | chars | diff cost | expresses it fully? |
|---|---|---|---|---|
| TidalCycles | `d1 $ stack [`<br>`  note "c4" # midichan 2 # miditouch (segment 64 $ range 0 127 saw),`<br>`  note "ef4" # midichan 3 # miditouch (segment 64 $ range 0 127 isaw),`<br>`  note "g4" # midichan 4 # ccn 74 # ccv (segment 64 $ range 0 127 sine),`<br>`  note "bf4" # midichan 5 # ccn 74 # ccv (segment 64 $ range 127 40 saw)] # s "m"` | 231 | ∞ | partial |
| Strudel | `stack(`<br>`  note("c4").midichan(2).miditouch(saw),`<br>`  note("eb4").midichan(3).miditouch(saw.range(1,0)),`<br>`  note("g4").midichan(4).ccn(74).ccv(sine),`<br>`  note("bb4").midichan(5).ccn(74).ccv(saw.mul(.6))`<br>`).midi()` | 191 | ∞ | partial |
| Sonic Pi | `n=[60,63,67,70].map{\|p\| play p,sustain: 4,cutoff: 70,cutoff_slide: 4,amp_slide: 4}`<br>`control n[0],amp: 1.5; control n[1],amp: 0.2; control n[2],cutoff: 120; control n[3],cutoff: 40` | 160 | ∞ | partial |
| Alda | **IMPOSSIBLE:** closest achievable — <br>`piano:`<br>` V1: (panning 0) (vol 80) o4 c1`<br>` V2: (panning 35) (vol 55) o4 e-1`<br>` V3: (panning 65) (vol 70) o4 g1`<br>` V4: (panning 100) (vol 95) o4 b-1` | 108 | ∞ | no |
| Ziffers | **IMPOSSIBLE:** closest achievable — <br>`zplay "w i+4", key: :c, scale: :minor, amp: [0.6,0.8,1.0,1.2]` | 53 | ∞ | no |
| LilyPond+articulate.ly | **IMPOSSIBLE:** closest achievable — <br>`<< { c''1\< } \\ { es'1\> } \\ { g'1--} \\ { bes'1\staccato } >>` | 49 | ∞ | no |

**Per-language notes, with sources.**

- **TidalCycles** — Works only because you manually give each voice its own channel: `miditouch` (0–127 aftertouch), `ccn`/`ccv` (CC number / value 0–127), `midichan`, `segment`, `range`, `saw`, `isaw` are all documented ([Tidal MIDI](https://tidalcycles.org/docs/configuration/MIDIOSC/midi/), [oscillators](https://tidalcycles.org/docs/reference/oscillators/), [alteration: range](https://tidalcycles.org/docs/reference/alteration/)). Partial: nothing in Tidal allocates channels per sounding note (no MPE rotation is documented), the voices are four unrelated patterns rather than one chord, and the curves are channel-scoped by definition. *Diff cost ∞:* vibrato would need a fifth control (`midibend`) per voice; the depth then lives in two more `range` numbers per channel.
- **Strudel** — Same manual-channel trick, in about half the characters: `miditouch` (0–1), `ccn`/`ccv` (normalized 0–1) and `midichan` are documented, and `midichan` “will use channel 1 by default” — a single number per pattern, so four voices need four patterns ([Strudel MIDI I/O](https://strudel.cc/learn/input-output/)). UNVERIFIED: `saw.range(1,0)` (descending range) is not shown in the docs, which only demonstrate ascending `range(min,max)` ([value modifiers](https://strudel.cc/functions/value-modifiers/)). Note also that `voicing()` produces anonymous notes — there is no way to name the alto and address it. *Diff cost ∞:* depth of a per-voice vibrato = a new `.midibend(...)` chain per voice (~30 chars each).
- **Sonic Pi** — Genuinely four independent per-voice curves — every controllable opt has a `_slide` twin and each running synth has its own handle ([tutorial §7.2–7.3](https://sonic-pi.net/tutorial.html), [control](https://sunderb.me/sonic-pi-docs-test/en/reference/lang/control.html)). Partial because “pressure/timbre” becomes `amp`/`cutoff` on Sonic Pi's own synths: there is no per-note MIDI channel pressure or CC74 path (`midi_cc`/`midi_pitch_bend` are device/channel-wide), and ADSR opts cannot be changed once the synth is running. *Diff cost ∞:* each voice needs its own `note_slide` + `control` loop (T3 pattern) before there is a depth number to edit.
- **Alda** — IMPOSSIBLE. Alda has named voices `V1:`–`V4:` and per-voice `panning`/`volume`/`quant`, but every attribute is a single value that “take[s] effect for all of an instrument's upcoming notes” — a step, not a movement ([attributes](https://alda.readthedocs.io/en/latest/attributes/), [cheat sheet: voices](https://alda.io/cheat-sheet/)). Closest achievable: four voices with four static pan/volume values. *Diff cost ∞:* attributes are scalars set before a note; there is no time axis inside a note.
- **Ziffers** — IMPOSSIBLE. Opt arrays/rings in Ziffers are consumed *per event* (or per sample slot), not per chord member, and there is no intra-note curve ([Effects](https://github.com/amiika/ziffers/wiki/Effects)). UNVERIFIED: whether an `amp:` array distributes across the members of a single chord event is not documented; the documented use is per-degree/per-loop. Closest achievable: one chord, one opt trajectory across successive events. *Diff cost ∞:* nothing per-voice and nothing continuous.
- **LilyPond+articulate.ly** — IMPOSSIBLE. Simultaneous voices and per-voice hairpins/articulations exist as *engraving* ([expressive marks attached to notes](https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks-attached-to-notes)), but `articulate.ly` renders articulation by “adjusting note lengths” and “may shorten chords” ([MIDI articulation](https://lilypond.org/doc/v2.25/Documentation/usage/midi-articulation), [enhancing MIDI output](https://lilypond.org/doc/v2.25/Documentation/notation/enhancing-midi-output)) — no pressure or CC74 output at all. *Diff cost ∞:* dynamics/articulations are symbols; MIDI only sees note-length scaling.

**Which rival is the bar for T4.** **Strongest bar: Strudel** — fewest characters for four genuinely independent, genuinely continuous MIDI expression streams, using documented normalized ranges (`miditouch` 0–1, `ccv` 0–1) and one `midichan` per voice — 191 non-whitespace characters against Tidal's 231 for the same manual channel bookkeeping. Sonic Pi is the only rival whose four curves are attached to *named running voices*, but they are internal-synth `amp`/`cutoff`, not pressure/CC74. Alda, Ziffers and LilyPond cannot do it at all. Note what every rival shares: **the voices are four separate patterns or handles, not four members of one chord** — revoicing the chord silently breaks the mapping.

---

## T5. Modal-interchange substitution in the middle of the progression

**Task statement.** Take the T1 progression and replace bar 2's `G7` with a chord borrowed from the parallel Dorian — `IV` of C Dorian, i.e. F major/F7 — keeping the rest identical. “Expresses it fully” requires stating the substitution *functionally* (as a borrowed degree), not just spelling different notes.

| language | snippet | chars | diff cost | expresses it fully? |
|---|---|---|---|---|
| TidalCycles | `d1 $ n "<d4'm7f5'4 f4'dom7'4 c4'min9'4!2>" # s "superpiano"` | 51 | ∞ | no |
| Strudel | `chord("<Dm7b5 F7 Cm9!2>").voicing().midi()` | 40 | ∞ | no |
| Sonic Pi | `play chord_degree(:ii,:c4,:minor,4); sleep 4`<br>`play chord_degree(:iv,:c4,:dorian,4); sleep 4`<br>`2.times{play chord_degree(:i,:c4,:minor,4); sleep 4}` | 132 | ∞ | partial |
| Alda | `piano: o3 d1/f/a-/>c <f/a/>c/e- <c/e-/g/b- *2` | 40 | ∞ | no |
| Ziffers | `zplay "w (ii+4 ivd+4 i+4 i+4)<lead>", key: :c, scale: :minor` | 51 | ∞ | yes |
| LilyPond+articulate.ly | `{ <d' f' af' c''>1 <f' a' c'' es''> <c' es' g' bes'> <c' es' g' bes'> }` | 54 | ∞ | no |

**Per-language notes, with sources.**

- **TidalCycles** — Absolute chord names only — `chordList`/`chordTable` are literal interval sets with no key context and no roman numerals ([harmony & melody](https://tidalcycles.org/docs/reference/harmony_melody)). The borrowing is expressible *as sound* (2 characters change: `g4`→`f4`) but not *as function*: nothing in the text says “borrowed from Dorian”, and transposing the key means retyping every root. *Diff cost ∞:* unrelated to vibrato; no expression in this snippet.
- **Strudel** — Same story, shorter, and the voicing still re-smooths itself around the substitution ([understanding voicings](https://strudel.cc/understand/voicings/)). Strudel does have a scale-degree world (`n().scale()`, `scaleTranspose`) but the docs give no roman-numeral or borrowed-chord notation ([tonal API](https://strudel.cc/learn/tonal/)), so the modal source is untyped. *Diff cost ∞:* n/a in this snippet.
- **Sonic Pi** — The substitution *is* stated functionally — degree `:iv` of `:dorian` on the same tonic `:c4` is literally modal interchange, and `chord_degree` takes any scale name ([chord_degree](https://sunderb.me/sonic-pi-docs-test/en/reference/lang/chord_degree.html)). Partial only because it costs a full function call per chord (~35 chars) and there is no notation-level shorthand. *Diff cost ∞:* n/a in this snippet.
- **Alda** — Spelling only. Alda has `(key-sig! '(c minor))` and mode names for key signatures ([cheat sheet: key signature](https://alda.io/cheat-sheet/)) but no functional-harmony layer, so the borrowed chord is indistinguishable from any other four notes. *Diff cost ∞:* n/a; no expression attributes.
- **Ziffers** — A **one-character** substitution: `iv` → `ivd`, where the trailing mode letter is documented borrowed-chord syntax (`a` aeolian, `b` locrian, `c` ionian, `d` dorian, `e` phrygian, `f` lydian, `g` mixolydian) with an explicit suitable-chord-type table, e.g. `z1 "q i iiia iv iv"` ([Ziffers wiki: Chords — borrowed chords and modal interchange](https://github.com/amiika/ziffers/wiki/Chords)). Note the README cheatsheet's looser gloss “Modal interchange (a-g): iiia ig ivf^7” ([README](https://github.com/amiika/ziffers)) — the wiki table is the authoritative letter mapping. The voice leading `<lead>` re-solves automatically after the substitution. *Diff cost ∞:* n/a — Ziffers has no expression to diff.
- **LilyPond+articulate.ly** — Spelling only in the note stream. LilyPond does have `\chordmode`/figured bass, but no key-relative degree or borrowed-chord notation in the expressive/harmonic vocabulary ([expressive marks](https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks)). *Diff cost ∞:* n/a; MIDI expression is note-length scaling only.

**Which rival is the bar for T5.** **Strongest bar by a wide margin: Ziffers.** `ivd` — three characters, one of which *is* the modal source — states the borrowing functionally, in key, and re-voices via `<lead>` automatically. Sonic Pi is the only other rival that names the mode (`chord_degree(:iv,:c4,:dorian,4)`), at ~10× the characters. Everyone else can only respell notes. This is the highest bar in the whole set: **3 characters.**

---

## T6. Reuse one named expressive gesture across 12 notes, changing one parameter on the 7th

**Task statement.** Play 12 ascending notes. Attach the *same named* vibrato gesture to all 12. On note 7 only, change one of its parameters (depth). “Expresses it fully” requires (a) the gesture to be a named, parameterized, reusable value and (b) the note-7 override to be a local edit, not a rewritten copy of the gesture.

| language | snippet | chars | diff cost | expresses it fully? |
|---|---|---|---|---|
| TidalCycles | `let vib d = ccn 1 # ccv d`<br>`d1 $ stack [n "0 .. 11" # s "m" # midichan 1, vib "40!6 90 40!5"]` | 66 | 2 | partial |
| Strudel | `n("0 .. 11").scale("C:minor").vib(6).vibmod("0.3!6 0.7 0.3!5")` | 58 | 2 | partial |
| Sonic Pi | `define :vib do \|p,d\|`<br>`  play p,sustain: 0.4,note_slide: 0.1`<br>`  3.times{control note: p+d; sleep 0.06; control note: p-d; sleep 0.06}`<br>`end`<br>`12.times{\|i\| vib 60+i,(i==6 ? 0.5 : 0.15); sleep 0.5}` | 157 | 3 | yes |
| Alda | **IMPOSSIBLE:** closest achievable — <br>`vib = (quant 40)`<br>`piano: vib o4 c8 d e f g a (quant 75) b > c d e f g` | 47 | ∞ | no |
| Ziffers | **IMPOSSIBLE:** closest achievable — <br>`z1 "e (0..11)", release: [0.15]*6+[0.5]+[0.15]*5, synth: :piano` | 57 | ∞ | no |
| LilyPond+articulate.ly | **IMPOSSIBLE:** closest achievable — <br>`v = \startTrillSpan`<br>`w = \stopTrillSpan`<br>`{ c''8\v d''\w e''\v f''\w g''\v a''\w b''\prall > c''\v d''\w e''\v f''\w g''\w }` | 101 | ∞ | no |

**Per-language notes, with sources.**

- **TidalCycles** — The gesture is a real Haskell value (`let vib d = ...`), and the per-note override is mini-notation: `!` replicates steps and `0 .. 11` is a documented range ([mini-notation](https://tidalcycles.org/docs/reference/mini_notation/), [harmony & melody: `scale "ritusen" "0 .. 7"`](https://tidalcycles.org/docs/reference/harmony_melody)); `ccn`/`ccv` are documented CC controls ([Tidal MIDI](https://tidalcycles.org/docs/configuration/MIDIOSC/midi/)). Partial, and this is the honest catch: CC1 “vibrato depth” is an *instrument-side* response, not a curve Tidal draws — the language sends one scalar per note and the synth decides what vibrato means. *Diff cost 2:* `90` → `70`: 2 chars, in a per-step list — the cheapest per-note override of any rival.
- **Strudel** — `vib` (“vibrato … in hertz”, synonyms `vibrato`, `v`) and `vibmod` (“vibrato depth in semitones”, synonym `vmod`) both accept patterns, so per-note depth is native ([synths](https://strudel.cc/learn/synths/)); `!` replication and `0 .. 11` come from the mini-notation ([mini-notation](https://strudel.cc/learn/mini-notation/)). Partial for two reasons: the gesture is not *named* (there is no gesture value — you repeat two method calls, or wrap them in a JS function yourself), and `vib` is an effect on Strudel's own oscillator, so it does not travel over `midi()` — the MIDI path would be `ccn(1).ccv(...)` again ([MIDI I/O](https://strudel.cc/learn/input-output/)). *Diff cost 2:* `0.7` → `0.9`: 2 chars, and the depth is a first-class per-note value.
- **Sonic Pi** — The only rival that satisfies both halves: the gesture is a named, parameterized function (`define :vib do |p,d|`) whose body is a real pitch curve, and note 7 overrides one parameter inline (`i==6 ? 0.5 : 0.15`) ([tutorial §7.2–7.3 and §5 `define`](https://sonic-pi.net/tutorial.html), [control](https://sunderb.me/sonic-pi-docs-test/en/reference/lang/control.html)). Cost: ~40% more characters than Strudel, internal synths only, and the gesture is imperative time (`sleep`) rather than a shape, so it cannot be stretched, reversed, or composed with another gesture. *Diff cost 3:* `0.5` → `0.25`: 3 chars in the conditional override.
- **Alda** — IMPOSSIBLE for vibrato. Alda *does* have named reusable values — “Define your own shorthand: quiet = (vol 25)” and multi-line variables ([cheat sheet: variables](https://alda.io/cheat-sheet/)) — but the only expressive parameter to put in one is `quant`/`vol`/`panning` ([attributes](https://alda.readthedocs.io/en/latest/attributes/)). Closest achievable: a named articulation shorthand, overridden on the 7th note. *Diff cost ∞:* the reusable value exists; the vibrato does not.
- **Ziffers** — IMPOSSIBLE for vibrato. Ziffers has strong per-event opt variation — “Effects can also be adjusted on the fly using ring or array”, plus `tweak(:linear,…)`, lambdas, and `run_each` ([Effects](https://github.com/amiika/ziffers/wiki/Effects)) — and `(0..11)` ranges are documented ([README](https://github.com/amiika/ziffers)), so “one value differs on the 7th event” is idiomatic and terse. What is missing is any expressive parameter worth varying: no bend, vibrato, pressure or CC in the notation. UNVERIFIED: the exact `[x]*6+[y]` Ruby array form is my construction; the documented forms are literal arrays and rings. *Diff cost ∞:* no vibrato depth exists; the array varies a synth opt instead.
- **LilyPond+articulate.ly** — IMPOSSIBLE. Named reuse is fine — identifiers can hold any music or post-event — but the vocabulary has no parameterized vibrato: trill spans and ornaments only ([expressive marks as lines](https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks-as-lines)), and `\articulate` turns ornaments into note sequences while scaling everything else's length ([enhancing MIDI output](https://lilypond.org/doc/v2.25/Documentation/notation/enhancing-midi-output)). UNVERIFIED: whether `\prall` on one note is rendered by `articulate.ly` — the manual says the supported list lives in `ly/articulate.ly` itself, not in the docs. *Diff cost ∞:* a trill span has no depth parameter to change.

**Which rival is the bar for T6.** **Strongest bar: Strudel** on characters and diffability — `vibmod("0.3!6 0.7 0.3!5")` puts a per-note vibrato depth in one pattern, and the note-7 override is 2 characters. **Strongest bar on the actual requirement: Sonic Pi**, the only rival with a *named, parameterized* gesture (`define :vib do |p,d|`) that contains a real curve. The split is the interesting result: the terse rival has no named gesture, and the rival with a named gesture is imperative and MIDI-less.

---

## Cross-task observations a critic can lean on

1. **No rival can bind an expressive curve to a note.** In all six, expression is either a parallel channel-scoped stream (Tidal `midibend`/`ccv`, Strudel `midibend`/`ccv`), a scalar event field (Strudel `vibmod`, Ziffers opt arrays, Alda `quant`), a running-synth handle (Sonic Pi `control` + `_slide`), or a printed glyph (LilyPond). Tidal's own docs make the channel scoping explicit — `midibend` is a `ControlPattern` sent with `midichan` ([Tidal MIDI](https://tidalcycles.org/docs/configuration/MIDIOSC/midi/)) — and Strudel's `midichan` “will use channel 1 by default” ([Strudel MIDI I/O](https://strudel.cc/learn/input-output/)).
2. **No rival joins harmony to expression.** Strudel and Ziffers have the best harmony (`voicing()`; `ii+4 … <lead>`), and in both the resulting notes are anonymous, so T2's “bend into the next chord's third” and T4's per-voice curves cannot reference the harmony at all ([Strudel voicings](https://strudel.cc/understand/voicings/), [Ziffers Chords](https://github.com/amiika/ziffers/wiki/Chords)).
3. **The terseness bar and the expression bar are held by different languages.** Ziffers wins T1/T5 with 3–60 characters and cannot express T2/T3/T4/T6 at all; Sonic Pi expresses T2/T3/T6 and costs 100–180 characters of unrolled imperative time. A candidate must beat Ziffers on the harmony tasks and Sonic Pi on the gesture tasks *simultaneously* — no existing rival does.
4. **Diff cost is only cheap where depth is a named scalar.** The 2-character edits (Strudel `vibmod`, Tidal `ccv` step list) are cheap precisely because the value is one number per note in a list; the moment a curve is drawn as literal breakpoints (Tidal `smooth "8192@35 8500 …"`) the cost jumps to ~24 characters spread over six numbers, and in Alda / Ziffers / LilyPond it is unbounded because the parameter does not exist.
5. **Two rivals are the honest 'read it at a glance' bar**: Alda (`o3 d1/f/a-/>c`) and Ziffers (`w (ii+4 ivd+4 i+4 i+4)`). Both are unreadable-proof in the sense that a stranger can guess what they sound like — and both are silent on expression. That contrast is the P1(b)/P1(c) trap: prose-like readability has so far only been achieved by languages that dropped continuous expression entirely.

---

<!-- BEGIN FILIGREE SCOREBOARD (generated by score_filigree.py) -->

## Scoreboard: Filigree vs the strongest rival on each task

Generated by [`score_filigree.py`](score_filigree.py). Filigree solutions live in
[`filigree/`](filigree/) as standalone files; each one is compiled by the scorer and
only scores if it compiles with **zero warnings**. Counts are non-whitespace
characters excluding comment lines, the same rule used for the rival snippets above.

| Task | Filigree solution | chars | Strongest rival | chars | Result |
|---|---|---|---|---|---|
| **T1** 4-bar minor-key ii-V-i with smooth 4-voice voicings | [`filigree/T1.fil`](filigree/T1.fil) | 76 | Ziffers | 49 | **Ziffers shorter** by 27 |
| **T2** Melody; one note bends up into the next chord's third | [`filigree/T2.fil`](filigree/T2.fil) | 121 | Sonic Pi | 92 | **Sonic Pi shorter** by 29 |
| **T3** Vibrato starting 35% into a held note, widening to the end | [`filigree/T3.fil`](filigree/T3.fil) | 121 | Sonic Pi | 129 | **Filigree shorter** by 8 |
| **T4** One chord, four voices, four different pressure/timbre moves | [`filigree/T4.fil`](filigree/T4.fil) | 146 | Strudel | 191 | **Filigree shorter** by 45 |
| **T5** Modal-interchange substitution mid-progression | [`filigree/T5.fil`](filigree/T5.fil) | 77 | Ziffers | 51 | **Ziffers shorter** by 26 |
| **T6** One named gesture across 12 notes, one parameter changed on the 7th | [`filigree/T6.fil`](filigree/T6.fil) | 186 | Strudel | 58 | **Strudel shorter** by 128 |

**Concision record: Filigree is shorter on 2 of 6 tasks and longer on 4.**

One comparison needs a footnote:

- **T6:** the 58-char Strudel snippet does not express the whole task (see the T6 section). Against the shortest rival that does -- Sonic Pi, 157 chars -- Filigree's 186 chars are 29 longer.

The losses are real and are the interesting part. Where a rival is shorter it is
because that rival has a dedicated shorthand for exactly that task and nothing
else; Filigree spends its characters on a construct (`voicing`, a named gesture
with parameters, a harmonic target) that is reusable across all six. Concision is
only one of P1's four measures in [`../BAR.md`](../BAR.md) -- the others are
expressive completeness, diff cost, and how much of the task the language can state
at all. Per-task expressive verdicts are in the task sections above.

<!-- END FILIGREE SCOREBOARD -->
