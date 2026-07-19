"""Hand-calculated benchmark problems for the beam engine.

Each test's expected values are derived independently by hand (see the
comments) and checked against the engine's output, per the project's
validation requirement: every release verified against known solutions.
"""
import pytest

from beams.load_inputs import entered_uniform_loads_to_plf
from engine import SPF_NO2, PointLoad, Section, UniformLoad, design_beam, get_material
from engine.beam import (
    analyze,
    back_span_deflection,
    deflection_at,
    max_deflection_between,
)
from engine.factors import DEFLECTION_LIMITS, required_bearing_length
from engine.span import clear_span


def test_simple_span_uniform_load_reactions_shear_moment():
    # 12 ft span, uniform total load w = 100 plf (40 dead + 60 live).
    # R = wL/2 = 100*12/2 = 600 lb
    # Mmax = wL^2/8 = 100*12^2/8 = 1800 ft-lb, at midspan (x=6 ft)
    span = 12.0
    loads = [UniformLoad(w=40, load_type="dead"), UniformLoad(w=60, load_type="live")]
    results = analyze(span, loads)

    assert results.r1 == pytest.approx(600.0)
    assert results.r2 == pytest.approx(600.0)
    # Max shear magnitude is the design quantity (fv = 1.5|V|/A). On a
    # symmetric simple span both supports carry +/-600 lb; which sign the
    # solver reports for "the" max is an arbitrary tie, so assert on |V|.
    assert abs(results.v_max) == pytest.approx(600.0)
    assert results.m_max == pytest.approx(1800.0, rel=1e-3)
    assert results.m_max_x == pytest.approx(6.0, abs=0.1)


def test_partial_length_distributed_load_reactions_and_moment():
    # 100 plf over the left 5 ft of a 10 ft simple span. The equivalent
    # 500 lb resultant acts 2.5 ft from the left support:
    # R2 = 500*2.5/10 = 125 lb; R1 = 500-125 = 375 lb.
    # Within the loaded zone V=0 at x=R1/w=3.75 ft, so
    # Mmax = 375*3.75 - 100*3.75^2/2 = 703.125 ft-lb.
    loads = [UniformLoad(w=100, load_type="live", start=0, end=5)]
    results = analyze(10.0, loads)

    assert results.r1 == pytest.approx(375.0)
    assert results.r2 == pytest.approx(125.0)
    assert results.m_max == pytest.approx(703.125, rel=1e-3)
    assert results.m_max_x == pytest.approx(3.75, abs=0.05)


def test_adjacent_distributed_zones_match_full_length_uniform_load():
    split = [
        UniformLoad(w=80, load_type="dead", start=0, end=4),
        UniformLoad(w=80, load_type="dead", start=4, end=10),
    ]
    full = [UniformLoad(w=80, load_type="dead")]

    split_results = analyze(10.0, split)
    full_results = analyze(10.0, full)
    assert split_results.reactions == pytest.approx(full_results.reactions)
    assert abs(split_results.v_max) == pytest.approx(abs(full_results.v_max))
    assert split_results.m_max == pytest.approx(full_results.m_max, rel=1e-6)


def test_2x10_spf_no2_beam_design_governs_on_bending():
    # Same beam as above, sized as a repetitive 2x10 SPF No. 2 member
    # (16" o.c.), 1.5 in bearing at each support. Hand calc:
    #
    # Section: b=1.5, d=9.25 -> A=13.875 in^2, S=21.39 in^3, I=98.93 in^4
    #
    # Bending (D+L governs):
    #   M = 1800 ft-lb = 21,600 in-lb
    #   fb = 21600 / 21.39 = 1009.8 psi
    #   Fb' = 875 * CF(1.1) * Cr(1.15) * CD(1.0) = 1106.9 psi
    #   ratio = 1009.8 / 1106.9 = 0.912
    #
    # Shear (D+L governs):
    #   fv = 1.5*600/13.875 = 64.9 psi
    #   Fv' = 135 * CD(1.0) = 135 psi
    #   ratio = 0.481
    #
    # Live deflection: delta = 0.202 in, limit = 144/360 = 0.4 in, ratio = 0.505
    # Total deflection: delta = 0.337 in, limit = 144/240 = 0.6 in, ratio = 0.562
    #
    # Bearing: fc_perp = 600/(1.5*1.5) = 266.7 psi
    #   Cb = (1.5+0.375)/1.5 = 1.25 -> Fc_perp' = 425*1.25 = 531.25 psi
    #   ratio = 0.502
    #
    # Governing check overall: bending, ratio ~= 0.912, design passes.
    span = 12.0
    loads = [UniformLoad(w=40, load_type="dead"), UniformLoad(w=60, load_type="live")]
    section = Section.from_nominal("2x10")

    result = design_beam(span, loads, section, SPF_NO2, repetitive=True)

    assert result.bending.ratio == pytest.approx(0.912, abs=0.002)
    assert result.bending.governing_combo == "D+L"
    assert result.shear.ratio == pytest.approx(0.481, abs=0.002)
    assert result.deflection_live.ratio == pytest.approx(0.505, abs=0.002)
    assert result.deflection_total.ratio == pytest.approx(0.562, abs=0.002)
    assert result.bearing_left.ratio == pytest.approx(0.502, abs=0.002)
    assert result.bearing_right.ratio == pytest.approx(0.502, abs=0.002)

    assert result.governing is result.bending
    assert result.passed is True

    # Transparent calculation report data: section properties, factors,
    # and per-combination reactions/shear/moment used above.
    summary = result.summary
    assert summary.section.A == pytest.approx(13.875)
    assert summary.section.S == pytest.approx(21.39, abs=0.01)
    assert summary.section.I == pytest.approx(98.93, abs=0.01)
    assert summary.cf == pytest.approx(1.1)
    assert summary.cr == pytest.approx(1.15)
    assert summary.cb_left == pytest.approx(1.25)

    dead_combo = next(c for c in summary.combos if c.name == "D")
    live_combo = next(c for c in summary.combos if c.name == "D+L")
    assert dead_combo.cd == pytest.approx(0.9)
    assert dead_combo.r1 == pytest.approx(240.0)
    assert dead_combo.m_max == pytest.approx(720.0, rel=1e-3)
    assert live_combo.cd == pytest.approx(1.0)
    assert live_combo.r1 == pytest.approx(600.0)
    assert live_combo.m_max == pytest.approx(1800.0, rel=1e-3)


