from engine import (
    DEFAULT_MATERIAL_ID,
    MEMBER_TYPE_LABELS,
    NOMINAL_SIZES,
    PERFORMANCE_PROFILE_LABELS,
    SPAN_MODE_LABELS,
    SUBFLOOR_PROFILE_LABELS,
    material_choices,
)

from .load_inputs import UNIFORM_LOAD_BASIS_CHOICES

NOMINAL_SIZE_CHOICES = [(size, size) for size in NOMINAL_SIZES]
MATERIAL_CHOICES = material_choices()
DEFAULT_MATERIAL = DEFAULT_MATERIAL_ID
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
