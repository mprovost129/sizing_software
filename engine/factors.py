"""NDS wood design adjustment factors.

Source references:
  - Load duration (CD):      NDS 2018 Table 2.3.2
  - Size factor (CF):        NDS Supplement 2018 Table 4A footnote
                             (Select Structural / No.1 / No.2 / No.3,
                              2"-4" thick, edgewise bending)
  - Repetitive member (Cr): NDS 2018 Section 4.3.9 / Table 4A note
  - Wet service (CM):        NDS 2018 Supplement Table 4A footnote
  - Beam stability (CL):     NDS 2018 Section 3.3.3
  - Bearing area (Cb):       NDS 2018 Section 3.10.4
  - Deflection limits:       IRC 2021 Table R301.7

Factors NOT yet implemented (out of scope for sawn-lumber MVP):
  Ct (temperature), Ci (incising),
  CT (buckling stiffness for trusses).
"""
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Load duration factor, CD
# NDS Table 2.3.2. Applies to all strength values except Fc_perp.
# ---------------------------------------------------------------------------
LOAD_DURATION_FACTORS: dict[str, float] = {
    "dead": 0.9,       # permanent / sustained load
    "live": 1.0,       # occupancy live load (10-year reference)
    "snow": 1.15,      # snow (2-month duration)
    "roof_live": 1.25, # roof live / short-duration construction-type loading
    "wind": 1.6,       # wind / impact-type short duration
}

# ---------------------------------------------------------------------------
# Size factor for Fb, CF
# NDS Supplement Table 4A footnote -- Select Structural, No.1, No.2, No.3
# grades, dimension lumber 2"-4" thick, edgewise use.
# Applies to: Fb only (Ft and Fc have their own CF values not yet used).
# ---------------------------------------------------------------------------
SIZE_FACTORS_FB: dict[str, float] = {
    "2x4":  1.5,   # d = 3.5"
    "2x6":  1.3,   # d = 5.5"
    "2x8":  1.2,   # d = 7.25"
    "2x10": 1.1,   # d = 9.25"
    "2x12": 1.0,   # d = 11.25"  (CF = 1.0 per NDS-S footnote)
}

# Size factor for Fc (compression parallel to grain), NDS-S Table 4A
# footnote -- different values than the Fb size factor above. Used for
# column design. Southern Pine and engineered materials use CF = 1.0.
SIZE_FACTORS_FC: dict[str, float] = {
    "2x4":  1.15,
    "2x6":  1.1,
    "2x8":  1.05,
    "2x10": 1.0,
    "2x12": 1.0,
}

# Size factor for Ft (tension parallel to grain), per same table footnote.
# Currently tabulated but not yet applied in design checks (tension check
# not implemented). Stored here for future use.
SIZE_FACTORS_FT: dict[str, float] = {
    "2x4":  1.5,
    "2x6":  1.3,
    "2x8":  1.3,   # note: Ft CF = 1.3 for 2x8, vs Fb CF = 1.2
    "2x10": 1.2,
    "2x12": 1.1,
}

# ---------------------------------------------------------------------------
# Repetitive member factor, Cr
# NDS 2018 Section 4.3.9: applies to Fb when member spacing <= 24" o.c.,
# >= 3 members, joined by adequate load-distributing elements.
# ---------------------------------------------------------------------------
REPETITIVE_MEMBER_FACTOR: float = 1.15

# ---------------------------------------------------------------------------
# Wet service factor, CM
# NDS 2018 Supplement Table 4A adjustment factors for visually graded sawn
# dimension lumber (2"-4" thick) used where the in-service moisture content
# exceeds 19% (exterior / damp exposure). Interior, dry members use CM = 1.0.
#
# Only the factors that affect this tool's checks are modelled: Fb (bending),
# Fv (shear), Fc_perp (bearing), and E / Emin (deflection and beam
# stability). Ft and Fc (tension / compression parallel to grain) are not
# checked here. Per the Table 4A footnote, the Fb factor is 0.85 except that
# it stays 1.0 when (Fb)(CF) <= 1,150 psi, and E and Emin take 0.90.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class WetServiceFactors:
    fb: float
    fv: float
    fc_perp: float
    e: float
    emin: float


DRY_SERVICE_FACTORS = WetServiceFactors(fb=1.0, fv=1.0, fc_perp=1.0, e=1.0, emin=1.0)


def wet_service_factors(fb_base: float, cf: float) -> WetServiceFactors:
    """CM per NDS-S Table 4A for sawn dimension lumber in wet service.

    ``fb_base`` and ``cf`` are the reference bending value and its size
    factor, used only to resolve the Fb footnote: CM,Fb stays 1.0 while
    (Fb)(CF) <= 1,150 psi, otherwise it is 0.85.
    """
    return WetServiceFactors(
        fb=1.0 if fb_base * cf <= 1150.0 else 0.85,
        fv=0.97,
        fc_perp=0.67,
        e=0.90,
        emin=0.90,
    )


