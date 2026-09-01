"""Adversarial P4 (MPE renderer) probes — critic-owned, hostile by design.

Builds ir.Score objects directly (no parser involved), renders each with
filigree.mpe.write_midi, then checks every rendered file with the independent
byte-level checker in tools/critic_smf_check.py.

Run:  python tests/critic_p4_mpe.py
Output: a table plus a per-case defect list; artifacts in /tmp/critic_p4/.
"""

from __future__ import annotations

import json
import math
import os
import sys
import traceback

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
sys.path.insert(0, os.path.join(HERE, "tools"))

from filigree import ir, mpe            # noqa: E402
import critic_smf_check as C            # noqa: E402

OUT = "/tmp/critic_p4"
os.makedirs(OUT, exist_ok=True)


def curve(lane, pts):
    return ir.Curve(lane=lane, points=[(float(t), float(v)) for t, v in pts])


def score(notes, **kw):
    s = ir.Score(**kw)
    st = ir.StaveIR(name="s1", notes=notes)
    s.staves.append(st)
    for i, n in enumerate(notes):
        n.id = i + 1
    return s


def vib(start, dur, rate=6.0, depth=0.5, tempo=120.0, step=0.01):
    pts = []
    t = 0.0
    while t <= dur + 1e-9:
        pts.append((start + t, depth * math.sin(2 * math.pi * rate * t * 60.0 / tempo)))
        t += step
    return curve(ir.BEND, pts)


# --------------------------------------------------------------------------- #
# cases
# --------------------------------------------------------------------------- #

def case_exhaustion():
    """20 simultaneous notes: only 15 member channels exist."""
    return score([ir.Note(start=0.0, dur=4.0, pitch=48 + i, velocity=90,
                          curves={ir.BEND: vib(0.0, 4.0, depth=0.3)})
                  for i in range(20)])


def case_zero_length():
    return score([ir.Note(start=0.0, dur=0.0, pitch=60),
                  ir.Note(start=1.0, dur=1e-9, pitch=62),
                  ir.Note(start=2.0, dur=1.0, pitch=64)])


def case_touching_same_channel():
    """Note ends exactly where the next begins, with ONE member channel."""
    return score([ir.Note(start=0.0, dur=1.0, pitch=60,
                          curves={ir.BEND: vib(0.0, 1.0)}),
                  ir.Note(start=1.0, dur=1.0, pitch=60,
                          curves={ir.BEND: vib(1.0, 1.0)})])


def case_nan():
    pts = [(0.0, 0.0), (0.25, float("nan")), (0.5, 1.0), (0.75, float("nan")), (1.0, -1.0)]
    return score([ir.Note(start=0.0, dur=1.0, pitch=60,
                          curves={ir.BEND: curve(ir.BEND, pts),
                                  ir.PRESS: curve(ir.PRESS, [(0.0, float("nan")), (1.0, 1.0)]),
                                  ir.TIMBRE: curve(ir.TIMBRE, [(0.0, 0.5), (0.5, float("nan"))])})])


def case_inf():
    return score([ir.Note(start=0.0, dur=1.0, pitch=60,
                          curves={ir.BEND: curve(ir.BEND, [(0.0, 0.0), (0.5, float("inf")),
                                                           (1.0, float("-inf"))])})])


def case_past_end():
    """Curve points run 3 beats past a 1-beat note, and 1 beat before it."""
    return score([ir.Note(start=1.0, dur=1.0, pitch=60,
                          curves={ir.BEND: curve(ir.BEND, [(0.0, -2.0), (1.0, 0.0),
                                                           (2.0, 1.0), (4.0, 2.0)]),
                                  ir.PRESS: curve(ir.PRESS, [(0.0, 0.0), (4.0, 1.0)])})])


def case_beyond_range():
    """Bend to ±60 st with a ±12 st member range: must clamp, must not wrap."""
    return score([ir.Note(start=0.0, dur=2.0, pitch=60,
                          curves={ir.BEND: curve(ir.BEND, [(0.0, -60.0), (1.0, 0.0), (2.0, 60.0)])})],
                 bend_range=12.0)


def case_dense_1000():
    notes = []
    for i in range(1000):
        notes.append(ir.Note(start=i * 0.05, dur=0.2, pitch=48 + (i % 24), velocity=80,
                             curves={ir.BEND: vib(i * 0.05, 0.2, depth=0.2)}))
    return score(notes)


