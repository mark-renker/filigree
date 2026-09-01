"""P4 tests: MPE renderer + realtime output.

Every test is built on synthetic ``ir.Score`` objects constructed here, so this
file has no dependency on parse.py / resolve.py / theory.py.  Each assertion
maps to a bullet of ``refs/BAR.md`` section P4 (RP-053 conformance, as digested
in ``research/mpe_technical.md``).
"""

from __future__ import annotations

import math
import os
import struct
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "src"), os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import smf_parse                                        # noqa: E402
from audit_mpe import (audit_file, bend_roundtrip_error,  # noqa: E402
                       kind_of, per_channel, rpn_writes, synthetic_score)

from filigree import ir, mpe, realtime                   # noqa: E402
from filigree.mpe import (CC_BANK_RPN_LSB, CC_BANK_RPN_MSB, CC_DATA_LSB,  # noqa: E402
                          CC_DATA_MSB, CC_TIMBRE, DEFAULT_TIMBRE, MpeOptions,
                          allocate_channels, bend_bytes, bend_to_semitones,
                          config_messages, render_events, render_midifile,
                          hold_budget_cents, hold_error, render_stats,
                          semitones_to_bend, thin, write_midi)


# --------------------------------------------------------------------------- #
# fixtures / helpers
# --------------------------------------------------------------------------- #

def curve(lane, fn, start, dur, n=201):
    return ir.Curve(lane=lane, points=[(start + dur * i / (n - 1), float(fn(i / (n - 1))))
                                       for i in range(n)])


def one_note_score(**kw):
    n = ir.Note(start=0.0, dur=2.0, pitch=60, velocity=90, stave="s", **kw)
    return ir.Score(tempo=120.0, staves=[ir.StaveIR(name="s", notes=[n])]), n


@pytest.fixture()
def synth():
    return synthetic_score()


@pytest.fixture()
def rendered(tmp_path, synth):
    opts = MpeOptions()
    path = str(tmp_path / "synth.mid")
    write_midi(synth, path, opts)
    return synth, opts, path


def stream(path):
    return smf_parse.parse_smf(path).voice_events()


# --------------------------------------------------------------------------- #
# 1. numerics (research/mpe_technical.md §6.1)
# --------------------------------------------------------------------------- #

def test_semitones_to_bend_centre():
    assert semitones_to_bend(0.0, 48) == 0
    assert bend_bytes(0) == (0x00, 0x40)                     # centre = 00 40


def test_semitones_to_bend_scale_and_clamp():
    assert semitones_to_bend(1.0, 48) == 171                 # 8192/48 = 170.67
    assert semitones_to_bend(12.0, 48) == 2048               # one octave
    assert semitones_to_bend(-1.0, 48) == -171
    assert semitones_to_bend(96.0, 48) == 8191               # clamped
    assert semitones_to_bend(-96.0, 48) == -8192


def test_bend_bytes_are_7bit():
    for st in (-48.0, -2.5, -0.01, 0.0, 0.33, 12.0, 47.9):
        lsb, msb = bend_bytes(semitones_to_bend(st, 48))
        assert 0 <= lsb <= 127 and 0 <= msb <= 127


def test_bend_quantisation_under_a_cent():
    # 48*100/8192 = 0.586 cents per LSB
    for st in (0.0, 0.1, 0.25, 1.0, -0.75):
        back = bend_to_semitones(semitones_to_bend(st, 48), 48)
        assert abs(back - st) * 100 <= 0.6


def test_thin_bounds_the_zero_order_hold_error():
    """The guarantee is stated in HOLD semantics (round-2 fix).

    A receiver holds the last transmitted value, so what must be bounded is
    ``|value_held(t) - value_true(t)|`` at every grid sample - not the error of
    an interpolated reconstruction.  ``hold_error`` measures exactly that.
    """
    frames = [(i * 0.005, int(round(100 * math.sin(2 * math.pi * 6 * i * 0.005))))
              for i in range(201)]
    for tol in (2, 5, 12, 30):
        out = thin(frames, tol=tol, min_dt=0.005, force_idx={0})
        assert out[0] == frames[0]
        assert hold_error(frames, out) <= tol, (tol, hold_error(frames, out))
        # extrema are emitted at their own time, so peaks are never shaved off
        assert max(v for _, v in out) == max(v for _, v in frames)
        assert min(v for _, v in out) == min(v for _, v in frames)
    # looser tolerance never costs more events than a tighter one
    counts = [len(thin(frames, tol=t, min_dt=0.005, force_idx={0}))
              for t in (2, 5, 12, 30)]
    assert counts == sorted(counts, reverse=True), counts


def test_thin_never_subdivides_the_grid():
    frames = [(i * 0.005, i * 40) for i in range(60)]        # brutal ramp
    out = thin(frames, tol=1, min_dt=0.005)
    gaps = [b - a for (a, _), (b, _) in zip(out, out[1:])]
    assert gaps and min(gaps) >= 0.005 - 1e-9
    assert len(out) <= len(frames)


def test_thin_flat_region_collapses_to_one_point():
    frames = [(i * 0.005, 500) for i in range(200)]
    out = thin(frames, tol=2, min_dt=0.005)
    assert len(out) == 1 and hold_error(frames, out) == 0


# --------------------------------------------------------------------------- #
# 2. zone configuration (RP-053 §1.2, §1.3)
# --------------------------------------------------------------------------- #

def test_mcm_on_channel_one_mm_15():
    msgs = config_messages(MpeOptions())
    recs = rpn_writes([(0, bytes(m)) for m in msgs])
    mcm = [r for r in recs if (r["msb"], r["lsb"]) == (0, 6) and r["channel"] == 0]
    assert len(mcm) == 1
    assert mcm[0]["data_msb"] == 15                           # mm = 15 members
    assert mcm[0]["msb_first"] is True                        # CC101 before CC100
    assert mcm[0]["closed"] is True                           # null RPN close


def test_upper_zone_switched_off():
    recs = rpn_writes([(0, bytes(m)) for m in config_messages(MpeOptions())])
    up = [r for r in recs if (r["msb"], r["lsb"]) == (0, 6) and r["channel"] == 15]
    assert len(up) == 1 and up[0]["data_msb"] == 0


