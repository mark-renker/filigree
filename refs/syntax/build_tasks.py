# Builds refs/syntax/tasks.md from verified snippet data.
# Char counts are computed, never typed by hand: non-whitespace characters.
import re, json, os

def nw(s):
    return len(re.sub(r"\s+", "", s))

D = "https://"  # noop

LANGS = ["TidalCycles", "Strudel", "Sonic Pi", "Alda", "Ziffers", "LilyPond+articulate.ly"]

tasks = []

# ---------------------------------------------------------------- T1
tasks.append(dict(
 id="T1",
 title="4-bar minor-key ii–V–i with smooth 4-voice voicings",
 statement=(
  "In C minor, write four bars, one chord per bar: **Dm7b5 | G7 | Cm9 | Cm9** "
  "(ii\u00f87 – V7 – i9 – i9). Each chord must sound as exactly four voices, and successive "
  "chords must be voiced so that total voice movement is small (no voice leaps an octave, no crossing)."),
 rows=[
  dict(lang="TidalCycles",
    snip='d1 $ n "<d4\'m7f5\'4 g4\'dom7\'4 c4\'min9\'4!2>" # s "superpiano"',
    full="partial",
    diff="\u221e",
    diffnote="no vibrato exists in this snippet; adding one means a second parallel `midibend`/`ccv` pattern (~45 chars), and it lands on the whole channel, not one note",
    note=("Chord names `m7f5`, `dom7`, `min9` and the voice-count modifier `'4` are documented "
       "([Tidal harmony & melody](https://tidalcycles.org/docs/reference/harmony_melody)); `!2` repeats a step "
       "([mini-notation](https://tidalcycles.org/docs/reference/mini_notation/)). Voicing control is limited to "
       "`'o` (open), `'dN` (drop N), `'iN` (inversion) and tone count \u2014 there is **no** voice-leading function, so "
       "smoothness must be hand-chosen per chord.")),
  dict(lang="Strudel",
    snip='chord("<Dm7b5 G7 Cm9!2>").voicing().midi()',
    full="yes",
    diff="\u221e",
    diffnote="no per-note vibrato: `.vib()` is a synth-side effect on Strudel's own oscillator and is one value per event; over MIDI, depth would be a channel-wide `ccv`",
    note=("`chord`, `voicing`, `dict`, `anchor`, `mode` are documented; the default dictionary lists `Dm7b5`, `G7`, `Cm9` "
       "verbatim and \u201cthe `voicing` function tries to minimize jumps\u201d "
       "([understanding voicings](https://strudel.cc/understand/voicings/), [tonal API](https://strudel.cc/learn/tonal/)). "
       "UNVERIFIED: the docs do not promise a fixed voice count, so \u201cexactly four voices\u201d depends on the dictionary entry "
       "chosen (`.dict('lefthand')` is shown in the tonal docs as a 4-note left-hand dictionary but its size is not stated).")),
  dict(lang="Sonic Pi",
    snip='[:ii,:v,:i,:i].each{|d| play chord_degree(d,:c4,:minor,4),sustain: 3.5; sleep 4}',
    full="partial",
    diff="\u221e",
    diffnote="`play` takes no vibrato opt; vibrato requires re-writing the chord as separate handles plus a `control`/`note_slide` loop per voice (T3 pattern, ~90 chars per voice)",
    note=("`chord_degree degree, tonic, scale, number_of_notes` with degrees `:i`\u2026`:vii` is documented and yields the "
       "diatonic 7th chords of C minor (so `:ii` is automatically m7b5) "
       "([chord_degree](https://sunderb.me/sonic-pi-docs-test/en/reference/lang/chord_degree.html)); `chord_invert` / the "
       "`invert:` opt is the only voicing control "
       "([chord_invert](https://sunderb.me/sonic-pi-docs-test/en/reference/lang/chord_invert.html)) \u2014 no voice-leading, so "
       "the voicings are close-position and the ii\u2192V motion is not minimised.")),
  dict(lang="Alda",
    snip='piano: o3 d1/f/a-/>c <g/b/>d/f <c/e-/g/b- *2',
    full="yes",
    diff="\u221e",
    diffnote="Alda's whole attribute set is `duration, key-signature, octave, panning, quantization, tempo, track-volume, volume` \u2014 there is no bend, vibrato, pressure or CC attribute at all",
    note=("Chords `c1/e-/g/b`, sticky note length, octave `<`/`>`, accidentals `+`/`-` and chord repeat `*2` are all in the "
       "[cheat sheet](https://alda.io/cheat-sheet/). Voice leading is whatever you type \u2014 fully expressible, zero help "
       "([attributes](https://alda.readthedocs.io/en/latest/attributes/)).")),
  dict(lang="Ziffers",
    snip='zplay "w (ii+4 v+4 i+4 i+4)<lead>", key: :c, scale: :minor',
    full="yes",
    diff="\u221e",
    diffnote="Ziffers has no expression syntax; the only lever is passing a Sonic Pi opt (e.g. `release:`) per degree as an array/ring, which cannot shape one note's pitch over time",
    note=("`i`\u2026`vii` build chords from the given scale, `+4` makes it a 7th chord (4 notes), and the `<lead>` transformation "
       "is documented as voice leading using \u201cthe taxi cab metric algorithm described in *The Geometry of Music*\u201d "
       "([Ziffers wiki: Chords](https://github.com/amiika/ziffers/wiki/Chords)); duration char `w` = whole "
       "([README cheatsheet](https://github.com/amiika/ziffers)). This is the only rival that gets correct minor-key "
       "ii\u2013V\u2013i **and** algorithmic voice leading in one line.")),
  dict(lang="LilyPond+articulate.ly",
    snip="{ <d' f' af' c''>1 <g' b' d'' f''> <c' es' g' bes'> <c' es' g' bes'> }",
    full="yes",
    diff="\u221e",
    diffnote="`articulate.ly` works purely by \u201cadjusting note lengths \u2026 according to the articulation markings\u201d \u2014 there is no vibrato depth to edit",
    note=("Chords `<...>`, absolute octaves and durations are core notation; MIDI comes from a `\\midi { }` block, optionally "
       "through `\\articulate` ([MIDI articulation](https://lilypond.org/doc/v2.25/Documentation/usage/midi-articulation), "
       "[enhancing MIDI output](https://lilypond.org/doc/v2.25/Documentation/notation/enhancing-midi-output)). Voicing is "
       "manual; engraving is the point.")),
 ],
 verdict=("**Strongest bar: Ziffers.** It is the only rival where the harmony is stated functionally (`ii+4 v+4 i+4`) *and* the "
      "voicing is solved for you by a documented voice-leading transformation `<lead>`. Strudel is a close second and is "
      "shorter, but its chords are absolute symbols (`Dm7b5`), so the key is implicit and re-keying means retyping every "
      "symbol. Tidal, Sonic Pi, Alda and LilyPond all require the composer to do the voice leading by hand."),
))