def test_off_center_point_load_reactions():
    # 10 ft span, single 800 lb point load 4 ft from the left support.
    # R1 = P*b/L = 800*6/10 = 480 lb, R2 = P*a/L = 800*4/10 = 320 lb
    span = 10.0
    loads = [PointLoad(p=800, location=4.0, load_type="live")]
    results = analyze(span, loads)

    assert results.r1 == pytest.approx(480.0)
    assert results.r2 == pytest.approx(320.0)
    # Max moment occurs under the point load: M = R1*a = 480*4 = 1920 ft-lb
    assert results.m_max == pytest.approx(1920.0, rel=1e-3)
    assert results.m_max_x == pytest.approx(4.0, abs=0.1)


def test_design_summary_preserves_point_loads_for_diagrams():
    loads = [
        PointLoad(p=800, location=4.0, load_type="live"),
        PointLoad(p=250, location=4.0, load_type="dead"),
    ]
    result = design_beam(10.0, loads, Section.from_nominal("2x10"), SPF_NO2)

    assert result.summary.point_loads == [
        {"p": 800, "location": 4.0, "load_type": "live"},
        {"p": 250, "location": 4.0, "load_type": "dead"},
    ]


def test_undersized_member_fails_bending():
    # Same load as the governing case above but on an undersized 2x6 --
    # should clearly fail the bending check (ratio > 1.0).
    span = 12.0
    loads = [UniformLoad(w=40, load_type="dead"), UniformLoad(w=60, load_type="live")]
    section = Section.from_nominal("2x6")

    result = design_beam(span, loads, section, SPF_NO2, repetitive=True)

    assert result.bending.ratio > 1.0
    assert result.bending.passed is False
    assert result.passed is False


def test_member_type_changes_deflection_limit_not_demand():
    # Same 12 ft / 2x10 beam as the governing benchmark case, sized once
    # as a floor joist (live limit L/360) and once as a rafter with no
    # ceiling finish (live limit L/180, per IRC Table R301.7). The
    # deflection demand is identical either way; only the allowable
    # limit changes, so ratio_A / ratio_B == denominator_A / denominator_B.
    span = 12.0
    loads = [UniformLoad(w=40, load_type="dead"), UniformLoad(w=60, load_type="live")]
    section = Section.from_nominal("2x10")

    floor = design_beam(
        span, loads, section, SPF_NO2, repetitive=True,
        deflection_limit_live=DEFLECTION_LIMITS["floor_joist"]["live"],
        deflection_limit_total=DEFLECTION_LIMITS["floor_joist"]["total"],
    )
    rafter = design_beam(
        span, loads, section, SPF_NO2, repetitive=True,
        deflection_limit_live=DEFLECTION_LIMITS["rafter_no_ceiling"]["live"],
        deflection_limit_total=DEFLECTION_LIMITS["rafter_no_ceiling"]["total"],
    )

    assert floor.deflection_live.demand == pytest.approx(rafter.deflection_live.demand)
    assert floor.deflection_live.ratio / rafter.deflection_live.ratio == pytest.approx(
        360 / 180, rel=1e-3,
    )
    # More lenient rafter limit means a design that's borderline as a
    # floor joist can still be comfortably governed by bending, not
    # deflection, once reclassified.
    assert rafter.deflection_live.ratio < floor.deflection_live.ratio


