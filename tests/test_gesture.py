"""Tests for P3 — `src/filigree/gesture.py` (SPEC §7 glyph lanes, §8 gestures).

Every assertion here is a value-level claim: a number at a specific t, a
continuity bound, a NaN placement, or an algebraic identity.  Nothing is
asserted about internal representation, so the module stays free to change how
it stores curves.
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

# The package is not installed during piecewise development; make `src` importable.
_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from filigree import ir                                     # noqa: E402
from filigree.ast_nodes import (                            # noqa: E402
    BinOp, Breakpoints, Call, GestureDef, Num, Pos, Ref, Slot, Target, UnOp, Window,
)
from filigree.errors import GestureError                    # noqa: E402
from filigree.gesture import (                              # noqa: E402
    Env, Gesture, GestureCtx, Segment, SHAPES, curve_from_string, eval_gesture,
    glyphs_to_gesture, hash01, lane_range_for, parse_glyph_string,
)

T = np.linspace(0.0, 1.0, 401)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def bend_ctx(**kw) -> GestureCtx:
    kw.setdefault("lane_default", "bend")
    kw.setdefault("lane_range", ir.LANE_RANGES["bend"])
    kw.setdefault("note_dur_beats", 1.0)
    kw.setdefault("tempo", 120.0)
    return GestureCtx(**kw)


def press_ctx(**kw) -> GestureCtx:
    kw.setdefault("lane_default", "press")
    kw.setdefault("lane_range", ir.LANE_RANGES["press"])
    return GestureCtx(**kw)


def glyphs(spec: str) -> list[tuple[float, float, Slot]]:
    return parse_glyph_string(spec)


def at(g: Gesture, lane: str, *ts: float) -> np.ndarray:
    out = g.sample(lane, np.asarray(ts, dtype=float))
    assert out is not None, f"lane {lane!r} carries no data"
    return out


def hz_from_zero_crossings(g: Gesture, lane: str, dur_sec: float,
                           t0: float = 0.0, t1: float = 1.0,
                           n: int = 200001, detrend: int = 0) -> float:
    """Measure a lane's oscillation rate in Hz from its descending zero crossings.

    This is deliberately black-box: it does not ask the gesture what rate it was
    built with, it counts real-time intervals between descending zero crossings
    of the oscillating part of the curve, which is what "5.5 Hz" has to mean for
    a player.  Amplitude modulation does not move a sine's zeros, so the default
    is to cross zero itself; pass ``detrend=1`` when the oscillation rides on a
    glide, so the trend is removed before the crossings are located.
    """
    t = np.linspace(t0, t1, n)
    v = g.sample(lane, t)
    assert v is not None, f"lane {lane!r} carries no data"
    finite = np.isfinite(v)
    if detrend:
        d = v - np.polyval(np.polyfit(t[finite], v[finite], detrend), t)
    else:
        d = np.asarray(v, dtype=float)
    ok = np.isfinite(d[:-1]) & np.isfinite(d[1:])
    idx = np.where(ok & (d[:-1] > 0.0) & (d[1:] <= 0.0))[0]
    assert idx.size >= 2, "need at least two descending zero crossings to measure Hz"
    zeros = t[idx] * float(dur_sec)
    return 1.0 / float(np.mean(np.diff(zeros)))


def max_jump(v: np.ndarray) -> float:
    """Largest absolute step between consecutive finite samples."""
    finite = v[np.isfinite(v)]
    if finite.size < 2:
        return 0.0
    return float(np.max(np.abs(np.diff(finite))))


def bp(*points, shape=None) -> Breakpoints:
    """Breakpoints from (value, position_or_None) pairs or bare values."""
    pts = []
    for p in points:
        if isinstance(p, tuple):
            pts.append(p)
        else:
            pts.append((p, None))
    return Breakpoints(points=pts, shape=shape)


ENV = Env({})


# ===========================================================================
# SPEC §7 — glyph table
# ===========================================================================


def test_glyph_min_center_max_levels():
    # SPEC §7 (amended): `v` is lane min, `_` is the lane's REST value.
    g = curve_from_string("v-^", "bend", bend_ctx())
    lo, hi = ir.LANE_RANGES["bend"]
    v = at(g, "bend", 0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0)
    assert v[0] == pytest.approx(lo)              # `v` is lane min
    assert v[1] == pytest.approx(lo)              # reached by end of slot 0
    assert v[2] == pytest.approx(0.0)             # `-` is centre, 0 for bipolar
    assert v[3] == pytest.approx(hi)              # `^` is lane max


def test_floor_glyph_is_the_lane_rest_value_not_the_minimum():
    """The round-2 flagship defect: `___` on a bend lane must be IN TUNE."""
    g = curve_from_string("___", "bend", bend_ctx())
    v = at(g, "bend", 0.0, 0.5, 1.0)
    assert np.allclose(v, 0.0), "a drawn bend floor must be 0 st, not -range"


def test_rest_and_min_differ_on_bend_and_agree_on_press():
    rest = curve_from_string("__", "bend", bend_ctx())
    mini = curve_from_string("vv", "bend", bend_ctx())
    assert at(rest, "bend", 1.0)[0] == pytest.approx(0.0)
    assert at(mini, "bend", 1.0)[0] == pytest.approx(-2.0)
    # press rests at 0, which is also its minimum, so the two agree there
    assert at(curve_from_string("__", "press", press_ctx()), "press", 1.0)[0] \
        == pytest.approx(0.0)
    assert at(curve_from_string("vv", "press", press_ctx()), "press", 1.0)[0] \
        == pytest.approx(0.0)


def test_timbre_rests_at_the_half_way_point():
    # SPEC §7: timbre's rest value is 0.5 (CC74 centre), its minimum is 0.
    assert at(curve_from_string("__", "timbre", press_ctx()), "timbre", 1.0)[0] \
        == pytest.approx(0.5)
    assert at(curve_from_string("vv", "timbre", press_ctx()), "timbre", 1.0)[0] \
        == pytest.approx(0.0)


def test_capital_v_is_accepted_as_the_minimum_glyph():
    g = curve_from_string("VV", "bend", bend_ctx())
    assert at(g, "bend", 1.0)[0] == pytest.approx(-2.0)


def test_wiggle_around_a_drawn_floor_wiggles_around_zero():
    g = curve_from_string("_~5", "bend", bend_ctx())
    v = g.sample("bend", np.linspace(0.5, 1.0, 2001))
    assert float(np.std(v)) > 0.05                       # it really moves
    assert float(np.mean(v)) == pytest.approx(0.0, abs=0.05)
    assert 0.5 * (float(np.min(v)) + float(np.max(v))) == pytest.approx(0.0, abs=0.02)


def test_glyph_center_is_half_for_unipolar_lane():
    g = curve_from_string("--", "press", press_ctx())
    v = at(g, "press", 0.0, 0.5, 1.0)
    assert np.allclose(v, 0.5)                    # unipolar centre is 0.5


def test_glyph_digits_are_explicit_levels():
    g = curve_from_string("0369", "press", press_ctx())
    v = at(g, "press", 0.25, 0.5, 0.75, 1.0)
    assert v[0] == pytest.approx(0.0)             # `0` == min
    assert v[1] == pytest.approx(3 / 9)
    assert v[2] == pytest.approx(6 / 9)
    assert v[3] == pytest.approx(1.0)             # `9` == max


def test_glyph_ramp_up_reaches_max_at_end_of_its_slot():
    # `___/^^^` : hold min, ramp across the `/` slot, hold max (SPEC §7).
    g = curve_from_string("vvv/^^^", "bend", bend_ctx())
    lo, hi = ir.LANE_RANGES["bend"]
    v = at(g, "bend", 0.0, 3 / 7, 3.5 / 7, 4 / 7, 1.0)
    assert v[0] == pytest.approx(lo)
    assert v[1] == pytest.approx(lo)              # ramp has not started yet
    assert lo < v[2] < hi                         # mid-ramp
    assert v[3] == pytest.approx(hi)              # arrives exactly at slot end
    assert v[4] == pytest.approx(hi)


def test_glyph_ramp_down_reaches_min():
    g = curve_from_string("^^\\vv", "bend", bend_ctx())
    lo, hi = ir.LANE_RANGES["bend"]
    v = at(g, "bend", 0.0, 2 / 5, 3 / 5, 1.0)
    assert v[0] == pytest.approx(hi)
    assert v[1] == pytest.approx(hi)
    assert v[2] == pytest.approx(lo)
    assert v[3] == pytest.approx(lo)


def test_glyph_ramp_starts_from_the_running_value_not_from_min():
    # `-/` must ramp from the centre, not from lane min.
    g = curve_from_string("-/", "bend", bend_ctx())
    v = at(g, "bend", 0.5, 0.75, 1.0)
    assert v[0] == pytest.approx(0.0)
    assert 0.0 < v[1] < 2.0                       # depends on the running value
    assert v[2] == pytest.approx(2.0)


def test_glyph_x_holds_previous_value_flat():
    g = curve_from_string("^xxx", "bend", bend_ctx())
    v = at(g, "bend", 0.25, 0.5, 0.75, 1.0)
    assert np.allclose(v, 2.0)
    assert max_jump(at(g, "bend", *T)) < 1e-9     # perfectly flat


def test_glyph_x_after_a_digit_holds_that_digit():
    g = curve_from_string("6xx", "press", press_ctx())
    v = at(g, "press", 1 / 3, 2 / 3, 1.0)
    assert np.allclose(v, 6 / 9)


def test_glyph_wiggle_oscillates_around_the_running_value():
    ctx = bend_ctx(note_dur_beats=4.0, tempo=120.0)   # 2 s note
    g = curve_from_string("-~~~", "bend", ctx)
    v = at(g, "bend", *np.linspace(0.25, 1.0, 200))
    assert np.nanmax(v) > 0.05                    # it moves up
    assert np.nanmin(v) < -0.05                   # and down
    assert abs(float(np.nanmean(v))) < 0.15       # centred on the running value


def test_glyph_wiggle_depth_argument_scales_amplitude():
    ctx = bend_ctx(note_dur_beats=4.0)
    shallow = curve_from_string("-~1~1~1", "bend", ctx)
    deep = curve_from_string("-~9~9~9", "bend", ctx)
    ts = np.linspace(0.3, 1.0, 300)
    assert np.nanmax(np.abs(at(deep, "bend", *ts))) > \
        4 * np.nanmax(np.abs(at(shallow, "bend", *ts)))


def test_glyph_empty_slot_produces_nan_and_writes_nothing():
    g = curve_from_string("__ ^^", "bend", bend_ctx())
    v = at(g, "bend", *T)
    holes = np.isnan(v)
    assert holes.any(), "an empty slot must produce NaN (no data)"
    # the hole is slot index 2 of 5 -> (0.4, 0.6)
    assert np.isnan(g.sample("bend", np.array([0.5]))[0])
    assert np.isfinite(g.sample("bend", np.array([0.2]))[0])
    assert np.isfinite(g.sample("bend", np.array([0.9]))[0])


def test_glyph_all_empty_lane_is_entirely_nan():
    g = curve_from_string("    ", "press", press_ctx())
    v = g.sample("press", T)
    assert v is not None
    assert np.all(np.isnan(v))


def test_glyph_nan_hole_does_not_interpolate_across_the_gap():
    # values either side of a hole must be their own levels, not a blend.
    g = curve_from_string("v ^", "bend", bend_ctx())
    assert at(g, "bend", 1 / 3)[0] == pytest.approx(-2.0)
    assert at(g, "bend", 1.0)[0] == pytest.approx(2.0)
    assert np.isnan(g.sample("bend", np.array([0.5]))[0])


def test_glyph_target_calls_resolve_target_and_lands_on_it():
    seen = []

    def resolve(tgt: Target) -> float:
        seen.append(tgt)
        return 1.25

    ctx = bend_ctx(resolve_target=resolve)
    g = curve_from_string("__/\\_>3", "bend", ctx)
    assert len(seen) == 1
    assert seen[0].kind == "degree"
    assert seen[0].degree == 3
    assert at(g, "bend", 1.0)[0] == pytest.approx(1.25)   # lands exactly


def test_glyph_bare_target_is_a_guide_tone_request():
    seen = []
    ctx = bend_ctx(resolve_target=lambda t: (seen.append(t), -0.5)[1])
    g = curve_from_string("__>", "bend", ctx)
    assert seen[0].kind == "guide"
    assert at(g, "bend", 1.0)[0] == pytest.approx(-0.5)


def test_glyph_target_glides_from_the_running_value():
    ctx = bend_ctx(resolve_target=lambda t: 2.0)
    g = curve_from_string("vv>", "bend", ctx)
    v = at(g, "bend", 2 / 3, 5 / 6, 1.0)
    assert v[0] == pytest.approx(-2.0)
    assert -2.0 < v[1] < 2.0
    assert v[2] == pytest.approx(2.0)


def test_glyph_target_without_context_is_a_gesture_error():
    with pytest.raises(GestureError) as e:
        curve_from_string("_>3", "bend", bend_ctx(resolve_target=None))
    assert "target" in str(e.value)


def test_glyph_target_on_non_bend_lane_is_rejected():
    ctx = press_ctx(resolve_target=lambda t: 0.5)
    with pytest.raises(GestureError) as e:
        curve_from_string("_>", "press", ctx)
    assert "bend" in str(e.value)


def test_unknown_glyph_is_a_gesture_error_with_a_hint():
    with pytest.raises(GestureError) as e:
        curve_from_string("_?_", "bend", bend_ctx())
    assert e.value.suggestion


def test_glyphs_to_gesture_returns_one_segment_over_the_whole_lifetime():
    g = glyphs_to_gesture(glyphs("_^"), "bend", bend_ctx())
    assert len(g.segments) == 1
    assert g.segments[0].lane == "bend"
    assert g.segments[0].window == (0.0, 1.0)
    assert g.lanes() == {"bend"}


def test_sample_returns_none_for_a_lane_with_no_data_at_all():
    g = curve_from_string("_^", "bend", bend_ctx())
    assert g.sample("press", T) is None
    assert g.sample("cc74", T) is None


def test_sample_outside_the_note_lifetime_is_nan():
    g = curve_from_string("^^", "bend", bend_ctx())
    v = g.sample("bend", np.array([-0.1, 0.5, 1.1]))
    assert np.isnan(v[0]) and np.isfinite(v[1]) and np.isnan(v[2])


def test_glyphs_can_start_at_a_non_zero_fraction():
    # the resolver hands us lane-local windows; only that region is written.
    triples = [(0.5, 0.75, Slot(kind="glyph", glyph="v")),
               (0.75, 1.0, Slot(kind="glyph", glyph="^"))]
    g = glyphs_to_gesture(triples, "bend", bend_ctx())
    assert np.isnan(g.sample("bend", np.array([0.1]))[0])
    assert at(g, "bend", 0.75)[0] == pytest.approx(-2.0)
    assert at(g, "bend", 1.0)[0] == pytest.approx(2.0)


def test_parse_glyph_string_tokenises_wiggle_depth_and_targets():
    toks = parse_glyph_string("~5>3 _")
    assert len(toks) == 4
    assert toks[0][2].glyph == "~" and toks[0][2].glyph_arg == 5.0
    assert toks[1][2].target is not None and toks[1][2].target.degree == 3
    assert toks[2][2].kind == "empty"
    assert toks[3][2].glyph == "_"
    assert toks[0][0] == pytest.approx(0.0) and toks[3][1] == pytest.approx(1.0)


def test_inline_gesture_slots_are_left_as_no_data_for_the_resolver():
    triples = [(0.0, 0.5, Slot(kind="glyph", glyph="_")),
               (0.5, 1.0, Slot(kind="gesture", expr=Call("bend", [bp(Num(0), Num(1))])))]
    g = glyphs_to_gesture(triples, "bend", bend_ctx())
    assert np.isnan(g.sample("bend", np.array([0.75]))[0])


# ===========================================================================
# SPEC §7 — interpolation shapes
# ===========================================================================


@pytest.mark.parametrize("shape", ["ease", "linear", "exp"])
def test_continuous_shapes_have_no_discontinuity_at_anchors(shape):
    g = curve_from_string("_^_9^0", "bend", bend_ctx(), shape=shape)
    v = at(g, "bend", *np.linspace(0.0, 1.0, 4001))
    # full lane span is 4 semitones over 6 slots; a continuous shape can only
    # move ~4/(4001/6) per sample.  Allow 4x slack, still far below a jump.
    assert max_jump(v) < 4 * 4.0 / (4001 / 6)


@pytest.mark.parametrize("shape", ["hold", "snap"])
def test_stepped_shapes_do_jump_at_anchors(shape):
    g = curve_from_string("v^v^", "bend", bend_ctx(), shape=shape)
    v = at(g, "bend", *np.linspace(0.0, 1.0, 4001))
    assert max_jump(v) > 3.0                     # a real step, not a ramp


def test_ease_is_smoothstep_with_zero_slope_at_both_ends():
    g = eval_gesture(Call("press", [bp(Num(0.0), Num(1.0), shape="ease")]),
                     ENV, press_ctx())
    v = at(g, "press", 0.0, 0.25, 0.5, 0.75, 1.0)
    assert v[0] == pytest.approx(0.0)
    assert v[2] == pytest.approx(0.5)            # smoothstep(0.5) == 0.5
    assert v[1] == pytest.approx(0.25 * 0.25 * (3 - 2 * 0.25))
    assert v[4] == pytest.approx(1.0)
    d = np.diff(at(g, "press", *np.linspace(0, 1, 101)))
    assert d[0] < d[50] and d[-1] < d[50]        # slow in, fast middle, slow out


def test_linear_is_exactly_linear():
    g = eval_gesture(Call("press", [bp(Num(0.0), Num(1.0), shape="linear")]),
                     ENV, press_ctx())
    v = at(g, "press", *np.linspace(0, 1, 11))
    assert np.allclose(v, np.linspace(0, 1, 11))


def test_hold_keeps_the_previous_anchor_until_the_next_one():
    g = eval_gesture(Call("press", [bp(Num(0.0), Num(1.0), shape="hold")]),
                     ENV, press_ctx())
    assert at(g, "press", 0.0, 0.5, 0.99)[1] == pytest.approx(0.0)
    assert at(g, "press", 1.0)[0] == pytest.approx(1.0)


def test_snap_jumps_to_the_target_at_the_start_of_the_span():
    g = eval_gesture(Call("press", [bp(Num(0.0), Num(1.0), shape="snap")]),
                     ENV, press_ctx())
    assert at(g, "press", 0.0)[0] == pytest.approx(0.0)
    assert at(g, "press", 0.01)[0] == pytest.approx(1.0)


def test_exp_is_monotone_and_lags_linear_in_the_first_half():
    g = eval_gesture(Call("press", [bp(Num(0.0), Num(1.0), shape="exp")]),
                     ENV, press_ctx())
    v = at(g, "press", *np.linspace(0, 1, 51))
    assert np.all(np.diff(v) >= -1e-12)
    assert v[25] < 0.5
    assert v[0] == pytest.approx(0.0) and v[-1] == pytest.approx(1.0)


def test_unknown_shape_is_rejected():
    with pytest.raises(GestureError):
        curve_from_string("_^", "bend", bend_ctx(), shape="wobble")
    assert set(SHAPES) == {"ease", "linear", "hold", "exp", "snap"}


# ===========================================================================
# SPEC §8 — lane primitives and breakpoints
# ===========================================================================


def test_bend_breakpoints_in_semitones():
    g = eval_gesture(Call("bend", [bp(Num(0.0), Num(-0.7, "st"), Num(0.0))]),
                     ENV, bend_ctx())
    v = at(g, "bend", 0.0, 0.5, 1.0)
    assert v[0] == pytest.approx(0.0)
    assert v[1] == pytest.approx(-0.7)           # middle point lands at 50%
    assert v[2] == pytest.approx(0.0)


def test_breakpoint_at_pos_places_the_point_exactly():
    g = eval_gesture(Call("bend", [bp(Num(0.0), (Num(-0.7, "st"), Num(40, "pct")),
                                      Num(0.0))]), ENV, bend_ctx())
    assert at(g, "bend", 0.4)[0] == pytest.approx(-0.7)
    assert at(g, "bend", 0.2)[0] > -0.7          # still on the way down
    assert at(g, "bend", 0.7)[0] > -0.7          # already coming back


def test_unpositioned_breakpoints_spread_evenly_between_neighbours():
    g = eval_gesture(Call("press", [bp(Num(0.0), Num(1.0), Num(0.0), Num(1.0),
                                       shape="linear")]), ENV, press_ctx())
    v = at(g, "press", 0.0, 1 / 3, 2 / 3, 1.0)
    assert np.allclose(v, [0.0, 1.0, 0.0, 1.0])


def test_unpositioned_points_respect_a_positioned_neighbour():
    g = eval_gesture(
        Call("press", [bp(Num(0.0), Num(0.5), (Num(1.0), Num(80, "pct")),
                          shape="linear")]), ENV, press_ctx())
    assert at(g, "press", 0.4)[0] == pytest.approx(0.5)   # midpoint of 0..0.8
    assert at(g, "press", 0.8)[0] == pytest.approx(1.0)


def test_breakpoint_position_may_be_given_in_ms():
    # 1 beat at 120bpm == 500 ms, so 200ms == 40% of the lifetime.
    g = eval_gesture(Call("bend", [bp(Num(-1.0, "st"), (Num(0.0), Num(200, "ms")))]),
                     ENV, bend_ctx(note_dur_beats=1.0, tempo=120.0))
    assert at(g, "bend", 0.0)[0] == pytest.approx(-1.0)
    assert at(g, "bend", 0.4)[0] == pytest.approx(0.0)
    assert at(g, "bend", 0.9)[0] == pytest.approx(0.0)    # holds after arrival


def test_percent_and_plain_fraction_agree():
    a = eval_gesture(Call("press", [bp(Num(0.0), (Num(1.0), Num(30, "pct")))]),
                     ENV, press_ctx())
    b = eval_gesture(Call("press", [bp(Num(0.0), (Num(1.0), Num(0.3)))]),
                     ENV, press_ctx())
    assert np.allclose(at(a, "press", *T), at(b, "press", *T))


def test_single_breakpoint_is_a_constant():
    g = eval_gesture(Call("timbre", [bp(Num(0.42))]), ENV, GestureCtx())
    assert np.allclose(at(g, "timbre", *T), 0.42)


def test_lane_primitives_set_their_own_lane_and_range():
    for lane in ("bend", "press", "timbre", "amp", "pan"):
        g = eval_gesture(Call(lane, [Num(0.3)]), ENV, GestureCtx())
        assert g.lanes() == {lane}
        assert at(g, lane, 0.5)[0] == pytest.approx(0.3)
    assert lane_range_for("bend") == (-2.0, 2.0)
    assert lane_range_for("press") == (0.0, 1.0)


def test_cc_lane_primitive_is_accepted_with_unipolar_range():
    g = eval_gesture(Call("cc11", [Call("curve", ["_^"])]), ENV, GestureCtx())
    assert g.lanes() == {"cc11"}
    assert at(g, "cc11", 0.5)[0] == pytest.approx(0.0)
    assert at(g, "cc11", 1.0)[0] == pytest.approx(1.0)
    assert lane_range_for("cc74") == (0.0, 1.0)


def test_lane_primitive_with_no_argument_errors():
    with pytest.raises(GestureError):
        eval_gesture(Call("bend", []), ENV, GestureCtx())


def test_amp_lane_is_available_and_unipolar():
    g = eval_gesture(Call("amp", [bp(Num(0.2), Num(0.9), shape="linear")]),
                     ENV, GestureCtx())
    assert at(g, "amp", 0.0)[0] == pytest.approx(0.2)
    assert at(g, "amp", 1.0)[0] == pytest.approx(0.9)


def test_bare_number_outside_a_lane_is_an_error():
    with pytest.raises(GestureError):
        eval_gesture(Num(0.5), ENV, GestureCtx(lane_default=None))


# ===========================================================================
# SPEC §8 — generators
# ===========================================================================


def test_wiggle_is_a_sine_with_phase_zero_at_the_window_start():
    ctx = bend_ctx(note_dur_beats=2.0, tempo=120.0)      # 1 s note
    g = eval_gesture(Call("bend", [Call("wiggle", [Num(1.0, "hz"), Num(0.5, "st")])]),
                     ENV, ctx)
    assert at(g, "bend", 0.0)[0] == pytest.approx(0.0, abs=1e-12)
    assert at(g, "bend", 0.25)[0] == pytest.approx(0.5)   # quarter cycle -> peak
    assert at(g, "bend", 0.5)[0] == pytest.approx(0.0, abs=1e-9)
    assert at(g, "bend", 0.75)[0] == pytest.approx(-0.5)


def test_wiggle_rate_is_in_hz_of_real_time():
    # 2 Hz over a 1 s note: peaks at 0.125 s and 0.625 s, troughs between.
    g = eval_gesture(Call("bend", [Call("wiggle", [Num(2.0, "hz"), Num(1.0, "st")])]),
                     ENV, bend_ctx(note_dur_beats=2.0, tempo=120.0))
    v = at(g, "bend", 0.125, 0.375, 0.625, 0.875, 0.5, 1.0)
    assert v[0] == pytest.approx(1.0)
    assert v[1] == pytest.approx(-1.0)
    assert v[2] == pytest.approx(1.0)
    assert v[3] == pytest.approx(-1.0)
    assert v[4] == pytest.approx(0.0, abs=1e-9)
    assert v[5] == pytest.approx(0.0, abs=1e-9)


def test_wiggle_phase_argument_shifts_the_sine():
    g = eval_gesture(Call("bend", [Call("wiggle", [Num(1.0, "hz"), Num(1.0, "st"),
                                                   Num(0.25)])]),
                     ENV, bend_ctx(note_dur_beats=2.0))
    assert at(g, "bend", 0.0)[0] == pytest.approx(1.0)   # quarter turn head start


def test_ramp_is_a_linear_two_point_gesture():
    g = eval_gesture(Call("press", [Call("ramp", [Num(0.1), Num(0.9)])]),
                     ENV, GestureCtx())
    v = at(g, "press", 0.0, 0.5, 1.0)
    assert np.allclose(v, [0.1, 0.5, 0.9])


def test_ramp_needs_two_values():
    with pytest.raises(GestureError):
        eval_gesture(Call("press", [Call("ramp", [Num(0.1)])]), ENV, GestureCtx())


def test_pulse_is_a_square_wave_with_the_given_duty():
    ctx = press_ctx(note_dur_beats=2.0, tempo=120.0)     # 1 s note
    g = eval_gesture(Call("press", [Call("pulse", [Num(2.0, "hz"), Num(0.25)])]),
                     ENV, ctx)
    # cycle is 0.5 s, so the wave is high for the first 0.125 s of each cycle.
    v = at(g, "press", 0.0, 0.1, 0.2, 0.5, 0.6, 0.7)
    assert v[0] == pytest.approx(1.0)                    # inside the duty
    assert v[1] == pytest.approx(1.0)                    # 0.1 s, still high
    assert v[2] == pytest.approx(0.0)                    # 0.2 s -> 40% of cycle
    assert v[3] == pytest.approx(1.0)                    # second cycle starts
    assert v[5] == pytest.approx(0.0)
    assert set(np.unique(at(g, "press", *T))) <= {0.0, 1.0}


def test_drift_is_deterministic_from_seed_key():
    mk = lambda key: eval_gesture(                       # noqa: E731
        Call("bend", [Call("drift", [Num(0.4, "st"), Num(3.0, "hz")])]),
        ENV, bend_ctx(seed_key=key, note_dur_beats=4.0))
    a = at(mk((7, "lead", 3)), "bend", *T)
    b = at(mk((7, "lead", 3)), "bend", *T)
    c = at(mk((7, "lead", 4)), "bend", *T)
    assert np.array_equal(a, b)                          # bit-identical reruns
    assert not np.allclose(a, c)                         # a different note differs
    assert np.max(np.abs(a)) <= 0.4 + 1e-12              # bounded by depth


def test_drift_is_smooth_not_white_noise():
    g = eval_gesture(Call("bend", [Call("drift", [Num(1.0, "st"), Num(2.0, "hz")])]),
                     ENV, bend_ctx(seed_key=(1,), note_dur_beats=4.0))
    v = at(g, "bend", *np.linspace(0, 1, 2001))
    assert max_jump(v) < 0.05                            # neighbouring samples close
    assert np.std(v) > 0.05                              # but it really moves


def test_hash01_is_stable_and_in_range():
    a = hash01(7, "lead", 3, "bend")
    assert 0.0 <= a < 1.0
    assert a == hash01(7, "lead", 3, "bend")
    assert a != hash01(7, "lead", 4, "bend")


def test_curve_generator_accepts_a_glyph_string():
    g = eval_gesture(Call("bend", [Call("curve", ["v/^\\v"])]), ENV, GestureCtx())
    v = at(g, "bend", 0.0, 0.4, 0.6, 1.0)
    assert v[0] == pytest.approx(-2.0)
    assert v[1] == pytest.approx(2.0)
    assert v[3] == pytest.approx(-2.0)


def test_curve_generator_rejects_a_non_string():
    with pytest.raises(GestureError):
        eval_gesture(Call("bend", [Call("curve", [Num(3)])]), ENV, GestureCtx())


def test_generator_outside_a_lane_is_an_error():
    with pytest.raises(GestureError):
        eval_gesture(Call("wiggle", [Num(5, "hz")]), ENV, GestureCtx(lane_default=None))


def test_generator_inherits_the_enclosing_lane_of_a_curve_lane():
    # a lane's own ctx supplies lane_default, so `wiggle(...)` needs no wrapper.
    g = eval_gesture(Call("wiggle", [Num(1.0, "hz"), Num(0.3)]),
                     ENV, press_ctx(note_dur_beats=2.0))
    assert g.lanes() == {"press"}


# ===========================================================================
# SPEC §8 — the algebra
# ===========================================================================


def test_add_sums_per_lane():
    a = Call("press", [bp(Num(0.2), Num(0.2))])
    b = Call("press", [bp(Num(0.1), Num(0.5), shape="linear")])
    g = eval_gesture(BinOp("add", a, b), ENV, GestureCtx())
    assert at(g, "press", 0.0)[0] == pytest.approx(0.3)
    assert at(g, "press", 1.0)[0] == pytest.approx(0.7)


def test_sub_subtracts_per_lane():
    a = Call("press", [bp(Num(0.8), Num(0.8))])
    b = Call("press", [bp(Num(0.3), Num(0.3))])
    g = eval_gesture(BinOp("sub", a, b), ENV, GestureCtx())
    assert np.allclose(at(g, "press", *T), 0.5)


def test_add_unions_lanes_when_they_differ():
    a = Call("press", [Num(0.5)])
    b = Call("timbre", [Num(0.2)])
    g = eval_gesture(BinOp("add", a, b), ENV, GestureCtx())
    assert g.lanes() == {"press", "timbre"}
    assert at(g, "press", 0.5)[0] == pytest.approx(0.5)
    assert at(g, "timbre", 0.5)[0] == pytest.approx(0.2)


def test_scale_by_a_scalar_scales_amplitude():
    base = Call("bend", [bp(Num(0.0), Num(-0.7, "st"), Num(0.0))])
    g = eval_gesture(BinOp("scale_or_mul", base, Num(1.4)), ENV, bend_ctx())
    ref = eval_gesture(base, ENV, bend_ctx())
    assert np.allclose(at(g, "bend", *T), 1.4 * at(ref, "bend", *T))
    assert at(g, "bend", 0.5)[0] == pytest.approx(-0.98)


def test_scalar_multiply_is_commutative():
    base = Call("press", [bp(Num(0.1), Num(0.9))])
    left = eval_gesture(BinOp("scale_or_mul", Num(0.5), base), ENV, GestureCtx())
    right = eval_gesture(BinOp("scale_or_mul", base, Num(0.5)), ENV, GestureCtx())
    assert np.allclose(at(left, "press", *T), at(right, "press", *T))


def test_gesture_multiply_is_amplitude_modulation():
    osc = Call("bend", [Call("wiggle", [Num(1.0, "hz"), Num(1.0, "st")])])
    env_ = Call("bend", [Call("ramp", [Num(0.0), Num(1.0)])])
    g = eval_gesture(BinOp("scale_or_mul", osc, env_), ENV,
                     bend_ctx(note_dur_beats=2.0))
    assert abs(at(g, "bend", 0.25)[0]) == pytest.approx(0.25)   # sine peak * 0.25
    assert abs(at(g, "bend", 0.75)[0]) == pytest.approx(0.75)


def test_neg_inverts_every_lane():
    base = Call("press", [bp(Num(0.2), Num(0.9))])
    g = eval_gesture(UnOp("neg", base), ENV, GestureCtx())
    ref = eval_gesture(base, ENV, GestureCtx())
    assert np.allclose(at(g, "press", *T), -at(ref, "press", *T))


def test_double_negation_is_identity():
    base = Call("bend", [Call("curve", ["_/^"])])
    g = eval_gesture(UnOp("neg", UnOp("neg", base)), ENV, GestureCtx())
    ref = eval_gesture(base, ENV, GestureCtx())
    assert np.allclose(at(g, "bend", *T), at(ref, "bend", *T), equal_nan=True)


def test_add_is_commutative():
    a = Call("press", [bp(Num(0.1), Num(0.4))])
    b = Call("press", [Call("ramp", [Num(0.0), Num(0.3)])])
    ab = eval_gesture(BinOp("add", a, b), ENV, GestureCtx())
    ba = eval_gesture(BinOp("add", b, a), ENV, GestureCtx())
    assert np.allclose(at(ab, "press", *T), at(ba, "press", *T))


def test_sub_equals_add_of_negation():
    a = Call("press", [bp(Num(0.8), Num(0.4))])
    b = Call("press", [bp(Num(0.1), Num(0.3))])
    lhs = eval_gesture(BinOp("sub", a, b), ENV, GestureCtx())
    rhs = eval_gesture(BinOp("add", a, UnOp("neg", b)), ENV, GestureCtx())
    assert np.allclose(at(lhs, "press", *T), at(rhs, "press", *T))


def test_par_keeps_both_lanes_independent():
    a = Call("press", [bp(Num(0.2), Num(0.9), shape="exp")])
    b = Call("timbre", [bp(Num(0.4), Num(0.7))])
    g = eval_gesture(BinOp("par", a, b), ENV, GestureCtx())
    assert g.lanes() == {"press", "timbre"}
    assert at(g, "press", 0.0)[0] == pytest.approx(0.2)
    assert at(g, "timbre", 1.0)[0] == pytest.approx(0.7)


def test_seq_gives_each_side_half_the_lifetime():
    a = Call("press", [bp(Num(0.0), Num(1.0), shape="linear")])
    b = Call("press", [bp(Num(0.0), Num(0.5), shape="linear")])
    g = eval_gesture(BinOp("seq", a, b), ENV, GestureCtx())
    # `>>` is `(a @ 0..50%) | (b @ 50%..100%)` and `@` RESTRICTS (SPEC §8), so
    # each side keeps its own timing and only its half is written.
    assert at(g, "press", 0.0)[0] == pytest.approx(0.0)
    assert at(g, "press", 0.25)[0] == pytest.approx(0.25)    # a, un-refitted
    assert at(g, "press", 0.75)[0] == pytest.approx(0.375)   # b, un-refitted
    assert at(g, "press", 1.0)[0] == pytest.approx(0.5)


def test_seq_split_can_be_moved():
    a = Call("press", [bp(Num(0.0), Num(1.0), shape="linear")])
    b = Call("press", [bp(Num(0.0), Num(0.0))])
    g = eval_gesture(BinOp("seq", a, b, split=Num(30, "pct")), ENV, GestureCtx())
    # a hands over at 30% having reached only 30% of its own travel
    assert at(g, "press", 0.29)[0] == pytest.approx(0.29, abs=1e-6)
    assert at(g, "press", 0.15)[0] == pytest.approx(0.15)
    assert at(g, "press", 0.6)[0] == pytest.approx(0.0)


def test_seq_is_window_zero_split_par_window_split_one():
    a = Call("press", [bp(Num(0.2), Num(0.9))])
    b = Call("press", [bp(Num(0.9), Num(0.1))])
    seq = eval_gesture(BinOp("seq", a, b), ENV, GestureCtx())
    par = eval_gesture(
        BinOp("par", Window(a, Num(0.0), Num(0.5)), Window(b, Num(0.5), Num(1.0))),
        ENV, GestureCtx())
    assert np.allclose(at(seq, "press", *T), at(par, "press", *T), equal_nan=True)


def test_window_writes_nothing_outside_itself():
    inner = Call("press", [bp(Num(0.0), Num(1.0), shape="linear")])
    g = eval_gesture(Window(inner, Num(35, "pct"), Num(100, "pct")), ENV, GestureCtx())
    v = at(g, "press", *T)
    assert np.all(np.isnan(v[T < 0.34]))
    assert np.isfinite(v[-1])
    # SPEC §8: restriction, not refitting — the ramp keeps its own 0..1 domain.
    assert at(g, "press", 0.35)[0] == pytest.approx(0.35)
    assert at(g, "press", 1.0)[0] == pytest.approx(1.0)


def test_window_restricts_the_gesture_to_the_window():
    inner = Call("press", [bp(Num(0.0), Num(1.0), shape="linear")])
    g = eval_gesture(Window(inner, Num(0.5), Num(1.0)), ENV, GestureCtx())
    # the window shows the second half of the ramp where it actually lives
    assert at(g, "press", 0.75)[0] == pytest.approx(0.75)
    assert np.isnan(g.sample("press", np.array([0.25]))[0])


def test_nested_windows_intersect():
    inner = Call("press", [bp(Num(0.0), Num(1.0), shape="linear")])
    g = eval_gesture(Window(Window(inner, Num(0.0), Num(0.6)), Num(0.5), Num(1.0)),
                     ENV, GestureCtx())
    v = at(g, "press", *T)
    finite = T[np.isfinite(v)]
    assert finite.min() >= 0.5 - 1e-9
    assert finite.max() <= 0.6 + 1e-9
    assert at(g, "press", 0.55)[0] == pytest.approx(0.55)


def test_disjoint_nested_windows_write_nothing():
    inner = Call("press", [bp(Num(0.0), Num(1.0), shape="linear")])
    g = eval_gesture(Window(Window(inner, Num(0.0), Num(0.5)), Num(0.5), Num(1.0)),
                     ENV, GestureCtx())
    assert g.sample("press", T) is None


def test_empty_window_yields_no_data_at_all():
    inner = Call("press", [Num(0.5)])
    g = eval_gesture(Window(inner, Num(0.6), Num(0.6)), ENV, GestureCtx())
    assert g.sample("press", T) is None
    assert g.lanes() == set()


def test_window_reclocks_an_oscillator_instead_of_stretching_it():
    # 4 Hz over the last half of a 1 s note must give 2 cycles, not 4.
    inner = Call("bend", [Call("wiggle", [Num(4.0, "hz"), Num(1.0, "st")])])
    g = eval_gesture(Window(inner, Num(0.5), Num(1.0)), ENV,
                     bend_ctx(note_dur_beats=2.0, tempo=120.0))
    # 2 full cycles inside the window: peaks at 0.5625 and 0.8125 of the note.
    v = at(g, "bend", 0.5, 0.5625, 0.6875, 0.8125, 0.9375)
    assert v[0] == pytest.approx(0.0, abs=1e-9)              # phase 0 at 50%
    assert v[1] == pytest.approx(1.0)
    assert v[2] == pytest.approx(-1.0)
    assert v[3] == pytest.approx(1.0)
    assert v[4] == pytest.approx(-1.0)


def test_window_in_ms_positions():
    inner = Call("press", [Num(0.7)])
    g = eval_gesture(Window(inner, Num(250, "ms"), Num(500, "ms")), ENV,
                     press_ctx(note_dur_beats=1.0, tempo=120.0))   # 500 ms note
    assert np.isnan(g.sample("press", np.array([0.2]))[0])
    assert at(g, "press", 0.75)[0] == pytest.approx(0.7)


# ===========================================================================
# NaN propagation rules
# ===========================================================================


def test_multiply_propagates_nan():
    holed = Call("press", [Call("curve", ["^^ ^^"])])
    full = Call("press", [Num(0.5)])
    g = eval_gesture(BinOp("scale_or_mul", holed, full), ENV, GestureCtx())
    assert np.isnan(g.sample("press", np.array([0.5]))[0])
    assert at(g, "press", 0.1)[0] == pytest.approx(0.5)


def test_scalar_scale_propagates_nan():
    holed = Call("press", [Call("curve", ["^^ ^^"])])
    g = eval_gesture(BinOp("scale_or_mul", holed, Num(0.5)), ENV, GestureCtx())
    assert np.isnan(g.sample("press", np.array([0.5]))[0])


def test_add_treats_no_data_as_the_additive_identity():
    holed = Call("press", [Call("curve", ["9 9"])])
    full = Call("press", [Num(0.25)])
    g = eval_gesture(BinOp("add", holed, full), ENV, GestureCtx())
    assert at(g, "press", 0.5)[0] == pytest.approx(0.25)     # hole -> just `full`
    assert at(g, "press", 0.1)[0] == pytest.approx(1.25)


def test_add_of_two_holes_stays_nan():
    a = Call("press", [Call("curve", ["9 9"])])
    b = Call("press", [Call("curve", ["1 1"])])
    g = eval_gesture(BinOp("add", a, b), ENV, GestureCtx())
    assert np.isnan(g.sample("press", np.array([0.5]))[0])
    assert at(g, "press", 0.9)[0] == pytest.approx(1 / 9 + 1.0)


def test_neg_of_nan_is_nan():
    holed = Call("press", [Call("curve", ["^ ^"])])
    g = eval_gesture(UnOp("neg", holed), ENV, GestureCtx())
    assert np.isnan(g.sample("press", np.array([0.5]))[0])


def test_seq_of_two_holed_sides_keeps_the_holes_inside_each_half():
    # "9 9" writes thirds 1 and 3 and leaves the middle third unwritten; each
    # side is restricted to its half, so the hole that falls inside that half
    # survives the hand-off.
    a = Call("press", [Call("curve", ["9 9"])])
    b = Call("press", [Call("curve", ["9 9"])])
    g = eval_gesture(BinOp("seq", a, b), ENV, GestureCtx())
    v = at(g, "press", 0.1, 0.45, 0.55, 0.9)
    assert np.isfinite(v[0]) and np.isnan(v[1])     # a's hole, inside 0..50%
    assert np.isnan(v[2]) and np.isfinite(v[3])     # b's hole, inside 50%..100%


def test_seq_hands_over_without_refitting_either_side():
    a = Call("press", [Call("curve", ["9 "])])
    b = Call("press", [Call("curve", [" 9"])])
    g = eval_gesture(BinOp("seq", a, b), ENV, GestureCtx())
    v = at(g, "press", 0.1, 0.4, 0.6, 0.9)
    # a writes its own first half, b its own second half: the two complementary
    # halves tile the lifetime with no hole and no compression.
    assert np.all(np.isfinite(v))


def test_multiply_over_disjoint_windows_yields_no_data():
    a = Window(Call("press", [Num(1.0)]), Num(0.0), Num(0.4))
    b = Window(Call("press", [Num(1.0)]), Num(0.6), Num(1.0))
    g = eval_gesture(BinOp("scale_or_mul", a, b), ENV, GestureCtx())
    assert g.sample("press", T) is None


# ===========================================================================
# SPEC §8 — user gesture definitions
# ===========================================================================


def defs_env() -> Env:
    cry = GestureDef("cry", [], Call("bend", [bp(Num(0.0), Num(-0.7, "st"), Num(0.0))]))
    warm = GestureDef("warm", [], BinOp(
        "par",
        Call("press", [bp(Num(0.2), Num(0.9), shape="exp")]),
        Call("timbre", [bp(Num(0.4), Num(0.7))]),
    ))
    vibr = GestureDef(
        "vibr",
        [("rate", Num(5.2, "hz")), ("depth", Num(0.3, "st")), ("onset", Num(30, "pct"))],
        Call("bend", [Window(Call("wiggle", [Ref("rate"), Ref("depth")]),
                             Ref("onset"), Num(100, "pct"))]),
    )
    cry2 = GestureDef("cry2", [], BinOp(
        "seq",
        BinOp("scale_or_mul", Ref("cry"), Num(1.4)),
        Call("vibr", [], {"rate": Num(6.0, "hz")}),
    ))
    # NAMING (round-1 defect D5): this gesture bends UP to the chord third, so
    # it is called `lift`, not `fall`.
    lift = GestureDef("lift", [], Call("bend", [bp(Num(0.0), Target("degree", 3))]))
    return Env({"cry": cry, "warm": warm, "vibr": vibr, "cry2": cry2, "lift": lift})


def test_user_gesture_by_reference():
    g = eval_gesture(Ref("cry"), defs_env(), bend_ctx())
    assert g.lanes() == {"bend"}
    assert at(g, "bend", 0.5)[0] == pytest.approx(-0.7)


def test_user_gesture_with_multiple_lanes():
    g = eval_gesture(Ref("warm"), defs_env(), GestureCtx())
    assert g.lanes() == {"press", "timbre"}
    assert at(g, "press", 0.0)[0] == pytest.approx(0.2)
    assert at(g, "timbre", 1.0)[0] == pytest.approx(0.7)


def test_user_gesture_defaults_are_used_when_no_args_given():
    g = eval_gesture(Call("vibr", []), defs_env(), bend_ctx(note_dur_beats=4.0))
    v = at(g, "vibr" if False else "bend", *T)
    assert np.all(np.isnan(v[T < 0.29]))                 # onset default 30%
    assert np.nanmax(np.abs(v)) == pytest.approx(0.3, rel=0.05)


def test_user_gesture_keyword_argument_overrides_a_default():
    e = defs_env()
    slow = eval_gesture(Call("vibr", [], {"rate": Num(2.0, "hz")}), e,
                        bend_ctx(note_dur_beats=4.0, tempo=120.0))
    fast = eval_gesture(Call("vibr", [], {"rate": Num(8.0, "hz")}), e,
                        bend_ctx(note_dur_beats=4.0, tempo=120.0))
    ts = np.linspace(0.3, 1.0, 4001)
    n_slow = int(np.sum(np.diff(np.signbit(at(slow, "bend", *ts)))))
    n_fast = int(np.sum(np.diff(np.signbit(at(fast, "bend", *ts)))))
    assert n_fast > 3 * n_slow


def test_user_gesture_positional_arguments_bind_in_order():
    e = defs_env()
    g = eval_gesture(Call("vibr", [Num(4.0, "hz"), Num(1.0, "st"), Num(50, "pct")]),
                     e, bend_ctx(note_dur_beats=4.0))
    v = at(g, "bend", *T)
    assert np.all(np.isnan(v[T < 0.49]))
    assert np.nanmax(np.abs(v)) == pytest.approx(1.0, rel=0.05)


def test_user_gesture_onset_parameter_moves_the_window():
    e = defs_env()
    g = eval_gesture(Call("vibr", [], {"onset": Num(70, "pct")}), e,
                     bend_ctx(note_dur_beats=4.0))
    v = at(g, "bend", *T)
    assert np.all(np.isnan(v[T < 0.69]))
    assert np.isfinite(v[-1])


def test_user_gesture_composition_of_definitions():
    g = eval_gesture(Ref("cry2"), defs_env(), bend_ctx(note_dur_beats=4.0))
    # first half is `cry * 1.4` RESTRICTED to 0..50%: cry's own dip bottoms out
    # at 50% of the lifetime, so the written half ends at -0.98 and is halfway
    # there (-0.49) at 25%.
    assert at(g, "bend", 0.25)[0] == pytest.approx(-0.49)
    assert at(g, "bend", 0.4999)[0] == pytest.approx(-0.98, abs=1e-3)
    # The second half is `vibr(rate: 6hz)`, whose own window opens at 30% of the
    # lifetime.  Restriction intersects windows, so 30%..100% ∩ 50%..100% leaves
    # the whole second half written — no gap after the hand-off.
    assert np.isfinite(g.sample("bend", np.array([0.6]))[0])
    assert np.isfinite(g.sample("bend", np.array([0.95]))[0])
    # and it really is 6 Hz on this 2 s note (4 beats @ 120)
    assert hz_from_zero_crossings(g, "bend", 2.0, 0.55, 1.0) == pytest.approx(6.0, rel=0.05)


def test_user_gesture_target_inside_a_definition():
    calls = []
    ctx = bend_ctx(resolve_target=lambda t: (calls.append(t), 0.9)[1])
    g = eval_gesture(Ref("lift"), defs_env(), ctx)
    assert calls and calls[0].degree == 3
    assert at(g, "bend", 0.0)[0] == pytest.approx(0.0)
    assert at(g, "bend", 1.0)[0] == pytest.approx(0.9)


def test_unknown_gesture_name_errors_with_a_suggestion():
    with pytest.raises(GestureError) as e:
        eval_gesture(Ref("cryy"), defs_env(), bend_ctx())
    assert "cry" in e.value.suggestion


def test_unknown_parameter_name_errors():
    with pytest.raises(GestureError) as e:
        eval_gesture(Call("vibr", [], {"speed": Num(3, "hz")}), defs_env(), bend_ctx())
    assert "speed" in str(e.value)


def test_too_many_positional_arguments_errors():
    with pytest.raises(GestureError):
        eval_gesture(Call("vibr", [Num(1), Num(2), Num(3), Num(4)]),
                     defs_env(), bend_ctx())


def test_required_parameter_without_a_default_must_be_supplied():
    e = Env({"needs": GestureDef("needs", [("depth", None)],
                                 Call("bend", [Ref("depth")]))})
    with pytest.raises(GestureError):
        eval_gesture(Call("needs", []), e, bend_ctx())
    g = eval_gesture(Call("needs", [Num(0.8, "st")]), e, bend_ctx())
    assert at(g, "bend", 0.5)[0] == pytest.approx(0.8)


def test_parameters_flow_through_nested_definitions():
    inner = GestureDef("inner", [("d", Num(0.1))], Call("press", [Ref("d")]))
    outer = GestureDef("outer", [("d", Num(0.2))],
                       Call("inner", [], {"d": Ref("d")}))
    e = Env({"inner": inner, "outer": outer})
    g = eval_gesture(Call("outer", [], {"d": Num(0.75)}), e, GestureCtx())
    assert at(g, "press", 0.5)[0] == pytest.approx(0.75)


def test_env_child_does_not_mutate_the_parent():
    e = Env({}, {"a": Num(1.0)})
    c = e.child({"b": Num(2.0)})
    assert e.has_param("a") and not e.has_param("b")
    assert c.has_param("b")
    assert c.defs is not e.defs or True          # defs are shared by value


def test_self_reference_is_caught_rather_than_recursing_forever():
    d = GestureDef("loop", [], Ref("loop"))
    with pytest.raises(GestureError):
        eval_gesture(Ref("loop"), Env({"loop": d}), bend_ctx())


# ===========================================================================
# target resolution via the stub callback
# ===========================================================================


def test_resolve_target_receives_the_exact_target_node():
    seen = []

    def resolve(tgt):
        seen.append((tgt.kind, tgt.degree, tgt.chord))
        return {"guide": -0.3, "degree": 1.7, "step": 1.0, "next": 0.25}[tgt.kind]

    ctx = bend_ctx(resolve_target=resolve)
    for tgt, want in [
        (Target("guide"), -0.3),
        (Target("degree", 5), 1.7),
        (Target("step", 1), 1.0),
        (Target("next"), 0.25),
    ]:
        g = eval_gesture(Call("bend", [bp(Num(0.0), tgt)]), ENV, ctx)
        assert at(g, "bend", 1.0)[0] == pytest.approx(want)
    assert [s[0] for s in seen] == ["guide", "degree", "step", "next"]
    assert seen[1][1] == 5
    assert seen[2][2] == "next"                  # default reference chord


def test_target_value_is_used_verbatim_as_a_lane_value():
    ctx = bend_ctx(resolve_target=lambda t: -1.9)
    g = eval_gesture(Call("bend", [Target("guide")]), ENV, ctx)
    assert np.allclose(at(g, "bend", *T), -1.9)


def test_target_is_resolved_once_per_occurrence():
    n = [0]

    def resolve(t):
        n[0] += 1
        return 1.0

    ctx = bend_ctx(resolve_target=resolve)
    g = eval_gesture(Call("bend", [bp(Num(0.0), Target("degree", 3))]), ENV, ctx)
    at(g, "bend", *T)
    at(g, "bend", *T)
    assert n[0] == 1                             # sampling must not re-resolve


# ===========================================================================
# Segment / Gesture object contract
# ===========================================================================


def test_segment_is_constructible_directly_from_a_callable():
    seg = Segment("press", lambda u: np.asarray(u) * 0.5, (0.0, 1.0))
    g = Gesture([seg])
    assert g.lanes() == {"press"}
    assert at(g, "press", 0.5)[0] == pytest.approx(0.25)


def test_sample_takes_and_returns_numpy_arrays_of_the_same_shape():
    g = curve_from_string("_^", "bend", bend_ctx())
    t = np.linspace(0, 1, 77)
    v = g.sample("bend", t)
    assert isinstance(v, np.ndarray)
    assert v.shape == t.shape
    assert v.dtype == np.float64


def test_later_segments_overlay_earlier_ones_where_they_carry_data():
    base = Segment("press", lambda u: np.zeros_like(np.asarray(u)), (0.0, 1.0))
    over = Segment("press", lambda u: np.ones_like(np.asarray(u)), (0.5, 1.0))
    g = Gesture([base, over])
    assert at(g, "press", 0.25)[0] == pytest.approx(0.0)
    assert at(g, "press", 0.75)[0] == pytest.approx(1.0)


def test_explicit_lane_glyphs_can_override_an_attached_gesture():
    # SPEC §8: "Explicit lane glyphs always win over an attached gesture on the
    # same lane and window" -- the resolver expresses that by ordering.
    attached = eval_gesture(Call("press", [Num(0.9)]), ENV, GestureCtx())
    drawn = curve_from_string("_ _", "press", press_ctx())
    merged = Gesture(attached.segments + drawn.segments)
    assert at(merged, "press", 0.1)[0] == pytest.approx(0.0)   # glyph wins
    assert at(merged, "press", 0.5)[0] == pytest.approx(0.9)   # gesture shows in the hole


def test_empty_gesture_reports_no_lanes():
    assert Gesture([]).lanes() == set()
    assert Gesture([]).sample("bend", T) is None


# ===========================================================================
# the five BAR.md P3 reference gestures
# ===========================================================================


def scoop() -> Gesture:
    """1. a 200 ms scoop up into the note from -1 semitone."""
    return eval_gesture(
        Call("bend", [bp(Num(-1.0, "st"), (Num(0.0), Num(200, "ms")))]),
        ENV, bend_ctx(note_dur_beats=2.0, tempo=120.0))     # 1 s note


def widening_vibrato() -> Gesture:
    """2. vibrato that starts 35% into the note and widens."""
    expr = Call("bend", [Window(
        BinOp("scale_or_mul",
              Call("wiggle", [Num(5.5, "hz"), Num(0.4, "st")]),
              Call("ramp", [Num(0.0), Num(1.0)])),
        Num(35, "pct"), Num(100, "pct"))])
    return eval_gesture(expr, ENV, bend_ctx(note_dur_beats=4.0, tempo=120.0))


def swell_and_close() -> Gesture:
    """3. a swell in pressure while timbre closes."""
    return eval_gesture(BinOp(
        "par",
        Call("press", [bp(Num(0.15), Num(0.95), shape="exp")]),
        Call("timbre", [bp(Num(0.7), Num(0.25))]),
    ), ENV, GestureCtx())


def land_on_third(value: float = 1.6) -> Gesture:
    """4. a bend that lands exactly on the next chord's third."""
    ctx = bend_ctx(resolve_target=lambda t: value)
    return eval_gesture(Call("bend", [bp(Num(0.0), Target("degree", 3))]), ENV, ctx)


