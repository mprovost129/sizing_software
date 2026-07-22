"""Dowel-type fastener lateral design (NDS 2018 Chapter 12).

The reference lateral design value Z of a single dowel (bolt, lag screw,
nail, or screw) is the minimum of the six yield-limit equations, each of
which represents a failure mode (wood crushing, fastener bending, or a
combination). Dowel bearing strengths come from the connected members'
specific gravities -- the same G values carried in engine/materials.py.

Scope (MVP): single-shear, two-member connections; parallel- or
perpendicular-to-grain loading (Hankinson angles between the two are a
future addition). Group action Cg, geometry CDelta, and the other
connection adjustment factors are not yet applied -- only load duration
CD -- so results are the single-fastener reference value, flagged as such.
"""
import math
from dataclasses import dataclass

YIELD_MODES = ("Im", "Is", "II", "IIIm", "IIIs", "IV")


def dowel_bearing_strength(specific_gravity: float, diameter: float, perpendicular: bool = False) -> float:
    """Dowel bearing strength Fe (psi), NDS 12.3.3. Small-diameter dowels
    (D < 0.25 in: nails, most screws) have no grain-angle dependence;
    larger dowels (bolts, lag screws) differ parallel vs perpendicular."""
    g = specific_gravity
    if diameter < 0.25:
        return 16600 * g ** 1.84
    if perpendicular:
        return 6100 * g ** 1.45 / math.sqrt(diameter)
    return 11200 * g


def _reduction_term(diameter: float, mode: str, angle_deg: float) -> float:
    """Rd, NDS Table 12.3.1B. For D <= 0.25 in it is Kd; for larger dowels
    it depends on the yield mode and the maximum load-to-grain angle."""
    if diameter <= 0.25:
        return 2.2 if diameter <= 0.17 else (10.0 * diameter + 0.5)
    k_theta = 1.0 + 0.25 * (angle_deg / 90.0)
    if mode in ("Im", "Is"):
        return 4.0 * k_theta
    if mode == "II":
        return 3.6 * k_theta
    return 3.2 * k_theta  # III and IV


@dataclass
class DowelYield:
    z: float                 # reference lateral design value, lb
    mode: str                # governing yield mode
    mode_values: dict        # every mode -> Z (lb)
    fem: float               # main-member dowel bearing strength, psi
    fes: float               # side-member dowel bearing strength, psi
    re: float                # Fem / Fes
    rt: float                # lm / ls


def single_shear_z(diameter: float, fyb: float, lm: float, ls: float, fem: float, fes: float, angle_deg: float = 0.0) -> DowelYield:
    """Reference lateral design value Z for a single dowel in single shear,
    the minimum of the six NDS 12.3.1 yield-limit equations. ``lm``/``ls``
    are the main/side dowel bearing lengths (in), ``fyb`` the fastener
    bending yield strength (psi), ``angle_deg`` the maximum load-to-grain
    angle (for Rd on larger dowels)."""
    d = diameter
    re = fem / fes
    rt = lm / ls
    k1 = (math.sqrt(re + 2 * re ** 2 * (1 + rt + rt ** 2) + rt ** 2 * re ** 3) - re * (1 + rt)) / (1 + re)
    k2 = -1 + math.sqrt(2 * (1 + re) + (2 * fyb * (1 + 2 * re) * d ** 2) / (3 * fem * lm ** 2))
    k3 = -1 + math.sqrt(2 * (1 + re) / re + (2 * fyb * (2 + re) * d ** 2) / (3 * fem * ls ** 2))

    def rd(mode):
        return _reduction_term(d, mode, angle_deg)

    values = {
        "Im": d * lm * fem / rd("Im"),
        "Is": d * ls * fes / rd("Is"),
        "II": k1 * d * ls * fes / rd("II"),
        "IIIm": k2 * d * lm * fem / ((1 + 2 * re) * rd("IIIm")),
        "IIIs": k3 * d * ls * fem / ((2 + re) * rd("IIIs")),
        "IV": (d ** 2 / rd("IV")) * math.sqrt(2 * fem * fyb / (3 * (1 + re))),
    }
    mode = min(values, key=values.get)
    return DowelYield(z=values[mode], mode=mode, mode_values=values, fem=fem, fes=fes, re=re, rt=rt)


