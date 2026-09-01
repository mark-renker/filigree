#!/usr/bin/env python3
"""Hand-authored fixture generator for the Filigree playground (piece P6).

The Python compiler (lex/parse/resolve) is not usable yet, so this script
hand-builds an ir.Score and dumps `Score.to_json()` verbatim.  It imports the
frozen contract in `src/filigree/ir.py` and NEVER edits it, so the fixture is
guaranteed to match the real schema byte-for-byte in shape.

Run:  python web/fixtures/make_fixture.py
Out:  web/fixtures/score.json   (paired with web/fixtures/source.fil)
"""

from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from filigree.ir import Curve, ChordEvent, Note, Score, StaveIR  # noqa: E402

# ---------------------------------------------------------------- curve maths

def smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def _shape(x: float, shape: str) -> float:
    if shape == "linear":
        return x
    if shape == "hold":
        return 0.0
    if shape == "snap":
        return 1.0 if x >= 1.0 else 0.0
    if shape == "exp":
        return x * x * x
    return smoothstep(x)


def bp(points, shape="ease"):
    """Breakpoint function: points = [(pos 0..1, value), ...] -> f(t)."""
    pts = sorted(points, key=lambda p: p[0])

    def f(t: float) -> float:
        if t <= pts[0][0]:
            return pts[0][1]
        if t >= pts[-1][0]:
            return pts[-1][1]
        for i in range(len(pts) - 1):
            t0, v0 = pts[i]
            t1, v1 = pts[i + 1]
            if t0 <= t <= t1:
                u = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
                return v0 + (v1 - v0) * _shape(u, shape)
        return pts[-1][1]

    return f


def wiggle(rate_hz, depth, onset=0.0, dur_sec=1.0, widen=True):
    """Vibrato that fades in after `onset` (fraction of note) and widens."""
    def f(t: float) -> float:
        if t < onset:
            return 0.0
        span = max(1e-6, 1.0 - onset)
        u = (t - onset) / span
        env = smoothstep(min(1.0, u * 2.2))
        if widen:
            env *= 0.45 + 0.55 * u
        return depth * env * math.sin(2 * math.pi * rate_hz * dur_sec * (t - onset))
    return f


def drift(depth, seed, octaves=3):
    """Deterministic smooth value-noise, so the fixture is reproducible."""
    def h(i: int) -> float:
        x = (i * 2654435761 + seed * 40503 + 12345) & 0xFFFFFFFF
        x ^= x >> 15
        x = (x * 2246822519) & 0xFFFFFFFF
        x ^= x >> 13
        return (x & 0xFFFF) / 65535.0 * 2.0 - 1.0

    def f(t: float) -> float:
        v = 0.0
        amp = 1.0
        freq = 3.0
        for o in range(octaves):
            p = t * freq
            i = int(math.floor(p))
            a, b = h(i + o * 977), h(i + 1 + o * 977)
            v += amp * (a + (b - a) * smoothstep(p - i))
            amp *= 0.5
            freq *= 2.0
        return depth * v * 0.62
    return f


def add(*fns):
    return lambda t: sum(f(t) for f in fns)


def sample(fn, start, dur, n, lo, hi, thin=0.004):
    """Sample fn over the note lifetime into absolute-beat (t, v) points."""
    raw = []
    for i in range(n + 1):
        t = i / n
        v = max(lo, min(hi, fn(t)))
        raw.append((start + t * dur, v))
    out = [raw[0]]
    for i in range(1, len(raw) - 1):
        if abs(raw[i][1] - out[-1][1]) >= thin:
            out.append(raw[i])
    out.append(raw[-1])
    return out


# ------------------------------------------------------------------- harmony