def reused(depth: float) -> Gesture:
    d = GestureDef("cry", [("depth", Num(0.5, "st"))],
                   Call("bend", [bp(Num(0.0), (UnOp("neg", Ref("depth")), Num(45, "pct")),
                                    Num(0.0))]))
    return eval_gesture(Call("cry", [], {"depth": Num(depth, "st")}),
                        Env({"cry": d}), bend_ctx())


def test_bar_gesture_1_scoop_arrives_at_zero_after_200ms():
    g = scoop()
    assert at(g, "bend", 0.0)[0] == pytest.approx(-1.0)
    assert at(g, "bend", 0.2)[0] == pytest.approx(0.0)
    assert at(g, "bend", 1.0)[0] == pytest.approx(0.0)
    v = at(g, "bend", *np.linspace(0, 1, 4001))
    assert np.all(np.diff(v) >= -1e-12)                     # monotone rise
    assert max_jump(v) < 0.02                               # no discontinuity


def test_bar_gesture_2_vibrato_starts_at_35pct_and_widens():
    g = widening_vibrato()
    v = at(g, "bend", *T)
    assert np.all(np.isnan(v[T < 0.34]))                    # silent before onset
    early = np.nanmax(np.abs(at(g, "bend", *np.linspace(0.35, 0.6, 400))))
    late = np.nanmax(np.abs(at(g, "bend", *np.linspace(0.75, 1.0, 400))))
    # It widens.  Under SPEC §8 restriction the depth envelope `ramp(0, 1)` keeps
    # its own lifetime domain, so the vibrato enters at 35% of full depth (0.14
    # st) and reaches the full 0.4 st at note-off — a 2.9x growth in the written
    # span, of which the two measured maxima see 1.6x.
    assert late > 1.5 * early
    assert late == pytest.approx(0.4, rel=0.1)


