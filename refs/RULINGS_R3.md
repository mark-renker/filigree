# Lead rulings on the round-3 SPEC amendment requests

Source of the requests: `NOTES_R3.md` §3 (R3-A1 … R3-A9). The round-3 fixer deliberately
did not edit the SPEC; these are my decisions on each request. Anything marked ACCEPTED must
appear in `docs/SPEC.md`. Anything marked REJECTED must not, and the reason is recorded here
so the next reader does not refile it.

## R3-A1 — define "slot"/"item" once, in anchors, not characters. **ACCEPTED as proposed.**
Adopt the proposed §3.1 wording, with one correction: whitespace inside a curve bar is a
**separator only** and produces no anchor at all (that was the round-3 lead ruling; a space
used to emit an empty slot, which made a lane written under 8 notes count 15 anchors and warn
about its own alignment). Write `.` for "no data here". Delete the old L187 character sentence.

## R3-A2 — `-` means three things. **ACCEPTED, documentation only.**
Do not retire `-` from curve lanes; that is a breaking change and the glyph is used throughout
the shipped examples. State the collision explicitly in §7 and document `x` as the spelling for
"hold the running value", with the sentence: *`-` never holds in a curve lane; it is a level.*

## R3-A3 — per-lane glyph table. **ACCEPTED.**
§7 gets a table with one row per lane (`bend`, `press`, `timbre`, `amp`, `pan`, `cc*`) and
columns min (`v`/`V`), rest (`_`), centre (`-`), max (`^`), so a reader can see directly that
`_` and `-` coincide on `bend` but not on `timbre`, and that `_` and `v` coincide on `press`.
Values must be read out of the implementation, not guessed — check `src/filigree/gesture.py`
and `src/filigree/resolve.py` and state the real numbers.

## R3-A4 — absent vs empty vs held, and the note-on reset. **ACCEPTED.**
Add the subsection. The note-on rule is normative and must be stated plainly: at note-on every
expression lane the bar does not write returns to its rest value.

## R3-A5 — gesture attachment precedence. **ACCEPTED.**
Document the list and say that attachments **compose**, with the later-listed winning on a
direct conflict. Verify the order against the implementation before writing it down; if the
code disagrees with the order in the request, the code is the truth and the SPEC states what
the code does.

## R3-A6 — chord-spelling disambiguation. **ACCEPTED.**
State the rule, and note that the discrimination happens before any quality suffix is parsed.
Correct one detail in the request: a pitch set is written `{0 3 7}` with braces, not `[...]`.
Also record that an unrecognised symbol is a hard error and what `--lenient` substitutes
(§12 already covers this after the round-3 leniency work — cross-reference, do not duplicate).

## R3-A7 — `0 -2` vs `0 - 2`. **ACCEPTED as documentation; the proposed warning is REJECTED.**
Document the trap in §5 with that exact pair and recommend writing negative degrees unspaced.
Do not add a warning: it would fire on legal existing files, and a bar that mixes both readings
is not in itself a mistake. Revisit only if a real file is found where the two readings are
genuinely ambiguous to the parser rather than to the reader.

## R3-A8 — postfix modifier order. **ACCEPTED.**
State the fixed order and that any other order is an error. Again: read the order out of
`src/filigree/parse.py` and document what the parser actually accepts. If the parser is more
permissive than the request assumes, say so honestly rather than documenting a stricter
language than the one that ships.

## R3-A9 — small confirmed behaviours. **ACCEPTED (a)-(e).**
All five go in. (a) belongs in §7 next to `>`; (b) in the §7 glyph table's notes; (c) in §5;
(d) in §8; (e) §4 gets the list of recognised lane options, read from the implementation.

## Standing requirement
`tests/test_docs.py` compiles every fenced Filigree block in `README.md` and `docs/*.md` and
requires **zero warnings**. Any example added while applying these amendments must satisfy it,
so run `python -m pytest -q tests/test_docs.py` after every edit. Do not weaken that test to
accommodate an example; fix the example.

---

## Corrections discovered while applying these rulings (documentation editor, R3 SPEC pass)

Recorded here so the next reader does not re-file the same wrong assumption. In every case the
SPEC now documents the implementation, not the request.

1. **R3-A3 — `_` and `-` also coincide on `timbre`.** The ruling says they coincide on `bend`
   "but not on `timbre`". They do coincide on `timbre`, and on `amp` and `pan`: those lanes rest
   at `0.5` (`gesture.py` `LANE_RESTS`) and their centre is the midpoint of `0..1`, i.e. also
   `0.5` (`GestureCtx.center`, `gesture.py:718`). `_` and `-` differ **only** on `press` and
   `cc<n>`, whose rest is `0` and whose centre is `0.5`.
   Evidence: `PYTHONPATH=src python -c` over `lane_rest_for`/`GestureCtx.center` for every lane —
   bend rest 0.0 centre 0.0; press 0.0 / 0.5; timbre 0.5 / 0.5; amp 0.5 / 0.5; pan 0.5 / 0.5;
   cc11 0.0 / 0.5.

2. **R3-A4 — the note-on reset is not universal.** Only the three MPE-mandated preamble
   dimensions are reset at every note-on (`mpe.py:1048-1057`): pitch bend (to the note's value
   or the static detune, i.e. `0st`), CC74 (to `DEFAULT_TIMBRE` 64, the `0.5` rest) and channel
   pressure (always 0, the `press` rest). `amp` (CC11), `pan` (CC10) and `cc<n>` have no
   preamble: where the bar writes nothing, nothing is emitted and the channel keeps its previous
   value. Evidence: rendering a two-bar stave that writes `press`/`pan`/`cc1`/`timbre` in bar 1
   only, the bar-2 note-on carries bend, CC74 and pressure events but no CC10 and no CC1.

3. **R3-A5 — attachments override, they do not compose, and the request's order is inverted.**
   `resolve.py:_note_curves` (§around 840-865) builds an ordered source list per lane and
   `_sample_lane` (`resolve.py:993`) fills only the NaN gaps left by higher-priority sources:
   `fill = np.isnan(values) & ~np.isnan(v)`. So the **earlier**-listed source wins a conflict —
   glyphs, then note-level `!gesture`, then voice-scoped lane option, then unscoped lane option,
   then the stave header — and nothing is summed. Verified: with `notes!gesture=down | 0!up |`
   the note follows `up` (press 0.0 at note-on), with the lane option alone it follows `down`
   (1.0); `gesture mid` in the stave header loses to `notes!gesture=down`.
   Two further errors in the request: `press!gesture=dig` on a **curve** lane attaches nothing
   (`_stave_attached` reads note-bearing and voices lanes only) and is not warned about; and
   there is no `@gesture` directive at all (`parse.py:48` `DIRECTIVES`) — `@gesture up` is a hard
   error "unknown directive '@gesture'".

4. **R3-A8 — the parser imposes no postfix order.** `_split_decorations` (`parse.py:1084-1100`)
   peels `!name` / `:v<n>` / `%<n>` / `'` / `,` / `?<n>` off the end of a token in **any** order
   and `_apply_decorations` applies them left to right, so `0!scoop:v90'` and `0':v90!scoop` are
   the same note and neither is an error. The SPEC therefore states the permissive truth instead
   of the requested "fixed order, anything else is an error". Also: the request's example
   `0!scoop.5~3` does not parse at all — there is no duration or dotted-duration modifier
   (timing is slot-inferred) and `~` is not a postfix ornament; the parser rejects `0!scoop~3`
   as "not a note token". What *is* ordered is the prefix side: octave marks, then accidental,
   then degree (`^#3` parses, `#^3` is a hard error).
