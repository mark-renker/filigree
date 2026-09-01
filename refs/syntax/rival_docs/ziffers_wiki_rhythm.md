# ziffers_wiki_rhythm
Source: https://github.com/amiika/ziffers/wiki/Rhythm
Fetched: 2026-08-30

amiika / **
ziffers ** Public

# Rhythm

Jump to bottom

Miika Alonen edited this page Nov 10, 2022 · 14 revisions

# Rhythm

Rhythm can be defined in different ways:

- Using note length characters, decimal notation or list notation to indicate the rhythm within the melody
- Defining rhythmic motives that transforms or overwrites the rhythm for the melody

## Rhythmic motive

Rhythmic motives can be modified separately from the melody to find a pleasant rhythm. Definining rhrythmic motive will overwrite all note lengths defined within the melody:

```
zplay "0 1 2 3", rhythm: [0.25,0.25,0.5]
sleep 1
zplay "0 1 2 3", rhythm: (ring 0.25,0.25,0.5)

```

Rhythmic motives can also be defined and changed in loops:

```
z1 "0 1 2 3", rhythm: "qeeqee"*3+"eeqh"*4
z2 "(1..8)~", key: :c3, rhythm: "eeq"

```

By default rhythmic motives are phased in loop cycles. Use **phase_rhythm: false** to not phase the rhythms.

```
# Test separately
z1 "2 0 4", rhythm: "qee" # Phased
z1 "2 0 4", rhythm: "qee", phase_rhythm: false # Not phased

```

## Note length mapping

Custom lengths can be assigned to each note using lengths parameter. This can be useful in gerative melodies:

```
zplay "1 2 3", rhythm: {0=>"h",1=>"q",2=>"h",3=>"q",4=>"e",5=>"e",6=>"q",7=>"q",8=>"e"}

```

## Integer mapping

Rhythm can be an integer, which is by default mapped to default lengths: [0.125, 0.25, 0.375, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0]

```
# Test separately
z1 "2 0 4", rhythm: 12345 # Integers are mapped to default lengths
z1 "2 0 4", rhythm: "01234" # If you want to start with zero

```

## Binary beats

Binary arrays, string or hex are transformed to binary representation where consecutive one's are counted together as interval arrays and divided by the total length of the sequence.

```
zplay "1 2 3", rhythm: {binary: 0x0F }
zplay "0 1 2 3 4 5", rhythm: {binary: 0x1234 }
zplay "0 1 2 3 4 5", rhythm: {binary: "foobar", ratio: 2.0 }
zplay "0 1 2 3 4 5", rhythm: {binary: spread(4,5) }
zplay "0 1 2 3 4 5", rhythm: {binary: [1,0,0,0,1,0,1,0,0], ratio: 3.0}

```

## Schillinger resultants

Schillinger rhythm is produced by the interference of two (or more) synchronized monomial periodicities. A periodicity consisting of greater value is the **major** generator and the the smaller **minor** generator:

```
zplay "0 1 2 3 4 5", rhythm: {major: 7, minor: 3}

```

Secondary counter can be added using **secondary: true**. This affects the way the interfernces are evaluated and makes the rhythm sequences longer.

```
zplay "0 1 2 3 4 5", rhythm: {major: 7, minor: 3, secondary: true}

```

Adding third generator is another way making the rhythmic patterns longer and more interesting:

```
zplay "(3 5 2 5)+(0 4 2 1)", rhythm: {major: 7, minor: 3, third: 5}

```

Using third generator and **complementary: true** minor and major generators are multiplied together, which makes the overall rhythm sequence shorter and the actual durations longer:

```
zplay "(3 5 2 5)+(0 4 2 1)", rhythm: {major: 7, minor: 3, third: 5, complementary: true}

```

These generators are described in the Schillinger's System of Composition Chapter 2.

## Adjusting note lengths