def test_rpn0_on_master_and_every_member():
    opts = MpeOptions()
    recs = rpn_writes([(0, bytes(m)) for m in config_messages(opts)])
    br = {r["channel"]: r for r in recs if (r["msb"], r["lsb"]) == (0, 0)}
    assert br[0]["data_msb"] == 2                             # zone bend = 2 st
    for ch in opts.members:
        assert ch in br, "no RPN 0 on member channel %d" % (ch + 1)
        assert br[ch]["data_msb"] == 48
        assert br[ch]["data_lsb"] == 0
        assert br[ch]["msb_first"] is True
        assert br[ch]["closed"] is True


def test_config_bend_range_follows_options():
    recs = rpn_writes([(0, bytes(m)) for m in config_messages(MpeOptions(bend_range=24.0))])
    br = {r["channel"]: r for r in recs if (r["msb"], r["lsb"]) == (0, 0)}
    assert br[1]["data_msb"] == 24


def test_config_rpn_byte_pattern():
    msgs = config_messages(MpeOptions())
    ccs = [(m[1], m[2]) for m in msgs if (m[0] & 0xF0) == 0xB0 and (m[0] & 0x0F) == 0]
    # first: reset-all-controllers, then the MCM triple, then the null RPN
    assert ccs[0] == (121, 0)
    assert ccs[1] == (CC_BANK_RPN_MSB, 0)
    assert ccs[2] == (CC_BANK_RPN_LSB, 6)
    assert ccs[3] == (CC_DATA_MSB, 15)
    assert ccs[4] == (CC_BANK_RPN_MSB, 127) and ccs[5] == (CC_BANK_RPN_LSB, 127)


def test_config_absent_when_disabled():
    score, _ = one_note_score()
    evs = render_events(score, MpeOptions(emit_config=False))
    assert not [d for _, d in evs if (d[0] & 0xF0) == 0xB0 and d[1] == CC_DATA_MSB]


def test_too_many_members_rejected():
    from filigree import errors
    with pytest.raises(errors.RenderError):
        config_messages(MpeOptions(members=tuple(range(0, 16))))


# --------------------------------------------------------------------------- #
# 3. per-note event order (RP-053 §1.4)
# --------------------------------------------------------------------------- #

def test_note_on_preamble_order():
    score, n = one_note_score(curves={ir.BEND: curve(ir.BEND, lambda t: 0.5, 0.0, 2.0)})
    evs = render_events(score, MpeOptions())
    kinds = [kind_of(bytes(d)) for _, d in evs if 0x80 <= d[0] < 0xF0 and (d[0] & 0x0F) == n.channel]
    i = kinds.index("note_on")
    assert kinds[i - 3] == "bend"
    assert kinds[i - 2] == "cc%d" % CC_TIMBRE
    assert kinds[i - 1] == "press"


def test_pressure_zero_before_note_on():
    score, n = one_note_score()
    evs = [(int(b * 960), bytes(d)) for b, d in render_events(score, MpeOptions())]
    ch = per_channel(evs)[n.channel]
    idx = [i for i, (_, d) in enumerate(ch) if kind_of(d) == "note_on"][0]
    assert kind_of(ch[idx - 1][1]) == "press"
    assert ch[idx - 1][1][1] == 0


def test_default_cc74_is_64_when_no_timbre_lane():
    score, n = one_note_score()
    evs = render_events(score, MpeOptions())
    cc74 = [d for _, d in evs if (d[0] & 0xF0) == 0xB0 and d[1] == CC_TIMBRE]
    assert cc74 and cc74[0][2] == DEFAULT_TIMBRE == 64


def test_pressure_zero_immediately_precedes_note_off():
    score, n = one_note_score(curves={ir.PRESS: curve(ir.PRESS, lambda t: 0.5 + 0.4 * t, 0.0, 2.0)})
    evs = [(int(b * 960), bytes(d)) for b, d in render_events(score, MpeOptions())]
    ch = per_channel(evs)[n.channel]
    idx = [i for i, (_, d) in enumerate(ch) if kind_of(d) == "note_off"][0]
    assert kind_of(ch[idx - 1][1]) == "press"
    assert ch[idx - 1][1][1] == 0


def test_no_expression_after_note_off(rendered):
    _, _, path = rendered
    rep = audit_file(path)
    named = {n: (ok, d) for n, ok, d in rep.checks}
    assert named["zero expression events between note-off and next note-on"][0]


def test_no_expression_outside_note_lifetime():
    score, n = one_note_score(curves={ir.BEND: curve(ir.BEND, lambda t: t, 0.0, 2.0)})
    evs = render_events(score, MpeOptions())
    on = [b for b, d in evs if (d[0] & 0xF0) == 0x90][0]
    off = [b for b, d in evs if (d[0] & 0xF0) == 0x80][0]
    for b, d in evs:
        if (d[0] & 0xF0) in (0xE0, 0xD0) or ((d[0] & 0xF0) == 0xB0 and d[1] == CC_TIMBRE):
            assert on <= b <= off, "expression at beat %s outside [%s, %s]" % (b, on, off)


def test_note_off_is_real_status_8n():
    score, _ = one_note_score()
    evs = render_events(score, MpeOptions())
    offs = [d for _, d in evs if (d[0] & 0xF0) == 0x80]
    assert len(offs) == 1 and offs[0][2] == 64          # release velocity survives
    assert not [d for _, d in evs if (d[0] & 0xF0) == 0x90 and d[2] == 0]


def test_no_notes_on_master_channel(rendered):
    _, _, path = rendered
    for tick, data in stream(path):
        if (data[0] & 0xF0) in (0x80, 0x90):
            assert (data[0] & 0x0F) != 0


def test_no_polytouch_anywhere(rendered):
    _, _, path = rendered
    assert not [d for _, d in stream(path) if (d[0] & 0xF0) == 0xA0]


# --------------------------------------------------------------------------- #
# 4. channel allocation (RP-053 §1.5)
# --------------------------------------------------------------------------- #

def test_allocation_spreads_a_chord():
    notes = [ir.Note(start=0.0, dur=4.0, pitch=p, stave="s", id=i)
             for i, p in enumerate((60, 64, 67, 71))]
    score = ir.Score(staves=[ir.StaveIR(name="s", notes=notes)])
    allocate_channels(score, MpeOptions())
    chans = [n.channel for n in notes]
    assert len(set(chans)) == 4
    assert all(c in MpeOptions().members for c in chans)