MAJ = "maj7"
CH = [
    # bar, symbol, root_pc, quality, voiced pitches (C3..C5), pcs, guide tones
    ("i9",    0, "min9",  [48, 55, 58, 62, 63], [0, 3, 7, 10, 2], [3, 10]),
    ("VI^7",  8, "maj7",  [44, 55, 60, 63],     [8, 0, 3, 7],     [0, 7]),
    ("iv11",  5, "min11", [41, 51, 56, 60, 63], [5, 8, 0, 3, 10], [8, 3]),
    ("V7alt", 7, "7alt",  [43, 53, 56, 59, 61], [7, 11, 5, 8, 1], [11, 5]),
    ("i9",    0, "min9",  [48, 55, 58, 62, 63], [0, 3, 7, 10, 2], [3, 10]),
    ("bVII^7", 10, "maj7", [46, 53, 57, 60],    [10, 2, 5, 9],    [2, 9]),
    ("ii0",   2, "min7b5", [38, 48, 53, 56],    [2, 5, 8, 0],     [5, 0]),
    ("V7alt", 7, "7alt",  [43, 53, 56, 59, 61], [7, 11, 5, 8, 1], [11, 5]),
]

TEMPO = 84.0
SPB = 60.0 / TEMPO           # seconds per beat


def chords_for(stave):
    out = []
    for i, (sym, root, qual, pitches, pcs, guides) in enumerate(CH):
        out.append(ChordEvent(start=i * 4.0, dur=4.0, symbol=sym, root_pc=root,
                              quality=qual, pitches=list(pitches),
                              pitch_classes=list(pcs), guide_tones=list(guides),
                              stave=stave))
    return out


_nid = [1]


def note(stave, voice, start, dur, pitch, vel, curves, detune=0.0, chan=None):
    n = Note(start=start, dur=dur, pitch=pitch, velocity=vel, stave=stave,
             voice=voice, detune=detune, channel=chan, id=_nid[0])
    _nid[0] += 1
    cv = {}
    for lane, fn in curves.items():
        lo, hi = (-2.0, 2.0) if lane == "bend" else (0.0, 1.0)
        npts = 40 if lane == "bend" else 20
        cv[lane] = Curve(lane=lane, points=sample(fn, start, dur, npts, lo, hi,
                                                  thin=0.006 if lane == "bend" else 0.012))
    n.curves = cv
    return n


# ---------------------------------------------------------------------- lead
# 8-bar melody in C minor: scoops, vibrato, harmonic-target glides (`>3`, `>7`).