def test_rafter_with_snow_load_governs_on_dead_plus_snow():
    # 12 ft rafter, 2x8 SPF No. 2, repetitive (16" o.c.), no ceiling
    # finish (live/snow limit L/180, total L/240). Dead = 15 plf,
    # snow = 35 plf, no live load. Hand calc:
    #
    # Section: b=1.5, d=7.25 -> A=10.875 in^2, S=13.14 in^3, I=47.635 in^4
    #
    # D+S combo (governs): w=50 plf, R=300 lb, M=900 ft-lb=10,800 in-lb
    #   fb = 10800/13.14 = 821.9 psi
    #   Fb' = 875 * CF(1.2) * Cr(1.15) * CD(1.15) = 1388.6 psi
    #   ratio = 821.9/1388.6 = 0.592
    # D alone: w=15 plf, R=90 lb, M=270 ft-lb=3240 in-lb
    #   fb = 3240/13.14 = 246.6 psi, Fb' = 875*1.2*1.15*0.9 = 1086.75
    #   ratio = 0.227 -- D+S governs
    #
    # Shear (D+S governs): fv = 1.5*300/10.875 = 41.4 psi
    #   Fv' = 135*1.15 = 155.25, ratio = 0.267
    #
    # Snow deflection (no live load present, so the transient-load
    # check uses snow alone): delta = 0.245 in, limit = 144/180 = 0.8 in
    #   ratio = 0.306
    # Total deflection: delta = 0.350 in, limit = 144/240 = 0.6 in
    #   ratio = 0.583
    #
    # Bearing: R=300 lb, Cb=(1.5+0.375)/1.5=1.25, Fc_perp'=531.25 psi
    #   fc_perp = 300/(1.5*1.5) = 133.3 psi, ratio = 0.251
    #
    # Governing: bending, ratio ~= 0.592, design passes.
    span = 12.0
    loads = [UniformLoad(w=15, load_type="dead"), UniformLoad(w=35, load_type="snow")]
    section = Section.from_nominal("2x8")

    result = design_beam(
        span, loads, section, SPF_NO2, repetitive=True,
        deflection_limit_live=DEFLECTION_LIMITS["rafter_no_ceiling"]["live"],
        deflection_limit_total=DEFLECTION_LIMITS["rafter_no_ceiling"]["total"],
    )

    assert result.bending.ratio == pytest.approx(0.592, abs=0.002)
    assert result.bending.governing_combo == "D+S"
    assert result.shear.ratio == pytest.approx(0.267, abs=0.002)
    assert result.shear.governing_combo == "D+S"
    assert result.deflection_live.ratio == pytest.approx(0.306, abs=0.002)
    assert result.deflection_live.name == "Snow-load deflection"
    assert result.deflection_total.ratio == pytest.approx(0.583, abs=0.002)
    assert result.bearing_left.ratio == pytest.approx(0.251, abs=0.002)
    assert result.bearing_left.governing_combo == "D+S"

    assert result.governing is result.bending
    assert result.passed is True

    # Sanity check on the duration factor itself: D+S combo should use
    # CD = 1.15 (NDS Table 2.3.2, snow), not 1.0 (live) or 0.9 (dead).
    snow_combo = next(c for c in result.summary.combos if c.name == "D+S")
    assert snow_combo.cd == pytest.approx(1.15)


def test_clear_span_all_three_modes_agree():
    # Bearings of different widths (3.5" left, 5.5" right) chosen so the
    # three input modes describe the SAME physical beam. Hand calc:
    #   out-to-out  = clear + (3.5+5.5)/12          = clear + 0.75 ft
    #   center-to-center = clear + (3.5+5.5)/2/12   = clear + 0.375 ft
    #   inside (clear span) = clear, unchanged
    # so all three should resolve to the same 19.25 ft clear span.
    expected_clear = 19.25
    assert clear_span(20.00, "out_to_out", 3.5, 5.5) == pytest.approx(expected_clear)
    assert clear_span(19.625, "center_to_center", 3.5, 5.5) == pytest.approx(expected_clear)
    assert clear_span(19.25, "inside", 3.5, 5.5) == pytest.approx(expected_clear)


def test_clear_span_rejects_bearings_larger_than_given_span():
    # 1 ft out-to-out span with 6"+8"=14" of bearing can't have a
    # positive clear span -- should fail loudly, not silently compute
    # a nonsense negative span.
    with pytest.raises(ValueError):
        clear_span(1.0, "out_to_out", 6.0, 8.0)


def test_design_beam_span_mode_matches_equivalent_clear_span():
    # Same governing benchmark beam as above (12 ft clear span, 2x10,
    # 40+60 plf, repetitive, 1.5" bearing both sides), but given as an
    # out-to-out span instead: 12 + (1.5+1.5)/12 = 12.25 ft out-to-out.
    # Result should be identical to passing the 12 ft clear span
    # directly, and the summary should report both the given and
    # resolved spans.
    loads = [UniformLoad(w=40, load_type="dead"), UniformLoad(w=60, load_type="live")]
    section = Section.from_nominal("2x10")

    baseline = design_beam(12.0, loads, section, SPF_NO2, repetitive=True)
    via_out_to_out = design_beam(
        12.25, loads, section, SPF_NO2, repetitive=True, span_mode="out_to_out",
    )

    assert via_out_to_out.bending.ratio == pytest.approx(baseline.bending.ratio)
    assert via_out_to_out.shear.ratio == pytest.approx(baseline.shear.ratio)
    assert via_out_to_out.deflection_total.ratio == pytest.approx(baseline.deflection_total.ratio)
    assert via_out_to_out.summary.span == pytest.approx(12.0)
    assert via_out_to_out.summary.given_span == pytest.approx(12.25)
    assert via_out_to_out.summary.span_mode == "out_to_out"
    assert baseline.summary.given_span == pytest.approx(12.0)
    assert baseline.summary.span_mode == "inside"


