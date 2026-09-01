# strudel_tonal
Source: https://strudel.cc/learn/tonal/
Fetched: 2026-08-30

# Tonal Functions

These functions use tonaljs to provide helpers for musical operations.

### voicing()

Turns chord symbols into voicings. You can use the following control params:

- `chord`: Note, followed by chord symbol, e.g. C Am G7 Bb^7
- `dict`: voicing dictionary to use, falls back to default dictionary
- `anchor`: the note that is used to align the chord
- `mode`: how the voicing is aligned to the anchor
  - `below`: top note <= anchor
  - `duck`: top note <= anchor, anchor excluded
  - `above`: bottom note >= anchor
  - `root`: bottom note is the lowest root of the chord >= anchor
  - `oldabove` : old (buggy) behavior of above, kept for legacy reason
  - `oldroot` : old (buggy) behavior of root, kept for legacy reason
- `offset`: whole number that shifts the voicing up or down to the next voicing
- `n`: if set, the voicing is played like a scale. Overshooting numbers will be octaved

All of the above controls are optional, except `chord`.
If you pass a pattern of strings to voicing, they will be interpreted as chords.

```
n("0 1 2 3").chord("<C Am F G>").voicing()
```

Here’s an example of how you can play chords and a bassline:

```
chord("<C^7 A7b13 Dm7 G7>*2")
.dict('ireal').layer(
x=>x.struct("[~ x]*2").voicing()
,
x=>n("0*4").set(x).mode("root:g2").voicing()
.s('sawtooth').cutoff("800:4:2")
)
```

### scale(name)

Turns numbers into notes in the scale (zero indexed) or quantizes notes to a scale.

When describing notes via numbers, note that negative numbers can be used to wrap backwards
in the scale as well as sharps or flats to produce notes outside of the scale.

Also sets scale for other scale operations, like Pattern#scaleTranspose.

A scale consists of a root note (e.g. `c4`, `c`, `f#`, `bb4`) followed by semicolon (':') and then a scale type.

The scale name must be written without spaces (because it would be interpreted as a multi-step pattern otherwise).
If your scale name includes spaces, replace them with colons.

The root note defaults to octave 3, if no octave number is given.

- scale (string): Name of scale

```
n("0 2 4 6 4 2").scale("C:major")
```

```
n("[0,7] 4 [2,7] 4")
.scale("C:<major minor>/2")
.s("piano")
```

```
n(rand.range(0,12).segment(8))
.scale("C:ritusen")
.s("piano")
```

```
n("<[0,7b] [-4# -4] [-2,7##] 4 [0,7] [-4# -4b] [-2,7###] 4b>*4")
.scale("C:<major minor>/2")
.s("piano")
```

```
note("C1*16").transpose(irand(36)).scale('Cb2 major').scaleTranspose(3)
```

```
n("[0 0] [1 2] [3 4] [5 6]").scale("C:major:blues")
```

### transpose(semitones)

Transposes all notes to the given number of semitones:

This method gets really exciting when we use it with a pattern as above.

Instead of numbers, scientific interval notation can be used as well:

### scaleTranspose(steps)

Transposes notes inside the scale by the number of steps:

```
"[-8 [2,4,6]]*2"
.scale('C4 bebop major')
.scaleTranspose("<0 -1 -2 -3 -4 -5 -6 -4>*2")
.note()
```

### rootNotes(octave = 2)

Turns chord symbols into root notes of chords in given octave.

Together with layer, struct and voicings, this can be used to create a basic backing track:

```
"<C^7 A7b13 Dm7 G7>*2".layer(
x => x.voicings('lefthand').struct("[~ x]*2").note(),
x => x.rootNotes(2).note().s('sawtooth').cutoff(800)
)
```