By default schillinger rhythm and binary beats are calculated from the interval array of the binary (for example [1,0,0,1,0]->[3,2]) by dividing using the total length and the ratio (default 1.0).
Default durations for intervals are (0-9) = e q q. h h. w w. d d. l or 0.125, 0.25, 0.375, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0.

Alternative way to map binary to durations is to define a mapping from the intervals to some durations using **durs**. For durations not to phase to the beginning the length of the array must be 10:

```
# Test separately
z1 "0 1 2 3", rhythm: spread(19,32), durs: [0.1,0.2,0.3] # Shorted arrays will phase
z1 "0 1 2 3", rhythm: spread(19,32), durs: [0.1,0.2,0.3], phase_rhythm: false # Unwanted phasing can be avoided
z1 "0 1 2 3", rhythm: {binary: ->(){rrand_i(100,600)}, durs: [0.01, 0.1, 0.125, 0.25, 0.45, 0.5, 0.75, 1.0]} # Can be indluded in the rhythm object
z1 "(0 5 3 1 3 6 8 3 1 3)+(1,4)", rhythm: {major: 9, minor: 4, durs: [0.05, 0.1, 0.125, 0.133333, 0.25, 0.375, 0.5, 0.75, 1.0]}

```

## Euclidean rhythm

Euclidean rhythms can be used to create rhythms or complex rhythmic variation to melodies. Ziffer's euclidean method is similar to Sonic Pi's spread method, but it extends it's features in many ways.

Default syntax: (onbeat)<2,4>(offbeat) where (offbeat) is optional (defaults to "r").

Reversed syntax: (onbeat)>2,4<(offbeat). Evaluates random numbers and cycles once per loop. By default randomization and nested cycles are evaluated multiple times within a loop.

```
# Basic syntax spreads everything inside a () set
z1 "q (X)<2,4>", X: :bd_haus

# Multiple values create alternating patterns
z1 "q (X S)<2,4>", X: :bd_haus, S: :drum_snare_soft

# Changing direction inputs the whole list for each slot
z1 "q (X S)>2,4>", X: :bd_haus, S: :drum_snare_soft

# Third parameter rotates the euclid circle
z1 "q (X S)<3,6,1>", X: :bd_haus, S: :drum_snare_soft

# Lists can also be defined for offbeat points using ()<x,y>() syntax
z1 "q (X S)<5,8>(H Z)", X: :bd_haus, S: :drum_snare_soft, H: :drum_cymbal_closed,

# Alternating pattern can also consist multiple notes
z1 "((e 4 2) (e 0 ?))<6,8>(q6 q(5,7))" # Patterns (e 4 2) (e 0 ?) are alternating in on set and patterns q6 q(5,7) in offset

# And the whole thing can also be used with the lists / melodies.
z1 "((e 1 3) (e 5 2))<5,7>((6 8))"

# By default euclidean syntax randomizes values multiple times in a loop. Randomization can be done once a loop by reversing notation to ()>x,y<(). Test following separately to see the difference:
z1 "((e (1,2) (3,6)) (e 5 2))<5,7>(q 6 (3,5))" # Default randomization
z1 "((e (1,2) (3,6)) (e 5 2))>5,7<(q 6 (3,5))" # Randomize only for each loop

# Or combination of samples and melodies. If note duration is changed within the pattern following rest duration must also be defined
z1 "q (X (e 3 ? q))<5,7>", X: :bd_haus, S: :drum_snare_soft

# Euclidean cycles and rotation can also be randomized:
z1 "q (0 2)<[2,3],[4,5],[0,1,2]>(4 3)"
z2 "q (0 2)<(1,4),(4,5)>(4 3)"

# Euclidean cycles also support inner cycles. By default cycles are evaluated multiple times in a loop. Reversing notation evaluates cycles for each loop.

z1 "(<0 1 2> <3 2>)<2,4>(1 2)" # First run: 0 1 3 2
z1 "(<0 1 2> <3 2>)<2,4<(<1 2>)" # First run: 0 1 3 1
z1 "(<0 1 2> <3 2>)>4,8>(1 2)" # First run: 0 1 3 2 0 1 3 2
z1 "(<0 1 2> <3 2>)<4,8>(1 2)" # First run: 0 1 3 2 1 1 2 2

# Euclidean cycles can also be cycled or Nested

z1 "<(1 2 3)<1,5>(4 (1,5) 6) (1 <2 3> 2)<2,5>(<4 5 6>)>" # Cycles euclidean cycles
z1 "(1 2 (1 2)<1,5>(4 (1,5)))<1,5>(4 (1 2 )<1,5>(4 (1,5)) (1,5))" # Nested euclidean cycles

```

