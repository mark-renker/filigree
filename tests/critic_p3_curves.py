"""Independent critic tests for the P3 gesture/curve system.

Written by a fresh-context critic against docs/SPEC.md §7/§8 and the public
claims in refs/syntax/curves.md ONLY.  Nothing here is derived from
NOTES_P3.md or tests/test_gesture.py.

Run:  PYTHONPATH=src python -m pytest tests/critic_p3_curves.py -q
"""

from __future__ import annotations

import math
import os
import subprocess
import sys

import numpy as np
import pytest

from filigree.ast_nodes import BinOp, Breakpoints, Call, Num, Ref, Slot, Target, UnOp, Window
from filigree.errors import GestureError
from filigree.gesture import (
    Env,
    GestureCtx,
    curve_from_string,
    eval_gesture,
    glyphs_to_gesture,
    parse_glyph_string,
)

EMPTY = Env({})
BEND_LO, BEND_HI = -2.0, 2.0


def ctx(dur_beats: float = 2.0, tempo: float = 120.0, **kw) -> GestureCtx:
    """A 1-second note at 120 bpm unless told otherwise."""
    return GestureCtx(note_dur_beats=dur_beats, tempo=tempo, **kw)


def bp(*vals, shape=None, pos=None):
    ps = list(pos) if pos else [None] * len(vals)
    return Breakpoints(points=[(Num(value=v), p) for v, p in zip(vals, ps)], shape=shape)


def lane(name, arg, **kwargs):
    return Call(name=name, args=[arg], kwargs=kwargs)


def ev(expr, c=None):
    return eval_gesture(expr, EMPTY, c or ctx())


def at(g, lane_name, t):
    return g.sample(lane_name, np.asarray([float(t)]))[0]


# ---------------------------------------------------------------------------
# 1. exact primitive values at t = 0 / 0.5 / 1
# ---------------------------------------------------------------------------


def test_ease_breakpoints_exact():
    g = ev(lane("bend", bp(0.0, 1.0)))
    assert at(g, "bend", 0.0) == pytest.approx(0.0, abs=1e-12)
    assert at(g, "bend", 0.5) == pytest.approx(0.5, abs=1e-12)      # smoothstep(0.5)
    assert at(g, "bend", 1.0) == pytest.approx(1.0, abs=1e-12)
    assert at(g, "bend", 0.25) == pytest.approx(0.15625, abs=1e-12)  # f^2(3-2f)


def test_linear_shape_exact():
    g = ev(lane("bend", bp(0.0, 1.0, shape="linear")))
    assert at(g, "bend", 0.25) == pytest.approx(0.25, abs=1e-12)
    assert at(g, "bend", 0.5) == pytest.approx(0.5, abs=1e-12)


def test_exp_shape_matches_documented_formula():
    # curves.md: exp is (e^{3f}-1)/(e^3-1)
    g = ev(lane("press", bp(0.0, 1.0, shape="exp")))
    want = (math.exp(3.0 * 0.5) - 1.0) / (math.exp(3.0) - 1.0)
    assert at(g, "press", 0.5) == pytest.approx(want, abs=1e-12)
    assert at(g, "press", 0.0) == pytest.approx(0.0, abs=1e-12)
    assert at(g, "press", 1.0) == pytest.approx(1.0, abs=1e-12)


def test_hold_and_snap_shapes():
    h = ev(lane("bend", bp(0.0, 1.0, shape="hold")))
    assert at(h, "bend", 0.5) == pytest.approx(0.0, abs=1e-12)   # post-hold
    assert at(h, "bend", 1.0) == pytest.approx(1.0, abs=1e-12)
    s = ev(lane("bend", bp(0.0, 1.0, shape="snap")))
    assert at(s, "bend", 0.5) == pytest.approx(1.0, abs=1e-12)   # pre-jump
    assert at(s, "bend", 0.0) == pytest.approx(0.0, abs=1e-12)


def test_ramp_generator_is_linear_by_default():
    g = ev(lane("bend", Call(name="ramp", args=[Num(value=0.0), Num(value=1.0)], kwargs={})))
    assert at(g, "bend", 0.5) == pytest.approx(0.5, abs=1e-12)
    assert at(g, "bend", 0.25) == pytest.approx(0.25, abs=1e-12)


