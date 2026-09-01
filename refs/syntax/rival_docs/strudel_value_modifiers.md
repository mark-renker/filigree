# strudel_value_modifiers
Source: https://strudel.cc/functions/value-modifiers/
Fetched: 2026-08-30

# Control Parameters

Besides functions that control time, we saw earlier that functions like `note` and `cutoff` control different parameters (short params) of an event.
Let’s now look more closely at how these `param(eter) functions` work.

# Parameter Functions

A very powerful feature of tidal patterns is that each parameter can be controlled independently:

In this example, the parameters `note`, `cutoff`, `gain` and `s` are controlled independently by either patterns or plain values (numbers / text).
After pressing play, we can observe the time and parameter values of each event (hap) in the output created by `.log()`.

## Plain vs Parameterized Values

Patterns that are not wrapped inside a param function will contain unlabeled `plain values`:

This will not generate any sound output, because Strudel could only guess which param is meant by these letters.

Now compare that to the version wrapped in `note`:

Now it is clear that these letters are meant to be played as notes.
Under the hood, the `note` function (as well as all other param functions)
will wrap each plain value in an object. If the note function did not exist, we would need to write:

This will have the same output, though it is rather unwieldy to read and write.

## Wrapping Parameter Functions

To avoid too much nesting, param functions can also be chained like this:

This is equivalent to `note(cat('c','e','g')).log()`.

You can use this with any function that declares a type (like `n`, `s`, `note`, `freq` etc), just make sure to leave the parens empty!

## Plain Value Modification

Patterns of plain values can be modified with any of the following operators:

Here, the add function modifies the numbers on the left.
Again, there is no output because these numbers have no meaning without a param.

## Param Value Modification

To modify a parameter value, you can either:

- Use the operator on the plain value pattern, inside the param function:
- Similarly, use the operator on the plain value pattern and wrap it later:
- Specify which param should be modified inside the operator function:

Remember the execution of the chained functions goes from left to right.

# Operators

This group of functions allows to modify the value of events.

## add

Assumes a pattern of numbers. Adds the given number to each item in the pattern.

```
// Here, the triad 0, 2, 4 is shifted by different amounts
n("0 2 4".add("<0 3 4 0>")).scale("C:major")
// Without add, the equivalent would be:
// n("<[0 2 4] [3 5 7] [4 6 8] [0 2 4]>").scale("C:major")
```

```
// You can also use add with notes:
note("c3 e3 g3".add("<0 5 7 0>"))
// Behind the scenes, the notes are converted to midi numbers:
// note("48 52 55".add("<0 5 7 0>"))
```

## sub

Like add, but the given numbers are subtracted.

```
n("0 2 4".sub("<0 1 2 3>")).scale("C4:minor")
// See add for more information.
```

## mul

Multiplies each number by the given factor.

```
"<1 1.5 [1.66, <2 2.33>]>*4".mul(150).freq()
```

## div

Divides each number by the given factor.

## round

Assumes a numerical pattern. Returns a new pattern with all values rounded
to the nearest integer.

```
n("0.5 1.5 2.5".round()).scale("C:major")
```

## floor

Assumes a numerical pattern. Returns a new pattern with all values set to
their mathematical floor. E.g. `3.7` replaced with to `3`, and `-4.2`
replaced with `-5`.

```
note("42 42.1 42.5 43".floor())
```

## ceil

Assumes a numerical pattern. Returns a new pattern with all values set to
their mathematical ceiling. E.g. `3.2` replaced with `4`, and `-4.2`
replaced with `-4`.

```
note("42 42.1 42.5 43".ceil())
```

## range

Assumes a numerical pattern, containing unipolar values in the range 0 .. 1.
Returns a new pattern with values scaled to the given min/max range.
Most useful in combination with continuous patterns.

```
s("[bd sd]*2,hh*8")
.cutoff(sine.range(500,4000))
```

## rangex

Assumes a numerical pattern, containing unipolar values in the range 0 .. 1
Returns a new pattern with values scaled to the given min/max range,
following an exponential curve.

```
s("[bd sd]*2,hh*8")
.cutoff(sine.rangex(500,4000))
```

## range2

Assumes a numerical pattern, containing bipolar values in the range -1 .. 1
Returns a new pattern with values scaled to the given min/max range.

```
s("[bd sd]*2,hh*8")
.cutoff(sine2.range2(500,4000))
```

## ratio

Allows dividing numbers via list notation using ":".
Returns a new pattern with just numbers.

```
ratio("1, 5:4, 3:2").mul(110)
.freq().s("piano")
```

## as

Sets properties in a batch.

- mapping (String|Array): the control names that are set

```
"c:.5 a:1 f:.25 e:.8".as("note:clip")
```

```
"{0@2 0.25 0 0.5 .3 .5}%8".as("begin").s("sax_vib").clip(1)
```

# Custom Parameters

You can also create your own parameters:

Multiple params can also be created in a more consice way, using `createParams`:

Note that these params will not do anything until you give them meaning in your custom output!

From modifying parameters we transition to the concept of Signals.