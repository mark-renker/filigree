# lilypond_enhancing_midi
Source: https://lilypond.org/doc/v2.25/Documentation/notation/enhancing-midi-output
Fetched: 2026-08-30

|[ << Creating MIDI output ]|[Top][Contents][Index]|[ Extracting musical information >> ]|
|--|--|--|
|[ < Context properties for MIDI effects ]|[ Up: Creating MIDI output ]|[ The articulate script > ]|

### 24.9 Enhancing MIDI output

The default MIDI output is basic but can be improved by setting MIDI
instruments and various `\midi` block properties.

Additional scripts allow to fine-tune the way dynamics, articulations
and rhythm are rendered in MIDI: the articulate script and the swing script.

|24.9.1 The articulate script| | |
|--|--|--|
|24.9.2 The swing script| | |

|[ << Creating MIDI output ]|[Top][Contents][Index]|[ Extracting musical information >> ]|
|--|--|--|
|[ < Enhancing MIDI output ]|[ Up: Enhancing MIDI output ]|[ The swing script > ]|

#### 24.9.1 The articulate script

To use the articulate script add the appropriate `\include`
command at the top of the input file;

```
\include "articulate.ly"

```

The script creates MIDI output into appropriately ‘time-scaled’ notes
to match many articulation and tempo indications. Engraved output
however, will also be altered to literally match the MIDI output.

```
\score {
  \articulate <<
    … music …
  >>
  \midi { }
}

```

The `\articulate` command enables abbreviatures (such as trills and
turns) to be processed. A full list of supported items can be found in
the script itself. See ly/articulate.ly.

#### See also

Learning Manual:
Other sources of information.

Notation Reference:
Score layout.

Installed Files:
ly/articulate.ly.

**Note:** The articulate script may shorten chords, which might not be appropriate for some types of instrument, such as organ music. Notes that do not have any articulations attached to them may also be shortened; so to allow for this, restrict the use of the `\articulate` function to shorter segments of music, or modify the
values of the variables defined in the articulate script to compensate for the note-shortening behavior.

|[ << Creating MIDI output ]|[Top][Contents][Index]|[ Extracting musical information >> ]|
|--|--|--|
|[ < The articulate script ]|[ Up: Enhancing MIDI output ]|[ Extracting musical information > ]|

#### 24.9.2 The swing script

The swing script provides additional functions allowing for regular durations to be played with an unequal rhythm. The most obvious example is ‘swing’ interpretation commonly found in jazz music where binary eighth notes should be played in a ternary fashion; however additional interpretations are also supported.

This script has to be `\include`-d at the beginning of the input file:

```
\include "swing.ly"

```

Three commands are provided:

- `\tripletFeel` creates a triplet-feel swing. It takes two
  arguments: the durations that should be affected by it (typically
  `8` for eighth notes), and then the music expression to which
  it should be applied.
- `\applySwing` takes an additional argument prior to the music
  expression: a ‘weight list’ of n number ratios expressing the way regular notes should be played: for example, `#'(2 1)` indicates
  that every other note should be played twice as long as the following note
  (in fact, `\tripletFeel duration {music}`
  is actually a shortcut for
  `\applySwing duration #'(2 1) {music}`). Smoother swung
  eighths may be obtained with a weight list of `#'(3 2)`, or other values
  depending on taste.

  That list may include more than two values, which allows for longer and more
  sophisticated groove patterns; for example, a samba feel for sixteenth notes
  may be obtained as follows:

  ```
  \score {
  \applySwing 16 #'(3 2 2 3) {
  … music …
  }
  \midi { }
  }

  ```
- `\applySwingWithOffset` adds yet another argument between the
  ‘weight list’ and the music expression: an offset length. This
  command should be used when the music expression has to start
  off-beat, with a partial swing cycle.

**Note:** As with the articulate script, all swing commands are also rendered in the engraved output, which results in irregular note spacing. This can be avoided by using them only in a `\score` block dedicated
to MIDI output, rather than to printed music.

Additional help and information is included in the script file:
see ly/swing.ly.

#### See also

Learning Manual:
Other sources of information.

Notation Reference:
Rhythms.

Installed Files:
ly/swing.ly.

#### Known issues and warnings
- `\repeat` constructs in music (even `\repeat unfold`) are not taken
  into consideration when determining note timing. This will lead
  to problems unless the durations of all repeated parts are
  integer multiples of the swing cycle duration.
- These functions are oblivious to time signatures and measures.
  That is why offsets need to be supplied by using
  `\applySwingWithOffset` if music starts off-beat.
- Grace notes are ignored and simply left unaffected; so are tuplets.

[Top][Contents][Index]
