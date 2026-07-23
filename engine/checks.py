"""Design checks: bending, shear, bearing, deflection.

Each check computes an allowable (capacity) value adjusted per NDS
factors, compares it to demand, and reports a utilization ratio
(demand/capacity). Bending and shear are evaluated for every load
combination in `combinations` and the governing (highest-ratio) result
is kept, matching how the checks would be verified by hand.

The member may have a left and/or right overhang beyond its two
supports (e.g. a cantilevered deck joist or roof overhang). Bending and
shear checks automatically cover the whole member, including the
negative moment over a support under an overhang, since a symmetric
wood section uses the same Fb either direction -- only max |M| and
max |V| anywhere on the member matter. Deflection gets a check for the
back span (support to support) plus one for each overhang's tip,
using 2x the overhang length as the effective span for the tip check's
allowable-deflection denominator, per common wood-engineering practice
(the tip of an overhang deflects similarly to the end of half of a
simple span twice its length).

`design_beam` also returns a `BeamSummary` alongside the checks -- the
section properties, base material values, adjustment factors, and
per-combination reactions/shear/moment that produced those checks --
so the result can be presented as a transparent, traceable calculation
report rather than a bare pass/fail table (per the project's Initial
MVP requirement).
"""
from dataclasses import dataclass, field, replace

from . import beam as beam_mod
from . import patterns as pattern_mod
from .factors import (
    DRY_SERVICE_FACTORS,
    LOAD_DURATION_FACTORS,
    REPETITIVE_MEMBER_FACTOR,
    SIZE_FACTORS_FB,
    beam_stability_factor,
    bearing_area_factor,
    glulam_volume_factor,
    required_bearing_length,
    wet_service_factors,
)
from .loads import PointLoad, UniformLoad
from .materials import Material
from .sections import SIZE_LABELS, Section
from .span import SpanMode, clear_span


@dataclass(frozen=True)
class Combination:
    name: str
    load_types: tuple
    cd: float


DEAD_ONLY = Combination("D", ("dead",), LOAD_DURATION_FACTORS["dead"])
DEAD_PLUS_LIVE = Combination("D+L", ("dead", "live"), LOAD_DURATION_FACTORS["live"])
DEAD_PLUS_SNOW = Combination("D+S", ("dead", "snow"), LOAD_DURATION_FACTORS["snow"])
DEAD_PLUS_ROOF_LIVE = Combination("D+Lr", ("dead", "roof_live"), LOAD_DURATION_FACTORS["roof_live"])
DEAD_PLUS_WIND = Combination("D+W", ("dead", "wind"), LOAD_DURATION_FACTORS["wind"])
DEFAULT_COMBINATIONS = (DEAD_ONLY, DEAD_PLUS_LIVE, DEAD_PLUS_SNOW, DEAD_PLUS_ROOF_LIVE, DEAD_PLUS_WIND)


def _filter(loads, load_types):
    return [load for load in loads if load.load_type in load_types]


@dataclass
class CheckResult:
    name: str
    demand: float
    capacity: float
    ratio: float
    governing_combo: str
    passed: bool
    # Bearing checks only: minimum bearing length (in) so demand <= capacity.
    # None for every other check.
    required_length: float | None = None


@dataclass
class SectionSummary:
    nominal: str
    b: float
    d: float
    A: float
    I: float
    S: float
    plies: int = 1

    @property
    def label(self) -> str:
        """Section label with a ply prefix for built-up members; engineered
        (LVL/glulam) sizes display their human label rather than the raw id."""
        base = SIZE_LABELS.get(self.nominal, self.nominal)
        return f"{self.plies}-ply {base}" if self.plies > 1 else base


@dataclass
class ComboSummary:
    name: str
    cd: float
    reactions: list[float]
    v_max: float
    v_max_x: float
    m_max: float
    m_max_x: float

    @property
    def r1(self):
        return self.reactions[0] if self.reactions else 0.0

    @property
    def r2(self):
        return self.reactions[1] if len(self.reactions) > 1 else 0.0


@dataclass
class DiagramPoint:
    x: float
    y: float


@dataclass
class DiagramSeries:
    name: str
    unit: str
    governing_combo: str
    peak_x: float
    peak_y: float
    points: list[DiagramPoint]
    # For continuous beams, moment/shear are drawn as a pattern (skip)
    # live-load ENVELOPE: `lower` holds the max-negative curve and `points`
    # the max-positive curve. `lower` is None for single-curve diagrams.
    lower: list[DiagramPoint] | None = None


@dataclass
class BeamSummary:
    span: float
    given_span: float
    span_mode: str
    left_overhang: float
    right_overhang: float
    total_length: float
    span_segments: list[float]
    support_positions: list[float]
    support_labels: list[str]
    section: SectionSummary
    material_name: str
    material_category: str
    fb_base: float
    fv_base: float
    fc_perp_base: float
    e: float
    cf: float
    cr: float
    cl: float
    rb: float
    unbraced_length: float
    bearing_length_left: float
    bearing_length_right: float
    cb_left: float
    cb_right: float
    deflection_limit_live: float
    deflection_limit_total: float
    cantilever_deflection_limit_live: float
    cantilever_deflection_limit_total: float
    combos: list
    load_zones: list
    point_loads: list
    wet_service: bool = False
    cm_fb: float = 1.0
    cm_fv: float = 1.0
    cm_fcperp: float = 1.0
    cm_e: float = 1.0
    end_notch_depth: float = 0.0
    notch_dn: float = 0.0
    hole_diameter: float = 0.0
    hole_location: float | None = None
    hole_net_depth: float = 0.0
    creep_factor: float = 1.0
    shear_diagram: DiagramSeries | None = None
    moment_diagram: DiagramSeries | None = None
    deflection_live_diagram: DiagramSeries | None = None
    deflection_total_diagram: DiagramSeries | None = None