def test_required_bearing_length_both_cb_branches_and_floor():
    # Case 1: R=600 lb on a 2x10 (b=1.5") -- same reaction as the
    # governing benchmark. lb_at_Cb=1 = 600/(1.5*425) = 0.941 in < 6,
    # so required = 0.941 - 0.375 = 0.566 in, but that's below the
    # 1.5" code-minimum floor, so the floor governs.
    assert required_bearing_length(600, 1.5, 425) == pytest.approx(1.5)

    # Case 2: R=3000 lb -- lb_at_Cb=1 = 3000/(1.5*425) = 4.706 in < 6,
    # required = 4.706 - 0.375 = 4.331 in (above the floor, not clamped).
    assert required_bearing_length(3000, 1.5, 425) == pytest.approx(4.331, abs=0.002)

    # Case 3: R=6000 lb -- lb_at_Cb=1 = 6000/(1.5*425) = 9.412 in >= 6,
    # so Cb=1.0 applies directly with no -0.375 adjustment.
    assert required_bearing_length(6000, 1.5, 425) == pytest.approx(9.412, abs=0.002)


def test_bearing_check_reports_required_length_only():
    # required_length should be populated on bearing checks and left
    # None on every other check (bending, shear, deflection).
    loads = [UniformLoad(w=40, load_type="dead"), UniformLoad(w=60, load_type="live")]
    section = Section.from_nominal("2x10")
    result = design_beam(12.0, loads, section, SPF_NO2, repetitive=True)

    # Same R=600 lb reaction as the required-bearing-length benchmark
    # above -- should hit the same 1.5" code-minimum floor.
    assert result.bearing_left.required_length == pytest.approx(1.5)
    assert result.bearing_right.required_length == pytest.approx(1.5)
    assert result.bending.required_length is None
    assert result.shear.required_length is None
    assert result.deflection_live.required_length is None


def test_bearing_left_and_right_are_independent():
    # 10 ft span, single 6000 lb point load at 3 ft from the left
    # support (off-center, so R1 != R2):
    #   R1 = P*b/L = 6000*7/10 = 4200 lb, R2 = P*a/L = 6000*3/10 = 1800 lb
    # 2x8 section (b=1.5"). Left bearing specified at 1.5", right at 3.5"
    # -- deliberately different, to prove each side is computed
    # independently rather than sharing one value.
    #
    # Left (actual 1.5" bearing):
    #   fc_perp = 4200/(1.5*1.5) = 1866.7 psi
    #   Cb = (1.5+0.375)/1.5 = 1.25 -> Fc_perp' = 425*1.25 = 531.25 psi
    #   ratio = 1866.7/531.25 = 3.514 (badly undersized -- fails)
    #   required = 4200/(1.5*425) = 6.588 in (>=6, Cb=1 branch, no
    #     -0.375 adjustment since that's self-consistent at >=6)
    #
    # Right (actual 3.5" bearing):
    #   fc_perp = 1800/(1.5*3.5) = 342.9 psi
    #   Cb = (3.5+0.375)/3.5 = 1.107 -> Fc_perp' = 425*1.107 = 470.5 psi
    #   ratio = 342.9/470.5 = 0.729 (passes)
    #   required = 1800/(1.5*425) - 0.375 = 2.824 - 0.375 = 2.449 in
    span = 10.0
    loads = [PointLoad(p=6000, location=3.0, load_type="live")]
    section = Section.from_nominal("2x8")

    result = design_beam(
        span, loads, section, SPF_NO2,
        bearing_length_left=1.5, bearing_length_right=3.5,
    )

    assert result.bearing_left.ratio == pytest.approx(3.514, abs=0.005)
    assert result.bearing_left.passed is False
    assert result.bearing_left.required_length == pytest.approx(6.588, abs=0.005)

    assert result.bearing_right.ratio == pytest.approx(0.729, abs=0.005)
    assert result.bearing_right.passed is True
    assert result.bearing_right.required_length == pytest.approx(2.449, abs=0.005)


def test_shear_discontinuity_at_support_is_not_missed_by_grid_sampling():
    # Regression test for a real bug found during development: shear
    # jumps discontinuously AT a support (by the reaction value), so a
    # naive one-sided evaluation on a sampled grid can land just next
    # to a support and under-report the true worst-case shear there.
    # 10 ft back span + 3 ft right overhang, uniform w=50 plf over the
    # full 13 ft. Hand calc: R1 = w*(L+a)^2/(2L) is for the OTHER end;
    # here at support 1: total load = 50*13 = 650 lb, centroid = 6.5 ft,
    # R2 = 650*6.5/10 = 422.5 lb, R1 = 650-422.5 = 227.5 lb.
    # Shear just left of support 2 (x=10, back-span side, before the
    # support's own reaction is picked up) = R1 - w*10 = 227.5-500 = -272.5 lb
    # -- this is the TRUE governing shear, exactly at the support, not
    # some slightly-smaller value at a nearby grid point.
    total_length = 13.0
    a1, a2 = 0.0, 10.0
    loads = [UniformLoad(w=50, load_type="dead")]
    results = analyze(total_length, loads, a1=a1, a2=a2)
    assert results.v_max == pytest.approx(-272.5, abs=1e-6)
    assert results.v_max_x == pytest.approx(10.0, abs=1e-6)


