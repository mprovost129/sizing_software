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
from .factors import SIZE_FACTORS_FC, column_stability_factor
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
