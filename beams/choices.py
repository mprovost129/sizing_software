from engine import (
    DEFAULT_MATERIAL_ID,
    GLULAM_SIZE_LABELS,
    GLULAM_SIZES,
    LVL_SIZE_LABELS,
    LVL_SIZES,
    MATERIALS,
    MEMBER_TYPE_LABELS,
    NOMINAL_SIZES,
    PERFORMANCE_PROFILE_LABELS,
    SPAN_MODE_LABELS,
    SUBFLOOR_PROFILE_LABELS,
    TIMBER_SIZE_LABELS,
    TIMBER_SIZES,
    material_choices,
)

from .load_inputs import UNIFORM_LOAD_BASIS_CHOICES

NOMINAL_SIZE_CHOICES = [(size, size) for size in NOMINAL_SIZES]
# Engineered sizes: id -> human label ('11-7/8"' for LVL depths,
# '5-1/8x15"' for glulam width x depth).
LVL_SIZE_CHOICES = [(size, LVL_SIZE_LABELS[size]) for size in LVL_SIZES]
GLULAM_SIZE_CHOICES = [(size, GLULAM_SIZE_LABELS[size]) for size in GLULAM_SIZES]
TIMBER_SIZE_CHOICES = [(size, TIMBER_SIZE_LABELS[size]) for size in TIMBER_SIZES]
# The size field/model validates against sawn AND engineered/timber ids;
# the UI shows only the group matching the selected material's category.
ALL_SIZE_CHOICES = NOMINAL_SIZE_CHOICES + LVL_SIZE_CHOICES + GLULAM_SIZE_CHOICES + TIMBER_SIZE_CHOICES
MATERIAL_CHOICES = material_choices()
# Material id -> "sawn" | "lvl" | "glulam" | "timber", and size id -> same,
# so the picker can filter sizes by category and the form validates the pair.
MATERIAL_CATEGORY = {mid: m.category for mid, m in MATERIALS.items()}
SIZE_CATEGORY = {
    **{s: "sawn" for s, _ in NOMINAL_SIZE_CHOICES},
    **{s: "lvl" for s, _ in LVL_SIZE_CHOICES},
    **{s: "glulam" for s, _ in GLULAM_SIZE_CHOICES},
    **{s: "timber" for s, _ in TIMBER_SIZE_CHOICES},
}
DEFAULT_MATERIAL = DEFAULT_MATERIAL_ID
# Built-up members: 1-4 plies fastened side by side (e.g. a 3-ply 2x10
# header). Section properties scale with ply count; see engine.sections.
PLY_CHOICES = [(n, f"{n} ply" if n == 1 else f"{n} plies") for n in (1, 2, 3, 4)]
DEFAULT_PLIES = 1

# Dowel-type fasteners (NDS Chapter 12). Each maps to a representative
# bending yield strength Fyb (psi) used to pre-fill the connection form.
FASTENER_TYPE_CHOICES = [
    ("bolt", "Bolt"),
    ("lag", "Lag screw"),
    ("nail", "Common nail"),
    ("screw", "Wood screw"),
]
FASTENER_FYB = {"bolt": 45000, "lag": 45000, "nail": 100000, "screw": 80000}
DEFAULT_FASTENER = "bolt"
SHEAR_PLANES_CHOICES = [
    ("single", "Single shear (2 members)"),
    ("double", "Double shear (3 members)"),
]
CONNECTION_LOADING_CHOICES = [
    ("lateral", "Lateral (shear)"),
    ("withdrawal", "Withdrawal (axial)"),
]

# Load-to-grain direction for dowel bearing strength.
LOAD_DIRECTION_CHOICES = [
    ("parallel", "Parallel to grain"),
    ("perpendicular", "Perpendicular to grain"),
]

# Load-duration factor CD (NDS Table 2.3.2) as a selectable value.
CONNECTION_CD_CHOICES = [
    (0.9, "Dead / permanent (CD = 0.9)"),
    (1.0, "Occupancy live (CD = 1.0)"),
    (1.15, "Snow (CD = 1.15)"),
    (1.25, "Construction (CD = 1.25)"),
    (1.6, "Wind / seismic (CD = 1.6)"),
]
DEFAULT_CONNECTION_CD = 1.0

# Temperature factor Ct (NDS Table 11.3.4): sustained service temperature
# range for connections. "normal" (T <= 100F) -> Ct = 1.0 (default).
CONNECTION_TEMPERATURE_CHOICES = [
    ("normal", "Normal (T ≤ 100°F)"),
    ("warm", "100°F – 125°F"),
    ("hot", "125°F – 150°F"),
]
DEFAULT_CONNECTION_TEMPERATURE = "normal"

# Long-term deflection creep factor Kcr (NDS 3.5.2): amplifies the
# sustained (dead) portion of the total-deflection check. 1.0 = immediate
# elastic only (default). Value stored as float; used by the total check.
CREEP_FACTOR_CHOICES = [
    (1.0, "None - immediate deflection only"),
    (1.5, "Seasoned / dry lumber (Kcr = 1.5)"),
    (2.0, "Unseasoned or wet service (Kcr = 2.0)"),
]
DEFAULT_CREEP_FACTOR = 1.0

# Column end conditions -> effective-length factor Ke (NDS Appendix G,
# recommended design values). Value is the Ke as a string; the view floats it.
END_CONDITION_CHOICES = [
    ("1.0", "Pinned - pinned, no sidesway (Ke = 1.0)"),
    ("0.8", "Fixed - pinned, no sidesway (Ke = 0.8)"),
    ("0.65", "Fixed - fixed, no sidesway (Ke = 0.65)"),
    ("2.1", "Fixed - free / flagpole (Ke = 2.1)"),
]
DEFAULT_END_CONDITION = "1.0"

# Service (moisture) condition: dry = interior/protected (CM = 1.0);
# wet = exterior/damp, MC > 19% (NDS-S Table 4A wet-service factors).
SERVICE_CONDITION_CHOICES = [
    ("dry", "Dry (interior / protected)"),
    ("wet", "Wet / exterior (MC > 19%)"),
]
DEFAULT_SERVICE_CONDITION = "dry"
MEMBER_TYPE_CHOICES = list(MEMBER_TYPE_LABELS.items())
PERFORMANCE_PROFILE_CHOICES = list(PERFORMANCE_PROFILE_LABELS.items())
SUBFLOOR_PROFILE_CHOICES = list(SUBFLOOR_PROFILE_LABELS.items())
LOAD_TYPE_CHOICES = [
    ("dead", "Dead"),
    ("live", "Live"),
    ("snow", "Snow"),
    ("roof_live", "Roof live"),
    ("wind", "Wind"),
]
UNIFORM_LOAD_BASIS_FORM_CHOICES = UNIFORM_LOAD_BASIS_CHOICES
SPAN_MODE_CHOICES = list(SPAN_MODE_LABELS.items())

# Bearing condition at each support -- visual only for now (drives which
# symbol the beam diagram draws); doesn't yet change the bearing check
# itself, which still uses a generic Fc-perp calculation regardless.
SUPPORT_TYPE_CHOICES = [
    ("wall_plate", "Wall / Plate"),
    ("column", "Column / Post"),
    ("hanger", "Hanger"),
]
