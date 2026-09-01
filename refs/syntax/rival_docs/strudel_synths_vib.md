# strudel_synths_vib
Source: https://strudel.cc/learn/synths/
Fetched: 2026-08-30

# Synths

In addition to the sampling engine, strudel comes with a synthesizer to create sounds on the fly.

## Basic Waveforms

The basic waveforms are `sine`, `sawtooth`, `square` and `triangle`, which can be selected via `sound` (or `s`):

```
note("c2 <eb2 <g2 g1>>".fast(2))
.sound("<sawtooth square triangle sine>")
._scope()
```

If you don’t set a `sound` but a `note` the default value for `sound` is `triangle`!

## Noise

You can also use noise as a source by setting the waveform to: `white`, `pink` or `brown`. These are different
flavours of noise, here written from hard to soft.

```
sound("<white pink brown>")._scope()
```

Here’s a more musical example of how to use noise for hihats:

```
sound("bd*2,<white pink brown>*8")
.decay(.04).sustain(0)._scope()
```

Some amount of pink noise can also be added to any oscillator by using the `noise` paremeter:

```
note("c3").noise("<0.1 0.25 0.5>")._scope()
```

You can also use the `crackle` type to play some subtle noise crackles. You can control noise amount by using the `density` parameter:

```
s("crackle*4").density("<0.01 0.04 0.2 0.5>".slow(2))._scope()
```

### Additive Synthesis

Periodic waveforms are composed of several harmonics above a fundamental frequency, lying at integer multiples. These overtones combine to give a sound its unique timbral quality.

For the basic waveforms, we offer you control over these harmonics with the `partials` and `phases` functions.

#### Partials

`partials` refers to the magnitude of each harmonic relative to the fundamental frequency. They can thus be used to spectrally filter these waveforms and tame some of their harshness:

```
note("c2 <eb2 <g2 g1>>".fast(2))
.sound("sawtooth")
.partials([1, 1, "<1 0>", "<1 0>", "<1 0>", "<1 0>", "<1 0>"])
._scope()
```

`partials` can also be used to construct *new* waveforms not present in our basic set with the ‘user’ sound source:

```
note("c2 <eb2 <g2 g1>>".fast(2))
.sound("user")
.partials([1, 0, 0.3, 0, 0.1, 0, 0, 0.3])
._scope()
```

We may algorithmically construct lists of magnitudes with Javascript code like:

```
const numHarmonics = 22;
note("c2 <eb2 <g2 g1>>".fast(2))
.sound("saw")
.partials(new Array(numHarmonics).fill(1))
._scope()
```

which acts as a spectral filter. Or:

```
note("c2 <eb2 <g2 g1>>").fast(2)
.sound("user")
.partials(new Array(50).fill(0)
.map((_, idx) => ((-1) ** (idx + 1)) / (idx + 1))
)
._scope()
```

which recovers a familiar waveform.

`partials` is also compatible with pattern functions designed to produce lists, like `randL` or `binaryL`:

```
note("c2 <eb2 <g2 g1>>").fast(2)
.sound("user")
.partials(randL(10))
._scope()
```

and with lists *of* patterns:

```
note("c2 <eb2 <g2 g1>>".fast(4))
.sound("user")
.partials([1, 0, "0 1", "0 1 0.3", rand])
._scope()
```

Note that the first value in the `partials` array controls the magnitude of the fundamental harmonic rather than the DC offset, which is fixed at 0.

#### Phases

Earlier, we mentioned that periodic waveforms can be broken into a set of harmonics above a fundamental frequency. Each harmonic has two defining properties: its magnitude (how loud it is) and its phase, which determines where in its cycle that sine wave starts when the waveform is built.

These phases too can be declared in Strudel and can give your sounds interesting depth.

```
s("saw").seg(16).n(irand(12)).scale("F1:minor")
.penv(48).panchor(0).pdec(0.05)
.delay(0.25).room(0.25)
.compressor(-20).vib(0.3)
.partials(randL(200))
.phases(randL(200))
```

## Vibrato

### vib
Synonyms: `vibrato, v`

Applies a vibrato to the frequency of the oscillator.

- frequency (number|Pattern): of the vibrato in hertz

```
note("a e")
.vib("<.5 1 2 4 8 16>")
._scope()
```

```
// change the modulation depth with ":"
note("a e")
.vib("<.5 1 2 4 8 16>:12")
._scope()
```

### vibmod
Synonyms: `vmod`

Sets the vibrato depth in semitones. Only has an effect if `vibrato` | `vib` | `v` is is also set

- depth (number|Pattern): of vibrato (in semitones)

```
note("a e").vib(4)
.vibmod("<.25 .5 1 2 12>")
._scope()
```

```
// change the vibrato frequency with ":"
note("a e")
.vibmod("<.25 .5 1 2 12>:8")
._scope()
```

