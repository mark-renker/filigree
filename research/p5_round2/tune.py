#!/usr/bin/env python3
"""Fast in-process tuning loop: apply a preset dict to a long 16th-note grid and
measure it with the SAME grid-free estimator used on the reference."""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE, os.path.join(ROOT, "src")]

import p5b_stats as S                                    # noqa: E402
from filigree import feel as F                           # noqa: E402
from filigree.feel import FeelSpec, apply_feel           # noqa: E402
from filigree.ir import Note                             # noqa: E402

TEMPO = 120.0


def grid(n=2048, gate=0.9):
    scale = [60, 62, 64, 65, 67, 69, 71, 72]
    return [Note(start=i * 0.25, dur=0.25 * gate, pitch=scale[(i * 5) % 8] + 12,
                 velocity=88, stave="rh", voice="mel", id=i) for i in range(n)]


def run(params: dict, n=2048, tempo=TEMPO, seed=42):
    notes = grid(n)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        apply_feel(notes, FeelSpec(**params), tempo, seed=seed)
    recs = S.from_beats(notes, tempo)
    res, idx, tats, rf = S.timing_residuals(recs)
    vsd, viqr, vr1, vacf = S.velocity_stats(recs)
    gates = S.gate_ratios(recs)
    g = S.iqr_stats(gates)
    ar = np.abs(np.array(res)) if res else np.array([0.0])
    return {
        "nres": len(res), "runfrac": rf,
        "absres": float(np.median(ar)),
        "p99_over_p50": float(np.percentile(ar, 99) / max(1e-9, np.median(ar))),
        "rt": float(np.median(ar)) / (np.median(tats) if tats else 1),
        "kurt": S.excess_kurtosis(res), "lag1": S.timing_lag1(res, idx),
        "vsd": vsd, "viqr": viqr, "vr1": vr1, "acf2": vacf[1],
        "gq1": g["q1"], "gmed": g["median"], "gq3": g["q3"],
        "gw": g["iqr_width"],
    }


def run_many(params: dict, n=1400, seeds=(1, 7, 13, 42, 99, 123)):
    """Median over several seeds: single realisations of kurtosis are noisy."""
    rows = [run(params, n=n, seed=s) for s in seeds]
    out = {}
    for k in rows[0]:
        vals = sorted(float(r[k]) for r in rows)
        out[k] = vals[len(vals) // 2]
        out[k + "_lo"], out[k + "_hi"] = vals[0], vals[-1]
    return out


def show(label, r):
    print(f"{label:24s} n={int(r['nres']):5d} |res|={r['absres']:6.2f} r/t={r['rt']:.3f} "
          f"kurt={r['kurt']:+6.2f} p99/p50={r['p99_over_p50']:4.1f} "
          f"tlag1={r['lag1']:+.2f} vsd={r['vsd']:5.1f} viqr={r['viqr']:5.1f} "
          f"vr1={r['vr1']:+.2f} acf2={r['acf2']:+.2f} "
          f"gate={r['gq1']:.2f}/{r['gmed']:.2f}/{r['gq3']:.2f} w={r['gw']:.2f}")


if __name__ == "__main__":
    print("TARGET                   |res| 6.9-10.3  r/t .071-.084  kurt +2.9..+7.8  "
          "vsd 10.7-14.5  viqr 13.4-19.1  vr1 .39-.54  gate .45/.99/3.41 w 1.6-3.6")
    for name in ("loose", "tight", "pushed", "breath"):
        r = run_many(dict(F.PRESETS[name]))
        show(name, r)
        print(f"{'':24s} spread over seeds: |res| {r['absres_lo']:.1f}-{r['absres_hi']:.1f} "
              f"kurt {r['kurt_lo']:+.1f}..{r['kurt_hi']:+.1f} vr1 {r['vr1_lo']:+.2f}..{r['vr1_hi']:+.2f}")
    for over in sys.argv[1:]:
        base, _, rest = over.partition(":")
        params = dict(F.PRESETS[base])
        for kv in rest.split(","):
            if not kv:
                continue
            k, _, v = kv.partition("=")
            params[k] = float(v)
        r = run_many(params)
        show(over, r)
        print(f"{'':24s} spread over seeds: |res| {r['absres_lo']:.1f}-{r['absres_hi']:.1f} "
              f"kurt {r['kurt_lo']:+.1f}..{r['kurt_hi']:+.1f} vr1 {r['vr1_lo']:+.2f}..{r['vr1_hi']:+.2f}")