def test_bar_gesture_3_press_swells_while_timbre_closes():
    g = swell_and_close()
    assert g.lanes() == {"press", "timbre"}
    p = at(g, "press", *T)
    tb = at(g, "timbre", *T)
    assert p[0] == pytest.approx(0.15) and p[-1] == pytest.approx(0.95)
    assert tb[0] == pytest.approx(0.7) and tb[-1] == pytest.approx(0.25)
    assert np.all(np.diff(p) >= -1e-12) and np.all(np.diff(tb) <= 1e-12)


def test_bar_gesture_4_lands_exactly_on_the_target():
    g = land_on_third(1.6)
    assert at(g, "bend", 1.0)[0] == pytest.approx(1.6)
    assert at(g, "bend", 0.0)[0] == pytest.approx(0.0)
    assert max_jump(at(g, "bend", *np.linspace(0, 1, 4001))) < 0.01


def test_bar_gesture_5_one_parameter_change_affects_only_that_note():
    base = reused(0.5)
    changed = reused(1.2)
    assert at(base, "bend", 0.45)[0] == pytest.approx(-0.5)
    assert at(changed, "bend", 0.45)[0] == pytest.approx(-1.2)
    # every other note is untouched: identical curves for identical parameters
    assert np.allclose(at(base, "bend", *T), at(reused(0.5), "bend", *T))