# ---------------------------------------------------------------- T2
tasks.append(dict(
 id="T2",
 title="Melody over the progression; one note bends up into the next chord's third",
 statement=(
  "Over the T1 progression, play a four-note melody `C5 Eb5 D5 D5`. The last `D5` must bend **up one semitone** "
  "during its own lifetime so that it arrives on `Eb5` \u2014 the third of the following `Cm9` \u2014 exactly at the bar line. "
  "The bend target must be the *chord's third*, not a hand-typed number, for the language to \u201cexpress it fully\u201d."),
 rows=[
  dict(lang="TidalCycles",
    snip='d1 $ stack [note "c5 ef5 d5 d5", midibend (compress (0.75,1) $ segment 64 $ range 8192 12288 saw)] # s "m" # midichan 1',
    full="no",
    diff="4",
    diffnote="`12288` \u2192 e.g. `13000`: 4 digits changed, but the edit is on a *parallel* pattern, not on the note token",
    note=("IMPOSSIBLE as specified. `midibend` is documented as a channel-scoped control pattern over the raw 14-bit range "
       "`0\u201316383`, `8192` neutral ([Tidal MIDI](https://tidalcycles.org/docs/configuration/MIDIOSC/midi/)), so (a) the target "
       "must be hand-computed \u2014 `12288` is +1 semitone only if the device's bend range is \u00b12 semitones, which Tidal does not "
       "set \u2014 and (b) the bend hits every note on channel 1, not just the last `D5`. Closest achievable: the snippet above, "
       "where `compress (0.75,1)` confines the ramp to the 4th beat "
       "([compress](https://tidalcycles.org/docs/reference/time/)) and `segment 64` sets the message rate.")),
  dict(lang="Strudel",
    snip='$: note("c5 eb5 d5 d5").midi()\n$: midibend(saw.range(0,.5).segment(32)).struct("~@3 x").midi()',
    full="no",
    diff="2",
    diffnote="`.5` \u2192 `.8` in the `range`, 2 chars \u2014 again on a separate lane",
    note=("IMPOSSIBLE as specified. `midibend` \u201csets MIDI pitch bend (-1 - 1)\u201d "
       "([Strudel MIDI I/O](https://strudel.cc/learn/input-output/)), so \u201c+1 semitone\u201d is `0.5` *only* if the synth's bend "
       "range is \u00b12 semitones \u2014 a number you compute, not a musical reference. Bend is also per-channel (`midichan` defaults "
       "to 1). `saw`/`range` are documented ([signals](https://strudel.cc/learn/signals/), "
       "[value modifiers](https://strudel.cc/functions/value-modifiers/)); the docs also warn that in one chained pattern "
       "\u201cstructure comes from the left\u201d, which is why the bend is written as its own `$:` lane.")),
  dict(lang="Sonic Pi",
    snip='play :c5; sleep 1; play :eb5; sleep 1\ns=play :d5,sustain: 1.8,note_slide: 0.5\nsleep 1.5\ncontrol s,note: :eb5',
    full="partial",
    diff="3",
    diffnote="edit the slide target/`note_slide:` value, e.g. `0.5`\u2192`0.25`: 3 chars",
    note=("The closest any rival gets: `note_slide:` plus `control` genuinely bends one voice's pitch over its own lifetime, "
       "with an audible glide, and the destination is written as a pitch name (`:eb5`) "
       "([Sonic Pi tutorial \u00a77.3 Sliding Opts](https://sonic-pi.net/tutorial.html), "
       "[control](https://sunderb.me/sonic-pi-docs-test/en/reference/lang/control.html)). Still not \u201cthe next chord's third\u201d: "
       "you type the pitch. Internal synths only \u2014 the MIDI path is `midi_pitch_bend`, which sends \u201cto *all* connected devices "
       "on *all* channels\u201d unless restricted "
       "([midi_pitch_bend](https://sunderb.me/sonic-pi-docs-test/en/reference/lang/midi_pitch_bend.html)).")),
  dict(lang="Alda",
    snip='piano: o5 c4 e- d~ e-8',
    full="no",
    diff="\u221e",
    diffnote="no bend/vibrato attribute exists",
    note=("IMPOSSIBLE. The documented attribute set is duration, key-signature, octave, panning, quantization, tempo, "
       "track-volume, volume ([Alda attributes](https://alda.readthedocs.io/en/latest/attributes/)) \u2014 no pitch bend, no CC. "
       "Closest achievable: a slur/legato step up to the target third (`d~ e-8`), i.e. two discrete notes instead of one bent "
       "note ([cheat sheet: slurs](https://alda.io/cheat-sheet/)).")),
  dict(lang="Ziffers",
    snip='zplay "q 4 6 5 5", key: :c, scale: :minor',
    full="no",
    diff="\u221e",
    diffnote="no bend syntax; Sonic Pi opts passed by Ziffers are set at note start and never `control`led afterwards",
    note=("IMPOSSIBLE. Ziffers' notation covers pitch, rhythm, chords, generative operations \u2014 nothing continuous "
       "([README cheatsheet](https://github.com/amiika/ziffers), [Effects](https://github.com/amiika/ziffers/wiki/Effects) "
       "which varies opts *per degree*, not *within* a note). Closest achievable: play the target third as the next degree.")),
  dict(lang="LilyPond+articulate.ly",
    snip="{ c''4 es'' d''\\glissando es''4 }",
    full="no",
    diff="\u221e",
    diffnote="nothing to edit \u2014 no bend depth parameter in the language",
    note=("IMPOSSIBLE. `\\glissando` and `\\bendAfter #+4` are engraving marks; `\\bendAfter`'s number \u201cindicates the pitch "
       "interval that the fall or doit will extend *beyond* the main note\u201d and is drawn, not performed "
       "([falls and doits](https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks-as-curves), "
       "[expressive marks as lines](https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks-as-lines)); "
       "`articulate.ly` only \u201cadjust[s] note lengths\u201d "
       "([MIDI articulation](https://lilypond.org/doc/v2.25/Documentation/usage/midi-articulation)), so no pitch curve reaches "
       "the MIDI file.")),
 ],
 verdict=("**Strongest bar: Sonic Pi.** It is the only rival that actually bends a single voice into a named destination pitch "
      "inside that note's lifetime (`note_slide:` + `control s,note: :eb5`), and it is the shortest thing that makes an audible "
      "glide. Tidal and Strudel can draw a bend curve but only channel-wide and only in hand-computed bend units; Alda, "
      "Ziffers and LilyPond cannot bend at all. **No rival can name the target harmonically** \u2014 every one of them makes you "
      "type the pitch of the next chord's third yourself."),
))