def test_allocation_no_simultaneous_sharing():
    notes = [ir.Note(start=i * 0.25, dur=3.0, pitch=60 + i, stave="s", id=i)
             for i in range(12)]
    score = ir.Score(staves=[ir.StaveIR(name="s", notes=notes)])
    allocate_channels(score, MpeOptions())
    for a in notes:
        for b in notes:
            if a is b:
                continue
            if a.start <= b.start <= a.end:
                assert a.channel != b.channel


def test_allocation_same_pitch_affinity():
    notes = [ir.Note(start=0.0, dur=1.0, pitch=60, stave="s", id=0),
             ir.Note(start=0.0, dur=1.0, pitch=62, stave="s", id=1),
             ir.Note(start=2.0, dur=1.0, pitch=60, stave="s", id=2)]
    score = ir.Score(staves=[ir.StaveIR(name="s", notes=notes)])
    allocate_channels(score, MpeOptions())
    assert notes[2].channel == notes[0].channel      # reuse the channel that played 60


def test_allocation_prefers_never_used_channels_first():
    # a never-used channel has last_off = -1, i.e. it is the oldest release of
    # all, so a fresh note spreads onto virgin channels (RP-053 reference alloc)
    notes = [ir.Note(start=0.0, dur=1.0, pitch=60, stave="s", id=0),
             ir.Note(start=2.0, dur=1.0, pitch=61, stave="s", id=1)]
    score = ir.Score(staves=[ir.StaveIR(name="s", notes=notes)])
    allocate_channels(score, MpeOptions())
    assert notes[1].channel != notes[0].channel


def test_allocation_oldest_release_tiebreak():
    # occupy all 15 members, with the pitch-41 voice releasing first
    notes = [ir.Note(start=0.0, dur=15.0 if p != 41 else 1.0, pitch=p, stave="s", id=i)
             for i, p in enumerate(range(40, 55))]
    notes.append(ir.Note(start=20.0, dur=1.0, pitch=90, stave="s", id=99))
    score = ir.Score(staves=[ir.StaveIR(name="s", notes=notes)])
    allocate_channels(score, MpeOptions())
    oldest = [n for n in notes if n.pitch == 41][0]
    assert notes[-1].channel == oldest.channel


def test_allocation_fewest_active_when_full():
    notes = [ir.Note(start=0.0, dur=8.0, pitch=40 + i, stave="s", id=i) for i in range(15)]
    notes.append(ir.Note(start=1.0, dur=1.0, pitch=90, stave="s", id=99))
    score = ir.Score(staves=[ir.StaveIR(name="s", notes=notes)])
    allocate_channels(score, MpeOptions())
    assert notes[-1].channel in MpeOptions().members
    assert any("share a member channel" in w for w in score.warnings)


def test_allocation_is_deterministic():
    a = synthetic_score()
    b = synthetic_score()
    allocate_channels(a, MpeOptions())
    allocate_channels(b, MpeOptions())
    assert [n.channel for n in a.notes] == [n.channel for n in b.notes]


def test_allocation_rejects_bad_members():
    from filigree import errors
    score, _ = one_note_score()
    with pytest.raises(errors.RenderError):
        allocate_channels(score, MpeOptions(members=()))
    with pytest.raises(errors.RenderError):
        allocate_channels(score, MpeOptions(members=(1, 99)))


def test_no_two_simultaneous_notes_in_output(rendered):
    _, _, path = rendered
    for ch, evs in per_channel(stream(path)).items():
        depth = 0
        for tick, data in evs:
            k = kind_of(data)
            if k == "note_on":
                depth += 1
                assert depth == 1, "overlap on channel %d at tick %d" % (ch + 1, tick)
            elif k == "note_off":
                depth -= 1


# --------------------------------------------------------------------------- #
# 5. grid, deadband, dedup
# --------------------------------------------------------------------------- #

def test_pitch_grid_is_5ms():
    score, n = one_note_score(curves={
        ir.BEND: curve(ir.BEND, lambda t: 2.0 * math.sin(2 * math.pi * 5 * t), 0.0, 2.0, 401)})
    opts = MpeOptions()
    evs = render_events(score, opts)
    beats = [b for b, d in evs if (d[0] & 0xF0) == 0xE0]
    spb = 60.0 / score.tempo
    tick_s = spb / opts.ppq                       # tick-rounding slack
    assert len(beats) > 10
    for a, b in zip(beats, beats[1:]):
        assert (b - a) * spb >= opts.pitch_grid_ms / 1000.0 - tick_s


def test_pressure_and_timbre_grid_is_10ms():
    score, n = one_note_score(curves={
        ir.PRESS: curve(ir.PRESS, lambda t: 0.5 + 0.5 * math.sin(2 * math.pi * 4 * t),
                        0.0, 2.0, 401),
        ir.TIMBRE: curve(ir.TIMBRE, lambda t: 0.5 - 0.5 * math.cos(2 * math.pi * 3 * t),
                         0.0, 2.0, 401)})
    opts = MpeOptions()
    evs = render_events(score, opts)
    spb = 60.0 / score.tempo
    for pred in (lambda d: (d[0] & 0xF0) == 0xD0,
                 lambda d: (d[0] & 0xF0) == 0xB0 and d[1] == CC_TIMBRE):
        beats = [b for b, d in evs if pred(d)]
        tick_s = spb / opts.ppq
        assert len(beats) > 5
        # Distinct sample times are >= one grid interval apart.  The single
        # permitted coincidence is at the note-on tick, where the mandated
        # pressure(0) of the preamble is followed by the lane's initial value.
        for a, b in zip(beats, beats[1:]):
            if b == a:
                assert a == 0.0
                continue
            assert (b - a) * spb >= opts.grid_ms / 1000.0 - tick_s