@dataclass
class BeamDesignResult:
    summary: BeamSummary
    bending: CheckResult
    shear: CheckResult
    bearing_left: CheckResult
    bearing_right: CheckResult
    deflection_live: CheckResult
    deflection_total: CheckResult
    # Only set when the member has a left/right overhang; None otherwise.
    deflection_left_cantilever_live: CheckResult | None = None
    deflection_left_cantilever_total: CheckResult | None = None
    deflection_right_cantilever_live: CheckResult | None = None
    deflection_right_cantilever_total: CheckResult | None = None
    extra_checks: list[CheckResult] = field(default_factory=list)

    @property
    def checks(self) -> list:
        fixed = [
            self.bending, self.shear, self.bearing_left, self.bearing_right,
            self.deflection_live, self.deflection_total,
        ]
        optional = [
            self.deflection_left_cantilever_live, self.deflection_left_cantilever_total,
            self.deflection_right_cantilever_live, self.deflection_right_cantilever_total,
        ]
        return fixed + [c for c in optional if c is not None] + self.extra_checks

    @property
    def governing(self) -> CheckResult:
        return max(self.checks, key=lambda c: c.ratio)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)


def design_beam(
    span: float,
    loads: list,
    section: Section,
    material: Material,
    repetitive: bool = False,
    bearing_length_left: float = 1.5,
    bearing_length_right: float = 1.5,
    deflection_limit_live: float = 360,
    deflection_limit_total: float = 240,
    cantilever_deflection_limit_live: float | None = None,
    cantilever_deflection_limit_total: float | None = None,
    span_mode: SpanMode = "inside",
    left_overhang: float = 0.0,
    right_overhang: float = 0.0,
    continuous_spans: list[float] | None = None,
    bearing_lengths: list[float] | None = None,
    unbraced_length: float | None = None,
    wet_service: bool = False,
    end_notch_depth: float = 0.0,
    hole_diameter: float = 0.0,
    hole_location: float | None = None,
    creep_factor: float = 1.0,
    combinations=DEFAULT_COMBINATIONS,
) -> BeamDesignResult:
    # `span` is interpreted per `span_mode`; the back span (support to
    # support) always resolves to the clear (inside-to-inside) distance
    # for analysis, per project convention -- see engine/span.py.
    # Default mode "inside" is a no-op conversion, so existing callers
    # that pass a bare clear span are unaffected.
    is_multi_span = bool(continuous_spans and len(continuous_spans) > 1)
    if is_multi_span:
        if not bearing_lengths or len(bearing_lengths) != len(continuous_spans) + 1:
            raise ValueError("bearing_lengths must contain one entry per support in multi-span mode.")
        analysis_spans = [
            clear_span(given_span, span_mode, bearing_lengths[i], bearing_lengths[i + 1])
            for i, given_span in enumerate(continuous_spans)
        ]
        support_positions = [left_overhang]
        for segment in analysis_spans:
            support_positions.append(support_positions[-1] + segment)
        analysis_span = analysis_spans[0]
        total_length = support_positions[-1] + right_overhang
        a1 = support_positions[0]
        a2 = support_positions[-1]
        span_segments = analysis_spans
    else:
        analysis_span = clear_span(span, span_mode, bearing_length_left, bearing_length_right)
        a1 = left_overhang
        a2 = left_overhang + analysis_span
        total_length = a2 + right_overhang
        support_positions = [a1, a2]
        span_segments = [analysis_span]
        bearing_lengths = [bearing_length_left, bearing_length_right]

    # Bending Fb adjustment for member depth. Visually graded sawn lumber
    # uses the tabulated size factor CF; engineered LVL uses a volume/depth
    # factor CV = (d_ref/d)^exponent -- both fold into Fb the same way, so
    # the rest of the code treats this single `cf` uniformly. Glulam is the
    # exception: its volume factor CV (a length/depth/width function) does
    # NOT apply simultaneously with the beam stability factor CL, so it is
    # kept separate (`glulam_cv`) and the bending check uses min(CV, CL).
    glulam_cv = None
    if material.is_lvl:
        cf = (material.cv_reference_depth / section.d) ** material.cv_exponent
    elif material.is_glulam:
        cf = 1.0
        # L = length between points of zero moment. Use the longest span
        # segment (conservative: a larger L gives a smaller CV).
        glulam_length = max(span_segments)
        glulam_cv = glulam_volume_factor(glulam_length, section.d, section.b, material.cv_exponent)
    elif material.fb_by_size:
        # Southern Pine (NDS-S Table 4B): Fb is tabulated per size, so the
        # size effect is already included and CF = 1.0. Swap in the
        # size-specific Fb so the summary and every check use it.
        cf = 1.0
        material = replace(material, Fb=material.fb_by_size.get(section.nominal, material.Fb))
    else:
        cf = SIZE_FACTORS_FB.get(section.nominal, 1.0)
    # The repetitive-member factor applies only to a system of 3+ single
    # sawn members spaced <= 24" o.c. sharing load through sheathing (NDS
    # 4.3.9); never to an engineered (LVL/glulam) or built-up member.
    cr = REPETITIVE_MEMBER_FACTOR if (repetitive and section.plies == 1 and material.category == "sawn") else 1.0
    # Wet service factor CM (NDS-S Table 4A) applies to sawn lumber only;
    # LVL and glulam are modelled dry-only here (CM = 1.0). The Fb footnote
    # depends on CF, so it is resolved here where CF is known.
    wet_applied = wet_service and material.category == "sawn"
    cm = wet_service_factors(material.Fb, cf) if wet_applied else DRY_SERVICE_FACTORS
    # Tension-side end-notch shear reduction (NDS 3.4.3.2): the remaining
    # depth dn = d - notch, and the effective shear capacity is scaled by
    # (dn/d)^2. dn <= 0 (notch through the section) -> zero capacity.
    notch_dn = section.d - end_notch_depth
    if end_notch_depth > 0:
        notch_factor = (notch_dn / section.d) ** 2 if notch_dn > 0 else 0.0
        notch_label = f"dn = {notch_dn:.2f} in"
    else:
        notch_factor = 1.0
        notch_label = ""
    cantilever_deflection_limit_live = cantilever_deflection_limit_live or deflection_limit_live
    cantilever_deflection_limit_total = cantilever_deflection_limit_total or deflection_limit_total

    summary = BeamSummary(
        span=analysis_span,
        given_span=span,
        span_mode=span_mode,
        left_overhang=left_overhang,
        right_overhang=right_overhang,
        total_length=total_length,
        span_segments=span_segments,
        support_positions=support_positions,
        support_labels=[f"B{i + 1}" for i in range(len(support_positions))],
        section=SectionSummary(
            nominal=section.nominal, b=section.b, d=section.d,
            A=section.A, I=section.I, S=section.S, plies=section.plies,
        ),
        material_name=material.name,
        material_category=material.category,
        fb_base=material.Fb,
        fv_base=material.Fv,
        fc_perp_base=material.Fc_perp,
        e=material.E,
        # For glulam, `cf` reports the volume factor CV (applied as
        # min(CV, CL)); for sawn/LVL it is the CF/CV depth factor folded
        # directly into F'b.
        cf=glulam_cv if glulam_cv is not None else cf,
        cr=cr,
        cl=1.0,  # updated below once the governing bending combination is known
        rb=0.0,
        unbraced_length=unbraced_length or 0.0,
        bearing_length_left=bearing_lengths[0],
        bearing_length_right=bearing_lengths[-1],
        cb_left=bearing_area_factor(bearing_lengths[0]),
        cb_right=bearing_area_factor(bearing_lengths[-1]),
        deflection_limit_live=deflection_limit_live,
        deflection_limit_total=deflection_limit_total,
        cantilever_deflection_limit_live=cantilever_deflection_limit_live,
        cantilever_deflection_limit_total=cantilever_deflection_limit_total,
        wet_service=wet_applied,
        cm_fb=cm.fb,
        cm_fv=cm.fv,
        cm_fcperp=cm.fc_perp,
        cm_e=cm.e,
        end_notch_depth=end_notch_depth,
        notch_dn=notch_dn if end_notch_depth > 0 else 0.0,
        hole_diameter=hole_diameter,
        hole_location=hole_location,
        hole_net_depth=(section.d - hole_diameter) if hole_diameter > 0 else 0.0,
        creep_factor=creep_factor,
        combos=_combo_summaries(total_length, loads, combinations, support_positions),
        load_zones=[
            {
                "w": load.w,
                "load_type": load.load_type,
                "start": load.start,
                "end": total_length if load.end is None else load.end,
            }
            for load in loads
            if isinstance(load, UniformLoad)
        ],
        point_loads=[
            {
                "p": load.p,
                "location": load.location,
                "load_type": load.load_type,
            }
            for load in loads
            if isinstance(load, PointLoad)
        ],
    )

    # From here on every check uses the moisture-adjusted reference values.
    # The summary above kept the unadjusted base values (and the CM factors
    # separately) so the report can show both. In dry service this is a
    # no-op (all CM factors are 1.0), so existing dry designs are unchanged.
    if wet_applied:
        material = replace(
            material,
            Fb=material.Fb * cm.fb,
            Fv=material.Fv * cm.fv,
            Fc_perp=material.Fc_perp * cm.fc_perp,
            E=material.E * cm.e,
            Emin=material.Emin * cm.emin,
        )

    pb = None
    if is_multi_span:
        # Continuous beam: pre-solve each elementary load case once, then
        # assemble every combination's pattern (skip) live-load envelope by
        # superposition. Captures the max positive span moment and max
        # negative support moment that full-span loading misses.
        pb = pattern_mod.PatternedBeam(total_length, loads, support_positions, material.E, section.I)
        bending, stability, shear = _governing_bending_shear_pattern(
            pb, section, material, cf, cr, combinations,
            unbraced_length, glulam_cv, notch_factor, notch_label,
        )
    else:
        bending, stability = _governing_bending(
            total_length, loads, section, material, cf, cr, combinations, support_positions,
            unbraced_length, glulam_cv,
        )
        shear = _governing_shear(
            total_length, loads, section, material, combinations, support_positions,
            notch_factor=notch_factor, notch_label=notch_label,
        )
    summary.cl = stability.cl
    summary.rb = stability.rb
    bearing_checks = [
        _bearing_check(total_length, loads, section, material, length, i, support_positions)
        for i, length in enumerate(bearing_lengths)
    ]
    live_checks, total_checks = _span_deflection_checks(
        total_length, loads, section, material,
        deflection_limit_live, deflection_limit_total, support_positions, creep_factor,
        pb=pb,
    )

    result = BeamDesignResult(
        summary=summary,
        bending=bending,
        shear=shear,
        bearing_left=bearing_checks[0],
        bearing_right=bearing_checks[-1],
        deflection_live=live_checks[0],
        deflection_total=total_checks[0],
    )
    if len(bearing_checks) > 2:
        result.extra_checks.extend(bearing_checks[1:-1])
    result.extra_checks.extend(live_checks[1:])
    result.extra_checks.extend(total_checks[1:])

    if hole_diameter > 0:
        result.extra_checks.append(_hole_shear_check(
            total_length, loads, section, material, combinations, support_positions,
            hole_diameter, hole_location,
        ))

    if left_overhang > 0:
        result.deflection_left_cantilever_live = _transient_cantilever_deflection_check(
            total_length, loads, section, material,
            support_positions, "left", left_overhang, cantilever_deflection_limit_live, pb,
        )
        result.deflection_left_cantilever_total = _cantilever_deflection_check(
            total_length, loads, section, material, ("dead", "live", "snow", "roof_live", "wind"),
            support_positions, "left", left_overhang, cantilever_deflection_limit_total,
            "Total-load deflection (left cantilever tip)", pb,
        )
    if right_overhang > 0:
        result.deflection_right_cantilever_live = _transient_cantilever_deflection_check(
            total_length, loads, section, material,
            support_positions, "right", right_overhang, cantilever_deflection_limit_live, pb,
        )
        result.deflection_right_cantilever_total = _cantilever_deflection_check(
            total_length, loads, section, material, ("dead", "live", "snow", "roof_live", "wind"),
            support_positions, "right", right_overhang, cantilever_deflection_limit_total,
            "Total-load deflection (right cantilever tip)", pb,
        )

    if is_multi_span:
        summary.shear_diagram = _envelope_diagram_series(
            "Shear envelope", "lb", result.shear.governing_combo, pb, "shear",
        )
        summary.moment_diagram = _envelope_diagram_series(
            "Moment envelope", "ft-lb", result.bending.governing_combo, pb, "moment",
        )
        summary.deflection_live_diagram = _pattern_deflection_diagram_series(
            result.deflection_live.name, "in", _transient_load_types_present(loads), pb,
        )
        summary.deflection_total_diagram = _pattern_deflection_diagram_series(
            result.deflection_total.name, "in", ("dead", "live", "snow", "roof_live", "wind"), pb,
        )
    else:
        summary.shear_diagram = _diagram_series_from_combo(
            "Shear diagram", "lb", result.shear.governing_combo, total_length, loads, support_positions, "shear",
        )
        summary.moment_diagram = _diagram_series_from_combo(
            "Moment diagram", "ft-lb", result.bending.governing_combo, total_length, loads, support_positions, "moment",
        )
        summary.deflection_live_diagram = _deflection_diagram_series(
            result.deflection_live.name, "in", _transient_load_types_present(loads),
            total_length, loads, section, material, support_positions,
        )
        summary.deflection_total_diagram = _deflection_diagram_series(
            result.deflection_total.name, "in", ("dead", "live", "snow", "roof_live", "wind"),
            total_length, loads, section, material, support_positions,
        )

    return result