def test_overhang_numerical_deflection_matches_closed_form_simple_span():
    # Sanity check that the general (a1, a2, total_length) machinery
    # reduces EXACTLY to the known 5wL^4/384EI closed form when there's
    # no overhang (a1=0, a2=total_length) -- confirms the numerical
    # double-integration deflection method isn't silently degrading
    # accuracy for the plain simply-supported case it replaced.
    span = 12.0
    w = 100.0
    loads = [UniformLoad(w=w, load_type="dead")]
    section = Section.from_nominal("2x10")
    E, I = SPF_NO2.E, section.I
    closed_form = 5 * (w / 12) * (span * 12) ** 4 / (384 * E * I)

    numeric = back_span_deflection(span, loads, E, I)
    assert numeric == pytest.approx(closed_form, rel=1e-4)


def test_right_overhang_uniform_load_full_design():
    # 10 ft back span + 3 ft right overhang (e.g. a cantilevered deck
    # joist), 2x10 SPF No. 2, repetitive, D=20 plf + L=30 plf over the
    # FULL 13 ft length. Reactions verified by hand (statics, moments
    # about support 1):
    #   total load (D+L) = 50*13 = 650 lb, centroid = 6.5 ft
    #   R2 = 650*6.5/10 = 422.5 lb, R1 = 650-422.5 = 227.5 lb
    # Max positive moment where V=0 in the back span: x* = R1/w = 4.55 ft
    #   M(4.55) = 227.5*4.55 - 50*4.55^2/2 = 517.5625 ft-lb = 6210.75 in-lb
    # Moment at the support (x=10, negative/hogging):
    #   M(10) = 227.5*10 - 50*10^2/2 = -225 ft-lb (smaller magnitude than
    #   the back-span positive moment here, so bending governs on the
    #   positive back-span moment, not the support's negative moment)
    # Governing shear: -272.5 lb at x=10 (see discontinuity test above)
    #
    # Section (2x10): A=13.875 in^2, S=21.391 in^3
    #   fb = 6210.75/21.391 = 290.35 psi
    #   Fb' = 875*CF(1.1)*Cr(1.15)*CD(1.0) = 1106.875 psi
    #   ratio = 290.35/1106.875 = 0.2623
    #   fv = 1.5*272.5/13.875 = 29.459 psi, Fv' = 135, ratio = 0.2182
    #
    # Bearing: R1=227.5 -> fc_perp=227.5/(1.5*1.5)=101.11, Cb=1.25,
    #   Fc_perp'=531.25, ratio=0.1903, required=1.5 (floor, R1 too small
    #   to need more than the code minimum)
    #   R2=422.5 -> fc_perp=187.78, ratio=0.3535, required=1.5 (floor)
    span = 10.0
    section = Section.from_nominal("2x10")
    loads = [UniformLoad(w=20, load_type="dead"), UniformLoad(w=30, load_type="live")]

    result = design_beam(span, loads, section, SPF_NO2, repetitive=True, right_overhang=3.0)

    assert result.summary.left_overhang == pytest.approx(0.0)
    assert result.summary.right_overhang == pytest.approx(3.0)
    assert result.summary.total_length == pytest.approx(13.0)

    combo = next(c for c in result.summary.combos if c.name == "D+L")
    assert combo.r1 == pytest.approx(227.5)
    assert combo.r2 == pytest.approx(422.5)
    assert combo.m_max == pytest.approx(517.5625, rel=1e-3)
    assert combo.m_max_x == pytest.approx(4.55, abs=0.01)
    assert combo.v_max == pytest.approx(-272.5, abs=1e-6)

    assert result.bending.ratio == pytest.approx(0.2623, abs=0.001)
    assert result.shear.ratio == pytest.approx(0.2182, abs=0.001)
    assert result.bearing_left.ratio == pytest.approx(0.1903, abs=0.001)
    assert result.bearing_left.required_length == pytest.approx(1.5)
    assert result.bearing_right.ratio == pytest.approx(0.3535, abs=0.001)
    assert result.bearing_right.required_length == pytest.approx(1.5)

    # Cantilever-tip deflection checks only appear on the overhanging side.
    assert result.deflection_right_cantilever_live is not None
    assert result.deflection_right_cantilever_total is not None
    assert result.deflection_left_cantilever_live is None
    assert result.deflection_left_cantilever_total is None
    assert "right cantilever tip" in result.deflection_right_cantilever_live.name

    assert result.passed is True
    assert result.governing is result.bearing_right