def test_wiggle_exact_values_and_real_time_rate():
    # 5 Hz, depth 1, 1 s note: peak at 0.05 s, trough at 0.15 s, zero at 0.1 s.
    w = Call(name="wiggle", args=[Num(value=5.0, unit="hz"), Num(value=1.0, unit="st")], kwargs={})
    g = ev(lane("bend", w))
    assert at(g, "bend", 0.0) == pytest.approx(0.0, abs=1e-12)
    assert at(g, "bend", 0.05) == pytest.approx(1.0, abs=1e-9)
    assert at(g, "bend", 0.10) == pytest.approx(0.0, abs=1e-9)
    assert at(g, "bend", 0.15) == pytest.approx(-1.0, abs=1e-9)


def test_pulse_duty():
    p = Call(name="pulse", args=[Num(value=2.0, unit="hz"), Num(value=0.25)], kwargs={})
    g = ev(lane("press", p))
    assert at(g, "press", 0.05) == 1.0
    assert at(g, "press", 0.20) == 0.0
    assert at(g, "press", 0.55) == 1.0


def test_published_scoop_snippet_values():
    # curves.md P3.1: gesture scoop = bend(-1st -> 0 @ 200ms)  on a 1 s note
    g = ev(lane("bend", bp(-1.0, 0.0, pos=[None, Num(value=200, unit="ms")])))
    assert at(g, "bend", 0.0) == pytest.approx(-1.0, abs=1e-12)
    assert at(g, "bend", 0.1) == pytest.approx(-0.5, abs=1e-12)   # smoothstep midpoint
    assert at(g, "bend", 0.2) == pytest.approx(0.0, abs=1e-12)
    assert at(g, "bend", 0.5) == pytest.approx(0.0, abs=1e-12)    # implicit hold to note-off
    assert at(g, "bend", 1.0) == pytest.approx(0.0, abs=1e-12)


def test_no_data_outside_the_note_lifetime():
    g = ev(lane("bend", bp(0.0, 1.0)))
    v = g.sample("bend", np.array([-0.01, 1.01, 2.0]))
    assert np.all(np.isnan(v))


# ---------------------------------------------------------------------------
# 2. glyph lanes: `/` `\` ramp from the previous running value, `x` holds,
#    `~` wiggles around it
# ---------------------------------------------------------------------------


# LEAD AMENDMENT, round 3: SPEC §7 was changed after the P1 ergonomics critic showed that
# `_` meaning *lane minimum* made a drawn "resting" floor play a minor third flat.  `_` now
# means the lane's REST value (0 st on bend) and the new glyph `v` means lane minimum.  The
# four assertions below tested lane-minimum behaviour, so they now use `v`; nothing else in
# this critic file was touched.


def test_slash_ramps_from_previous_running_value():
    g = curve_from_string("v/", "bend", ctx())
    assert at(g, "bend", 0.0) == pytest.approx(BEND_LO, abs=1e-12)
    assert at(g, "bend", 0.5) == pytest.approx(BEND_LO, abs=1e-12)
    assert at(g, "bend", 0.75) == pytest.approx(0.0, abs=1e-9)   # halfway lo->hi
    assert at(g, "bend", 1.0) == pytest.approx(BEND_HI, abs=1e-12)


def test_backslash_ramps_from_previous_running_value():
    g = curve_from_string("^\\", "bend", ctx())
    assert at(g, "bend", 0.5) == pytest.approx(BEND_HI, abs=1e-12)
    assert at(g, "bend", 0.75) == pytest.approx(0.0, abs=1e-9)
    assert at(g, "bend", 1.0) == pytest.approx(BEND_LO, abs=1e-12)


def test_documented_glyph_run_shape():
    # curves.md: "vvv/^^^ is hold-min, ramp across the /, hold-max"
    g = curve_from_string("vvv/^^^", "bend", ctx())
    t = np.linspace(0.0, 3.0 / 7.0, 200)
    assert np.allclose(g.sample("bend", t), BEND_LO)
    t2 = np.linspace(4.0 / 7.0, 1.0, 200)
    assert np.allclose(g.sample("bend", t2), BEND_HI)


def test_x_holds_previous_value_flat():
    g = curve_from_string("9x", "bend", ctx())
    assert at(g, "bend", 0.5) == pytest.approx(BEND_HI, abs=1e-12)
    t = np.linspace(0.5, 1.0, 100)
    assert np.allclose(g.sample("bend", t), BEND_HI)


