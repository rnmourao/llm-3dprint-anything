"""FDM material properties — single source of truth for thermal & structural checks.

Values are typical "in-plane" (parallel to layer lines) properties for
hobby-grade printed parts. Inter-layer (z-direction) strength is 30–60% of
these values; consumers that care about layer orientation should apply a
derating factor (the structural checks default safety_factor=3.0 absorbs
some of this).

Sources cross-checked: filament vendor datasheets (Prusa, Polymaker,
Hatchbox), Wikipedia material articles, and 3dhubs / hubs.com FDM strength
references. Where values disagree, the conservative end is chosen.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Material:
    name: str
    yield_mpa: float          # tensile yield strength
    youngs_modulus_gpa: float # elastic modulus, in GPa
    glass_transition_c: float # Tg — material softens, structural strength collapses
    hdt_c: float              # heat deflection temperature at 0.45 MPa load
    cte_per_c: float          # linear thermal-expansion coefficient, 1/°C
    density_kg_m3: float


MATERIALS_FDM: dict[str, Material] = {
    "PLA": Material(
        name="PLA",
        yield_mpa=50.0,
        youngs_modulus_gpa=3.5,
        glass_transition_c=60.0,
        hdt_c=55.0,
        cte_per_c=70e-6,
        density_kg_m3=1240.0,
    ),
    "PETG": Material(
        name="PETG",
        yield_mpa=45.0,
        youngs_modulus_gpa=2.2,
        glass_transition_c=80.0,
        hdt_c=70.0,
        cte_per_c=60e-6,
        density_kg_m3=1270.0,
    ),
    "ABS": Material(
        name="ABS",
        yield_mpa=40.0,
        youngs_modulus_gpa=2.0,
        glass_transition_c=105.0,
        hdt_c=95.0,
        cte_per_c=90e-6,
        density_kg_m3=1040.0,
    ),
}


def get_material(name: str) -> Material:
    if name not in MATERIALS_FDM:
        valid = ", ".join(sorted(MATERIALS_FDM))
        raise ValueError(f"Unknown material {name!r}; expected one of: {valid}")
    return MATERIALS_FDM[name]


def supported_materials() -> tuple[str, ...]:
    return tuple(sorted(MATERIALS_FDM))