def test_left_and_right_overhang_are_mirror_symmetric():
    # The same beam described as a right overhang (10 ft back span + 3 ft
    # right overhang) vs a left overhang (3 ft left overhang + 10 ft back
    # span) under the same total loading should be physical mirror
    # images: identical bending/shear ratios, reactions swapped R1<->R2,
    # and identical tip deflection magnitude on the (now opposite) side.
    section = Section.from_nominal("2x10")
    loads = [UniformLoad(w=20, load_type="dead"), UniformLoad(w=30, load_type="live")]

    right = design_beam(10.0, loads, section, SPF_NO2, repetitive=True, right_overhang=3.0)
    left = design_beam(10.0, loads, section, SPF_NO2, repetitive=True, left_overhang=3.0)

    # Tolerance is 1e-7 (not machine epsilon): the continuous-beam FEM
    # solver carries ~1e-9 relative floating-point noise, so a mirrored
    # pair agrees to ~1e-9 rather than exactly. 1e-7 still verifies real
    # symmetry while tolerating that numerical noise.
    assert left.bending.ratio == pytest.approx(right.bending.ratio, rel=1e-7)
    assert left.shear.ratio == pytest.approx(right.shear.ratio, rel=1e-7)

    right_combo = next(c for c in right.summary.combos if c.name == "D+L")
    left_combo = next(c for c in left.summary.combos if c.name == "D+L")
    assert left_combo.r1 == pytest.approx(right_combo.r2, rel=1e-7)
    assert left_combo.r2 == pytest.approx(right_combo.r1, rel=1e-7)

    assert left.deflection_left_cantilever_live.demand == pytest.approx(
        right.deflection_right_cantilever_live.demand, rel=1e-6,
    )


def test_cantilever_deflection_limits_can_be_more_strict_than_back_span():
    # Settings-tab regression: cantilever tip limits should be
    # independently configurable from the back-span limits. Tightening
    # only the cantilever live criterion must change only the
    # cantilever live ratio, not the back-span live ratio.
    section = Section.from_nominal("2x10")
    loads = [UniformLoad(w=20, load_type="dead"), UniformLoad(w=30, load_type="live")]

    # The default cantilever limit here is L/360 (same as the back span
    # for this member type). A deflection limit is a denominator, so a
    # LARGER number is stricter: L/720 halves the allowable deflection
    # and therefore doubles the utilization ratio. (The prior version of
    # this test used L/180 expecting it to be stricter, but 180 < 360 is
    # looser -- the direction was inverted.)
    baseline = design_beam(10.0, loads, section, SPF_NO2, repetitive=True, right_overhang=3.0)
    stricter = design_beam(
        10.0, loads, section, SPF_NO2,
        repetitive=True,
        right_overhang=3.0,
        deflection_limit_live=360,
        deflection_limit_total=240,
        cantilever_deflection_limit_live=720,
        cantilever_deflection_limit_total=240,
    )

    # Tightening only the cantilever live criterion must leave the
    # back-span live ratio unchanged and double the cantilever live ratio.
    assert stricter.deflection_live.ratio == pytest.approx(baseline.deflection_live.ratio, rel=1e-7)
    assert stricter.deflection_right_cantilever_live.ratio == pytest.approx(
        baseline.deflection_right_cantilever_live.ratio * 2, rel=1e-6,
    )
    assert stricter.summary.cantilever_deflection_limit_live == pytest.approx(720)
    assert stricter.summary.deflection_limit_live == pytest.approx(360)


def test_overhang_point_load_causing_uplift_is_flagged_not_silently_passed():
    # A large point load right at an overhang's tip can pull the OTHER
    # support into net uplift -- a hold-down/connector problem this
    # tool doesn't check, not a bearing problem. It must fail loudly,
    # not report a misleadingly reassuring near-zero or negative ratio.
    # 10 ft back span + 3 ft right overhang, dead load only on the back
    # span plus a large live point load at the very tip (x=13 ft):
    #   Taking moments about support 1 (x=0): with only the point load
    #   (ignore small dead load for the sign check), R2 dominates and
    #   R1 must go negative to balance a load that far out past support 2.
    section = Section.from_nominal("2x10")
    loads = [UniformLoad(w=20, load_type="dead"), PointLoad(p=500, location=13.0, load_type="live")]

    result = design_beam(10.0, loads, section, SPF_NO2, repetitive=True, right_overhang=3.0)

    combo = next(c for c in result.summary.combos if c.name == "D+L")
    assert combo.r1 < 0  # net uplift at the left support

    assert result.bearing_left.passed is False
    assert "UPLIFT" in result.bearing_left.name
    assert result.bearing_left.required_length is None
    assert result.passed is False
    assert result.governing is result.bearing_left


def test_area_loads_convert_to_linear_loads_by_spacing():
    plf = entered_uniform_loads_to_plf({
        "uniform_load_basis": "psf",
        "spacing_in": 16.0,
        "dead_load_plf": 10.0,
        "live_load_plf": 40.0,
        "snow_load_plf": 0.0,
        "roof_live_load_plf": 20.0,
        "wind_load_plf": 15.0,
    })
    assert plf["dead"] == pytest.approx(13.3333333)
    assert plf["live"] == pytest.approx(53.3333333)
    assert plf["roof_live"] == pytest.approx(26.6666667)
    assert plf["wind"] == pytest.approx(20.0)


def test_roof_live_load_uses_d_plus_lr_combo_and_cd_125():
    span = 12.0
    loads = [UniformLoad(w=10, load_type="dead"), UniformLoad(w=20, load_type="roof_live")]
    section = Section.from_nominal("2x8")

    result = design_beam(
        span, loads, section, SPF_NO2, repetitive=True,
        deflection_limit_live=DEFLECTION_LIMITS["rafter_no_ceiling"]["live"],
        deflection_limit_total=DEFLECTION_LIMITS["rafter_no_ceiling"]["total"],
    )

    assert result.bending.governing_combo == "D+Lr"
    combo = next(c for c in result.summary.combos if c.name == "D+Lr")
    assert combo.cd == pytest.approx(1.25)
    assert result.deflection_live.name == "Roof live-load deflection"