def test_x_holds_a_mid_level():
    g = curve_from_string("5x", "bend", ctx())
    five = BEND_LO + (5.0 / 9.0) * (BEND_HI - BEND_LO)
    t = np.linspace(0.5, 1.0, 100)
    assert np.allclose(g.sample("bend", t), five, atol=1e-12)


def test_tilde_wiggles_around_the_running_value_not_instead_of_it():
    g = curve_from_string("5~", "bend", ctx())
    five = BEND_LO + (5.0 / 9.0) * (BEND_HI - BEND_LO)
    t = np.linspace(0.5, 1.0, 4001)
    v = g.sample("bend", t)
    assert not np.any(np.isnan(v))
    assert float(np.std(v)) > 0.1                                # actually moving
    # excursion is symmetric about the running value, not about the lane centre
    assert 0.5 * (float(np.min(v)) + float(np.max(v))) == pytest.approx(five, abs=1e-3)


def test_tilde_does_not_bias_the_running_value():
    # a vibrato must not shift the average pitch of the slot it decorates
    g = curve_from_string("5~", "bend", ctx())
    five = BEND_LO + (5.0 / 9.0) * (BEND_HI - BEND_LO)
    v = g.sample("bend", np.linspace(0.5, 1.0, 4001))
    assert float(np.mean(v)) == pytest.approx(five, abs=0.01)


def test_tilde_depth_argument_scales():
    shallow = curve_from_string("5~1", "bend", ctx())
    deep = curve_from_string("5~9", "bend", ctx())
    t = np.linspace(0.5, 1.0, 4001)
    assert float(np.std(deep.sample("bend", t))) > 3.0 * float(
        np.std(shallow.sample("bend", t)))


def test_empty_slot_is_no_data_and_neighbours_stay_written():
    g = curve_from_string("^ ^", "bend", ctx())
    mid = np.linspace(1.0 / 3.0 + 0.02, 2.0 / 3.0 - 0.02, 100)
    assert np.all(np.isnan(g.sample("bend", mid)))
    left = np.linspace(0.0, 1.0 / 3.0 - 0.02, 100)
    right = np.linspace(2.0 / 3.0 + 0.02, 1.0, 100)
    assert not np.any(np.isnan(g.sample("bend", left)))
    assert not np.any(np.isnan(g.sample("bend", right)))


def test_nan_never_leaks_into_a_written_region():
    for s in ("_/^\\_", "___/^^^", "5x9x", "_-^", "9~5x_", "^ ^", "_ / ^"):
        g = curve_from_string(s, "bend", ctx())
        t = np.linspace(0.0, 1.0, 2001)
        v = g.sample("bend", t)
        toks = parse_glyph_string(s)
        for (a, b, slot) in toks:
            if getattr(slot, "kind", None) == "empty":
                continue
            m = (t > a + 1e-3) & (t < b - 1e-3)
            assert not np.any(np.isnan(v[m])), f"NaN inside written slot {a}..{b} of {s!r}"


def test_glyph_curves_stay_inside_the_lane_range():
    # BAR.md P3: "check by eye ... no data outside note lifetimes"; a bend lane
    # is +-2 st by SPEC 3.2, so a drawn curve must not exceed it.
    for s in ("_/^\\_", "___/^^^", "5x9x", "^~", "9~9", "-~9"):
        g = curve_from_string(s, "bend", ctx())
        v = g.sample("bend", np.linspace(0.0, 1.0, 4001))
        v = v[~np.isnan(v)]
        assert float(np.min(v)) >= BEND_LO - 1e-9, f"{s!r} goes below lane min"
        assert float(np.max(v)) <= BEND_HI + 1e-9, f"{s!r} exceeds lane max"


def test_harmonic_target_glyph_ramps_from_previous_and_resolves_once():
    calls = []

    def resolve(tgt):
        calls.append(tgt)
        return 1.5

    c = GestureCtx(note_dur_beats=2.0, lane_range=(BEND_LO, BEND_HI),
                   resolve_target=resolve)
    g = curve_from_string("v>3", "bend", c)
    assert at(g, "bend", 0.5) == pytest.approx(BEND_LO, abs=1e-12)
    assert at(g, "bend", 1.0) == pytest.approx(1.5, abs=1e-12)
    assert len(calls) == 1, "targets must resolve once at eval time, not per sample"