def test_linear_ramp_needs_interior_points_under_hold_semantics():
    """Round-2 correction: a ramp does NOT thin to its endpoints.

    The round-1 renderer kept only the endpoints of a straight ramp because it
    assumed the receiver interpolates.  A hold receiver would sit at the start
    value for the whole ramp and then jump, i.e. a full-scale error.  Under hold
    semantics a ramp needs a point every time it moves by the tolerance, so a
    0 -> 127 pressure ramp needs on the order of 127 points (capped by the 10 ms
    grid over a 1 s note = 101 samples).
    """
    score, n = one_note_score(curves={ir.PRESS: curve(ir.PRESS, lambda t: t, 0.0, 2.0, 401)})
    evs = render_events(score, MpeOptions())
    press = [d[1] for _, d in evs if (d[0] & 0xF0) == 0xD0]
    assert press[0] == 0 and press[-1] == 0      # mandated zeros around the note
    assert len(press) > 50, len(press)
    interior = press[1:-1]
    assert interior == sorted(interior)          # monotone, nothing shuffled
    assert max(interior) >= 126                  # the top of the ramp is reached
    # A hold error of <= 1 LSB means consecutive transmitted values are at most
    # 2 LSB apart (the held value may be 1 low, the next 1 high).
    assert max(b - a for a, b in zip(interior, interior[1:])) <= 2
    # and the held reconstruction really is within 1 LSB of the true ramp
    frames = [(i * 0.01, min(127, int(round(127 * i / 100.0)))) for i in range(101)]
    kept = [(i * 0.01, v) for i, v in enumerate(interior)][:len(frames)]
    assert hold_error(frames, kept) <= 2


def test_dedup_no_consecutive_equal_values():
    score, n = one_note_score(curves={
        ir.BEND: curve(ir.BEND, lambda t: 0.4 * math.sin(2 * math.pi * 3 * t), 0.0, 2.0, 401)})
    evs = render_events(score, MpeOptions())
    last = None
    for _, d in evs:
        if (d[0] & 0xF0) == 0xE0:
            v = (d[2] << 7) | d[1]
            assert v != last
            last = v


def test_deadband_kills_sub_lsb_motion():
    # a bend that never exceeds 1 LSB at +-48 st (1 LSB = 0.00586 st)
    score, n = one_note_score(curves={
        ir.BEND: curve(ir.BEND, lambda t: 0.002 * math.sin(2 * math.pi * 4 * t), 0.0, 2.0, 401)})
    evs = render_events(score, MpeOptions())
    bends = [d for _, d in evs if (d[0] & 0xF0) == 0xE0]
    assert len(bends) == 1                       # only the mandatory preamble


def test_thinning_ratio_is_reported_not_targeted(synth):
    """Round-2 amendment (see refs/BAR.md P4 amendment, NOTES_P4.md fix 1).

    The thinning ratio is a *property of the music* once the hold-error bound is
    the criterion: flat and slow lanes still collapse to almost nothing, fast
    ramps legitimately need a point per grid step.  What must hold is the hold
    error, checked below.
    """
    st = render_stats(synth, MpeOptions())
    assert st.raw_frames > 600
    assert 0.0 <= st.thinning_ratio <= 1.0
    assert st.thinning_ratio >= 0.30, st.thinning_ratio      # still substantial
    budget, floor, _where = hold_budget_cents(synth, MpeOptions())
    assert st.max_hold_error_bend_cents <= budget
    assert st.max_hold_error_cc_lsb <= 1 or st.escalated_channels


def test_flat_lanes_still_thin_almost_completely():
    score, n = one_note_score(curves={
        ir.PRESS: curve(ir.PRESS, lambda t: 0.5, 0.0, 2.0, 401),
        ir.TIMBRE: curve(ir.TIMBRE, lambda t: 0.25, 0.0, 2.0, 401)})
    st = render_stats(score, MpeOptions())
    assert st.thinning_ratio >= 0.95, st.thinning_ratio


def test_expression_density_under_250_per_second(rendered):
    _, _, path = rendered
    rep = audit_file(path)
    assert rep.metrics["max_expr_events_per_sec_per_channel"] <= 250


def test_nan_regions_write_no_data():
    pts = [(0.0, 0.5), (0.5, 0.5), (1.0, float("nan")), (1.5, float("nan"))]
    score, n = one_note_score(curves={ir.TIMBRE: ir.Curve(lane=ir.TIMBRE, points=pts)})
    evs = render_events(score, MpeOptions())
    vals = [d[2] for _, d in evs if (d[0] & 0xF0) == 0xB0 and d[1] == CC_TIMBRE]
    assert vals and all(0 <= v <= 127 for v in vals)
    assert all(not math.isnan(v) for v in vals)


# --------------------------------------------------------------------------- #
# 5b. round-2 robustness policy (documented in mpe.py's module docstring)
# --------------------------------------------------------------------------- #

def test_semitones_to_bend_handles_non_finite():
    for bad in (float("nan"), float("inf"), float("-inf"), 1e300, -1e300):
        v = mpe.semitones_to_bend(bad, 48.0)
        assert -8192 <= v <= 8191
    assert mpe.semitones_to_bend(float("nan"), 48.0) == 0
    assert mpe.semitones_to_bend(float("inf"), 48.0) == 8191
    assert mpe.semitones_to_bend(float("-inf"), 48.0) == -8192


def test_inf_breakpoints_are_dropped_with_a_warning():
    pts = [(0.0, 0.0), (0.5, float("inf")), (1.0, float("-inf")), (1.5, 0.25)]
    score, n = one_note_score(curves={ir.BEND: ir.Curve(lane=ir.BEND, points=pts)})
    evs = render_events(score, MpeOptions())
    bends = [((d[2] << 7) | d[1]) - 8192 for _, d in evs if (d[0] & 0xF0) == 0xE0]
    assert bends and all(-8192 <= v <= 8191 for v in bends)
    # nothing anywhere near the range limit was synthesised out of an infinity
    assert max(abs(v) for v in bends) < 8000
    assert any("non-finite bend" in w for w in score.warnings), score.warnings


def test_nan_region_only_kills_that_region_not_the_lane():
    """NaN is ir.Curve's gap sentinel: a gap, never 'delete the lane', and
    never a warning (it is normal resolver output)."""
    pts = [(0.0, 0.0), (0.5, float("nan")), (1.0, 1.0), (2.0, 1.0)]
    score, n = one_note_score(curves={ir.BEND: ir.Curve(lane=ir.BEND, points=pts)})
    evs = render_events(score, MpeOptions())
    bends = [((d[2] << 7) | d[1]) - 8192 for _, d in evs if (d[0] & 0xF0) == 0xE0]
    assert len(bends) > 1                       # the lane survived
    assert max(bends) > 0                       # the +1 st part was written
    assert score.warnings == []                 # a gap is not an anomaly


