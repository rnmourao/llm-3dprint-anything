"""Mesh-integrity checks (study 03).

Implemented in pure Trimesh. Two MeshLib-style defects are intentionally
absent from v1 because they require a stronger backend (manifold3d /
MeshLib / pymeshlab) — adding stubs would lie about coverage:
  * non-manifold *vertices* (vertex fans split into disjoint components)
  * self-intersections (faces crossing without sharing edges)

When those are added, follow the same Verdict pattern below.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
from trimesh import repair

from .types import Severity, Verdict


def _load(stl_path: Path) -> trimesh.Trimesh:
    mesh = trimesh.load(str(stl_path), force="mesh")
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError(
            f"{stl_path}: expected a single Trimesh, got {type(mesh).__name__}"
        )
    return mesh


def _edge_anomalies(mesh: trimesh.Trimesh) -> tuple[int, int]:
    """Return (non_manifold_edge_count, boundary_edge_count).

    An edge shared by 1 face is a boundary edge (hole); >2 faces is non-manifold.
    """
    edges_sorted = np.sort(mesh.edges, axis=1)
    _, counts = np.unique(edges_sorted, axis=0, return_counts=True)
    non_manifold = int((counts > 2).sum())
    boundary = int((counts == 1).sum())
    return non_manifold, boundary


def check_mesh_integrity(stl_path: Path | str) -> list[Verdict]:
    """Check mesh integrity. Returns one Verdict per rule, always the same set,
    so the report shape is stable across runs.
    """
    stl_path = Path(stl_path)
    mesh = _load(stl_path)
    verdicts: list[Verdict] = []
    non_manifold_edges, boundary_edges = _edge_anomalies(mesh)

    if mesh.is_watertight:
        verdicts.append(Verdict(
            rule="mesh_watertight",
            severity=Severity.PASS,
            message="Mesh is watertight.",
            evidence={"boundary_edges": 0},
        ))
    else:
        verdicts.append(Verdict(
            rule="mesh_watertight",
            severity=Severity.BLOCK,
            message=f"Mesh is not watertight ({boundary_edges} boundary edges). Slicer will reject.",
            evidence={"boundary_edges": boundary_edges},
            suggested_action="Run repair_mesh() to attempt automatic hole-filling.",
        ))

    if mesh.is_winding_consistent:
        verdicts.append(Verdict(
            rule="mesh_winding_consistent",
            severity=Severity.PASS,
            message="Face winding is consistent.",
        ))
    else:
        verdicts.append(Verdict(
            rule="mesh_winding_consistent",
            severity=Severity.WARN,
            message="Face winding is inconsistent; some normals are flipped.",
            suggested_action="Run repair_mesh() to fix winding.",
        ))

    if non_manifold_edges == 0:
        verdicts.append(Verdict(
            rule="mesh_non_manifold_edges",
            severity=Severity.PASS,
            message="No non-manifold edges.",
            evidence={"non_manifold_edges": 0},
        ))
    else:
        verdicts.append(Verdict(
            rule="mesh_non_manifold_edges",
            severity=Severity.BLOCK,
            message=(
                f"{non_manifold_edges} non-manifold edges (each shared by 3+ faces). "
                "Slicers will reject this mesh."
            ),
            evidence={"non_manifold_edges": non_manifold_edges},
            suggested_action=(
                "Edit the source geometry. repair_mesh(allow_destructive=True) "
                "will delete the offending triangles, which may alter your design."
            ),
        ))

    return verdicts


def repair_mesh(
    stl_path: Path | str,
    *,
    output_path: Path | str | None = None,
    allow_destructive: bool = True,
) -> tuple[Path, list[Verdict]]:
    """Apply best-effort automatic repairs and write a new STL.

    Returns (output_path, verdicts). Verdicts describe every alteration
    so the user can see what changed — MeshLib's own caveat applies:
    repair "can remove or alter parts of the geometry you expected to keep."

    Repair order: winding → normals → drop non-manifold faces (destructive)
    → fill holes (closes any holes, including ones just created).
    """
    stl_path = Path(stl_path)
    mesh = _load(stl_path)
    verdicts: list[Verdict] = []

    if not mesh.is_winding_consistent:
        repair.fix_winding(mesh)
        verdicts.append(Verdict(
            rule="mesh_winding_consistent",
            severity=Severity.AUTO_REPAIRED,
            message="Fixed inconsistent face winding.",
        ))

    repair.fix_inversion(mesh)
    repair.fix_normals(mesh)

    non_manifold_before, _ = _edge_anomalies(mesh)
    if non_manifold_before > 0:
        if allow_destructive:
            edges_sorted = np.sort(mesh.edges, axis=1)
            _, inverse, counts = np.unique(
                edges_sorted, axis=0, return_inverse=True, return_counts=True
            )
            bad_face_mask = (counts > 2)[inverse].reshape(-1, 3).any(axis=1)
            n_dropped = int(bad_face_mask.sum())
            mesh.update_faces(~bad_face_mask)
            mesh.remove_unreferenced_vertices()
            non_manifold_after, _ = _edge_anomalies(mesh)
            verdicts.append(Verdict(
                rule="mesh_non_manifold_edges",
                severity=Severity.AUTO_REPAIRED,
                message=(
                    f"Removed {n_dropped} face(s) touching non-manifold edges. "
                    f"Mesh may now have new boundary edges."
                ),
                evidence={
                    "non_manifold_edges_before": non_manifold_before,
                    "non_manifold_edges_after": non_manifold_after,
                    "faces_removed": n_dropped,
                },
                suggested_action="Re-run check_mesh_integrity; new holes may need filling.",
            ))
        else:
            verdicts.append(Verdict(
                rule="mesh_non_manifold_edges",
                severity=Severity.WARN,
                message=(
                    f"{non_manifold_before} non-manifold edges; "
                    "allow_destructive=False so left as-is."
                ),
                evidence={"non_manifold_edges": non_manifold_before},
                suggested_action="Set allow_destructive=True or repair the source geometry.",
            ))

    if not mesh.is_watertight:
        _, boundary_before = _edge_anomalies(mesh)
        filled = bool(repair.fill_holes(mesh))
        _, boundary_after = _edge_anomalies(mesh)
        verdicts.append(Verdict(
            rule="mesh_watertight",
            severity=Severity.AUTO_REPAIRED if filled else Severity.WARN,
            message=(
                f"Filled holes: {boundary_before} → {boundary_after} boundary edges."
                if filled else
                f"Could not auto-fill all holes; {boundary_after} boundary edges remain."
            ),
            evidence={
                "boundary_edges_before": boundary_before,
                "boundary_edges_after": boundary_after,
            },
            suggested_action=(
                "" if filled else "Inspect the source; complex holes need manual repair."
            ),
        ))

    out = Path(output_path) if output_path else stl_path.with_stem(stl_path.stem + "_repaired")
    mesh.export(str(out))
    return out, verdicts
