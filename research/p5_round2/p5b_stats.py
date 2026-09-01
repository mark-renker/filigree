#!/usr/bin/env python3
"""P5 round-2 statistics library (builder's independent re-derivation).

Implements the *grid-free* estimator adopted by the round-1 critic
(refs/verdicts/P5_round1.md §1), written from the description, not copied:

  * onsets clustered at 50 ms (one chord = one onset);
  * maximal runs of >= 8 consecutive cluster onsets whose IOIs stay inside
    0.75 .. 1.34 x the running median IOI;
  * degree-1 least-squares fit of time vs index inside the run; the residual
    (ms) is the micro-timing deviation, and the index gives an unambiguous
    tatum index;
  * phrases: onset gap <= 0.60 s, >= 4 notes;
  * hand-streams: pitch split at 60;
  * gate = note duration / IOI to the next note in the same hand-stream,
    clipped at 4.0.

Used for BOTH sides (MAESTRO reference and Filigree renders) so the numbers are
directly comparable.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

CHORD_WINDOW_S = 0.050
PHRASE_GAP_S = 0.60
PHRASE_MIN_NOTES = 4
GATE_CLIP = 4.0
RUN_MIN = 8
RUN_LO, RUN_HI = 0.75, 1.34
HAND_SPLIT = 60


@dataclass(frozen=True)
class Rec:
    start: float          # seconds
    dur: float            # seconds
    pitch: int
    velocity: int


# --------------------------------------------------------------------------- #
# input
# --------------------------------------------------------------------------- #

def load_midi(path: str) -> list[Rec]:
    import mido
    mid = mido.MidiFile(path)
    out: list[Rec] = []
    open_: dict[tuple[int, int], list[tuple[float, int]]] = {}
    t = 0.0
    for msg in mid:
        t += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            open_.setdefault((msg.channel, msg.note), []).append((t, msg.velocity))
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            st = open_.get((msg.channel, msg.note))
            if st:
                t0, v = st.pop(0)
                out.append(Rec(t0, max(t - t0, 1e-4), msg.note, v))
    out.sort(key=lambda n: (n.start, n.pitch))
    return out


def from_beats(notes: Iterable, tempo: float) -> list[Rec]:
    spb = 60.0 / float(tempo)
    out = [Rec(float(n.start) * spb, float(n.dur) * spb, int(n.pitch), int(n.velocity))
           for n in notes]
    out.sort(key=lambda n: (n.start, n.pitch))
    return out


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def clusters(notes: Sequence[Rec], window: float = CHORD_WINDOW_S) -> list[list[Rec]]:
    cl: list[list[Rec]] = []
    for n in sorted(notes, key=lambda x: (x.start, x.pitch)):
        if cl and n.start - cl[-1][0].start <= window:
            cl[-1].append(n)
        else:
            cl.append([n])
    return cl


def _runs(onsets: np.ndarray) -> list[tuple[int, int]]:
    """Maximal runs of >= RUN_MIN onsets with locally stable IOI."""
    if onsets.size < RUN_MIN:
        return []
    iois = np.diff(onsets)
    out: list[tuple[int, int]] = []
    i = 0
    n = iois.size
    while i < n:
        j = i + 1
        cur = [iois[i]]
        while j < n:
            med = float(np.median(cur))
            if med <= 0:
                break
            r = iois[j] / med
            if RUN_LO <= r <= RUN_HI:
                cur.append(iois[j])
                j += 1
            else:
                break
        if (j - i) + 1 >= RUN_MIN:
            out.append((i, j))            # onset indices i .. j inclusive
        i = j if j > i else i + 1
    return out


def timing_residuals(notes: Sequence[Rec]) -> tuple[list[float], list[int], list[float], float]:
    """(residual ms, tatum index inside run, run tatum ms per residual, runfrac)."""
    cl = clusters(notes)
    onsets = np.array([c[0].start for c in cl], dtype=float)
    res: list[float] = []
    idx: list[int] = []
    tats: list[float] = []
    covered = 0
    for a, b in _runs(onsets):
        seg = onsets[a:b + 1]
        k = np.arange(seg.size, dtype=float)
        slope, intercept = np.polyfit(k, seg, 1)
        r = (seg - (slope * k + intercept)) * 1000.0
        res.extend(r.tolist())
        idx.extend(range(seg.size))
        tats.extend([slope * 1000.0] * seg.size)
        covered += seg.size
    runfrac = covered / max(1, onsets.size)
    return res, idx, tats, runfrac


def phrases(notes: Sequence[Rec]) -> list[list[Rec]]:
    ns = sorted(notes, key=lambda n: (n.start, n.pitch))
    out: list[list[Rec]] = []
    cur: list[Rec] = []
    prev = None
    for n in ns:
        if prev is not None and n.start - prev > PHRASE_GAP_S:
            if len(cur) >= PHRASE_MIN_NOTES:
                out.append(cur)
            cur = []
        cur.append(n)
        prev = n.start
    if len(cur) >= PHRASE_MIN_NOTES:
        out.append(cur)
    return out


def hand_streams(notes: Sequence[Rec]) -> list[list[Rec]]:
    lo = [n for n in notes if n.pitch < HAND_SPLIT]
    hi = [n for n in notes if n.pitch >= HAND_SPLIT]
    return [s for s in (lo, hi) if len(s) >= 2]


def velocity_stats(notes: Sequence[Rec]) -> tuple[float, float, float, list[float]]:
    """(median within-phrase sd, median within-phrase IQR, pooled lag-1 r, acf)."""
    sds, iqrs = [], []
    xs, ys = [], []
    lagbuf: list[list[float]] = []
    for ph in phrases(notes):
        v = np.array([n.velocity for n in ph], dtype=float)
        if v.size >= PHRASE_MIN_NOTES:
            sds.append(float(np.std(v, ddof=1)))
            iqrs.append(float(np.percentile(v, 75) - np.percentile(v, 25)))
        for st in hand_streams(ph):
            sv = np.array([n.velocity for n in
                           sorted(st, key=lambda n: (n.start, n.pitch))], dtype=float)
            if sv.size >= 3:
                xs.extend(sv[:-1].tolist())
                ys.extend(sv[1:].tolist())
                lagbuf.append(sv.tolist())
    r1 = _pearson(xs, ys)
    acf = []
    for lag in range(1, 9):
        a, b = [], []
        for sv in lagbuf:
            if len(sv) > lag:
                a.extend(sv[:-lag])
                b.extend(sv[lag:])
        acf.append(_pearson(a, b))
    return (_med(sds), _med(iqrs), r1, acf)


def timing_lag1(res: Sequence[float], idx: Sequence[int]) -> float:
    a, b = [], []
    for i in range(1, len(idx)):
        if idx[i] == idx[i - 1] + 1:
            a.append(res[i - 1])
            b.append(res[i])
    return _pearson(a, b)


def gate_ratios(notes: Sequence[Rec]) -> list[float]:
    out: list[float] = []
    for st in hand_streams(sorted(notes, key=lambda n: (n.start, n.pitch))):
        st = sorted(st, key=lambda n: (n.start, n.pitch))
        for a, b in zip(st, st[1:]):
            ioi = b.start - a.start
            if ioi <= 1e-6:
                continue
            out.append(min(GATE_CLIP, a.dur / ioi))
    return out


def chord_stats(notes: Sequence[Rec]) -> tuple[float, float, float, int]:
    """(median spread ms over >=2-note clusters, median spearman r(pitch,onset)
    over >=3-note clusters, median top-note lead ms, n clusters)."""
    spreads, rs, leads = [], [], []
    for c in clusters(notes):
        if len(c) >= 2:
            ts = [n.start for n in c]
            spreads.append((max(ts) - min(ts)) * 1000.0)
        if len(c) >= 3:
            p = np.array([n.pitch for n in c], dtype=float)
            t = np.array([n.start for n in c], dtype=float)
            if len(set(p.tolist())) >= 3 and len(set(t.tolist())) >= 2:
                rs.append(_spearman(p, t))
                top = int(np.argmax(p))
                others = [t[i] for i in range(len(c)) if i != top]
                leads.append((t[top] - float(np.mean(others))) * 1000.0)
    return (_med(spreads), _med(rs), _med(leads), len(spreads))


# --------------------------------------------------------------------------- #
# small stats
# --------------------------------------------------------------------------- #

def _pearson(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) < 3:
        return float("nan")
    x = np.array(a, dtype=float)
    y = np.array(b, dtype=float)
    if x.std() < 1e-12 or y.std() < 1e-12:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def _spearman(x, y) -> float:
    from scipy.stats import rankdata
    return _pearson(rankdata(x).tolist(), rankdata(y).tolist())


def _med(xs) -> float:
    xs = [x for x in xs if x == x]
    return float(np.median(xs)) if xs else float("nan")


def excess_kurtosis(xs: Sequence[float]) -> float:
    if len(xs) < 8:
        return float("nan")
    a = np.array(xs, dtype=float)
    s = a.std()
    if s < 1e-12:
        return float("nan")
    return float(((a - a.mean()) ** 4).mean() / s ** 4 - 3.0)


def skew(xs: Sequence[float]) -> float:
    a = np.array(xs, dtype=float)
    s = a.std()
    if len(a) < 8 or s < 1e-12:
        return float("nan")
    return float(((a - a.mean()) ** 3).mean() / s ** 3)


def dagostino(xs: Sequence[float]) -> tuple[float, float]:
    from scipy.stats import normaltest
    if len(xs) < 20:
        return (float("nan"), float("nan"))
    k2, p = normaltest(np.array(xs, dtype=float))
    return (float(k2), float(p))


def q(xs: Sequence[float], p: float) -> float:
    xs = [x for x in xs if x == x]
    return float(np.percentile(xs, p)) if xs else float("nan")


def iqr_stats(xs: Sequence[float]) -> dict:
    return {"n": len(xs), "q1": q(xs, 25), "median": q(xs, 50), "q3": q(xs, 75),
            "iqr_width": q(xs, 75) - q(xs, 25)}


# --------------------------------------------------------------------------- #
# metrical position (candidate side: nominal grid is known)
# --------------------------------------------------------------------------- #

def kruskal(groups: list[list[float]]) -> tuple[float, float, float]:
    """(H, p, span of class medians) for >=2 non-empty groups."""
    from scipy.stats import kruskal as kw
    gs = [g for g in groups if len(g) >= 3]
    if len(gs) < 2:
        return (float("nan"), float("nan"), float("nan"))
    H, p = kw(*gs)
    meds = [float(np.median(g)) for g in gs]
    return (float(H), float(p), max(meds) - min(meds))


def parity_alternation(res: Sequence[float], idx: Sequence[int]) -> float:
    """|median(even idx) - median(odd idx)| in ms — label-invariant period-2 test."""
    ev = [r for r, i in zip(res, idx) if i % 2 == 0]
    od = [r for r, i in zip(res, idx) if i % 2 == 1]
    if len(ev) < 3 or len(od) < 3:
        return float("nan")
    return abs(float(np.median(ev)) - float(np.median(od)))


# --------------------------------------------------------------------------- #
# one-file summary
# --------------------------------------------------------------------------- #

def summarise(notes: Sequence[Rec], label: str) -> dict:
    res, idx, tats, runfrac = timing_residuals(notes)
    absres = [abs(r) for r in res]
    tat = _med(tats)
    vsd, viqr, vr1, vacf = velocity_stats(notes)
    gates = gate_ratios(notes)
    csp, cr, clead, ncl = chord_stats(notes)
    k2, pval = dagostino(res)
    return {
        "label": label,
        "n_notes": len(notes),
        "tatum_ms": tat,
        "runfrac": runfrac,
        "n_res": len(res),
        "abs_res_ms": _med(absres),
        "res_over_tatum": (_med(absres) / tat) if tat and tat == tat else float("nan"),
        "res_kurtosis": excess_kurtosis(res),
        "res_skew": skew(res),
        "res_k2": k2,
        "res_k2_p": pval,
        "res_lag1_r": timing_lag1(res, idx),
        "res_parity_ms": parity_alternation(res, idx),
        "vel_sd": vsd,
        "vel_iqr": viqr,
        "vel_lag1_r": vr1,
        "vel_acf": vacf,
        "gate": iqr_stats(gates),
        "chord_spread_ms": csp,
        "chord_pitch_onset_r": cr,
        "chord_top_lead_ms": clead,
        "n_chords": ncl,
    }


def aggregate(rows: list[dict], keys: Sequence[str]) -> dict:
    out = {}
    for k in keys:
        vals = [r[k] for r in rows if isinstance(r.get(k), float) and r[k] == r[k]]
        out[k] = {"median": _med(vals), "q1": q(vals, 25), "q3": q(vals, 75),
                  "n_files": len(vals)}
    return out


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    mdir = os.path.join(root, "refs", "midi")
    rows = []
    for fn in sorted(os.listdir(mdir)):
        if not fn.lower().endswith(".mid"):
            continue
        rows.append(summarise(load_midi(os.path.join(mdir, fn)), fn))
        r = rows[-1]
        print(f"{fn[:44]:44s} tat={r['tatum_ms']:6.1f} rf={r['runfrac']:.2f} "
              f"n={r['n_res']:5d} |res|={r['abs_res_ms']:6.2f} "
              f"r/t={r['res_over_tatum']:.3f} kurt={r['res_kurtosis']:+6.2f} "
              f"vsd={r['vel_sd']:5.1f} viqr={r['vel_iqr']:5.1f} "
              f"vr1={r['vel_lag1_r']:+.2f} "
              f"gate={r['gate']['q1']:.2f}/{r['gate']['median']:.2f}/{r['gate']['q3']:.2f} "
              f"chord={r['chord_spread_ms']:5.1f} clead={r['chord_top_lead_ms']:+5.1f} "
              f"cr={r['chord_pitch_onset_r']:+.2f}")
    agg = aggregate(rows, ["tatum_ms", "runfrac", "abs_res_ms", "res_over_tatum",
                           "res_kurtosis", "res_lag1_r", "vel_sd", "vel_iqr",
                           "vel_lag1_r", "chord_spread_ms", "chord_top_lead_ms",
                           "chord_pitch_onset_r"])
    gq1 = _med([r["gate"]["q1"] for r in rows])
    gmed = _med([r["gate"]["median"] for r in rows])
    gq3 = _med([r["gate"]["q3"] for r in rows])
    gw = [r["gate"]["q3"] - r["gate"]["q1"] for r in rows]
    agg["gate_pooled"] = {"q1": gq1, "median": gmed, "q3": gq3,
                          "iqr_width_median": _med(gw),
                          "iqr_width_q1": q(gw, 25), "iqr_width_q3": q(gw, 75)}
    acfs = np.array([r["vel_acf"] for r in rows], dtype=float)
    agg["vel_acf_median"] = np.nanmedian(acfs, axis=0).tolist()
    out = {"per_file": rows, "aggregate": agg}
    with open(os.path.join(here, "ground_truth.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print("\nAGGREGATE (median [q1, q3] over 12 files)")
    for k, v in agg.items():
        if k in ("gate_pooled", "vel_acf_median"):
            print(f"  {k}: {v}")
        else:
            print(f"  {k:22s} {v['median']:+8.3f}  [{v['q1']:+8.3f}, {v['q3']:+8.3f}]")