# Transient loads that share a single deflection limit per IRC R301.7
# (that table doesn't distinguish "live" from "snow" for this purpose).
TRANSIENT_LOAD_TYPES = ("live", "snow", "roof_live", "wind")


def _transient_load_types_present(loads):
    present = [t for t in TRANSIENT_LOAD_TYPES if any(load.load_type == t for load in loads)]
    return tuple(present) if present else ("live",)  # no transient load entered; keep prior default


def _transient_back_span_deflection_check(total_length, loads, section, material, limit_denominator, a1, a2):
    present = _transient_load_types_present(loads)
    labels = {"live": "Live", "snow": "Snow", "roof_live": "Roof live", "wind": "Wind"}
    label = "/".join(labels[t] for t in present) + "-load deflection"
    return _back_span_deflection_check(total_length, loads, section, material, present, limit_denominator, label, a1, a2)


def _present_load_label(loads):
    order = ("dead", "live", "snow", "roof_live", "wind")
    codes = {"dead": "D", "live": "L", "snow": "S", "roof_live": "Lr", "wind": "W"}
    present = {load.load_type for load in loads}
    return "+".join(codes[t] for t in order if t in present) or "None"


def _diagram_x_values(total_length, support_positions, loads, samples=180):
    xs = {0.0, float(total_length), *support_positions}
    for load in loads:
        if isinstance(load, PointLoad):
            x = float(load.location)
            xs.add(x)
            eps = min(max(total_length / 10000.0, 1e-4), 0.02)
            if 0.0 < x - eps < total_length:
                xs.add(x - eps)
            if 0.0 < x + eps < total_length:
                xs.add(x + eps)
    for x in support_positions:
        eps = min(max(total_length / 10000.0, 1e-4), 0.02)
        if 0.0 < x - eps < total_length:
            xs.add(x - eps)
        if 0.0 < x + eps < total_length:
            xs.add(x + eps)
    for i in range(samples + 1):
        xs.add(total_length * i / samples)
    return sorted(xs)


