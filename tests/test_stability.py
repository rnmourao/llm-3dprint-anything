import numpy as np
import pytest
import trimesh

from validators import Severity, check_grounded, check_static_stability


def _box_on_bed(extents=(10, 10, 10)) -> trimesh.Trimesh:
    """Box centred at origin in xy, sitting on z=0 plane."""
    m = trimesh.creation.box(extents=extents)
    m.apply_translation((0, 0, extents[2] / 2))
    return m


def _l_shape(arm_y_translation: float = 4.5) -> trimesh.Trimesh:
    """1×1×10 column on the bed + a 1×10×1 arm extending in +y at the top.

    With arm_y_translation = 4.5, the arm's centre is at y=4.5 and its tip
    reaches y=9.5, dragging the COM well outside the column's 1×1 footprint.
    """
    column = trimesh.creation.box(extents=(1, 1, 10))
    column.apply_translation((0, 0, 5))
    arm = trimesh.creation.box(extents=(1, 10, 1))
    arm.apply_translation((0, arm_y_translation, 9.5))
    return trimesh.util.concatenate([column, arm])


def _tetra_apex_down() -> trimesh.Trimesh:
    """Tetrahedron with apex at origin (z=0), base at z=1. Single contact point."""
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 1.0],
            [-0.5, 0.866, 1.0],
            [-0.5, -0.866, 1.0],
        ]
    )
    faces = np.array(
        [
            [0, 1, 2],
            [0, 2, 3],
            [0, 3, 1],
            [1, 3, 2],
        ]
    )
    return trimesh.Trimesh(vertices=vertices, faces=faces)


# ----- happy path -----


def test_centered_box_passes():
    v = check_static_stability(_box_on_bed())
    assert v.severity is Severity.PASS
    assert v.evidence["n_contact_points"] == 4
    assert v.evidence["com_projected_mm"] == pytest.approx([0.0, 0.0], abs=1e-6)
    assert v.evidence["support_polygon_area_mm2"] == pytest.approx(100.0, rel=1e-3)


# ----- tippy geometry -----


def test_l_shape_tips_over_warns():
    v = check_static_stability(_l_shape())
    assert v.severity is Severity.WARN
    assert "OUTSIDE" in v.message
    # COM should be at +y (where the arm extends)
    assert v.evidence["com_projected_mm"][1] > 0.5  # outside the 1x1 base


def test_l_shape_with_short_arm_passes():
    """If the arm is short enough that COM stays over the base, it's stable."""
    v = check_static_stability(_l_shape(arm_y_translation=0.0))  # arm centred over base
    assert v.severity is Severity.PASS


# ----- degenerate contact -----


def test_no_contact_warns():
    box = trimesh.creation.box(extents=(1, 1, 1))
    box.apply_translation((0, 0, 5))  # bottom at z=4.5, well above bed_z=0
    v = check_static_stability(box, bed_z=0.0)
    assert v.severity is Severity.WARN
    assert "does not rest" in v.message
    assert v.evidence["n_contact_points"] == 0


def test_single_contact_point_warns():
    v = check_static_stability(_tetra_apex_down())
    assert v.severity is Severity.WARN
    assert "point" in v.message
    assert v.evidence["n_contact_points"] == 1


# ----- API edges -----


def test_unknown_axis_raises():
    with pytest.raises(ValueError, match="Unknown gravity axis"):
        check_static_stability(_box_on_bed(), gravity_axis="-w")


def test_alternative_gravity_axis_horizontal():
    """Object lying on its side: gravity along -y, so the bed is the y=min plane."""
    box = trimesh.creation.box(extents=(10, 10, 10))
    box.apply_translation((0, 5, 0))  # bottom (in y) at y=0
    v = check_static_stability(box, gravity_axis="-y")
    assert v.severity is Severity.PASS
    assert v.evidence["gravity_axis"] == "-y"
    assert v.evidence["bed_z"] == pytest.approx(0.0, abs=1e-6)


def test_explicit_bed_z_overrides_inference():
    box = _box_on_bed()  # bottom at z=0
    # Set bed_z=-1: now no vertices are within 0.1mm of bed → no contact
    v = check_static_stability(box, bed_z=-1.0)
    assert v.evidence["bed_z"] == -1.0
    assert v.evidence["n_contact_points"] == 0


