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
    material_choices,
)

from .load_inputs import UNIFORM_LOAD_BASIS_CHOICES

NOMINAL_SIZE_CHOICES = [(size, size) for size in NOMINAL_SIZES]
# Engineered sizes: id -> human label ('11-7/8"' for LVL depths,
# '5-1/8x15"' for glulam width x depth).
LVL_SIZE_CHOICES = [(size, LVL_SIZE_LABELS[size]) for size in LVL_SIZES]
GLULAM_SIZE_CHOICES = [(size, GLULAM_SIZE_LABELS[size]) for size in GLULAM_SIZES]
# The size field/model validates against sawn AND engineered ids; the UI
# shows only the group matching the selected material's category.
ALL_SIZE_CHOICES = NOMINAL_SIZE_CHOICES + LVL_SIZE_CHOICES + GLULAM_SIZE_CHOICES
MATERIAL_CHOICES = material_choices()
# Material id -> "sawn" | "lvl" | "glulam", and size id -> same, so the
# picker can filter sizes by category and the form can validate the pair.
MATERIAL_CATEGORY = {mid: m.category for mid, m in MATERIALS.items()}
SIZE_CATEGORY = {
    **{s: "sawn" for s, _ in NOMINAL_SIZE_CHOICES},
    **{s: "lvl" for s, _ in LVL_SIZE_CHOICES},
    **{s: "glulam" for s, _ in GLULAM_SIZE_CHOICES},
}
DEFAULT_MATERIAL = DEFAULT_MATERIAL_ID
# Built-up members: 1-4 plies fastened side by side (e.g. a 3-ply 2x10
# header). Section properties scale with ply count; see engine.sections.
PLY_CHOICES = [(n, f"{n} ply" if n == 1 else f"{n} plies") for n in (1, 2, 3, 4)]
DEFAULT_PLIES = 1

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