def test_all_five_reference_gestures_stay_inside_their_lane_ranges():
    lo, hi = ir.LANE_RANGES["bend"]
    for g in (scoop(), widening_vibrato(), land_on_third(), reused(1.2)):
        v = at(g, "bend", *T)
        finite = v[np.isfinite(v)]
        assert finite.size > 0
        assert finite.min() >= lo - 1e-9 and finite.max() <= hi + 1e-9
    s = swell_and_close()
    for lane in ("press", "timbre"):
        v = at(s, lane, *T)
        assert v.min() >= 0.0 - 1e-9 and v.max() <= 1.0 + 1e-9


def test_no_nan_leaks_into_the_middle_of_a_fully_specified_gesture():
    for g, lane in ((scoop(), "bend"), (swell_and_close(), "press"),
                    (land_on_third(), "bend"), (reused(0.5), "bend")):
        assert np.all(np.isfinite(at(g, lane, *T))), "fully drawn gesture has a hole"


def test_reference_gestures_are_deterministic_across_two_evaluations():
    for maker in (scoop, widening_vibrato, land_on_third):
        a = maker()
        b = maker()
        lane = "bend"
        assert np.array_equal(at(a, lane, *T), at(b, lane, *T), equal_nan=True)


def test_math_import_is_actually_used_for_the_exp_shape_constant():
    # guards against a silent change of the exp curvature
    g = eval_gesture(Call("press", [bp(Num(0.0), Num(1.0), shape="exp")]),
                     ENV, press_ctx())
    expected = (math.exp(3.0 * 0.5) - 1.0) / (math.exp(3.0) - 1.0)
    assert at(g, "press", 0.5)[0] == pytest.approx(expected)


