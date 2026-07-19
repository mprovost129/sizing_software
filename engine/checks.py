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
from dataclasses import dataclass, field

from . import beam as beam_mod
from .factors import (
    LOAD_DURATION_FACTORS,
    REPETITIVE_MEMBER_FACTOR,
    SIZE_FACTORS_FB,
    bearing_area_factor,
    required_bearing_length,
)
from .loads import PointLoad, UniformLoad
from .materials import Material
from .sections import Section
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
    fb_base: float
    fv_base: float
    fc_perp_base: float
    e: float
    cf: float
    cr: float
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

    cf = SIZE_FACTORS_FB.get(section.nominal, 1.0)
    cr = REPETITIVE_MEMBER_FACTOR if repetitive else 1.0
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
            A=section.A, I=section.I, S=section.S,
        ),
        material_name=material.name,
        fb_base=material.Fb,
        fv_base=material.Fv,
        fc_perp_base=material.Fc_perp,
        e=material.E,
        cf=cf,
        cr=cr,
        bearing_length_left=bearing_lengths[0],
        bearing_length_right=bearing_lengths[-1],
        cb_left=bearing_area_factor(bearing_lengths[0]),
        cb_right=bearing_area_factor(bearing_lengths[-1]),
        deflection_limit_live=deflection_limit_live,
        deflection_limit_total=deflection_limit_total,
        cantilever_deflection_limit_live=cantilever_deflection_limit_live,
        cantilever_deflection_limit_total=cantilever_deflection_limit_total,
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

    bending = _governing_bending(total_length, loads, section, material, cf, cr, combinations, support_positions)
    shear = _governing_shear(total_length, loads, section, material, combinations, support_positions)
    bearing_checks = [
        _bearing_check(total_length, loads, section, material, length, i, support_positions)
        for i, length in enumerate(bearing_lengths)
    ]
    live_checks, total_checks = _span_deflection_checks(
        total_length, loads, section, material,
        deflection_limit_live, deflection_limit_total, support_positions,
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

    if left_overhang > 0:
        result.deflection_left_cantilever_live = _transient_cantilever_deflection_check(
            total_length, loads, section, material,
            support_positions, "left", left_overhang, cantilever_deflection_limit_live,
        )
        result.deflection_left_cantilever_total = _cantilever_deflection_check(
            total_length, loads, section, material, ("dead", "live", "snow", "roof_live", "wind"),
            support_positions, "left", left_overhang, cantilever_deflection_limit_total,
            "Total-load deflection (left cantilever tip)",
        )
    if right_overhang > 0:
        result.deflection_right_cantilever_live = _transient_cantilever_deflection_check(
            total_length, loads, section, material,
            support_positions, "right", right_overhang, cantilever_deflection_limit_live,
        )
        result.deflection_right_cantilever_total = _cantilever_deflection_check(
            total_length, loads, section, material, ("dead", "live", "snow", "roof_live", "wind"),
            support_positions, "right", right_overhang, cantilever_deflection_limit_total,
            "Total-load deflection (right cantilever tip)",
        )

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


def _governing_bending(total_length, loads, section, material, cf, cr, combinations, support_positions):
    best = None
    for combo in combinations:
        active = _filter(loads, combo.load_types)
        results = beam_mod.analyze(total_length, active, support_positions=support_positions)
        m_in_lb = abs(results.m_max) * 12
        fb = m_in_lb / section.S
        fb_allow = material.Fb * cf * cr * combo.cd
        ratio = fb / fb_allow
        if best is None or ratio > best.ratio:
            best = CheckResult("Bending", fb, fb_allow, ratio, combo.name, ratio <= 1.0)
    return best


def _governing_shear(total_length, loads, section, material, combinations, support_positions):
    best = None
    for combo in combinations:
        active = _filter(loads, combo.load_types)
        results = beam_mod.analyze(total_length, active, support_positions=support_positions)
        fv = 1.5 * abs(results.v_max) / section.A
        fv_allow = material.Fv * combo.cd
        ratio = fv / fv_allow
        if best is None or ratio > best.ratio:
            best = CheckResult("Shear", fv, fv_allow, ratio, combo.name, ratio <= 1.0)
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


def _span_deflection_checks(total_length, loads, section, material, live_limit, total_limit, support_positions):
    present = _transient_load_types_present(loads)
    labels = {"live": "Live", "snow": "Snow", "roof_live": "Roof live", "wind": "Wind"}
    live_name = "/".join(labels[t] for t in present) + "-load deflection"
    live_checks = []
    total_checks = []
    for i, (x1, x2) in enumerate(zip(support_positions, support_positions[1:])):
        span_label = f" (B{i + 1}-B{i + 2})" if len(support_positions) > 2 else ""
        live_checks.append(_back_span_deflection_check(
            total_length, loads, section, material, present, live_limit,
            live_name + span_label, x1, x2, support_positions,
        ))
        total_checks.append(_back_span_deflection_check(
            total_length, loads, section, material, ("dead", "live", "snow", "roof_live", "wind"),
            total_limit, "Total-load deflection" + span_label, x1, x2, support_positions,
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


def _transient_cantilever_deflection_check(total_length, loads, section, material, support_positions, side, overhang, limit_denominator):
    present = _transient_load_types_present(loads)
    labels = {"live": "Live", "snow": "Snow", "roof_live": "Roof live", "wind": "Wind"}
    label = "/".join(labels[t] for t in present) + f"-load deflection ({side} cantilever tip)"
    return _cantilever_deflection_check(
        total_length, loads, section, material, present, support_positions, side, overhang, limit_denominator, label,
    )


def _cantilever_deflection_check(total_length, loads, section, material, load_types, support_positions, side, overhang, limit_denominator, label):
    active = _filter(loads, load_types)
    delta = beam_mod.tip_deflection(
        total_length, active, material.E, section.I, side=side, support_positions=support_positions,
    )
    effective_span_in = CANTILEVER_EFFECTIVE_SPAN_FACTOR * overhang * 12
    allow = effective_span_in / limit_denominator
    ratio = delta / allow
    return CheckResult(label, delta, allow, ratio, "/".join(load_types), ratio <= 1.0)