# ---------------------------------------------------------------- T3
tasks.append(dict(
 id="T3",
 title="Vibrato that starts 35% into a held note and widens toward the end",
 statement=(
  "One held note (4 beats, C4). Nothing for the first 35% of its duration; then vibrato begins and its depth grows "
  "monotonically from ~0 to about \u00b135 cents by the note's end. Rate roughly 6 Hz. Delay + depth-envelope must both be "
  "expressible for the language to \u201cexpress it fully\u201d."),
 rows=[
  dict(lang="TidalCycles",
    snip='d1 $ stack [note "c", midibend (smooth "8192@35 8500 7900 8800 7600 9200 7200 9600")] # s "m" # midichan 1',
    full="partial",
    diff="4",
    diffnote="each wiggle is its own literal, so changing the *depth* means editing 6 numbers (~24 chars); changing only the last excursion is 4 chars",
    note=("`smooth` \u201creceives a pattern of numbers and linearly goes from one to the next\u201d "
       "([oscillators](https://tidalcycles.org/docs/reference/oscillators/)) and `@` elongates a step "
       "([mini-notation](https://tidalcycles.org/docs/reference/mini_notation/)), so `8192@35` buys the 35% delay and the "
       "widening is hand-drawn as literal 14-bit breakpoints "
       "([Tidal MIDI](https://tidalcycles.org/docs/configuration/MIDIOSC/midi/)). Partial: the shape is anonymous, per-channel, "
       "and the depth is in bend units, not cents.")),
  dict(lang="Strudel",
    snip='note("c4").midibend(sine2.fast(6).mul(saw).mul(.3)).midi()',
    full="partial",
    diff="2",
    diffnote="`.3` \u2192 `.6`: 2 chars \u2014 the best diff cost of any rival, because depth is one named factor",
    note=("`sine2` (\u22121..1) and `saw` are documented signals ([signals](https://strudel.cc/learn/signals/)) and `.mul()` is a "
       "documented value modifier ([value modifiers](https://strudel.cc/functions/value-modifiers/)); multiplying the "
       "oscillator by a rising `saw` gives the widening. The 35% delay is what fails: no documented signal gates the first 35% "
       "of an event, so the vibrato starts at zero depth *at onset* instead. On Strudel's own synth the shorter "
       "`note(\"c4\").vib(\"6:0.3\")` exists but is constant-depth and undelayed \u2014 `vib` is \u201cvibrato \u2026 in hertz\u201d, `vibmod` "
       "\u201cvibrato depth in semitones\u201d ([synths](https://strudel.cc/learn/synths/)).")),
  dict(lang="Sonic Pi",
    snip='s=play 60,sustain: 4,note_slide: 0.06\nsleep 1.4\n6.times{|i| control s,note: 60+0.08*(i+1); sleep 0.13; control s,note: 60-0.08*(i+1); sleep 0.13}',
    full="yes",
    diff="4",
    diffnote="`0.08` \u2192 `0.15`: 4 chars, one occurrence, because depth is a single multiplier in the loop",
    note=("Fully expressible on Sonic Pi's own synths: `sleep 1.4` is the 35% delay, `note_slide: 0.06` makes each step a glide "
       "rather than a jump (\u201csliding is sticky\u201d), and `i+1` is the widening envelope "
       "([tutorial \u00a77.3](https://sonic-pi.net/tutorial.html), "
       "[control](https://sunderb.me/sonic-pi-docs-test/en/reference/lang/control.html)). Caveats: this is hand-unrolled time, "
       "one target per `control` call, and there is no MIDI equivalent \u2014 `midi_pitch_bend` is all-devices/all-channels by "
       "default ([midi_pitch_bend](https://sunderb.me/sonic-pi-docs-test/en/reference/lang/midi_pitch_bend.html)).")),
  dict(lang="Alda",
    snip='piano: (quant 99) o4 c1',
    full="no",
    diff="\u221e",
    diffnote="no vibrato, no depth, nothing to edit",
    note=("IMPOSSIBLE. Alda's only articulation lever is `quantization`, \u201cthe percentage of a note's full duration that is "
       "heard\u201d, 0\u2013100, default 90 ([attributes](https://alda.readthedocs.io/en/latest/attributes/)). Closest achievable: "
       "hold the note nearly its full length \u2014 a length change, not a pitch modulation.")),
  dict(lang="Ziffers",
    snip='zplay "w 0", key: :c, scale: :minor, synth: :piano',
    full="no",
    diff="\u221e",
    diffnote="no continuous-expression syntax at any depth",
    note=("IMPOSSIBLE. Ziffers can vary Sonic Pi opts *between* events (rings, arrays, `tweak`, lambdas) but exposes no "
       "intra-note curve and no synth handle to `control` "
       "([Effects](https://github.com/amiika/ziffers/wiki/Effects)). Closest achievable: a plain held degree.")),
  dict(lang="LilyPond+articulate.ly",
    snip="{ c''1\\startTrillSpan c''1\\stopTrillSpan }",
    full="no",
    diff="\u221e",
    diffnote="a trill span has no depth, rate, or onset parameter",
    note=("IMPOSSIBLE. The nearest vocabulary items are `\\startTrillSpan`/`\\stopTrillSpan` and `\\espressivo` "
       "([expressive marks as lines](https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks-as-lines), "
       "[attached to notes](https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks-attached-to-notes)); "
       "`\\articulate` renders \u201cabbreviatures (such as trills and turns)\u201d as *note sequences* and otherwise only scales note "
       "lengths ([enhancing MIDI output](https://lilypond.org/doc/v2.25/Documentation/notation/enhancing-midi-output)) \u2014 a "
       "semitone trill, not a widening vibrato.")),
 ],
 verdict=("**Strongest bar: Sonic Pi** \u2014 the only rival that can actually state both halves of the gesture (delay *and* widening) "
      "and hear them, via `sleep` + `note_slide:` + a `control` loop. But it costs ~130 non-whitespace characters of unrolled "
      "time and works only on internal synths. **On diffability the strongest bar is Strudel**: 2 characters (`.3`\u2192`.6`) change "
      "the depth, because depth is a single named factor; its failure is the 35% onset."),
))