def test_nan_is_silent_while_inf_warns_exactly_once():
    """The ir.Curve contract: NaN == gap sentinel (silent); inf == anomaly."""
    nan, inf = float("nan"), float("inf")
    gap, _ = one_note_score(curves={ir.BEND: ir.Curve(
        lane=ir.BEND, points=[(0.0, 0.0), (0.4, 0.5), (0.5, nan),
                              (1.0, nan), (1.5, 0.5), (2.0, 0.0)])})
    evs = render_events(gap, MpeOptions())
    assert gap.warnings == [], gap.warnings
    assert [d for _, d in evs if (d[0] & 0xF0) == 0xE0]        # still renders

    bad, _ = one_note_score(curves={ir.BEND: ir.Curve(
        lane=ir.BEND, points=[(0.0, 0.0), (1.0, inf), (2.0, 0.25)])})
    render_events(bad, MpeOptions())
    assert len(bad.warnings) == 1, bad.warnings
    assert "non-finite bend" in bad.warnings[0]
    assert "inf is never written" in bad.warnings[0]


def test_no_data_is_emitted_inside_a_nan_gap():
    """A hold receiver keeps the last value through a gap, so the renderer must
    emit nothing between the gap sentinel and the next real point."""
    nan = float("nan")
    pts = [(0.0, 0.0), (0.5, 1.0), (0.5001, nan), (1.5, nan), (1.75, 1.0), (2.0, 0.0)]
    score, n = one_note_score(curves={ir.BEND: ir.Curve(lane=ir.BEND, points=pts)})
    evs = render_events(score, MpeOptions())
    beats = [b for b, d in evs if (d[0] & 0xF0) == 0xE0]
    assert beats
    inside = [b for b in beats if 0.55 < b < 1.7]
    assert inside == [], inside


def test_all_nan_lane_falls_back_to_default():
    nan = float("nan")
    score, n = one_note_score(detune=0.25, curves={
        ir.BEND: ir.Curve(lane=ir.BEND, points=[(0.0, nan), (1.0, nan)]),
        ir.TIMBRE: ir.Curve(lane=ir.TIMBRE, points=[(0.0, nan), (1.0, nan)])})
    evs = render_events(score, MpeOptions())
    bends = [((d[2] << 7) | d[1]) - 8192 for _, d in evs if (d[0] & 0xF0) == 0xE0]
    cc74 = [d[2] for _, d in evs if (d[0] & 0xF0) == 0xB0 and d[1] == CC_TIMBRE]
    assert bends == [semitones_to_bend(0.25, 48.0)]      # bend -> the detune
    assert cc74 == [DEFAULT_TIMBRE]                      # CC74 -> 64
    assert score.warnings == []                          # all-NaN == all gap


def test_non_finite_start_and_detune_are_survivable():
    n = ir.Note(start=float("nan"), dur=1.0, pitch=60, stave="s",
                detune=float("inf"))
    score = ir.Score(staves=[ir.StaveIR(name="s", notes=[n])])
    evs = render_events(score, MpeOptions())
    assert [d for _, d in evs if (d[0] & 0xF0) == 0x90 and d[2]]
    assert any("non-finite" in w for w in score.warnings), score.warnings


def test_bend_clamp_warning_names_the_note_and_value():
    score, n = one_note_score(curves={
        ir.BEND: ir.Curve(lane=ir.BEND, points=[(0.0, 0.0), (2.0, -60.0)])})
    opts = MpeOptions(bend_range=12.0)
    evs = render_events(score, opts)
    bends = [((d[2] << 7) | d[1]) - 8192 for _, d in evs if (d[0] & 0xF0) == 0xE0]
    assert min(bends) == -8192                  # clamped, never wrapped
    assert max(bends) <= 8191
    w = [x for x in score.warnings if "clamped" in x]
    assert w, score.warnings
    assert "60" in w[0] and "pitch 60" in w[0] and "12" in w[0], w[0]


def test_absurd_curve_values_do_not_crash():
    score, n = one_note_score(curves={
        ir.BEND: ir.Curve(lane=ir.BEND, points=[(0.0, -1e300), (2.0, 1e300)]),
        ir.PRESS: ir.Curve(lane=ir.PRESS, points=[(0.0, 1e12), (2.0, -1e12)])})
    evs = render_events(score, MpeOptions())
    for _, d in evs:
        assert all(0 <= b <= 255 for b in d)
        if (d[0] & 0xF0) in (0xB0, 0xD0, 0x90, 0x80):
            assert all(0 <= b <= 127 for b in d[1:])


# --------------------------------------------------------------------------- #
# 5c. round-2: channel reuse and sharing never cost a note its expression
# --------------------------------------------------------------------------- #

def _preambles(evs):
    """[(channel, [kinds of the 3 events immediately before each note-on])]."""
    out = []
    for ch, stream in mpe.channel_streams(evs).items():
        seq = [d for _b, d in stream]
        for i, d in enumerate(seq):
            if (d[0] & 0xF0) == 0x90 and d[2]:
                out.append((ch, [kind_of(bytes(x)) for x in seq[max(0, i - 3):i]]))
    return out


def test_touching_notes_on_one_channel_both_get_the_full_preamble():
    """Round-2 fix: a note end is EXCLUSIVE, so note 2 may reuse the channel
    and must still get bend -> CC74 -> pressure(0) before its own note-on."""
    a = ir.Note(start=0.0, dur=1.0, pitch=60, velocity=90, stave="s",
                curves={ir.BEND: curve(ir.BEND, lambda t: 0.5 * t, 0.0, 1.0, 101)})
    b = ir.Note(start=1.0, dur=1.0, pitch=62, velocity=90, stave="s",
                curves={ir.BEND: curve(ir.BEND, lambda t: -0.5 * t, 1.0, 1.0, 101)})
    score = ir.Score(tempo=120.0, staves=[ir.StaveIR(name="s", notes=[a, b])])
    opts = MpeOptions(members=(1,))
    evs = render_events(score, opts)
    pre = _preambles(evs)
    assert len(pre) == 2
    for ch, kinds in pre:
        assert kinds == ["bend", "cc%d" % CC_TIMBRE, "press"], (ch, kinds)
    # both notes are on the one member channel, and both bend lanes are present
    assert {ch for ch, _k in pre} == {1}
    bends = [b_ for b_, d in evs if (d[0] & 0xF0) == 0xE0]
    assert len([x for x in bends if x >= 1.0]) > 3      # note 2 still bends
    assert len([x for x in bends if x < 1.0]) > 3       # note 1 still bends