See list of all possible (up to 32) euclidean rhythms for some ideas.

# Rhythm with MIDI

## Note length charactes with a midi flag

Integers can be parsed as midi notes using **midi** flag and sent to virtual synths to play drum lines, for example:

```
# 12 kick - 90 hihat
zplay "[: q 12 90 [12 12] 90 :4]", midi: true, port: "loopmidi", channel: 1

```

Same rhythm can also be defined as more re-usable rhythmic pattern. It is easier to change the midi mapping using capital letters to indicate the kicks and hits in the rhythm:

```
# 12 kick - 90 hihat
zplay "[: q K H [K K] H :4]", K: 12, H: 90, port: "loopmidi", channel: 1

```

To define your own notation for drum sets, you can use simple hash to map midi notes to capital letters, for example General Midi Drum mapping:

```
gm1 = {
  # GM1 Drum MAP: https://computermusicresource.com/GM.Percussion.KeyMap.html
  A: 35, # Acoustic Bass Drum
  B: 36, # Bass Drum
  C: 42, # Closed hi-hat
  D: 37, # Side stick
  E: 53, # Ride bell
  F: 55, # Splash Cymbal
  G: 57, # Crash Cymbal 2
  H: 39, # Hand clap
  I: 48, # Hi Mid Tom
  J: 58, # Vibraslap
  K: 75, # Claves
  L: 67, # High Agogo
  M: 68, # Low Agogo
  N: 70, # Maracas
  O: 46, # Open Hi-hat
  P: 44, # Pedal Hi-hat
  Q: 81, # Open Cuica
  R: 59, # Ride cymbal
  S: 38, # Acoustic snare
  T: 41, # Low Floor Tom
  U: 47, # Low Mid Tom
  W: 76, # High Wood Block
  X: 35, # Acoustic Bass Drum
  Y: 43, # High Floor Tom
  Z: 77 # Low Wood Block
}

z1 "(BC)<1,4>(C S)", use: gm1, c: 10, p: "microsoft_gs_wavetable_synth_0"

```

Drum mapping can also contain more information, like separate channel, port or additional midi CC control messages:

```
M = {
  X: {port: "port_1", channel: 3, note: 40},
  H: {port: "port_2", channel: 2, note: 30, cc: 30, value: 50}
}

z1 "h X [h H,q X X,[q X e H H,q H X]]", use: M

```

To send different notes to multiple channels fast, you can also use **multi** parameter as follows:

```
z1 "q 1 [2 3]", multi: true # Interpret numbers as channels. Notes default to 60, if note value doesnt matter.
z1 "q 1 [2 3]", multi: [60,70,80] # Notes map to array index
z1 "q 1 [2 3]", multi: {1=>65,2=>70} # Notes hash mapping

```

------------------------------------ See more stuff from the menu --------------------------------------->

- Home
- Chords
- Combinatorics
- Composition
- Contributions
- Effects
- Enumerables
- Euclidean
- Generative
- Install
- Issues
- Melody
- Play
- Rhythm

  - Rhythm
  - Rhythmic motive
  - Note length mapping
  - Integer mapping
  - Binary beats
  - Schillinger resultants
  - Adjusting note lengths
  - Euclidean rhythm
  - Rhythm with MIDI
  - Note length charactes with a midi flag
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
