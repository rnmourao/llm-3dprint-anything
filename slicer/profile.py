"""Slice profile — parameters for converting an STL to G-code.

The profile maps to PrusaSlicer CLI flags. Per-material defaults live below;
override individual fields with `dataclasses.replace(profile, layer_height_mm=0.15)`.

This module deliberately keeps a small surface — the upstream skill
`pjt222/select-print-material` handles material selection, and the downstream
manufacturability skills (`flowful-ai/cad-skill`, etc.) handle support /
overhang / wall-thickness analysis. We are only the mechanical bridge.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class SliceProfile:
    layer_height_mm: float = 0.20
    nozzle_diameter_mm: float = 0.40
    infill_percent: int = 20
    perimeters: int = 2
    material: str = "PLA"
    extruder_temp_c: int = 215
    bed_temp_c: int = 60
    extra_args: tuple[str, ...] = field(default_factory=tuple)


_BY_MATERIAL: dict[str, SliceProfile] = {
    "PLA":  SliceProfile(material="PLA",  extruder_temp_c=215, bed_temp_c=60),
    "PETG": SliceProfile(material="PETG", extruder_temp_c=230, bed_temp_c=75),
    "ABS":  SliceProfile(material="ABS",  extruder_temp_c=240, bed_temp_c=100),
}


def profile_for_material(material: str, **overrides) -> SliceProfile:
    """Look up the default profile for a material, with optional field overrides.

    >>> profile_for_material("PLA", layer_height_mm=0.15)
    SliceProfile(layer_height_mm=0.15, ..., material='PLA', extruder_temp_c=215, ...)
    """
    if material not in _BY_MATERIAL:
        valid = ", ".join(sorted(_BY_MATERIAL))
        raise ValueError(f"Unknown material {material!r}; expected one of: {valid}")
    base = _BY_MATERIAL[material]
    return replace(base, **overrides) if overrides else base


def supported_materials() -> tuple[str, ...]:
    return tuple(sorted(_BY_MATERIAL))