def test_target_on_non_bend_lane_is_rejected():
    c = GestureCtx(note_dur_beats=2.0, resolve_target=lambda t: 1.0)
    with pytest.raises(GestureError):
        curve_from_string("_>3", "press", c)


# ---------------------------------------------------------------------------
# 3. algebra: >> split points, @ window, * scalar vs elementwise
# ---------------------------------------------------------------------------


def _const(lane_name, v):
    return Call(name=lane_name, args=[Num(value=v)], kwargs={})


def test_seq_default_split_is_the_midpoint():
    g = ev(BinOp(op="seq", lhs=_const("bend", 1.0), rhs=_const("bend", -1.0), split=None))
    assert at(g, "bend", 0.25) == pytest.approx(1.0)
    assert at(g, "bend", 0.75) == pytest.approx(-1.0)


def test_seq_explicit_split_point():
    g = ev(BinOp(op="seq", lhs=_const("bend", 1.0), rhs=_const("bend", -1.0),
                 split=Num(value=30, unit="pct")))
    assert at(g, "bend", 0.20) == pytest.approx(1.0)
    assert at(g, "bend", 0.40) == pytest.approx(-1.0)


def test_seq_rescales_each_half_and_matches_the_published_law():
    # curves.md: a >> b == (a @ 0..50%) | (b @ 50%..100%)
    a = lane("bend", bp(0.0, 1.0))
    b = lane("bend", bp(1.0, 0.0))
    seq = ev(BinOp(op="seq", lhs=a, rhs=b, split=None))
    par = ev(BinOp(op="par",
                   lhs=Window(inner=a, start=Num(value=0), end=Num(value=50, unit="pct")),
                   rhs=Window(inner=b, start=Num(value=50, unit="pct"),
                              end=Num(value=100, unit="pct"))))
    t = np.linspace(0.0, 1.0, 501)
    assert np.allclose(seq.sample("bend", t), par.sample("bend", t), equal_nan=True)


def test_window_leaves_the_rest_of_the_lifetime_unwritten():
    g = ev(Window(inner=lane("bend", bp(0.0, 1.0)),
                  start=Num(value=0), end=Num(value=50, unit="pct")))
    assert np.isnan(at(g, "bend", 0.75))
    assert not np.isnan(at(g, "bend", 0.25))


def test_window_restricts_rather_than_rescales_per_SPEC_8():
    # SPEC §8: "a @ x..y  |  restrict to a window of the note lifetime".
    # Restriction means the curve keeps its own shape and is merely masked.
    g = ev(Window(inner=lane("bend", bp(0.0, 1.0, shape="linear")),
                  start=Num(value=0), end=Num(value=50, unit="pct")))
    assert at(g, "bend", 0.25) == pytest.approx(0.25, abs=1e-9)
    assert at(g, "bend", 0.50) == pytest.approx(0.50, abs=1e-9)


def test_window_clips_out_of_range_bounds():
    g = ev(Window(inner=_const("bend", 1.0),
                  start=Num(value=-50, unit="pct"), end=Num(value=150, unit="pct")))
    assert at(g, "bend", 0.0) == pytest.approx(1.0)
    assert at(g, "bend", 1.0) == pytest.approx(1.0)
    assert np.isnan(at(g, "bend", 1.2))


def test_mul_by_scalar_scales_amplitude():
    g = ev(BinOp(op="scale_or_mul", lhs=lane("bend", bp(0.0, 1.0)), rhs=Num(value=2.0)))
    assert at(g, "bend", 1.0) == pytest.approx(2.0, abs=1e-12)
    assert at(g, "bend", 0.5) == pytest.approx(1.0, abs=1e-12)


def test_mul_of_two_gestures_is_elementwise():
    g = ev(BinOp(op="scale_or_mul", lhs=_const("bend", 0.5), rhs=_const("bend", 0.5)))
    assert at(g, "bend", 0.5) == pytest.approx(0.25, abs=1e-12)


def test_mul_absorbs_no_data():
    g = ev(BinOp(op="scale_or_mul",
                 lhs=lane("bend", bp(0.0, 1.0)),
                 rhs=Window(inner=_const("bend", 1.0),
                            start=Num(value=50, unit="pct"),
                            end=Num(value=100, unit="pct"))))
    assert np.isnan(at(g, "bend", 0.25))
    assert not np.isnan(at(g, "bend", 0.75))


