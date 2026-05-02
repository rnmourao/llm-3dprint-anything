"""Hard clash detection — pairwise volumetric intersection between parts.

Two-pass design (study 03):
  Broad phase  — AABB overlap. Prunes pairs that can't possibly clash.
  Narrow phase — boolean intersection volume. Must exceed min_volume_mm3
                 to count, suppressing numerical-precision sliver noise.

Whitelist (study 01) — a set of name pairs that are *intended* to interpenetrate
(screw boss into a receiving boss, dovetail joint, threaded fastener). The
LLM populates this from OpenSCAD intent annotations; the validator never
guesses.

Soft clash (clearance / fit) lives in fit.py — same machinery but with one
mesh inflated by the fit-class gap.
"""

from __future__ import annotations

import itertools

import trimesh

from .types import Part, Severity, Verdict


def _aabb_overlap(a: trimesh.Trimesh, b: trimesh.Trimesh) -> bool:
    a_min, a_max = a.bounds
    b_min, b_max = b.bounds
    return bool((a_min <= b_max).all() and (b_min <= a_max).all())


def _intersection_volume(a: trimesh.Trimesh, b: trimesh.Trimesh) -> float:
    inter = trimesh.boolean.intersection([a, b])
    if inter is None or inter.is_empty:
        return 0.0
    return float(inter.volume)


def _pair_rule(name_a: str, name_b: str) -> tuple[str, tuple[str, str]]:
    pair = tuple(sorted((name_a, name_b)))
    return f"hard_clash:{pair[0]}~{pair[1]}", pair


def check_hard_clash(
    parts: list[Part],
    *,
    min_volume_mm3: float = 0.01,
    whitelist: set[tuple[str, str]] | None = None,
) -> list[Verdict]:
    """Run hard clash detection on every unordered pair in `parts`.

    Returns one Verdict per pair, with stable rule keys of the form
    `hard_clash:<a>~<b>` (names sorted lexicographically). The shape of the
    output is always pair-symmetric; tests can assert on rule keys directly.
    """
    names = [p.name for p in parts]
    if len(set(names)) != len(names):
        raise ValueError(f"Part names must be unique; got {names}")

    wl = {tuple(sorted(p)) for p in (whitelist or set())}
    verdicts: list[Verdict] = []

    for a, b in itertools.combinations(parts, 2):
        rule, pair = _pair_rule(a.name, b.name)

        if pair in wl:
            verdicts.append(Verdict(
                rule=rule,
                severity=Severity.PASS,
                message=f"{a.name} and {b.name} intersect by design (whitelisted).",
                evidence={"whitelisted": True},
            ))
            continue

        if not _aabb_overlap(a.mesh, b.mesh):
            verdicts.append(Verdict(
                rule=rule,
                severity=Severity.PASS,
                message=f"{a.name} and {b.name} have disjoint bounding boxes.",
                evidence={"phase": "broad", "aabb_overlap": False},
            ))
            continue

        volume = _intersection_volume(a.mesh, b.mesh)
        if volume < min_volume_mm3:
            verdicts.append(Verdict(
                rule=rule,
                severity=Severity.PASS,
                message=(
                    f"{a.name} and {b.name} intersect at {volume:.4g} mm³, "
                    f"below the {min_volume_mm3} mm³ noise threshold."
                ),
                evidence={
                    "phase": "narrow",
                    "intersection_volume_mm3": volume,
                    "min_volume_mm3": min_volume_mm3,
                },
            ))
            continue

        verdicts.append(Verdict(
            rule=rule,
            severity=Severity.BLOCK,
            message=f"{a.name} and {b.name} interpenetrate by {volume:.4g} mm³.",
            evidence={
                "phase": "narrow",
                "intersection_volume_mm3": volume,
            },
            suggested_action=(
                f"If intentional, add ('{a.name}', '{b.name}') to the whitelist; "
                "otherwise edit the geometry to separate the parts."
            ),
        ))

    return verdicts