def _diagram_series_from_combo(name, unit, combo_name, total_length, loads, support_positions, quantity):
    combo = next((c for c in DEFAULT_COMBINATIONS if c.name == combo_name), None)
    active = _filter(loads, combo.load_types) if combo else []
    # Reactions do not depend on x -- solve the continuous-beam system
    # once and reuse it for every sample point (avoids a full FEM solve
    # per point, which dominated design_beam runtime).
    reactions = beam_mod._reactions(total_length, active, support_positions=support_positions)
    points = []
    peak_x = 0.0
    peak_y = 0.0
    for x in _diagram_x_values(total_length, support_positions, active):
        if quantity == "shear":
            y = beam_mod.shear_at(x, active, total_length=total_length, side="plus",
                                  support_positions=support_positions, reactions=reactions)
        else:
            y = beam_mod.moment_at(x, active, total_length=total_length,
                                   support_positions=support_positions, reactions=reactions)
        points.append(DiagramPoint(x=x, y=y))
        if abs(y) > abs(peak_y):
            peak_x = x
            peak_y = y
    return DiagramSeries(name=name, unit=unit, governing_combo=combo_name, peak_x=peak_x, peak_y=peak_y, points=points)


def _envelope_diagram_series(name, unit, combo_name, pb, quantity):
    """Moment/shear diagram for a continuous beam as a pattern (skip)
    live-load envelope: `points` = max-positive curve, `lower` = max-negative
    curve. Peak is the larger magnitude of the two. Assembled from the
    pre-solved PatternedBeam."""
    combo = next((c for c in DEFAULT_COMBINATIONS if c.name == combo_name), None)
    load_types = combo.load_types if combo else ()
    xs, m_up, m_lo, v_up, v_lo = pb.moment_shear_envelope(load_types)
    if quantity == "moment":
        upper, lower = m_up, m_lo
    else:
        xs = [x for x, _ in pb.v_samples]
        upper, lower = v_up, v_lo
    upper_points = [DiagramPoint(x=x, y=y) for x, y in zip(xs, upper)]
    lower_points = [DiagramPoint(x=x, y=y) for x, y in zip(xs, lower)]
    peak_x = peak_y = 0.0
    for x, y in [*zip(xs, upper), *zip(xs, lower)]:
        if abs(y) > abs(peak_y):
            peak_x, peak_y = x, y
    return DiagramSeries(
        name=name, unit=unit, governing_combo=f"{combo_name} (pattern)",
        peak_x=peak_x, peak_y=peak_y, points=upper_points, lower=lower_points,
    )