# ---------------------------------------------------------------------------
# Beam stability factor, CL
# NDS 2018 Section 3.3.3 (lateral-torsional buckling of bending members).
#
# When the compression edge of a bending member is not laterally supported
# throughout its length, the member can buckle sideways before reaching its
# full bending strength, so Fb is reduced by CL <= 1.0. A member whose
# compression edge is braced continuously (e.g. a floor joist under nailed
# sheathing) has CL = 1.0, and so does any member no deeper than it is wide
# (d <= b), where lateral-torsional buckling cannot occur.
#
# The effective length le is taken from NDS Table 3.3.3 for a single-span
# beam under a UNIFORMLY DISTRIBUTED load. Among the common single-span
# cases that row gives the largest le, hence the smallest (most
# conservative) CL, so it is a safe default for this tool's predominantly
# uniform loading. The report states this assumption explicitly.
# ---------------------------------------------------------------------------
RB_MAX: float = 50.0  # NDS 3.3.3.7: slenderness ratio RB must not exceed 50


@dataclass(frozen=True)
class BeamStability:
    cl: float           # beam stability factor CL (<= 1.0)
    le: float           # effective unbraced length le, in.
    rb: float           # slenderness ratio RB = sqrt(le*d / b^2)
    fbE: float          # critical buckling design value FbE, psi
    braced: bool        # True when CL is forced to 1.0 (braced, or d <= b)
    over_slender: bool  # True when RB exceeds the code limit of 50 (invalid)


def _effective_unbraced_length(lu: float, d: float) -> float:
    """le per NDS Table 3.3.3, single-span beam, uniformly distributed load."""
    ratio = lu / d
    if ratio < 7.0:
        return 2.06 * lu
    if ratio <= 14.3:
        return 1.63 * lu + 3.0 * d
    return 1.84 * lu


def glulam_volume_factor(length_ft: float, d: float, b: float, exponent: float) -> float:
    """Volume factor CV for glulam bending members, NDS 2018 Section 5.3.6:

        CV = (21/L)^(1/x) * (12/d)^(1/x) * (5.125/b)^(1/x)  <= 1.0

    with L the length between points of zero moment (ft), d the depth and b
    the width (in), referenced to 21 ft / 12 in / 5.125 in. ``exponent`` is
    1/x: 0.10 for species other than Southern Pine (x = 10), 0.05 for
    Southern Pine (x = 20). CV never exceeds 1.0. Unlike the sawn size
    factor or the LVL depth factor, CV does NOT apply simultaneously with
    the beam stability factor CL -- the caller uses the lesser of the two
    (NDS 5.3.6).
    """
    if length_ft <= 0 or d <= 0 or b <= 0:
        return 1.0
    cv = ((21.0 / length_ft) * (12.0 / d) * (5.125 / b)) ** exponent
    return min(cv, 1.0)


def beam_stability_factor(
    unbraced_length_in: float | None,
    d: float,
    b: float,
    emin: float,
    fb_star: float,
) -> BeamStability:
    """CL per NDS 3.3.3.

    ``unbraced_length_in`` is the distance between points of lateral support
    of the compression edge (lu). ``None`` or a non-positive value means the
    compression edge is continuously braced, giving CL = 1.0. ``fb_star`` is
    the reference bending value adjusted by every applicable factor EXCEPT CL
    (i.e. Fb x CD x CF x Cr for sawn lumber). ``emin`` is the reference
    modulus for stability, E_min.

    When the slenderness ratio RB exceeds the NDS limit of 50 the member is
    invalid; ``over_slender`` is flagged (rather than raising) so callers can
    surface a loud failed check the same way net-uplift bearing does.
    """
    if not unbraced_length_in or unbraced_length_in <= 0 or d <= b:
        return BeamStability(cl=1.0, le=0.0, rb=0.0, fbE=0.0, braced=True, over_slender=False)
    le = _effective_unbraced_length(unbraced_length_in, d)
    rb = (le * d / (b * b)) ** 0.5
    fbE = 1.20 * emin / (rb * rb)
    ratio = fbE / fb_star
    a = (1.0 + ratio) / 1.9
    # Discriminant a^2 - ratio/0.95 is provably positive for all ratio > 0
    # (the quadratic ratio^2 - 1.8*ratio + 1 has no real roots), so this
    # square root is always real.
    cl = a - (a * a - ratio / 0.95) ** 0.5
    return BeamStability(cl=cl, le=le, rb=rb, fbE=fbE, braced=False, over_slender=rb > RB_MAX)