def test_add_treats_no_data_as_the_additive_identity():
    g = ev(BinOp(op="add",
                 lhs=lane("bend", bp(0.0, 1.0, shape="linear")),
                 rhs=Window(inner=_const("bend", 1.0),
                            start=Num(value=50, unit="pct"),
                            end=Num(value=100, unit="pct"))))
    assert at(g, "bend", 0.25) == pytest.approx(0.25, abs=1e-9)
    assert at(g, "bend", 0.75) == pytest.approx(1.75, abs=1e-9)


def test_parallel_keeps_lanes_independent():
    g = ev(BinOp(op="par", lhs=lane("press", bp(0.15, 0.95, shape="exp")),
                 rhs=lane("timbre", bp(0.7, 0.25))))
    assert g.lanes() == {"press", "timbre"}
    assert at(g, "press", 0.0) == pytest.approx(0.15)
    assert at(g, "timbre", 1.0) == pytest.approx(0.25)
    assert g.sample("bend", np.array([0.5])) is None


def test_negation_inverts():
    g = ev(UnOp(op="neg", operand=lane("bend", bp(0.0, 1.0))))
    assert at(g, "bend", 1.0) == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# 4. rate primitives must reclock (curves.md: "Hz stay real-time Hz")
# ---------------------------------------------------------------------------


def _first_descending_zero(g, lane_name, t0, t1, n=200001):
    t = np.linspace(t0, t1, n)
    v = g.sample(lane_name, t)
    ok = ~np.isnan(v)
    t, v = t[ok], v[ok]
    for i in range(1, len(v)):
        if v[i - 1] > 0.0 and v[i] <= 0.0:
            return float(t[i])
    return float("nan")


def test_bare_wiggle_reclocks_under_a_window():
    # 5 Hz over a window: first descending zero 0.1 s after the window start.
    w = Call(name="wiggle", args=[Num(value=5.0, unit="hz"), Num(value=1.0, unit="st")],
             kwargs={})
    g = ev(Window(inner=lane("bend", w), start=Num(value=35, unit="pct"),
                  end=Num(value=100, unit="pct")))
    # 1 s note -> lifetime units == seconds
    assert _first_descending_zero(g, "bend", 0.0, 1.0) == pytest.approx(0.45, abs=2e-3)


def test_published_vibrato_snippet_keeps_its_documented_rate():
    # curves.md P3.2: bend(wiggle(5.5hz, 0.4st) * ramp(0, 1) @ 35%..100%)
    # "The window reclocks the wiggle so 5.5 Hz stays 5.5 Hz of real time".
    c = ctx(dur_beats=4.0)   # 2 s note, as plotted in refs/plots/p3_2_vibrato.png
    w = Call(name="wiggle", args=[Num(value=5.5, unit="hz"), Num(value=0.4, unit="st")],
             kwargs={})
    r = Call(name="ramp", args=[Num(value=0.0), Num(value=1.0)], kwargs={})
    g = eval_gesture(
        lane("bend", Window(inner=BinOp(op="scale_or_mul", lhs=w, rhs=r),
                            start=Num(value=35, unit="pct"),
                            end=Num(value=100, unit="pct"))),
        EMPTY, c)
    # first descending zero crossing: half a period (1/11 s) after window start
    want = 0.35 + (1.0 / 11.0) / c.note_dur_sec
    assert _first_descending_zero(g, "bend", 0.30, 1.0) == pytest.approx(want, abs=3e-3)


def test_glyph_wiggle_reclocks_when_the_curve_is_windowed():
    g = curve_from_string("~", "bend", ctx())
    full = _first_descending_zero(g, "bend", 0.0, 1.0)
    w = g.windowed(0.0, 0.5)
    half = _first_descending_zero(w, "bend", 0.0, 0.5)
    # 1 s note: the wiggle occupies 0.5 s of real time after windowing, so its
    # real-time period must be unchanged.
    assert half == pytest.approx(full, abs=2e-3)


# ---------------------------------------------------------------------------
# 5. drift determinism
# ---------------------------------------------------------------------------