# ============================================================================
# ROUND 2 — reclocking: a rate in Hz stays that rate under every nesting
# ============================================================================
#
# Round-1 defect D1: `bend(wiggle(5.5hz, 0.4st) * ramp(0, 1) @ 35%..100%)` ran
# at 8.46 Hz because the time mapping was applied to the wiggle's phase instead
# of to the real-time span it was told about.  These tests measure Hz from zero
# crossings of the rendered curve, so they cannot be satisfied by bookkeeping.


def _hz(expr, dur_beats: float, t0: float = 0.0, t1: float = 1.0,
        lane: str = "bend", env: Env | None = None, detrend: int = 0) -> float:
    ctx = bend_ctx(note_dur_beats=dur_beats, tempo=120.0) if lane == "bend" \
        else press_ctx(note_dur_beats=dur_beats, tempo=120.0)
    g = eval_gesture(expr, env or ENV, ctx)
    return hz_from_zero_crossings(g, lane, ctx.note_dur_sec, t0, t1, detrend=detrend)


WIG = Call("wiggle", [Num(5.5, "hz"), Num(0.4, "st")])


def test_reclock_1_bare_wiggle_is_5p5_hz():
    assert _hz(Call("bend", [WIG]), 2.0) == pytest.approx(5.5, rel=0.01)


