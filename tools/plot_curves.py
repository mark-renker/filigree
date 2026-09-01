#!/usr/bin/env python3
"""Render the five BAR.md P3 reference gestures to PNGs for eyeball inspection.

    python tools/plot_curves.py [--out refs/plots] [--dpi 130]

Each plot shows the sampled curve exactly as ``gesture.Gesture.sample`` returns
it, in note-lifetime normalised time.  Regions where the lane carries **no
data** (``NaN``) are left blank and shaded, so a critic can see at a glance
that nothing is written outside a gesture's window (BAR.md P3: "no NaN leaking
into written data, no data outside note lifetimes").  Anchor positions are
marked so discontinuities at anchors are visible.

This is a dev tool: it is never imported by library code.
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import matplotlib                                            # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt                              # noqa: E402

from filigree import ir                                      # noqa: E402
from filigree.ast_nodes import (                             # noqa: E402
    BinOp, Breakpoints, Call, GestureDef, Num, Ref, Target, UnOp, Window,
)
from filigree.gesture import Env, GestureCtx, eval_gesture    # noqa: E402

N = 2000
T = np.linspace(0.0, 1.0, N)

LANE_COLOR = {
    "bend": "#7dd3fc",
    "press": "#fca5a5",
    "timbre": "#a7f3d0",
    "amp": "#fcd34d",
}

BG = "#0f1116"
FG = "#e6e8ee"
GRID = "#2a2f3a"


# ---------------------------------------------------------------------------
# helpers for building expression trees by hand
#
# P1's parser is a separate piece; these trees are exactly what it must produce
# for the Filigree source quoted in each title (see refs/syntax/curves.md).
# ---------------------------------------------------------------------------


def bp(*points, shape=None) -> Breakpoints:
    pts = []
    for p in points:
        pts.append(p if isinstance(p, tuple) else (p, None))
    return Breakpoints(points=pts, shape=shape)


def ctx(**kw) -> GestureCtx:
    kw.setdefault("tempo", 120.0)
    kw.setdefault("note_dur_beats", 2.0)      # 1 s notes at 120 bpm
    return GestureCtx(**kw)


EMPTY = Env({})


# ---------------------------------------------------------------------------
# the five reference gestures
# ---------------------------------------------------------------------------


def g1_scoop():
    """1. a 200 ms scoop up into the note from -1 semitone."""
    src = "gesture scoop = bend(-1st -> 0 @ 200ms)"
    expr = Call("bend", [bp(Num(-1.0, "st"), (Num(0.0), Num(200, "ms")))])
    return src, eval_gesture(expr, EMPTY, ctx()), ["bend"], [0.0, 0.2]


def g2_vibrato():
    """2. vibrato that starts 35 % into the note and widens.

    The parentheses matter: `@` binds tighter than `*`, so without them the
    window would apply to the depth envelope alone.
    """
    src = ("gesture vib = bend((wiggle(5.5hz, 0.4st) * ramp(0, 1)) @ 35%..100%)")
    expr = Call("bend", [Window(
        BinOp("scale_or_mul",
              Call("wiggle", [Num(5.5, "hz"), Num(0.4, "st")]),
              Call("ramp", [Num(0.0), Num(1.0)])),
        Num(35, "pct"), Num(100, "pct"))])
    # 4 beats @ 120 bpm = a 2 s note, so 5.5 Hz must show ~11 cycles in the
    # written 65% of the lifetime.
    return src, eval_gesture(expr, EMPTY, ctx(note_dur_beats=4.0)), ["bend"], [0.35]


def g3_swell():
    """3. a swell in pressure while timbre closes."""
    src = ("gesture warm = press(0.15 -> 0.95, shape: exp) "
           "| timbre(0.7 -> 0.25)")
    expr = BinOp("par",
                 Call("press", [bp(Num(0.15), Num(0.95), shape="exp")]),
                 Call("timbre", [bp(Num(0.7), Num(0.25))]))
    return src, eval_gesture(expr, EMPTY, ctx()), ["press", "timbre"], [0.0, 1.0]


def g4_land_on_third():
    """4. a bend that lands exactly on the next chord's third."""
    src = "gesture lift = bend(0 -> >3)"
    # the resolver supplies this callback; +1.6 st == the next chord's third
    # sitting a minor third above the sounding pitch, scaled into the lane.
    c = ctx(resolve_target=lambda t: 1.6)
    expr = Call("bend", [bp(Num(0.0), Target("degree", 3))])
    return src, eval_gesture(expr, EMPTY, c), ["bend"], [0.0, 1.0]