# ---------------------------------------------------------------------------
# Column stability factor, CP
# NDS 2018 Section 3.7.1 (axial compression / column buckling). A column
# too slender to reach its crushing strength buckles first, so Fc is
# reduced by CP <= 1.0.
#
#   FcE = 0.822 * Emin' / (le/d)^2
#   CP  = (1 + FcE/Fc*)/(2c) - sqrt[ ((1 + FcE/Fc*)/(2c))^2 - (FcE/Fc*)/c ]
#
# where Fc* is the reference compression value times every factor except
# CP, le/d is the governing slenderness ratio, and c = 0.8 for sawn
# lumber, 0.9 for glulam and structural composite lumber (LVL). The
# slenderness ratio must not exceed 50 (NDS 3.7.1.4).
# ---------------------------------------------------------------------------
SLENDERNESS_MAX: float = 50.0


@dataclass(frozen=True)
class ColumnStability:
    cp: float           # column stability factor CP (<= 1.0)
    fce: float          # critical buckling design value FcE, psi
    slenderness: float  # governing le/d
    over_slender: bool  # True when le/d exceeds the code limit of 50


def column_stability_factor(slenderness: float, emin: float, fc_star: float, c: float) -> ColumnStability:
    """CP per NDS 3.7.1. ``slenderness`` is the governing le/d, ``fc_star``
    the reference Fc adjusted by every factor except CP, ``c`` = 0.8 for
    sawn lumber / 0.9 for glulam and LVL. The discriminant is provably
    non-negative for c in (0, 1)."""
    fce = 0.822 * emin / (slenderness * slenderness)
    alpha = fce / fc_star
    k = (1.0 + alpha) / (2.0 * c)
    cp = k - (k * k - alpha / c) ** 0.5
    return ColumnStability(cp=cp, fce=fce, slenderness=slenderness, over_slender=slenderness > SLENDERNESS_MAX)


# ---------------------------------------------------------------------------
# Bearing area factor, Cb
# NDS 2018 Section 3.10.4. Increases Fc_perp for short bearing lengths.
# Not applicable to bearing at the ends of a member.
# ---------------------------------------------------------------------------
def bearing_area_factor(bearing_length_in: float) -> float:
    """Cb per NDS 3.10.4. Returns 1.0 for bearing length >= 6 in."""
    if bearing_length_in >= 6.0:
        return 1.0
    return (bearing_length_in + 0.375) / bearing_length_in


# Code-minimum bearing length for wood/metal supports (IRC R502.6). Masonry
# or concrete requires 3 in, but this app doesn't yet collect a bearing
# surface material distinct enough from support_type to apply that --
# floor stays at the wood/metal minimum until it does.
MINIMUM_BEARING_LENGTH_IN: float = 1.5


def required_bearing_length(
    reaction_lb: float,
    width_in: float,
    fc_perp_base_psi: float,
    minimum_in: float = MINIMUM_BEARING_LENGTH_IN,
) -> float:
    """Minimum bearing length Lb such that the actual bearing stress does
    not exceed the allowable: R / (b * Lb) <= Fc_perp_base * Cb(Lb).

    Cb(Lb) = (Lb + 0.375) / Lb for Lb < 6 in (NDS 3.10.4), which makes Lb
    cancel out of both sides algebraically:

        R / (b * Lb) = Fc_perp_base * (Lb + 0.375) / Lb
        R / b         = Fc_perp_base * (Lb + 0.375)
        Lb            = R / (b * Fc_perp_base) - 0.375

    That closed form is only valid where it's self-consistent with the
    Cb formula's applicable range (Lb < 6 in); above that Cb is flat at
    1.0, so the -0.375 adjustment doesn't apply.
    """
    if reaction_lb <= 0 or width_in <= 0:
        return minimum_in
    lb_at_cb_one = reaction_lb / (width_in * fc_perp_base_psi)
    if lb_at_cb_one >= 6.0:
        required = lb_at_cb_one
    else:
        required = lb_at_cb_one - 0.375
    return max(required, minimum_in)


# ---------------------------------------------------------------------------
# Member type labels and deflection limits
# IRC 2021 Table R301.7 "Allowable Deflection of Structural Members"
#
# live denominator = limit for transient loads (live or snow)
# total denominator = limit for total load (dead + live + snow)
#
# Note: IRC R301.7 uses L/240 for total load across all listed member types.
# The transient limit varies by member type.
# ---------------------------------------------------------------------------
MEMBER_TYPE_LABELS: dict[str, str] = {
    "floor_joist":                  "Floor joist",
    "ceiling_joist_no_storage":     "Ceiling joist (no attic storage)",
    "ceiling_joist_limited_storage":"Ceiling joist (limited attic storage)",
    "rafter_no_ceiling":            "Rafter (no ceiling finish attached)",
    "rafter_with_ceiling":          "Rafter (with ceiling finish attached)",
    "beam_header":                  "Beam / header",
}