def test_every_note_gets_pressure_zero_before_its_own_note_off():
    a = ir.Note(start=0.0, dur=1.0, pitch=60, stave="s")
    b = ir.Note(start=1.0, dur=1.0, pitch=62, stave="s")
    c = ir.Note(start=2.0, dur=1.0, pitch=64, stave="s")
    score = ir.Score(tempo=120.0, staves=[ir.StaveIR(name="s", notes=[a, b, c])])
    evs = render_events(score, MpeOptions(members=(1,)))
    seq = [d for _b, d in evs if (d[0] & 0x0F) == 1]
    offs = [i for i, d in enumerate(seq)
            if (d[0] & 0xF0) == 0x80 or ((d[0] & 0xF0) == 0x90 and d[2] == 0)]
    assert len(offs) == 3
    for i in offs:
        prev = seq[i - 1]
        assert (prev[0] & 0xF0) == 0xD0 and prev[1] == 0, prev


def test_more_simultaneous_notes_than_channels_keeps_every_note():
    notes = [ir.Note(start=0.0, dur=2.0, pitch=48 + i, stave="s") for i in range(20)]
    score = ir.Score(tempo=120.0, staves=[ir.StaveIR(name="s", notes=notes)])
    evs = render_events(score, MpeOptions())
    ons = [d for _b, d in evs if (d[0] & 0xF0) == 0x90 and d[2]]
    assert len(ons) == 20                      # nothing is dropped
    assert all((d[0] & 0x0F) != 0 for d in ons)          # never on the master
    for ch, kinds in _preambles(evs):
        assert kinds == ["bend", "cc%d" % CC_TIMBRE, "press"], (ch, kinds)
    assert any("share a member channel" in w for w in score.warnings)


def test_expression_never_appears_between_a_note_off_and_the_next_note_on():
    a = ir.Note(start=0.0, dur=1.0, pitch=60, stave="s",
                curves={ir.PRESS: curve(ir.PRESS, lambda t: t, 0.0, 1.0, 101)})
    b = ir.Note(start=2.0, dur=1.0, pitch=62, stave="s",
                curves={ir.PRESS: curve(ir.PRESS, lambda t: 1.0 - t, 2.0, 1.0, 101)})
    score = ir.Score(tempo=120.0, staves=[ir.StaveIR(name="s", notes=[a, b])])
    evs = render_events(score, MpeOptions(members=(1,)))
    seq = [d for _b, d in evs if (d[0] & 0x0F) == 1
           and not ((d[0] & 0xF0) == 0xB0 and d[1] in mpe.CONFIG_CCS)]
    depth = 0
    for i, d in enumerate(seq):
        hi = d[0] & 0xF0
        if hi == 0x90 and d[2]:
            depth += 1
        elif hi == 0x80 or (hi == 0x90 and not d[2]):
            depth -= 1
        elif depth == 0:
            # only the next note's mandated 3-event preamble may appear here
            nxt = next((j for j in range(i, len(seq))
                        if (seq[j][0] & 0xF0) == 0x90 and seq[j][2]), None)
            assert nxt is not None and nxt - i <= 3, (i, d)


def test_panic_stream_recentres_bend_and_stops_every_note():
    opts = MpeOptions(members=(1, 2))
    msgs = realtime.panic_stream(opts, sounding={(1, 60), (2, 64)})
    kinds = [(d[0] & 0xF0, d[0] & 0x0F, d[1] if len(d) > 1 else None) for d in msgs]
    assert (0x80, 1, 60) in kinds and (0x80, 2, 64) in kinds     # real note-offs
    for ch in (0, 1, 2, 15):
        assert (0xD0, ch, 0) in kinds                            # pressure 0
        assert (0xE0, ch, 0x00) in kinds                         # bend re-centred
        for cc in (mpe.CC_SUSTAIN, mpe.CC_RESET_ALL, mpe.CC_ALL_NOTES_OFF,
                   mpe.CC_ALL_SOUND_OFF):
            assert (0xB0, ch, cc) in kinds, (ch, cc)
    for d in msgs:
        if (d[0] & 0xF0) == 0xE0:
            assert (d[1], d[2]) == (0x00, 0x40)                   # exactly centre


def test_static_detune_lands_in_preamble_bend():
    score, n = one_note_score(detune=0.5)
    evs = render_events(score, MpeOptions())
    bends = [d for _, d in evs if (d[0] & 0xF0) == 0xE0]
    assert len(bends) == 1
    v = ((bends[0][2] << 7) | bends[0][1]) - 8192
    assert abs(bend_to_semitones(v, 48) - 0.5) * 100 <= 1.0


def test_detune_and_bend_curve_add():
    score, n = one_note_score(detune=-0.25,
                              curves={ir.BEND: curve(ir.BEND, lambda t: 1.0, 0.0, 2.0)})
    evs = render_events(score, MpeOptions())
    d = [m for _, m in evs if (m[0] & 0xF0) == 0xE0][0]
    v = ((d[2] << 7) | d[1]) - 8192
    assert abs(bend_to_semitones(v, 48) - 0.75) * 100 <= 1.0


def test_press_and_amp_map_to_7bit():
    score, n = one_note_score(curves={
        ir.PRESS: curve(ir.PRESS, lambda t: t, 0.0, 2.0),
        ir.AMP: curve(ir.AMP, lambda t: t, 0.0, 2.0)})
    evs = render_events(score, MpeOptions())
    press = [d[1] for _, d in evs if (d[0] & 0xF0) == 0xD0]
    amp = [d[2] for _, d in evs if (d[0] & 0xF0) == 0xB0 and d[1] == mpe.CC_AMP]
    assert min(press) == 0                       # mandated pressure 0
    assert max(press) >= 120                     # reaches the top of the curve
    assert amp and max(amp) >= 120 and all(0 <= v <= 127 for v in amp)