def case_long_note():
    return score([ir.Note(start=0.0, dur=200.0, pitch=60,
                          curves={ir.BEND: vib(0.0, 200.0, rate=5.0, depth=0.5, step=0.02)})])


def case_identical_pitches():
    return score([ir.Note(start=0.0, dur=2.0, pitch=60,
                          curves={ir.BEND: vib(0.0, 2.0, depth=0.1)}) for _ in range(4)])


def case_no_curves():
    return score([ir.Note(start=i * 0.5, dur=0.5, pitch=60 + i) for i in range(8)])


def case_triple_lane_fast():
    """All three dimensions wiggling fast on one channel — density stress."""
    dur = 4.0
    bend = vib(0.0, dur, rate=9.0, depth=1.0, step=0.005)
    pr, ti = [], []
    t = 0.0
    while t <= dur:
        pr.append((t, 0.5 + 0.5 * math.sin(2 * math.pi * 11 * t * 0.5)))
        ti.append((t, 0.5 + 0.5 * math.sin(2 * math.pi * 13 * t * 0.5)))
        t += 0.005
    return score([ir.Note(start=0.0, dur=dur, pitch=60,
                          curves={ir.BEND: bend,
                                  ir.PRESS: curve(ir.PRESS, pr),
                                  ir.TIMBRE: curve(ir.TIMBRE, ti)})])


CASES = [
    ("exhaustion", case_exhaustion, {}),
    ("zero_length", case_zero_length, {}),
    ("touching_1ch", case_touching_same_channel, {"members": (1,)}),
    ("nan", case_nan, {}),
    ("inf", case_inf, {}),
    ("curve_past_end", case_past_end, {}),
    ("beyond_range", case_beyond_range, {}),
    ("dense_1000", case_dense_1000, {}),
    ("long_200beats", case_long_note, {}),
    ("identical_pitch", case_identical_pitches, {}),
    ("no_curves", case_no_curves, {}),
    ("triple_lane_fast", case_triple_lane_fast, {}),
]


# --------------------------------------------------------------------------- #
# independent raw-frame count (for the thinning ratio)
# --------------------------------------------------------------------------- #

def raw_frame_count(s: ir.Score, opts) -> int:
    spb = 60.0 / s.tempo
    pitch_grid = (opts.pitch_grid_ms / 1000.0) / spb
    slow_grid = (opts.grid_ms / 1000.0) / spb
    total = 0
    for n in s.notes:
        if n.dur <= 0:
            continue
        for lane, g in ((ir.BEND, pitch_grid), (ir.PRESS, slow_grid),
                        (ir.TIMBRE, slow_grid), (ir.AMP, slow_grid), (ir.PAN, slow_grid)):
            c = n.curves.get(lane)
            if not c or not c.points:
                continue
            total += max(1, int(math.floor((n.dur - 1e-12) / g)) + 1)
    return total


def expect_for(s: ir.Score, opts) -> dict:
    return {
        "bend_range": opts.bend_range,
        "raw_frames": raw_frame_count(s, opts),
        "input_notes": len(s.notes),
        "notes": [
            {"start": n.start, "dur": n.dur, "pitch": n.pitch, "detune": n.detune,
             "points": [[t, v] for t, v in n.curves[ir.BEND].points]
             if ir.BEND in n.curves else []}
            for n in s.notes if n.dur > 0
        ],
    }


def main() -> int:
    reps = []
    for name, fn, optkw in CASES:
        path = os.path.join(OUT, f"{name}.mid")
        try:
            s = fn()
            opts = mpe.MpeOptions(bend_range=s.bend_range, ppq=s.ppq,
                                 grid_ms=s.grid_ms, pitch_grid_ms=s.grid_ms / 2.0, **optkw)
            mpe.write_midi(s, path, opts)
        except Exception:
            print(f"\n### {name}: RENDER CRASH")
            traceback.print_exc()
            continue
        exp = expect_for(s, opts)
        with open(os.path.join(OUT, f"{name}.expect.json"), "w") as fh:
            json.dump(exp, fh)
        r = C.check_file(path, exp)
        r.path = name
        reps.append(r)
        if s.warnings:
            print(f"[{name}] score warnings: {s.warnings}")
    print()
    C.print_table(reps)
    for r in reps:
        d = r.defects()
        print(f"\n=== {r.path} ===")
        for x in d:
            print("   DEFECT:", x)
        ok, msg = C.mido_crosscheck(os.path.join(OUT, f"{r.path}.mid"))
        print(f"   mido cross-check: {'OK' if ok else 'MISMATCH'} — {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