def _pattern_deflection_diagram_series(name, unit, load_types, pb):
    """Live/total deflection diagram for a continuous beam: the worst
    downward deflection at each point over all live-load patterns."""
    env = pb.deflection_envelope(load_types)
    points = [DiagramPoint(x=x, y=y) for x, y in zip(pb.xs, env)]
    peak_x = peak_y = 0.0
    for x, y in zip(pb.xs, env):
        if abs(y) > abs(peak_y):
            peak_x, peak_y = x, y
    return DiagramSeries(
        name=name, unit=unit, governing_combo="/".join(load_types) + " (pattern)",
        peak_x=peak_x, peak_y=peak_y, points=points,
    )


def _deflection_diagram_series(name, unit, load_types, total_length, loads, section, material, support_positions):
    active = _filter(loads, load_types)
    # Solve the deflected shape ONCE (a single FEM solve returns the full
    # sampled shape) rather than re-solving per diagram point.
    xs, ys = beam_mod.deflection_shape(total_length, active, material.E, section.I, support_positions)
    points = [DiagramPoint(x=x, y=y) for x, y in zip(xs, ys)]
    peak_x = 0.0
    peak_y = 0.0
    for x, y in zip(xs, ys):
        if abs(y) > abs(peak_y):
            peak_x = x
            peak_y = y
    return DiagramSeries(name=name, unit=unit, governing_combo="/".join(load_types), peak_x=peak_x, peak_y=peak_y, points=points)


