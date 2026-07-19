"""NDS wood design adjustment factors.

Source references:
  - Load duration (CD):      NDS 2018 Table 2.3.2
  - Size factor (CF):        NDS Supplement 2018 Table 4A footnote
                             (Select Structural / No.1 / No.2 / No.3,
                              2"-4" thick, edgewise bending)
  - Repetitive member (Cr): NDS 2018 Section 4.3.9 / Table 4A note
  - Bearing area (Cb):       NDS 2018 Section 3.10.4
  - Deflection limits:       IRC 2021 Table R301.7

Factors NOT yet implemented (out of scope for sawn-lumber MVP):
  CM (wet service), Ct (temperature), CL (beam stability),
  Ci (incising), CT (buckling stiffness for trusses).
"""

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
