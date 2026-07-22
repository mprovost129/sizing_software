"""Axial compression (column / post) design per NDS 2018 Chapter 3.7.

A column is a compression member sized for the axial load parallel to
grain, distinct from the bending members in engine/checks.py. The check
is fc = P/A vs Fc' = Fc x CD x CF x CP, where CP (engine/factors.py) is
the column stability factor that captures buckling.

The member may buckle about either principal axis. The two axes can have
different unbraced lengths (e.g. a stud braced by sheathing about its weak
axis), so the governing slenderness ratio is the larger of le/d and le/b,
each with its own unbraced length and the effective-length factor Ke.

Scope (MVP): dry service (CM = 1.0), concentric axial load only (no
combined bending -- that is a future beam-column addition). Values come
from the same material library as the beam checks; Fc drives the result.
"""
from dataclasses import dataclass

from .checks import DEFAULT_COMBINATIONS, SectionSummary
from .factors import (
    SIZE_FACTORS_FB,
    SIZE_FACTORS_FC,
    beam_stability_factor,
    column_stability_factor,
)
from .materials import Material
from .sections import Section


@dataclass
class ColumnCheckResult:
    name: str
    demand: float      # applied compressive stress fc, psi
    capacity: float    # allowable Fc', psi
    ratio: float
    governing_combo: str
    passed: bool


@dataclass
class ColumnComboSummary:
    name: str
    cd: float
    p: float           # axial load for this combination, lb
    fc: float          # fc = P/A, psi
    cp: float          # column stability factor for this combination
    fc_allow: float    # Fc', psi
    ratio: float


@dataclass
class ColumnSummary:
    section: SectionSummary
    material_name: str
    material_category: str
    fc_base: float          # reference Fc, psi
    e: float
    emin: float
    cf_c: float             # compression size factor CF (1.0 for SP/engineered)
    c_coefficient: float    # 0.8 sawn / 0.9 glulam & LVL
    ke: float
    unbraced_length_d: float  # in, buckling about the strong (depth) axis
    unbraced_length_b: float  # in, buckling about the weak (width) axis
    le_d: float               # effective length about the d axis, in
    le_b: float               # effective length about the b axis, in
    slenderness: float        # governing le/d
    fce: float                # critical buckling design value, psi
    cp: float                 # governing column stability factor
    over_slender: bool
    combos: list


@dataclass
class ColumnResult:
    summary: ColumnSummary
    compression: ColumnCheckResult

    @property
    def passed(self) -> bool:
        return self.compression.passed

    @property
    def governing(self) -> ColumnCheckResult:
        return self.compression


def design_column(
    axial_loads: dict,
    section: Section,
    material: Material,
    unbraced_length_d: float,
    unbraced_length_b: float,
    ke: float = 1.0,
    combinations=DEFAULT_COMBINATIONS,
) -> ColumnResult:
    """Design a wood column for concentric axial compression.

    ``axial_loads`` maps load type -> axial load in lb (e.g.
    {"dead": 10000, "live": 5000}). ``unbraced_length_d`` /
    ``unbraced_length_b`` are the unbraced lengths (in) for buckling about
    the depth and width axes; ``ke`` is the effective-length factor.
    """
    # Compression size factor: the CF table applies to visually graded
    # dimension lumber; Southern Pine (size-specific values) and the
    # engineered materials use CF = 1.0.
    if material.category == "sawn" and not material.fb_by_size:
        cf_c = SIZE_FACTORS_FC.get(section.nominal, 1.0)
    else:
        cf_c = 1.0
    c_coefficient = 0.9 if material.category in ("lvl", "glulam") else 0.8

    le_d = ke * unbraced_length_d
    le_b = ke * unbraced_length_b
    # Slenderness about each axis uses that axis's resisting dimension: the
    # depth d resists buckling about the strong axis, the width b the weak.
    slenderness = max(le_d / section.d, le_b / section.b)

    combos = []
    best = None
    governing_cp = 1.0
    governing_fce = 0.0
    for combo in combinations:
        p = sum(axial_loads.get(t, 0) or 0 for t in combo.load_types)
        if p <= 0:
            continue
        fc = p / section.A
        fc_star = material.Fc * cf_c * combo.cd
        stability = column_stability_factor(slenderness, material.Emin, fc_star, c_coefficient)
        fc_allow = fc_star * stability.cp
        ratio = fc / fc_allow
        combos.append(ColumnComboSummary(
            name=combo.name, cd=combo.cd, p=p, fc=fc, cp=stability.cp, fc_allow=fc_allow, ratio=ratio,
        ))
        if best is None or ratio > best.ratio:
            best = ColumnCheckResult("Axial compression", fc, fc_allow, ratio, combo.name, ratio <= 1.0)
            governing_cp = stability.cp
            governing_fce = stability.fce

    over_slender = slenderness > 50.0
    if best is None:
        # No positive axial load entered -- report a zero-demand pass so the
        # caller still gets a well-formed result rather than None.
        best = ColumnCheckResult("Axial compression", 0.0, 0.0, 0.0, "None", True)
    elif over_slender:
        best = ColumnCheckResult(
            f"Axial compression -- le/d = {slenderness:.0f} EXCEEDS NDS SLENDERNESS LIMIT OF 50: "
            "shorten the unbraced length or use a larger section",
            demand=best.demand, capacity=best.capacity, ratio=max(best.ratio, 999.0),
            governing_combo=best.governing_combo, passed=False,
        )

    summary = ColumnSummary(
        section=SectionSummary(
            nominal=section.nominal, b=section.b, d=section.d,
            A=section.A, I=section.I, S=section.S, plies=section.plies,
        ),
        material_name=material.name,
        material_category=material.category,
        fc_base=material.Fc,
        e=material.E,
        emin=material.Emin,
        cf_c=cf_c,
        c_coefficient=c_coefficient,
        ke=ke,
        unbraced_length_d=unbraced_length_d,
        unbraced_length_b=unbraced_length_b,
        le_d=le_d,
        le_b=le_b,
        slenderness=slenderness,
        fce=governing_fce,
        cp=governing_cp,
        over_slender=over_slender,
        combos=combos,
    )
    return ColumnResult(summary=summary, compression=best)


