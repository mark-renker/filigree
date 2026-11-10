"""P5 round-2 tests — deterministic humanisation against the re-derived truth.

The reference numbers used here are the ones re-derived from the 12 MAESTRO
performances in ``refs/midi/`` and written up, with method and per-file numbers,
in ``refs/specs/feel_truth.md``.  They are *not* taken from
``refs/midi/stats.json``: that file's own targets (timing_dev_ms 30.5,
gate_ratio 0.49) do not survive re-derivation with a grid-free estimator
(8.3 ms and 0.99), so the tests below measure the way the reference was measured.

Run from the repo root:  PYTHONPATH=src python -m pytest tests/test_feel.py -q
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import statistics
import subprocess
import sys
import textwrap
import warnings

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "src"), os.path.join(ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import perf_stats as PS                                  # noqa: E402
from filigree import feel as F                            # noqa: E402
from filigree.feel import (AUTO, FeelSpec, FeelWarning, apply_feel,  # noqa: E402
                           gauss, hash01, normalise, preset)
from filigree.ir import Note                              # noqa: E402

TEMPO = 96.0
BASE_GATE = 0.62
PRESET_NAMES = ["loose", "tight", "pushed", "breath"]

# ---- refs/specs/feel_truth.md, median [q1, q3] over the 12 MAESTRO files --- #
REF = {
    "abs_res_ms": (8.32, 6.90, 10.30),
    "res_over_tatum": (0.076, 0.071, 0.084),
    "res_kurtosis": (5.64, 2.87, 7.79),
    "vel_sd": (11.86, 10.73, 14.53),
    "vel_lag1_r": (0.452, 0.385, 0.538),
    "gate_iqr_width": (2.93, 1.59, 3.63),
    "gate_median": (0.986, 0.447, 3.408),
    "chord_spread_ms": (16.93, 14.97, 21.09),
    "chord_top_lead_ms": (-5.32, -8.0, -2.0),
}


# --------------------------------------------------------------------------- #
# fixtures / helpers
# --------------------------------------------------------------------------- #

def synthetic_phrase(bars: int = 24, gate: float = BASE_GATE) -> list[Note]:
    """A rigid, perfectly quantised 4/4 input: 16th-note melody + chord stabs."""
    notes: list[Note] = []
    scale = [60, 62, 64, 65, 67, 69, 71, 72]
    nid = 0
    for bar in range(bars):
        for step in range(16):
            beat = bar * 4 + step * 0.25
            pitch = scale[(bar * 3 + step * 5) % len(scale)] + 12
            notes.append(Note(start=beat, dur=0.25 * gate, pitch=pitch,
                              velocity=88, stave="rh", voice="mel", id=nid))
            nid += 1
        for k, iv in enumerate((0, 4, 7)):
            for beat in (bar * 4 + 0.0, bar * 4 + 2.0):
                notes.append(Note(start=beat, dur=1.0 * gate, pitch=48 + iv,
                                  velocity=80, stave="lh", voice=f"c{k}", id=nid))
                nid += 1
    notes.sort(key=lambda n: (n.start, n.pitch))
    return notes


def melody_line(bars: int = 96, tempo: float = 120.0) -> list[Note]:
    """A long single-hand 16th-note line: the material the statistics need."""
    scale = [60, 62, 64, 65, 67, 69, 71, 72]
    return [Note(start=i * 0.25, dur=0.25 * 0.9, pitch=scale[(i * 5) % 8] + 12,
                 velocity=88, stave="rh", voice="mel", id=i)
            for i in range(bars * 16)]


def snapshot(notes) -> list[tuple]:
    return [(n.id, round(n.start, 12), round(n.dur, 12), n.velocity) for n in notes]


def humanise(notes, spec, tempo=TEMPO, seed=42):
    """Apply feel, swallowing the warnings (they are asserted on separately)."""
    msgs: list[str] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        apply_feel(notes, spec, tempo, seed=seed, on_warning=msgs.append)
    return msgs


# ---- the reference estimator, in miniature (see refs/specs/feel_truth.md) -- #

def _clusters(secs):
    out: list[list] = []
    for n in sorted(secs, key=lambda x: (x[0], x[2])):
        if out and n[0] - out[-1][0][0] <= 0.050:
            out[-1].append(n)
        else:
            out.append([n])
    return out


def _runs(onsets, lo=0.75, hi=1.34, minlen=8):
    if len(onsets) < minlen:
        return []
    iois = [b - a for a, b in zip(onsets, onsets[1:])]
    out, i = [], 0
    while i < len(iois):
        j, cur = i + 1, [iois[i]]
        while j < len(iois):
            med = statistics.median(cur)
            if med > 0 and lo <= iois[j] / med <= hi:
                cur.append(iois[j])
                j += 1
            else:
                break
        if (j - i) + 1 >= minlen:
            out.append((i, j))
        i = j if j > i else i + 1
    return out


def _fit(xs, ys):
    n = len(xs)
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx else 0.0
    return slope, my - slope * mx


def residuals(notes, tempo):
    """(residual ms, tatum index, tatum ms) exactly as the reference is measured."""
    secs = [(n.start * 60.0 / tempo, n.dur * 60.0 / tempo, n.pitch, n.velocity)
            for n in notes]
    onsets = [c[0][0] for c in _clusters(secs)]
    res, idx, tats = [], [], []
    for a, b in _runs(onsets):
        seg = onsets[a:b + 1]
        ks = list(range(len(seg)))
        slope, ic = _fit(ks, seg)
        res.extend((y - (slope * k + ic)) * 1000.0 for k, y in zip(ks, seg))
        idx.extend(ks)
        tats.extend([slope * 1000.0] * len(seg))
    return res, idx, tats


def excess_kurtosis(xs):
    n = len(xs)
    m = statistics.fmean(xs)
    sd = statistics.pstdev(xs)
    if n < 8 or sd == 0:
        return float("nan")
    return sum(((x - m) / sd) ** 4 for x in xs) / n - 3.0


def pearson(a, b):
    if len(a) < 3:
        return float("nan")
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da and db else float("nan")


def lag1(xs, idx=None):
    if idx is None:
        return pearson(xs[:-1], xs[1:])
    a = [xs[i - 1] for i in range(1, len(xs)) if idx[i] == idx[i - 1] + 1]
    b = [xs[i] for i in range(1, len(xs)) if idx[i] == idx[i - 1] + 1]
    return pearson(a, b)


def gate_ratios(notes, clip=4.0):
    ns = sorted(notes, key=lambda n: (n.start, n.pitch))
    out = []
    for a, b in zip(ns, ns[1:]):
        ioi = b.start - a.start
        if ioi > 1e-9:
            out.append(min(a.dur / ioi, clip))
    return out


def quartiles(xs):
    ys = sorted(xs)
    def q(p):
        k = (len(ys) - 1) * p
        lo, hi = int(math.floor(k)), int(math.ceil(k))
        return ys[lo] + (ys[hi] - ys[lo]) * (k - lo)
    return q(0.25), q(0.50), q(0.75)


@pytest.fixture(scope="module")
def rendered() -> dict:
    """Every preset applied to the same long line, measured once per module."""
    out = {}
    for name in PRESET_NAMES:
        rows = []
        for seed in (11, 23, 37, 59, 71):
            notes = melody_line()
            humanise(notes, preset(name), 120.0, seed=seed)
            res, idx, tats = residuals(notes, 120.0)
            vel = [n.velocity for n in sorted(notes, key=lambda n: n.start)]
            gq1, gmed, gq3 = quartiles(gate_ratios(notes))
            rows.append({
                "abs_res_ms": statistics.median(abs(r) for r in res),
                "res_over_tatum": (statistics.median(abs(r) for r in res)
                                   / statistics.median(tats)),
                "res_kurtosis": excess_kurtosis(res),
                "res_lag1_r": lag1(res, idx),
                "vel_sd": statistics.stdev(vel),
                "vel_lag1_r": lag1(vel),
                "gate_iqr_width": gq3 - gq1,
                "gate_median": gmed,
                "notes": notes,
            })
        med = {k: statistics.median(r[k] for r in rows)
               for k in rows[0] if k != "notes"}
        med["seeds"] = rows
        out[name] = med
    return out


# --------------------------------------------------------------------------- #
# 1. counter-based randomness (unchanged: resolve.py depends on these)
# --------------------------------------------------------------------------- #

def test_hash01_range_and_determinism():
    vals = [hash01(7, "rh", 1.25, 60, "timing") for _ in range(3)]
    assert vals[0] == vals[1] == vals[2]
    assert 0.0 <= vals[0] < 1.0
    assert hash01(7, "rh", 1.25, 60, "timing") != hash01(7, "rh", 1.25, 61, "timing")
    assert hash01(7, "rh", 1.25, 60, "timing") != hash01(7, "rh", 1.25, 60, "gate")


def test_hash01_uniformity():
    xs = [hash01(i, "s", float(i) * 0.25, 60 + i % 12, "f") for i in range(4000)]
    assert all(0.0 <= x < 1.0 for x in xs)
    assert abs(statistics.fmean(xs) - 0.5) < 0.02
    assert abs(statistics.pstdev(xs) - (1 / 12) ** 0.5) < 0.02
    bins = [0] * 10
    for x in xs:
        bins[int(x * 10)] += 1
    assert min(bins) > 250 and max(bins) < 550


def test_gauss_moments_and_determinism():
    xs = [gauss(i, "s", i * 0.5, 64, "velocity") for i in range(6000)]
    assert abs(statistics.fmean(xs)) < 0.05
    assert abs(statistics.pstdev(xs) - 1.0) < 0.05
    assert max(abs(x) for x in xs) > 2.5
    assert abs(excess_kurtosis(xs)) < 0.5          # the source itself is normal
    assert gauss(1, 2, 3) == gauss(1, 2, 3)
    assert gauss(1, 2, 3) != gauss(1, 2, 4)


def test_no_salted_string_hash_across_invocations():
    """Different PYTHONHASHSEED must give byte-identical output."""
    code = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {os.path.join(ROOT, 'src')!r})
        from filigree.feel import hash01, gauss, apply_feel, preset
        from filigree.ir import Note
        ns = [Note(start=i * 0.25, dur=0.2, pitch=60 + i % 7, velocity=90,
                   stave="rh", voice="mel", id=i) for i in range(24)]
        apply_feel(ns, preset("loose"), 96.0, seed=42)
        print(repr([hash01("rh", 1.5, 60), gauss("rh", 1.5, 60),
                    [(round(n.start, 12), round(n.dur, 12), n.velocity) for n in ns]]))
    """)
    outs = []
    for salt in ("0", "1", "12345", "random"):
        env = dict(os.environ, PYTHONHASHSEED=salt)
        outs.append(subprocess.run([sys.executable, "-c", code], env=env,
                                   capture_output=True, text=True, check=True).stdout)
    assert outs[0].strip() != ""
    assert len(set(outs)) == 1


