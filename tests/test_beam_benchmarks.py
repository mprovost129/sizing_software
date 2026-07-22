"""Hand-calculated benchmark problems for the beam engine.

Each test's expected values are derived independently by hand (see the
comments) and checked against the engine's output, per the project's
validation requirement: every release verified against known solutions.
"""
import pytest

from beams.load_inputs import entered_uniform_loads_to_plf
from engine import (
    SPF_NO2,
    PointLoad,
    Section,
    UniformLoad,
    design_beam,
    design_beam_column,
    design_column,
    get_material,
)
from engine.beam import (
    analyze,
    back_span_deflection,
    deflection_at,
    max_deflection_between,
)
from engine.factors import (
    DEFLECTION_LIMITS,
    beam_stability_factor,
    glulam_volume_factor,
    required_bearing_length,
    wet_service_factors,
)
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


def test_three_ply_builtup_member_scales_capacity_and_drops_cr():
    # Same 2x10 SPF No. 2 beam and loads as
    # test_2x10_spf_no2_beam_design_governs_on_bending, but built up from
    # 3 plies fastened side by side (a typical multi-ply header).
    #
    # A built-up member's section properties scale linearly with the ply
    # count (total width b = 3 * 1.5 = 4.5 in, depth unchanged):
    #   A = 4.5 * 9.25          = 41.625 in^2  (3x single ply)
    #   S = 4.5 * 9.25^2 / 6    = 64.17  in^3  (3x single ply)
    #   I = 4.5 * 9.25^3 / 12   = 296.79 in^4  (3x single ply)
    #
    # The Fb size factor CF is depth-based, so it is unchanged (1.1). The
    # repetitive-member factor Cr must NOT apply to a built-up member --
    # it is a single member, not 3+ members spaced o.c. -- so even with
    # repetitive=True, Cr drops from 1.15 to 1.0.
    #
    # Every demand/capacity ratio therefore becomes the single-ply,
    # Cr-removed value divided by 3:
    #   Bending: 0.912 * 1.15 / 3 = 0.350   (Cr removed, section x3)
    #   Shear:            0.481 / 3 = 0.160
    #   Live deflection:  0.505 / 3 = 0.168
    #   Total deflection: 0.562 / 3 = 0.187
    #   Bearing:          0.502 / 3 = 0.167
    span = 12.0
    loads = [UniformLoad(w=40, load_type="dead"), UniformLoad(w=60, load_type="live")]
    single = Section.from_nominal("2x10")
    builtup = Section.from_nominal("2x10", plies=3)

    # Section properties scale exactly with ply count.
    assert builtup.plies == 3
    assert builtup.b == pytest.approx(4.5)
    assert builtup.d == pytest.approx(single.d)
    assert builtup.A == pytest.approx(3 * single.A)
    assert builtup.S == pytest.approx(3 * single.S)
    assert builtup.I == pytest.approx(3 * single.I)
    assert builtup.label == "3-ply 2x10"

    result = design_beam(span, loads, builtup, SPF_NO2, repetitive=True)

    # Cr is suppressed for the built-up member even though repetitive=True.
    assert result.summary.cr == pytest.approx(1.0)
    assert result.summary.cf == pytest.approx(1.1)
    assert result.summary.section.plies == 3

    assert result.bending.ratio == pytest.approx(0.350, abs=0.002)
    assert result.shear.ratio == pytest.approx(0.160, abs=0.002)
    assert result.deflection_live.ratio == pytest.approx(0.168, abs=0.002)
    assert result.deflection_total.ratio == pytest.approx(0.187, abs=0.002)
    assert result.bearing_left.ratio == pytest.approx(0.167, abs=0.002)
    assert result.passed is True


def test_beam_stability_factor_matches_nds_hand_calc():
    # NDS 3.3.3 worked by hand for a 2x12 (d=11.25, b=1.5) with a 12 ft
    # (144 in) unbraced compression edge, SPF No. 2 (Emin = 510,000 psi),
    # governing D+L combination Fb* = 875 psi (CF=1.0, Cr=1.0, CD=1.0):
    #
    #   lu/d = 144/11.25 = 12.8  -> 7 <= lu/d <= 14.3
    #   le   = 1.63*144 + 3*11.25 = 268.47 in
    #   RB   = sqrt(268.47*11.25 / 1.5^2) = 36.64  (<= 50, OK)
    #   FbE  = 1.20*510000 / 36.64^2 = 455.9 psi
    #   FbE/Fb* = 455.9 / 875 = 0.5210
    #   CL   = (1+0.5210)/1.9 - sqrt[((1.5210)/1.9)^2 - 0.5210/0.95]
    #        = 0.8005 - 0.3040 = 0.4965
    stab = beam_stability_factor(144.0, 11.25, 1.5, 510_000, 875.0)
    assert stab.braced is False
    assert stab.over_slender is False
    assert stab.rb == pytest.approx(36.64, abs=0.02)
    assert stab.fbE == pytest.approx(455.9, abs=0.5)
    assert stab.cl == pytest.approx(0.4965, abs=0.002)

    # A continuously braced compression edge (lu None/0), or a member no
    # deeper than it is wide, gets CL = 1.0 with no reduction.
    assert beam_stability_factor(None, 11.25, 1.5, 510_000, 875.0).cl == 1.0
    assert beam_stability_factor(0.0, 11.25, 1.5, 510_000, 875.0).cl == 1.0
    assert beam_stability_factor(144.0, 3.5, 6.0, 510_000, 875.0).cl == 1.0  # d <= b

    # RB above 50 is flagged (invalid per NDS 3.3.3.7), not silently used.
    assert beam_stability_factor(600.0, 11.25, 1.5, 510_000, 875.0).over_slender is True