# ---------------------------------------------------------------------------
# Beam-column: combined axial compression + bending (NDS 2018 Section 3.9.2)
# ---------------------------------------------------------------------------
@dataclass
class BeamColumnComboSummary:
    name: str
    cd: float
    p: float           # axial load, lb
    fc: float          # axial stress, psi
    fc_allow: float    # Fc', psi
    m: float           # bending moment, in-lb
    fb: float          # bending stress, psi
    fb_allow: float    # Fb', psi
    amplification: float  # 1 - fc/FcE1 (P-delta magnifier denominator)
    interaction: float    # NDS 3.9-3 left-hand side


@dataclass
class BeamColumnSummary:
    section: SectionSummary
    material_name: str
    material_category: str
    fc_base: float
    fb_base: float
    e: float
    emin: float
    cf_c: float
    cf_b: float
    c_coefficient: float
    ke: float
    unbraced_length_d: float
    unbraced_length_b: float
    slenderness: float          # governing le/d for the axial (column) check
    cp: float                   # governing column stability factor
    cl: float                   # beam stability factor for the bending term
    fce1: float                 # Euler buckling stress in the plane of bending
    lateral_load_plf: float
    bending_moment: float       # M = w*H^2/8, in-lb
    height_ft: float
    combos: list


@dataclass
class BeamColumnResult:
    summary: BeamColumnSummary
    axial: ColumnCheckResult          # fc / Fc'  (pure axial)
    bending: ColumnCheckResult        # fb / Fb'  (pure bending)
    interaction: ColumnCheckResult    # NDS 3.9-3 combined

    @property
    def passed(self) -> bool:
        return self.axial.passed and self.bending.passed and self.interaction.passed

    @property
    def governing(self) -> ColumnCheckResult:
        return max((self.axial, self.bending, self.interaction), key=lambda c: c.ratio)


def _bending_base_and_cf(material, section):
    """Reference Fb and its size/volume factor for the bending term,
    matching how the beam checks treat each material family."""
    if material.is_lvl:
        return material.Fb, (material.cv_reference_depth / section.d) ** material.cv_exponent
    if material.fb_by_size:
        return material.fb_by_size.get(section.nominal, material.Fb), 1.0
    if material.category == "sawn":
        return material.Fb, SIZE_FACTORS_FB.get(section.nominal, 1.0)
    return material.Fb, 1.0  # glulam / timber