def build_lead():
    st = StaveIR(name="lead", channel_group=1)
    st.chords = chords_for("lead")
    L = "lead"
    ch = 2

    def sec(dur):  # note duration in seconds, for vibrato rates
        return dur * SPB

    spec = [
        # (start, dur, pitch, vel, kind)
        (0.0, 1.5, 72, 96, "scoop"),        # C5  — scoop up into the note
        (1.5, 0.5, 74, 78, "plain"),        # D5
        (2.0, 2.0, 75, 104, "vib"),         # Eb5 — vibrato that widens
        (4.0, 1.0, 79, 100, "fall"),        # G5  -> glide to Ab^7 3rd (C)
        (5.0, 1.0, 77, 84, "swell"),        # F5
        (6.0, 2.0, 75, 92, "vib"),          # Eb5
        (8.0, 1.5, 77, 98, "scoop"),        # F5
        (9.5, 0.5, 79, 82, "plain"),        # G5
        (10.0, 1.0, 80, 106, "cry"),        # Ab5 — cry: dip and recover
        (11.0, 1.0, 79, 90, "fall"),        # G5  -> G7alt guide tone (B)
        (12.0, 2.5, 77, 108, "vibwide"),    # F5  over V7alt
        (14.5, 1.5, 74, 88, "swell"),       # D5
        (16.0, 2.0, 72, 100, "vib"),        # C5  reprise
        (18.0, 1.0, 74, 86, "plain"),       # D5
        (19.0, 1.0, 75, 96, "scoop"),       # Eb5
        (20.0, 2.0, 77, 102, "vib"),        # F5  over bVII^7
        (22.0, 2.0, 79, 94, "fall"),        # G5  -> ii0 guide (F)
        (24.0, 1.5, 80, 104, "cry"),        # Ab5 over ii0
        (25.5, 0.5, 79, 80, "plain"),
        (26.0, 2.0, 77, 98, "vibwide"),     # F5
        (28.0, 3.0, 75, 110, "resolve"),    # Eb5 -> lands on B (V7alt 3rd)
        (31.0, 1.0, 72, 72, "sigh"),        # C5 tail
    ]

    for (s, d, p, v, kind) in spec:
        secs = sec(d)
        if kind == "scoop":
            bend = add(bp([(0.0, -1.0), (0.18, 0.0), (1.0, 0.0)]),
                       wiggle(5.4, 0.16, 0.42, secs), drift(0.05, p))
            press = bp([(0.0, 0.18), (0.22, 0.86), (0.75, 0.72), (1.0, 0.1)])
            timb = bp([(0.0, 0.34), (0.3, 0.62), (1.0, 0.48)])
        elif kind == "vib":
            bend = add(wiggle(5.2, 0.34, 0.3, secs), drift(0.06, p))
            press = bp([(0.0, 0.3), (0.35, 0.9), (0.8, 0.78), (1.0, 0.08)])
            timb = bp([(0.0, 0.42), (0.55, 0.74), (1.0, 0.5)])
        elif kind == "vibwide":
            bend = add(wiggle(6.1, 0.52, 0.22, secs), bp([(0.0, 0.0), (1.0, 0.12)]),
                       drift(0.07, p))
            press = bp([(0.0, 0.24), (0.28, 0.96), (0.7, 0.88), (1.0, 0.06)],)
            timb = bp([(0.0, 0.3), (0.4, 0.82), (1.0, 0.58)])
        elif kind == "fall":
            bend = add(bp([(0.0, 0.0), (0.55, 0.0), (1.0, -1.7)], shape="ease"),
                       wiggle(5.0, 0.1, 0.2, secs))
            press = bp([(0.0, 0.4), (0.4, 0.92), (1.0, 0.16)])
            timb = bp([(0.0, 0.56), (1.0, 0.24)])
        elif kind == "cry":
            bend = add(bp([(0.0, 0.0), (0.32, -0.72), (0.62, 0.06), (1.0, 0.0)]),
                       wiggle(6.4, 0.2, 0.6, secs))
            press = bp([(0.0, 0.5), (0.25, 0.98), (0.6, 0.6), (0.85, 0.86), (1.0, 0.1)])
            timb = bp([(0.0, 0.5), (0.3, 0.9), (0.7, 0.44), (1.0, 0.6)])
        elif kind == "swell":
            bend = add(bp([(0.0, 0.0), (1.0, 0.0)]), drift(0.09, p))
            press = bp([(0.0, 0.06), (0.7, 0.94), (1.0, 0.3)], shape="exp")
            timb = bp([(0.0, 0.28), (1.0, 0.86)])
        elif kind == "resolve":
            bend = add(bp([(0.0, 0.0), (0.4, 0.0), (0.82, 1.9), (1.0, 1.9)]),
                       wiggle(4.6, 0.22, 0.08, secs))
            press = bp([(0.0, 0.34), (0.3, 0.9), (0.85, 0.96), (1.0, 0.12)])
            timb = bp([(0.0, 0.4), (0.5, 0.66), (1.0, 0.92)])
        elif kind == "sigh":
            bend = bp([(0.0, 0.0), (0.5, -0.2), (1.0, -0.85)])
            press = bp([(0.0, 0.42), (0.35, 0.5), (1.0, 0.02)])
            timb = bp([(0.0, 0.46), (1.0, 0.16)])
        else:  # plain
            bend = add(bp([(0.0, -0.22), (0.25, 0.0), (1.0, 0.0)]), drift(0.04, p))
            press = bp([(0.0, 0.26), (0.45, 0.7), (1.0, 0.12)])
            timb = bp([(0.0, 0.48), (1.0, 0.56)])

        st.notes.append(note("lead", "lead", s, d, p, v,
                             {"bend": bend, "press": press, "timbre": timb},
                             detune=0.0, chan=ch))
        ch = 2 + ((ch - 1) % 5)
    return st


# ---------------------------------------------------------------------- keys
# Named voices `mid` / `top` playing the resolved voicings as chords.