def test_two_span_continuous_uniform_load_matches_classic_coefficients():
    # Two equal 10 ft spans, simple end supports at x=0 and x=20 ft, one
    # interior support at x=10 ft, uniform load 100 plf over the FULL
    # member. Classic closed-form results for equal spans loaded on both
    # spans:
    #   R_end = 3wL/8 = 375 lb
    #   R_mid = 5wL/4 = 1250 lb
    #   M_negative at interior support = -wL^2/8 = -1250 ft-lb
    #   M_positive max in each span = 9wL^2/128 = 703.125 ft-lb
    loads = [UniformLoad(w=100, load_type="dead")]
    result = analyze(20.0, loads, support_positions=[0.0, 10.0, 20.0])

    assert result.reactions[0] == pytest.approx(375.0, abs=1e-3)
    assert result.reactions[1] == pytest.approx(1250.0, abs=1e-3)
    assert result.reactions[2] == pytest.approx(375.0, abs=1e-3)
    assert result.m_max == pytest.approx(-1250.0, abs=2.0)
    assert result.m_max_x == pytest.approx(10.0, abs=0.05)
    assert result.v_max == pytest.approx(-625.0, abs=2.0)
    assert result.v_max_x == pytest.approx(10.0, abs=0.05)


def test_two_span_continuous_support_deflections_are_zero_and_spans_are_symmetric():
    loads = [UniformLoad(w=100, load_type="dead")]
    section = Section.from_nominal("2x10")
    support_positions = [0.0, 10.0, 20.0]

    assert deflection_at(20.0, loads, SPF_NO2.E, section.I, 0.0, support_positions) == pytest.approx(0.0, abs=1e-6)
    assert deflection_at(20.0, loads, SPF_NO2.E, section.I, 10.0, support_positions) == pytest.approx(0.0, abs=1e-6)
    assert deflection_at(20.0, loads, SPF_NO2.E, section.I, 20.0, support_positions) == pytest.approx(0.0, abs=1e-6)

    left_span = max_deflection_between(20.0, loads, SPF_NO2.E, section.I, 0.0, 10.0, support_positions)
    right_span = max_deflection_between(20.0, loads, SPF_NO2.E, section.I, 10.0, 20.0, support_positions)
    assert left_span > 0
    assert right_span == pytest.approx(left_span, rel=1e-4)


def test_design_beam_two_span_mode_surfaces_interior_support_checks():
    section = Section.from_nominal("2x10")
    loads = [UniformLoad(w=40, load_type="dead"), UniformLoad(w=60, load_type="live")]

    result = design_beam(
        10.0, loads, section, SPF_NO2, repetitive=True,
        span_mode="inside",
        continuous_spans=[10.0, 10.0],
        bearing_lengths=[1.5, 3.5, 1.5],
    )

    assert len(result.summary.support_positions) == 3
    assert result.summary.support_labels == ["B1", "B2", "B3"]
    assert any("support B2" in check.name for check in result.extra_checks)
    assert any("B1-B2" in check.name for check in result.checks)
    assert any("B2-B3" in check.name for check in result.checks)


def test_design_beam_three_span_mode_surfaces_both_interior_support_checks():
    section = Section.from_nominal("2x10")
    loads = [UniformLoad(w=30, load_type="dead"), UniformLoad(w=50, load_type="live")]

    result = design_beam(
        10.0, loads, section, SPF_NO2, repetitive=True,
        span_mode="inside",
        continuous_spans=[10.0, 10.0, 10.0],
        bearing_lengths=[1.5, 3.5, 3.5, 1.5],
    )

    assert len(result.summary.support_positions) == 4
    assert result.summary.support_labels == ["B1", "B2", "B3", "B4"]
    assert any("support B2" in check.name for check in result.extra_checks)
    assert any("support B3" in check.name for check in result.extra_checks)
    assert any("B1-B2" in check.name for check in result.checks)
    assert any("B2-B3" in check.name for check in result.checks)
    assert any("B3-B4" in check.name for check in result.checks)


def test_design_beam_two_span_mode_allows_end_overhangs_and_surfaces_tip_checks():
    section = Section.from_nominal("2x10")
    loads = [UniformLoad(w=35, load_type="dead"), UniformLoad(w=45, load_type="live")]

    result = design_beam(
        10.0, loads, section, SPF_NO2, repetitive=True,
        span_mode="inside",
        left_overhang=2.0,
        right_overhang=3.0,
        continuous_spans=[10.0, 10.0],
        bearing_lengths=[1.5, 3.5, 1.5],
    )

    assert result.summary.support_positions == pytest.approx([2.0, 12.0, 22.0])
    assert result.summary.total_length == pytest.approx(25.0)
    assert result.deflection_left_cantilever_live is not None
    assert result.deflection_left_cantilever_total is not None
    assert result.deflection_right_cantilever_live is not None
    assert result.deflection_right_cantilever_total is not None
    assert "left cantilever tip" in result.deflection_left_cantilever_live.name
    assert "right cantilever tip" in result.deflection_right_cantilever_live.name
    assert any("support B2" in check.name for check in result.extra_checks)