# ---------------------------------------------------------------- T4
tasks.append(dict(
 id="T4",
 title="One chord, four voices, four different pressure/timbre movements",
 statement=(
  "Sound Cm7 (C4 Eb4 G4 Bb4) as one chord for 4 beats. Each of the four voices must carry its own independent "
  "continuous movement over its own lifetime: e.g. bass pressure swelling up, tenor pressure fading, alto timbre "
  "(CC74) opening, soprano timbre closing. Four independent curves, four voices, one chord."),
 rows=[
  dict(lang="TidalCycles",
    snip='d1 $ stack [\n  note "c4" # midichan 2 # miditouch (segment 64 $ range 0 127 saw),\n  note "ef4" # midichan 3 # miditouch (segment 64 $ range 0 127 isaw),\n  note "g4" # midichan 4 # ccn 74 # ccv (segment 64 $ range 0 127 sine),\n  note "bf4" # midichan 5 # ccn 74 # ccv (segment 64 $ range 127 40 saw)] # s "m"',
    full="partial",
    diff="\u221e",
    diffnote="vibrato would need a fifth control (`midibend`) per voice; the depth then lives in two more `range` numbers per channel",
    note=("Works only because you manually give each voice its own channel: `miditouch` (0\u2013127 aftertouch), `ccn`/`ccv` "
       "(CC number / value 0\u2013127), `midichan`, `segment`, `range`, `saw`, `isaw` are all documented "
       "([Tidal MIDI](https://tidalcycles.org/docs/configuration/MIDIOSC/midi/), "
       "[oscillators](https://tidalcycles.org/docs/reference/oscillators/), "
       "[alteration: range](https://tidalcycles.org/docs/reference/alteration/)). Partial: nothing in Tidal allocates channels "
       "per sounding note (no MPE rotation is documented), the voices are four unrelated patterns rather than one chord, and "
       "the curves are channel-scoped by definition.")),
  dict(lang="Strudel",
    snip='stack(\n  note("c4").midichan(2).miditouch(saw),\n  note("eb4").midichan(3).miditouch(saw.range(1,0)),\n  note("g4").midichan(4).ccn(74).ccv(sine),\n  note("bb4").midichan(5).ccn(74).ccv(saw.mul(.6))\n).midi()',
    full="partial",
    diff="\u221e",
    diffnote="depth of a per-voice vibrato = a new `.midibend(...)` chain per voice (~30 chars each)",
    note=("Same manual-channel trick, in about half the characters: `miditouch` (0\u20131), `ccn`/`ccv` (normalized 0\u20131) and "
       "`midichan` are documented, and `midichan` \u201cwill use channel 1 by default\u201d \u2014 a single number per pattern, so four "
       "voices need four patterns ([Strudel MIDI I/O](https://strudel.cc/learn/input-output/)). "
       "UNVERIFIED: `saw.range(1,0)` (descending range) is not shown in the docs, which only demonstrate ascending "
       "`range(min,max)` ([value modifiers](https://strudel.cc/functions/value-modifiers/)). Note also that `voicing()` "
       "produces anonymous notes \u2014 there is no way to name the alto and address it.")),
  dict(lang="Sonic Pi",
    snip='n=[60,63,67,70].map{|p| play p,sustain: 4,cutoff: 70,cutoff_slide: 4,amp_slide: 4}\ncontrol n[0],amp: 1.5; control n[1],amp: 0.2; control n[2],cutoff: 120; control n[3],cutoff: 40',
    full="partial",
    diff="\u221e",
    diffnote="each voice needs its own `note_slide` + `control` loop (T3 pattern) before there is a depth number to edit",
    note=("Genuinely four independent per-voice curves \u2014 every controllable opt has a `_slide` twin and each running synth has "
       "its own handle ([tutorial \u00a77.2\u20137.3](https://sonic-pi.net/tutorial.html), "
       "[control](https://sunderb.me/sonic-pi-docs-test/en/reference/lang/control.html)). Partial because \u201cpressure/timbre\u201d "
       "becomes `amp`/`cutoff` on Sonic Pi's own synths: there is no per-note MIDI channel pressure or CC74 path "
       "(`midi_cc`/`midi_pitch_bend` are device/channel-wide), and ADSR opts cannot be changed once the synth is running.")),
  dict(lang="Alda",
    snip='piano:\n V1: (panning 0) (vol 80) o4 c1\n V2: (panning 35) (vol 55) o4 e-1\n V3: (panning 65) (vol 70) o4 g1\n V4: (panning 100) (vol 95) o4 b-1',
    full="no",
    diff="\u221e",
    diffnote="attributes are scalars set before a note; there is no time axis inside a note",
    note=("IMPOSSIBLE. Alda has named voices `V1:`\u2013`V4:` and per-voice `panning`/`volume`/`quant`, but every attribute is a "
       "single value that \u201ctake[s] effect for all of an instrument's upcoming notes\u201d \u2014 a step, not a movement "
       "([attributes](https://alda.readthedocs.io/en/latest/attributes/), [cheat sheet: voices](https://alda.io/cheat-sheet/)). "
       "Closest achievable: four voices with four static pan/volume values.")),
  dict(lang="Ziffers",
    snip='zplay "w i+4", key: :c, scale: :minor, amp: [0.6,0.8,1.0,1.2]',
    full="no",
    diff="\u221e",
    diffnote="nothing per-voice and nothing continuous",
    note=("IMPOSSIBLE. Opt arrays/rings in Ziffers are consumed *per event* (or per sample slot), not per chord member, and "
       "there is no intra-note curve ([Effects](https://github.com/amiika/ziffers/wiki/Effects)). "
       "UNVERIFIED: whether an `amp:` array distributes across the members of a single chord event is not documented; the "
       "documented use is per-degree/per-loop. Closest achievable: one chord, one opt trajectory across successive events.")),
  dict(lang="LilyPond+articulate.ly",
    snip="<< { c''1\\< } \\\\ { es'1\\> } \\\\ { g'1--} \\\\ { bes'1\\staccato } >>",
    full="no",
    diff="\u221e",
    diffnote="dynamics/articulations are symbols; MIDI only sees note-length scaling",
    note=("IMPOSSIBLE. Simultaneous voices and per-voice hairpins/articulations exist as *engraving* "
       "([expressive marks attached to notes](https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks-attached-to-notes)), "
       "but `articulate.ly` renders articulation by \u201cadjusting note lengths\u201d and \u201cmay shorten chords\u201d "
       "([MIDI articulation](https://lilypond.org/doc/v2.25/Documentation/usage/midi-articulation), "
       "[enhancing MIDI output](https://lilypond.org/doc/v2.25/Documentation/notation/enhancing-midi-output)) \u2014 no pressure or "
       "CC74 output at all.")),
 ],
 verdict=("**Strongest bar: Strudel** \u2014 fewest characters for four genuinely independent, genuinely continuous MIDI expression "
      "streams, using documented normalized ranges (`miditouch` 0\u20131, `ccv` 0\u20131) and one `midichan` per voice — 191 non-whitespace "
      "characters against Tidal's 231 for the same manual channel bookkeeping. Sonic Pi is the only rival "
      "whose four curves are attached to *named running voices*, but they are internal-synth `amp`/`cutoff`, not pressure/CC74. "
      "Alda, Ziffers and LilyPond cannot do it at all. Note what every rival shares: **the voices are four separate patterns or "
      "handles, not four members of one chord** \u2014 revoicing the chord silently breaks the mapping."),
))

