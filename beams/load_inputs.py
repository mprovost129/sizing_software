"""Load-input helpers for the beam designer.

UI-facing concepts such as psf/plf entry basis and on-center spacing
live here so the structural engine can stay normalized around plf.
"""
from engine import UniformLoad

UNIFORM_LOAD_BASIS_CHOICES = [
    ("psf", "Area load (psf)"),
    ("plf", "Line load (plf)"),
]

UNIFORM_COMPONENT_FIELDS = (
    ("dead_load_plf", "dead"),
    ("live_load_plf", "live"),
    ("snow_load_plf", "snow"),
    ("roof_live_load_plf", "roof_live"),
    ("wind_load_plf", "wind"),
)

DEFAULT_UNIFORM_LOADS_PSF = {
    "floor_joist": {
        "dead_load_plf": 10.0,
        "live_load_plf": 40.0,
        "snow_load_plf": 0.0,
        "roof_live_load_plf": 0.0,
        "wind_load_plf": 0.0,
    },
    "ceiling_joist_no_storage": {
        "dead_load_plf": 5.0,
        "live_load_plf": 10.0,
        "snow_load_plf": 0.0,
        "roof_live_load_plf": 0.0,
        "wind_load_plf": 0.0,
    },
    "ceiling_joist_limited_storage": {
        "dead_load_plf": 10.0,
        "live_load_plf": 20.0,
        "snow_load_plf": 0.0,
        "roof_live_load_plf": 0.0,
        "wind_load_plf": 0.0,
    },
    "rafter_no_ceiling": {
        "dead_load_plf": 10.0,
        "live_load_plf": 0.0,
        "snow_load_plf": 0.0,
        "roof_live_load_plf": 20.0,
        "wind_load_plf": 0.0,
    },
    "rafter_with_ceiling": {
        "dead_load_plf": 15.0,
        "live_load_plf": 0.0,
        "snow_load_plf": 0.0,
        "roof_live_load_plf": 20.0,
        "wind_load_plf": 0.0,
    },
    "beam_header": {
        "dead_load_plf": 10.0,
        "live_load_plf": 40.0,
        "snow_load_plf": 0.0,
        "roof_live_load_plf": 0.0,
        "wind_load_plf": 0.0,
    },
}


def spacing_factor(spacing_in: float | None) -> float:
    spacing = spacing_in or 0.0
    return spacing / 12.0


def normalize_uniform_component(value: float | None, basis: str, spacing_in: float | None) -> float:
    entered = value or 0.0
    if basis == "psf":
        return entered * spacing_factor(spacing_in)
    return entered


def entered_uniform_loads_to_plf(data) -> dict[str, float]:
    basis = data.get("uniform_load_basis") or "plf"
    spacing_in = data.get("spacing_in") or 0.0
    plf_values = {}
    for field_name, load_type in UNIFORM_COMPONENT_FIELDS:
        plf_values[load_type] = normalize_uniform_component(data.get(field_name), basis, spacing_in)
    return plf_values


def build_uniform_loads(data) -> list[UniformLoad]:
    return [
        UniformLoad(w=value, load_type=load_type)
        for load_type, value in entered_uniform_loads_to_plf(data).items()
        if value
    ]


def default_uniform_component_values(member_type: str, basis: str = "psf", spacing_in: float = 16.0) -> dict[str, float]:
    base = DEFAULT_UNIFORM_LOADS_PSF[member_type]
    if basis == "psf":
        return dict(base)
    factor = spacing_factor(spacing_in)
    return {name: value * factor for name, value in base.items()}
