"""Closed-form structural checks — bending, buckling, pressure-vessel hoop.

Studies 02 and 05 are firm that this is *intentionally not FEA*: each
formula here is a back-of-envelope sanity check, drawing the same fit/hold
split mechanical engineering already settled. Coupled / nonlinear / fatigue
analysis stays out of scope.

Three rules live in this module:

  `cantilever_stress` — point load at the tip of a cantilever beam.
      σ = F·L / S, compared to σ_yield / safety_factor.

  `column_buckling` — axial compression on a slender column.
      P_critical = π²·E·I / (K·L)², compared to applied load × safety_factor.

  `pressure_vessel_hoop` — internal pressure on a thin-walled cylinder.
      σ_hoop = P·r / t, compared to σ_yield / safety_factor.

Material data flows through validators.materials.MATERIALS_FDM (Tg, HDT,
yield, Young's modulus, CTE, density). YIELD_MPA_FDM remains as a derived
alias for callers that only need yield strengths.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .materials import MATERIALS_FDM, get_material
from .types import Severity, Verdict


# Derived alias for back-compat. Prefer MATERIALS_FDM directly in new code.
YIELD_MPA_FDM: dict[str, float] = {
    name: mat.yield_mpa for name, mat in MATERIALS_FDM.items()
}


@dataclass(frozen=True)
class RectSection:
    """Solid rectangular cross-section.

    width_mm  — dimension perpendicular to the load (b in beam textbooks)
    height_mm — dimension parallel to the load (h); doubling h drops stress 4×
    """

    width_mm: float
    height_mm: float

    @property
    def section_modulus_mm3(self) -> float:
        return self.width_mm * self.height_mm**2 / 6.0


@dataclass(frozen=True)
class RoundSection:
    """Solid circular cross-section."""

    diameter_mm: float

    @property
    def section_modulus_mm3(self) -> float:
        return math.pi * self.diameter_mm**3 / 32.0


CrossSection = RectSection | RoundSection


def _second_moment_mm4(section: CrossSection) -> float:
    """I (mm^4) — needed by buckling, distinct from the section modulus S = I/c."""
    if isinstance(section, RectSection):
        return section.width_mm * section.height_mm**3 / 12.0
    if isinstance(section, RoundSection):
        return math.pi * section.diameter_mm**4 / 64.0
    raise TypeError(f"Unknown cross-section type: {type(section).__name__}")


# Effective length factor K for Euler buckling, by end-condition convention.
# K · L is the effective length used in P_cr = π² E I / (K L)².
_BUCKLING_K = {
    "fixed-free":     2.0,   # one end fixed, one free (worst case)
    "pinned-pinned":  1.0,   # both ends pinned (textbook case)
    "fixed-pinned":   0.7,   # one fixed, one pinned
    "fixed-fixed":    0.5,   # both ends fully fixed (best case)
}


def check_cantilever(
    beam_length_mm: float,
    cross_section: CrossSection,
    load_n: float,
    *,
    material: str = "PLA",
    safety_factor: float = 3.0,
) -> Verdict:
    if material not in YIELD_MPA_FDM:
        valid = ", ".join(sorted(YIELD_MPA_FDM))
        raise ValueError(f"Unknown material {material!r}; expected one of: {valid}")
    if beam_length_mm <= 0 or load_n < 0 or safety_factor <= 0:
        raise ValueError("beam_length_mm, load_n, safety_factor must be positive")

    yield_mpa = YIELD_MPA_FDM[material]
    allowable_mpa = yield_mpa / safety_factor

    moment_n_mm = load_n * beam_length_mm
    s_mm3 = cross_section.section_modulus_mm3
    stress_mpa = moment_n_mm / s_mm3  # N·mm / mm³ = MPa

    evidence = {
        "beam_length_mm": beam_length_mm,
        "load_n": load_n,
        "material": material,
        "yield_mpa": yield_mpa,
        "safety_factor": safety_factor,
        "allowable_stress_mpa": allowable_mpa,
        "applied_stress_mpa": stress_mpa,
        "section_modulus_mm3": s_mm3,
        "margin": allowable_mpa / stress_mpa if stress_mpa > 0 else math.inf,
    }

    rule = "cantilever_stress"

    if stress_mpa > yield_mpa:
        return Verdict(
            rule=rule,
            severity=Severity.BLOCK,
            message=(
                f"Bending stress {stress_mpa:.1f} MPa exceeds {material} yield "
                f"strength {yield_mpa:.1f} MPa. Beam will fail under this load."
            ),
            evidence=evidence,
            suggested_action=(
                "Doubling the height parallel to the load drops stress 4×; "
                "shortening the beam drops stress linearly."
            ),
        )

    if stress_mpa > allowable_mpa:
        return Verdict(
            rule=rule,
            severity=Severity.WARN,
            message=(
                f"Bending stress {stress_mpa:.1f} MPa is below {material} yield "
                f"({yield_mpa:.1f} MPa) but exceeds the {safety_factor}× safety "
                f"limit ({allowable_mpa:.1f} MPa). Margin = {evidence['margin']:.2f}."
            ),
            evidence=evidence,
            suggested_action=(
                "Increase the cross-section, shorten the beam, or accept the "
                "reduced safety margin explicitly."
            ),
        )

    return Verdict(
        rule=rule,
        severity=Severity.PASS,
        message=(
            f"Bending stress {stress_mpa:.2f} MPa is within the {safety_factor}× "
            f"safety margin (allowable {allowable_mpa:.1f} MPa); "
            f"margin = {evidence['margin']:.2f}."
        ),
        evidence=evidence,
    )


def check_buckling(
    column_length_mm: float,
    cross_section: CrossSection,
    axial_load_n: float,
    *,
    material: str = "PLA",
    end_condition: str = "fixed-free",
    safety_factor: float = 3.0,
) -> Verdict:
    """Euler column buckling: P_critical = π² · E · I / (K · L)².

    Buckling is *sudden* — it's not predicted by the yield-stress check
    because a slender column can fail at axial loads far below σ_yield · A.
    This is the relevant failure mode for tall thin printed legs, struts,
    and screw posts under compression.
    """
    if column_length_mm <= 0 or axial_load_n < 0 or safety_factor <= 0:
        raise ValueError("column_length_mm, axial_load_n, safety_factor must be positive")
    if end_condition not in _BUCKLING_K:
        valid = ", ".join(sorted(_BUCKLING_K))
        raise ValueError(f"Unknown end_condition {end_condition!r}; expected one of: {valid}")

    mat = get_material(material)
    K = _BUCKLING_K[end_condition]
    I_mm4 = _second_moment_mm4(cross_section)
    E_n_per_mm2 = mat.youngs_modulus_gpa * 1000.0  # GPa → N/mm²
    L_eff_mm = K * column_length_mm

    P_critical_n = (math.pi**2) * E_n_per_mm2 * I_mm4 / (L_eff_mm**2)
    P_allowable_n = P_critical_n / safety_factor

    rule = "column_buckling"
    evidence = {
        "column_length_mm": column_length_mm,
        "axial_load_n": axial_load_n,
        "material": material,
        "end_condition": end_condition,
        "effective_length_factor_K": K,
        "second_moment_of_area_mm4": I_mm4,
        "youngs_modulus_gpa": mat.youngs_modulus_gpa,
        "P_critical_n": P_critical_n,
        "P_allowable_n": P_allowable_n,
        "safety_factor": safety_factor,
        "margin": P_allowable_n / axial_load_n if axial_load_n > 0 else math.inf,
    }

    if axial_load_n > P_critical_n:
        return Verdict(
            rule=rule,
            severity=Severity.BLOCK,
            message=(
                f"Axial load {axial_load_n:.1f} N exceeds the Euler critical load "
                f"{P_critical_n:.1f} N. Column will buckle catastrophically."
            ),
            evidence=evidence,
            suggested_action=(
                "Shorten the column (P_cr scales as 1/L²), increase the cross-section "
                f"(I scales with the 4th power of {('width' if isinstance(cross_section, RectSection) else 'diameter')}), "
                "or change the end fixity to a stiffer condition."
            ),
        )
    if axial_load_n > P_allowable_n:
        return Verdict(
            rule=rule,
            severity=Severity.WARN,
            message=(
                f"Axial load {axial_load_n:.1f} N is below P_critical {P_critical_n:.1f} N "
                f"but exceeds the {safety_factor}× safety threshold {P_allowable_n:.1f} N. "
                f"Margin = {evidence['margin']:.2f}."
            ),
            evidence=evidence,
            suggested_action=(
                "Increase the cross-section, shorten the column, or accept the "
                "reduced buckling margin explicitly."
            ),
        )
    return Verdict(
        rule=rule,
        severity=Severity.PASS,
        message=(
            f"Axial load {axial_load_n:.1f} N is well within Euler buckling limit "
            f"(P_critical {P_critical_n:.1f} N, allowable {P_allowable_n:.1f} N); "
            f"margin = {evidence['margin']:.2f}."
        ),
        evidence=evidence,
    )


def check_pressure_vessel(
    wall_thickness_mm: float,
    internal_radius_mm: float,
    internal_pressure_pa: float,
    *,
    material: str = "PLA",
    safety_factor: float = 3.0,
) -> Verdict:
    """Thin-walled cylinder hoop stress: σ_hoop = P · r / t.

    Valid for wall_thickness < radius / 10 ("thin wall" regime, where the
    stress is approximately uniform through the wall). For thicker walls
    use Lamé's equations — out of scope for v1.
    """
    if wall_thickness_mm <= 0 or internal_radius_mm <= 0 or safety_factor <= 0:
        raise ValueError("wall_thickness_mm, internal_radius_mm, safety_factor must be positive")
    if internal_pressure_pa < 0:
        raise ValueError("internal_pressure_pa must be non-negative")

    mat = get_material(material)
    yield_mpa = mat.yield_mpa
    allowable_mpa = yield_mpa / safety_factor

    # Pa = N/m² = N/m² × (1 m / 1000 mm)² = (10⁻⁶) N/mm² → MPa.
    p_mpa = internal_pressure_pa * 1e-6
    hoop_mpa = p_mpa * internal_radius_mm / wall_thickness_mm

    is_thin_wall = wall_thickness_mm < (internal_radius_mm / 10.0)

    rule = "pressure_vessel_hoop"
    evidence = {
        "wall_thickness_mm": wall_thickness_mm,
        "internal_radius_mm": internal_radius_mm,
        "internal_pressure_pa": internal_pressure_pa,
        "material": material,
        "yield_mpa": yield_mpa,
        "safety_factor": safety_factor,
        "allowable_stress_mpa": allowable_mpa,
        "hoop_stress_mpa": hoop_mpa,
        "thin_wall_assumption_valid": is_thin_wall,
        "margin": allowable_mpa / hoop_mpa if hoop_mpa > 0 else math.inf,
    }

    thick_wall_note = (
        "" if is_thin_wall
        else " Note: wall_thickness >= radius/10 — the thin-wall hoop formula under-"
             "estimates peak stress; treat the result as a lower bound."
    )

    if hoop_mpa > yield_mpa:
        return Verdict(
            rule=rule,
            severity=Severity.BLOCK,
            message=(
                f"Hoop stress {hoop_mpa:.2f} MPa exceeds {material} yield "
                f"{yield_mpa:.1f} MPa. Vessel will rupture under this pressure.{thick_wall_note}"
            ),
            evidence=evidence,
            suggested_action=(
                "Thicken the wall (stress scales 1/t) or reduce the radius. "
                "If the design needs to hold this pressure, switch to a "
                "stronger material (PETG/ABS over PLA at temperature)."
            ),
        )
    if hoop_mpa > allowable_mpa:
        return Verdict(
            rule=rule,
            severity=Severity.WARN,
            message=(
                f"Hoop stress {hoop_mpa:.2f} MPa is below {material} yield "
                f"({yield_mpa:.1f} MPa) but exceeds the {safety_factor}× safety "
                f"limit ({allowable_mpa:.1f} MPa). Margin = {evidence['margin']:.2f}.{thick_wall_note}"
            ),
            evidence=evidence,
            suggested_action="Thicken the wall or reduce the operating pressure.",
        )
    return Verdict(
        rule=rule,
        severity=Severity.PASS,
        message=(
            f"Hoop stress {hoop_mpa:.3f} MPa is within {safety_factor}× safety "
            f"margin (allowable {allowable_mpa:.1f} MPa); margin = "
            f"{evidence['margin']:.2f}.{thick_wall_note}"
        ),
        evidence=evidence,
    )
