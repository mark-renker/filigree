# lilypond_marks_notes
Source: https://lilypond.org/doc/v2.24/Documentation/notation/expressive-marks-attached-to-notes
Fetched: 2026-08-30

|[ << Musical notation ]|[Top][Contents][Index]|[ Specialist notation >> ]|
|--|--|--|
|[ < Expressive marks ]|[ Up : Expressive marks ]|[ Articulations and ornamentations > ]|

### 1.3.1 Expressive marks attached to notes

This section explains how to create expressive marks that are
attached to notes: articulations, ornamentations, and dynamics.
Methods to create new dynamic markings are also discussed.

|Articulations and ornamentations| | |
|--|--|--|
|Dynamics| | |
|New dynamic marks| | |
|[ << Musical notation ]|[Top][Contents][Index]|[ Specialist notation >> ]|
|--|--|--|
|[ < Expressive marks attached to notes ]|[ Up : Expressive marks attached to notes ]|[ Dynamics > ]|

#### Articulations and ornamentations

A variety of symbols that denote articulations, ornamentations,
and other performance indications can be attached to a note using
this syntax:

> ```
> note\name
> ```

The possible values for `name` are listed in
List of articulations. For example:

> ```
> \relative {
>   c''4\staccato c\mordent b2\turn
>   c1\fermata
> }
> ```

Some of these articulations have shorthands for easier entry.
Shorthands are appended to the note name, and their syntax
consists of a dash `-` followed by a symbol signifying the
articulation. Predefined shorthands exist for marcato, stopped, tenuto, staccatissimo, accent, staccato, and portato. Their corresponding output appears as follows:

> ```
> \relative {
>   c''4-^ c-+ c-- c-!
>   c4-> c-. c2-_
> }
> ```

The rules for the default placement of articulations are defined
in ‘scm/script.scm’. Articulations and ornamentations may be manually placed above or below the staff; see Direction and placement.

The type of grob that an articulation creates depends on what it
is attached to.

- On notes or ordinary rests, articulations create `Script`
  objects.
- On multi-measure rests, articulations create
  `MultiMeasureRestScript` objects.
- On `\caesura`, articulations create `CaesuraScript`
  objects.

> ```
> \override Score.Script.color = #(universal-color 'vermillion)
> \override Score.MultiMeasureRestScript.color = #(universal-color 'blue)
> \override Score.CaesuraScript.color = #(universal-color 'orange)
> a'2\fermata r\fermata
> R1\fermata
> g'2 \caesura \fermata f'2
> ```

In addition to articulations, text and markups can be attached to
notes. See Text scripts.

For more information about the ordering of `Script` and
`TextScript` grobs that are attached to notes, see
Placement of objects.

#### Selected Snippets

#### Modifying default values for articulation shorthand notation

The shorthands are defined in ‘ly/script-init.ly’, where the variables `dashHat`, `dashPlus`, `dashDash`,
`dashBang`, `dashLarger`, `dashDot`, and
`dashUnderscore` are assigned default values. The default values
for the shorthands can be modified. For example, to associate the
`-+` (`dashPlus`) shorthand with the *trill* symbol instead of the default *+* symbol, assign the value `\trill`
to the variable `dashPlus`:

> ```
> \relative c'' { c1-+ }
> dashPlus = \trill
> \relative c'' { c1-+ }
> ```

#### Controlling the vertical ordering of scripts

The vertical ordering of scripts is controlled with the
`'script-priority` property. The lower this number, the closer it
will be put to the note. In this example, the `TextScript` (the
*sharp* symbol) first has the lowest priority, so it is put lowest in the first example. In the second, the *prall trill* (the `Script`) has the lowest, so it is on the inside. When two objects
have the same priority, the order in which they are entered determines
which one comes first.

> ```
> \relative c''' {
>   \once \override TextScript.script-priority = #-100
>   a2^\prall^\markup { \sharp }
>   \once \override Script.script-priority = #-100
>   a2^\prall^\markup { \sharp }
> }
> ```

#### Creating a delayed turn

