# lilypond_marks_lines
Source: https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks-as-lines
Fetched: 2026-08-30

|[ << Musical notation ]|[Top][Contents][Index]|[ Specialist notation >> ]|
|--|--|--|
|[ < Falls and doits ]|[ Up : Expressive marks ]|[ Glissando > ]|

### 1.3.3 Expressive marks as lines

This section explains how to create various expressive marks that
follow a linear path: glissandos, arpeggios, and trills.

|Glissando| | |
|--|--|--|
|Arpeggio| | |
|Trills| | |
|[ << Musical notation ]|[Top][Contents][Index]|[ Specialist notation >> ]|
|--|--|--|
|[ < Expressive marks as lines ]|[ Up : Expressive marks as lines ]|[ Arpeggio > ]|

#### Glissando

A glissando is created by appending `\glissando`
to a note:

> ```
> \relative {
>   g'2\glissando g'
>   c2\glissando c,
>   \afterGrace f,1\glissando f'16
> }
> ```

A glissando can connect notes across staves:

> ```
> \new PianoStaff <<
>   \new Staff = "right" {
>     e'''2\glissando
>     \change Staff = "left"
>     a,,4\glissando
>     \change Staff = "right"
>     b''8 r |
>   }
>   \new Staff = "left" {
>     \clef bass
>     s1
>   }
> >>
> ```

A glissando can connect notes in chords. If anything other than a
direct one-to-one pairing of the notes in the two chords is required,
the connections between the notes are defined by setting
`\glissandoMap` to a Scheme list. The elements are pairs of
integers; each pair (x . y) creates a glissando line from the x-th note of the first chord to the y-th note of the second chord. Notes are numbered from zero in the order in which they appear in the input ‘.ly’ file. Not all notes need be part in a glissando.

> ```
> \relative {
>   <c' e>2\glissando g'
>   <c, e>\glissando <g' b>
>   \break
>   \set glissandoMap = #'((0 . 1) (1 . 0))
>   <c, g'>\glissando <d a'>
>   \set glissandoMap = #'((0 . 0) (0 . 1) (0 . 2))
>   c\glissando <d f a>
>   \set glissandoMap = #'((2 . 2) (0 . 0))
>   <f d a'>\glissando <c f c'>
> }
> ```

Different styles of glissandi can be created. For details, see
Line styles.

#### Selected Snippets

#### Contemporary glissando

A contemporary glissando without a final note can be typeset using a
hidden note and cadenza timing.

> ```
> \relative c'' {
>   \time 3/4
>   \override Glissando.style = #'zigzag
>   c4 c
>   \cadenzaOn
>   c4\glissando
>   \hideNotes
>   c,,4
>   \unHideNotes
>   \cadenzaOff
>   \bar "|"
> }
> ```

#### Adding timing marks to long glissandi

Skipped beats in very long glissandi are sometimes indicated by timing
marks, often consisting of stems without noteheads. Such stems can
also be used to carry intermediate expression markings.

If the stems do not align well with the glissando, they may need to be
repositioned slightly.

> ```
> glissandoSkipOn = {
>   \override NoteColumn.glissando-skip = ##t
>   \hide NoteHead
>   \override NoteHead.no-ledgers = ##t
> }
> glissandoSkipOff = {
>   \revert NoteColumn.glissando-skip
>   \undo \hide NoteHead
>   \revert NoteHead.no-ledgers
> }
> \relative c'' {
>   r8 f8\glissando
>   \glissandoSkipOn
>   f4 g a a8\noBeam
>   \glissandoSkipOff
>   a8
>   r8 f8\glissando
>   \glissandoSkipOn
>   g4 a8
>   \glissandoSkipOff
>   a8 |
>   r4 f\glissando \<
>   \glissandoSkipOn
>   a4\f \>
>   \glissandoSkipOff
>   b8\! r |
> }
> ```

#### Making glissandi breakable

Setting the `breakable` property to `#t` in combination with
`after-line-breaking` allows a glissando to break if it occurs at
a line break:

> ```
> glissandoSkipOn = {
>   \override NoteColumn.glissando-skip = ##t
>   \hide NoteHead
>   \override NoteHead.no-ledgers = ##t
> }
> \relative c'' {
>   \override Glissando.breakable = ##t
>   \override Glissando.after-line-breaking = ##t
>   f1\glissando |
>   \break
>   a4 r2. |
>   f1\glissando
>   \once \glissandoSkipOn
>   \break
>   a2 a4 r4 |
> }
> ```

#### Extending glissandi across repeats

A glissando which extends into several `\alternative` blocks can
be simulated by adding a hidden grace note with a glissando at the
start of each `\alternative` block. The grace note should be at
the same pitch as the note which starts the initial glissando. This is
implemented here with a music function which takes the pitch of the
grace note as its argument.

Note that in polyphonic music the grace note must be matched with
corresponding grace notes in all other voices.