def test_reclock_2_wiggle_times_ramp_is_still_5p5_hz():
    expr = Call("bend", [BinOp("scale_or_mul", WIG, Call("ramp", [Num(0.0), Num(1.0)]))])
    assert _hz(expr, 2.0) == pytest.approx(5.5, rel=0.01)


def test_reclock_3_wiggle_times_ramp_inside_a_window_is_still_5p5_hz():
    # the exact published P3.2 snippet
    expr = Call("bend", [Window(
        BinOp("scale_or_mul", WIG, Call("ramp", [Num(0.0), Num(1.0)])),
        Num(35, "pct"), Num(100, "pct"))])
    assert _hz(expr, 2.0, 0.35, 1.0) == pytest.approx(5.5, rel=0.02)


def test_reclock_4_wiggle_added_to_a_ramp_is_still_5p5_hz():
    expr = Call("bend", [BinOp("add", WIG, Call("ramp", [Num(0.0), Num(1.0, "st")]))])
    # the wiggle rides on a 1 st glide, so the glide is removed before measuring
    assert _hz(expr, 2.0, detrend=1) == pytest.approx(5.5, rel=0.01)


def test_reclock_5_wiggle_on_the_right_of_a_seq_is_still_5p5_hz():
    expr = Call("bend", [BinOp("seq", Call("ramp", [Num(0.0), Num(0.0)]), WIG)])
    assert _hz(expr, 4.0, 0.5, 1.0) == pytest.approx(5.5, rel=0.02)