Creating a delayed turn, where the lower note of the turn uses the
accidental, requires several overrides. The
`outside-staff-priority` property must be set to `#f`, as
otherwise this would take precedence over the
`avoid-slur property`. Changing the fraction `2/3`
adjusts the horizontal position.

> ```
> \relative c'' {
>   \after 2*2/3 \turn c2( d4) r |
>   \after 4 \turn c4.( d8)
>   \after 4
>   {
>     \once \set suggestAccidentals = ##t
>     \once \override AccidentalSuggestion.outside-staff-priority = ##f
>     \once \override AccidentalSuggestion.avoid-slur = #'inside
>     \once \override AccidentalSuggestion.font-size = -3
>     \once \override AccidentalSuggestion.script-priority = -1
>     \once \hideNotes
>     cis8\turn \noBeam
>   }
>   d4.( e8)
> }
> ```

#### See also

Music Glossary:
tenuto, accent, staccato, portato.

Learning Manual:
Placement of objects.

Notation Reference:
Text scripts, Direction and placement, List of articulations, Trills.

Installed Files:
‘scm/script.scm’.

Snippets:
Expressive marks.

Internals Reference:
CaesuraScript, MultiMeasureRestScript, Script, TextScript.

|[ << Musical notation ]|[Top][Contents][Index]|[ Specialist notation >> ]|
|--|--|--|
|[ < Articulations and ornamentations ]|[ Up : Expressive marks attached to notes ]|[ New dynamic marks > ]|

#### Dynamics

Absolute dynamic marks are specified using a command after a note,
such as `c4\ff`. The available dynamic marks are
`\ppppp`, `\pppp`, `\ppp`, `\pp`, `\p`,
`\mp`, `\mf`, `\f`, `\ff`, `\fff`,
`\ffff`, `\fffff`, `\fp`, `\sf`, `\sff`,
`\sp`, `\spp`, `\sfz`, `\rfz`, and `\n`.
Dynamic marks may be manually placed above or below the staff; see
Direction and placement.

> ```
> \relative c'' {
>   c2\ppp c\mp
>   c2\rfz c^\mf
>   c2_\spp c^\ff
> }
> ```

A crescendo mark is started with `\<` and
terminated with `\!`, an absolute dynamic, or an additional
crescendo or decrescendo mark. A decrescendo mark is started with `\>` and is also terminated with `\!`, an
absolute dynamic, or another crescendo or decrescendo mark.
`\cr` and `\decr` may be used instead of `\<` and
`\>`; `\endcr` and `\enddecr` maybe used instead of
`\!` to end a crescendo or decrescendo mark, respectively.
Hairpins are engraved by default using this notation.

> ```
> \relative c'' {
>   c2\< c\!
>   d2\< d\f
>   e2\< e\>
>   f2\> f\!
>   e2\> e\mp
>   d2\> d\>
>   c1\!
> }
> ```

A hairpin that is terminated with `\!` will end at the
right edge of the note that has the `\!` assigned to it. In the
case where it is terminated with the start of another crescendo or decrescendo mark, it will end at the center of the note that has the next `\<` or `\>` assigned to it. The next
hairpin will then start at the right edge of the same note
instead of the usual left edge had it been terminated with `\!`
before. A hairpin ending on a downbeat will stop at the preceding bar line.

> ```
> \relative {
>   c''1\< | c4 a c\< a | c4 a c\! a\< | c4 a c a\!
> }
> ```

Hairpins that are terminated with absolute dynamic marks instead of
`\!` will also be engraved in a similar way. However, the length
of the absolute dynamic itself can alter where the preceding hairpin
ends.

> ```
> \relative {
>   c''1\< | c4 a c\mf a | c1\< | c4 a c\ffff a
> }
> ```

Often, marks like crescendo or decrescendo should begin or end at some point of time during a sustained note. This can be achieved with `\after`, which can also be used to create
delayed articulations or text scripts:

> ```
> <<
>   \relative {
>     \after 2 \< c'1
>     d4\f\> e f g
>     \after 2. \pp c,1
>     \after 2. \fermata e
>     \after 2. ^"Fine." f
>   }
>   \relative {
>     \repeat unfold 12 c'4
>     c c c c\fermata
>     c c c c
>   }
> >>
> ```

