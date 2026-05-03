"""Thermal-deformation checks — operating-temperature safety.

A printed FDM part has two relevant thermal landmarks:

  HDT (heat deflection temperature) — the part starts to sag under load.
      Operating above HDT but below Tg → WARN. The part still has some
      structural strength but will deform measurably under sustained load.

  Tg (glass transition) — the polymer transitions from glassy to rubbery.
      Operating above Tg → BLOCK. The part loses most of its yield strength
      and will deform freely; structural rules no longer apply.

This module is closed-form lookup only. Thermal stress under transient
heating, creep over time, and thermo-mechanical coupling are out of scope —
they need real FEA (CalculiX, Code_Aster) and a separate workstream.
"""

from __future__ import annotations

from typing import Optional

from .materials import get_material
from .types import Severity, Verdict


def check_operating_temperature(
    *,
    operating_temp_c: float,
    material: str = "PLA",
    part_name: Optional[str] = None,
) -> Verdict:
    """Compare an operating temperature against the material's HDT and Tg.

    No geometry argument: this is purely a material-property lookup. If a
    part is named, it appears in the rule key so reports involving multiple
    parts at different temperatures stay distinguishable.
    """
    mat = get_material(material)
    suffix = f":{part_name}" if part_name else ""
    rule = f"operating_temperature{suffix}"
    label = f"{part_name} ({material})" if part_name else material

    evidence = {
        "operating_temp_c": float(operating_temp_c),
        "material": material,
        "hdt_c": mat.hdt_c,
        "glass_transition_c": mat.glass_transition_c,
        "margin_to_hdt_c": mat.hdt_c - operating_temp_c,
        "margin_to_tg_c": mat.glass_transition_c - operating_temp_c,
    }

    if operating_temp_c >= mat.glass_transition_c:
        return Verdict(
            rule=rule,
            severity=Severity.BLOCK,
            message=(
                f"{label} operating at {operating_temp_c:.1f} °C — at or above "
                f"the glass transition temperature ({mat.glass_transition_c:.1f} °C). "
                "Material loses structural strength; the part will deform freely."
            ),
            evidence=evidence,
            suggested_action=(
                "Reduce operating temperature, switch to a higher-Tg material "
                f"(PETG Tg≈80°C, ABS Tg≈105°C — vs {material} Tg≈{mat.glass_transition_c:.0f}°C), "
                "or redesign so this part is not load-bearing at temperature."
            ),
        )

    if operating_temp_c >= mat.hdt_c:
        return Verdict(
            rule=rule,
            severity=Severity.WARN,
            message=(
                f"{label} operating at {operating_temp_c:.1f} °C — between HDT "
                f"({mat.hdt_c:.1f} °C) and Tg ({mat.glass_transition_c:.1f} °C). "
                "Part will sag under sustained load; treat structural margins as advisory."
            ),
            evidence=evidence,
            suggested_action=(
                "Avoid sustained loads at this temperature; switch to a material "
                "with higher HDT if creep matters."
            ),
        )

    return Verdict(
        rule=rule,
        severity=Severity.PASS,
        message=(
            f"{label} operating at {operating_temp_c:.1f} °C — comfortably below "
            f"HDT ({mat.hdt_c:.1f} °C); structural rules apply."
        ),
        evidence=evidence,
    )