def test_unbraced_beam_applies_cl_to_bending_and_can_fail():
    # Same 2x12 SPF No. 2, 12 ft simple span, 40 plf dead + 60 plf live.
    # With the compression edge continuously braced the bending check
    # passes; leaving 12 ft of the compression edge unbraced cuts the
    # bending capacity by CL = 0.4965 and pushes the check past 1.0.
    span = 12.0
    loads = [UniformLoad(w=40, load_type="dead"), UniformLoad(w=60, load_type="live")]
    section = Section.from_nominal("2x12")

    braced = design_beam(span, loads, section, SPF_NO2)
    assert braced.summary.cl == 1.0
    assert braced.bending.ratio == pytest.approx(0.780, abs=0.003)
    assert braced.bending.passed is True

    unbraced = design_beam(span, loads, section, SPF_NO2, unbraced_length=144.0)
    assert unbraced.summary.cl == pytest.approx(0.4965, abs=0.002)
    assert unbraced.summary.rb == pytest.approx(36.64, abs=0.02)
    # Braced ratio divided by CL: 0.780 / 0.4965 = 1.571
    assert unbraced.bending.ratio == pytest.approx(1.571, abs=0.005)
    assert unbraced.bending.passed is False
    assert unbraced.bending.governing_combo == "D+L"


def test_wet_service_factors_table_4a():
    # NDS-S Table 4A wet-service CM for sawn dimension lumber. Fv, Fc_perp,
    # E, Emin are fixed; Fb is 0.85 unless (Fb)(CF) <= 1150 psi (then 1.0).
    #   SPF No.2 2x10: Fb*CF = 875*1.1 = 962.5 <= 1150 -> CM,Fb = 1.0
    #   SPF No.2 2x4:  Fb*CF = 875*1.5 = 1312.5 > 1150 -> CM,Fb = 0.85
    cm_2x10 = wet_service_factors(875, 1.1)
    assert cm_2x10.fb == 1.0
    assert cm_2x10.fv == 0.97
    assert cm_2x10.fc_perp == 0.67
    assert cm_2x10.e == 0.90
    assert cm_2x10.emin == 0.90
    assert wet_service_factors(875, 1.5).fb == 0.85


def test_wet_service_reduces_shear_bearing_and_deflection():
    # Same repetitive 2x10 SPF No. 2 beam as the dry benchmark, but in wet
    # service. For a 2x10 (Fb)(CF) <= 1150 so CM,Fb = 1.0 and bending is
    # unchanged; the other checks scale by 1/CM:
    #   Shear:            0.481 / 0.97 = 0.496
    #   Bearing:          0.502 / 0.67 = 0.749
    #   Live deflection:  0.505 / 0.90 = 0.561   (E reduced 10%)
    #   Total deflection: 0.562 / 0.90 = 0.624
    span = 12.0
    loads = [UniformLoad(w=40, load_type="dead"), UniformLoad(w=60, load_type="live")]
    section = Section.from_nominal("2x10")

    wet = design_beam(span, loads, section, SPF_NO2, repetitive=True, wet_service=True)

    assert wet.summary.wet_service is True
    assert wet.summary.cm_fb == 1.0
    assert wet.summary.cm_fv == 0.97
    assert wet.summary.cm_fcperp == 0.67
    assert wet.summary.cm_e == 0.90
    # Reported base values stay unadjusted; CM is shown as a separate factor.
    assert wet.summary.fb_base == 875
    assert wet.summary.fc_perp_base == 425

    assert wet.bending.ratio == pytest.approx(0.912, abs=0.002)   # CM,Fb = 1.0
    assert wet.shear.ratio == pytest.approx(0.496, abs=0.002)
    assert wet.bearing_left.ratio == pytest.approx(0.749, abs=0.003)
    assert wet.deflection_live.ratio == pytest.approx(0.561, abs=0.003)
    assert wet.deflection_total.ratio == pytest.approx(0.624, abs=0.003)


def test_lvl_uses_cv_depth_factor_and_suppresses_cr_and_cm():
    # 2-ply 2.0E LVL (representative), 14 in deep, 16 ft span, 200 plf dead
    # + 400 plf live. LVL is engineered: the bending value uses the volume
    # depth factor CV = (12/d)^0.136 instead of a tabulated CF, the
    # repetitive factor Cr never applies, and wet service is not modelled
    # (CM stays 1.0).
    #
    #   CV = (12/14)^0.136 = 0.97925
    #   Section: b = 2*1.75 = 3.5, d = 14 -> S = 3.5*14^2/6 = 114.33 in^3
    #   M = 600*16^2/8 = 19,200 ft-lb = 230,400 in-lb
    #   fb = 230400 / 114.33 = 2015.2 psi
    #   Fb* = 2900 * CV(0.97925) * CD(1.0) = 2839.8 psi
    #   bending ratio = 2015.2 / 2839.8 = 0.7096
    material = get_material("lvl_2_0e")
    assert material.is_lvl is True
    section = Section.from_nominal("lvl_14", plies=2)
    assert section.b == pytest.approx(3.5)   # two 1.75" laminations
    assert section.d == pytest.approx(14.0)
    assert section.label == '2-ply 14"'

    loads = [UniformLoad(w=200, load_type="dead"), UniformLoad(w=400, load_type="live")]
    # repetitive=True and wet_service=True are both requested but must be
    # ignored for an engineered LVL member.
    result = design_beam(16.0, loads, section, material, repetitive=True, wet_service=True)

    assert result.summary.material_category == "lvl"
    assert result.summary.cf == pytest.approx(0.97925, abs=0.0002)  # this is CV
    assert result.summary.cr == 1.0            # Cr never applies to LVL
    assert result.summary.wet_service is False  # CM not applied to LVL
    assert result.summary.cm_fb == 1.0

    assert result.bending.governing_combo == "D+L"
    assert result.bending.ratio == pytest.approx(0.7096, abs=0.002)


