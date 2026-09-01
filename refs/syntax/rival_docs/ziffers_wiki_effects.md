# ziffers_wiki_effects
Source: https://github.com/amiika/ziffers/wiki/Effects
Fetched: 2026-08-30

amiika / **
ziffers ** Public

# Effects

Jump to bottom

Miika Alonen edited this page Dec 15, 2022 · 13 revisions

# Fading volume

Volume is the most obvious thing you might want to adjust. To make it simple there is a **fade** parameter that takes in a range, for example:

```
zplay "q 0 1 2 3 4 5 6 7", fade: 1..0
zplay "q 0 1 2 3 4 5 6 7", fade: 0.5..2

```

To fade in a loop over longer period of time use **fade_in** or **fade_out** to define how many loop rounds the fading takes. **fade** can be optionally used to define starting and ending point.

```
z1 "q 0 2 1 3 5 4 6", fade_in: 2 # Loop fading in 2 rounds
z2 "q 6 4 3 2 1 0 -1", fade_out: 2, fade: 2.0..0.25 # Loop fading out in 2 rounds. Starting from 2.0 to 0.25

```

You can also use **fader** parameter to define type of fader (linear, cubic etc.). For different types of faders look at **tweak** method below. See **tweak** for different faders.

```
z1 "q 0 2 1 3 5 4 6", fade: 0..1, fade_in: 3, fader: :expo # Loop fading in 2 rounds

```

# Tweak

**tweak** creates array that can be used in fading etc.

Available easing / fading functions:

:linear, :sine, :quad, :cubic, :quart, :quint, :expo, :circ, :back, :bounce

Some also include in and out function like `:in_sine, :out_sine`. For visual aid see easings.net.

Examples:

```
quad = (tweak :quad,-1,1,10).ring.mirror
expo = (tweak :expo,0,10,30).ring.mirror
sine = (tweak :cubic,0,30,100).ring.mirror
quint = (tweak :quint,0,20,40).ring.mirror

live_loop :beat do
  with_fx :pan, pan: quad.tick do
    play 60+expo.look
    play 30+sine.look
    play 70+quint.look, amp: 0.1
    sleep 0.25
  end
end

```

# Adjusting Parameters

Parameters can be adjusted by defining range manually or using **tweak**. Rings can be used to continuously adjust some parameter like **pan**.

Examples:

```
# Adjusting
z1 "q 0 1 2 3 4 5 6 7", pan: tweak(:quint,-1,1,7).ring.mirror
z1 "q 0 1 2 3 4 5 6 7", release: tweak(:quint,0.1,0.5,7).ring.mirror, synth: :piano

```

Adjust can be used to adjust any parameter:

```
z1 "q 0 1 2 3 4 5 6 7", pan: tweak(:cubic,-1,1,10).ring
z2 "q 0 1 2 3 4 5 6 7", amp: tweak(:expo,0,2,10).ring.mirror

```

## Adjusting with lambdas

Alternatively use labdas to change any parameter.

Examples:

```
z1 "q 0 1 3 2 4 5 6 7 8 9", release: ->(){rrand_i(0,1)}
z2 "q 0 1 3 2 4 5 6 7 8 9", pan: ->(i){i%2==0 ? 0 : 1}
z3 "q 0 1 3 2 4 5 6 7 8 9", retrograde: ->(i){ i%3==0} #

```

## Adjusting samples

Sample options can also be adjusted separately:

```
m = {
  K: { sample: :drum_heavy_kick, amp: tweak(:linear,0,1,20), pan: [0,1,-1].ring},
  S: { sample: :drum_snare_soft, amp: [0.25,0.5,1.0,1.5,1.0,0.5].ring },
  H: { sample: :drum_cymbal_closed, amp: tweak(:sine,0,1,20), pan: tweak(:sine,-1,1,20).ring.mirror },
  O: { sample: :drum_cymbal_open, amp: ->(){rrand 0.5, 2.0}}
}

z1 "[:h [KH H] [SH H] [KH KH] <[SH H] [SH K]>:]", use: m

```

