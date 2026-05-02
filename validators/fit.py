"""Mating-feature clearance / fit check (study 02).

For each pair of mating parts the user supplies a fit class — RC/LC/LT for
clearance fits (positive gap, parts don't touch) or LN/FN for interference
fits (negative gap, parts overlap by a controlled amount).

The validator computes the minimum signed distance between the two meshes:
    > 0 → parts are separated by this distance (clearance).
    < 0 → parts overlap; magnitude is the maximum penetration depth.

…and compares the result to the spec range for the named fit class.

Sampling is vertex-only — adequate for typical FDM mating geometry (posts,
sockets, bosses) where vertices densely populate the contact region.
Pathological cases (large coplanar shared faces) can under-report
penetration; document and revisit if it bites.

PRECONDITION: both meshes must be watertight and winding-consistent — the
signed-distance sign is undefined otherwise. Run check_mesh_integrity first.

The clearance table below is FDM-adjusted (PLA, ~0.4 mm nozzle), NOT ANSI
B4.1 — 3D-printed parts have very different tolerance behaviour from
machined ones. Per study 02, statistical (RSS / Monte Carlo) stack-ups are
explicitly out of scope for v1: FDM tolerance distributions aren't Gaussian.
"""

from __future__ import annotations

import trimesh

from .types import Part, Severity, Verdict


# (min_gap_mm, max_gap_mm). Negative values denote interference (overlap).
FIT_CLEARANCES_MM_FDM_PLA: dict[str, tuple[float, float]] = {
    "RC": (0.30, 0.50),    # Running clearance — rotating parts
    "LC": (0.20, 0.30),    # Locational clearance — easy slip-fit
    "LT": (0.10, 0.20),    # Locational transition — snug
    "LN": (-0.05, 0.05),   # Locational interference — borderline / press-aligned
    "FN": (-0.20, -0.10),  # Force / shrink fit — permanent press fit
}


def _gap_or_overlap(a: trimesh.Trimesh, b: trimesh.Trimesh) -> float:
    """Single scalar describing the contact state of two meshes.

      > 0 → clearance (the closest gap between surfaces, in mm)
      < 0 → overlap   (the deepest vertex penetration, in mm)
      = 0 → surfaces touch

    Trimesh's `signed_distance` returns positive INSIDE the mesh and negative
    OUTSIDE — the opposite of our preferred semantics — so we take the max
    (deepest interior vertex if any, else closest exterior vertex) and negate.
    """
    sd_a = trimesh.proximity.signed_distance(b, a.vertices)
    sd_b = trimesh.proximity.signed_distance(a, b.vertices)
    deepest = max(float(sd_a.max()), float(sd_b.max()))
    return -deepest


def check_clearance(part_a: Part, part_b: Part, fit_class: str) -> Verdict:
    if fit_class not in FIT_CLEARANCES_MM_FDM_PLA:
        valid = ", ".join(sorted(FIT_CLEARANCES_MM_FDM_PLA))
        raise ValueError(f"Unknown fit_class {fit_class!r}; expected one of: {valid}")

    spec_min, spec_max = FIT_CLEARANCES_MM_FDM_PLA[fit_class]
    actual = _gap_or_overlap(part_a.mesh, part_b.mesh)
    pair = tuple(sorted((part_a.name, part_b.name)))
    rule = f"clearance:{pair[0]}~{pair[1]}"

    evidence = {
        "fit_class": fit_class,
        "spec_min_mm": spec_min,
        "spec_max_mm": spec_max,
        "actual_mm": actual,
    }

    if actual < spec_min:
        # too tight: gap smaller than spec, or interference larger than spec
        diagnosis = (
            "Parts overlap too aggressively." if actual < 0
            else "Parts will not assemble — gap too small."
        )
        return Verdict(
            rule=rule,
            severity=Severity.BLOCK,
            message=(
                f"{part_a.name}/{part_b.name} {fit_class} fit: actual gap "
                f"{actual:.3f} mm is below spec minimum {spec_min:.3f} mm. {diagnosis}"
            ),
            evidence=evidence,
            suggested_action=(
                f"Open the gap by at least {spec_min - actual:.3f} mm in the source geometry."
            ),
        )

    if actual > spec_max:
        # too loose: gap larger than spec, or interference smaller than spec
        diagnosis = (
            "Parts may rattle." if spec_max > 0
            else "Interference is too small to hold — joint will work loose."
        )
        return Verdict(
            rule=rule,
            severity=Severity.WARN,
            message=(
                f"{part_a.name}/{part_b.name} {fit_class} fit: actual gap "
                f"{actual:.3f} mm exceeds spec maximum {spec_max:.3f} mm. {diagnosis}"
            ),
            evidence=evidence,
            suggested_action=(
                f"Close the gap by at least {actual - spec_max:.3f} mm in the source geometry."
            ),
        )

    return Verdict(
        rule=rule,
        severity=Severity.PASS,
        message=(
            f"{part_a.name}/{part_b.name} {fit_class} fit: actual gap "
            f"{actual:.3f} mm is within spec ({spec_min:.3f} to {spec_max:.3f} mm)."
        ),
        evidence=evidence,
    )
