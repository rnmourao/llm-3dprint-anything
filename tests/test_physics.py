"""Two layers of tests:

  1. Unit tests with a fake simulator — exercises the threshold logic
     (translation/rotation gates) deterministically without launching MuJoCo.
  2. Integration tests with the real default_simulator — confirms an actually-
     grounded design settles, and a known-floating component falls.

Integration tests skip cleanly if MuJoCo isn't importable.
"""

from typing import Optional

import numpy as np
import pytest
import trimesh

from validators import (
    Part,
    Pose,
    Severity,
    SimRequest,
    SimResult,
    check_settles_under_gravity,
    default_simulator,
)


def _box_part(name: str, *, extents=(10, 10, 10), translation=(0, 0, 5)) -> Part:
    m = trimesh.creation.box(extents=extents)
    m.apply_translation(translation)
    return Part(name=name, mesh=m)


def _identity_pose(com_mm) -> Pose:
    return Pose(
        translation_mm=tuple(float(x) for x in com_mm),
        rotation_quat=(0.0, 0.0, 0.0, 1.0),
    )


def _displaced_pose(com_mm, *, dz_mm=0.0, rotation_xyzw=(0.0, 0.0, 0.0, 1.0)) -> Pose:
    return Pose(
        translation_mm=(float(com_mm[0]), float(com_mm[1]), float(com_mm[2] + dz_mm)),
        rotation_quat=rotation_xyzw,
    )


# ----- fake-simulator unit tests -----


def test_no_motion_passes():
    a = _box_part("a")
    fake = lambda req: SimResult(final_poses={"a": _identity_pose(a.mesh.center_mass)})
    [v] = check_settles_under_gravity([a], simulator=fake)
    assert v.severity is Severity.PASS
    assert v.evidence["translation_mm"] == pytest.approx(0.0, abs=1e-6)
    assert v.evidence["rotation_deg"] == pytest.approx(0.0, abs=1e-6)


def test_translation_above_threshold_warns():
    a = _box_part("a")
    fake = lambda req: SimResult(final_poses={
        "a": _displaced_pose(a.mesh.center_mass, dz_mm=-8.0)  # fell 8 mm
    })
    [v] = check_settles_under_gravity([a], simulator=fake, max_translation_mm=1.0)
    assert v.severity is Severity.WARN
    assert v.evidence["translation_mm"] == pytest.approx(8.0, rel=1e-6)
    assert "drifted" in v.message
    assert "another part" in v.suggested_action


def test_rotation_above_threshold_warns():
    a = _box_part("a")
    # 30° rotation about z: quat = (0, 0, sin(15°), cos(15°))
    angle_rad = np.radians(30.0)
    quat = (0.0, 0.0, float(np.sin(angle_rad / 2)), float(np.cos(angle_rad / 2)))
    fake = lambda req: SimResult(final_poses={
        "a": Pose(translation_mm=tuple(a.mesh.center_mass), rotation_quat=quat)
    })
    [v] = check_settles_under_gravity([a], simulator=fake, max_rotation_deg=5.0)
    assert v.severity is Severity.WARN
    assert v.evidence["rotation_deg"] == pytest.approx(30.0, rel=1e-3)


def test_translation_within_tolerance_passes():
    a = _box_part("a")
    fake = lambda req: SimResult(final_poses={
        "a": _displaced_pose(a.mesh.center_mass, dz_mm=-0.5)  # numerical settling
    })
    [v] = check_settles_under_gravity([a], simulator=fake, max_translation_mm=1.0)
    assert v.severity is Severity.PASS


def test_missing_pose_blocks():
    a = _box_part("a")
    fake = lambda req: SimResult(final_poses={})  # simulator returned nothing for "a"
    [v] = check_settles_under_gravity([a], simulator=fake)
    assert v.severity is Severity.BLOCK
    assert "no pose" in v.message


def test_empty_parts_returns_empty():
    fake = lambda req: SimResult(final_poses={})
    assert check_settles_under_gravity([], simulator=fake) == []


def test_multiple_parts_one_passes_one_warns():
    a = _box_part("grounded", translation=(0, 0, 5))   # COM at (0,0,5)
    b = _box_part("floating", translation=(20, 0, 50)) # COM at (20,0,50) — far up
    fake = lambda req: SimResult(final_poses={
        "grounded": _identity_pose(a.mesh.center_mass),
        # `floating` falls and lands on the bed
        "floating": _displaced_pose(b.mesh.center_mass, dz_mm=-45.0),
    })
    verdicts = check_settles_under_gravity([a, b], simulator=fake)
    by_rule = {v.rule: v for v in verdicts}
    assert by_rule["physics_settles:grounded"].severity is Severity.PASS
    assert by_rule["physics_settles:floating"].severity is Severity.WARN
    assert by_rule["physics_settles:floating"].evidence["translation_mm"] == pytest.approx(45.0)


def test_request_propagates_inter_part_collision_flag():
    """The flag passes through to the simulator unchanged."""
    a = _box_part("a")
    captured = {}

    def fake(req: SimRequest) -> SimResult:
        captured["icp"] = req.inter_part_collision
        return SimResult(final_poses={"a": _identity_pose(a.mesh.center_mass)})

    check_settles_under_gravity([a], simulator=fake, inter_part_collision=True)
    assert captured["icp"] is True
    check_settles_under_gravity([a], simulator=fake, inter_part_collision=False)
    assert captured["icp"] is False


# ----- real-MuJoCo integration tests -----


mujoco = pytest.importorskip("mujoco")


def _mesh_at_z(z_min: float, *, side=4.0, height=4.0) -> trimesh.Trimesh:
    m = trimesh.creation.box(extents=(side, side, height))
    m.apply_translation((0, 0, z_min + height / 2))
    return m


def test_real_sim_grounded_box_settles():
    """A box already on the bed should not move appreciably under gravity."""
    part = Part(name="block", mesh=_mesh_at_z(0.0))
    [v] = check_settles_under_gravity(
        [part],
        duration_s=0.5,
        max_translation_mm=1.0,
        max_rotation_deg=5.0,
    )
    assert v.severity is Severity.PASS, v.message


def test_real_sim_floating_box_falls():
    """A box held 8 mm above the bed should fall and trigger a WARN."""
    part = Part(name="floater", mesh=_mesh_at_z(8.0))
    [v] = check_settles_under_gravity(
        [part],
        duration_s=1.0,
        max_translation_mm=1.0,
        max_rotation_deg=5.0,
    )
    assert v.severity is Severity.WARN, v.message
    # Bottom started at z=8; after fall the box settles on the bed (bottom at z=0),
    # so its COM travels ~8 mm. Allow tolerance for settling dynamics.
    assert v.evidence["translation_mm"] == pytest.approx(8.0, abs=0.5)


def test_real_sim_unsupported_axis_raises():
    """v1 default_simulator only handles -z gravity; +z should raise."""
    part = Part(name="x", mesh=_mesh_at_z(0.0))
    with pytest.raises(NotImplementedError, match="-z"):
        check_settles_under_gravity([part], gravity_axis="+z", duration_s=0.1)
