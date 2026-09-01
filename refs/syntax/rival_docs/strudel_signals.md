# strudel_signals
Source: https://strudel.cc/learn/signals/
Fetched: 2026-08-30

# Continuous Signals

Signals are patterns with continuous values, meaning they have theoretically infinite steps.
They can provide streams of numbers that can be sampled at discrete points in time.

## saw

A sawtooth signal between 0 and 1.

```
note("<c3 [eb3,g3] g2 [g3,bb3]>*8")
.clip(saw.slow(2))
```

```
n(saw.range(0,8).segment(8))
.scale('C major')
```

## sine

A sine signal between 0 and 1.

```
n(sine.segment(16).range(0,15))
.scale("C:minor")
```

## cosine

A cosine signal between 0 and 1.

```
n(stack(sine,cosine).segment(16).range(0,15))
.scale("C:minor")
```

## tri

A triangle signal between 0 and 1.

```
n(tri.segment(8).range(0,7)).scale("C:minor")
```

## square

A square signal between 0 and 1.

```
n(square.segment(4).range(0,7)).scale("C:minor")
```

## rand

A continuous pattern of random numbers, between 0 and 1.

```
// randomly change the cutoff
s("bd*4,hh*8").cutoff(rand.range(500,8000))
```

## Ranges from -1 to 1

There is also `saw2`, `sine2`, `cosine2`, `tri2`, `square2` and `rand2` which have a range from -1 to 1!

## perlin

Generates a continuous pattern of perlin noise, in the range 0..1.

```
// randomly change the cutoff
s("bd*4,hh*8").cutoff(perlin.range(500,8000))
```

## irand

A continuous pattern of random integers, between 0 and n-1.

- n (number): max value (exclusive)

```
// randomly select scale notes from 0 - 7 (= C to C)
n(irand(8)).struct("x x*2 x x*3").scale("C:minor")
```

## brand

A continuous pattern of 0 or 1 (binary random)

```
s("hh*10").pan(brand)
```

## brandBy

A continuous pattern of 0 or 1 (binary random), with a probability for the value being 1

- probability (number): a number between 0 and 1

```
s("hh*10").pan(brandBy(0.2))
```

## mouseX

The mouse's x position value ranges from 0 to 1.

```
n(mousex.segment(4).range(0,7)).scale("C:minor")
```

## mouseY

The mouse's y position value ranges from 0 to 1.

```
n(mousey.segment(4).range(0,7)).scale("C:minor")
```

Next up: Random Modifiers
