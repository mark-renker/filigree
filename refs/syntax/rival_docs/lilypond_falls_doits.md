# lilypond_falls_doits
Source: https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks-as-curves
Fetched: 2026-08-30

|[ << Musical notation ]|[Top][Contents][Index]|[ Specialist notation >> ]|
|--|--|--|
|[ < New dynamic marks ]|[ Up : Expressive marks ]|[ Slurs > ]|
### 1.3.2 Expressive marks as curves

This section explains how to create various expressive marks that are curved: normal slurs, phrasing slurs, breath marks, falls, and doits.

|Slurs|
|--|
|Phrasing slurs|
|Breath marks|
|Falls and doits|
|[ << Musical notation ]|[Top][Contents][Index]|[ Specialist notation >> ]|
|--|--|--|
|[ < Expressive marks as curves ]|[ Up : Expressive marks as curves ]|[ Phrasing slurs > ]|
#### Slurs

`Slurs` are entered using parentheses:

**Note:** In polyphonic music, a slur must be terminated

in the same voice it began.

\relative { f''4( g a) a8 b( a4 g2 f4) <c e>2( <b d>2) }

Slurs may be manually placed above or below the staff; see Direction and placement.

Simultaneous or overlapping slurs require special attention. Most

occurences of outer slurs actually indicate phrasing, and phrasing

slurs may overlap a regular slur, see Phrasing slurs. When

multiple regular slurs are needed in a single

`Voice`,

matching slur starts and ends need to be labelled by preceding

them with

`\=` followed by an identifying key (a symbol or

non-negative integer).

\fixed c' { <c~ f\=1( g\=2( >2 <c e\=1) a\=2) > }

Slurs can be solid, dotted, or dashed. Solid is the default slur style:

\relative { c'4( e g2) \slurDashed g4( e c2) \slurDotted c4( e g2) \slurSolid g4( e c2) }

Slurs can also be made half-dashed (the first half dashed, the second half solid) or half-solid (the first half solid, the second half dashed):

\relative { c'4( e g2) \slurHalfDashed g4( e c2) \slurHalfSolid c4( e g2) \slurSolid g4( e c2) }

Custom dash patterns for slurs can be defined:

\relative { c'4( e g2) \slurDashPattern #0.7 #0.75 g4( e c2) \slurDashPattern #0.5 #2.0 c4( e g2) \slurSolid g4( e c2) }

#### Predefined commands

`\slurUp`,

`\slurDown`,

`\slurNeutral`,

`\slurDashed`,

`\slurDotted`,

`\slurHalfDashed`,

`\slurHalfSolid`,

`\slurDashPattern`,

`\slurSolid`.

#### Selected Snippets

*Using double slurs for legato chords*

Some composers write two

*slurs* when they want legato

chords. This can be achieved by setting

`doubleSlurs`.

\relative c' { \set doubleSlurs = ##t <c e>4( <d f> <c e> <d f>) }

*Positioning text markups inside slurs*

Text markups need to have the

`outside-staff-priority` property

set to false in order to be printed inside slurs.

\relative c'' { \override TextScript.avoid-slur = #'inside \override TextScript.outside-staff-priority = ##f c2(^\markup { \halign #-10 \natural } d4.) c8 }

*Making slurs with complex dash structure*

Slurs can be made with complex dash patterns by defining the

`dash-definition` property.

`dash-definition` is a list of

`dash-elements`. A

`dash-element` is a list of parameters

defining the dash behavior for a segment of the slur.

The slur is defined in terms of the bezier parameter t which ranges

from 0 at the left end of the slur to 1 at the right end of the slur.

`dash-element` is a list

`(start-t stop-t dash-fraction dash-period)`. The region of the

slur from

`start-t` to

`stop-t` will have a fraction

`dash-fraction` of each

`dash-period`

black.

`dash-period` is defined in terms of staff

spaces.

`dash-fraction` is set to 1 for a solid slur.

\relative c' { \once \override Slur.dash-definition = #'((0 0.3 0.1 0.75) (0.3 0.6 1 1) (0.65 1.0 0.4 0.75)) c4( d e f) \once \override Slur.dash-definition = #'((0 0.25 1 1) (0.3 0.7 0.4 0.75) (0.75 1.0 1 1)) c4( d e f) }

#### See also

Music Glossary: slur.

Learning Manual: On the un-nestedness of brackets and ties.

Notation Reference: Direction and placement, Phrasing slurs.

Snippets: Expressive marks.

Internals Reference: Slur.

|[ << Musical notation ]|[Top][Contents][Index]|[ Specialist notation >> ]|
|--|--|--|
|[ < Slurs ]|[ Up : Expressive marks as curves ]|[ Breath marks > ]|
#### Phrasing slurs

`Phrasing slurs` (or phrasing marks) that indicate a

musical sentence are written using the commands

`\(` and

`\)` respectively:

\relative { c''4\( d( e) f( e2) d\) }

Typographically, a phrasing slur behaves almost exactly like a

normal slur. However, they are treated as different objects; a

`\slurUp` will have no effect on a phrasing slur. Phrasing

may be manually placed above or below the staff; see

Direction and placement.

Simultaneous or overlapping phrasing slurs are entered using

`\=` as with regular slurs, see Slurs.

Phrasing slurs can be solid, dotted, or dashed. Solid is the default style for phrasing slurs:

\relative { c'4\( e g2\) \phrasingSlurDashed g4\( e c2\) \phrasingSlurDotted c4\( e g2\) \phrasingSlurSolid g4\( e c2\) }

Phrasing slurs can also be made half-dashed (the first half dashed, the second half solid) or half-solid (the first half solid, the second half dashed):

\relative { c'4\( e g2\) \phrasingSlurHalfDashed g4\( e c2\) \phrasingSlurHalfSolid c4\( e g2\) \phrasingSlurSolid g4\( e c2\) }

Custom dash patterns for phrasing slurs can be defined:

\relative { c'4\( e g2\) \phrasingSlurDashPattern #0.7 #0.75 g4\( e c2\) \phrasingSlurDashPattern #0.5 #2.0 c4\( e g2\) \phrasingSlurSolid g4\( e c2\) }

Dash pattern definitions for phrasing slurs have the same structure as dash pattern definitions for slurs. For more information about complex dash patterns, see the snippets under Slurs.

#### Predefined commands

`\phrasingSlurUp`,

`\phrasingSlurDown`,

`\phrasingSlurNeutral`,

`\phrasingSlurDashed`,

`\phrasingSlurDotted`,

`\phrasingSlurHalfDashed`,

`\phrasingSlurHalfSolid`,

`\phrasingSlurDashPattern`,

`\phrasingSlurSolid`.

#### See also

Learning Manual: On the un-nestedness of brackets and ties.

Notation Reference: Direction and placement, Slurs.

Snippets: Expressive marks.

Internals Reference: PhrasingSlur.

|[ << Musical notation ]|[Top][Contents][Index]|[ Specialist notation >> ]|
|--|--|--|
|[ < Phrasing slurs ]|[ Up : Expressive marks as curves ]|[ Falls and doits > ]|
#### Breath marks

The

`\breathe` command calls for the performer to shorten the

previous note to take a breath.

\fixed c'' { c2. \breathe d4 }

For a short break in sound that is not taken away from the previous note, see Caesuras.

Unlike other expressive marks, a breath mark is treated as a

separate music event; therefore, any expressive marks pertaining

to the preceding note, and any brackets indicating manual beams,

slurs, or phrasing slurs, must be placed before

`\breathe`.

`\breathe` does not accept articulations itself, but

see Caesuras.

A breath mark ends an automatic beam; to override this, see Manual beams.

\fixed c'' { c8 \breathe d e f g2 }

The

`breathMarkType` context property controls which of

several predefined breath marks the

`\breathe` command

creates. See List of breath marks.

\fixed c'' { \set breathMarkType = #'tickmark c2. \breathe d4 }

#### See also

Music Glossary: breath mark.

Notation Reference: Caesuras, Divisiones.

Snippets: Expressive marks.

Internals Reference: BreathingEvent, BreathingSign, Breathing_sign_engraver.

|[ << Musical notation ]|[Top][Contents][Index]|[ Specialist notation >> ]|
|--|--|--|
|[ < Breath marks ]|[ Up : Expressive marks as curves ]|[ Expressive marks as lines > ]|
#### Falls and doits

`Falls` and `doits` can be added to notes using

the

`\bendAfter` command. The direction of the fall or doit

is indicated with a plus or minus (up or down). The number

indicates the pitch interval that the fall or doit will extend

*beyond* the main note.

\relative c'' { c2\bendAfter #+4 c2\bendAfter #-4 c2\bendAfter #+6.5 c2\bendAfter #-6.5 c2\bendAfter #+8 c2\bendAfter #-8 }

#### Selected Snippets

*Adjusting the shape of falls and doits*

The

`shortest-duration-space` property may be tweaked to adjust

the shape of

*falls* and *doits*.

\relative c'' { \override Score.SpacingSpanner.shortest-duration-space = #4.0 c2-\bendAfter #5 c2-\bendAfter #-4.75 c2-\bendAfter #8.5 c2-\bendAfter #-6 }

#### See also

Snippets: Expressive marks.

|[ << Musical notation ]|[Top][Contents][Index]|[ Specialist notation >> ]|
|--|--|--|
|[ < Breath marks ]|[ Up : Expressive marks as curves ]|[ Expressive marks as lines > ]|