def g5_reuse():
    """5. the same gesture on 12 notes, one parameter changed on note 7."""
    src = ("gesture cry(depth: 0.5st) = bend(0 -> -depth @ 45% -> 0)  ;  "
           "notes!gesture=cry | 0 1 2 3 4 5 6!cry(depth: 1.2st) 7 8 9 ^0 ^1 |")
    d = GestureDef("cry", [("depth", Num(0.5, "st"))],
                   Call("bend", [bp(Num(0.0),
                                    (UnOp("neg", Ref("depth")), Num(45, "pct")),
                                    Num(0.0))]))
    env = Env({"cry": d})
    curves = []
    for i in range(12):
        depth = 1.2 if i == 6 else 0.5
        g = eval_gesture(Call("cry", [], {"depth": Num(depth, "st")}), env, ctx())
        curves.append((i, depth, g))
    return src, curves


# ---------------------------------------------------------------------------
# plotting
# ---------------------------------------------------------------------------


def _style(ax, title, subtitle, ylabel, ylim):
    ax.set_facecolor(BG)
    ax.set_title(title, color=FG, fontsize=12, loc="left", pad=14, weight="bold")
    ax.text(0.0, 1.015, subtitle, transform=ax.transAxes, color="#8b93a7",
            fontsize=8.5, family="monospace", va="bottom")
    ax.set_xlabel("note lifetime  (0 = note-on, 1 = note-off)", color="#8b93a7",
                  fontsize=9)
    ax.set_ylabel(ylabel, color="#8b93a7", fontsize=9)
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(*ylim)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.axhline(0.0 if ylim[0] < 0 else ylim[0], color="#3c4354", linewidth=0.9)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.tick_params(colors="#8b93a7", labelsize=8)


def _shade_no_data(ax, v, ylim):
    """Shade every region where the lane writes nothing (NaN)."""
    nan = np.isnan(v)
    if not nan.any():
        return
    edges = np.diff(nan.astype(int))
    starts = list(np.where(edges == 1)[0] + 1)
    ends = list(np.where(edges == -1)[0] + 1)
    if nan[0]:
        starts = [0] + starts
    if nan[-1]:
        ends = ends + [len(v) - 1]
    for a, b in zip(starts, ends):
        ax.axvspan(T[a], T[b], color="#1b2030", zorder=0)
        ax.text((T[a] + T[b]) / 2.0, ylim[0] + 0.07 * (ylim[1] - ylim[0]),
                "no data", ha="center", color="#5b6478", fontsize=8,
                family="monospace")


def measured_hz(v: np.ndarray, dur_sec: float) -> float | None:
    """Rate of the plotted curve, measured from its own descending zero crossings.

    Captions are generated with this rather than written by hand, so a caption
    cannot claim a rate the picture does not show.
    """
    d = np.asarray(v, dtype=float)
    ok = np.isfinite(d[:-1]) & np.isfinite(d[1:])
    idx = np.where(ok & (d[:-1] > 0.0) & (d[1:] <= 0.0))[0]
    if idx.size < 2:
        return None
    zeros = T[idx] * dur_sec
    return float(1.0 / np.mean(np.diff(zeros)))


