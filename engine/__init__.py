"""Structural calculation engine.

Plain Python, no Django dependency, per the project's guiding
philosophy: the calculation engine is the foundation every interface
(web, API, CLI, AI assistant) builds on, not the other way around.
"""
from .checks import BeamDesignResult, CheckResult, design_beam
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
from .sections import NOMINAL_SIZES, Section
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
    "UniformLoad",
    "PointLoad",
    "design_beam",
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
