#!/usr/bin/env python3
"""Performance-realism statistics for MIDI files (and for synthetic note lists).

Four statistics, all in the units the P5 quality bar asks for:

1. ``timing_dev_ms``  — |deviation| of each onset from the nearest line of the
   locally estimated metric grid, in milliseconds.
2. ``velocity_sd``    — standard deviation of MIDI velocity *within a phrase*
   (phrases are cut at large onset gaps), one value per phrase.
3. ``gate_ratio``     — note length / inter-onset interval to the next note in
   the same hand-stream (1.0 == perfectly legato, 0.5 == staccato-ish).
4. ``chord_spread_ms``— onset spread (max-min, ms) inside each cluster of
   "simultaneous-ish" notes (>= 2 notes within ``CHORD_WINDOW_S``).

Usage::

    python tools/perf_stats.py refs/midi -o refs/midi/stats.json

The module is import-safe: ``stats_for_notes`` / ``summarise`` take plain
``(start_s, dur_s, pitch, velocity)`` tuples so tests can measure synthetic
notes with exactly the same code path.

Dependencies: standard library + numpy + mido.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

CHORD_WINDOW_S = 0.050      # notes this close count as one chord onset
PHRASE_GAP_S = 0.60        # onset gap that ends a phrase
PHRASE_MIN_NOTES = 4       # phrases shorter than this are skipped
GATE_CLIP = 4.0            # gate ratios are clipped here (tied/held notes)
SUBDIV_MIN_S = 0.070       # fastest grid line spacing considered
SUBDIV_MAX_S = 0.700       # slowest grid line spacing considered
WINDOW_S = 6.0             # length of a local tempo-estimation window

STAT_NAMES = ("timing_dev_ms", "velocity_sd", "gate_ratio", "chord_spread_ms")


# --------------------------------------------------------------------------- #
# note extraction
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class NoteRec:
    start: float      # seconds
    dur: float        # seconds
    pitch: int
    velocity: int


def load_midi_notes(path: str) -> list[NoteRec]:
    """Read a MIDI file into absolute-time notes (seconds). Pedal is ignored."""
    import mido

    mid = mido.MidiFile(path)
    notes: list[NoteRec] = []
    open_notes: dict[tuple[int, int], list[tuple[float, int]]] = {}
    t = 0.0
    for msg in mid:                     # mido iteration yields delta in seconds
        t += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            open_notes.setdefault((msg.channel, msg.note), []).append((t, msg.velocity))
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            stack = open_notes.get((msg.channel, msg.note))
            if stack:
                t0, vel = stack.pop(0)
                notes.append(NoteRec(t0, max(t - t0, 1e-4), msg.note, vel))
    notes.sort(key=lambda n: (n.start, n.pitch))
    return notes


def as_notes(seq: Iterable) -> list[NoteRec]:
    """Accept NoteRec, ir.Note, or (start, dur, pitch, velocity) tuples."""
    out: list[NoteRec] = []
    for item in seq:
        if isinstance(item, NoteRec):
            out.append(item)
        elif hasattr(item, "start") and hasattr(item, "pitch"):
            out.append(NoteRec(float(item.start), float(item.dur),
                               int(item.pitch), int(item.velocity)))
        else:
            s, d, p, v = item
            out.append(NoteRec(float(s), float(d), int(p), int(v)))
    out.sort(key=lambda n: (n.start, n.pitch))
    return out


def beats_to_seconds(notes: Iterable, tempo: float) -> list[NoteRec]:
    """Convert beat-domain notes (ir.Note or tuples) to seconds at ``tempo`` BPM."""
    spb = 60.0 / float(tempo)
    recs = as_notes(notes)
    return [NoteRec(n.start * spb, n.dur * spb, n.pitch, n.velocity) for n in recs]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def onset_clusters(notes: Sequence[NoteRec],
                   window: float = CHORD_WINDOW_S) -> list[list[NoteRec]]:
    """Group notes whose onsets are within ``window`` of the cluster start."""
    clusters: list[list[NoteRec]] = []
    for n in sorted(notes, key=lambda x: x.start):
        if clusters and n.start - clusters[-1][0].start <= window:
            clusters[-1].append(n)
        else:
            clusters.append([n])
    return clusters


def _best_grid(onsets: np.ndarray) -> tuple[float, float]:
    """Estimate (spacing, phase) of the metric grid for one window of onsets.

    Candidate spacings are seeded from the observed inter-onset intervals so the
    search cannot collapse onto an arbitrarily fine grid; each candidate is then
    refined over a +-25% range with a phase sweep, scored by mean squared
    normalised distance to the nearest grid line.
    """
    if onsets.size < 3:
        return (0.25, float(onsets[0]) if onsets.size else 0.0)
    iois = np.diff(onsets)
    iois = iois[(iois > SUBDIV_MIN_S * 0.5) & (iois < SUBDIV_MAX_S * 2.0)]
    seeds = []
    if iois.size:
        med = float(np.median(iois))
        seeds += [med, med * 2.0, med * 0.5, float(np.percentile(iois, 25))]
    seeds += [0.125, 0.25, 0.5]
    cands: list[float] = []
    for s in seeds:
        if not (s > 0) or not math.isfinite(s):
            continue
        for f in np.linspace(0.75, 1.25, 21):
            d = s * f
            if SUBDIV_MIN_S <= d <= SUBDIV_MAX_S:
                cands.append(d)
    if not cands:
        cands = [0.25]
    best = (float("inf"), 0.25, float(onsets[0]))
    for d in cands:
        # closed-form-ish phase sweep
        phases = np.linspace(0.0, d, 25, endpoint=False)
        rel = (onsets[:, None] - phases[None, :]) / d
        dev = np.abs(rel - np.round(rel))          # in grid units, 0..0.5
        score = np.mean(dev ** 2, axis=0)
        i = int(np.argmin(score))
        # prefer coarser grids: a finer grid always fits better, so penalise
        s = float(score[i]) + 0.004 * (SUBDIV_MAX_S / d)
        if s < best[0]:
            best = (s, d, float(phases[i]))
    return (best[1], best[2])


def timing_deviations_ms(notes: Sequence[NoteRec],
                         grid_s: float | None = None) -> list[float]:
    """|deviation| of each chord-onset from the nearest local metric grid line."""
    clusters = onset_clusters(notes)
    onsets = np.array([c[0].start for c in clusters], dtype=float)
    if onsets.size < 3:
        return []
    out: list[float] = []
    t0 = onsets[0]
    while t0 < onsets[-1] + 1e-9:
        sel = onsets[(onsets >= t0) & (onsets < t0 + WINDOW_S)]
        if sel.size >= 3:
            if grid_s is None:
                d, ph = _best_grid(sel)
            else:
                d = grid_s
                phases = np.linspace(0.0, d, 49, endpoint=False)
                rel = (sel[:, None] - phases[None, :]) / d
                ph = float(phases[int(np.argmin(
                    np.mean(np.abs(rel - np.round(rel)) ** 2, axis=0)))])
            rel = (sel - ph) / d
            dev = np.abs(rel - np.round(rel)) * d * 1000.0
            out.extend(float(x) for x in dev)
        t0 += WINDOW_S
    return out


def phrase_velocity_sds(notes: Sequence[NoteRec]) -> list[float]:
    """Velocity standard deviation inside each phrase."""
    notes = sorted(notes, key=lambda n: n.start)
    phrases: list[list[NoteRec]] = [[]]
    prev = None
    for n in notes:
        if prev is not None and n.start - prev > PHRASE_GAP_S:
            phrases.append([])
        phrases[-1].append(n)
        prev = n.start
    out = []
    for ph in phrases:
        if len(ph) >= PHRASE_MIN_NOTES:
            out.append(float(np.std([n.velocity for n in ph], ddof=1)))
    return out


def voice_streams(notes: Sequence[NoteRec],
                  max_leap: int = 14) -> list[list[NoteRec]]:
    """Greedy monophonic voice separation: each note joins the stream whose last
    note is closest in pitch and already (nearly) finished. Keeps a held bass
    note from being paired against a fast right-hand figure."""
    streams: list[list[NoteRec]] = []
    for n in sorted(notes, key=lambda x: (x.start, x.pitch)):
        best, best_cost = None, None
        for s in streams:
            last = s[-1]
            if last.start >= n.start - 1e-6:
                continue
            if last.start + last.dur > n.start + 0.060:
                continue                     # still sounding: different voice
            leap = abs(last.pitch - n.pitch)
            if leap > max_leap:
                continue
            cost = leap + 4.0 * (n.start - last.start)
            if best_cost is None or cost < best_cost:
                best, best_cost = s, cost
        if best is None:
            streams.append([n])
        else:
            best.append(n)
    return streams


def gate_ratios(notes: Sequence[NoteRec]) -> list[float]:
    """dur / IOI to the next note of the same monophonic voice stream."""
    recs = sorted(notes, key=lambda n: (n.start, n.pitch))
    if len(recs) < 4:
        return []
    out: list[float] = []
    for stream in voice_streams(recs):
        for a, b in zip(stream, stream[1:]):
            ioi = b.start - a.start
            if ioi <= 1e-4 or ioi > 2.0:
                continue
            out.append(min(a.dur / ioi, GATE_CLIP))
    return out


def chord_spreads_ms(notes: Sequence[NoteRec]) -> list[float]:
    """Onset spread within each simultaneous-ish cluster of >= 2 notes."""
    out = []
    for c in onset_clusters(notes):
        if len(c) >= 2:
            ts = [n.start for n in c]
            out.append((max(ts) - min(ts)) * 1000.0)
    return out


# --------------------------------------------------------------------------- #
# summarisation
# --------------------------------------------------------------------------- #

def summarise(values: Sequence[float]) -> dict:
    v = np.asarray([x for x in values if math.isfinite(x)], dtype=float)
    if v.size == 0:
        return {"n": 0}
    q1, med, q3 = (float(x) for x in np.percentile(v, [25, 50, 75]))
    return {
        "n": int(v.size),
        "mean": float(np.mean(v)),
        "sd": float(np.std(v, ddof=1)) if v.size > 1 else 0.0,
        "p10": float(np.percentile(v, 10)),
        "q1": q1,
        "median": med,
        "q3": q3,
        "p90": float(np.percentile(v, 90)),
        "iqr": [q1, q3],
    }


def stats_for_notes(notes: Iterable, grid_s: float | None = None) -> dict:
    """All four statistics for one performance (notes in **seconds**)."""
    recs = as_notes(notes)
    return {
        "n_notes": len(recs),
        "timing_dev_ms": summarise(timing_deviations_ms(recs, grid_s=grid_s)),
        "velocity_sd": summarise(phrase_velocity_sds(recs)),
        "gate_ratio": summarise(gate_ratios(recs)),
        "chord_spread_ms": summarise(chord_spreads_ms(recs)),
    }


def raw_for_notes(notes: Iterable, grid_s: float | None = None) -> dict[str, list[float]]:
    recs = as_notes(notes)
    return {
        "timing_dev_ms": timing_deviations_ms(recs, grid_s=grid_s),
        "velocity_sd": phrase_velocity_sds(recs),
        "gate_ratio": gate_ratios(recs),
        "chord_spread_ms": chord_spreads_ms(recs),
    }


def analyse_dir(path: str) -> dict:
    files = sorted(f for f in os.listdir(path)
                   if f.lower().endswith((".mid", ".midi")))
    per_file: dict[str, dict] = {}
    pooled: dict[str, list[float]] = {k: [] for k in STAT_NAMES}
    for f in files:
        recs = load_midi_notes(os.path.join(path, f))
        raw = raw_for_notes(recs)
        per_file[f] = {"n_notes": len(recs),
                       **{k: summarise(v) for k, v in raw.items()}}
        for k, v in raw.items():
            pooled[k].extend(v)
    aggregate = {k: summarise(v) for k, v in pooled.items()}
    medians = {k: summarise([per_file[f][k]["median"] for f in per_file
                             if per_file[f][k].get("n")]) for k in STAT_NAMES}
    return {
        "corpus": os.path.relpath(path),
        "source": "MAESTRO v3.0.0 (CC BY-NC-SA 4.0) — see SOURCES.md",
        "n_files": len(files),
        "definitions": {
            "timing_dev_ms": "|onset - nearest local metric grid line| in ms",
            "velocity_sd": "sd of MIDI velocity within a phrase (gap > %.2fs cuts)" % PHRASE_GAP_S,
            "gate_ratio": "note dur / IOI to next note in same hand-stream, clipped at %.1f" % GATE_CLIP,
            "chord_spread_ms": "max-min onset ms within clusters of >=2 notes inside %.0f ms" % (CHORD_WINDOW_S * 1000),
        },
        "per_file": per_file,
        "aggregate": aggregate,
        "per_file_median_distribution": medians,
        "targets": {k: aggregate[k]["iqr"] for k in STAT_NAMES},
    }


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", help="directory of MIDI files (or a single file)")
    ap.add_argument("-o", "--out", default=None, help="write JSON here")
    args = ap.parse_args(argv)
    if os.path.isdir(args.path):
        data = analyse_dir(args.path)
    else:
        data = {"per_file": {os.path.basename(args.path):
                             stats_for_notes(load_midi_notes(args.path))}}
    text = json.dumps(data, indent=1, sort_keys=False)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(text + "\n")
        for k in STAT_NAMES:
            agg = data.get("aggregate", {}).get(k)
            if agg:
                print(f"{k:16s} n={agg['n']:7d} q1={agg['q1']:.3f} "
                      f"med={agg['median']:.3f} q3={agg['q3']:.3f}")
        print("wrote", args.out)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