def test_numbered_cc_lane():
    score, n = one_note_score(curves={"cc17": curve("cc17", lambda t: 1.0, 0.0, 2.0)})
    evs = render_events(score, MpeOptions())
    assert [d for _, d in evs if (d[0] & 0xF0) == 0xB0 and d[1] == 17 and d[2] == 127]


# --------------------------------------------------------------------------- #
# 6. SMF layout + independent parser
# --------------------------------------------------------------------------- #

def test_smf_type_and_resolution(rendered):
    _, _, path = rendered
    smf = smf_parse.parse_smf(path)
    assert smf.fmt == 1
    assert smf.division == 960
    assert smf.ppq == 960


def test_one_track_per_stave_plus_conductor(rendered):
    score, _, path = rendered
    smf = smf_parse.parse_smf(path)
    assert len(smf.tracks) == 1 + len(score.staves) == 3
    assert [tr.name for tr in smf.tracks][1:] == [s.name for s in score.staves]


def test_conductor_track_has_tempo_and_meter(rendered):
    score, _, path = rendered
    smf = smf_parse.parse_smf(path)
    metas = {e.meta_type for e in smf.tracks[0].events if e.kind == "meta"}
    assert 0x51 in metas and 0x58 in metas
    assert abs(60e6 / smf.tempo() - score.tempo) < 0.01


def test_single_track_mode(tmp_path, synth):
    path = str(tmp_path / "single.mid")
    write_midi(synth, path, MpeOptions(one_track_per_stave=False))
    smf = smf_parse.parse_smf(path)
    assert len(smf.tracks) == 2
    assert smf.tracks[1].name == "MPE Zone 1"


def test_independent_parser_matches_mido(rendered):
    import mido
    _, _, path = rendered
    ours = stream(path)
    mid = mido.MidiFile(path)
    theirs = []
    for ti, track in enumerate(mid.tracks):
        tick = 0
        for i, msg in enumerate(track):
            tick += msg.time
            if not msg.is_meta and msg.type != "sysex":
                theirs.append((tick, ti, i, bytes(msg.bytes())))
    theirs.sort(key=lambda r: (r[0], r[1], r[2]))
    assert ours == [(t, d) for t, _, _, d in theirs]
    assert len(ours) > 50


def test_independent_parser_handles_running_status():
    # MThd + one MTrk using running status for a second note-on
    track = bytes([0x00, 0x90, 0x3C, 0x40,      # note on
                   0x10, 0x3E, 0x40,            # running status note on
                   0x00, 0xFF, 0x2F, 0x00])
    buf = (b"MThd" + struct.pack(">IHHH", 6, 1, 1, 960)
           + b"MTrk" + struct.pack(">I", len(track)) + track)
    smf = smf_parse.parse_bytes(buf)
    evs = smf.voice_events()
    assert len(evs) == 2
    assert evs[0][1] == bytes([0x90, 0x3C, 0x40])
    assert evs[1] == (16, bytes([0x90, 0x3E, 0x40]))


def test_independent_parser_rejects_garbage():
    with pytest.raises(smf_parse.SmfError):
        smf_parse.parse_bytes(b"not a midi file at all")


def test_midifile_reloads_in_mido(rendered):
    import mido
    _, _, path = rendered
    mid = mido.MidiFile(path)
    assert mid.type == 1 and mid.ticks_per_beat == 960
    assert sum(1 for _ in mid) > 50


def test_render_midifile_object(synth):
    mid = render_midifile(synth, MpeOptions())
    assert mid.type == 1
    assert mid.ticks_per_beat == 960
    assert all(msg.time >= 0 for tr in mid.tracks for msg in tr)


# --------------------------------------------------------------------------- #
# 7. round-trip accuracy
# --------------------------------------------------------------------------- #

def test_bend_roundtrip_within_the_hold_budget(rendered):
    """Hold-model round trip: tolerance + the grid/rate resolution floor."""
    score, opts, path = rendered
    worst, where = bend_roundtrip_error(score, path, opts.bend_range, opts)
    budget, floor, bwhere = hold_budget_cents(score, opts)
    assert worst <= budget, ("worst=%.3f cents %s vs budget %.3f (floor %.3f %s)"
                             % (worst, where, budget, floor, bwhere))
    assert floor > 0.0                       # a real 6 Hz vibrato does move
    # the honest number is strictly worse than the old interpolating one
    lin, _ = bend_roundtrip_error(score, path, opts.bend_range, opts,
                                  model="linear")
    assert worst >= lin - 1e-9


def test_bend_roundtrip_vibrato_only(tmp_path):
    n = ir.Note(start=0.0, dur=2.0, pitch=64, velocity=100, stave="s",
                curves={ir.BEND: curve(ir.BEND,
                                       lambda t: 0.25 * math.sin(2 * math.pi * 6 * t),
                                       0.0, 2.0, 401)})
    score = ir.Score(tempo=120.0, staves=[ir.StaveIR(name="s", notes=[n])])
    opts = MpeOptions()
    path = str(tmp_path / "vib.mid")
    write_midi(score, path, opts)
    worst, where = bend_roundtrip_error(score, path, opts.bend_range, opts)
    budget, _floor, _bw = hold_budget_cents(score, opts)
    assert worst <= budget, "worst=%.3f cents %s" % (worst, where)


def test_slow_bend_holds_within_three_cents(tmp_path):
    """When the grid CAN resolve the curve, the 3-cent bar is met outright."""
    n = ir.Note(start=0.0, dur=4.0, pitch=64, velocity=100, stave="s",
                curves={ir.BEND: curve(ir.BEND,
                                       lambda t: 0.5 * math.sin(2 * math.pi * 0.25 * t),
                                       0.0, 4.0, 401)})
    score = ir.Score(tempo=120.0, staves=[ir.StaveIR(name="s", notes=[n])])
    opts = MpeOptions()
    path = str(tmp_path / "slow.mid")
    write_midi(score, path, opts)
    worst, where = bend_roundtrip_error(score, path, opts.bend_range, opts)
    assert worst <= 3.0, "worst=%.3f cents %s" % (worst, where)