# --------------------------------------------------------------------------- #
# 2. apply_feel contract
# --------------------------------------------------------------------------- #

def test_apply_feel_is_deterministic_across_runs():
    a, b = synthetic_phrase(4), synthetic_phrase(4)
    humanise(a, preset("loose"), seed=9)
    humanise(b, preset("loose"), seed=9)
    assert snapshot(a) == snapshot(b)
    c = synthetic_phrase(4)
    humanise(c, preset("loose"), seed=10)
    assert snapshot(c) != snapshot(a)


def test_three_invocations_are_byte_identical():
    outs = []
    for _ in range(3):
        ns = synthetic_phrase(6)
        humanise(ns, preset("breath"), seed=4)
        outs.append(snapshot(ns))
    assert outs[0] == outs[1] == outs[2]


def test_different_seeds_differ_genuinely():
    starts = []
    for seed in (1, 2, 3, 4):
        ns = synthetic_phrase(4)
        humanise(ns, preset("loose"), seed=seed)
        starts.append([round(n.start, 9) for n in ns])
    assert len({tuple(s) for s in starts}) == 4
    a, b = starts[0], starts[1]
    differing = sum(1 for x, y in zip(a, b) if x != y)
    assert differing > 0.9 * len(a)        # not just a couple of notes


def test_memory_decays_forward_only():
    """AR memory means a change propagates *forward* and dies out — never back.

    Round 1 had strictly independent per-note draws (lag-1 r ~ 0), which is why
    a preceding note could never influence the next one.  Editing a note may
    therefore now move later notes a little, but must never move earlier ones,
    and the influence must decay.
    """
    a = melody_line(bars=8)
    b = melody_line(bars=8)
    victim = len(b) // 2
    b[victim].pitch += 1
    humanise(a, preset("loose"), 120.0, seed=5)
    humanise(b, preset("loose"), 120.0, seed=5)
    diffs = [abs(x.start - y.start) + abs(x.dur - y.dur) + abs(x.velocity - y.velocity)
             for x, y in zip(a, b)]
    assert all(d == 0.0 for d in diffs[:victim])            # nothing earlier moved
    assert diffs[victim] > 0.0                              # the note itself moved
    near = statistics.fmean(diffs[victim + 1:victim + 5] or [0.0])
    far = statistics.fmean(diffs[victim + 40:victim + 60] or [0.0])
    assert far <= near                                      # and it decays


