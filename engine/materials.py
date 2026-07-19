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

Scope note: the sawn materials below are VISUALLY GRADED SAWN DIMENSION
LUMBER. Spruce-Pine-Fir, Douglas Fir-Larch and Hem-Fir share the NDS-S
Table 4A size-factor (CF) framework in engine/factors.py (SIZE_FACTORS_FB,
valid for Select Structural / No.1 / No.2 / No.3 grades). Southern Pine is
different: NDS-S Table 4B tabulates Fb PER NOMINAL SIZE (2x4..2x12), so the
size effect is already built in and CF = 1.0; those grades carry an
``fb_by_size`` map instead. Southern Pine is otherwise a normal sawn
material (Cr, CM, CL all apply and it uses the sawn size set).

LVL (laminated veneer lumber) is included as an ENGINEERED category
(category="lvl"). Unlike sawn lumber it uses a volume/depth factor CV =
(d_ref/d)^cv_exponent applied to Fb instead of the tabulated CF, the
repetitive-member factor Cr never applies, and it is modelled as
dry-service only (wet-service LVL design values are manufacturer-specific
and not modelled here). The LVL grades below are GENERIC industry-typical
grades named by their E-grade (modulus of elasticity); published values
vary somewhat by manufacturer, so confirm your product meets the selected
grade. Emin is derived from E via the NDS relationship using COV_E = 0.10
(Emin ~= 0.518 * E).

