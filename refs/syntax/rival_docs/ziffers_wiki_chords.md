# ziffers_wiki_chords
Source: https://github.com/amiika/ziffers/wiki/Chords
Fetched: 2026-08-30

amiika / **
ziffers ** Public

# Chords

Jump to bottom

Miika Alonen edited this page Dec 4, 2022 · 20 revisions

# Chords

Chords can be played using groups of numbers "024 357" or using roman numerals: i ii iii iv v vi vii

```
zplay "[: i vi v :]" # Play chords as a sequence using default chord length of 1

zplay "q [: iv 1 2 3 iii 2 3 4 ii 4 3 2 i 1 2 3 :]", chord_duration: 0 # Play chord simultaniously with the melody using **chord_duration**

```

In major scale (or any other diatonic) roman numerals would correspond to these pitch classes:

```
i = 024
ii = 135
iii = 246
iv = 357 or 35^0
v = 468 or 46^1
vi = 579 or 5^0^2
vii = 68{10} or 6^1^3

```

Chord key is assigned with **key** parameter (defaults to major). Alternatively **chord_key** can be used to change the key for the chords.

Chords can be customized by taking more notes from the scale or by using chord names. Works for major and minor scales only.

Examples using the scale:

```
zplay "i" # Plays trichord
zplay "i+1" # Plays root
zplay "i+4" # Plays 7th chord
zplay "i+5" # Plays 9th chord
zplay "i+24" # Plays chord in multiple octaves

```

## Chord names

Chord names are nice shorthands for similar group of notes. Define chord name using using **^** with the name or by using **chord_name** parameter. Chord names work for minor, major and chromatic scales. Other than that who knows? Not me. Some might work and others might sound a bit funny.

Examples using the chord names:

```
zplay "i vi^dim"
zplay "i vi", chord_name: :dim # Play all chords as diminished
zplay "i vi^m11+"
zplay "i^7*2" # Plays chord in 2 octaves
zplay "i^maj*9" # Plays chord in 9 octaves (Current max)

```

Chords can also be inverted using % char, for example %1 to invert all following chords up by one:

```
zplay "vii%-2 iii%-1 vi%-1 ii v i%1 iv%2", chord_duration: 0.25, key: :d, scale: :minor

```

List of all chord names (Pitch classes in chromatic scale):

```
^major = 047 # ^M
^min = 037 # ^minor or ^m
^major7 = 04711 # ^maj7 or ^M7
^7 = 047T # ^dom7
^m7 = 037{10} # ^minor7
^aug = 048 # ^augmented or ^a
^dim = 036 # ^diminished or ^i
^dim7 = 0369 # ^diminished7 or ^i7
^m7-5 = 036{10} # ^m7b5 or ^halfdim or ^halfdiminished
^1 = 0
^5 = 07
^+5 = 048
^m+5 = 038
^sus2 = 027
^sus4 = 057
^6 = 0479
^m6 = 0379
^7sus2 = 027{10}
^7sus4 = 057{10}
^7-5 = 046{10}
^7+5 = 048{10}
^m7+5 = 038{10}
^9 = 047{10}{14}
^m9 = 037{10}{14}
^m7+9 = 037{10}{14}
^maj9 = 04711{14}
^9sus4 = 057{10}{14}
^6*9 = 0479{14}
^m6*9 = 0379{14}
^7-9 = 047{10}{13}
^m7-9 = 037{10}{13}
^7-10 = 047{10}{15}
^7-11 = 047{10}{16}
^7-13 = 047{10}{20}
^9+5 = 0{10}{13}
^m9+5 = 0{10}{14}
^7+5-9 = 048{10}{13}
^m7+5-9 = 038{10}{13}
^11 = 047{10}{14}{17}
^m11 = 037{10}{14}{17}
^maj11 = 04711{14}{17}
^11+ = 047{10}{14}{18}
^m11+ = 037{10}{14}{18}
^13 = 047{10}{14}{17}{21}
^m13 = 037{10}{14}{17}{21}
^add2 = 0247
^add4 = 0457
^add9 = 047{14}
^add11 = 047{17}
^add13 = 047{21}
^madd2 = 0237
^madd4 = 0357
^madd9 = 037{14}
^madd11 = 037{17}
^madd13 = 037{21}

# Some chords added to Sonic Pi via Monkeypatching

^mM7 = 037{11} # https://en.wikipedia.org/wiki/Minor_major_seventh_chord
^maj7+5 = 048{11} # https://en.wikipedia.org/wiki/Augmented_major_seventh_chord
^6+5 = 0489
^maj7sus2 = 046
^maj7sus4 = 026
^7-5-3 = 036{10} # Missing altered chords: https://en.wikipedia.org/wiki/Altered_chord
^7+5+9 = 048{10}{14}
^7-5-9 = 046{10}{13}
^7-5+9 = 046{10}{14}

```