def test_glulam_volume_factor_matches_nds_5_3_6():
    # NDS 5.3.6 volume factor CV = (21/L)^0.1 (12/d)^0.1 (5.125/b)^0.1 <= 1.0
    # for a 5-1/8 x 18 in glulam over a 20 ft length (x = 10, non-SP):
    #   CV = (21/20 * 12/18 * 5.125/5.125)^0.1 = (0.7)^0.1 = 0.96496
    assert glulam_volume_factor(20.0, 18.0, 5.125, 0.10) == pytest.approx(0.96496, abs=0.0002)
    # CV is capped at 1.0 (a short, shallow, narrow member does not get a
    # bonus above the reference).
    assert glulam_volume_factor(5.0, 6.0, 3.125, 0.10) == 1.0


def test_glulam_uses_volume_factor_and_lesser_of_cv_cl():
    # 24F-1.8E glulam (balanced), 5-1/8 x 18 in, 20 ft simple span,
    # 300 plf dead + 500 plf live. Glulam uses the volume factor CV in
    # place of CF, no Cr, and the LESSER of CV and CL (never both).
    #
    #   CV = 0.96496 (above); S = 5.125*18^2/6 = 276.75 in^3
    #   M = 800*20^2/8 = 40,000 ft-lb = 480,000 in-lb
    #   fb = 480000 / 276.75 = 1734.4 psi
    #   Braced (CL = 1.0): F'b = 2400 * min(0.96496, 1.0) = 2315.9 psi
    #   ratio = 1734.4 / 2315.9 = 0.749
    material = get_material("gl_24f_1_8e")
    assert material.is_glulam is True
    section = Section.from_nominal("gl_5.125x18")
    assert section.b == pytest.approx(5.125)
    assert section.d == pytest.approx(18.0)
    assert section.plies == 1
    assert section.label == '5-1/8x18"'

    loads = [UniformLoad(w=300, load_type="dead"), UniformLoad(w=500, load_type="live")]

    braced = design_beam(20.0, loads, section, material, repetitive=True, wet_service=True)
    assert braced.summary.material_category == "glulam"
    assert braced.summary.cr == 1.0             # Cr never applies to glulam
    assert braced.summary.wet_service is False  # CM not applied to glulam
    assert braced.summary.cf == pytest.approx(0.96496, abs=0.0002)  # this is CV
    assert braced.summary.cl == 1.0
    assert braced.bending.ratio == pytest.approx(0.749, abs=0.002)

    # Leaving 20 ft unbraced drops CL to 0.931 < CV, so CL now governs the
    # bending factor (min(CV, CL) = CL), raising the ratio.
    unbraced = design_beam(20.0, loads, section, material, unbraced_length=240.0)
    assert unbraced.summary.cl == pytest.approx(0.9308, abs=0.002)
    assert unbraced.summary.cl < unbraced.summary.cf  # CL is the lesser
    assert unbraced.bending.ratio == pytest.approx(0.776, abs=0.003)


def test_southern_pine_uses_size_specific_fb_and_no_cf():
    # Southern Pine (NDS-S Table 4B) tabulates Fb per nominal size, so the
    # size factor CF = 1.0. For SP No. 2 the reference Fb is 1050 psi at
    # 2x10 and 1200 psi at 2x8 -- different values for different depths,
    # unlike the CF-scaled species.
    #
    # Repetitive 2x10 SP No. 2, 12 ft, 40 plf dead + 60 plf live (D+L):
    #   fb = 21600 / 21.39 = 1009.8 psi
    #   F'b = 1050 * CF(1.0) * Cr(1.15) * CD(1.0) = 1207.5 psi
    #   ratio = 1009.8 / 1207.5 = 0.836
    material = get_material("sp_no2")
    assert material.category == "sawn"      # SP is a normal sawn material
    loads = [UniformLoad(w=40, load_type="dead"), UniformLoad(w=60, load_type="live")]

    r_2x10 = design_beam(12.0, loads, Section.from_nominal("2x10"), material, repetitive=True)
    assert r_2x10.summary.cf == 1.0          # no size factor for Southern Pine
    assert r_2x10.summary.fb_base == 1050    # size-specific Fb (2x10)
    assert r_2x10.summary.cr == pytest.approx(1.15)
    assert r_2x10.bending.ratio == pytest.approx(0.836, abs=0.002)

    # A different depth pulls a different tabulated Fb (not a CF scaling of
    # a single base value).
    r_2x8 = design_beam(12.0, loads, Section.from_nominal("2x8"), material, repetitive=True)
    assert r_2x8.summary.fb_base == 1200
    assert r_2x8.summary.cf == 1.0

    # Contrast: SPF No. 2 2x10 still uses the CF framework (CF = 1.1).
    spf = design_beam(12.0, loads, Section.from_nominal("2x10"), get_material("spf_no2"), repetitive=True)
    assert spf.summary.cf == pytest.approx(1.1)