# ---------------------------------------------------------------- T5
tasks.append(dict(
 id="T5",
 title="Modal-interchange substitution in the middle of the progression",
 statement=(
  "Take the T1 progression and replace bar 2's `G7` with a chord borrowed from the parallel Dorian \u2014 `IV` of C Dorian, "
  "i.e. F major/F7 \u2014 keeping the rest identical. \u201cExpresses it fully\u201d requires stating the substitution *functionally* "
  "(as a borrowed degree), not just spelling different notes."),
 rows=[
  dict(lang="TidalCycles",
    snip='d1 $ n "<d4\'m7f5\'4 f4\'dom7\'4 c4\'min9\'4!2>" # s "superpiano"',
    full="no",
    diff="\u221e",
    diffnote="unrelated to vibrato; no expression in this snippet",
    note=("Absolute chord names only \u2014 `chordList`/`chordTable` are literal interval sets with no key context and no roman "
       "numerals ([harmony & melody](https://tidalcycles.org/docs/reference/harmony_melody)). The borrowing is expressible "
       "*as sound* (2 characters change: `g4`\u2192`f4`) but not *as function*: nothing in the text says \u201cborrowed from Dorian\u201d, "
       "and transposing the key means retyping every root.")),
  dict(lang="Strudel",
    snip='chord("<Dm7b5 F7 Cm9!2>").voicing().midi()',
    full="no",
    diff="\u221e",
    diffnote="n/a in this snippet",
    note=("Same story, shorter, and the voicing still re-smooths itself around the substitution "
       "([understanding voicings](https://strudel.cc/understand/voicings/)). Strudel does have a scale-degree world "
       "(`n().scale()`, `scaleTranspose`) but the docs give no roman-numeral or borrowed-chord notation "
       "([tonal API](https://strudel.cc/learn/tonal/)), so the modal source is untyped.")),
  dict(lang="Sonic Pi",
    snip='play chord_degree(:ii,:c4,:minor,4); sleep 4\nplay chord_degree(:iv,:c4,:dorian,4); sleep 4\n2.times{play chord_degree(:i,:c4,:minor,4); sleep 4}',
    full="partial",
    diff="\u221e",
    diffnote="n/a in this snippet",
    note=("The substitution *is* stated functionally \u2014 degree `:iv` of `:dorian` on the same tonic `:c4` is literally modal "
       "interchange, and `chord_degree` takes any scale name "
       "([chord_degree](https://sunderb.me/sonic-pi-docs-test/en/reference/lang/chord_degree.html)). Partial only because it "
       "costs a full function call per chord (~35 chars) and there is no notation-level shorthand.")),
  dict(lang="Alda",
    snip='piano: o3 d1/f/a-/>c <f/a/>c/e- <c/e-/g/b- *2',
    full="no",
    diff="\u221e",
    diffnote="n/a; no expression attributes",
    note=("Spelling only. Alda has `(key-sig! '(c minor))` and mode names for key signatures "
       "([cheat sheet: key signature](https://alda.io/cheat-sheet/)) but no functional-harmony layer, so the borrowed chord is "
       "indistinguishable from any other four notes.")),
  dict(lang="Ziffers",
    snip='zplay "w (ii+4 ivd+4 i+4 i+4)<lead>", key: :c, scale: :minor',
    full="yes",
    diff="\u221e",
    diffnote="n/a \u2014 Ziffers has no expression to diff",
    note=("A **one-character** substitution: `iv` \u2192 `ivd`, where the trailing mode letter is documented borrowed-chord syntax "
       "(`a` aeolian, `b` locrian, `c` ionian, `d` dorian, `e` phrygian, `f` lydian, `g` mixolydian) with an explicit "
       "suitable-chord-type table, e.g. `z1 \"q i iiia iv iv\"` "
       "([Ziffers wiki: Chords \u2014 borrowed chords and modal interchange](https://github.com/amiika/ziffers/wiki/Chords)). Note "
       "the README cheatsheet's looser gloss \u201cModal interchange (a-g): iiia ig ivf^7\u201d "
       "([README](https://github.com/amiika/ziffers)) \u2014 the wiki table is the authoritative letter mapping. The voice leading "
       "`<lead>` re-solves automatically after the substitution.")),
  dict(lang="LilyPond+articulate.ly",
    snip="{ <d' f' af' c''>1 <f' a' c'' es''> <c' es' g' bes'> <c' es' g' bes'> }",
    full="no",
    diff="\u221e",
    diffnote="n/a; MIDI expression is note-length scaling only",
    note=("Spelling only in the note stream. LilyPond does have `\\chordmode`/figured bass, but no key-relative degree or "
       "borrowed-chord notation in the expressive/harmonic vocabulary "
       "([expressive marks](https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks)).")),
 ],
 verdict=("**Strongest bar by a wide margin: Ziffers.** `ivd` \u2014 three characters, one of which *is* the modal source \u2014 states the "
      "borrowing functionally, in key, and re-voices via `<lead>` automatically. Sonic Pi is the only other rival that names the "
      "mode (`chord_degree(:iv,:c4,:dorian,4)`), at ~10\u00d7 the characters. Everyone else can only respell notes. This is the "
      "highest bar in the whole set: **3 characters.**"),
))