Multiple instances of `\after` can be used to engrave multiple marks
on one note. This is particularly useful when adding a crescendo
and decrescendo to the same note:

> ```
> \relative {
>   c''4\< d\! e\> c\!
>   \after 4 \< \after 2\> \after 2. \! f1
>   \textLengthOn
>   \after 4 \> \after 2. ^"hush!" c1
>   g4\pp
> }
> ```

If the first in such a sequence of marks on a single note is supposed
to coincide with the onset of the note, it is convenient to attach
it to an empty chord `<>`. This way, all marks can be entered
in their natural visual order:

> ```
> {
>   <>\< \after 4 \> \after 2 \! c'1
>   % easier to write and read than:
>   \after 4 \> \after 2 \! c'1\<
> }
> ```

The `\espressivo` command can also be used to indicate a crescendo
and decrescendo on the same note. However, be warned that this is
implemented as an articulation, not a dynamic.

> ```
> \relative {
>   c''2 b4 a
>   g1\espressivo
>   \after 2. \espressivo c
> }
> ```

Textual crescendo marks begin with `\cresc`.
Textual decrescendos begin with `\decresc` or `\dim`.
Extender lines are engraved as required.

> ```
> \relative {
>   g'8\cresc a b c b c d e\mf |
>   f8\decresc e d c e\> d c b |
>   a1\dim ~ |
>   a2. r4\! |
> }
> ```

Textual marks for dynamic changes can also replace hairpins:

> ```
> \relative c'' {
>   \crescTextCresc
>   c4\< d e f\! |
>   \dimTextDecresc
>   g4\> e d c\! |
>   \dimTextDecr
>   e4\> d c b\! |
>   \dimTextDim
>   d4\> c b a\! |
>   \crescHairpin
>   \dimHairpin
>   c4\< d\! e\> d\! |
> }
> ```

To create new absolute dynamic marks or text that should be
aligned with dynamics, see New dynamic marks.

Vertical positioning of dynamics is handled by
DynamicLineSpanner.

A `Dynamics` context is available to engrave dynamics on
their own horizontal line. Use spacer rests to indicate timing.
(Notes in a `Dynamics` context will also take up
musical time, but will not be engraved.)
The `Dynamics` context can usefully contain some other
items such as text scripts, text spanners, and piano pedal marks.

> ```
> <<
>   \new Staff \relative {
>     c'2 d4 e |
>     c4 e e,2 |
>     g'4 a g a |
>     c1 |
>   }
>   \new Dynamics {
>     s1\< |
>     s1\f |
>     s2\dim s2-"rit." |
>     s1\p |
>   }
> >>
> ```

#### Predefined commands

`\dynamicUp`,
`\dynamicDown`,
`\dynamicNeutral`,
`\crescTextCresc`,
`\dimTextDim`,
`\dimTextDecr`,
`\dimTextDecresc`,
`\crescHairpin`,
`\dimHairpin`.

#### Selected Snippets

#### Setting hairpin behavior at bar lines

If the note which ends a hairpin falls on a downbeat, the hairpin stops
at the bar line immediately preceding. This behavior can be controlled
by overriding the `'to-barline` property.

> ```
> \relative c'' {
>   e4\< e2.
>   e1\!
>   \override Hairpin.to-barline = ##f
>   e4\< e2.
>   e1\!
> }
> ```

#### Setting the minimum length of hairpins

If hairpins are too short, they can be lengthened by modifying the
`minimum-length` property of the `Hairpin` object.

> ```
> <<
>   {
>     \after 4 \< \after 2 \> \after 2. \! f'1
>     \override Hairpin.minimum-length = #8
>     \after 4 \< \after 2 \> \after 2. \! f'1
>   }
>   {
>     \repeat unfold 8 c'4
>   }
> >>
> ```

#### Aligning the ends of hairpins to NoteColumn directions

The ends of hairpins may be aligned to the `LEFT`, `CENTER`
or `RIGHT` of `NoteColumn` grobs by overriding the property
`endpoint-alignments`, which is a pair of numbers representing
the left and right ends of the hairpin. `endpoint-alignments`
are expected to be directions (either -1, 0 or 1). Other values
will be transformed with a warning. The right end of a hairpin
terminating at a rest is not affected, always ending at the left edge
of the rest.