def test_column_stability_and_axial_check_nds_3_7():
    # 3-ply 2x6 SPF No. 2 post (b = 4.5, d = 5.5, A = 24.75 in^2), 8 ft
    # (96 in) unbraced both ways, Ke = 1.0, carrying 10,000 lb dead +
    # 5,000 lb live. NDS 3.7 by hand, D+L governing:
    #   slenderness = max(96/5.5, 96/4.5) = 96/4.5 = 21.33 (weak axis)
    #   FcE = 0.822*510000 / 21.33^2 = 921 psi
    #   Fc* = 1150 * CF(1.1) * CD(1.0) = 1265 psi
    #   alpha = 921/1265 = 0.728;  c = 0.8
    #   CP = (1.728/1.6) - sqrt[(1.728/1.6)^2 - 0.728/0.8] = 0.574
    #   Fc' = 1265 * 0.574 = 726 psi;  fc = 15000/24.75 = 606 psi
    #   ratio = 606 / 726 = 0.835
    section = Section.from_nominal("2x6", plies=3)
    result = design_column(
        {"dead": 10000, "live": 5000}, section, SPF_NO2,
        unbraced_length_d=96.0, unbraced_length_b=96.0, ke=1.0,
    )
    s = result.summary
    assert s.cf_c == pytest.approx(1.1)          # Fc size factor for 2x6
    assert s.c_coefficient == 0.8                # sawn lumber
    assert s.slenderness == pytest.approx(21.333, abs=0.01)
    assert s.fce == pytest.approx(921.0, abs=1.5)
    assert s.cp == pytest.approx(0.574, abs=0.002)
    assert result.compression.governing_combo == "D+L"
    assert result.compression.ratio == pytest.approx(0.835, abs=0.003)
    assert result.passed is True

    # A single 2x6 (b = 1.5) unbraced 8 ft is far too slender: le/b = 64 >
    # 50, so the check fails loudly regardless of stress.
    slender = design_column(
        {"dead": 2000}, Section.from_nominal("2x6"), SPF_NO2, 96.0, 96.0, ke=1.0,
    )
    assert slender.summary.slenderness == pytest.approx(64.0, abs=0.1)
    assert slender.summary.over_slender is True
    assert slender.passed is False

    # Engineered lumber uses c = 0.9 (vs 0.8 for sawn).
    glulam = design_column(
        {"dead": 10000}, Section.from_nominal("gl_5.125x12"), get_material("gl_24f_1_8e"),
        120.0, 120.0, ke=1.0,
    )
    assert glulam.summary.c_coefficient == 0.9
    assert glulam.summary.cf_c == 1.0


def test_posts_and_timbers_and_4x_sizes():
    # Posts & Timbers (NDS-S Table 4D) are a distinct "timber" category:
    # lower reference values than dimension lumber, no Cr, CF = 1.0, dry.
    # 6x6 DF-L No.1 P&T (b = d = 5.5, A = 30.25), 10 ft column, Ke = 1.0,
    # 10,000 lb dead + 5,000 lb live, D+L governing:
    #   Fc = 1000 psi (Table 4D, well below dimension-lumber DF-L No.1)
    #   slenderness = 120/5.5 = 21.82; FcE = 0.822*580000/21.82^2 = 1001 psi
    #   Fc* = 1000; alpha = 1.001; c = 0.8 -> CP = 0.692
    #   Fc' = 692 psi; fc = 15000/30.25 = 496 psi; ratio = 0.717
    timber = get_material("pt_dfl_no1")
    assert timber.is_timber is True
    column = design_column(
        {"dead": 10000, "live": 5000}, Section.from_nominal("pt_6x6"), timber,
        unbraced_length_d=120.0, unbraced_length_b=120.0, ke=1.0,
    )
    assert column.summary.section.label == "6x6"
    assert column.summary.cf_c == 1.0            # no size factor for P&T
    assert column.summary.c_coefficient == 0.8   # sawn timber
    assert column.summary.slenderness == pytest.approx(21.818, abs=0.01)
    assert column.summary.cp == pytest.approx(0.692, abs=0.003)
    assert column.compression.ratio == pytest.approx(0.717, abs=0.003)

    # A P&T member used as a beam takes no Cr and no wet-service CM, even
    # when both are requested (it is a single solid timber, dry-modelled).
    beam = design_beam(
        10.0, [UniformLoad(w=100, load_type="dead"), UniformLoad(w=200, load_type="live")],
        Section.from_nominal("pt_6x8"), timber, repetitive=True, wet_service=True,
    )
    assert beam.summary.material_category == "timber"
    assert beam.summary.cf == 1.0
    assert beam.summary.cr == 1.0
    assert beam.summary.wet_service is False

    # 4x4 / 4x6 are dimension lumber (existing materials): they carry the
    # usual size factors (Fc CF = 1.1 for 4x6) and section geometry.
    dl_column = design_column(
        {"dead": 8000}, Section.from_nominal("4x6"), get_material("dfl_no2"),
        unbraced_length_d=96.0, unbraced_length_b=96.0, ke=1.0,
    )
    assert dl_column.summary.section.A == pytest.approx(3.5 * 5.5)
    assert dl_column.summary.cf_c == pytest.approx(1.1)


