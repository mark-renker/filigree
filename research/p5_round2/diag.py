#!/usr/bin/env python3
"""Diagnose the run-level structure of the residuals (mine vs reference)."""
from __future__ import annotations
import os
import sys
import warnings
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE, os.path.join(ROOT, "src")]
import p5b_stats as S            # noqa: E402
import tune                      # noqa: E402
from filigree import feel as F    # noqa: E402
from filigree.feel import FeelSpec, apply_feel  # noqa: E402


def diag(recs, label):
    cl = S.clusters(recs)
    ons = np.array([c[0].start for c in cl])
    runs = S._runs(ons)
    if not runs:
        print(f"{label:44s} no runs")
        return
    allres, sds, lens, tats = [], [], [], []
    for a, b in runs:
        seg = ons[a:b + 1]
        k = np.arange(seg.size, dtype=float)
        sl, ic = np.polyfit(k, seg, 1)
        r = (seg - (sl * k + ic)) * 1000.0
        allres.append(r)
        sds.append(float(r.std()))
        lens.append(seg.size)
        tats.append(sl * 1000.0)
    r = np.concatenate(allres)
    z = np.concatenate([(x - x.mean()) / (x.std() + 1e-9) for x in allres if x.std() > 0])
    sds = np.array(sds)
    tt = float(np.median(tats))
    print(f"{label:44s} runs={len(runs):4d} cov={sum(lens)/len(ons):.2f} tat={tt:6.1f} "
          f"|res|={np.median(np.abs(r)):5.2f} "
          f"sdrun/tat med={np.median(sds)/tt:.3f} q3={np.percentile(sds, 75)/tt:.3f} "
          f"p95={np.percentile(sds, 95)/tt:.3f} p95/med={np.percentile(sds, 95)/np.median(sds):4.1f} "
          f"kurt={S.excess_kurtosis(r.tolist()):+6.2f} kw={S.excess_kurtosis(z.tolist()):+5.2f}")


if __name__ == "__main__":
    for fn in sorted(os.listdir(os.path.join(ROOT, "refs/midi"))):
        if fn.endswith(".mid"):
            diag(S.load_midi(os.path.join(ROOT, "refs/midi", fn)), "REF " + fn[:38])
    for over in sys.argv[1:]:
        base, _, rest = over.partition(":")
        params = dict(F.PRESETS[base])
        for kv in rest.split(","):
            if kv:
                k, _, v = kv.partition("=")
                params[k] = float(v)
        ns = tune.grid(2048)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            apply_feel(ns, FeelSpec(**params), 120.0, seed=42)
        diag(S.from_beats(ns, 120.0), "MINE " + over[:38])
