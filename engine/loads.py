"""Loads applied to a beam."""
from dataclasses import dataclass
from typing import Literal

LoadType = Literal["dead", "live", "snow", "roof_live", "wind"]


@dataclass(frozen=True)
class UniformLoad:
    w: float  # lb/ft
    load_type: LoadType
    start: float = 0.0  # ft from the left end of the member
    end: float | None = None  # None applies the load through the right end

    def __post_init__(self):
        if self.w < 0:
            raise ValueError("Distributed load intensity cannot be negative.")
        if self.start < 0:
            raise ValueError("Distributed load start cannot be negative.")
        if self.end is not None and self.end <= self.start:
            raise ValueError("Distributed load end must be greater than its start.")


@dataclass(frozen=True)
class PointLoad:
    p: float  # lb
    location: float  # ft from the left support
    load_type: LoadType