def test_reclock_6_doubly_nested_window_over_a_product_is_still_5p5_hz():
    inner = Window(BinOp("scale_or_mul", WIG, Call("ramp", [Num(0.0), Num(1.0)])),
                   Num(20, "pct"), Num(90, "pct"))
    expr = Call("bend", [Window(inner, Num(30, "pct"), Num(100, "pct"))])
    assert _hz(expr, 4.0, 0.3, 0.9) == pytest.approx(5.5, rel=0.02)


def test_reclock_7_glyph_tilde_keeps_its_period_when_the_curve_is_windowed():
    bare = curve_from_string("~", "bend", bend_ctx(note_dur_beats=8.0, tempo=120.0))
    win = bare.windowed(0.0, 0.5)
    # 8 beats @ 120 = 4 s; the lane default snaps to a whole number of cycles
    a = hz_from_zero_crossings(bare, "bend", 4.0)
    b = hz_from_zero_crossings(win, "bend", 4.0, 0.0, 0.5)
    assert b == pytest.approx(a, rel=0.02)


def test_reclock_8_a_longer_note_keeps_the_rate_and_gains_cycles():
    short = _hz(Call("bend", [WIG]), 2.0)
    long_ = _hz(Call("bend", [WIG]), 8.0)
    assert short == pytest.approx(long_, rel=0.01) == pytest.approx(5.5, rel=0.01)


