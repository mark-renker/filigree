# sonicpi_control
Source: https://sunderb.me/sonic-pi-docs-test/en/reference/lang/control.html
Fetched: 2026-08-30

control node (synth_node)

Control a running synth node by passing new parameters to it. A synth node represents a running synth and can be obtained by assigning the return value of a call to play or sample or by specifying a parameter to the do/end block of an FX. You may modify any of the parameters you can set when triggering the synth, sample or FX. See documentation for opt details. If the synth to control is a chord, then control will change all the notes of that chord group at once to a new target set of notes - see example. Also, you may use the on: opt to conditionally trigger the control - see the docs for the

`synth` and

`sample` fns for more information.

If no synth to control is specified, then the last synth triggered by the current (or parent) thread will be controlled - see example below.

Introduced in v2.0

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
|# Example 9|
|||
|# Example 10|
|||
|# Example 11|
|||