Glulam (glued-laminated timber) is also an ENGINEERED category
(category="glulam"), with generic stress-class values from NDS 2018
Supplement Table 5A (Douglas Fir, dry). It uses the volume factor CV (NDS
5.3.6, a length/depth/width function -- see engine.factors) applied as the
LESSER of CV and the beam stability factor CL, never both. Cr does not
apply and it is modelled dry-service only. The seeded combinations are
treated as BALANCED layups (Fb+ = Fb-), so the single Fb is valid for both
positive and negative moment (safe for continuous/cantilever members);
cross-check against your NDS-S like the non-SPF sawn values. Steel is
still intentionally not here yet.
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
    # "sawn" (visually graded dimension lumber, uses tabulated CF and can
    # take Cr/CM) or "lvl" (engineered; uses the CV depth factor below, no
    # Cr, dry-service only). See checks.py for how these branch.
    category: str = "sawn"
    # LVL bending depth (volume) factor CV = (cv_reference_depth / d) **
    # cv_exponent, applied to Fb in place of CF. Ignored for sawn lumber.
    cv_exponent: float = 0.0
    cv_reference_depth: float = 12.0
    # Southern Pine: NDS-S Table 4B tabulates Fb per nominal size (the size
    # effect is already incorporated, so CF = 1.0). When set, the reference
    # Fb is looked up here by nominal size and no size factor is applied.
    fb_by_size: dict | None = None

    @property
    def is_lvl(self) -> bool:
        return self.category == "lvl"

    @property
    def is_glulam(self) -> bool:
        return self.category == "glulam"


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
    # --- Southern Pine (visually graded, NDS-S Table 4B) -------------------
    # Fb is tabulated PER SIZE (fb_by_size); CF = 1.0. The `Fb` field is a
    # representative fallback only. Fv/Fc_perp/E/Emin are size-independent.
    # SP is a normal sawn material otherwise (Cr, CM, CL apply). Values are
    # representative post-2013 SPIB figures -- cross-check against NDS-S 4B.
    Material(
        id="sp_ss", name="Southern Pine Select Structural",
        species="Southern Pine", grade="Select Structural",
        Fb=2300, Ft=1400, Fv=175, Fc_perp=565, Fc=1800, E=1_800_000, Emin=660_000, G=0.55,
        fb_by_size={"2x4": 2850, "2x6": 2550, "2x8": 2350, "2x10": 2050, "2x12": 1900},
    ),
    Material(
        id="sp_no1", name="Southern Pine No. 1",
        species="Southern Pine", grade="No. 1",
        Fb=1500, Ft=900, Fv=175, Fc_perp=565, Fc=1650, E=1_600_000, Emin=580_000, G=0.55,
        fb_by_size={"2x4": 1850, "2x6": 1650, "2x8": 1500, "2x10": 1300, "2x12": 1250},
    ),
    Material(
        id="sp_no2", name="Southern Pine No. 2",
        species="Southern Pine", grade="No. 2",
        Fb=1200, Ft=725, Fv=175, Fc_perp=565, Fc=1650, E=1_400_000, Emin=510_000, G=0.55,
        fb_by_size={"2x4": 1500, "2x6": 1250, "2x8": 1200, "2x10": 1050, "2x12": 975},
    ),
    # --- Laminated veneer lumber (ENGINEERED) ------------------------------
    # Generic LVL grades named by E-grade (MoE). Fb is the value at the 12"
    # reference depth; the CV = (12/d)^0.136 depth factor adjusts it for
    # other depths. Emin ~= 0.518*E (NDS, COV_E = 0.10). LVL is dry-service
    # and Cr never applies. Confirm your product meets the chosen grade.
    Material(
        id="lvl_1_55e", name="1.55E LVL",
        species="Laminated veneer lumber", grade="1.55E",
        Fb=2325, Ft=1390, Fv=285, Fc_perp=750, Fc=2250, E=1_550_000, Emin=804_000, G=0.50,
        category="lvl", cv_exponent=0.136, cv_reference_depth=12.0,
    ),
    Material(
        id="lvl_1_75e", name="1.75E LVL",
        species="Laminated veneer lumber", grade="1.75E",
        Fb=2600, Ft=1555, Fv=285, Fc_perp=750, Fc=2510, E=1_750_000, Emin=907_000, G=0.50,
        category="lvl", cv_exponent=0.136, cv_reference_depth=12.0,
    ),
    Material(
        id="lvl_1_9e", name="1.9E LVL",
        species="Laminated veneer lumber", grade="1.9E",
        Fb=2600, Ft=1555, Fv=285, Fc_perp=750, Fc=2510, E=1_900_000, Emin=985_000, G=0.50,
        category="lvl", cv_exponent=0.136, cv_reference_depth=12.0,
    ),
    Material(
        id="lvl_2_0e", name="2.0E LVL",
        species="Laminated veneer lumber", grade="2.0E",
        Fb=2900, Ft=1735, Fv=285, Fc_perp=750, Fc=2800, E=2_000_000, Emin=1_037_000, G=0.50,
        category="lvl", cv_exponent=0.136, cv_reference_depth=12.0,
    ),
    Material(
        id="lvl_2_1e", name="2.1E LVL",
        species="Laminated veneer lumber", grade="2.1E",
        Fb=3100, Ft=1855, Fv=285, Fc_perp=750, Fc=2990, E=2_100_000, Emin=1_089_000, G=0.50,
        category="lvl", cv_exponent=0.136, cv_reference_depth=12.0,
    ),
    # --- Glued-laminated timber (ENGINEERED) -------------------------------
    # Generic stress classes, NDS 2018-S Table 5A (Douglas Fir, dry),
    # modelled as balanced layups (Fb+ = Fb-). cv_exponent = 0.10 is 1/x
    # for non-Southern-Pine species; the CV volume factor (factors.py) is
    # applied as the lesser of CV and CL. Cr n/a; dry-service.
    Material(
        id="gl_20f_1_5e", name="20F-1.5E Glulam",
        species="Glued-laminated timber", grade="20F-1.5E",
        Fb=2000, Ft=1100, Fv=265, Fc_perp=560, Fc=1950, E=1_500_000, Emin=790_000, G=0.50,
        category="glulam", cv_exponent=0.10,
    ),
    Material(
        id="gl_24f_1_8e", name="24F-1.8E Glulam",
        species="Glued-laminated timber", grade="24F-1.8E",
        Fb=2400, Ft=1150, Fv=265, Fc_perp=650, Fc=1650, E=1_800_000, Emin=950_000, G=0.50,
        category="glulam", cv_exponent=0.10,
    ),
    Material(
        id="gl_26f_1_9e", name="26F-1.9E Glulam",
        species="Glued-laminated timber", grade="26F-1.9E",
        Fb=2600, Ft=1250, Fv=265, Fc_perp=650, Fc=1900, E=1_900_000, Emin=1_000_000, G=0.50,
        category="glulam", cv_exponent=0.10,
    ),
    Material(
        id="gl_30f_2_1e", name="30F-2.1E Glulam",
        species="Glued-laminated timber", grade="30F-2.1E",
        Fb=3000, Ft=1450, Fv=265, Fc_perp=650, Fc=2100, E=2_100_000, Emin=1_110_000, G=0.50,
        category="glulam", cv_exponent=0.10,
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