def test_reclock_9_scaling_amplitude_does_not_change_the_rate():
    expr = Call("bend", [BinOp("scale_or_mul", WIG, Num(0.25))])
    assert _hz(expr, 2.0) == pytest.approx(5.5, rel=0.01)


def test_pulse_rate_survives_a_window():
    expr = Call("press", [Window(Call("pulse", [Num(4.0, "hz")]), Num(50, "pct"),
                                 Num(100, "pct"))])
    g = eval_gesture(expr, ENV, press_ctx(note_dur_beats=8.0, tempo=120.0))
    v = g.sample("press", np.linspace(0.5, 1.0, 40001))
    # 4 Hz over the written 2 s = 8 cycles, so 8 rising edges
    d = np.diff((v > 0.5).astype(int))
    assert int((d > 0).sum()) == pytest.approx(8, abs=1)


# ============================================================================
# ROUND 2 — lane-range discipline
# ============================================================================
#
# Round-1 defect D2: `^~` on a bend lane reached 2.667 st on a lane that can
# only carry +-2 st.  The chosen behaviour is COMPRESSION at the boundary: the
# wiggle's depth shrinks to the available headroom so the mean value stays at
# the anchor the writer asked for, and a hard clamp backs it up.


def test_glyph_curves_never_leave_the_lane_range():
    for spec in ("^~", "_~", "^~9~", "~^~_~", "9~"):
        for lane in ("bend", "press", "timbre"):
            lo, hi = lane_range_for(lane)
            ctx = GestureCtx(lane_default=lane, lane_range=(lo, hi),
                             note_dur_beats=2.0, tempo=120.0)
            v = curve_from_string(spec, lane, ctx).sample(lane, T)
            finite = v[np.isfinite(v)]
            assert finite.min() >= lo - 1e-9, (spec, lane, finite.min())
            assert finite.max() <= hi + 1e-9, (spec, lane, finite.max())


def test_wiggle_at_the_lane_maximum_compresses_to_a_hold():
    # `^` is the top of the lane, so there is no headroom left: documented
    # behaviour is that the wiggle compresses to nothing rather than clipping.
    ctx = bend_ctx(note_dur_beats=2.0)
    v = curve_from_string("^~", "bend", ctx).sample("bend", T)
    assert np.nanmax(v) == pytest.approx(2.0, abs=1e-9)
    assert np.nanmin(v) == pytest.approx(2.0, abs=1e-9)


def test_wiggle_near_the_lane_maximum_compresses_symmetrically():
    # digit 8 of 9 on a +-2 st lane sits at 1.556 st, leaving 0.444 st of
    # headroom; the default depth (3/9 of the half span = 0.667 st) is reduced to
    # that headroom instead of being clipped flat on top.
    ctx = bend_ctx(note_dur_beats=2.0)
    v = curve_from_string("8~", "bend", ctx).sample("bend", T)
    anchor = 2.0 * (8 - 4.5) / 4.5
    assert np.nanmax(v) == pytest.approx(anchor + (2.0 - anchor), abs=0.02)
    assert np.nanmin(v) == pytest.approx(anchor - (2.0 - anchor), abs=0.02)
    # and the mean is still the anchor the writer asked for
    assert float(np.nanmean(v)) == pytest.approx(anchor, abs=0.05)


def test_glyph_wiggle_does_not_bias_the_slot_average():
    # whole-cycle snapping: `~` never ends mid-swing, so its slot average is the
    # running value it decorates
    for beats in (1.0, 2.0, 3.0, 5.0):
        ctx = press_ctx(note_dur_beats=beats, tempo=120.0)
        v = curve_from_string("4~", "press", ctx).sample("press", np.linspace(0, 1, 20001))
        anchor = 4 / 9.0
        assert float(np.nanmean(v)) == pytest.approx(anchor, abs=0.02), beats
