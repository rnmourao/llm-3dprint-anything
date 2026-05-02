from pathlib import Path

import numpy as np
import pytest
import trimesh

from validators import Severity, check_mesh_integrity, repair_mesh


def _verdict(verdicts, rule):
    matches = [v for v in verdicts if v.rule == rule]
    assert len(matches) == 1, f"expected one verdict for {rule}, got {len(matches)}"
    return matches[0]


def _save(mesh: trimesh.Trimesh, tmp_path: Path, name: str = "in.stl") -> Path:
    p = tmp_path / name
    mesh.export(str(p))
    return p


def _box_with_hole() -> trimesh.Trimesh:
    box = trimesh.creation.box(extents=(10, 10, 10))
    keep = np.ones(len(box.faces), dtype=bool)
    keep[0] = False
    box.update_faces(keep)
    return box


def _fan_with_extra() -> trimesh.Trimesh:
    """Three triangles share edge (0,1) — non-manifold. Plus one unrelated
    triangle so the mesh isn't empty after destructive repair drops the fan.
    """
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, -1.0, 0.0],
            [0.0, 0.0, 1.0],
            [5.0, 5.0, 5.0],
            [6.0, 5.0, 5.0],
            [5.0, 6.0, 5.0],
        ]
    )
    faces = np.array(
        [
            [0, 1, 2],
            [0, 1, 3],
            [0, 1, 4],
            [5, 6, 7],
        ]
    )
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


# ----- check_mesh_integrity -----


def test_clean_box_all_pass(tmp_path):
    stl = _save(trimesh.creation.box(extents=(10, 10, 10)), tmp_path)
    verdicts = check_mesh_integrity(stl)
    assert {v.rule for v in verdicts} == {
        "mesh_watertight",
        "mesh_winding_consistent",
        "mesh_non_manifold_edges",
    }
    for v in verdicts:
        assert v.severity is Severity.PASS, f"{v.rule}: {v.severity} — {v.message}"


def test_missing_face_blocks_watertight(tmp_path):
    stl = _save(_box_with_hole(), tmp_path)
    verdicts = check_mesh_integrity(stl)

    watertight = _verdict(verdicts, "mesh_watertight")
    assert watertight.severity is Severity.BLOCK
    assert watertight.evidence["boundary_edges"] == 3

    assert _verdict(verdicts, "mesh_non_manifold_edges").severity is Severity.PASS


def test_inconsistent_winding_warns(tmp_path):
    box = trimesh.creation.box(extents=(10, 10, 10))
    faces = box.faces.copy()
    faces[0] = faces[0][::-1]
    bad = trimesh.Trimesh(vertices=box.vertices, faces=faces, process=False)
    stl = _save(bad, tmp_path)

    verdicts = check_mesh_integrity(stl)
    assert _verdict(verdicts, "mesh_winding_consistent").severity is Severity.WARN


def test_non_manifold_edge_blocks(tmp_path):
    stl = _save(_fan_with_extra(), tmp_path)
    verdicts = check_mesh_integrity(stl)

    nm = _verdict(verdicts, "mesh_non_manifold_edges")
    assert nm.severity is Severity.BLOCK
    assert nm.evidence["non_manifold_edges"] >= 1


# ----- repair_mesh -----


def test_repair_fills_simple_hole(tmp_path):
    stl = _save(_box_with_hole(), tmp_path)
    out, verdicts = repair_mesh(stl)

    assert out.exists()
    watertight_repair = _verdict(verdicts, "mesh_watertight")
    assert watertight_repair.severity is Severity.AUTO_REPAIRED
    assert watertight_repair.evidence["boundary_edges_after"] == 0

    after = check_mesh_integrity(out)
    assert _verdict(after, "mesh_watertight").severity is Severity.PASS


def test_repair_drops_non_manifold_faces(tmp_path):
    stl = _save(_fan_with_extra(), tmp_path)
    _, verdicts = repair_mesh(stl, allow_destructive=True)

    nm_repair = _verdict(verdicts, "mesh_non_manifold_edges")
    assert nm_repair.severity is Severity.AUTO_REPAIRED
    assert nm_repair.evidence["faces_removed"] >= 3
    assert nm_repair.evidence["non_manifold_edges_after"] == 0


def test_repair_non_destructive_preserves_non_manifold(tmp_path):
    stl = _save(_fan_with_extra(), tmp_path)
    _, verdicts = repair_mesh(stl, allow_destructive=False)

    nm = _verdict(verdicts, "mesh_non_manifold_edges")
    assert nm.severity is Severity.WARN
    assert nm.evidence["non_manifold_edges"] >= 1