def test_beam_column_interaction_nds_3_9():
    # 4x6 DF-L No. 1 (b=3.5, d=5.5, A=19.25, Sx=17.646), 10 ft, Ke=1.0,
    # unbraced both ways. Axial 3000 lb dead + 1000 lb live; lateral wind
    # 120 plf about the strong axis (M = 120*10^2/8 = 1500 ft-lb). NDS 3.9.2,
    # D+W governing the interaction (CD=1.6):
    #   slenderness = 120/3.5 = 34.29 (weak axis) -> CP small
    #   fc = 3000/19.25 = 155.8; Fc* = 1550*1.1*1.6 = 2728; CP=0.153 -> Fc'=418
    #   fc/Fc' = 0.372 -> squared 0.139
    #   fb = 1500*12/17.646 = 1020; Fb' = 1200*1.3*1.6 = 2496; fb/Fb'=0.409
    #   FcE1 = 0.822*620000/(120/5.5)^2 = 1071; amp = 1 - 155.8/1071 = 0.854
    #   interaction = 0.139 + 0.409/0.854 = 0.617
    section = Section.from_nominal("4x6")
    result = design_beam_column(
        {"dead": 3000, "live": 1000}, section, get_material("dfl_no1"),
        unbraced_length_d=120.0, unbraced_length_b=120.0, ke=1.0,
        height_ft=10.0, lateral_load_plf=120.0, lateral_load_type="wind",
    )
    s = result.summary
    assert s.cf_c == pytest.approx(1.1)
    assert s.cf_b == pytest.approx(1.3)
    assert s.slenderness == pytest.approx(34.286, abs=0.01)
    assert s.fce1 == pytest.approx(1070.6, abs=1.5)

    # Pure-axial utilization is reported unsquared (governed by D+L), so a
    # high axial ratio is never masked by the squared interaction term.
    assert result.axial.governing_combo == "D+L"
    assert result.axial.ratio == pytest.approx(0.509, abs=0.003)
    assert result.bending.governing_combo == "D+W"
    assert result.bending.ratio == pytest.approx(0.409, abs=0.003)

    assert result.interaction.governing_combo == "D+W"
    assert result.interaction.ratio == pytest.approx(0.617, abs=0.003)
    assert result.governing is result.interaction
    assert result.passed is True

    # Adding no lateral load reduces the interaction to the pure column
    # squared term -- the member with only axial passes on axial alone.
    axial_only = design_beam_column(
        {"dead": 3000, "live": 1000}, section, get_material("dfl_no1"),
        unbraced_length_d=120.0, unbraced_length_b=120.0, ke=1.0,
        height_ft=10.0, lateral_load_plf=0.0,
    )
    assert axial_only.bending.ratio == 0.0
    assert axial_only.interaction.ratio == pytest.approx(0.509 ** 2, abs=0.003)


def test_end_notch_reduces_shear_capacity_nds_3_4_3():
    # Same repetitive 2x10 SPF No. 2 beam (base shear ratio 0.481). A 2 in
    # tension-side end notch leaves dn = 9.25 - 2 = 7.25 in. NDS 3.4.3.2(a)
    # magnifies the shear stress by (d/dn)^2, i.e. an effective capacity
    # factor (dn/d)^2 = (7.25/9.25)^2 = 0.614:
    #   notched shear ratio = 0.481 / 0.614 = 0.782
    span = 12.0
    loads = [UniformLoad(w=40, load_type="dead"), UniformLoad(w=60, load_type="live")]
    section = Section.from_nominal("2x10")

    base = design_beam(span, loads, section, SPF_NO2, repetitive=True)
    notched = design_beam(span, loads, section, SPF_NO2, repetitive=True, end_notch_depth=2.0)

    assert notched.summary.end_notch_depth == 2.0
    assert notched.summary.notch_dn == pytest.approx(7.25)
    assert notched.shear.ratio == pytest.approx(0.782, abs=0.002)
    # Only shear at the notched end is affected; bending is unchanged.
    assert notched.bending.ratio == pytest.approx(base.bending.ratio, abs=1e-6)
    assert "end notch" in notched.shear.name

    # A notch through the full depth leaves no section to resist shear.
    through = design_beam(span, loads, section, SPF_NO2, end_notch_depth=9.25)
    assert through.shear.ratio == 999.0
    assert through.shear.passed is False


def test_round_hole_net_section_shear_check():
    # Repetitive 2x10 SPF No. 2 (base shear ratio 0.481, A = 13.875 in^2).
    # A 2 in round hole leaves net depth dn = 7.25 in (net area 10.875 in^2).
    # Evaluated at max shear it is the full-section check scaled by the net
    # area: 0.481 * 13.875/10.875 = 0.613. Placed at 3 ft on the 12 ft span,
    # the shear there is V = 600 - 100*3 = 300 lb (half of Vmax), so the
    # check halves to 0.307 -- holes in low-shear zones are not over-penalized.
    span = 12.0
    loads = [UniformLoad(w=40, load_type="dead"), UniformLoad(w=60, load_type="live")]
    section = Section.from_nominal("2x10")

    at_max = design_beam(span, loads, section, SPF_NO2, repetitive=True, hole_diameter=2.0)
    hole_max = next(c for c in at_max.checks if "hole" in c.name)
    assert at_max.summary.hole_net_depth == pytest.approx(7.25)
    assert hole_max.ratio == pytest.approx(0.613, abs=0.002)

    at_3ft = design_beam(span, loads, section, SPF_NO2, repetitive=True, hole_diameter=2.0, hole_location=3.0)
    hole_3 = next(c for c in at_3ft.checks if "hole" in c.name)
    assert hole_3.ratio == pytest.approx(0.3065, abs=0.002)
    assert "3.00 ft" in hole_3.name

    # A hole as deep as the member leaves no section to resist shear.
    oversize = design_beam(span, loads, section, SPF_NO2, hole_diameter=9.25)
    hole_big = next(c for c in oversize.checks if "hole" in c.name)
    assert hole_big.ratio == 999.0
    assert hole_big.passed is False