def test_bend_extrema_preserved(tmp_path):
    n = ir.Note(start=0.0, dur=2.0, pitch=64, stave="s",
                curves={ir.BEND: curve(ir.BEND,
                                       lambda t: 0.5 * math.sin(2 * math.pi * 3 * t),
                                       0.0, 2.0, 401)})
    score = ir.Score(tempo=120.0, staves=[ir.StaveIR(name="s", notes=[n])])
    evs = render_events(score, MpeOptions())
    vals = [bend_to_semitones(((d[2] << 7) | d[1]) - 8192, 48)
            for _, d in evs if (d[0] & 0xF0) == 0xE0]
    assert max(vals) >= 0.49 and min(vals) <= -0.49


# --------------------------------------------------------------------------- #
# 8. determinism + stream shape
# --------------------------------------------------------------------------- #

def test_render_is_byte_identical_across_runs(tmp_path):
    p1, p2 = str(tmp_path / "a.mid"), str(tmp_path / "b.mid")
    write_midi(synthetic_score(), p1, MpeOptions())
    write_midi(synthetic_score(), p2, MpeOptions())
    assert open(p1, "rb").read() == open(p2, "rb").read()


def test_render_events_sorted_and_wellformed(synth):
    evs = render_events(synth, MpeOptions())
    assert evs == sorted(evs, key=lambda e: e[0]) or all(
        a[0] <= b[0] for a, b in zip(evs, evs[1:]))
    for beat, data in evs:
        assert beat >= 0.0
        assert 0x80 <= data[0] <= 0xEF
        assert all(0 <= b <= 127 for b in data[1:])


def test_render_events_note_counts_balance(synth):
    evs = render_events(synth, MpeOptions())
    ons = [d for _, d in evs if (d[0] & 0xF0) == 0x90]
    offs = [d for _, d in evs if (d[0] & 0xF0) == 0x80]
    assert len(ons) == len(offs) == len(synth.notes)


def test_velocity_is_clamped():
    n = ir.Note(start=0.0, dur=1.0, pitch=60, velocity=200, stave="s")
    score = ir.Score(staves=[ir.StaveIR(name="s", notes=[n])])
    evs = render_events(score, MpeOptions())
    on = [d for _, d in evs if (d[0] & 0xF0) == 0x90][0]
    assert on[2] == 127


def test_zero_length_notes_get_one_tick_and_a_warning():
    """Round-2 policy: a zero-length note is never silently dropped."""
    n = ir.Note(start=0.0, dur=0.0, pitch=60, stave="s")
    score = ir.Score(staves=[ir.StaveIR(name="s", notes=[n])])
    opts = MpeOptions()
    evs = render_events(score, opts)
    ons = [(b, d) for b, d in evs if (d[0] & 0xF0) == 0x90 and d[2]]
    offs = [(b, d) for b, d in evs if (d[0] & 0xF0) == 0x80
            or ((d[0] & 0xF0) == 0x90 and d[2] == 0)]
    assert len(ons) == 1 and len(offs) == 1
    dt_ticks = round((offs[0][0] - ons[0][0]) * opts.ppq)
    assert dt_ticks == 1                                   # exactly one tick
    assert any("minimum duration" in w for w in score.warnings), score.warnings


def test_negative_length_note_is_also_one_tick():
    n = ir.Note(start=1.0, dur=-3.0, pitch=60, stave="s")
    score = ir.Score(staves=[ir.StaveIR(name="s", notes=[n])])
    evs = render_events(score, MpeOptions())
    assert len([d for _, d in evs if (d[0] & 0xF0) == 0x90 and d[2]]) == 1
    assert any("minimum duration" in w for w in score.warnings)


def test_empty_score_renders_config_only():
    score = ir.Score(staves=[])
    evs = render_events(score, MpeOptions())
    assert evs and all((d[0] & 0xF0) == 0xB0 for _, d in evs)


# --------------------------------------------------------------------------- #
# 9. the auditor itself
# --------------------------------------------------------------------------- #

def test_audit_passes_on_clean_file(rendered):
    score, opts, path = rendered
    rep = audit_file(path, score=score, opts=opts)
    assert rep.failures == [], rep.render()
    assert len(rep.checks) >= 20


def test_audit_fails_without_config(tmp_path, synth):
    path = str(tmp_path / "noconfig.mid")
    write_midi(synth, path, MpeOptions(emit_config=False))
    rep = audit_file(path)
    names = [n for n, ok, _ in rep.checks if not ok]
    assert any("MCM" in n for n in names)
    assert rep.failures


def test_audit_cli_exit_codes(tmp_path, synth):
    import audit_mpe
    assert audit_mpe.main(["--synth"]) == 0
    path = str(tmp_path / "bad.mid")
    write_midi(synth, path, MpeOptions(emit_config=False))
    assert audit_mpe.main([path]) == 1


def test_audit_reports_thinning_and_density(rendered):
    _, _, path = rendered
    rep = audit_file(path)
    assert 0.0 <= rep.metrics["thinning_ratio_curved_lanes"] <= 1.0
    assert rep.metrics["thinning_ratio_all_lanes"] >= 0.60
    assert rep.metrics["max_expr_events_per_sec_per_channel"] > 0


# --------------------------------------------------------------------------- #
# 10. realtime
# --------------------------------------------------------------------------- #

def test_realtime_imports_without_rtmidi():
    assert hasattr(realtime, "list_ports") and hasattr(realtime, "play")
    assert realtime.PORT_NAME == "Filigree"


def test_list_ports_never_raises():
    ports = realtime.list_ports()
    assert isinstance(ports, list)


def test_dry_run_matches_render_events(synth):
    assert realtime.dry_run(synth, MpeOptions()) == render_events(synth, MpeOptions())


def test_play_reports_a_clear_error_without_a_backend(synth):
    from filigree import errors
    try:
        import rtmidi  # noqa: F401
        pytest.skip("rtmidi present: cannot test the missing-backend path")
    except ImportError:
        pass
    with pytest.raises((errors.RenderError, OSError, IOError)):
        realtime.play(synth, port=None, opts=MpeOptions())


def test_conductor_track_is_named_conductor(rendered):
    _, _, path = rendered
    assert smf_parse.parse_smf(path).tracks[0].name == "conductor"


def test_title_is_written_as_a_text_meta(rendered):
    score, _, path = rendered
    texts = [e.meta_data.decode("latin-1")
             for e in smf_parse.parse_smf(path).tracks[0].events
             if e.kind == "meta" and e.meta_type == 0x01]
    assert score.title in texts
