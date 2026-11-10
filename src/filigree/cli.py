"""filigree — command line interface.

    filigree render piece.fil [-o piece.mid]
    filigree play   piece.fil [--port "IAC Driver Bus 1"] [--loop]
    filigree watch  piece.fil [--port ...]
    filigree explain piece.fil
    filigree json   piece.fil [-o piece.json]
    filigree serve  [--port 8787] [--open]
    filigree ports
    filigree new    piece.fil
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from . import __version__, compile_source
from .errors import FiligreeError

TEMPLATE = """# {name} — Filigree
@tempo 84
@key C minor
@seed 7

gesture cry = bend(0 -> -0.6st @ 35% -> 0, shape: ease)

stave lead {{
  harm              | i9       | VI^7     | iv11     | V7alt     |
  notes!gesture=cry | 0 . 2 3  | 4 - - 2  | 0 3 . 5  | 7 - 6 -   |
  bend              | ___/^^^^ | ^^\\_____ |          | __/\\___>3 |
  press             | /^^^\\___ | -----^^^ | __/^^^\\_ | ^^^^\\___  |
  timbre            | ---^^^-- |          |          |           |
}}
"""


PC_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def pitch_name(midi: float) -> str:
    """MIDI number (may be fractional) -> readable name, e.g. 66 -> 'F#4'."""
    i = int(round(midi))
    return f"{PC_NAMES[i % 12]}{i // 12 - 1}"


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _load(path: str, lenient: bool = False):
    # Leniency starts at the parser: a typo'd chord symbol or an unknown glyph
    # fails while parsing, long before the resolver runs (lead ruling, round 3).
    return compile_source(_read(path), path, lenient=lenient)


def _report(score) -> None:
    for w in score.warnings:
        print(f"  {w}", file=sys.stderr)


def cmd_render(args) -> int:
    score = _load(args.file, getattr(args, "lenient", False))
    out = args.output or os.path.splitext(args.file)[0] + ".mid"
    from .mpe import MpeOptions, write_midi

    write_midi(score, out, MpeOptions(
        bend_range=score.bend_range, ppq=score.ppq, grid_ms=score.grid_ms))
    n = len(score.notes)
    print(f"wrote {out}  ({n} notes, {score.duration_beats:.2f} beats, "
          f"{len(score.staves)} stave(s), MPE lower zone)")
    _report(score)
    return 0


def cmd_json(args) -> int:
    score = _load(args.file, getattr(args, "lenient", False))
    payload = json.dumps(score.to_json(), indent=None if args.compact else 2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(payload)
        print(f"wrote {args.output}")
    else:
        print(payload)
    return 0


def cmd_play(args) -> int:
    score = _load(args.file)
    from .realtime import play

    _report(score)
    play(score, args.port, loop=args.loop)
    return 0


def cmd_watch(args) -> int:
    from .realtime import play

    last = None
    print(f"watching {args.file} — Ctrl-C to stop")
    try:
        while True:
            try:
                mtime = os.path.getmtime(args.file)
            except OSError:
                time.sleep(0.3)
                continue
            if mtime != last:
                last = mtime
                try:
                    score = compile_source(_read(args.file), args.file)
                except FiligreeError as exc:
                    print(f"\n{exc}", file=sys.stderr)
                    continue
                print(f"\n[{time.strftime('%H:%M:%S')}] {len(score.notes)} notes")
                _report(score)
                try:
                    play(score, args.port)
                except Exception as exc:
                    print(f"  playback unavailable: {exc}", file=sys.stderr)
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\nbye")
    return 0


def cmd_explain(args) -> int:
    score = _load(args.file, getattr(args, "lenient", False))
    print(f"{score.title or args.file}   {score.tempo:g} bpm  "
          f"{score.meter[0]}/{score.meter[1]}  "
          f"key={PC_NAMES[score.key[0] % 12]} {score.key[1]}  "
          f"mpe-bend=±{score.bend_range:g}st  seed={score.seed}")
    for st in score.staves:
        print(f"\nstave {st.name!r}  ({len(st.notes)} notes)")
        if st.chords:
            print("  harmony:")
            for c in st.chords:
                pcs = " ".join(PC_NAMES[p % 12] for p in c.pitch_classes)
                gts = " ".join(PC_NAMES[p % 12] for p in c.guide_tones)
                voiced = " ".join(pitch_name(p) for p in c.pitches)
                print(f"    bar{c.start / 4 + 1:>5.2f}  {c.symbol:<10} {c.quality:<10}"
                      f" [{pcs}]  guide[{gts}]  voiced[{voiced}]")
        print("  notes:")
        print(f"    {'beat':>7} {'dur':>6} {'pitch':>5} {'name':<4} {'vel':>4} "
              f"{'voice':<8} lanes  (bend shows where the note lands)")
        for n in st.notes:
            lanes = []
            for lane, cur in sorted(n.curves.items()):
                real = cur.real_points()
                if not real:
                    continue
                vals = [v for _, v in real]
                gaps = len(cur.spans())
                tag = f"{lane}[{min(vals):+.2f}..{max(vals):+.2f}×{len(vals)}"
                tag += f" {gaps}span]" if gaps > 1 else "]"
                if lane == "bend":
                    # where the drawn bend actually leaves the note sounding
                    tag += (f"→{pitch_name(n.pitch + real[-1][1] + n.detune)}"
                            f"({real[-1][1]:+.2f}st)")
                lanes.append(tag)
            print(f"    {n.start:>7.3f} {n.dur:>6.3f} {n.pitch:>5} "
                  f"{pitch_name(n.pitch):<4} {n.velocity:>4} "
                  f"{(n.voice or '-'):<8} {' '.join(lanes)}")
    _report(score)
    return 0


def cmd_serve(args) -> int:
    from .server import serve

    serve(args.port, args.web, args.open)
    return 0


def cmd_ports(args) -> int:
    try:
        from .realtime import list_ports

        ports = list_ports()
    except Exception as exc:
        print(f"realtime MIDI unavailable: {exc}", file=sys.stderr)
        return 1
    if not ports:
        print("no MIDI output ports found. On macOS enable the IAC Driver in\n"
              "Audio MIDI Setup → Window → Show MIDI Studio → IAC Driver → "
              "'Device is online'.")
    for p in ports:
        print(p)
    return 0


def cmd_new(args) -> int:
    if os.path.exists(args.file) and not args.force:
        print(f"{args.file} exists (use --force)", file=sys.stderr)
        return 1
    name = os.path.splitext(os.path.basename(args.file))[0]
    with open(args.file, "w", encoding="utf-8") as fh:
        fh.write(TEMPLATE.format(name=name))
    print(f"wrote {args.file}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="filigree", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"filigree {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    lenient_help = ("downgrade unknown chord symbols from errors to warnings and "
                    "sustain the previous chord (for live sessions)")

    p = sub.add_parser("render", help="compile to a .mid file")
    p.add_argument("file")
    p.add_argument("-o", "--output")
    p.add_argument("--lenient", action="store_true", help=lenient_help)
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("json", help="compile to JSON (the playground schema)")
    p.add_argument("file")
    p.add_argument("-o", "--output")
    p.add_argument("--compact", action="store_true")
    p.add_argument("--lenient", action="store_true", help=lenient_help)
    p.set_defaults(fn=cmd_json)

    p = sub.add_parser("play", help="play live to a MIDI port")
    p.add_argument("file")
    p.add_argument("--port")
    p.add_argument("--loop", action="store_true")
    p.set_defaults(fn=cmd_play)

    p = sub.add_parser("watch", help="recompile and replay on save")
    p.add_argument("file")
    p.add_argument("--port")
    p.set_defaults(fn=cmd_watch)

    p = sub.add_parser("explain", help="print resolved harmony, voicings and gestures")
    p.add_argument("file")
    p.add_argument("--lenient", action="store_true", help=lenient_help)
    p.set_defaults(fn=cmd_explain)

    p = sub.add_parser("serve", help="run the browser playground")
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--web")
    p.add_argument("--open", action="store_true")
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser("ports", help="list MIDI output ports")
    p.set_defaults(fn=cmd_ports)

    p = sub.add_parser("new", help="write a starter .fil file")
    p.add_argument("file")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_new)

    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except FiligreeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