def plot_single(path, title, src, gesture, lanes, anchors, caption=None):
    fig, ax = plt.subplots(figsize=(8.4, 3.5), dpi=130)
    fig.patch.set_facecolor(BG)
    bipolar = any(l in ir.BIPOLAR for l in lanes)
    ylim = (-2.2, 2.2) if bipolar else (-0.05, 1.05)
    ylabel = "semitones" if bipolar else "0..1"
    _style(ax, title, src.replace("\n", " ; "), ylabel, ylim)

    first = True
    for lane in lanes:
        v = gesture.sample(lane, T)
        if v is None:
            continue
        if first:
            _shade_no_data(ax, v, ylim)
            first = False
        ax.plot(T, v, color=LANE_COLOR.get(lane, "#c4b5fd"), linewidth=2.0,
                label=lane, solid_capstyle="round")
        finite = np.isfinite(v)
        if finite.any():
            ax.scatter(T[finite][[0, -1]], v[finite][[0, -1]], s=18, zorder=5,
                       color=LANE_COLOR.get(lane, "#c4b5fd"),
                       edgecolor=BG, linewidth=0.8)
    for a in anchors:
        ax.axvline(a, color="#4b5468", linewidth=0.8, linestyle=(0, (3, 3)))
    leg = ax.legend(loc="upper right", frameon=False, fontsize=9)
    for t in leg.get_texts():
        t.set_color(FG)
    if caption:
        lines = []
        for para in caption.split("\n"):
            lines.extend(textwrap.wrap(para, 96) or [""])
        fig.set_size_inches(8.4, 3.5 + 0.16 * len(lines))
        fig.tight_layout(rect=(0, 0.055 * len(lines), 1, 1))
        fig.text(0.012, 0.012, "\n".join(lines), color="#7f8899", fontsize=8,
                 family="monospace", va="bottom")
    else:
        fig.tight_layout()
    fig.savefig(path, facecolor=BG)
    plt.close(fig)
    return path


def plot_reuse(path, title, src, curves):
    """Twelve consecutive notes, each carrying the same gesture, laid out in bar
    time so the one changed parameter is visible against its neighbours."""
    n = len(curves)
    gate = 0.82                       # notes sound 82% of their slot
    fig, ax = plt.subplots(figsize=(9.6, 3.6), dpi=130)
    fig.patch.set_facecolor(BG)
    _style(ax, title, src, "bend  (semitones)", (-1.45, 0.35))
    ax.set_xlim(0.0, float(n))
    ax.set_xlabel("bar time  (12 slots, one note per slot)", color="#8b93a7",
                  fontsize=9)
    ax.set_xticks([i + 0.5 for i in range(n)])
    ax.set_xticklabels([str(i + 1) for i in range(n)])
    ax.grid(False)
    ax.grid(True, axis="y", color=GRID, linewidth=0.6)
    for i, depth, g in curves:
        changed = depth != 0.5
        x = i + T * gate
        v = g.sample("bend", T)
        ax.axvspan(i, i + gate, color="#171b25" if not changed else "#241a24",
                   zorder=0)
        ax.plot(x, v, color="#f472b6" if changed else "#7dd3fc",
                linewidth=2.4 if changed else 1.6,
                zorder=5 if changed else 3,
                label=("note 7  !cry(depth: 1.2st)" if changed else None))
        ax.plot([i + 0.45 * gate], [-depth], marker="o", markersize=4,
                color="#f472b6" if changed else "#7dd3fc", zorder=6)
    ax.plot([], [], color="#7dd3fc", linewidth=1.6,
            label="notes 1-6, 8-12  cry() default depth 0.5st")
    leg = ax.legend(loc="lower left", frameon=False, fontsize=9, ncol=2)
    for t in leg.get_texts():
        t.set_color(FG)
    fig.tight_layout()
    fig.savefig(path, facecolor=BG)
    plt.close(fig)
    return path


def _glyph_panel(ax, spec, resolve=None, label_row=2.6):
    """Draw one glyph string on ``ax`` and return its sampled values."""
    from filigree.gesture import curve_from_string, parse_glyph_string

    c = ctx(lane_default="bend", lane_range=ir.LANE_RANGES["bend"],
            resolve_target=resolve or (lambda t: 1.2))
    g = curve_from_string(spec, "bend", c)
    v = g.sample("bend", T)
    _shade_no_data(ax, v, (-2.3, 2.3))
    ax.plot(T, v, color=LANE_COLOR["bend"], linewidth=2.0, label="bend")
    ax.axhline(label_row - 0.15, color=GRID, linewidth=0.8)
    for (s, e, slot) in parse_glyph_string(spec):
        ax.axvline(e, color="#242a36", linewidth=0.7)
        if slot.kind == "empty":
            label = "␣"
        elif slot.target is not None:
            label = ">" + (str(slot.target.degree) if slot.target.degree else "")
        else:
            label = slot.glyph + ("" if slot.glyph_arg is None
                                  else str(int(slot.glyph_arg)))
        ax.text((s + e) / 2.0, label_row, label, ha="center", color="#c9cfdd",
                fontsize=11, family="monospace")
    ax.set_ylabel("bend  (semitones)", color="#8b93a7", fontsize=9)
    return v