def test_locality_edit_in_late_bar_leaves_early_bars_untouched():
    a = synthetic_phrase(8)
    b = synthetic_phrase(8)
    for n in b:
        if n.start >= 28.0:
            n.pitch = 71
            n.velocity = 100
    humanise(a, preset("breath"), seed=3)
    humanise(b, preset("breath"), seed=3)
    early_a = [snapshot([n]) for n in a if n.start < 24.0]
    early_b = [snapshot([n]) for n in b if n.start < 24.0]
    assert early_a == early_b
    assert len(early_a) > 120


def test_zero_spec_is_a_no_op():
    a = synthetic_phrase(2)
    before = snapshot(a)
    humanise(a, FeelSpec(), seed=1)
    assert snapshot(a) == before


def test_zero_percent_feel_is_bit_exact():
    a = synthetic_phrase(3)
    before = snapshot(a)
    humanise(a, FeelSpec(timing_ms=0.0, velocity=0.0, gate=0.0, onset_ms=0.0,
                         release_ms=0.0, seed=7), seed=7)
    assert snapshot(a) == before


def test_pitch_multiset_never_changes():
    for name in PRESET_NAMES:
        ns = synthetic_phrase(4)
        before = sorted(n.pitch for n in ns)
        humanise(ns, preset(name), seed=13)
        assert sorted(n.pitch for n in ns) == before


def test_empty_note_list_is_safe():
    assert apply_feel([], preset("loose"), TEMPO, seed=1) is None


def test_bounds_are_respected():
    notes = [Note(start=0.0, dur=0.05, pitch=60, velocity=1, stave="rh", id=0),
             Note(start=0.0, dur=0.05, pitch=61, velocity=127, stave="rh", id=1)]
    notes += [Note(start=i * 0.25, dur=0.1, pitch=62 + i % 5, velocity=126,
                   stave="lh", voice="v", id=10 + i) for i in range(200)]
    humanise(notes, FeelSpec(timing_ms=400.0, velocity=0.9, gate=0.9,
                             onset_ms=50.0, release_ms=30.0, seed=2), seed=77)
    assert all(1 <= n.velocity <= 127 for n in notes)
    assert all(isinstance(n.velocity, int) for n in notes)
    assert all(n.dur > 0.0 for n in notes)
    assert all(n.start >= 0.0 for n in notes)