def test_creep_factor_amplifies_dead_deflection_nds_3_5_2():
    # Repetitive 2x10 SPF No. 2, 40 plf dead + 60 plf live. Elastic total
    # deflection = 0.337 in (ratio 0.561). NDS 3.5.2 long-term deflection
    # amplifies the sustained (dead) portion by Kcr; the dead-only
    # deflection is 40/100 of the total = 0.135 in, so:
    #   Kcr = 1.5:  0.337 + 0.5*0.135 = 0.404 in -> ratio 0.674
    #   Kcr = 2.0:  0.337 + 1.0*0.135 = 0.472 in -> ratio 0.786
    span = 12.0
    loads = [UniformLoad(w=40, load_type="dead"), UniformLoad(w=60, load_type="live")]
    section = Section.from_nominal("2x10")

    base = design_beam(span, loads, section, SPF_NO2, repetitive=True)
    assert base.deflection_total.ratio == pytest.approx(0.561, abs=0.002)

    k15 = design_beam(span, loads, section, SPF_NO2, repetitive=True, creep_factor=1.5)
    assert k15.summary.creep_factor == 1.5
    assert k15.deflection_total.ratio == pytest.approx(0.674, abs=0.003)
    assert "Kcr=1.5" in k15.deflection_total.name
    # Only the total (sustained-inclusive) check is affected; live is not.
    assert k15.deflection_live.ratio == pytest.approx(base.deflection_live.ratio, abs=1e-6)

    k20 = design_beam(span, loads, section, SPF_NO2, repetitive=True, creep_factor=2.0)
    assert k20.deflection_total.ratio == pytest.approx(0.786, abs=0.003)


def test_single_shear_bolt_yield_limit_nds_12_3():
    # 1/2" bolt, single shear, two Douglas Fir-Larch members (G = 0.50),
    # main 3.5 in / side 1.5 in, load parallel to grain, Fyb = 45,000 psi.
    # Fem = Fes = 11,200*0.50 = 5,600 psi. Yield-limit equations (Rd = 4 for
    # Im/Is, 3.6 for II, 3.2 for III/IV; Ktheta = 1 parallel):
    #   Im = 2450, Is = 1050, II = 913, IIIm = 1103, IIIs = 615, IV = 716 lb
    #   Z = min = 615 lb, governed by mode IIIs.
    from engine import design_connection, single_shear_z
    from engine.connections import dowel_bearing_strength

    fe = dowel_bearing_strength(0.50, 0.5)
    assert fe == pytest.approx(5600.0)
    y = single_shear_z(0.5, 45000, lm=3.5, ls=1.5, fem=fe, fes=fe, angle_deg=0.0)
    assert y.mode == "IIIs"
    assert y.z == pytest.approx(614.8, abs=1.0)
    assert y.mode_values["Im"] == pytest.approx(2450.0, abs=1.0)
    assert y.mode_values["IV"] == pytest.approx(716.0, abs=1.0)

    # Design wrapper: 4 bolts, CD = 1.0, 2000 lb lateral -> ratio 0.81.
    r = design_connection(0.5, 45000, 3.5, 1.5, 0.50, 0.50, load_lb=2000, cd=1.0, n_fasteners=4)
    assert r.z_adjusted == pytest.approx(614.8, abs=1.0)
    assert r.capacity == pytest.approx(2459.0, abs=4.0)
    assert r.ratio == pytest.approx(0.813, abs=0.003)
    assert r.passed is True

    # Perpendicular loading uses a different, lower dowel bearing strength.
    assert dowel_bearing_strength(0.50, 0.5, perpendicular=True) < fe
    # Small-diameter dowels (nails) have no grain-angle dependence.
    assert dowel_bearing_strength(0.42, 0.131) == dowel_bearing_strength(0.42, 0.131, perpendicular=True)