# ----- check_grounded -----


def test_grounded_single_box_on_bed_passes():
    v = check_grounded(_box_on_bed())
    assert v.severity is Severity.PASS
    assert v.evidence["components"] == 1


def test_grounded_two_components_both_on_bed_passes():
    a = _box_on_bed(extents=(2, 2, 2))
    b = _box_on_bed(extents=(2, 2, 2))
    b.apply_translation((10, 0, 0))  # disjoint in xy, both at z=0
    combined = trimesh.util.concatenate([a, b])
    v = check_grounded(combined)
    assert v.severity is Severity.PASS
    assert v.evidence["components"] == 2


def test_grounded_floating_component_warns():
    grounded = _box_on_bed(extents=(2, 2, 2))
    floating = trimesh.creation.box(extents=(2, 2, 2))
    floating.apply_translation((10, 0, 5))  # z-bottom = 4 → 4 mm above bed
    combined = trimesh.util.concatenate([grounded, floating])

    v = check_grounded(combined)
    assert v.severity is Severity.WARN
    assert "floating" in v.message.lower()
    assert v.evidence["components"] == 2
    assert len(v.evidence["floating"]) == 1
    flt = v.evidence["floating"][0]
    assert flt["distance_above_bed_mm"] == pytest.approx(4.0, abs=1e-6)


def test_grounded_all_floating_warns():
    a = trimesh.creation.box(extents=(1, 1, 1))
    b = trimesh.creation.box(extents=(1, 1, 1))
    a.apply_translation((0, 0, 5))
    b.apply_translation((10, 0, 5))
    combined = trimesh.util.concatenate([a, b])

    # bed_z=0 explicit; both components 4.5 mm above
    v = check_grounded(combined, bed_z=0.0)
    assert v.severity is Severity.WARN
    assert len(v.evidence["floating"]) == 2


def test_grounded_alternative_gravity_axis():
    """Object on its side: bed is the y=0 plane. One component touches it,
    the other is offset in +y."""
    a = trimesh.creation.box(extents=(2, 2, 2))
    a.apply_translation((0, 1, 0))  # y=0 to y=2 — touches bed at y=0
    b = trimesh.creation.box(extents=(2, 2, 2))
    b.apply_translation((0, 5, 0))  # y=4 to y=6 — floating 4 mm
    combined = trimesh.util.concatenate([a, b])
    v = check_grounded(combined, gravity_axis="-y")
    assert v.severity is Severity.WARN
    assert v.evidence["components"] == 2


def test_grounded_unknown_axis_raises():
    with pytest.raises(ValueError, match="Unknown gravity axis"):
        check_grounded(_box_on_bed(), gravity_axis="diagonal")


def test_peg_on_bed_with_socket_above_warns():
    """Re-creates the smoke-test bug: peg at z=0..14, socket at z=8..14
    (floating). Validator should flag the socket."""
    peg = trimesh.creation.cylinder(radius=3, height=14)
    peg.apply_translation((0, 0, 7))  # base at z=0, top at z=14
    plate = trimesh.creation.box(extents=(30, 30, 6))
    plate.apply_translation((0, 0, 11))  # bottom at z=8, top at z=14
    assembly = trimesh.util.concatenate([peg, plate])

    v = check_grounded(assembly)
    assert v.severity is Severity.WARN
    floating = v.evidence["floating"]
    assert len(floating) == 1
    assert floating[0]["distance_above_bed_mm"] == pytest.approx(8.0, abs=1e-6)


def test_grounded_ignores_hollow_body_internal_cavity():
    """Hollow bottle: a single physical part with an internal void. trimesh.split
    returns two connected components — the outer shell and the inner cavity
    surface — but the void isn't a real part and shouldn't trigger a "floating
    component" WARN. Filter is by volume sign (cavities have inward normals).
    """
    outer = trimesh.creation.box(extents=(20, 20, 20))
    outer.apply_translation((0, 0, 10))  # bottom at z=0
    inner = trimesh.creation.box(extents=(16, 16, 16))
    inner.apply_translation((0, 0, 10))  # entirely inside outer
    hollow = outer.difference(inner)

    v = check_grounded(hollow)
    assert v.severity is Severity.PASS, v.message
    assert v.evidence["components"] == 1  # the void is filtered out