def test_flat_timing_is_a_constant_shift_and_honours_on_beats():
    notes = [Note(start=float(b), dur=0.5, pitch=60, velocity=90, stave="rh", id=b)
             for b in range(8)]
    # `flat` is a groove template, not humanisation: no drift, no profiles.
    spec = FeelSpec(timing_ms=-30.0, timing_dist="flat", on_beats=(2, 4))
    humanise(notes, spec, 120.0, seed=1)
    shift_beats = -30.0 / 1000.0 * 120.0 / 60.0
    for n in notes:
        beat_in_bar = n.id % 4 + 1
        expected = n.id + (shift_beats if beat_in_bar in (2, 4) else 0.0)
        assert abs(n.start - max(0.0, expected)) < 1e-12
    assert notes[1].start < 1.0 and notes[0].start == 0.0


def test_timing_scales_with_tempo():
    fast, slow = synthetic_phrase(4), synthetic_phrase(4)
    spec = FeelSpec(timing_ms=20.0, seed=1)
    humanise(fast, spec, 240.0, seed=1)
    humanise(slow, spec, 60.0, seed=1)
    d_fast = [abs(a.start - b.start) for a, b in zip(fast, synthetic_phrase(4))]
    d_slow = [abs(a.start - b.start) for a, b in zip(slow, synthetic_phrase(4))]
    assert statistics.fmean(d_fast) > statistics.fmean(d_slow) * 3.5


def test_velocity_jitter_is_proportional_and_centred():
    notes = synthetic_phrase(8)
    humanise(notes, FeelSpec(velocity=0.15, seed=2), seed=3)
    rh = [n.velocity for n in notes if n.stave == "rh"]
    assert abs(statistics.fmean(rh) - 88) < 2.5
    assert 8.0 < statistics.pstdev(rh) < 22.0


# --------------------------------------------------------------------------- #
# 3. round-2 fixes: memory, timing shape, gate spread, metre, units
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", PRESET_NAMES)
def test_velocity_has_memory(name, rendered):
    """Defect D3: round 1 measured a velocity lag-1 r of -0.010."""
    lo, hi = REF["vel_lag1_r"][1] - 0.06, REF["vel_lag1_r"][2] + 0.10
    r = rendered[name]["vel_lag1_r"]
    assert lo <= r <= hi, (name, r)


def test_iid_mode_has_no_memory_and_normal_tails():
    ns = melody_line(bars=48)
    humanise(ns, FeelSpec(timing_ms=14.0, timing_dist="iid", velocity=0.12,
                          velocity_ar=0.0, accent_profile=(), accent_period2=0.0,
                          timing_profile_ms=(), timing_period2_ms=0.0,
                          timing_drift_ms=0.0, seed=3), 120.0, seed=3)
    vel = [n.velocity for n in ns]
    assert abs(lag1(vel)) < 0.12                 # explicitly memoryless
    res, idx, _t = residuals(ns, 120.0)
    assert abs(excess_kurtosis(res)) < 1.6       # and explicitly gaussian


@pytest.mark.parametrize("name", PRESET_NAMES)
def test_timing_deviation_spread_is_human(name, rendered):
    med, lo, hi = REF["abs_res_ms"]
    assert lo <= rendered[name]["abs_res_ms"] <= hi, (name, rendered[name])
    lo, hi = REF["res_over_tatum"][1] - 0.006, REF["res_over_tatum"][2]
    assert lo <= rendered[name]["res_over_tatum"] <= hi


@pytest.mark.parametrize("name", PRESET_NAMES)
def test_timing_deviation_is_leptokurtic(name, rendered):
    """Defect D4: round 1 was textbook gaussian (kurtosis +0.058)."""
    _med, lo, hi = REF["res_kurtosis"]
    assert lo <= rendered[name]["res_kurtosis"] <= hi, (name, rendered[name])


@pytest.mark.parametrize("name", PRESET_NAMES)
def test_velocity_sd_is_inside_the_reference_iqr(name, rendered):
    _med, lo, hi = REF["vel_sd"]
    assert lo <= rendered[name]["vel_sd"] <= hi, (name, rendered[name])


@pytest.mark.parametrize("name", PRESET_NAMES)
def test_gate_distribution_is_wide(name, rendered):
    """Defect D6: round 1's gate IQR width was 0.17-0.48 against 2.93."""
    _med, lo, hi = REF["gate_iqr_width"]
    assert lo <= rendered[name]["gate_iqr_width"] <= hi, (name, rendered[name])
    assert 0.45 <= rendered[name]["gate_median"] <= 3.41


def test_gate_covers_staccato_and_overlap():
    ns = melody_line(bars=32)
    humanise(ns, preset("loose"), 120.0, seed=5)
    ratios = gate_ratios(ns)
    assert min(ratios) < 0.5                     # genuinely detached notes
    assert max(ratios) > 1.5                     # and genuinely overlapping ones


def test_release_lengthens_without_reordering():
    base = melody_line(bars=8)
    held = melody_line(bars=8)
    humanise(held, FeelSpec(release_ms=40.0, seed=4), 120.0, seed=8)
    assert all(h.dur >= b.dur for h, b in zip(held, base))
    assert any(h.dur > b.dur for h, b in zip(held, base))
    assert [h.start for h in held] == sorted(h.start for h in held)


