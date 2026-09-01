#!/usr/bin/env python3
"""Small grid search over the timing parameters against the reference IQRs."""
from __future__ import annotations
import itertools
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE]
import tune                                   # noqa: E402
from filigree import feel as F                # noqa: E402

# median [q1, q3] from refs/specs/feel_truth.md
T = {"absres": (8.32, 6.90, 10.30), "rt": (0.076, 0.071, 0.084),
     "kurt": (5.64, 2.87, 7.79), "lag1": (0.55, 0.45, 0.68),
     "vsd": (11.86, 10.73, 14.53), "vr1": (0.452, 0.385, 0.538)}


def score(r):
    s = 0.0
    for k, (med, lo, hi) in T.items():
        v = r[k]
        half = (hi - lo) / 2.0
        if v < lo:
            s += ((lo - v) / half) ** 2 + 1.0
        elif v > hi:
            s += ((v - hi) / half) ** 2 + 1.0
        else:
            s += 0.15 * abs(v - med) / half
    return s


def main(base="loose", n=1024):
    grid = {
        "timing_ms": [9, 11],
        "timing_drift_ms": [18, 22, 26, 30],
        "timing_drift_span": [4, 5],
        "timing_swell": [1.2, 1.4, 1.6],
    }
    keys = list(grid)
    rows = []
    for combo in itertools.product(*(grid[k] for k in keys)):
        params = dict(F.PRESETS[base])
        params.update(dict(zip(keys, combo)))
        r = tune.run_many(params, n=n)
        rows.append((score(r), dict(zip(keys, combo)), r))
    rows.sort(key=lambda x: x[0])
    for sc, combo, r in rows[:10]:
        print(f"{sc:6.3f} " + " ".join(f"{k}={v}" for k, v in combo.items()))
        tune.show("   ->", r)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "loose",
         int(sys.argv[2]) if len(sys.argv) > 2 else 1024)
