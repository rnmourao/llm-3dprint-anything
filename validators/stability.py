"""Static stability — does the object stand up under gravity?

Two distinct rules live here:

  `stability_com_over_support` — does the assembly as a whole tip?
      Project the COM onto the bed plane; check it lies inside the convex
      hull of contact points (the support polygon).

  `stability_grounded` — is every part physically supported?
      Split the mesh into connected components; each must have its
      extreme vertex on the gravity axis within `bed_tol_mm` of the bed
      plane. Catches "floating part" design errors that the COM check
      would miss.

PRECONDITION: mesh should be watertight and winding-consistent for
`center_mass` to be physically meaningful. Run check_mesh_integrity first.
"""

from __future__ import annotations

import trimesh
from scipy.spatial import ConvexHull, Delaunay, QhullError

from .types import Severity, Verdict

_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


def _parse_axis(axis: str) -> tuple[int, int]:
    """Return (axis_index, sign) where sign ∈ {-1, +1}.

    "-z" → (2, -1) — gravity points in -z, object rests on its lowest-z face.
    "+z" → (2, +1) — gravity points in +z, object rests on its highest-z face.
    "z" treated as "+z".
    """
    s = axis.strip().lower()
    if s and s[0] in "+-":
        sign = -1 if s[0] == "-" else 1
        letter = s[1:]
    else:
        sign = 1
        letter = s
    if letter not in _AXIS_INDEX:
        raise ValueError(f"Unknown gravity axis {axis!r}; expected ±x/y/z")
    return _AXIS_INDEX[letter], sign


def check_static_stability(
    mesh: trimesh.Trimesh,
    *,
    gravity_axis: str = "-z",
    bed_z: float | None = None,
    bed_tol_mm: float = 0.1,
) -> Verdict:
    rule = "stability_com_over_support"
    axis, sign = _parse_axis(gravity_axis)
    plane_axes = [a for a in (0, 1, 2) if a != axis]

    vertical = mesh.vertices[:, axis]
    if bed_z is None:
        bed_z = float(vertical.min() if sign == -1 else vertical.max())

    if sign == -1:
        contact_mask = vertical <= (bed_z + bed_tol_mm)
    else:
        contact_mask = vertical >= (bed_z - bed_tol_mm)

    contact_points_2d = mesh.vertices[contact_mask][:, plane_axes]
    n = len(contact_points_2d)

    com_3d = mesh.center_mass
    com_2d = com_3d[plane_axes]

    evidence = {
        "gravity_axis": gravity_axis,
        "bed_z": float(bed_z),
        "n_contact_points": int(n),
        "com_projected_mm": [float(c) for c in com_2d],
    }

    if n == 0:
        return Verdict(
            rule=rule,
            severity=Severity.WARN,
            message=(
                f"No vertices within {bed_tol_mm} mm of the bed plane "
                f"(bed_z={bed_z:.3f}). The mesh does not rest on the bed."
            ),
            evidence=evidence,
            suggested_action="Confirm orientation; reposition so the mesh touches the bed.",
        )

    if n < 3:
        kind = "point" if n == 1 else "line"
        return Verdict(
            rule=rule,
            severity=Severity.WARN,
            message=(
                f"Only {n} contact point(s); support is a {kind}, not an area. "
                "Object will balance precariously."
            ),
            evidence=evidence,
            suggested_action="Flatten the bottom or add a base to widen the support footprint.",
        )

    try:
        hull = ConvexHull(contact_points_2d)
    except QhullError as e:
        return Verdict(
            rule=rule,
            severity=Severity.WARN,
            message=(
                f"Contact points are degenerate (colinear or near-colinear). "
                f"Support polygon has zero area. ({e})"
            ),
            evidence=evidence,
            suggested_action="Widen the contact area so the support polygon has nonzero area.",
        )

    hull_verts = contact_points_2d[hull.vertices]
    inside = bool(Delaunay(hull_verts).find_simplex(com_2d) >= 0)
    evidence["support_polygon_area_mm2"] = float(hull.volume)

    if inside:
        return Verdict(
            rule=rule,
            severity=Severity.PASS,
            message=(
                f"COM projects to ({com_2d[0]:.2f}, {com_2d[1]:.2f}); "
                f"inside the {hull.volume:.1f} mm² support polygon ({n} contacts)."
            ),
            evidence=evidence,
        )

    return Verdict(
        rule=rule,
        severity=Severity.WARN,
        message=(
            f"COM projects to ({com_2d[0]:.2f}, {com_2d[1]:.2f}); "
            f"OUTSIDE the support polygon. Object will tip over under gravity."
        ),
        evidence=evidence,
        suggested_action=(
            "Widen the base, lower the centre of mass, or add ballast on the "
            "side opposite the lean."
        ),
    )


def check_grounded(
    mesh: trimesh.Trimesh,
    *,
    gravity_axis: str = "-z",
    bed_z: Optional[float] = None,
    bed_tol_mm: float = 0.1,
) -> Verdict:
    """Verify every connected component touches the bed plane.

    Splits the mesh into connected components (sets of triangles linked by
    shared edges); each must have its extreme vertex on the gravity axis
    within `bed_tol_mm` of `bed_z`. A component further away is "floating"
    — under gravity it would fall, regardless of where the assembly's
    overall COM projects.

    LIMITATION (v1): does not detect a part supported by *another part*
    rather than directly by the bed (e.g., a screw resting on a flange).
    Modeling stacked-part assemblies as a single watertight mesh works
    around this; a graph-of-supported-components check is future work.
    """
    rule = "stability_grounded"
    axis, sign = _parse_axis(gravity_axis)

    components = mesh.split(only_watertight=False)
    n = len(components)

    if bed_z is None:
        all_vertical = mesh.vertices[:, axis]
        bed_z = float(all_vertical.min() if sign == -1 else all_vertical.max())

    floating: list[dict] = []
    for i, comp in enumerate(components):
        comp_vertical = comp.vertices[:, axis]
        if sign == -1:
            extreme = float(comp_vertical.min())
            distance = extreme - bed_z
        else:
            extreme = float(comp_vertical.max())
            distance = bed_z - extreme
        if distance > bed_tol_mm:
            floating.append({
                "component_index": i,
                "vertex_count": int(len(comp.vertices)),
                "extreme_along_gravity_mm": extreme,
                "distance_above_bed_mm": float(distance),
            })

    evidence = {
        "components": int(n),
        "bed_z": float(bed_z),
        "gravity_axis": gravity_axis,
    }

    if not floating:
        return Verdict(
            rule=rule,
            severity=Severity.PASS,
            message=(
                f"All {n} connected component(s) rest on the bed plane "
                f"(bed_z={bed_z:.3f}, tol={bed_tol_mm:.3f} mm)."
            ),
            evidence=evidence,
        )

    evidence["floating"] = floating
    summary = ", ".join(
        f"#{f['component_index']} {f['distance_above_bed_mm']:.2f} mm above"
        for f in floating
    )
    return Verdict(
        rule=rule,
        severity=Severity.WARN,
        message=(
            f"{len(floating)} of {n} connected components are floating: {summary}. "
            "Under gravity these will fall — the assembly cannot physically rest in this configuration."
        ),
        evidence=evidence,
        suggested_action=(
            "Reposition floating parts to touch the bed, add a shoulder or "
            "ledge for them to rest on, or model interlocking parts as a "
            "single connected mesh."
        ),
    )