> ```
> {
>   c'2\< <c' d'>\! |
>   \override Hairpin.endpoint-alignments = #'(1 . -1)
>   c'2\< <c' d'>\! |
>   \override Hairpin.endpoint-alignments = #`(,LEFT . ,CENTER)
>   c'2\< <c' d'>\! |
> }
> ```

#### Moving the ends of hairpins

The ends of hairpins may be offset by setting the `shorten-pair`
property of the `Hairpin` object. Positive values move endpoints
to the right, negative to the left. Unlike the `minimum-length`
property, this property only affects the appearance of the hairpin; it
does not adjust horizontal spacing (including the position of bounding
dynamics). This method is thus suitable for fine-tuning a hairpin
within its allotted space.

> ```
> {
>   c'1~\<
>   c'2~ c'\!
>   \once \override Hairpin.shorten-pair = #'(2 . 2)
>   c'1~\<
>   c'2~ c'\!
>   \once \override Hairpin.shorten-pair = #'(-2 . -2)
>   c'1~\<
>   c'2~ c'\!
>   c'1~\p-\tweak shorten-pair #'(2 . 0)\<
>   c'2~ c'\ffff
> }
> ```

#### Printing hairpins using al niente notation

Hairpin dynamics may be printed with a circled tip (“al niente”
notation) by setting the `circled-tip` property of the
`Hairpin` object to `#t`.

> ```
> \relative c'' {
>   \override Hairpin.circled-tip = ##t
>   c2\< c\!
>   c4\> c\< c2\!
> }
> ```

#### Printing hairpins in various styles

Hairpin dynamics may be created in a variety of styles.

> ```
> \relative c'' {
>   \override Hairpin.stencil = #flared-hairpin
>   a4\< a a a\f
>   a4\p\< a a a\ff
>   a4\sfz\< a a a\!
>   \override Hairpin.stencil = #constante-hairpin
>   a4\< a a a\f
>   a4\p\< a a a\ff
>   a4\sfz\< a a a\!
>   \override Hairpin.stencil = #flared-hairpin
>   a4\> a a a\f
>   a4\p\> a a a\ff
>   a4\sfz\> a a a\!
>   \override Hairpin.stencil = #constante-hairpin
>   a4\> a a a\f
>   a4\p\> a a a\ff
>   a4\sfz\> a a a\!
> }
> ```

#### Vertically aligned dynamics and textscripts

All `DynamicLineSpanner` objects (hairpins and dynamic texts) are
placed with their reference line at least `'staff-padding` from
the staff, unless other notation forces them to be farther. Setting
`'staff-padding` to a sufficiently large value aligns the
dynamics.

The same idea, together with `\textLengthOn`, is used to align
the text scripts along their baseline.

> ```
> music = \relative c' {
>   a'2\p b\f
>   e4\p f\f\> g, b\p
>   c2^\markup { \huge gorgeous } c^\markup { \huge fantastic }
> }
> {
>   \music
>   \break
>   \override DynamicLineSpanner.staff-padding = #3
>   \textLengthOn
>   \override TextScript.staff-padding = #1
>   \music
> }
> ```

#### Hiding the extender line for text dynamics

Text style dynamic changes (such as *cresc.* and *dim.*) are printed with a dashed line showing their extent. This line can be suppressed in the following way:

> ```
> \relative c'' {
>   \override DynamicTextSpanner.style = #'none
>   \crescTextCresc
>   c1\< | d | b | c\!
> }
> ```

#### Changing text and spanner styles for text dynamics

The text used for *crescendos* and *decrescendos* can be changed by modifying the context properties `crescendoText` and
`decrescendoText`.

The style of the spanner line can be changed by modifying the
`'style` property of `DynamicTextSpanner`. The default value
is `'dashed-line`, and other possible values include `'line`,
`'dotted-line` and `'none`.