def group_action_factor(n: int, spacing: float, diameter: float, ea_main: float, ea_side: float, gamma: float | None = None) -> float:
    """Group action factor Cg, NDS 2018 Eq. 11.3-1, for a row of ``n``
    fasteners at center-to-center ``spacing`` (in). ``ea_main``/``ea_side``
    are the members' axial stiffnesses E*A (lb). ``gamma`` is the load/slip
    modulus (default 180,000*D^1.5 for wood-to-wood dowels). Cg <= 1.0."""
    if n <= 1:
        return 1.0
    if gamma is None:
        gamma = 180000 * diameter ** 1.5
    u = 1.0 + gamma * (spacing / 2.0) * (1.0 / ea_main + 1.0 / ea_side)
    m = u - math.sqrt(u * u - 1.0)
    rea = min(ea_side / ea_main, ea_main / ea_side)
    mn = m ** n
    m2n = mn * mn
    numerator = m * (1.0 - m2n)
    denominator = n * ((1.0 + rea * mn) * (1.0 + m) - 1.0 + m2n)
    cg = (numerator / denominator) * ((1.0 + rea) / (1.0 - m))
    return min(cg, 1.0)


def geometry_factor(diameter: float, end_distance: float | None, spacing: float | None) -> float:
    """Geometry factor CDelta, NDS 2018 Section 12.5.1, for parallel-to-grain
    tension loading of larger dowels (D >= 0.25 in). It is the smaller of the
    end-distance factor (full at 7D, reduced floor at 3.5D) and the in-row
    spacing factor (full at 4D, reduced floor at 3D). Below the reduced
    minimum the connection is not permitted (returns 0.0). Small-diameter
    dowels (nails/screws) are not reduced here (CDelta = 1.0)."""
    if diameter < 0.25:
        return 1.0
    c_end = 1.0
    if end_distance is not None and end_distance > 0:
        if end_distance < 3.5 * diameter:
            return 0.0
        c_end = min(1.0, end_distance / (7.0 * diameter))
    c_spacing = 1.0
    if spacing is not None and spacing > 0:
        if spacing < 3.0 * diameter:
            return 0.0
        c_spacing = min(1.0, spacing / (4.0 * diameter))
    return min(c_end, c_spacing)


def wet_service_factor(fastener_type: str, wet: bool, withdrawal: bool = False) -> float:
    """Wet service factor CM for connections, NDS 2018 Table 11.3.3, for
    members that are wet in service (moisture content >= 19%). Dry service
    returns 1.0. Laterally loaded dowel-type fasteners take CM = 0.7.
    Withdrawal takes CM = 0.25 for nails/spikes and 0.7 for lag/wood screws.
    (Assumes the wood is dry at time of fabrication; the additional
    wet-at-fabrication reductions for multiple fasteners are not modeled.)"""
    if not wet:
        return 1.0
    if withdrawal:
        return 0.25 if fastener_type in ("nail", "spike") else 0.7
    return 0.7


def toe_nail_factor(fastener_type: str, toe_nail: bool, withdrawal: bool = False) -> float:
    """Toe-nail factor Ctn, NDS 2018 Section 12.5.4, for nails or spikes
    driven at an angle to the grain (toe-nailed): Ctn = 0.83 for lateral
    loading and 0.67 for withdrawal. Only nails and spikes qualify;
    other fasteners or non-toe-nailed connections return 1.0."""
    if not toe_nail or fastener_type not in ("nail", "spike"):
        return 1.0
    return 0.67 if withdrawal else 0.83


def temperature_factor(temperature: str, wet: bool) -> float:
    """Temperature factor Ct for connections, NDS 2018 Table 11.3.4, for
    fasteners subject to sustained elevated temperatures. ``temperature``
    is "normal" (T <= 100F, Ct = 1.0), "warm" (100F < T <= 125F), or
    "hot" (125F < T <= 150F); the reduction is larger when wet in service."""
    if temperature == "warm":
        return 0.7 if wet else 0.8
    if temperature == "hot":
        return 0.5 if wet else 0.7
    return 1.0