def _drift_values(seed_key=("s", 1)):
    c = GestureCtx(note_dur_beats=2.0, lane_range=(BEND_LO, BEND_HI), seed_key=seed_key)
    d = Call(name="drift", args=[Num(value=0.5, unit="st"), Num(value=3.0, unit="hz")],
             kwargs={})
    g = eval_gesture(lane("bend", d), EMPTY, c)
    return g.sample("bend", np.linspace(0.0, 1.0, 33))


def test_drift_is_deterministic_in_process():
    assert np.array_equal(_drift_values(), _drift_values())


def test_drift_depends_on_the_seed_key():
    assert not np.allclose(_drift_values(("s", 1)), _drift_values(("s", 2)))


def test_drift_is_deterministic_across_processes():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = (
        "import numpy as np,sys;sys.path.insert(0,%r);"
        "from filigree.ast_nodes import Call,Num;"
        "from filigree.gesture import Env,GestureCtx,eval_gesture;"
        "c=GestureCtx(note_dur_beats=2.0,lane_range=(-2.0,2.0),seed_key=('s',1));"
        "d=Call(name='drift',args=[Num(value=0.5,unit='st'),Num(value=3.0,unit='hz')],kwargs={});"
        "g=eval_gesture(Call(name='bend',args=[d],kwargs={}),Env({}),c);"
        "print(' '.join('%%.17g'%%x for x in g.sample('bend',np.linspace(0,1,33))))"
        % os.path.join(root, "src")
    )
    env = dict(os.environ)
    outs = []
    for salt in ("1", "2"):
        env["PYTHONHASHSEED"] = salt
        r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                           text=True, env=env, cwd=root)
        assert r.returncode == 0, r.stderr
        outs.append(np.array([float(x) for x in r.stdout.split()]))
    assert np.array_equal(outs[0], outs[1])
    assert np.array_equal(outs[0], np.asarray(_drift_values(("s", 1))))


def test_drift_stays_within_its_depth():
    v = np.asarray(_drift_values())
    assert float(np.max(np.abs(v))) <= 0.5 + 1e-9


# ---------------------------------------------------------------------------
# 6. degenerate inputs
# ---------------------------------------------------------------------------


def test_zero_length_note_does_not_crash_or_emit_nan():
    c = ctx(dur_beats=0.0)
    g = eval_gesture(lane("bend", bp(0.0, 1.0)), EMPTY, c)
    v = g.sample("bend", np.linspace(0.0, 1.0, 51))
    assert not np.any(np.isnan(v))


def test_zero_length_note_wiggle_is_not_a_dead_flat_line():
    c = ctx(dur_beats=0.0)
    w = Call(name="wiggle", args=[Num(value=5.0, unit="hz"), Num(value=1.0, unit="st")],
             kwargs={})
    g = eval_gesture(lane("bend", w), EMPTY, c)
    v = g.sample("bend", np.linspace(0.0, 1.0, 51))
    assert float(np.std(v)) > 0.0, "a zero-duration note silently flattens every oscillator"


def test_single_glyph_bar():
    g = curve_from_string("^", "bend", ctx())
    v = g.sample("bend", np.linspace(0.0, 1.0, 101))
    assert not np.any(np.isnan(v))
    assert np.allclose(v, BEND_HI)


def test_single_ramp_glyph_starts_from_the_lane_centre():
    g = curve_from_string("/", "bend", ctx())
    assert at(g, "bend", 0.0) == pytest.approx(0.0, abs=1e-12)
    assert at(g, "bend", 1.0) == pytest.approx(BEND_HI, abs=1e-12)


def test_sixty_four_anchor_bar():
    s = "v^" * 32
    g = curve_from_string(s, "bend", ctx())
    t = np.linspace(0.0, 1.0, 8001)
    v = g.sample("bend", t)
    assert not np.any(np.isnan(v))
    assert float(np.min(v)) >= BEND_LO - 1e-9
    assert float(np.max(v)) <= BEND_HI + 1e-9
    # anchors land at the end of their slot: slot k ends at (k+1)/64
    for k in (0, 1, 30, 63):
        want = BEND_LO if k % 2 == 0 else BEND_HI
        assert at(g, "bend", (k + 1) / 64.0) == pytest.approx(want, abs=1e-9)


def test_empty_glyph_string_is_empty_gesture():
    g = curve_from_string("", "bend", ctx())
    assert g.segments == []
    assert g.sample("bend", np.array([0.5])) is None