def design_beam_column(
    axial_loads: dict,
    section: Section,
    material: Material,
    unbraced_length_d: float,
    unbraced_length_b: float,
    ke: float,
    height_ft: float,
    lateral_load_plf: float,
    lateral_load_type: str = "wind",
    bending_unbraced_length: float | None = None,
    combinations=DEFAULT_COMBINATIONS,
) -> BeamColumnResult:
    """Design a member for combined axial compression and uniaxial (strong
    axis) bending, per NDS 2018 Section 3.9.2:

        (fc/Fc')^2 + fb / [Fb' (1 - fc/FcE1)] <= 1.0

    The bending comes from a uniform lateral load (e.g. wind on a stud) of
    ``lateral_load_plf`` over ``height_ft``, giving M = w*H^2/8 about the
    strong axis. It is added in every load combination that contains
    ``lateral_load_type``. FcE1 is the Euler buckling stress in the plane of
    bending (resisted by the depth). ``bending_unbraced_length`` is the
    compression-edge unbraced length for CL (None = braced, CL = 1.0).
    """
    if material.category == "sawn" and not material.fb_by_size:
        cf_c = SIZE_FACTORS_FC.get(section.nominal, 1.0)
    else:
        cf_c = 1.0
    c_coefficient = 0.9 if material.category in ("lvl", "glulam") else 0.8
    fb_base, cf_b = _bending_base_and_cf(material, section)

    le_d = ke * unbraced_length_d
    le_b = ke * unbraced_length_b
    slenderness = max(le_d / section.d, le_b / section.b)
    # Euler stress for buckling in the plane of strong-axis bending
    # (resisted by the depth), NDS 3.9.2.
    fce1 = 0.822 * material.Emin / (le_d / section.d) ** 2

    bending_moment = lateral_load_plf * height_ft ** 2 / 8.0 * 12.0  # in-lb

    combos = []
    axial_best = None
    bending_best = None
    interaction_best = None
    governing_cp = 1.0
    governing_cl = 1.0
    for combo in combinations:
        p = sum(axial_loads.get(t, 0) or 0 for t in combo.load_types)
        has_lateral = lateral_load_plf > 0 and lateral_load_type in combo.load_types
        if p <= 0 and not has_lateral:
            continue

        fc = p / section.A
        fc_star = material.Fc * cf_c * combo.cd
        col_stab = column_stability_factor(slenderness, material.Emin, fc_star, c_coefficient)
        fc_allow = fc_star * col_stab.cp
        axial_ratio = fc / fc_allow if fc_allow else 0.0

        m = bending_moment if has_lateral else 0.0
        fb = m / section.S if m else 0.0
        fb_star = fb_base * cf_b * combo.cd
        beam_stab = beam_stability_factor(bending_unbraced_length, section.d, section.b, material.Emin, fb_star)
        fb_allow = fb_star * beam_stab.cl
        bending_ratio = fb / fb_allow if (m and fb_allow) else 0.0

        amplification = 1.0 - fc / fce1
        if amplification <= 0:
            # fc has reached the Euler buckling stress in the plane of
            # bending: the member is unstable. Force a loud failure.
            interaction = 999.0
        else:
            interaction = axial_ratio ** 2 + (bending_ratio / amplification if fb else 0.0)

        combos.append(BeamColumnComboSummary(
            name=combo.name, cd=combo.cd, p=p, fc=fc, fc_allow=fc_allow,
            m=m, fb=fb, fb_allow=fb_allow, amplification=amplification, interaction=interaction,
        ))
        if axial_best is None or axial_ratio > axial_best.ratio:
            axial_best = ColumnCheckResult("Axial compression", fc, fc_allow, axial_ratio, combo.name, axial_ratio <= 1.0)
            governing_cp = col_stab.cp
        if m and (bending_best is None or bending_ratio > bending_best.ratio):
            bending_best = ColumnCheckResult("Bending", fb, fb_allow, bending_ratio, combo.name, bending_ratio <= 1.0)
            governing_cl = beam_stab.cl
        if interaction_best is None or interaction > interaction_best.ratio:
            interaction_best = ColumnCheckResult(
                "Combined axial + bending (NDS 3.9-3)", 0.0, 0.0, interaction, combo.name, interaction <= 1.0,
            )

    if axial_best is None:
        axial_best = ColumnCheckResult("Axial compression", 0.0, 0.0, 0.0, "None", True)
    if bending_best is None:
        bending_best = ColumnCheckResult("Bending", 0.0, 0.0, 0.0, "None", True)
    if interaction_best is None:
        interaction_best = ColumnCheckResult("Combined axial + bending (NDS 3.9-3)", 0.0, 0.0, 0.0, "None", True)
    if slenderness > 50.0:
        interaction_best = ColumnCheckResult(
            f"Combined axial + bending -- le/d = {slenderness:.0f} EXCEEDS NDS SLENDERNESS LIMIT OF 50",
            0.0, 0.0, max(interaction_best.ratio, 999.0), interaction_best.governing_combo, False,
        )

    summary = BeamColumnSummary(
        section=SectionSummary(
            nominal=section.nominal, b=section.b, d=section.d,
            A=section.A, I=section.I, S=section.S, plies=section.plies,
        ),
        material_name=material.name,
        material_category=material.category,
        fc_base=material.Fc,
        fb_base=fb_base,
        e=material.E,
        emin=material.Emin,
        cf_c=cf_c,
        cf_b=cf_b,
        c_coefficient=c_coefficient,
        ke=ke,
        unbraced_length_d=unbraced_length_d,
        unbraced_length_b=unbraced_length_b,
        slenderness=slenderness,
        cp=governing_cp,
        cl=governing_cl,
        fce1=fce1,
        lateral_load_plf=lateral_load_plf,
        bending_moment=bending_moment,
        height_ft=height_ft,
        combos=combos,
    )
    return BeamColumnResult(summary=summary, axial=axial_best, bending=bending_best, interaction=interaction_best)