PERFORMANCE_PROFILE_LABELS: dict[str, str] = {
    "code_minimum": "Code minimum",
    "enhanced_comfort": "Enhanced comfort",
    "premium_finish": "Premium finish / hard-surface focus",
}

SUBFLOOR_PROFILE_LABELS: dict[str, str] = {
    "none": "None / not applicable",
    "panel": "Standard panel subfloor",
    "glued_screwed": "Glued and screwed panel subfloor",
}

DEFLECTION_LIMITS: dict[str, dict[str, int]] = {
    "floor_joist":                  {"live": 360, "total": 240},
    "ceiling_joist_no_storage":     {"live": 240, "total": 240},
    "ceiling_joist_limited_storage":{"live": 360, "total": 240},
    "rafter_no_ceiling":            {"live": 180, "total": 240},
    "rafter_with_ceiling":          {"live": 240, "total": 240},
    "beam_header":                  {"live": 360, "total": 240},
}

PERFORMANCE_PROFILE_LIMITS: dict[str, dict[str, int | None]] = {
    "code_minimum": {
        "live": None,
        "total": None,
        "cantilever_live": None,
        "cantilever_total": None,
    },
    "enhanced_comfort": {
        "live": 480,
        "total": 360,
        "cantilever_live": 360,
        "cantilever_total": 240,
    },
    "premium_finish": {
        "live": 600,
        "total": 480,
        "cantilever_live": 480,
        "cantilever_total": 360,
    },
}

SUBFLOOR_PROFILE_LIMITS: dict[str, dict[str, int | None]] = {
    "none": {
        "live": None,
        "total": None,
        "cantilever_live": None,
        "cantilever_total": None,
    },
    "panel": {
        "live": 480,
        "total": 360,
        "cantilever_live": None,
        "cantilever_total": None,
    },
    "glued_screwed": {
        "live": 600,
        "total": 480,
        "cantilever_live": None,
        "cantilever_total": None,
    },
}


def default_deflection_settings(
    member_type: str,
    performance_profile: str = "code_minimum",
    subfloor_profile: str = "none",
) -> dict[str, int]:
    """Default settings for the app's Settings tab.

    Back-span limits come from IRC Table R301.7 per ``DEFLECTION_LIMITS``.
    Cantilever limits default to the same denominators, but remain
    independently editable in the UI because BC Calc-style workflows
    often treat overhang serviceability separately.

    ``performance_profile`` tightens those defaults when the user wants a
    stiffer-feeling member than bare code minimum. ``subfloor_profile`` is
    intentionally a serviceability-only modifier for floor joists; it does
    not assume composite action or increase strength/stiffness in the
    structural model itself.
    """
    base = DEFLECTION_LIMITS[member_type]
    settings = {
        "deflection_limit_live": base["live"],
        "deflection_limit_total": base["total"],
        "cantilever_deflection_limit_live": base["live"],
        "cantilever_deflection_limit_total": base["total"],
    }
    profile_limits = PERFORMANCE_PROFILE_LIMITS.get(
        performance_profile, PERFORMANCE_PROFILE_LIMITS["code_minimum"],
    )
    if profile_limits["live"] is not None:
        settings["deflection_limit_live"] = max(settings["deflection_limit_live"], int(profile_limits["live"]))
    if profile_limits["total"] is not None:
        settings["deflection_limit_total"] = max(settings["deflection_limit_total"], int(profile_limits["total"]))
    if profile_limits["cantilever_live"] is not None:
        settings["cantilever_deflection_limit_live"] = max(
            settings["cantilever_deflection_limit_live"], int(profile_limits["cantilever_live"]),
        )
    if profile_limits["cantilever_total"] is not None:
        settings["cantilever_deflection_limit_total"] = max(
            settings["cantilever_deflection_limit_total"], int(profile_limits["cantilever_total"]),
        )

    if member_type == "floor_joist":
        subfloor_limits = SUBFLOOR_PROFILE_LIMITS.get(subfloor_profile, SUBFLOOR_PROFILE_LIMITS["none"])
        if subfloor_limits["live"] is not None:
            settings["deflection_limit_live"] = max(settings["deflection_limit_live"], int(subfloor_limits["live"]))
        if subfloor_limits["total"] is not None:
            settings["deflection_limit_total"] = max(settings["deflection_limit_total"], int(subfloor_limits["total"]))
        if subfloor_limits["cantilever_live"] is not None:
            settings["cantilever_deflection_limit_live"] = max(
                settings["cantilever_deflection_limit_live"], int(subfloor_limits["cantilever_live"]),
            )
        if subfloor_limits["cantilever_total"] is not None:
            settings["cantilever_deflection_limit_total"] = max(
                settings["cantilever_deflection_limit_total"], int(subfloor_limits["cantilever_total"]),
            )
    return settings