# ---------------------------------------------------------------- T6
tasks.append(dict(
 id="T6",
 title="Reuse one named expressive gesture across 12 notes, changing one parameter on the 7th",
 statement=(
  "Play 12 ascending notes. Attach the *same named* vibrato gesture to all 12. On note 7 only, change one of its "
  "parameters (depth). \u201cExpresses it fully\u201d requires (a) the gesture to be a named, parameterized, reusable value and "
  "(b) the note-7 override to be a local edit, not a rewritten copy of the gesture."),
 rows=[
  dict(lang="TidalCycles",
    snip='let vib d = ccn 1 # ccv d\nd1 $ stack [n "0 .. 11" # s "m" # midichan 1, vib "40!6 90 40!5"]',
    full="partial",
    diff="2",
    diffnote="`90` \u2192 `70`: 2 chars, in a per-step list \u2014 the cheapest per-note override of any rival",
    note=("The gesture is a real Haskell value (`let vib d = ...`), and the per-note override is mini-notation: `!` replicates "
       "steps and `0 .. 11` is a documented range "
       "([mini-notation](https://tidalcycles.org/docs/reference/mini_notation/), "
       "[harmony & melody: `scale \"ritusen\" \"0 .. 7\"`](https://tidalcycles.org/docs/reference/harmony_melody)); `ccn`/`ccv` "
       "are documented CC controls ([Tidal MIDI](https://tidalcycles.org/docs/configuration/MIDIOSC/midi/)). Partial, and this "
       "is the honest catch: CC1 \u201cvibrato depth\u201d is an *instrument-side* response, not a curve Tidal draws \u2014 the language "
       "sends one scalar per note and the synth decides what vibrato means.")),
  dict(lang="Strudel",
    snip='n("0 .. 11").scale("C:minor").vib(6).vibmod("0.3!6 0.7 0.3!5")',
    full="partial",
    diff="2",
    diffnote="`0.7` \u2192 `0.9`: 2 chars, and the depth is a first-class per-note value",
    note=("`vib` (\u201cvibrato \u2026 in hertz\u201d, synonyms `vibrato`, `v`) and `vibmod` (\u201cvibrato depth in semitones\u201d, synonym `vmod`) "
       "both accept patterns, so per-note depth is native ([synths](https://strudel.cc/learn/synths/)); `!` replication and "
       "`0 .. 11` come from the mini-notation ([mini-notation](https://strudel.cc/learn/mini-notation/)). Partial for two "
       "reasons: the gesture is not *named* (there is no gesture value \u2014 you repeat two method calls, or wrap them in a JS "
       "function yourself), and `vib` is an effect on Strudel's own oscillator, so it does not travel over `midi()` \u2014 the MIDI "
       "path would be `ccn(1).ccv(...)` again ([MIDI I/O](https://strudel.cc/learn/input-output/)).")),
  dict(lang="Sonic Pi",
    snip='define :vib do |p,d|\n  play p,sustain: 0.4,note_slide: 0.1\n  3.times{control note: p+d; sleep 0.06; control note: p-d; sleep 0.06}\nend\n12.times{|i| vib 60+i,(i==6 ? 0.5 : 0.15); sleep 0.5}',
    full="yes",
    diff="3",
    diffnote="`0.5` \u2192 `0.25`: 3 chars in the conditional override",
    note=("The only rival that satisfies both halves: the gesture is a named, parameterized function (`define :vib do |p,d|`) "
       "whose body is a real pitch curve, and note 7 overrides one parameter inline (`i==6 ? 0.5 : 0.15`) "
       "([tutorial \u00a77.2\u20137.3 and \u00a75 `define`](https://sonic-pi.net/tutorial.html), "
       "[control](https://sunderb.me/sonic-pi-docs-test/en/reference/lang/control.html)). Cost: ~40% more characters than "
       "Strudel, internal synths only, and the gesture is imperative time (`sleep`) rather than a shape, so it cannot be "
       "stretched, reversed, or composed with another gesture.")),
  dict(lang="Alda",
    snip='vib = (quant 40)\npiano: vib o4 c8 d e f g a (quant 75) b > c d e f g',
    full="no",
    diff="\u221e",
    diffnote="the reusable value exists; the vibrato does not",
    note=("IMPOSSIBLE for vibrato. Alda *does* have named reusable values \u2014 \u201cDefine your own shorthand: quiet = (vol 25)\u201d and "
       "multi-line variables ([cheat sheet: variables](https://alda.io/cheat-sheet/)) \u2014 but the only expressive parameter to "
       "put in one is `quant`/`vol`/`panning` ([attributes](https://alda.readthedocs.io/en/latest/attributes/)). Closest "
       "achievable: a named articulation shorthand, overridden on the 7th note.")),
  dict(lang="Ziffers",
    snip='z1 "e (0..11)", release: [0.15]*6+[0.5]+[0.15]*5, synth: :piano',
    full="no",
    diff="\u221e",
    diffnote="no vibrato depth exists; the array varies a synth opt instead",
    note=("IMPOSSIBLE for vibrato. Ziffers has strong per-event opt variation \u2014 \u201cEffects can also be adjusted on the fly using "
       "ring or array\u201d, plus `tweak(:linear,\u2026)`, lambdas, and `run_each` "
       "([Effects](https://github.com/amiika/ziffers/wiki/Effects)) \u2014 and `(0..11)` ranges are documented "
       "([README](https://github.com/amiika/ziffers)), so \u201cone value differs on the 7th event\u201d is idiomatic and terse. What "
       "is missing is any expressive parameter worth varying: no bend, vibrato, pressure or CC in the notation. "
       "UNVERIFIED: the exact `[x]*6+[y]` Ruby array form is my construction; the documented forms are literal arrays and "
       "rings.")),
  dict(lang="LilyPond+articulate.ly",
    snip="v = \\startTrillSpan\nw = \\stopTrillSpan\n{ c''8\\v d''\\w e''\\v f''\\w g''\\v a''\\w b''\\prall > c''\\v d''\\w e''\\v f''\\w g''\\w }",
    full="no",
    diff="\u221e",
    diffnote="a trill span has no depth parameter to change",
    note=("IMPOSSIBLE. Named reuse is fine \u2014 identifiers can hold any music or post-event \u2014 but the vocabulary has no "
       "parameterized vibrato: trill spans and ornaments only "
       "([expressive marks as lines](https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks-as-lines)), and "
       "`\\articulate` turns ornaments into note sequences while scaling everything else's length "
       "([enhancing MIDI output](https://lilypond.org/doc/v2.25/Documentation/notation/enhancing-midi-output)). "
       "UNVERIFIED: whether `\\prall` on one note is rendered by `articulate.ly` \u2014 the manual says the supported list lives in "
       "`ly/articulate.ly` itself, not in the docs.")),
 ],
 verdict=("**Strongest bar: Strudel** on characters and diffability \u2014 `vibmod(\"0.3!6 0.7 0.3!5\")` puts a per-note vibrato depth "
      "in one pattern, and the note-7 override is 2 characters. **Strongest bar on the actual requirement: Sonic Pi**, the only "
      "rival with a *named, parameterized* gesture (`define :vib do |p,d|`) that contains a real curve. The split is the "
      "interesting result: the terse rival has no named gesture, and the rival with a named gesture is imperative and "
      "MIDI-less."),
))

