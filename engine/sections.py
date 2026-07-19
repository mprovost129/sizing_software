"""Sawn lumber and LVL section geometry.

Actual dressed sizes for standard sawn dimension lumber (per NDS-S Table
1B) plus standard laminated-veneer-lumber (LVL) sizes. Each entry maps a
size id to (single-ply width in., depth in.); for a built-up member the
total width is that single-ply width times the ply count. Sawn plies are
1.5" wide; LVL laminations are 1.75" wide.
"""
from dataclasses import dataclass

# sawn nominal size -> (single-ply actual width in., actual depth in.)
_SAWN_SIZES = {
    "2x4": (1.5, 3.5),
    "2x6": (1.5, 5.5),
    "2x8": (1.5, 7.25),
    "2x10": (1.5, 9.25),
    "2x12": (1.5, 11.25),
}

# LVL size id -> (single-lamination width 1.75", depth in.). LVL is built
# up from 1.75"-wide laminations, so ply count sets the total width the
# same way it does for sawn lumber.
_LVL_SIZES = {
    "lvl_7.25": (1.75, 7.25),
    "lvl_9.25": (1.75, 9.25),
    "lvl_11.25": (1.75, 11.25),
    "lvl_11.875": (1.75, 11.875),
    "lvl_14": (1.75, 14.0),
    "lvl_16": (1.75, 16.0),
    "lvl_18": (1.75, 18.0),
}

# Human-readable depth labels for LVL sizes (depth only; width comes from
# the ply count and is shown separately).
LVL_SIZE_LABELS = {
    "lvl_7.25": '7-1/4"',
    "lvl_9.25": '9-1/4"',
    "lvl_11.25": '11-1/4"',
    "lvl_11.875": '11-7/8"',
    "lvl_14": '14"',
    "lvl_16": '16"',
    "lvl_18": '18"',
}

# Glulam is a monolithic section specified as width x depth (it is not
# built up from plies), so each size id encodes both. Western-species
# widths (3.5, 5.125, 5.5, 6.75 in) and depths in 1.5" lamination
# multiples. (single-ply width, depth); plies is always 1 for glulam.
_GLULAM_SIZES = {
    "gl_3.5x9": (3.5, 9.0),
    "gl_3.5x12": (3.5, 12.0),
    "gl_3.5x15": (3.5, 15.0),
    "gl_5.125x12": (5.125, 12.0),
    "gl_5.125x15": (5.125, 15.0),
    "gl_5.125x18": (5.125, 18.0),
    "gl_5.5x15": (5.5, 15.0),
    "gl_5.5x18": (5.5, 18.0),
    "gl_6.75x18": (6.75, 18.0),
    "gl_6.75x21": (6.75, 21.0),
}

GLULAM_SIZE_LABELS = {
    "gl_3.5x9": '3-1/2x9"',
    "gl_3.5x12": '3-1/2x12"',
    "gl_3.5x15": '3-1/2x15"',
    "gl_5.125x12": '5-1/8x12"',
    "gl_5.125x15": '5-1/8x15"',
    "gl_5.125x18": '5-1/8x18"',
    "gl_5.5x15": '5-1/2x15"',
    "gl_5.5x18": '5-1/2x18"',
    "gl_6.75x18": '6-3/4x18"',
    "gl_6.75x21": '6-3/4x21"',
}

# Size id -> human depth/section label, across every engineered family.
SIZE_LABELS = {**LVL_SIZE_LABELS, **GLULAM_SIZE_LABELS}

_ALL_SIZES = {**_SAWN_SIZES, **_LVL_SIZES, **_GLULAM_SIZES}

NOMINAL_SIZES = tuple(_SAWN_SIZES)  # sawn only (existing dropdown/choices)
LVL_SIZES = tuple(_LVL_SIZES)
GLULAM_SIZES = tuple(_GLULAM_SIZES)


@dataclass(frozen=True)
class Section:
    nominal: str
    b: float  # total actual width across all plies, in.
    d: float  # actual depth, in.
    plies: int = 1

    @property
    def ply_width(self) -> float:
        """Actual width of a single ply / lamination, in."""
        return self.b / self.plies

    @property
    def label(self) -> str:
        """Section label with a ply prefix for built-up members. LVL sizes
        show their depth (e.g. "11-7/8\"") and glulam its width x depth
        (e.g. "5-1/8x15\"") rather than the raw id."""
        base = SIZE_LABELS.get(self.nominal, self.nominal)
        return f"{self.plies}-ply {base}" if self.plies > 1 else base

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
    def from_nominal(cls, nominal: str, plies: int = 1) -> "Section":
        """Build a section for `plies` fastened side-by-side (a built-up
        member, e.g. a 3-ply 2x10 header or a 2-ply LVL). The plies are
        assumed adequately fastened to act together, so section properties
        scale linearly with ply count: the total width is one ply's
        dressed width times the ply count, while the depth is unchanged."""
        try:
            single_b, d = _ALL_SIZES[nominal]
        except KeyError:
            raise ValueError(f"Unknown nominal size: {nominal!r}")
        if plies < 1:
            raise ValueError(f"plies must be >= 1, got {plies!r}")
        return cls(nominal=nominal, b=single_b * plies, d=d, plies=plies)