def test_multispan_overhang_supports_stay_at_zero_deflection():
    loads = [UniformLoad(w=80, load_type="dead")]
    section = Section.from_nominal("2x10")
    support_positions = [2.0, 12.0, 22.0]

    assert deflection_at(25.0, loads, SPF_NO2.E, section.I, 2.0, support_positions) == pytest.approx(0.0, abs=1e-6)
    assert deflection_at(25.0, loads, SPF_NO2.E, section.I, 12.0, support_positions) == pytest.approx(0.0, abs=1e-6)
    assert deflection_at(25.0, loads, SPF_NO2.E, section.I, 22.0, support_positions) == pytest.approx(0.0, abs=1e-6)


def test_design_beam_ten_span_mode_handles_long_support_chains():
    section = Section.from_nominal("2x10")
    loads = [UniformLoad(w=20, load_type="dead"), UniformLoad(w=35, load_type="live")]
    spans = [8.0] * 10
    bearings = [1.5] + [3.5] * 9 + [1.5]

    result = design_beam(
        8.0, loads, section, SPF_NO2, repetitive=True,
        span_mode="inside",
        continuous_spans=spans,
        bearing_lengths=bearings,
    )

    assert len(result.summary.span_segments) == 10
    assert len(result.summary.support_positions) == 11
    assert result.summary.support_labels[0] == "B1"
    assert result.summary.support_labels[-1] == "B11"
    assert any("B10-B11" in check.name for check in result.checks)


def test_design_result_exposes_analysis_diagram_series():
    section = Section.from_nominal("2x10")
    loads = [UniformLoad(w=40, load_type="dead"), UniformLoad(w=60, load_type="live")]

    result = design_beam(12.0, loads, section, SPF_NO2, repetitive=True)

    assert result.summary.shear_diagram is not None
    assert result.summary.moment_diagram is not None
    assert result.summary.deflection_live_diagram is not None
    assert result.summary.deflection_total_diagram is not None
    assert len(result.summary.shear_diagram.points) > 10
    assert result.summary.shear_diagram.governing_combo == result.shear.governing_combo
    assert result.summary.moment_diagram.governing_combo == result.bending.governing_combo


def test_douglas_fir_larch_no2_material_drives_checks():
    # Same geometry as the SPF governing benchmark (12 ft, 2x10, 40D+60L
    # plf, repetitive, 1.5" bearing) but Douglas Fir-Larch No. 2, so the
    # only thing that changes is the material's design values. Verifies
    # the engine applies the SELECTED material (not a hardcoded SPF).
    #
    # DF-L No.2 (NDS-S Table 4A): Fb=900, Fv=180, Fc_perp=625, E=1.6e6.
    # Section 2x10: A=13.875, S=21.391, I=98.93. Reactions/moments are
    # material-independent: R=600 lb, Mmax=1800 ft-lb, Vmax=600 lb (D+L).
    #
    # Bending (D+L): fb = 1800*12/21.391 = 1009.8 psi
    #   F'b = 900 * CF(1.1) * Cr(1.15) * CD(1.0) = 1138.5 psi
    #   ratio = 1009.8/1138.5 = 0.887
    # Shear (D+L): fv = 1.5*600/13.875 = 64.86 psi
    #   F'v = 180 * 1.0 = 180 -> ratio = 0.360
    # Bearing: fc_perp = 600/(1.5*1.5) = 266.67 psi
    #   Cb=1.25 -> F'c_perp = 625*1.25 = 781.25 -> ratio = 0.341
    # Live deflection: delta = 5*(60/12)*144^4/(384*1.6e6*98.93) = 0.1768 in
    #   limit 144/360 = 0.4 -> ratio = 0.442  (stiffer E than SPF, so less
    #   deflection than the SPF 0.505 baseline)
    span = 12.0
    loads = [UniformLoad(w=40, load_type="dead"), UniformLoad(w=60, load_type="live")]
    section = Section.from_nominal("2x10")
    dfl = get_material("dfl_no2")

    result = design_beam(span, loads, section, dfl, repetitive=True)

    assert result.summary.material_name == "Douglas Fir-Larch No. 2"
    assert result.summary.fb_base == 900
    assert result.summary.fv_base == 180
    assert result.summary.fc_perp_base == 625
    assert result.bending.ratio == pytest.approx(0.887, abs=0.002)
    assert result.shear.ratio == pytest.approx(0.360, abs=0.002)
    assert result.bearing_left.ratio == pytest.approx(0.341, abs=0.002)
    assert result.deflection_live.ratio == pytest.approx(0.442, abs=0.003)

    # And the SPF baseline (same geometry) should differ, proving the
    # material actually changed the result rather than being ignored.
    spf = design_beam(span, loads, section, SPF_NO2, repetitive=True)
    assert spf.bending.ratio == pytest.approx(0.912, abs=0.002)  # SPF Fb=875
    assert spf.deflection_live.ratio == pytest.approx(0.505, abs=0.002)  # SPF E=1.4e6
    assert result.bending.ratio < spf.bending.ratio  # DF-L stronger in bending
    assert result.deflection_live.ratio < spf.deflection_live.ratio  # DF-L stiffer
