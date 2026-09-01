# sonicpi_chord_degree
Source: https://sunderb.me/sonic-pi-docs-test/en/reference/lang/chord_degree.html
Fetched: 2026-08-30

chord_degree degree (symbol_or_number), tonic (symbol), scale (symbol), number_of_notes (number)

In music we build chords from scales. For example, a C major chord is made by taking the 1st, 3rd and 5th notes of the C major scale (C, E and G). If you do this on a piano you might notice that you play one, skip one, play one, skip one etc. If we use the same spacing and start from the second note in C major (which is a D), we get a D minor chord which is the 2nd, 4th and 6th notes in C major (D, F and A). We can move this pattern all the way up or down the scale to get different types of chords.

`chord_degree` is a helper method that returns a ring of midi note numbers when given a degree (starting point in a scale) which is a symbol

`:i`,

`:ii`,

`:iii`,

`:iv`,

`:v`,

`:vi`,

`:vii` or a number

`1`-

`7`. The second argument is the tonic note of the scale, the third argument is the scale type and finally the fourth argument is number of notes to stack up in the chord. If we choose 4 notes from degree

`:i` of the C major scale, we take the 1st, 3rd, 5th and 7th notes of the scale to get a C major 7 chord.

Introduced in v2.1

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
|# Example 6|
|||
|# Example 7|
|||
|# Example 8|
|||