> ```
> \relative c'' {
>   \set crescendoText = \markup { \italic { cresc. poco } }
>   \set crescendoSpanner = #'text
>   \override DynamicTextSpanner.style = #'dotted-line
>   a2\< a
>   a2 a
>   a2 a
>   a2 a\mf
> }
> ```

#### See also

Music Glossary:
al niente, crescendo, decrescendo, hairpin.

Learning Manual:
Articulations and dynamics.

Notation Reference:
Direction and placement, New dynamic marks, Enhancing MIDI output, Controlling MIDI dynamics.

Snippets:
Expressive marks.

Internals Reference:
DynamicText, Hairpin, DynamicLineSpanner, Dynamics.

|[ << Musical notation ]|[Top][Contents][Index]|[ Specialist notation >> ]|
|--|--|--|
|[ < Dynamics ]|[ Up : Expressive marks attached to notes ]|[ Expressive marks as curves > ]|

#### New dynamic marks

The easiest way to create dynamic indications is to use
`\markup` objects.

> ```
> moltoF = \markup { molto \dynamic f }
> \relative {
>   <d' e>16_\moltoF <d e>
>   <d e>2..
> }
> ```

In markup mode, editorial dynamics (within parentheses or square
brackets) can be created. The syntax for markup mode is described
in Formatting text.

> ```
> roundF = \markup {
>     \center-align \concat { \bold { \italic ( }
>            \dynamic f \bold { \italic ) } } }
> boxF = \markup { \bracket { \dynamic f } }
> \relative {
>   c'1_\roundF
>   c1_\boxF
> }
> ```

Simple, centered dynamic marks are easily created with the
`make-dynamic-script` function.

> ```
> sfzp = #(make-dynamic-script "sfzp")
> \relative {
>   c'4 c c\sfzp c
> }
> ```

In general, `make-dynamic-script` takes any markup object as its
argument. The dynamic font only contains the characters
`f,m,p,r,s` and `z`, so if a dynamic mark that includes
plain text or punctuation symbols is desired, markup commands that
reverts font family and font encoding to normal text should be used,
for example `\normal-text`. The interest of using
`make-dynamic-script` instead of an ordinary markup is ensuring
the vertical alignment of markup objects and hairpins that are
attached to the same note head.

> ```
> roundF = \markup { \center-align \concat {
>            \normal-text { \bold { \italic ( } }
>            \dynamic f
>            \normal-text { \bold { \italic ) } } } }
> boxF = \markup { \bracket { \dynamic f } }
> mfEspress = \markup { \center-align \line {
>               \hspace #3.7 mf \normal-text \italic espress. } }
> roundFdynamic = #(make-dynamic-script roundF)
> boxFdynamic = #(make-dynamic-script boxF)
> mfEspressDynamic = #(make-dynamic-script mfEspress)
> \relative {
>   c'4_\roundFdynamic\< d e f
>   g,1~_\boxFdynamic\>
>   g1
>   g'1~\mfEspressDynamic
>   g1
> }
> ```

The Scheme form of markup mode may be used instead. Its syntax is
explained in Markup construction in Scheme.

> ```
> moltoF = #(make-dynamic-script
>             (markup #:normal-text "molto"
>                     #:dynamic "f"))
> \relative {
>   <d' e>16 <d e>
>   <d e>2..\moltoF
> }
> ```

To left-align the dynamic text rather than centering it on a note
use a `\tweak`:

> ```
> moltoF = \tweak DynamicText.self-alignment-X #LEFT
>          #(make-dynamic-script
>             (markup #:normal-text "molto"
>                     #:dynamic "f"))
> \relative {
>   <d' e>16 <d e>
>   <d e>2..\moltoF <d e>1
> }
> ```

Font settings in markup mode are described in
Selecting font and font size.

#### See also

Notation Reference:
Formatting text, Selecting font and font size, Enhancing MIDI output, Controlling MIDI dynamics.

Extending LilyPond:
Markup construction in Scheme.

Snippets:
Expressive marks.

|[ << Musical notation ]|[Top][Contents][Index]|[ Specialist notation >> ]|
|--|--|--|
|[ < Dynamics ]|[ Up : Expressive marks attached to notes ]|[ Expressive marks as curves > ]|
