# sonicpi_midi_pitch_bend
Source: https://sunderb.me/sonic-pi-docs-test/en/reference/lang/midi_pitch_bend.html
Fetched: 2026-08-30

midi_pitch_bend delta (float01)

Sends a MIDI pitch bend message to

*all* connected devices on *all* channels. Use the

`port:` and

`channel:` opts to restrict which MIDI ports and channels are used.

Delta value is between 0 and 1 with 0.5 representing no pitch bend, 1 max pitch bend and 0 minimum pitch bend.

Typical MIDI values such as note or cc are represented with 7 bit numbers which translates to the range 0-127. This makes sense for keyboards which have at most 88 keys. However, it translates to a poor resolution when working with pitch bend. Therefore, pitch bend is unlike most MIDI values in that it has a much greater range: 0 - 16383 (by virtue of being represented by 14 bits).

`delta_midi:` opt.

`delta_midi:` opt no pitch bend is the value 8192

MIDI 1.0 Specification - Channel Voice Messages - Pitch Bend Change

Introduced in v3.0

|# Example 1|
|--|
|||
|# Example 2|
|||
|# Example 3|
|||
|# Example 4|
|||
|# Example 5|
|||