def plot_glyph_lane(path):
    """Bonus: the drawn glyph lane of SPEC §7, including a no-data hole."""
    spec = "___/^^^ ^^\\_>3"
    fig, ax = plt.subplots(figsize=(8.4, 3.5), dpi=130)
    fig.patch.set_facecolor(BG)
    ylim = (-2.3, 3.0)          # headroom for the glyph label row
    _style(ax, "SPEC §7 drawn glyph lane", f'bend | {spec} |', "semitones", ylim)
    ax.set_yticks([-2, -1, 0, 1, 2])
    v = _glyph_panel(ax, spec)
    cap = (f"rendered on a 1.0 s note, 12 equal slots: {np.nanmin(v):+.2f} .. "
           f"{np.nanmax(v):+.2f} st, inside the ±2 st bend lane. The blank "
           f"slot writes nothing (NaN, shaded) instead of interpolating "
           f"across it;\nthe final `>3` slot lands on the value "
           f"ctx.resolve_target gives for the next chord's third "
           f"({v[-1]:+.2f} st here).")
    lines = [l for para in cap.split("\n") for l in textwrap.wrap(para, 96)]
    fig.set_size_inches(8.4, 3.5 + 0.16 * len(lines))
    fig.tight_layout(rect=(0, 0.055 * len(lines), 1, 1))
    fig.text(0.012, 0.012, "\n".join(lines), color="#7f8899", fontsize=8,
             family="monospace", va="bottom")
    fig.savefig(path, facecolor=BG)
    plt.close(fig)
    return path