def _combo_summaries(total_length, loads, combinations, support_positions):
    summaries = []
    for combo in combinations:
        active = _filter(loads, combo.load_types)
        r = beam_mod.analyze(total_length, active, support_positions=support_positions)
        summaries.append(ComboSummary(
            name=combo.name, cd=combo.cd,
            reactions=r.reactions,
            v_max=r.v_max, v_max_x=r.v_max_x,
            m_max=r.m_max, m_max_x=r.m_max_x,
        ))
    return summaries


def _governing_bending(total_length, loads, section, material, cf, cr, combinations, support_positions, unbraced_length=None, glulam_cv=None):
    # The beam stability factor CL (NDS 3.3.3) reduces Fb when the
    # compression edge is not continuously braced. CL depends on Fb* (which
    # includes the per-combination CD), so it is evaluated inside the combo
    # loop; the stability data of the governing combination is returned for
    # the report. Geometry-only quantities (le, RB) are identical across
    # combinations. Emin (the reference modulus for stability) drives FbE.
    #
    # For glulam, `cf` is 1.0 and the volume factor CV (glulam_cv) is
    # applied as the LESSER of CV and CL, not simultaneously (NDS 5.3.6);
    # Fb* deliberately excludes CV so CL is computed on the same basis.
    best = None
    best_stability = None
    for combo in combinations:
        active = _filter(loads, combo.load_types)
        results = beam_mod.analyze(total_length, active, support_positions=support_positions)
        m_in_lb = abs(results.m_max) * 12
        fb = m_in_lb / section.S
        fb_star = material.Fb * cf * cr * combo.cd
        stability = beam_stability_factor(unbraced_length, section.d, section.b, material.Emin, fb_star)
        bending_factor = min(glulam_cv, stability.cl) if glulam_cv is not None else stability.cl
        fb_allow = fb_star * bending_factor
        ratio = fb / fb_allow
        if best is None or ratio > best.ratio:
            best = CheckResult("Bending", fb, fb_allow, ratio, combo.name, ratio <= 1.0)
            best_stability = stability
    if best_stability and best_stability.over_slender:
        # RB > 50 is prohibited by NDS 3.3.3.7 regardless of the stress
        # ratio. Force a loud, unmistakable failure (same pattern as a
        # net-uplift bearing check) instead of reporting a value that
        # could be misread as adequate.
        best = CheckResult(
            f"Bending -- RB = {best_stability.rb:.0f} EXCEEDS NDS SLENDERNESS LIMIT OF 50: "
            "more lateral bracing of the compression edge or a wider member is required",
            demand=best.demand, capacity=best.capacity, ratio=max(best.ratio, 999.0),
            governing_combo=best.governing_combo, passed=False,
        )
    return best, best_stability


def _governing_shear(total_length, loads, section, material, combinations, support_positions, notch_factor=1.0, notch_label=""):
    # A tension-side end notch concentrates shear stress at the re-entrant
    # corner. Per NDS 3.4.3.2(a) the notched-end shear stress is
    # fv = (3V)/(2 b dn) x (d/dn), i.e. the full-section fv magnified by
    # (d/dn)^2. That is applied here as an equivalent capacity reduction
    # notch_factor = (dn/d)^2, evaluated at the maximum-shear section.
    best = None
    name = "Shear" + (f" (end notch: {notch_label})" if notch_factor < 1.0 else "")
    for combo in combinations:
        active = _filter(loads, combo.load_types)
        results = beam_mod.analyze(total_length, active, support_positions=support_positions)
        fv = 1.5 * abs(results.v_max) / section.A
        fv_allow = material.Fv * combo.cd * notch_factor
        ratio = fv / fv_allow if fv_allow else 999.0
        if best is None or ratio > best.ratio:
            best = CheckResult(name, fv, fv_allow, ratio, combo.name, ratio <= 1.0)
    return best


def _governing_bending_shear_pattern(
    pb, section, material, cf, cr, combinations, unbraced_length, glulam_cv, notch_factor, notch_label,
):
    """Governing bending and shear for a CONTINUOUS (multi-span) beam, using
    the pattern (skip) live-load envelope (IBC 1607.12 / ASCE 7). The design
    moment and shear are the worst over all live-load patterns -- not just
    all spans loaded -- assembled by superposition from the pre-solved
    ``PatternedBeam`` (no per-combination re-solving).
    """
    best_b = best_stability = best_v = None
    v_name = "Shear" + (f" (end notch: {notch_label})" if notch_factor < 1.0 else "")
    for combo in combinations:
        _, m_up, m_lo, v_up, v_lo = pb.moment_shear_envelope(combo.load_types)
        # Bending: design moment = worst |M| over all patterns.
        m_in_lb = pattern_mod.peak_abs(m_up, m_lo) * 12
        fb = m_in_lb / section.S
        fb_star = material.Fb * cf * cr * combo.cd
        stability = beam_stability_factor(unbraced_length, section.d, section.b, material.Emin, fb_star)
        bending_factor = min(glulam_cv, stability.cl) if glulam_cv is not None else stability.cl
        fb_allow = fb_star * bending_factor
        b_ratio = fb / fb_allow
        if best_b is None or b_ratio > best_b.ratio:
            best_b = CheckResult("Bending", fb, fb_allow, b_ratio, combo.name, b_ratio <= 1.0)
            best_stability = stability
        # Shear: design shear = worst |V| over all patterns.
        fv = 1.5 * pattern_mod.peak_abs(v_up, v_lo) / section.A
        fv_allow = material.Fv * combo.cd * notch_factor
        v_ratio = fv / fv_allow if fv_allow else 999.0
        if best_v is None or v_ratio > best_v.ratio:
            best_v = CheckResult(v_name, fv, fv_allow, v_ratio, combo.name, v_ratio <= 1.0)
    if best_stability and best_stability.over_slender:
        best_b = CheckResult(
            f"Bending -- RB = {best_stability.rb:.0f} EXCEEDS NDS SLENDERNESS LIMIT OF 50: "
            "more lateral bracing of the compression edge or a wider member is required",
            demand=best_b.demand, capacity=best_b.capacity, ratio=max(best_b.ratio, 999.0),
            governing_combo=best_b.governing_combo, passed=False,
        )
    return best_b, best_stability, best_v