def build_keys():
    st = StaveIR(name="keys", channel_group=1)
    st.chords = chords_for("keys")
    rhythm = [(0.0, 2.5), (2.5, 1.5)]      # two hits per bar
    ch = 7
    for bar, (sym, root, qual, pitches, pcs, guides) in enumerate(CH):
        inner = [p for p in pitches if p >= 51][:4]
        if len(inner) < 3:
            inner = pitches[1:5]
        for hi_i, (off, dur) in enumerate(rhythm):
            start = bar * 4.0 + off
            for vi, p in enumerate(inner):
                voice = "top" if vi == len(inner) - 1 else ("mid%d" % (vi + 1))
                vel = 74 - vi * 4 + (6 if hi_i == 0 else -6)
                if voice == "top":
                    vel += 10
                # each voice gets its own swell + a tiny independent drift bend
                press = bp([(0.0, 0.14 + 0.05 * vi),
                            (0.30 + 0.06 * vi, 0.80 - 0.07 * vi),
                            (0.72, 0.58),
                            (1.0, 0.05)])
                timb = bp([(0.0, 0.30 + 0.06 * vi), (0.5, 0.62 + 0.05 * vi),
                           (1.0, 0.40)])
                bend = add(drift(0.14, p * 7 + bar),
                           bp([(0.0, -0.12 if vi == 0 else 0.0), (0.2, 0.0), (1.0, 0.0)]))
                st.notes.append(note("keys", voice, start, dur * 0.94, p, max(30, min(120, vel)),
                                     {"bend": bend, "press": press, "timbre": timb},
                                     detune=(0.06 if vi % 2 else -0.04), chan=ch))
                ch = 7 + ((ch - 6) % 7)
    return st


# ---------------------------------------------------------------------- bass

def build_bass():
    st = StaveIR(name="bass", channel_group=2)
    st.chords = chords_for("bass")
    roots = [36, 32, 29, 31, 36, 34, 38, 31]
    pat = [(0.0, 1.4, 1.0), (1.5, 0.9, 0.86), (2.5, 0.45, 0.7), (3.0, 0.95, 0.92)]
    ch = 14
    for bar, root in enumerate(roots):
        nxt = roots[(bar + 1) % 8]
        for i, (off, dur, gain) in enumerate(pat):
            p = root if i != 2 else root + 7
            last = (i == len(pat) - 1)
            if last:
                # slide of up to a whole tone toward the next bar's root
                delta = max(-2.0, min(2.0, float(nxt - p)))
                target = 0.0 if abs(delta) > 2.0 else delta
                bend = bp([(0.0, 0.0), (0.6, 0.0), (1.0, target)])
            else:
                bend = add(bp([(0.0, -0.35), (0.14, 0.0), (1.0, 0.0)]), drift(0.05, p + bar))
            press = bp([(0.0, 0.6 * gain), (0.12, 0.95 * gain), (0.6, 0.55 * gain),
                        (1.0, 0.04)], shape="ease")
            timb = bp([(0.0, 0.2), (0.25, 0.46), (1.0, 0.22)])
            st.notes.append(note("bass", "bass", bar * 4.0 + off, dur, p,
                                 int(88 * gain) + 10,
                                 {"bend": bend, "press": press, "timbre": timb},
                                 chan=ch))
            ch = 14 if ch == 16 else ch + 1
    return st


def build_score() -> Score:
    sc = Score(tempo=TEMPO, meter=(4, 4), ppq=960, key=(0, "minor"),
               bend_range=48.0, grid_ms=10.0, seed=7,
               title="Filigree — Cinder Study (8 bars)")
    sc.staves = [build_lead(), build_keys(), build_bass()]
    sc.warnings = [
        "source.fil:31:51: bend lane bar 3 has 6 slots but notes bar 3 has 8 slots; "
        "lane resampled (6 -> 8)",
        "source.fil:39:14: timbre lane bar 5 is empty, so no timbre data is written "
        "for that bar (the instrument's own default stands)",
        "source.fil:47:14: voice 'mid3' is never referenced by an @voice lane; "
        "it inherits the stave-wide press curve",
    ]
    return sc


if __name__ == "__main__":
    score = build_score()
    data = score.to_json()
    out = os.path.join(HERE, "score.json")
    with open(out, "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
        fh.write("\n")
    npts = sum(len(pts) for s in data["staves"] for n in s["notes"]
               for pts in n["curves"].values())
    print("wrote %s  (%d bytes)" % (out, os.path.getsize(out)))
    print("staves=%d notes=%d curvePoints=%d durationBeats=%s" % (
        len(data["staves"]),
        sum(len(s["notes"]) for s in data["staves"]),
        npts, data["durationBeats"]))