def test_connection_group_and_geometry_factors():
    # Group action factor Cg (NDS 11.3-1): 4 x 1/2" bolts at 3 in spacing,
    # two DF-L 3.5x5.5 members (A = 19.25, E = 1.6e6, EA = 3.08e7),
    # gamma = 180000*0.5^1.5. Worked by hand: u = 1.0062, m = 0.8947,
    # Cg = 0.994. More/closer fasteners in thinner members reduce Cg.
    from engine.connections import (
        design_connection,
        geometry_factor,
        group_action_factor,
    )

    ea = 1.6e6 * 19.25
    assert group_action_factor(4, 3.0, 0.5, ea, ea) == pytest.approx(0.994, abs=0.002)
    assert group_action_factor(1, 3.0, 0.5, ea, ea) == 1.0
    ea_thin = 1.4e6 * (1.5 * 3.5)
    assert group_action_factor(8, 2.5, 0.5, ea_thin, ea_thin) < group_action_factor(4, 3.0, 0.5, ea, ea)

    # Geometry factor CDelta (NDS 12.5.1), 1/2" bolt: full at end >= 7D (3.5)
    # and spacing >= 4D (2.0); reduced proportionally; below 3.5D end / 3D
    # spacing it is not permitted (0.0).
    assert geometry_factor(0.5, 3.5, 2.0) == pytest.approx(1.0)
    assert geometry_factor(0.5, 2.5, 1.75) == pytest.approx(0.714, abs=0.002)  # end governs
    assert geometry_factor(0.5, 1.5, 2.0) == 0.0                                # end < 3.5D -> not permitted
    assert geometry_factor(0.131, 1.0, 0.5) == 1.0                              # nails not reduced here

    # Applied to a connection: Cg drops the capacity from the ungrouped value.
    grouped = design_connection(
        0.5, 45000, 3.5, 1.5, 0.50, 0.50, load_lb=2000, cd=1.0, n_fasteners=4,
        spacing=3.0, end_distance=3.5, ea_main=ea, ea_side=ea,
    )
    assert grouped.cg == pytest.approx(0.994, abs=0.002)
    assert grouped.c_delta == pytest.approx(1.0)
    assert grouped.z_adjusted == pytest.approx(614.8 * grouped.cg, abs=1.0)


def test_double_shear_bolt_yield_limit():
    # Same 1/2" bolt / DF-L (Fem = Fes = 5600, Fyb = 45000) but in DOUBLE
    # shear: a 3.5 in main member between two 1.5 in side members. Only four
    # yield modes apply (Im, Is, IIIs, IV), and Is/IIIs/IV carry a factor of
    # 2 for the two shear planes:
    #   Im = 2450, Is = 2100, IIIs = 1230, IV = 1432 lb -> Z = 1230 (IIIs),
    # exactly twice the single-shear IIIs value (615).
    from engine import design_connection, double_shear_z, single_shear_z
    from engine.connections import dowel_bearing_strength

    fe = dowel_bearing_strength(0.50, 0.5)
    ss = single_shear_z(0.5, 45000, 3.5, 1.5, fe, fe)
    ds = double_shear_z(0.5, 45000, 3.5, 1.5, fe, fe)
    assert set(ds.mode_values) == {"Im", "Is", "IIIs", "IV"}
    assert ds.mode == "IIIs"
    assert ds.z == pytest.approx(1229.6, abs=1.5)
    assert ds.z == pytest.approx(2 * ss.z, abs=1.0)  # IIIs governs both -> exactly 2x

    r = design_connection(0.5, 45000, 3.5, 1.5, 0.50, 0.50, load_lb=4000, cd=1.0,
                          n_fasteners=4, double_shear=True)
    assert r.double_shear is True
    assert r.capacity == pytest.approx(4 * 1229.6, abs=6.0)
    assert r.ratio == pytest.approx(0.813, abs=0.003)


def test_withdrawal_design_values_nds_12_2():
    # NDS 12.2 withdrawal design values W (lb per inch of penetration):
    #   10d nail   D = 0.148, G = 0.50: W = 1380*0.5^2.5*0.148 = 36.1
    #   1/4 lag    D = 0.25,  G = 0.50: W = 1800*0.5^1.5*0.25^0.75 = 225.0
    #   #10 screw  D = 0.19,  G = 0.42: W = 2850*0.42^2*0.19 = 95.5
    #   bolt: not designed for withdrawal -> 0
    from engine import design_withdrawal
    from engine.connections import withdrawal_value

    assert withdrawal_value("nail", 0.50, 0.148) == pytest.approx(36.1, abs=0.2)
    assert withdrawal_value("lag", 0.50, 0.25) == pytest.approx(225.0, abs=0.5)
    assert withdrawal_value("screw", 0.42, 0.19) == pytest.approx(95.5, abs=0.3)
    assert withdrawal_value("bolt", 0.50, 0.5) == 0.0

    # Design: 4 x 10d nails, 1.5 in penetration, CD = 1.0, 150 lb pull.
    #   W' = 36.1*1.5 = 54.2 lb/nail; capacity = 4*54.2 = 217 lb; ratio 0.69
    r = design_withdrawal("nail", 0.50, 0.148, penetration=1.5, load_lb=150, cd=1.0, n_fasteners=4)
    assert r.applicable is True
    assert r.w_single == pytest.approx(54.2, abs=0.3)
    assert r.capacity == pytest.approx(216.6, abs=1.5)
    assert r.ratio == pytest.approx(0.692, abs=0.003)
    assert r.passed is True

    # Bolts are not designed for withdrawal -> not applicable, fails.
    b = design_withdrawal("bolt", 0.50, 0.5, penetration=3.5, load_lb=1000, cd=1.0, n_fasteners=2)
    assert b.applicable is False
    assert b.passed is False