def double_shear_z(diameter: float, fyb: float, lm: float, ls: float, fem: float, fes: float, angle_deg: float = 0.0) -> DowelYield:
    """Reference lateral design value Z for a single dowel in DOUBLE shear
    (a symmetric three-member connection: one main/middle member of
    thickness ``lm`` between two side members of thickness ``ls`` each).
    Per NDS 12.3.1 only four yield modes apply -- Im, Is, IIIs, IV -- and
    the Is/IIIs/IV values carry the factor of 2 for the two shear planes.
    """
    d = diameter
    re = fem / fes
    rt = lm / ls
    k3 = -1 + math.sqrt(2 * (1 + re) / re + (2 * fyb * (2 + re) * d ** 2) / (3 * fem * ls ** 2))

    def rd(mode):
        return _reduction_term(d, mode, angle_deg)

    values = {
        "Im": d * lm * fem / rd("Im"),
        "Is": 2 * d * ls * fes / rd("Is"),
        "IIIs": 2 * k3 * d * ls * fem / ((2 + re) * rd("IIIs")),
        "IV": 2 * (d ** 2 / rd("IV")) * math.sqrt(2 * fem * fyb / (3 * (1 + re))),
    }
    mode = min(values, key=values.get)
    return DowelYield(z=values[mode], mode=mode, mode_values=values, fem=fem, fes=fes, re=re, rt=rt)


@dataclass
class ConnectionResult:
    z: float                 # single-fastener reference value Z, lb
    z_adjusted: float        # Z' = Z * CD * CM * Ct * Ctn * Cg * CDelta, lb
    capacity: float          # n * Z', lb
    demand: float            # applied lateral load, lb
    ratio: float
    passed: bool
    mode: str
    yield_result: DowelYield
    cd: float
    cg: float
    c_delta: float
    cm: float                # wet service factor (NDS Table 11.3.3)
    ctn: float               # toe-nail factor (NDS 12.5.4)
    ct: float                # temperature factor (NDS Table 11.3.4)
    n_fasteners: int
    perpendicular: bool
    double_shear: bool = False


def withdrawal_value(fastener_type: str, specific_gravity: float, diameter: float) -> float:
    """Reference withdrawal design value W (lb per inch of penetration),
    NDS 2018 Section 12.2. Nails/spikes W = 1380 G^2.5 D; wood screws
    W = 2850 G^2 D; lag screws W = 1800 G^1.5 D^0.75. Bolts are not
    designed for withdrawal (returns 0.0)."""
    g = specific_gravity
    d = diameter
    if fastener_type == "lag":
        return 1800 * g ** 1.5 * d ** 0.75
    if fastener_type == "screw":
        return 2850 * g ** 2 * d
    if fastener_type in ("nail", "spike"):
        return 1380 * g ** 2.5 * d
    return 0.0  # bolts: withdrawal not applicable


@dataclass
class WithdrawalResult:
    w_per_inch: float    # W, lb per inch of penetration
    penetration: float   # in
    w_single: float      # W * penetration, lb per fastener (unadjusted)
    w_adjusted: float    # W' = W * penetration * CD, lb per fastener
    capacity: float      # n * W', lb
    demand: float
    ratio: float
    passed: bool
    applicable: bool     # False for bolts (no withdrawal design value)
    fastener_type: str
    cd: float
    cm: float            # wet service factor (NDS Table 11.3.3)
    ctn: float           # toe-nail factor (NDS 12.5.4)
    ct: float            # temperature factor (NDS Table 11.3.4)
    n_fasteners: int