def _beat_means(notes, tempo=120.0, bpb=4):
    """Deviations (ms) per beat of the bar, de-drifted bar by bar.

    The agogic tempo curve is a slow common-mode term; removing each bar's own
    mean isolates the metrical profile, which is what this is measuring.
    """
    nominal = melody_line(bars=len(notes) // 16)
    devs = [(n.start - nom.start) * 60000.0 / tempo for n, nom in zip(notes, nominal)]
    beats = [int(math.floor(nom.start % bpb)) + 1 for nom in nominal]
    bars = [int(nom.start // bpb) for nom in nominal]
    bar_mean: dict[int, float] = {}
    for b in set(bars):
        vals = [d for d, bb in zip(devs, bars) if bb == b]
        bar_mean[b] = statistics.fmean(vals)
    per: dict[int, list[float]] = {}
    for d, beat, b in zip(devs, beats, bars):
        per.setdefault(beat, []).append(d - bar_mean[b])
    return per


@pytest.mark.parametrize("name", PRESET_NAMES)
def test_metrical_position_matters(name):
    """Defect D7: round 1 scored KW p=0.60-0.85 with a beat span <= 1.6 ms.

    Measured with the agogic drift switched off, so this isolates the metrical
    profile from the (deliberately larger) passage-level rubato it rides on.
    """
    spec = dataclasses.replace(preset(name), timing_drift_ms=0.0)
    ns = melody_line(bars=48)
    humanise(ns, spec, 120.0, seed=17)
    per = _beat_means(ns)
    means = {b: statistics.fmean(v) for b, v in per.items()}
    span = max(means.values()) - min(means.values())
    assert span > 1.6, (name, means)
    # beat 1 must be distinguishable from beat 4: difference vs. its own error
    a, b = per[1], per[4]
    se = math.sqrt(statistics.variance(a) / len(a) + statistics.variance(b) / len(b))
    assert abs(statistics.fmean(a) - statistics.fmean(b)) > 4.0 * se, (name, means)


@pytest.mark.parametrize("name", PRESET_NAMES)
def test_metrical_profile_survives_the_full_model(name):
    """The profile must still be visible with the drift on — pooled over seeds.

    In any single passage the passage-level rubato is larger than the metrical
    profile (as it is in the reference corpus), so this is a pooled test: the
    beat means over five seeds must still span more than round 1's 1.6 ms.
    """
    per: dict[int, list[float]] = {}
    for seed in (11, 23, 37, 59, 71):
        ns = melody_line(bars=48)
        humanise(ns, preset(name), 120.0, seed=seed)
        for beat, vals in _beat_means(ns).items():
            per.setdefault(beat, []).extend(vals)
    means = {b: statistics.fmean(v) for b, v in per.items()}
    assert max(means.values()) - min(means.values()) > 1.6, (name, means)
    a, b = per[1], per[4]
    se = math.sqrt(statistics.variance(a) / len(a) + statistics.variance(b) / len(b))
    assert abs(statistics.fmean(a) - statistics.fmean(b)) > 2.0 * se, (name, means)


@pytest.mark.parametrize("name", PRESET_NAMES)
def test_velocity_has_a_metrical_accent(name):
    ns = melody_line(bars=48)
    humanise(ns, preset(name), 120.0, seed=19)
    nominal = melody_line(bars=48)
    per: dict[int, list[int]] = {}
    for n, nom in zip(ns, nominal):
        per.setdefault(int(math.floor(nom.start % 4)) + 1, []).append(n.velocity)
    means = {b: statistics.fmean(v) for b, v in per.items()}
    assert max(means.values()) - min(means.values()) > 1.5, (name, means)
    # and a period-2 comb inside the beat (strong 8th vs weak 8th)
    on = [n.velocity for n, nom in zip(ns, nominal)
          if abs(nom.start * 4 % 2) < 1e-9]
    off = [n.velocity for n, nom in zip(ns, nominal)
           if abs(nom.start * 4 % 2 - 1) < 1e-9]
    assert statistics.fmean(on) > statistics.fmean(off)


def test_melody_leads_the_chord():
    """The reference shows the top voice about 5.3 ms early, r = -0.45."""
    notes, nid = [], 0
    for bar in range(64):
        for k, p in enumerate((62, 66, 69, 74)):
            notes.append(Note(start=float(bar) * 2.0, dur=1.0, pitch=p,
                              velocity=80, stave="lh", voice=f"v{k}", id=nid))
            nid += 1
    humanise(notes, preset("loose"), 120.0, seed=21)
    tops, bottoms, spreads = [], [], []
    for bar in range(64):
        grp = sorted(notes[bar * 4:bar * 4 + 4], key=lambda n: n.pitch)
        base = statistics.fmean(n.start for n in grp)
        bottoms.append((grp[0].start - base) * 500.0)
        tops.append((grp[-1].start - base) * 500.0)
        spreads.append((max(n.start for n in grp) - min(n.start for n in grp)) * 500.0)
    assert statistics.fmean(tops) < -1.5                 # the melody is early
    assert statistics.fmean(tops) < statistics.fmean(bottoms)
    _med, lo, hi = REF["chord_spread_ms"]
    assert lo * 0.75 <= statistics.median(spreads) <= hi * 1.25


def test_chord_notes_share_the_beat_shift_but_spread_inside_it():
    notes = [Note(start=4.0, dur=1.0, pitch=p, velocity=80, stave="lh",
                  voice=f"v{i}", id=i) for i, p in enumerate((48, 52, 55, 59))]
    humanise(notes, preset("loose"), seed=6)
    starts = sorted(n.start for n in notes)
    spread_ms = (starts[-1] - starts[0]) * 60000.0 / TEMPO
    assert 1.0 < spread_ms < 60.0
    assert len({round(n.start, 9) for n in notes}) == 4


# --------------------------------------------------------------------------- #
# 4. units, warnings and absurd values (defects D1, D2)
# --------------------------------------------------------------------------- #

def _sd_for(velocity):
    ns = melody_line(bars=16)
    msgs = humanise(ns, FeelSpec(velocity=velocity, seed=1), 120.0, seed=1)
    return statistics.pstdev([n.velocity for n in ns]), msgs


def test_no_unit_cliff_at_one():
    """Defect D1: round 1 gave sd 49.2 for 0.99 and 1.04 for 1.01 (a 47x cliff)."""
    sd99, m99 = _sd_for(0.99)
    sd100, m100 = _sd_for(1.0)
    sd101, m101 = _sd_for(1.01)
    assert sd99 > 10.0 and sd100 > 10.0
    assert abs(sd100 - sd99) / sd99 < 0.25          # continuous through 1.0
    assert abs(sd101 - sd100) < 1e-9                # 1.01 is clamped to 1.0
    assert any("ambiguous" in m and "1.01" in m for m in m101)
    assert not any("ambiguous" in m for m in m99 + m100)


def test_percent_strings_are_explicit_and_400_percent_is_not_4_percent():
    """Defect D1: round 1 read '400%' as 4 % without a word."""
    sd12, m12 = _sd_for("12%")
    sd012, _ = _sd_for(0.12)
    assert abs(sd12 - sd012) < 1e-9
    assert m12 == []
    sd400, m400 = _sd_for("400%")
    sd100, _ = _sd_for(1.0)
    assert abs(sd400 - sd100) < 1e-9                       # 400 % -> clamp to 100 %
    assert any("above the maximum 100%" in m for m in m400)
    sd_pct, _ = _sd_for("12pct")
    assert abs(sd_pct - sd012) < 1e-9


def test_bare_number_above_one_is_reported_not_guessed():
    _sd, msgs = _sd_for(4.0)
    assert any("ambiguous" in m and "4" in m for m in msgs)
    assert any("4%" in m or "0.04" in m for m in msgs)


def test_nan_and_inf_are_refused_by_name():
    for bad in (float("nan"), float("inf"), float("-inf")):
        ns = melody_line(bars=4)
        msgs = humanise(ns, FeelSpec(timing_ms=bad, velocity=0.1, seed=1),
                        120.0, seed=1)
        assert any("timing" in m for m in msgs), (bad, msgs)
        assert all(n.start == n.start and n.dur == n.dur for n in ns)
        assert all(math.isfinite(n.start) and math.isfinite(n.dur) for n in ns)


def test_warnings_name_the_parameter_and_the_value():
    ns = melody_line(bars=4)
    msgs = humanise(ns, FeelSpec(timing_ms=2000.0, seed=1), 120.0, seed=1)
    assert any("timing" in m and "2000" in m and "500" in m for m in msgs)


def test_warnings_are_python_warnings_by_default():
    ns = melody_line(bars=4)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        apply_feel(ns, FeelSpec(timing_ms=9000.0, seed=1), 120.0, seed=1)
    assert any(issubclass(w.category, FeelWarning) for w in caught)
    assert any("timing" in str(w.message) for w in caught)


@pytest.mark.parametrize("spec", [
    FeelSpec(timing_ms=2000.0, velocity=4.0, gate=9.0, onset_ms=2000.0,
             release_ms=2000.0, seed=1),
    FeelSpec(timing_ms=-2000.0, timing_dist="flat", seed=1),
    FeelSpec(timing_ms=1e9, velocity=1e9, seed=1),
    FeelSpec(timing_ms=500.0, onset_ms=250.0, max_shift_ratio=4.0, seed=1),
])
def test_absurd_values_never_break_the_music(spec):
    """Defect D2: no reordering, no pile-up at t=0, no runaway ends, no NaN."""
    ns = melody_line(bars=16)
    nominal = melody_line(bars=16)
    piece_end = max(n.start + n.dur for n in nominal)
    pitches = sorted(n.pitch for n in ns)
    humanise(ns, spec, 120.0, seed=5)
    order = [n.start for n in ns]
    assert order == sorted(order)                                  # no reordering
    assert sum(1 for s in order if s == 0.0) <= 1                  # no stack at 0
    assert max(n.start + n.dur for n in ns) <= piece_end + 4.0     # bounded tail
    assert all(math.isfinite(n.start) and math.isfinite(n.dur) for n in ns)
    assert all(n.dur > 0.0 and n.start >= 0.0 for n in ns)
    assert sorted(n.pitch for n in ns) == pitches
    assert all(1 <= n.velocity <= 127 for n in ns)


def test_unknown_distribution_is_named_and_falls_back():
    ns = melody_line(bars=4)
    msgs = humanise(ns, FeelSpec(timing_ms=20.0, timing_dist="triangular", seed=1),
                    120.0, seed=1)
    assert any("triangular" in m and "not a known distribution" in m for m in msgs)


def test_identical_duplicate_notes_decorrelate():
    """64 exactly identical notes must not become 64 copies of one draw."""
    ns = [Note(start=1.0, dur=0.25, pitch=60, velocity=90, stave="rh",
               voice="v", id=i) for i in range(64)]
    humanise(ns, preset("loose"), 120.0, seed=2)
    assert len({round(n.start, 9) for n in ns}) > 8
    assert len({n.velocity for n in ns}) > 4
    assert len({round(n.dur, 9) for n in ns}) > 8


# --------------------------------------------------------------------------- #
# 5. presets and the legibility of the model
# --------------------------------------------------------------------------- #

def test_presets_exist_and_are_valid():
    assert set(F.PRESETS) == set(PRESET_NAMES)
    for name, params in F.PRESETS.items():
        assert isinstance(params, dict)
        spec = preset(name)
        assert isinstance(spec, FeelSpec)
        assert spec.timing_ms != 0.0
    # "tight" is tighter in every structural dimension.  Note it is *not*
    # tighter in `timing_ms` alone: the per-note sd is only one term of the
    # timing model now, and the drift term is the dominant one.
    for key in ("timing_drift_ms", "velocity", "onset_ms", "gate", "gate_spread"):
        assert F.TIGHT[key] < F.LOOSE[key], key
    assert F.BREATH["release_ms"] > F.TIGHT["release_ms"]
    with pytest.raises(KeyError):
        preset("nope")


def test_the_model_is_legible_in_the_preset_syntax():
    """Every structural parameter is a named field, not a hidden constant."""
    fields = set(FeelSpec.__dataclass_fields__)
    for key in ("timing_df", "timing_ar", "timing_drift_ms", "timing_drift_span",
                "timing_swell", "timing_profile_ms", "timing_period2_ms",
                "velocity_ar", "accent_profile", "accent_period2",
                "articulation", "gate_center", "gate_spread", "gate_ar",
                "melody_lead_ms", "max_shift_ratio", "beats_per_bar"):
        assert key in fields, key
    for name in PRESET_NAMES:
        params = F.PRESETS[name]
        for key in ("timing_ar", "velocity_ar", "timing_drift_ms", "timing_swell",
                    "accent_profile", "timing_profile_ms", "articulation",
                    "melody_lead_ms"):
            assert key in params, (name, key)
        assert set(params) <= fields, (name, set(params) - fields)


def test_pushed_anticipates_the_beat_gradually():
    """Round 1's `pushed` was a two-spike on/off switch; it is now graded."""
    assert F.PUSHED["timing_dist"] != "flat"
    assert F.PUSHED.get("on_beats", ()) == ()
    ns = melody_line(bars=32)
    humanise(ns, preset("pushed"), 120.0, seed=3)
    per = _beat_means(ns)
    means = {b: statistics.fmean(v) for b, v in per.items()}
    assert min(means.values()) < -3.0                     # some beats are early
    assert len({round(v, 3) for v in means.values()}) == 4  # graded, not on/off


def test_auto_fields_supply_the_structure_for_a_plain_feel_block():
    """`feel { timing: 16ms }` — all parse.py accepts today — still gets memory."""
    spec = FeelSpec(timing_ms=16.0, velocity=0.09, gate=0.05, onset_ms=6.0, seed=3)
    assert spec.velocity_ar is AUTO
    p, _msgs = normalise(spec, lambda m: None)
    assert p.vel_ar > 0.2
    assert p.timing_ar > 0.1
    assert p.drift_ms > 0.0
    assert p.accent and p.timing_profile
    assert p.lead_ms != 0.0


def test_a_zero_spec_stays_a_no_op_despite_auto_defaults():
    p, msgs = normalise(FeelSpec(), lambda m: None)
    assert not p.active
    assert msgs == []


@pytest.mark.parametrize("name", PRESET_NAMES)
def test_preset_reports_its_measured_numbers(name, rendered, capsys):
    """Not an assertion so much as the report the verdict asked for."""
    r = rendered[name]
    print(f"{name}: |res|={r['abs_res_ms']:.2f} ms  kurt={r['res_kurtosis']:+.2f}  "
          f"vel sd={r['vel_sd']:.2f}  vel lag-1 r={r['vel_lag1_r']:+.3f}  "
          f"res lag-1 r={r['res_lag1_r']:+.3f}  "
          f"gate {r['gate_median']:.2f} (IQR width {r['gate_iqr_width']:.2f})")
    assert r["res_lag1_r"] > 0.2            # timing has memory too


# --------------------------------------------------------------------------- #
# 6. the re-derived ground truth is documented and reproducible
# --------------------------------------------------------------------------- #

def test_feel_truth_document_exists_and_matches_the_constants():
    path = os.path.join(ROOT, "refs", "specs", "feel_truth.md")
    text = open(path).read()
    assert "maestro" in text.lower()
    for token in ("8.32", "5.64", "11.86", "0.452", "2.93", "16.93"):
        assert token in text, token
    assert "stats.json" in text          # says why it is not the source of truth


def test_reference_corpus_present():
    """The corpus provenance must be documented, and present if it was fetched.

    The MAESTRO excerpts themselves are CC BY-NC-SA 4.0 and are deliberately not
    redistributed with this MIT-licensed source tree, so a fresh clone has the
    provenance document but not the audio-derived MIDI.  ``SOURCES.md`` carries
    the archive URL, its checksum and the per-file paths needed to re-create the
    corpus; once you have, this test checks it is intact.
    """
    src = os.path.join(ROOT, "refs", "midi", "SOURCES.md")
    text = open(src).read()
    assert "CC BY-NC-SA 4.0" in text
    n_mid = len([f for f in os.listdir(os.path.join(ROOT, "refs", "midi"))
                 if f.endswith(".mid")])
    if n_mid == 0:
        pytest.skip("MAESTRO corpus not present locally — see refs/midi/SOURCES.md")
    assert n_mid >= 5


def test_stats_json_targets_are_superseded_and_we_say_so():
    """The old bar was partly mis-measured; the numbers must not be used blind."""
    with open(os.path.join(ROOT, "refs", "midi", "stats.json")) as fh:
        old = json.load(fh)
    assert "timing_dev_ms" in old["targets"]
    old_lo, old_hi = old["targets"]["timing_dev_ms"]
    assert old_lo > REF["abs_res_ms"][2]      # 30.5 ms vs a re-derived 8.3 ms
    truth = open(os.path.join(ROOT, "refs", "specs", "feel_truth.md")).read()
    assert "timing_dev_ms" in truth


# --------------------------------------------------------------------------- #
# 7. the measurement tool itself (unchanged)
# --------------------------------------------------------------------------- #

def test_chord_spread_measurement():
    notes = [(0.0, 0.5, 60, 90), (0.010, 0.5, 64, 90), (0.030, 0.5, 67, 90),
             (2.0, 0.5, 72, 90)]
    spreads = PS.chord_spreads_ms(PS.as_notes(notes))
    assert len(spreads) == 1
    assert abs(spreads[0] - 30.0) < 1e-6


def test_gate_ratio_measurement():
    notes = [(0.0, 0.25, 60, 90), (0.5, 0.25, 62, 90), (1.0, 0.25, 64, 90),
             (1.5, 0.25, 65, 90)]
    ratios = PS.gate_ratios(PS.as_notes(notes))
    assert ratios and all(abs(r - 0.5) < 1e-9 for r in ratios)


def test_timing_deviation_recovers_a_clean_grid():
    notes = [(i * 0.25, 0.2, 60 + i % 5, 90) for i in range(64)]
    dev = PS.timing_deviations_ms(PS.as_notes(notes))
    assert dev
    assert max(dev) < 1.0
    jittered = [(i * 0.25 + (0.02 if i % 2 else -0.02), 0.2, 60 + i % 5, 90)
                for i in range(64)]
    dev2 = PS.timing_deviations_ms(PS.as_notes(jittered))
    assert statistics.fmean(dev2) > statistics.fmean(dev)


def test_phrase_velocity_sd_measurement():
    a = [(i * 0.2, 0.1, 60, 70 + (10 if i % 2 else -10)) for i in range(12)]
    sds = PS.phrase_velocity_sds(PS.as_notes(a))
    assert len(sds) == 1
    assert 9.0 < sds[0] < 12.0
    b = a + [(20.0 + i * 0.2, 0.1, 60, 90) for i in range(8)]
    assert len(PS.phrase_velocity_sds(PS.as_notes(b))) == 2


def test_beats_to_seconds_roundtrip():
    recs = PS.beats_to_seconds([Note(start=4.0, dur=1.0, pitch=60, velocity=90)], 120.0)
    assert abs(recs[0].start - 2.0) < 1e-12
    assert abs(recs[0].dur - 0.5) < 1e-12


# --------------------------------------------------------------------------- #
# 8. my own estimator, checked against a known answer
# --------------------------------------------------------------------------- #

def test_residual_estimator_recovers_a_known_deviation():
    ns = [Note(start=i * 0.25 + (0.01 if i % 2 else -0.01), dur=0.2,
               pitch=60 + i % 5, velocity=90, stave="rh", id=i) for i in range(64)]
    res, idx, tats = residuals(ns, 120.0)
    assert len(res) > 40
    assert 4.0 < statistics.median(abs(r) for r in res) < 6.0    # 10 ms at 120 bpm
    assert abs(statistics.median(tats) - 125.0) < 2.0
    assert lag1(res, idx) < -0.5                                 # alternating


def test_residual_estimator_finds_nothing_in_a_clean_grid():
    ns = melody_line(bars=8)
    res, _idx, _t = residuals(ns, 120.0)
    assert res
    assert max(abs(r) for r in res) < 1e-6


def test_clamp_at_piece_start_is_not_a_parameter_warning():
    """A ``flat`` push of a few ms moves the beat-0 notes before the piece
    starts; they are clamped to 0, but that is the piece boundary, not the
    parameter, so no 'too large' warning may be raised for it."""
    ns = [Note(start=b * 1.0, dur=0.9, pitch=60 + 12 * v, velocity=90,
               stave="ch", voice=f"v{v}", id=b * 3 + v)
          for b in range(4) for v in range(3)]            # 3 voices x 4 beats
    msgs = humanise(ns, FeelSpec(timing_ms=-6.0, timing_dist="flat", seed=1),
                    132.0, seed=5)
    assert not [m for m in msgs if "timing" in m], msgs
    assert all(n.start >= 0.0 for n in ns)
    assert min(n.start for n in ns) == 0.0               # still clamped


def test_genuinely_oversized_flat_timing_still_warns():
    ns = melody_line(bars=2)
    msgs = humanise(ns, FeelSpec(timing_ms=-900.0, timing_dist="flat", seed=1),
                    120.0, seed=1)
    assert any("timing" in m for m in msgs), msgs