def _hole_shear_check(total_length, loads, section, material, combinations, support_positions, hole_diameter, hole_location):
    # A round hole reduces the net depth resisting shear at its location.
    # This is a conservative net-section shear check: fv = 1.5 V / (b * dn)
    # with dn = d - hole_diameter, using the shear V AT the hole (so a hole
    # in a low-shear zone near midspan is not over-penalized). Manufacturer
    # hole charts for engineered lumber may permit larger holes; this is a
    # simplified rational check, not those tables.
    net_depth = section.d - hole_diameter
    loc_label = f"at {hole_location:.2f} ft" if hole_location is not None else "at max shear"
    name = f"Shear at hole (dia {hole_diameter:.2f} in, {loc_label})"
    if net_depth <= 0:
        return CheckResult(
            name + " -- hole diameter exceeds member depth",
            demand=hole_diameter, capacity=0.0, ratio=999.0,
            governing_combo="-", passed=False,
        )
    net_area = section.b * net_depth
    best = None
    for combo in combinations:
        active = _filter(loads, combo.load_types)
        if hole_location is not None:
            reactions = beam_mod._reactions(total_length, active, support_positions=support_positions)
            v = beam_mod.shear_at(
                hole_location, active, total_length=total_length, side="plus",
                support_positions=support_positions, reactions=reactions,
            )
        else:
            v = beam_mod.analyze(total_length, active, support_positions=support_positions).v_max
        fv = 1.5 * abs(v) / net_area
        fv_allow = material.Fv * combo.cd
        ratio = fv / fv_allow
        if best is None or ratio > best.ratio:
            best = CheckResult(name, fv, fv_allow, ratio, combo.name, ratio <= 1.0)
    return best


def _bearing_check(total_length, loads, section, material, bearing_length, support_index, support_positions):
    # Compression perpendicular to grain is not adjusted by CD (NDS
    # Table 4.3.1 footnote), so bearing uses the full, unfactored
    # reaction rather than a per-combination one.
    results = beam_mod.analyze(total_length, loads, support_positions=support_positions)
    reaction = results.reactions[support_index]
    label = f"Bearing (support B{support_index + 1})"

    if reaction < 0:
        # A cantilever/overhang can pull the OTHER support into net
        # uplift (e.g. a heavy point load out on the overhang tip).
        # That's a hold-down/connector capacity problem, not a bearing
        # (compression) problem, and this tool doesn't check it. Fail
        # loudly and unmistakably rather than report a meaningless
        # negative bearing ratio that could be misread as "passing."
        return CheckResult(
            label + " -- NET UPLIFT: hold-down hardware required, not checked by this tool",
            # ratio is a large finite sentinel (not inf/nan) so it sorts
            # as governing and reads clearly as failed everywhere this
            # gets formatted (templates, CSV, PDF) without float-inf
            # edge cases in those paths.
            demand=abs(reaction), capacity=0.0, ratio=999.0,
            governing_combo=_present_load_label(loads), passed=False,
            required_length=None,
        )

    cb = bearing_area_factor(bearing_length)
    fc_perp = reaction / (section.b * bearing_length)
    fc_perp_allow = material.Fc_perp * cb
    ratio = fc_perp / fc_perp_allow
    required_length = required_bearing_length(reaction, section.b, material.Fc_perp)
    return CheckResult(
        label, fc_perp, fc_perp_allow, ratio, _present_load_label(loads), ratio <= 1.0,
        required_length=required_length,
    )


def _back_span_deflection_check(total_length, loads, section, material, load_types, limit_denominator, label, x1, x2, support_positions):
    active = _filter(loads, load_types)
    back_span = x2 - x1
    delta = beam_mod.max_deflection_between(total_length, active, material.E, section.I, x1, x2, support_positions)
    allow = (back_span * 12) / limit_denominator
    ratio = delta / allow
    return CheckResult(label, delta, allow, ratio, "/".join(load_types), ratio <= 1.0)