## Borrowed chords / Modal interchange

Borrowed chords can be easily created using shorthand characters for modes (a-g). Combine chars with roman numerals, for example: iib (locrian), iiig (mixolydian).

Suitable chord types for modal interchange can be found from the following table (or from the internet):

|Char|Type|Mode|i|ii|iii|iv|v|vi|vii|
|--|--|--|--|--|--|--|--|--|--|
|a|Minor|:aeolian|i|II|iii|#iv¤|V|vi|vii|
|b|Minor|:locrian|i¤|bII|biii|iv|bV|bVI|bvii|
|c|Major|:ionian|I|ii|iii|IV|V|vi|vii¤|
|d|Minor|:dorian|i|ii|bIII|IV|v|vi¤|bVII|
|e|Minor|:phrygian|i|bII|bIII|iv|v¤|bVI|bvii|
|f|Major|:lydian|I|II|iii|#iv¤|V|vi|vii|
|g|Major|:mixolydian|I|ii|iii¤|IV|v|vi|bVII|

Capital letters (meaning minor and major chords) etc. in the table are for info only. In ziffers, roman numerals are always in lower case, since chords are construcred from the given scale. Char column tells the character that is put after the roman numeral, like: "ia" or "ivg".

Here are some common chord progressions with modal interchange:

```
z1 "q i iiia iv iv", synth: :pluck, stretch: 4
z1 "q i viia via i", synth: :pluck, stretch: 4
z1 "q i viib vib viig", synth: :pluck, stretch: 4

```

## Voice Leading

In voice leading chords are rearranged in a way that each voice moves as little as possible when moving from chord to another. Voice leading uses taxi cab metric algorithm described in The Geometry of Music by Dmitri Tymoczko.

```
zplay "(i v vi) (i v vi)<lead>"
zplay "(035 136 432) (035 136 432)<lead>"

```

## Arpeggios

Arpeggios can be generated using the list syntax, where first list are the chords and the second list the indexes. See Generative-page for more information about the list notation.

Examples:

```
zplay "(i ii iii iv v vi vii)@(q 0 1 2 1)"

zplay "([: i^7 :3][: iv^dim7%-1 :3])@(q 0 1 e 2 1 0 1)", key: :d4, scale: :mixolydian

zplay "([: i^7 :4][: iv%-1 :4])@(q 0 123)"

zplay "([: i^7 :4] [: iv^7 :2] [: i^7 :2] v^7 iv^7 i^7 i^7)@(q 0 1 2 b3 3 b3 2 1)"

zplay "((i ii iv)@(q 0 1 2 1))+(0 1 -1)" # Can be combined with other list transformations

```

FYI! Deprecated arpeggio notation (Might not work in the future):

```
zplay "@(q 1 2 3 1) i ii iii iv v vi vii"

zplay "@(q 0 1 e 2 1 0 1) [: i^7 :3][: iv^dim7%-1 :3]", key: :d4, scale: :mixolydian

zplay "@(q 0 123) [: i^7 :4][: iv%-1 :4]"

```

### Horizontal arpeggio

Horizontal arpeggios work in a similar way, but indexes work horizontally. This allows you to generate new melody out of existing one by manipulating the indexes.

Examples:

```
zplay "(0 4 2 5 3 2)#(q 0 3 021)" # Selects 0 5 024
zplay "(0 023)#(0 1 01 11)" # If chords are selected those are combined
z1 "(0..7)#(q (0,4) ? 024)" # Indexes can be selected randomly

```

------------------------------------ See more stuff from the menu --------------------------------------->

- Home
- Chords

  - Chords
  - Chord names
  - Borrowed chords / Modal interchange
  - Voice Leading
  - Arpeggios
  - Horizontal arpeggio
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