# ---------------------------------------------------------------- render
out = []
out.append("# Syntax bar: six canonical composition tasks, solved in six rival languages\n")
out.append(
 "Reference corpus for **P1 \u2014 Language surface / ergonomics** in [`refs/BAR.md`](../BAR.md). Each task below is posed "
 "language-neutrally, then solved as idiomatically and concisely as the rival's *documented* syntax allows. Every function "
 "name, argument and operator is checked against primary docs; the fetched doc extracts are in "
 "[`refs/syntax/rival_docs/`](rival_docs/) with their source URLs at the top of each file.\n")
out.append(
 "**Rules used here.** `IMPOSSIBLE:` marks a task a language genuinely cannot express, followed by the closest achievable "
 "approximation and a one-sentence reason with a doc citation. `UNVERIFIED` marks anything I could not confirm in primary "
 "documentation. No syntax is invented: where a rival's docs do not show a construct, the snippet does not use it.\n")
out.append(
 "**`chars`** = non-whitespace character count of the snippet, computed by "
 "[`build_tasks.py`](build_tasks.py), never typed by hand.\n"
 "**`diff cost`** = how many characters must change, *starting from that snippet*, to alter one note's vibrato depth. "
 "`\u221e` means the language has no vibrato depth to alter, so the edit is not a character edit but a redesign. This is the "
 "P1(d) diffability measure.\n"
 "**`expresses it fully?`** = `yes` / `partial` / `no` against the task statement as written, including its harmonic or "
 "per-note-scoping requirements.\n")
out.append("Common musical ground for all tasks: **key C minor**, ii\u2013V\u2013i as `Dm7b5 \u2013 G7 \u2013 Cm9`, tempo irrelevant.\n")