Note that use of **adjust** will override any sample spesific options.

# Running with effects

Ziffers methods like **zplay**, **zloop**, **z1** etc. can be run with Sonic Pi FX effects (and some other blocks) by defining **run** array. Benefit of using **run** compared to normal block is that effects with **run** can be changed during the the loop.

Run works with fx effects and following blocks. See parameters from Sonic Pi:s documentation:

- with_fx
- with_bpm
- density
- with_swing
- with_cent_tuning
- with_octave

Example:

```
zplay "|h 1 2 3 4 | 4 3 2 1|", run: [
  {with_bpm: 120},
  {with_fx: :echo},
  {with_fx: :bitcrusher, bits: 5 }
]

```

Effects can also be applied to samples using **run**:

```
z1 "B K (B B) K",
  run: [{with_bpm: 120}],
  use: {
    B: :bd_fat,
    K: { sample: :drum_snare_soft, run: [{with_fx: :echo}] }
  }

```

Or all of the samples:

```
z1 "B K (B B) K",
  run: [{with_bpm: 120}],
use: {
  B: :bd_fat,
  K: { sample: :drum_snare_soft },
  run: [{with_fx: :echo}]
}

```

## Adjusting Effects

Effects can also be adjusted on the fly using ring or array. Rings can be used to create continuous change and arrays as fade in or fade out. Normally using **run** the adjusting happens at the start of the loop, alternatively **run_each** (or apply&run) will adjust the parameters for each degree or sample.

```
# Phase parameter is adjusted at the start of the loop
z1 "q 1 3 2 4", run: [
  {with_fx: :ixi_techno, phase: tweak(:sine, 0.01,1.0,10).ring.mirror}
]

# Phase parameter is adjusted for each degree in the melody
z2 "e 0 1 2 3 4 5 6 7 8 7 6 5 4 3 2 1 0", run_each: [
  {with_fx: :flanger, phase: tweak(:sine, 0.05,1.0,10).ring.mirror}
]

```

## Cycle options and transformations

Options and transformations can be applied only for certain runs of the loop. Use **cycle**, **on** and **range** to define which cycles the given options or transformations are applied:

```
# This will do the retrograde for every other cycle of the loop
z1 "q 0 2 1 3", cycle: { at: 2, retrograde: true }

# This set the loop length to 6 and do the inverse from 4 to 6.
z2 "q 0 2 1 3", cycle: { at: 6, range: (4..6), invert: true }

```

Parameters support lambdas which allows randomized values etc. for example:

```
z1 "q 0 1 2 3 4", cycle: { at: 2, pan:->(){ rrand_i(-1,1) } }

```

Multiple transformations can also be applied in an array:

```
z1 "q 0 1 2", cycle: [
  { at: 3, invert: true },
  { at: 4, retrograde: true }
]

```

# Pitch detuning

Detuning can be used to alter the tuning of the synths with hz offset. This can be used to produce dissonance or for example binaural frequencies (really annoying squeals):

```
z1 "P1 q1234", pitch_detune: 10
z2 "P-1 q1234"

```

------------------------------------ See more stuff from the menu --------------------------------------->

- Home
- Chords
- Combinatorics
- Composition
- Contributions
- Effects

  - Fading volume
  - Tweak
  - Adjusting Parameters
  - Adjusting with lambdas
  - Adjusting samples
  - Running with effects
  - Adjusting Effects
  - Cycle options and transformations
  - Pitch detuning
- Enumerables
- Euclidean
- Generative
- Install
- Issues
- Melody
- Play
- Rhythm
- Rules
- Samples
- Supportive
- Transformations
-

# Start

Info

Installation

# Notation

Basic syntax

Chords

Rhythm

Generative syntax

# Methods

Play

Samples

Effects

Supportive

## Generative methods

Rules

Transformations

Combinatorics

Enumberables

# Help

Issues

Contributions

### Clone this wiki locally