def test_connection_wet_service_factor_nds_11_3_3():
    # NDS Table 11.3.3 wet service factor CM (wood dry at fabrication,
    # wet in service): lateral dowels 0.7; withdrawal 0.25 nails/spikes,
    # 0.7 lag/wood screws. Dry service -> 1.0 in every case.
    from engine import design_connection, design_withdrawal, wet_service_factor

    assert wet_service_factor("bolt", wet=False) == 1.0
    assert wet_service_factor("bolt", wet=True) == 0.7                     # lateral
    assert wet_service_factor("nail", wet=True, withdrawal=True) == 0.25
    assert wet_service_factor("spike", wet=True, withdrawal=True) == 0.25
    assert wet_service_factor("lag", wet=True, withdrawal=True) == 0.7
    assert wet_service_factor("screw", wet=True, withdrawal=True) == 0.7
    assert wet_service_factor("nail", wet=False, withdrawal=True) == 1.0

    # Lateral: CM = 0.7 scales Z' and the capacity to exactly 70% of dry.
    dry = design_connection(0.5, 45000, 3.5, 1.5, 0.5, 0.5, 2000, cd=1.0, n_fasteners=4)
    wet = design_connection(0.5, 45000, 3.5, 1.5, 0.5, 0.5, 2000, cd=1.0, n_fasteners=4, wet=True)
    assert wet.cm == 0.7
    assert wet.z == pytest.approx(dry.z)                 # reference Z unchanged
    assert wet.capacity == pytest.approx(0.7 * dry.capacity, rel=1e-6)

    # Withdrawal: nail CM = 0.25 (severe), lag CM = 0.7.
    wn = design_withdrawal("nail", 0.50, 0.148, penetration=1.5, load_lb=150, cd=1.0, n_fasteners=4, wet=True)
    assert wn.cm == 0.25
    assert wn.capacity == pytest.approx(0.25 * 216.6, abs=1.0)
    wl = design_withdrawal("lag", 0.50, 0.25, penetration=3.0, load_lb=600, cd=1.0, n_fasteners=2, wet=True)
    assert wl.cm == 0.7


def test_connection_toe_nail_factor_nds_12_5_4():
    # NDS 12.5.4 toe-nail factor Ctn for nails/spikes: 0.83 lateral,
    # 0.67 withdrawal. Other fasteners and non-toe-nailed connections: 1.0.
    from engine import design_connection, design_withdrawal, toe_nail_factor

    assert toe_nail_factor("nail", toe_nail=True) == 0.83                       # lateral
    assert toe_nail_factor("spike", toe_nail=True, withdrawal=True) == 0.67
    assert toe_nail_factor("bolt", toe_nail=True) == 1.0                        # not a nail
    assert toe_nail_factor("nail", toe_nail=False, withdrawal=True) == 1.0      # not toe-nailed

    # Lateral: 16d nail (D = 0.162) in DF-L; Ctn scales Z' to 83% of base.
    base = design_connection(0.162, 100000, 1.5, 1.5, 0.5, 0.5, 0, cd=1.0, fastener_type="nail")
    toe = design_connection(0.162, 100000, 1.5, 1.5, 0.5, 0.5, 0, cd=1.0, fastener_type="nail", toe_nail=True)
    assert base.ctn == 1.0
    assert toe.ctn == 0.83
    assert toe.z_adjusted == pytest.approx(0.83 * base.z_adjusted, rel=1e-6)

    # Withdrawal: Ctn = 0.67, and it stacks multiplicatively with wet CM.
    dry = design_withdrawal("nail", 0.50, 0.162, penetration=1.5, load_lb=0, cd=1.0)
    tn = design_withdrawal("nail", 0.50, 0.162, penetration=1.5, load_lb=0, cd=1.0, toe_nail=True)
    assert tn.ctn == 0.67
    assert tn.w_adjusted == pytest.approx(0.67 * dry.w_adjusted, rel=1e-6)
    wet_toe = design_withdrawal("nail", 0.50, 0.162, penetration=1.5, load_lb=0, cd=1.0, toe_nail=True, wet=True)
    assert wet_toe.w_adjusted == pytest.approx(0.25 * 0.67 * dry.w_adjusted, rel=1e-6)


def test_connection_temperature_factor_nds_11_3_4():
    # NDS Table 11.3.4 temperature factor Ct: T <= 100F -> 1.0;
    # 100-125F -> 0.8 dry / 0.7 wet; 125-150F -> 0.7 dry / 0.5 wet.
    from engine import design_connection, design_withdrawal, temperature_factor

    assert temperature_factor("normal", wet=False) == 1.0
    assert temperature_factor("warm", wet=False) == 0.8
    assert temperature_factor("warm", wet=True) == 0.7
    assert temperature_factor("hot", wet=False) == 0.7
    assert temperature_factor("hot", wet=True) == 0.5

    # Lateral: Ct scales Z' and capacity; stacks with wet CM.
    base = design_connection(0.5, 45000, 3.5, 1.5, 0.5, 0.5, 2000, cd=1.0, n_fasteners=4)
    warm = design_connection(0.5, 45000, 3.5, 1.5, 0.5, 0.5, 2000, cd=1.0, n_fasteners=4, temperature="warm")
    assert base.ct == 1.0
    assert warm.ct == 0.8
    assert warm.capacity == pytest.approx(0.8 * base.capacity, rel=1e-6)
    hot_wet = design_connection(0.5, 45000, 3.5, 1.5, 0.5, 0.5, 2000, cd=1.0, n_fasteners=4,
                                temperature="hot", wet=True)
    assert hot_wet.ct == 0.5
    assert hot_wet.cm == 0.7
    assert hot_wet.capacity == pytest.approx(0.5 * 0.7 * base.capacity, rel=1e-6)

    # Withdrawal: Ct applies the same way.
    w = design_withdrawal("lag", 0.50, 0.25, penetration=3.0, load_lb=600, cd=1.0, n_fasteners=2, temperature="warm")
    assert w.ct == 0.8


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