def design_withdrawal(
    fastener_type: str,
    specific_gravity: float,
    diameter: float,
    penetration: float,
    load_lb: float,
    cd: float = 1.0,
    n_fasteners: int = 1,
    wet: bool = False,
    toe_nail: bool = False,
    temperature: str = "normal",
) -> WithdrawalResult:
    """Design a fastener group loaded in withdrawal (axial). ``penetration``
    is the embedment length in the holding (main) member, in. Load duration
    CD, the wet service factor CM (when ``wet``), the toe-nail factor
    Ctn = 0.67 (when ``toe_nail`` for nails/spikes), and the temperature
    factor Ct (when ``temperature`` is elevated) are applied."""
    w = withdrawal_value(fastener_type, specific_gravity, diameter)
    applicable = w > 0
    cm = wet_service_factor(fastener_type, wet, withdrawal=True)
    ctn = toe_nail_factor(fastener_type, toe_nail, withdrawal=True)
    ct = temperature_factor(temperature, wet)
    w_single = w * penetration
    w_adjusted = w_single * cd * cm * ctn * ct
    capacity = n_fasteners * w_adjusted
    ratio = (load_lb / capacity if capacity else 999.0) if applicable else 999.0
    return WithdrawalResult(
        w_per_inch=w, penetration=penetration, w_single=w_single, w_adjusted=w_adjusted,
        capacity=capacity, demand=load_lb, ratio=ratio, passed=applicable and ratio <= 1.0,
        applicable=applicable, fastener_type=fastener_type, cd=cd, cm=cm, ctn=ctn, ct=ct,
        n_fasteners=n_fasteners,
    )


def design_connection(
    diameter: float,
    fyb: float,
    main_thickness: float,
    side_thickness: float,
    main_specific_gravity: float,
    side_specific_gravity: float,
    load_lb: float,
    cd: float = 1.0,
    n_fasteners: int = 1,
    perpendicular: bool = False,
    angle_deg: float = 0.0,
    spacing: float | None = None,
    end_distance: float | None = None,
    ea_main: float | None = None,
    ea_side: float | None = None,
    double_shear: bool = False,
    wet: bool = False,
    fastener_type: str = "",
    toe_nail: bool = False,
    temperature: str = "normal",
) -> ConnectionResult:
    """Design a single-shear dowel connection for an applied lateral load.
    ``main_thickness``/``side_thickness`` are the member dowel bearing
    lengths (in). If ``spacing`` and the member axial stiffnesses
    ``ea_main``/``ea_side`` (E*A) are given, the group action factor Cg is
    applied; if ``end_distance``/``spacing`` are given, the geometry factor
    CDelta is applied. Otherwise those default to 1.0. Load duration CD
    always applies; the wet service factor CM when ``wet``; the toe-nail
    factor Ctn = 0.83 when ``toe_nail`` and ``fastener_type`` is a nail/spike;
    and the temperature factor Ct when ``temperature`` is elevated."""
    fem = dowel_bearing_strength(main_specific_gravity, diameter, perpendicular)
    fes = dowel_bearing_strength(side_specific_gravity, diameter, perpendicular)
    yield_fn = double_shear_z if double_shear else single_shear_z
    yld = yield_fn(diameter, fyb, main_thickness, side_thickness, fem, fes, angle_deg)

    cg = 1.0
    if spacing and ea_main and ea_side and n_fasteners > 1:
        cg = group_action_factor(n_fasteners, spacing, diameter, ea_main, ea_side)
    c_delta = geometry_factor(diameter, end_distance, spacing) if (spacing or end_distance) else 1.0
    cm = wet_service_factor("", wet, withdrawal=False)
    ctn = toe_nail_factor(fastener_type, toe_nail, withdrawal=False)
    ct = temperature_factor(temperature, wet)

    z_adjusted = yld.z * cd * cm * ctn * ct * cg * c_delta
    capacity = n_fasteners * z_adjusted
    ratio = load_lb / capacity if capacity else 999.0
    return ConnectionResult(
        z=yld.z, z_adjusted=z_adjusted, capacity=capacity, demand=load_lb, ratio=ratio,
        passed=ratio <= 1.0, mode=yld.mode, yield_result=yld, cd=cd, cg=cg, c_delta=c_delta,
        cm=cm, ctn=ctn, ct=ct, n_fasteners=n_fasteners, perpendicular=perpendicular,
        double_shear=double_shear,
    )
