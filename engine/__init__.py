"""Structural calculation engine.

Plain Python, no Django dependency, per the project's guiding
philosophy: the calculation engine is the foundation every interface
(web, API, CLI, AI assistant) builds on, not the other way around.
"""
from .checks import BeamDesignResult, CheckResult, design_beam
from .columns import ColumnResult, design_column
from .factors import (
    DEFLECTION_LIMITS,
    MEMBER_TYPE_LABELS,
    PERFORMANCE_PROFILE_LABELS,
    SUBFLOOR_PROFILE_LABELS,
    default_deflection_settings,
)
from .loads import PointLoad, UniformLoad
from .materials import (
    DEFAULT_MATERIAL_ID,
    MATERIALS,
    SPF_NO2,
    Material,
    get_material,
    material_choices,
)
from .sections import (
    GLULAM_SIZE_LABELS,
    GLULAM_SIZES,
    LVL_SIZE_LABELS,
    LVL_SIZES,
    NOMINAL_SIZES,
    SIZE_LABELS,
    TIMBER_SIZE_LABELS,
    TIMBER_SIZES,
    Section,
)
from .span import SPAN_MODE_LABELS, SpanMode, clear_span

__all__ = [
    "Material",
    "SPF_NO2",
    "MATERIALS",
    "DEFAULT_MATERIAL_ID",
    "get_material",
    "material_choices",
    "Section",
    "NOMINAL_SIZES",
    "LVL_SIZES",
    "LVL_SIZE_LABELS",
    "GLULAM_SIZES",
    "GLULAM_SIZE_LABELS",
    "TIMBER_SIZES",
    "TIMBER_SIZE_LABELS",
    "SIZE_LABELS",
    "UniformLoad",
    "PointLoad",
    "design_beam",
    "design_column",
    "ColumnResult",
    "BeamDesignResult",
    "CheckResult",
    "MEMBER_TYPE_LABELS",
    "DEFLECTION_LIMITS",
    "PERFORMANCE_PROFILE_LABELS",
    "SUBFLOOR_PROFILE_LABELS",
    "default_deflection_settings",
    "SPAN_MODE_LABELS",
    "SpanMode",
    "clear_span",
]