## FM Synthesis

FM Synthesis is a technique that changes the frequency of a basic waveform rapidly to alter the timbre.

You can use fm with any of the above waveforms, although the below examples all use the default triangle wave.

### fm

### fmh

Sets the Frequency Modulation Harmonicity Ratio.
Controls the timbre of the sound.
Whole numbers and simple ratios sound more natural,
while decimal numbers and complex ratios sound metallic.

A number may be added afterwards to control the harmonicity of
any of the 8 individual FMs (e.g. `fmh2`)

- harmonicity (number|Pattern):

```
note("c e g b g e")
.fm(4)
.fmh("<1 2 1.5 1.61>")
._scope()
```

### fmattack
Synonyms: `fmatt`

Attack time for the FM envelope: time it takes to reach maximum modulation

A number may be added afterwards to control the attack of the envelope of
any of the 8 individual FMs (e.g. `fmatt5`)

- time (number|Pattern): attack time

```
note("c e g b g e")
.fm(4)
.fmattack("<0 .05 .1 .2>")
._scope()
```

### fmdecay
Synonyms: `fmdec`

Decay time for the FM envelope: seconds until the sustain level is reached after the attack phase.

A number may be added afterwards to control the decay of the envelope of
any of the 8 individual FMs (e.g. `fmdec6`)

- time (number|Pattern): decay time

```
note("c e g b g e")
.fm(4)
.fmdecay("<.01 .05 .1 .2>")
.fmsustain(.4)
._scope()
```

### fmsustain
Synonyms: `fmsus`

Sustain level for the FM envelope: how much modulation is applied after the decay phase

A number may be added afterwards to control the sustain of the envelope of
any of the 8 individual FMs (e.g. `fmsus7`)

- level (number|Pattern): sustain level

```
note("c e g b g e")
.fm(4)
.fmdecay(.1)
.fmsustain("<1 .75 .5 0>")
._scope()
```

### fmenv
Synonyms: `fme`

Ramp type of fm envelope. Exp might be a bit broken..

A number may be added afterwards to control the envelope of
any of the 8 individual FMs (e.g. `fmenv4`)

- type (number|Pattern): lin | exp

```
note("c e g b g e")
.fm(4)
.fmdecay(.2)
.fmsustain(0)
.fmenv("<exp lin>")
._scope()
```

## Wavetable Synthesis

Strudel can also use the sampler to load custom waveforms as a replacement of the default waveforms used by WebAudio for the base synth. A default set of more than 1000 wavetables is accessible by default (coming from the AKWF set). You can also import/use your own. A wavetable is a one-cycle waveform, which is then repeated to create a sound at the desired frequency. It is a classic but very effective synthesis technique.

Any sample preceded by the `wt_` prefix will be loaded as a wavetable. This means that the `loop` argument will be set to `1` by default. You can scan over the wavetable by using `loopBegin` and `loopEnd` as well.

```
samples('bubo:waveforms');
note("<[g3,b3,e4]!2 [a3,c3,e4] [b3,d3,f#4]>")
.n("<1 2 3 4 5 6 7 8 9 10>/2").room(0.5).size(0.9)
.s('wt_flute').velocity(0.25).often(n => n.ply(2))
.release(0.125).decay("<0.1 0.25 0.3 0.4>").sustain(0)
.cutoff(2000).cutoff("<1000 2000 4000>").fast(4)
._scope()

```

## ZZFX

The “Zuper Zmall Zound Zynth” ZZFX is also integrated in strudel. Developed by Frank Force, it is a synth and FX engine originally intended to be used for size coding games.

It has 20 parameters in total, here is a snippet that uses all:

```
note("c2 eb2 f2 g2") // also supports freq
.s("{z_sawtooth z_tan z_noise z_sine z_square}%4")
.zrand(0) // randomization
// zzfx envelope
.attack(0.001)
.decay(0.1)
.sustain(.8)
.release(.1)
// special zzfx params
.curve(1) // waveshape 1-3
.slide(0) // +/- pitch slide
.deltaSlide(0) // +/- pitch slide (?)
.noise(0) // make it dirty
.zmod(0) // fm speed
.zcrush(0) // bit crush 0 - 1
.zdelay(0) // simple delay
.pitchJump(0) // +/- pitch change after pitchJumpTime
.pitchJumpTime(0) // >0 time after pitchJump is applied
.lfo(0) // >0 resets slide + pitchJump + sets tremolo speed
.tremolo(0.5) // 0-1 lfo volume modulation amount
//.duration(.2) // overwrite strudel event duration
//.gain(1) // change volume
._scope() // vizualise waveform (not zzfx related)

```

Note that you can also combine zzfx with all the other audio fx (next chapter).

Next up: Audio Effects…