def _total_deflection_check(total_length, loads, section, material, total_limit, label, x1, x2, support_positions, creep_factor):
    all_types = ("dead", "live", "snow", "roof_live", "wind")
    active = _filter(loads, all_types)
    back_span = x2 - x1
    delta = beam_mod.max_deflection_between(total_length, active, material.E, section.I, x1, x2, support_positions)
    combo = "D+L+S+Lr+W"
    if creep_factor > 1.0:
        # NDS 3.5.2 long-term deflection amplifies the SUSTAINED (dead)
        # portion by Kcr. The elastic total already includes the immediate
        # dead deflection, so add (Kcr - 1) x the dead-only deflection.
        dead = _filter(loads, ("dead",))
        delta_dead = beam_mod.max_deflection_between(total_length, dead, material.E, section.I, x1, x2, support_positions)
        delta = delta + (creep_factor - 1.0) * delta_dead
        label = label + f" (long-term, Kcr={creep_factor:g})"
        combo = "Kcr*D + L+S+Lr+W"
    allow = (back_span * 12) / total_limit
    ratio = delta / allow
    return CheckResult(label, delta, allow, ratio, combo, ratio <= 1.0)


def _span_deflection_checks(total_length, loads, section, material, live_limit, total_limit, support_positions, creep_factor=1.0, pb=None):
    present = _transient_load_types_present(loads)
    labels = {"live": "Live", "snow": "Snow", "roof_live": "Roof live", "wind": "Wind"}
    live_name = "/".join(labels[t] for t in present) + "-load deflection"
    live_checks = []
    total_checks = []

    if pb is not None:
        # Continuous beam: the worst downward deflection in each span occurs
        # under the pattern that loads that span's live load (and alternate
        # spans), which full-span loading under-predicts. Assembled from the
        # pre-solved elementary load cases -- no re-solving here.
        total_types = ("dead", "live", "snow", "roof_live", "wind")
        dead = _filter(loads, ("dead",))
        for i, (x1, x2) in enumerate(zip(support_positions, support_positions[1:])):
            span_label = f" (B{i + 1}-B{i + 2})" if len(support_positions) > 2 else ""
            back_span = x2 - x1
            live_delta = pb.max_downward_between(present, x1, x2)
            live_allow = (back_span * 12) / live_limit
            live_checks.append(CheckResult(
                live_name + span_label, live_delta, live_allow,
                live_delta / live_allow, "/".join(present) + " (pattern)", live_delta <= live_allow))
            total_delta = pb.max_downward_between(total_types, x1, x2)
            total_label = "Total-load deflection" + span_label
            total_combo = "D+L+S+Lr+W (pattern)"
            if creep_factor > 1.0:
                delta_dead = beam_mod.max_deflection_between(
                    total_length, dead, material.E, section.I, x1, x2, support_positions)
                total_delta += (creep_factor - 1.0) * delta_dead
                total_label += f" (long-term, Kcr={creep_factor:g})"
                total_combo = "Kcr*D + L+S+Lr+W (pattern)"
            total_allow = (back_span * 12) / total_limit
            total_checks.append(CheckResult(
                total_label, total_delta, total_allow, total_delta / total_allow,
                total_combo, total_delta <= total_allow))
    else:
        for i, (x1, x2) in enumerate(zip(support_positions, support_positions[1:])):
            span_label = f" (B{i + 1}-B{i + 2})" if len(support_positions) > 2 else ""
            live_checks.append(_back_span_deflection_check(
                total_length, loads, section, material, present, live_limit,
                live_name + span_label, x1, x2, support_positions,
            ))
            total_checks.append(_total_deflection_check(
                total_length, loads, section, material, total_limit,
                "Total-load deflection" + span_label, x1, x2, support_positions, creep_factor,
            ))
    live_checks.sort(key=lambda c: c.ratio, reverse=True)
    total_checks.sort(key=lambda c: c.ratio, reverse=True)
    return live_checks, total_checks


# Effective span used for a cantilever tip's allowable-deflection
# denominator: 2x the overhang length, per common wood-engineering
# practice (a cantilever tip deflects similarly to the end of half of a
# simple span twice as long). IRC R301.7 doesn't address cantilevers
# directly, so this is a widely used convention, not a code citation --
# flagged clearly in the report rather than presented as a code value.
CANTILEVER_EFFECTIVE_SPAN_FACTOR = 2.0


def _transient_cantilever_deflection_check(total_length, loads, section, material, support_positions, side, overhang, limit_denominator, pb=None):
    present = _transient_load_types_present(loads)
    labels = {"live": "Live", "snow": "Snow", "roof_live": "Roof live", "wind": "Wind"}
    label = "/".join(labels[t] for t in present) + f"-load deflection ({side} cantilever tip)"
    return _cantilever_deflection_check(
        total_length, loads, section, material, present, support_positions, side, overhang, limit_denominator, label, pb,
    )


def _cantilever_deflection_check(total_length, loads, section, material, load_types, support_positions, side, overhang, limit_denominator, label, pb=None):
    active = _filter(loads, load_types)
    if pb is not None:
        delta = pb.tip_deflection(load_types, side)
        combo = "/".join(load_types) + " (pattern)"
    else:
        delta = beam_mod.tip_deflection(
            total_length, active, material.E, section.I, side=side, support_positions=support_positions,
        )
        combo = "/".join(load_types)
    effective_span_in = CANTILEVER_EFFECTIVE_SPAN_FACTOR * overhang * 12
    allow = effective_span_in / limit_denominator
    ratio = delta / allow
    return CheckResult(label, delta, allow, ratio, combo, ratio <= 1.0)
