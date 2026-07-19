"""Reference wood design values (manufacturer-independent).

Source: NDS 2018 Supplement Table 4A -- Reference Design Values for
Visually Graded Dimension Lumber (2"-4" thick), published by the
American Wood Council (AWC). Values are for the 2" & wider size
classification, dry service, normal load duration (all base values,
before adjustment factors CF/Cr/CD are applied in checks.py).

============================================================================
VERIFICATION STATUS -- READ BEFORE RELYING ON THESE FOR REAL DESIGN
============================================================================
Only ``Spruce-Pine-Fir No. 2`` was independently confirmed against the
printed NDS 2018 Supplement (Table 4A). The other species/grades below
were transcribed from NDS 2018-S reference knowledge and have NOT been
re-verified against the printed table. Cross-check every Fb, Ft, Fv,
Fc_perp, Fc, E, and Emin against your own NDS-S copy before using them
for actual member design. Fb/Fv/Fc_perp/E drive the checks; Ft/Fc are
stored for future tension/column checks and are not yet used.

Scope note: these are all VISUALLY GRADED SAWN DIMENSION LUMBER species
that share the NDS-S Table 4A size-factor (CF) framework in
engine/factors.py (SIZE_FACTORS_FB, valid for Select Structural / No.1 /
No.2 / No.3 grades). Southern Pine (size-specific tabulated values, no
standard CF), LVL/glulam (volume factor CV, different stability rules),
and steel are intentionally NOT here yet -- they need different
adjustment handling and will be added separately once that handling
exists.
============================================================================
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Material:
    id: str          # stable key for storage / dropdowns
    name: str        # display name, e.g. "Douglas Fir-Larch No. 2"
    species: str     # e.g. "Douglas Fir-Larch"
    grade: str       # e.g. "No. 2"
    Fb: float        # reference bending design value, psi
    Ft: float        # tension parallel to grain, psi (not yet used in checks)
    Fv: float        # shear parallel to grain, psi
    Fc_perp: float   # compression perpendicular to grain, psi
    Fc: float        # compression parallel to grain, psi (not yet used)
    E: float         # modulus of elasticity, psi
    Emin: float      # for stability (beam/column) calculations, psi
    G: float = 0.0   # specific gravity (oven-dry); used for fastener design


# ---------------------------------------------------------------------------
# Material library. Ordered as it should appear in the picker: species
# grouped, Select Structural -> No.1 -> No.2 within each species.
# ---------------------------------------------------------------------------
_LIBRARY = [
    # --- Spruce-Pine-Fir (NLGA) --------------------------------------------
    Material(
        id="spf_ss", name="Spruce-Pine-Fir Select Structural",
        species="Spruce-Pine-Fir", grade="Select Structural",
        Fb=1250, Ft=700, Fv=135, Fc_perp=425, Fc=1400, E=1_500_000, Emin=550_000, G=0.42,
    ),
    Material(
        id="spf_no1", name="Spruce-Pine-Fir No. 1",
        species="Spruce-Pine-Fir", grade="No. 1",
        # NDS-S lists SPF No.1 and No.2 on a single combined row.
        Fb=875, Ft=350, Fv=135, Fc_perp=425, Fc=1150, E=1_400_000, Emin=510_000, G=0.42,
    ),
    Material(
        # The originally-verified reference material. Kept byte-for-byte so
        # existing benchmarks and the SPF_NO2 alias stay stable.
        id="spf_no2", name="Spruce-Pine-Fir No. 2",
        species="Spruce-Pine-Fir", grade="No. 2",
        Fb=875, Ft=350, Fv=135, Fc_perp=425, Fc=1150, E=1_400_000, Emin=510_000, G=0.42,
    ),
    # --- Douglas Fir-Larch (WCLIB/WWPA) ------------------------------------
    Material(
        id="dfl_ss", name="Douglas Fir-Larch Select Structural",
        species="Douglas Fir-Larch", grade="Select Structural",
        Fb=1500, Ft=1000, Fv=180, Fc_perp=625, Fc=1700, E=1_900_000, Emin=690_000, G=0.50,
    ),
    Material(
        id="dfl_no1", name="Douglas Fir-Larch No. 1",
        species="Douglas Fir-Larch", grade="No. 1",
        Fb=1200, Ft=825, Fv=180, Fc_perp=625, Fc=1550, E=1_700_000, Emin=620_000, G=0.50,
    ),
    Material(
        id="dfl_no2", name="Douglas Fir-Larch No. 2",
        species="Douglas Fir-Larch", grade="No. 2",
        Fb=900, Ft=575, Fv=180, Fc_perp=625, Fc=1350, E=1_600_000, Emin=580_000, G=0.50,
    ),
    # --- Hem-Fir (WWPA/WCLIB) ----------------------------------------------
    Material(
        id="hf_ss", name="Hem-Fir Select Structural",
        species="Hem-Fir", grade="Select Structural",
        Fb=1400, Ft=925, Fv=150, Fc_perp=405, Fc=1500, E=1_600_000, Emin=580_000, G=0.43,
    ),
    Material(
        id="hf_no1", name="Hem-Fir No. 1",
        species="Hem-Fir", grade="No. 1",
        Fb=1100, Ft=725, Fv=150, Fc_perp=405, Fc=1350, E=1_500_000, Emin=550_000, G=0.43,
    ),
    Material(
        id="hf_no2", name="Hem-Fir No. 2",
        species="Hem-Fir", grade="No. 2",
        Fb=850, Ft=525, Fv=150, Fc_perp=405, Fc=1300, E=1_300_000, Emin=470_000, G=0.43,
    ),
]

MATERIALS = {m.id: m for m in _LIBRARY}
DEFAULT_MATERIAL_ID = "spf_no2"

# Backward-compatible alias: the original single reference material.
SPF_NO2 = MATERIALS["spf_no2"]


def get_material(material_id) -> Material:
    """Look up a material by id, falling back to the default (SPF No. 2)
    for unknown/blank ids so a stale saved value never crashes a design."""
    return MATERIALS.get(material_id, SPF_NO2)


def material_choices() -> list[tuple[str, str]]:
    """(id, display name) pairs for a form ChoiceField / dropdown."""
    return [(m.id, m.name) for m in _LIBRARY]