> ```
> repeatGliss = #(define-music-function (grace)
>   (ly:pitch?)
>   #{
>     % the next two lines ensure the glissando is long enough
>     % to be visible
>     \once \override Glissando.springs-and-rods
>       = #ly:spanner::set-spacing-rods
>     \once \override Glissando.minimum-length = #3.5
>     \once \hideNotes
>     \grace $grace \glissando
>   #})
> \score {
>   \relative c'' {
>     \repeat volta 3 { c4 d e f\glissando }
>     \alternative {
>       { g2 d }
>       { \repeatGliss f g2 e }
>       { \repeatGliss f e2 d }
>     }
>   }
> }
> music = \relative c' {
>   \voiceOne
>   \repeat volta 2 {
>     g a b c\glissando
>   }
>   \alternative {
>     { d1 }
>     { \repeatGliss c \once \omit StringNumber e1\2 }
>   }
> }
> \score {
>   \new StaffGroup <<
>     \new Staff <<
>       \new Voice { \clef "G_8" \music }
>     >>
>     \new TabStaff <<
>       \new TabVoice { \clef "moderntab" \music }
>     >>
>   >>
> }
> ```

#### See also

Music Glossary:
glissando.

Notation Reference:
Line styles.

Snippets:
Expressive marks.

Internals Reference:
Glissando.

#### Known issues and warnings

Printing text over the line (such as gliss.) is not supported.

|[ << Musical notation ]|[Top][Contents][Index]|[ Specialist notation >> ]|
|--|--|--|
|[ < Glissando ]|[ Up : Expressive marks as lines ]|[ Trills > ]|

#### Arpeggio

An arpeggio on a chord (also known as a broken chord) is denoted by appending `\arpeggio` to the chord construct:

> ```
> \relative { <c' e g c>1\arpeggio }
> ```

Different types of arpeggios may be written.
`\arpeggioNormal` reverts to a normal arpeggio:

> ```
> \relative {
>   <c' e g c>2\arpeggio
>   \arpeggioArrowUp
>   <c e g c>2\arpeggio
>   \arpeggioArrowDown
>   <c e g c>2\arpeggio
>   \arpeggioNormal
>   <c e g c>2\arpeggio
> }
> ```

These predefined commands internally modify the
`arpeggio-direction` property; see their full
definition in the ‘ly/property-init.ly’ file.

Special *bracketed* arpeggio symbols can be created:

> ```
> \relative {
>   <c' e g c>2
>   \arpeggioBracket
>   <c e g c>2\arpeggio
>   \arpeggioParenthesis
>   <c e g c>2\arpeggio
>   \arpeggioParenthesisDashed
>   <c e g c>2\arpeggio
>   \arpeggioNormal
>   <c e g c>2\arpeggio
> }
> ```

These predefined commands internally override the `Arpeggio`
object’s `stencil` property, and may also adapt its
`X-extent` (that is, the horizontal dimension it takes
not to collide with other objects).

The dash properties of the parenthesis arpeggio are controlled
with the `dash-definition` property (see Slurs).

Arpeggios can be explicitly written out with ties. For more
information, see Ties.

#### Predefined commands

`\arpeggio`,
`\arpeggioArrowUp`,
`\arpeggioArrowDown`,
`\arpeggioNormal`,
`\arpeggioBracket`,
`\arpeggioParenthesis`,
`\arpeggioParenthesisDashed`.

#### Selected Snippets

#### Creating cross-staff arpeggios in a piano staff

In a `PianoStaff`, it is possible to let an *arpeggio* cross between the staves by setting the property `PianoStaff.connectArpeggios`.

> ```
> \new PianoStaff \relative c'' <<
>   \set PianoStaff.connectArpeggios = ##t
>   \new Staff {
>     <c e g c>4\arpeggio
>     <g c e g>4\arpeggio
>     <e g c e>4\arpeggio
>     <c e g c>4\arpeggio
>   }
>   \new Staff {
>     \clef bass
>     \repeat unfold 4 {
>       <c,, e g c>4\arpeggio
>     }
>   }
> >>
> ```

#### Creating cross-staff arpeggios in other contexts

Cross-staff *arpeggios* can be created in contexts other than `GrandStaff`, `PianoStaff` and `StaffGroup` if the
`Span_arpeggio_engraver` is included in the `Score` context.

> ```
> \score {
>   \new ChoirStaff {
>     \set Score.connectArpeggios = ##t
>     <<
>       \new Voice \relative c' {
>         <c e>2\arpeggio
>         <d f>2\arpeggio
>         <c e>1\arpeggio
>       }
>       \new Voice \relative c {
>         \clef bass
>         <c g'>2\arpeggio
>         <b g'>2\arpeggio
>         <c g'>1\arpeggio
>       }
>     >>
>   }
>   \layout {
>     \context {
>       \Score
>       \consists "Span_arpeggio_engraver"
>     }
>   }
> }
> ```

#### Creating arpeggios across notes in different voices

An *arpeggio* can be drawn across notes in different voices on the same staff if the `Span_arpeggio_engraver` is added to the
`Staff` context:

> ```
> \new Staff \with {
>   \consists "Span_arpeggio_engraver"
> }
> \relative c' {
>   \set Staff.connectArpeggios = ##t
>   <<
>     { <e' g>4\arpeggio <d f> <d f>2 }
>     \\
>     { <d, f>2\arpeggio <g b>2 }
>   >>
> }
> ```

#### See also

Music Glossary:
arpeggio.

Notation Reference:
Slurs, Ties.

Installed Files:
‘ly/property-init.ly’.

Snippets:
Expressive marks.

Internals Reference:
Arpeggio, Slur, PianoStaff.

#### Known issues and warnings

Predefined commands such as `\arpeggioArrowUp` only
apply to the current context, and thus will not affect
arpeggios spanning several voices or staves. In such cases,
these commands need to be used in a `\context` block within
`\layout`, or in a `\with` block, as explained in
Changing context default settings. Alternatively, rather than using predefined shortcuts, it may be advisable to directly override the relevant properties for the `Arpeggio` object in the appropriate context; for example:

> ```
> \override Staff.Arpeggio.stencil = #ly:arpeggio::brew-chord-bracket
> ```

to print cross-voice arpeggio brackets at the `Staff` level, or

> ```
> \override PianoStaff.Arpeggio.arpeggio-direction = #UP
> ```

to print cross-staff arrowed arpeggios (pointing upwards) in a
`PianoStaff` context.

It is not possible to mix connected arpeggios and unconnected
arpeggios in one `PianoStaff` at the same point in
time.

The simple way of setting parenthesis-style arpeggio brackets does not work for
cross-staff arpeggios; see Cross-staff stems.

|[ << Musical notation ]|[Top][Contents][Index]|[ Specialist notation >> ]|
|--|--|--|
|[ < Arpeggio ]|[ Up : Expressive marks as lines ]|[ Repeats > ]|

#### Trills

Short trills without an extender line are printed with
`\trill`; see Articulations and ornamentations.

Longer trills with an extender line are made with
`\startTrillSpan` and `\stopTrillSpan`:

> ```
> \relative {
>   d''1\startTrillSpan
>   d1
>   c2\stopTrillSpan
>   r2
> }
> ```

A trill spanner crossing a line break will restart exactly above
the first note on the new line.

> ```
> \relative {
>   d''1\startTrillSpan
>   \break
>   d1
>   c2\stopTrillSpan
>   r2
> }
> ```

Consecutive trill spans will work without explicit
`\stopTrillSpan` commands, since successive trill spanners will
automatically become the right bound of the previous trill.

> ```
> \relative {
>   d''1\startTrillSpan
>   d1
>   b1\startTrillSpan
>   d2\stopTrillSpan
>   r2
> }
> ```

Trills can also be combined with grace notes. The syntax of this
construct and the method to precisely position the grace notes are
described in Grace notes.

> ```
> \relative {
>   d''1~\afterGrace
>   d1\startTrillSpan { c32[ d]\stopTrillSpan }
>   c2 r2
> }
> ```

Trills that require an auxiliary note with an explicit pitch can
be typeset with the `\pitchedTrill` command. The first
argument is the main note, and the second is the *trilled* note, printed as a stemless note head in parentheses.

> ```
> \relative {
>   \pitchedTrill
>   d''2\startTrillSpan fis
>   d2
>   c2\stopTrillSpan
>   r2
> }
> ```

The Accidental of the first pitched trill in a measure is always
printed, even for naturals.

> ```
> {
>   \key d \major
>   \pitchedTrill
>   d'2\startTrillSpan cis d\stopTrillSpan
>   \pitchedTrill
>   d2\startTrillSpan c d\stopTrillSpan
>   \pitchedTrill
>   d2\startTrillSpan e d\stopTrillSpan
> }
> ```

Subsequent accidentals (of the same note in the same measure) will need
to be added manually.

> ```
> \relative {
>   \pitchedTrill
>   eis''4\startTrillSpan fis
>   eis4\stopTrillSpan
>   \pitchedTrill
>   eis4\startTrillSpan cis
>   eis4\stopTrillSpan
>   \pitchedTrill
>   eis4\startTrillSpan fis
>   eis4\stopTrillSpan
>   \pitchedTrill
>   eis4\startTrillSpan fis!
>   eis4\stopTrillSpan
> }
> ```

#### Predefined commands

`\startTrillSpan`,
`\stopTrillSpan`.

#### See also

Music Glossary:
trill.

Notation Reference:
Articulations and ornamentations, Grace notes.

Snippets:
Expressive marks.

Internals Reference:
TrillSpanner, TrillPitchHead, TrillPitchAccidental, TrillPitchParentheses, TrillPitchGroup, Pitched_trill_engraver.

|[ << Musical notation ]|[Top][Contents][Index]|[ Specialist notation >> ]|
|--|--|--|
|[ < Arpeggio ]|[ Up : Expressive marks as lines ]|[ Repeats > ]|
