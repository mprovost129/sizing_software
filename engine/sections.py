"""Sawn lumber section geometry.

Actual dressed sizes for standard dimension lumber, per NDS-S Table 1B.
"""
from dataclasses import dataclass

# nominal size -> (actual width in., actual depth in.)
_DRESSED_SIZES = {
    "2x4": (1.5, 3.5),
    "2x6": (1.5, 5.5),
    "2x8": (1.5, 7.25),
    "2x10": (1.5, 9.25),
    "2x12": (1.5, 11.25),
}

NOMINAL_SIZES = tuple(_DRESSED_SIZES)


@dataclass(frozen=True)
class Section:
    nominal: str
    b: float  # actual width, in.
    d: float  # actual depth, in.

    @property
    def A(self) -> float:
        return self.b * self.d

    @property
    def I(self) -> float:
        return self.b * self.d ** 3 / 12

    @property
    def S(self) -> float:
        return self.b * self.d ** 2 / 6

    @classmethod
    def from_nominal(cls, nominal: str) -> "Section":
        try:
            b, d = _DRESSED_SIZES[nominal]
        except KeyError:
            raise ValueError(f"Unknown nominal lumber size: {nominal!r}")
        return cls(nominal=nominal, b=b, d=d)