def plot_glyph_lane_range(path):
    """Lane-range discipline: `~` compresses at a boundary instead of clipping."""
    specs = ["4~", "8~", "^~"]
    fig, axes = plt.subplots(1, 3, figsize=(11.0, 3.4), dpi=130)
    fig.patch.set_facecolor(BG)
    lo, hi = ir.LANE_RANGES["bend"]
    caps = []
    for ax, spec in zip(axes, specs):
        _style(ax, f"bend | {spec} |", "", "semitones", (-2.4, 2.9))
        ax.set_yticks([-2, -1, 0, 1, 2])
        ax.set_xlabel("note lifetime", color="#8b93a7", fontsize=8)
        for y in (lo, hi):
            ax.axhline(y, color="#8b5cf6", linewidth=1.0, linestyle=(0, (2, 2)))
        v = _glyph_panel(ax, spec, label_row=2.5)
        ax.legend().remove()
        caps.append(f"{spec}: {np.nanmin(v):+.3f} .. {np.nanmax(v):+.3f} st "
                    f"(mean {np.nanmean(v):+.3f})")
    fig.suptitle("Lane-range discipline — `~` compresses to the available "
                 "headroom; it never leaves the ±2 st bend lane (dashed)",
                 color=FG, fontsize=11, x=0.008, ha="left", weight="bold")
    body = ("   ·   ".join(caps) + "\n`^~` sits exactly at the lane top, so it "
            "has no headroom left and renders as a flat hold rather than a "
            "clipped, distorted wiggle.")
    fig.text(0.008, 0.012, "\n".join(
        l for para in body.split("\n") for l in textwrap.wrap(para, 128)),
        color="#7f8899", fontsize=8, family="monospace", va="bottom")
    fig.tight_layout(rect=(0, 0.15, 1, 0.90))
    fig.savefig(path, facecolor=BG)
    plt.close(fig)
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(_ROOT, "refs", "plots"))
    ap.add_argument("--dpi", type=int, default=130)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    matplotlib.rcParams["savefig.dpi"] = args.dpi

    written = []

    # -- P3.1 -------------------------------------------------------------
    src, g, lanes, anchors = g1_scoop()
    v = g.sample("bend", T)
    at200 = float(np.interp(0.2, T, v))
    at200 = 0.0 if abs(at200) < 5e-3 else at200
    cap = (f"rendered on a 1.0 s note: {v[0]:+.2f} st at note-on, "
           f"{at200:+.2f} st at 200 ms (dashed), then held to note-off. "
           f"shape = ease (smoothstep); nothing is unwritten.")
    written.append(plot_single(os.path.join(args.out, "p3_1_scoop.png"),
                              "P3.1 — 200 ms scoop up from −1 semitone",
                              src, g, lanes, anchors, cap))

    # -- P3.2 -------------------------------------------------------------
    src, g, lanes, anchors = g2_vibrato()
    v = g.sample("bend", T)
    dur = 2.0                                   # 4 beats @ 120 bpm
    hz = measured_hz(v, dur)
    late = float(np.nanmax(np.abs(v[T > 0.9])))
    early = float(np.nanmax(np.abs(v[(T > 0.35) & (T < 0.45)])))
    cap = (f"rendered on a {dur:.1f} s note: measured {hz:.2f} Hz from zero "
           f"crossings (written 5.5hz), ±{early:.2f} st just after the 35 % "
           f"onset growing to ±{late:.2f} st at note-off.\n"
           f"@ 35%..100% restricts (SPEC §8): before 35 % the lane is unwritten, "
           f"and the wiggle keeps absolute Hz with phase 0 at the window open.")
    written.append(plot_single(os.path.join(args.out, "p3_2_vibrato.png"),
                              "P3.2 — vibrato from 35 %, widening",
                              src, g, lanes, anchors, cap))

    # -- P3.3 -------------------------------------------------------------
    src, g, lanes, anchors = g3_swell()
    p = g.sample("press", T)
    tb = g.sample("timbre", T)
    mid = float(np.interp(0.5, T, p))
    lin = 0.15 + 0.5 * (0.95 - 0.15)
    tmid = float(np.interp(0.5, T, tb))
    cap = (f"rendered on a 1.0 s note: press {p[0]:.2f}→{p[-1]:.2f} with "
           f"shape: exp — {mid:.3f} at the midpoint vs {lin:.3f} for a "
           f"straight line, i.e. it holds back early and accelerates into "
           f"note-off.\n"
           f"timbre {tb[0]:.2f}→{tb[-1]:.2f} on the default shape (ease / "
           f"smoothstep: {tmid:.3f} at the midpoint, flat at both ends, not a "
           f"straight line), running in parallel on its own lane.")
    written.append(plot_single(os.path.join(args.out, "p3_3_swell.png"),
                              "P3.3 — pressure swells while timbre closes",
                              src, g, lanes, anchors, cap))

    # -- P3.4 -------------------------------------------------------------
    src, g, lanes, anchors = g4_land_on_third()
    v = g.sample("bend", T)
    cap = (f"rendered on a 1.0 s note: {v[0]:+.2f} st → {v[-1]:+.2f} st, the "
           f"value ctx.resolve_target returned for >3 (the third of the chord "
           f"under the next note).\nThe number is never written in the source; "
           f"reharmonise and the landing moves.")
    written.append(plot_single(os.path.join(args.out, "p3_4_target.png"),
                              "P3.4 — bend landing on the next chord's third",
                              src, g, lanes, anchors, cap))
    src, curves = g5_reuse()
    written.append(plot_reuse(os.path.join(args.out, "p3_5_reuse.png"),
                              "P3.5 — one gesture on 12 notes, note 7 retuned",
                              src, curves))
    written.append(plot_glyph_lane(os.path.join(args.out, "p3_6_glyph_lane.png")))
    written.append(plot_glyph_lane_range(
        os.path.join(args.out, "p3_7_lane_range.png")))

    for p in written:
        size = os.path.getsize(p)
        print(f"wrote {os.path.relpath(p, _ROOT)}  ({size} bytes)")
        if size < 4000:
            print("  WARNING: suspiciously small PNG", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
