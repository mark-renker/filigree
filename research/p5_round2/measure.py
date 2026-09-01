#!/usr/bin/env python3
"""P5 round-2 candidate measurement — the same six statistics as the critic.

Three measurement grounds, each labelled in the output:

* **CLI renders** of ``examples/pulse.fil`` and ``examples/nocturne.fil`` (the
  files the work order names) with each preset substituted for the authored
  feel, re-parsed from the SMF with ``mido``;
* a **probe** — 16 bars of straight 16ths, 4/4, 120 bpm, 256 notes — rendered
  through the same CLI, because 25–39 notes cannot support a distribution
  statistic (the critic's evidence gate, §0);
* **isolation** — ``apply_feel`` called on a synthetic 4000-note score, which
  gives the exact perturbation per note with no estimator noise.

Plus determinism / independence / edge probes.

    PYTHONPATH=src python research/p5_round2/measure.py
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
import warnings

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import p5b_stats as S                                            # noqa: E402
from filigree import feel as F                                    # noqa: E402
from filigree.feel import FeelSpec, apply_feel, preset            # noqa: E402
from filigree.ir import Note                                     # noqa: E402

PRESETS = ["loose", "tight", "pushed", "breath"]
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)

PROBE = """@title "probe"
@tempo 120
@meter 4/4
@key C major
@seed 11
feel FEELNAME
stave p {
  feel FEELNAME
  notes | 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 |
}
"""


def probe_src(feel_name: str | None, bars: int = 16) -> str:
    line = " ".join(str(i % 16) for i in range(16))
    bars_txt = " | ".join([line] * bars)
    feel = f"  feel {feel_name}\n" if feel_name else ""
    return (f'@title "probe"\n@tempo 120\n@meter 4/4\n@key C major\n@seed 11\n'
            f"stave p {{\n{feel}  notes | {bars_txt} |\n}}\n")


def example_src(name: str, feel_name: str | None) -> str:
    """The example, with its authored feel block replaced by a preset name."""
    src = open(os.path.join(ROOT, "examples", name)).read()
    m = re.search(r"^feel\s+(\w+)\s*(=)?\s*\{", src, re.M)
    authored = m.group(1) if m else None
    if authored is None:
        return src
    src = re.sub(r"^feel\s+\w+\s*=?\s*\{[^}]*\}\s*$", "", src, flags=re.M)
    if feel_name is None:
        src = re.sub(rf"^\s*feel\s+{authored}\s*$", "", src, flags=re.M)
    else:
        src = re.sub(rf"(^\s*)feel\s+{authored}\s*$", rf"\1feel {feel_name}",
                     src, flags=re.M)
    return src


def render(src: str, tag: str) -> tuple[str, str]:
    fil = os.path.join(OUT, tag + ".fil")
    mid = os.path.join(OUT, tag + ".mid")
    with open(fil, "w") as fh:
        fh.write(src)
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"),
               PYTHONWARNINGS="ignore")
    r = subprocess.run([sys.executable, "-m", "filigree.cli", "render", fil,
                        "-o", mid], capture_output=True, text=True, env=env,
                       cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit(f"render failed for {tag}:\n{r.stdout}\n{r.stderr}")
    return mid, hashlib.md5(open(mid, "rb").read()).hexdigest()


# --------------------------------------------------------------------------- #
# isolation
# --------------------------------------------------------------------------- #

def synth(n_notes: int = 4000, chords: bool = False) -> list[Note]:
    """A rigid 16th-note line at 120 bpm, 4/4 — nominal grid known exactly."""
    scale = [60, 62, 64, 65, 67, 69, 71, 72]
    out = []
    for i in range(n_notes):
        out.append(Note(start=i * 0.25, dur=0.25 * 0.9,
                        pitch=scale[(i * 5) % 8] + 12, velocity=88,
                        stave="rh", voice="mel", id=i))
    return out


def synth_chords(n: int = 300) -> list[Note]:
    out = []
    k = 0
    for c in range(n):
        for j, iv in enumerate((0, 4, 7, 11)):
            out.append(Note(start=c * 1.0, dur=0.9, pitch=60 + iv,
                            velocity=80, stave="rh", voice=f"v{j}", id=k))
            k += 1
    return out


def isolation(name: str) -> dict:
    base = synth()
    notes = synth()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        apply_feel(notes, preset(name), 120.0, seed=42)
    dev = [(n.start - b.start) * 500.0 for n, b in zip(notes, base)]   # ms @120bpm
    k2, pv = S.dagostino(dev)
    # lag-1 of the perturbation
    r1 = S._pearson(dev[:-1], dev[1:])
    # metrical: position inside the beat (4 classes) and beat of bar (4 classes)
    by_sub = [[] for _ in range(4)]
    by_beat = [[] for _ in range(4)]
    vel_by_beat = [[] for _ in range(4)]
    for b, d in zip(base, dev):
        sub = int(round((b.start % 1.0) / 0.25)) % 4
        beat = int(math.floor(b.start)) % 4
        by_sub[sub].append(d)
        by_beat[beat].append(d)
    for b, n in zip(base, notes):
        vel_by_beat[int(math.floor(b.start)) % 4].append(float(n.velocity))
    Hs, ps, spans = S.kruskal(by_sub)
    Hb, pb, spanb = S.kruskal(by_beat)
    Hv, pv2, spanv = S.kruskal(vel_by_beat)
    vels = [n.velocity for n in notes]
    gates = [n.dur / 0.25 for n in notes]
    # chords
    cb, cn = synth_chords(), synth_chords()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        apply_feel(cn, preset(name), 120.0, seed=42)
    rs, leads, spreads = [], [], []
    for c in range(300):
        grp = [(cn[c * 4 + j].pitch, cn[c * 4 + j].start) for j in range(4)]
        p_ = np.array([g[0] for g in grp], float)
        t_ = np.array([g[1] for g in grp], float)
        rs.append(S._spearman(p_, t_))
        top = int(np.argmax(p_))
        leads.append((t_[top] - np.mean([t_[j] for j in range(4) if j != top])) * 500.0)
        spreads.append((t_.max() - t_.min()) * 500.0)
    return {
        "preset": name,
        "dev_mean": float(np.mean(dev)), "dev_sd": float(np.std(dev, ddof=1)),
        "abs_dev_med": float(np.median(np.abs(dev))),
        "dev_kurt": S.excess_kurtosis(dev), "dev_skew": S.skew(dev),
        "dev_k2": k2, "dev_k2_p": pv, "dev_lag1_r": r1,
        "dev_min": float(np.min(dev)), "dev_max": float(np.max(dev)),
        "vel_sd": float(np.std(vels, ddof=1)),
        "vel_iqr": float(np.percentile(vels, 75) - np.percentile(vels, 25)),
        "vel_lag1_r": S._pearson(vels[:-1], vels[1:]),
        "vel_acf": [S._pearson(vels[:-k], vels[k:]) for k in range(1, 9)],
        "gate": S.iqr_stats(gates),
        "kw_subbeat": {"H": Hs, "p": ps, "span_ms": spans},
        "kw_beat": {"H": Hb, "p": pb, "span_ms": spanb},
        "kw_vel_beat": {"H": Hv, "p": pv2, "span_vel": spanv},
        "chord_r": S._med(rs), "chord_lead_ms": S._med(leads),
        "chord_spread_ms": S._med(spreads),
        "pitches_preserved": [n.pitch for n in cn] == [n.pitch for n in cb],
        "order_inversions": sum(1 for a, b in zip(notes, notes[1:])
                                if b.start < a.start - 1e-12),
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def measure_render(mid: str, label: str) -> dict:
    return S.summarise(S.load_midi(mid), label)


def main() -> None:
    res: dict = {"renders": [], "isolation": [], "determinism": {}, "edges": []}

    jobs = [("probe", lambda f: probe_src(f, bars=96)),
            ("pulse", lambda f: example_src("pulse.fil", f)),
            ("nocturne", lambda f: example_src("nocturne.fil", f))]
    for base, mk in jobs:
        for name in PRESETS + [None]:
            tag = f"{base}_{name or 'none'}"
            mid, md5 = render(mk(name), tag)
            row = measure_render(mid, tag)
            if base == "probe" and name:
                # the reference numbers are per-file medians over thousands of
                # notes: repeat the probe over several seeds and report the
                # median, so a single lucky realisation cannot flatter us
                reps = []
                for k, sd in enumerate((11, 23, 37, 59, 71)):
                    src = probe_src(name, bars=96).replace("@seed 11", f"@seed {sd}")
                    m2, _ = render(src, f"{tag}_s{sd}")
                    reps.append(measure_render(m2, f"{tag}_s{sd}"))
                for key in ("abs_res_ms", "res_over_tatum", "res_kurtosis",
                            "vel_sd", "vel_lag1_r"):
                    vals = sorted(r[key] for r in reps)
                    row[key + "_seedmed"] = vals[len(vals) // 2]
                    row[key + "_seedrange"] = [vals[0], vals[-1]]
                gw = sorted(r["gate"]["iqr_width"] for r in reps)
                row["gate_width_seedmed"] = gw[len(gw) // 2]
                row["gate_med_seedmed"] = sorted(
                    r["gate"]["median"] for r in reps)[len(reps) // 2]
            row["md5"] = md5
            res["renders"].append(row)
            g = row["gate"]
            print(f"{tag:20s} n={row['n_notes']:4d} nres={row['n_res']:4d} "
                  f"tat={row['tatum_ms']:6.1f} |res|={row['abs_res_ms']:6.2f} "
                  f"r/t={row['res_over_tatum']:.3f} kurt={row['res_kurtosis']:+6.2f} "
                  f"vsd={row['vel_sd']:5.1f} vr1={row['vel_lag1_r']:+.2f} "
                  f"gate={g['q1']:.2f}/{g['median']:.2f}/{g['q3']:.2f} "
                  f"(w={g['iqr_width']:.2f}) chord={row['chord_spread_ms']:5.1f} "
                  f"lead={row['chord_top_lead_ms']:+5.1f} cr={row['chord_pitch_onset_r']:+.2f}")
            if "res_kurtosis_seedmed" in row:
                print(f"{'':20s} seed-median: |res|={row['abs_res_ms_seedmed']:6.2f} "
                      f"r/t={row['res_over_tatum_seedmed']:.3f} "
                      f"kurt={row['res_kurtosis_seedmed']:+6.2f} "
                      f"(range {row['res_kurtosis_seedrange'][0]:+.1f}..{row['res_kurtosis_seedrange'][1]:+.1f}) "
                      f"vsd={row['vel_sd_seedmed']:5.1f} "
                      f"vr1={row['vel_lag1_r_seedmed']:+.2f} "
                      f"gatew={row['gate_width_seedmed']:.2f} "
                      f"gatemed={row['gate_med_seedmed']:.2f}")

    print()
    for name in PRESETS:
        iso = isolation(name)
        res["isolation"].append(iso)
        print(f"iso/{name:7s} sd={iso['dev_sd']:6.2f} |dev|={iso['abs_dev_med']:6.2f} "
              f"kurt={iso['dev_kurt']:+6.2f} lag1={iso['dev_lag1_r']:+.3f} "
              f"vsd={iso['vel_sd']:5.2f} viqr={iso['vel_iqr']:5.1f} "
              f"vr1={iso['vel_lag1_r']:+.3f} "
              f"gate={iso['gate']['q1']:.2f}/{iso['gate']['median']:.2f}/"
              f"{iso['gate']['q3']:.2f} "
              f"KWsub p={iso['kw_subbeat']['p']:.2e} span={iso['kw_subbeat']['span_ms']:5.2f} "
              f"KWbeat p={iso['kw_beat']['p']:.2e} span={iso['kw_beat']['span_ms']:5.2f} "
              f"clead={iso['chord_lead_ms']:+5.1f} cr={iso['chord_r']:+.2f} "
              f"csp={iso['chord_spread_ms']:5.1f}")

    # ---- determinism: 3 separate interpreter invocations ----------------- #
    det = {}
    for base, mk in jobs:
        hs = [render(mk("loose"), f"det_{base}_{k}")[1] for k in range(3)]
        det[base] = {"md5s": hs, "identical": len(set(hs)) == 1}
    seeds = {}
    for s in (11, 12, 13, 101):
        src = probe_src("loose").replace("@seed 11", f"@seed {s}")
        seeds[s] = render(src, f"seed_{s}")[1]
    det["seed_md5s"] = seeds
    det["seeds_differ"] = len(set(seeds.values())) == 4
    # zero feel vs no feel
    zsrc = probe_src("zero").replace(
        "stave p {",
        "feel zero = { timing: 0ms, velocity: 0%, gate: 0%, onset: 0ms, "
        "release: 0ms }\nstave p {")
    _, z = render(zsrc, "probe_zero")
    _, nofeel = render(probe_src(None), "probe_nofeel2")
    det["zero_feel_md5"] = z
    det["no_feel_md5"] = nofeel
    det["zero_is_bit_exact"] = (z == nofeel)
    res["determinism"] = det
    print("\ndeterminism:", json.dumps({k: v for k, v in det.items()
                                        if k != "seed_md5s"}, indent=1))

    # ---- edges ----------------------------------------------------------- #
    def edge(label: str, spec, notes=None):
        ns = notes if notes is not None else synth(256)
        base = [(n.start, n.pitch) for n in ns]
        msgs: list[str] = []
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            apply_feel(ns, spec, 120.0, seed=5, on_warning=msgs.append)
        starts = [n.start for n in ns]
        # a real reordering: two notes whose NOMINAL onsets differ swapped places
        inv = 0
        for (sa, _pa), (sb, _pb), na, nb in zip(base, base[1:], ns, ns[1:]):
            if sa < sb - 1e-12 and nb.start < na.start - 1e-12:
                inv += 1
        row = {
            "label": label,
            "warnings": msgs,
            "inversions": inv,
            "stacked_at_zero": sum(1 for s in starts if s == 0.0),
            "max_start": max(starts), "min_start": min(starts),
            "max_end": max(n.start + n.dur for n in ns),
            "nan": any(n.start != n.start or n.dur != n.dur for n in ns),
            "inf": any(math.isinf(n.start) or math.isinf(n.dur) for n in ns),
            "pitches_preserved": sorted(n.pitch for n in ns) == sorted(p for _s, p in base),
            "vel_ok": all(1 <= n.velocity <= 127 and isinstance(n.velocity, int) for n in ns),
            "dur_positive": all(n.dur > 0 for n in ns),
        }
        res["edges"].append(row)
        print(f"edge {label:22s} inv={row['inversions']:3d} zero={row['stacked_at_zero']:3d} "
              f"max_start={row['max_start']:7.2f} max_end={row['max_end']:7.2f} "
              f"nan={row['nan']} inf={row['inf']} pitches={row['pitches_preserved']} "
              f"warn={len(msgs)}")
        for m in msgs:
            print("      !", m)

    edge("absurd", FeelSpec(timing_ms=2000.0, onset_ms=2000.0, release_ms=2000.0,
                            velocity=4.0, gate=9.0, seed=2))
    edge("flat -2000ms", FeelSpec(timing_ms=-2000.0, timing_dist="flat", seed=2))
    edge("nan timing", FeelSpec(timing_ms=float("nan"), velocity=0.1, seed=2))
    edge("inf timing", FeelSpec(timing_ms=float("inf"), seed=2))
    edge("velocity 0.99", FeelSpec(velocity=0.99, seed=2))
    edge("velocity 1.01", FeelSpec(velocity=1.01, seed=2))
    edge("velocity '400%'", FeelSpec(velocity="400%", seed=2))
    edge("velocity '12%'", FeelSpec(velocity="12%", seed=2))
    edge("gate 1.0", FeelSpec(gate=1.0, seed=2))
    edge("gate 1.01", FeelSpec(gate=1.01, seed=2))
    edge("unknown dist", FeelSpec(timing_ms=20.0, timing_dist="triangular", seed=2))
    edge("negative gate", FeelSpec(gate=-0.5, seed=2))
    edge("single note", FeelSpec(**F.LOOSE),
         notes=[Note(start=0.0, dur=1.0, pitch=60, velocity=90, stave="rh", id=0)])
    edge("200 same key", FeelSpec(**F.LOOSE),
         notes=[Note(start=4.0, dur=0.5, pitch=60, velocity=90, stave="rh", id=i)
                for i in range(200)])

    with open(os.path.join(HERE, "candidate.json"), "w") as fh:
        json.dump(res, fh, indent=1, default=float)
    print("\nwrote", os.path.join(HERE, "candidate.json"))


if __name__ == "__main__":
    main()