# summary table
out.append("## Summary: shortest rival that expresses each task\n")
out.append("| Task | Strongest rival | chars | Rivals that cannot express it at all |")
out.append("|---|---|---|---|")
summary_rows = [
 ("T1", "Ziffers", "T1", "Ziffers", "\u2014 (all six can voice the chords; four cannot voice-lead automatically)"),
 ("T2", "Sonic Pi", "T2", "Sonic Pi", "Alda, Ziffers, LilyPond (and Tidal/Strudel cannot target the chord's third)"),
 ("T3", "Sonic Pi", "T3", "Sonic Pi", "Alda, Ziffers, LilyPond"),
 ("T4", "Strudel", "T4", "Strudel", "Alda, Ziffers, LilyPond"),
 ("T5", "Ziffers", "T5", "Ziffers", "Tidal, Strudel, Alda, LilyPond (sound only, no function)"),
 ("T6", "Strudel", "T6", "Strudel", "Alda, Ziffers, LilyPond"),
]
snip_lookup = {(t["id"], r["lang"]): r["snip"] for t in tasks for r in t["rows"]}
for tid, best, _, lang, cannot in summary_rows:
    c = nw(snip_lookup[(tid, lang)])
    title = next(t["title"] for t in tasks if t["id"] == tid)
    out.append(f"| **{tid}** {title} | {best} | {c} | {cannot} |")
out.append("")
out.append(
 "\"Strongest\" here means *strongest bar for a candidate to clear*: the rival that expresses the task most completely, with "
 "character count as the tiebreak. Three places where a shorter rival does **not** hold the bar: T1 \u2014 Strudel is 40 chars vs "
 "Ziffers' 49, but its chords are absolute symbols with no key context; T4 \u2014 Sonic Pi is 160 chars vs Strudel's 191, but its "
 "four curves are internal-synth `amp`/`cutoff`, not pressure/CC74; T6 \u2014 Strudel is 58 chars vs Sonic Pi's 157, but only "
 "Sonic Pi has a *named, parameterized* gesture as the task requires. Per-task verdicts below give the full reasoning.\n")

for t in tasks:
    out.append(f"---\n\n## {t['id']}. {t['title']}\n")
    out.append(f"**Task statement.** {t['statement']}\n")
    out.append("| language | snippet | chars | diff cost | expresses it fully? |")
    out.append("|---|---|---|---|---|")
    for r in t["rows"]:
        cell = "<br>".join("`" + ln + "`" for ln in r["snip"].split("\n"))
        cell = cell.replace("|", "\\|")
        if r["note"].startswith("IMPOSSIBLE"):
            cell = "**IMPOSSIBLE:** closest achievable — <br>" + cell
        out.append(f"| {r['lang']} | {cell} | {nw(r['snip'])} | {r['diff']} | {r['full']} |")
    out.append("")
    out.append("**Per-language notes, with sources.**\n")
    for r in t["rows"]:
        out.append(f"- **{r['lang']}** \u2014 {r['note']} *Diff cost {r['diff']}:* {r['diffnote']}.")
    out.append("")
    out.append(f"**Which rival is the bar for {t['id']}.** {t['verdict']}\n")

out.append("---\n\n## Cross-task observations a critic can lean on\n")
out.append(
 "1. **No rival can bind an expressive curve to a note.** In all six, expression is either a parallel channel-scoped stream "
 "(Tidal `midibend`/`ccv`, Strudel `midibend`/`ccv`), a scalar event field (Strudel `vibmod`, Ziffers opt arrays, Alda "
 "`quant`), a running-synth handle (Sonic Pi `control` + `_slide`), or a printed glyph (LilyPond). Tidal's own docs make the "
 "channel scoping explicit \u2014 `midibend` is a `ControlPattern` sent with `midichan` "
 "([Tidal MIDI](https://tidalcycles.org/docs/configuration/MIDIOSC/midi/)) \u2014 and Strudel's `midichan` \u201cwill use channel 1 by "
 "default\u201d ([Strudel MIDI I/O](https://strudel.cc/learn/input-output/)).")
out.append(
 "2. **No rival joins harmony to expression.** Strudel and Ziffers have the best harmony (`voicing()`; `ii+4 \u2026 <lead>`), and "
 "in both the resulting notes are anonymous, so T2's \u201cbend into the next chord's third\u201d and T4's per-voice curves cannot "
 "reference the harmony at all ([Strudel voicings](https://strudel.cc/understand/voicings/), "
 "[Ziffers Chords](https://github.com/amiika/ziffers/wiki/Chords)).")
out.append(
 "3. **The terseness bar and the expression bar are held by different languages.** Ziffers wins T1/T5 with 3\u201360 characters "
 "and cannot express T2/T3/T4/T6 at all; Sonic Pi expresses T2/T3/T6 and costs 100\u2013180 characters of unrolled imperative "
 "time. A candidate must beat Ziffers on the harmony tasks and Sonic Pi on the gesture tasks *simultaneously* \u2014 no existing "
 "rival does.")
out.append(
 "4. **Diff cost is only cheap where depth is a named scalar.** The 2-character edits (Strudel `vibmod`, Tidal `ccv` step "
 "list) are cheap precisely because the value is one number per note in a list; the moment a curve is drawn as literal "
 "breakpoints (Tidal `smooth \"8192@35 8500 \u2026\"`) the cost jumps to ~24 characters spread over six numbers, and in Alda / "
 "Ziffers / LilyPond it is unbounded because the parameter does not exist.")
out.append(
 "5. **Two rivals are the honest 'read it at a glance' bar**: Alda (`o3 d1/f/a-/>c`) and Ziffers (`w (ii+4 ivd+4 i+4 i+4)`). "
 "Both are unreadable-proof in the sense that a stranger can guess what they sound like \u2014 and both are silent on expression. "
 "That contrast is the P1(b)/P1(c) trap: prose-like readability has so far only been achieved by languages that dropped "
 "continuous expression entirely.\n")

os.makedirs(os.path.dirname("refs/syntax/tasks.md"), exist_ok=True)
open("refs/syntax/tasks.md", "w").write("\n".join(out) + "\n")

print("wrote refs/syntax/tasks.md")
for t in tasks:
    print(t["id"], {r["lang"]: nw(r["snip"]) for r in t["rows"]})
