"""Pipeline integration tests using a fake renderer.

The fake renderer is a small dispatcher that maps SCAD call expressions
(`shaft();`, `assembly();`) to pre-built STLs the test sets up. This lets
us cover the full validator-orchestration path without depending on the
`openscad` CLI being installed.
"""

import shutil
from pathlib import Path
from typing import Callable

import pytest
import trimesh

from orchestrator import RenderRequest, run_pipeline
from validators import Pose, Severity, SimRequest, SimResult


def _passthrough_simulator(req: SimRequest) -> SimResult:
    """Test fake: every part returns its starting pose unchanged → all PASS."""
    poses = {
        p.name: Pose(
            translation_mm=tuple(float(x) for x in p.mesh.center_mass),
            rotation_quat=(0.0, 0.0, 0.0, 1.0),
        )
        for p in req.parts
    }
    return SimResult(final_poses=poses)


def _stl_dispatcher(stl_map: dict[str, Path]) -> Callable[[RenderRequest], Path]:
    """Build a fake renderer that maps call_expression → STL fixture path.

    Looks up the call by stripping the trailing `();`.
    """

    def fake(req: RenderRequest) -> Path:
        key = req.call_expression.replace("();", "").strip()
        if key not in stl_map:
            raise RuntimeError(f"fake renderer has no fixture for {key!r}")
        shutil.copy(stl_map[key], req.output_stl)
        return req.output_stl

    return fake


def _box(extents=(1, 1, 1), translation=(0, 0, 0)) -> trimesh.Trimesh:
    m = trimesh.creation.box(extents=extents)
    m.apply_translation(translation)
    return m


# ----- happy path -----


def test_clean_assembly_passes(tmp_path):
    shaft = tmp_path / "shaft.stl"
    hole = tmp_path / "hole.stl"
    asm = tmp_path / "asm.stl"

    s = _box(translation=(0, 0, 0.5))
    h = _box(translation=(1.4, 0, 0.5))
    s.export(shaft)
    h.export(hole)
    trimesh.util.concatenate([s, h]).export(asm)

    scad = tmp_path / "design.scad"
    scad.write_text(
        "// part: shaft\n"
        "// part: hole\n"
        "// fit: shaft~hole class=RC\n"
        "module shaft() {}\n"
        "module hole() {}\n"
        "module assembly() {}\n"
    )

    work = tmp_path / "work"
    report = run_pipeline(
        scad,
        work_dir=work,
        renderer=_stl_dispatcher({"shaft": shaft, "hole": hole, "assembly": asm}),
        simulator=_passthrough_simulator,
    )
    assert report.status is Severity.PASS, report.to_text()


# ----- failure surfaces correctly -----


def test_overlapping_parts_block(tmp_path):
    shaft = tmp_path / "shaft.stl"
    hole = tmp_path / "hole.stl"
    asm = tmp_path / "asm.stl"

    s = _box(translation=(0, 0, 0.5))
    h = _box(translation=(0.5, 0, 0.5))  # 50% overlap
    s.export(shaft)
    h.export(hole)
    trimesh.util.concatenate([s, h]).export(asm)

    scad = tmp_path / "design.scad"
    scad.write_text(
        "// part: shaft\n// part: hole\nmodule x() {}\n"
    )

    report = run_pipeline(
        scad,
        work_dir=tmp_path / "work",
        renderer=_stl_dispatcher({"shaft": shaft, "hole": hole, "assembly": asm}),
        simulator=_passthrough_simulator,
    )
    assert report.has_blockers
    assert any(v.rule.startswith("hard_clash:") for v in report.verdicts)


def test_clash_whitelist_suppresses_block(tmp_path):
    shaft = tmp_path / "shaft.stl"
    hole = tmp_path / "hole.stl"
    asm = tmp_path / "asm.stl"

    s = _box(translation=(0, 0, 0.5))
    h = _box(translation=(0.5, 0, 0.5))
    s.export(shaft)
    h.export(hole)
    trimesh.util.concatenate([s, h]).export(asm)

    scad = tmp_path / "design.scad"
    scad.write_text(
        "// part: shaft\n"
        "// part: hole\n"
        "// clash_whitelist: shaft~hole\n"
    )

    report = run_pipeline(
        scad,
        work_dir=tmp_path / "work",
        renderer=_stl_dispatcher({"shaft": shaft, "hole": hole, "assembly": asm}),
        simulator=_passthrough_simulator,
    )
    # No hard_clash BLOCKer
    blockers = [v for v in report.verdicts if v.severity is Severity.BLOCK]
    assert all(not v.rule.startswith("hard_clash:") for v in blockers)


def test_load_annotation_runs_cantilever(tmp_path):
    arm = tmp_path / "arm.stl"
    asm = tmp_path / "asm.stl"
    a = _box(extents=(1, 1, 1), translation=(0, 0, 0.5))
    a.export(arm)
    a.export(asm)

    scad = tmp_path / "design.scad"
    scad.write_text(
        "// part: arm\n"
        "// load: part=arm force=10 axis=-z length_mm=100 section=rect:1x1\n"
    )
    report = run_pipeline(
        scad,
        work_dir=tmp_path / "work",
        renderer=_stl_dispatcher({"arm": arm, "assembly": asm}),
        simulator=_passthrough_simulator,
    )
    cantilever = [v for v in report.verdicts if v.rule.startswith("cantilever_stress")]
    assert len(cantilever) == 1
    assert cantilever[0].severity is Severity.BLOCK  # 1x1 beam, 100mm, 10N → way over yield


def test_unknown_part_in_fit_blocks(tmp_path):
    arm = tmp_path / "arm.stl"
    asm = tmp_path / "asm.stl"
    _box().export(arm)
    _box().export(asm)

    scad = tmp_path / "design.scad"
    scad.write_text(
        "// part: arm\n"
        "// fit: arm~ghost class=RC\n"
    )
    report = run_pipeline(
        scad,
        work_dir=tmp_path / "work",
        renderer=_stl_dispatcher({"arm": arm, "assembly": asm}),
        simulator=_passthrough_simulator,
    )
    blockers = [v for v in report.verdicts
                if v.severity is Severity.BLOCK and v.rule.startswith("clearance:")]
    assert len(blockers) == 1
    assert "ghost" in blockers[0].message


# ----- structural failures of the pipeline itself -----


def test_no_part_annotations_blocks(tmp_path):
    scad = tmp_path / "design.scad"
    scad.write_text("// just a comment\nmodule foo() {}\n")
    report = run_pipeline(
        scad,
        work_dir=tmp_path / "work",
        renderer=lambda req: req.output_stl,  # never called
        simulator=_passthrough_simulator,
    )
    assert report.has_blockers
    assert any(v.rule == "annotations" for v in report.verdicts)


def test_render_failure_surfaces_as_blocker(tmp_path):
    scad = tmp_path / "design.scad"
    scad.write_text("// part: arm\n")

    def broken_renderer(req: RenderRequest) -> Path:
        raise RuntimeError("synthetic render failure")

    report = run_pipeline(scad, work_dir=tmp_path / "work", renderer=broken_renderer, simulator=_passthrough_simulator)
    assert report.has_blockers
    assert any(v.rule.startswith("render:") for v in report.verdicts)


# ----- heat & pressure annotations drive the new checks -----


def test_operating_temperature_annotation_fires_per_part(tmp_path):
    arm = tmp_path / "arm.stl"
    asm = tmp_path / "asm.stl"
    _box().export(arm)
    _box().export(asm)

    scad = tmp_path / "design.scad"
    # 70°C is above PLA Tg=60 → BLOCK
    scad.write_text(
        "// part: arm\n"
        "// operating: temp_c=70\n"
    )

    report = run_pipeline(
        scad,
        work_dir=tmp_path / "work",
        renderer=_stl_dispatcher({"arm": arm, "assembly": asm}),
        simulator=_passthrough_simulator,
    )
    op_temp = [v for v in report.verdicts if v.rule.startswith("operating_temperature")]
    assert len(op_temp) == 1
    assert op_temp[0].severity is Severity.BLOCK


def test_buckling_annotation_drives_check(tmp_path):
    column = tmp_path / "column.stl"
    asm = tmp_path / "asm.stl"
    _box().export(column)
    _box().export(asm)

    scad = tmp_path / "design.scad"
    # Long thin column under heavy axial load → BLOCK
    scad.write_text(
        "// part: column\n"
        "// buckling: part=column axial_n=100 length_mm=200 section=round:3\n"
    )

    report = run_pipeline(
        scad,
        work_dir=tmp_path / "work",
        renderer=_stl_dispatcher({"column": column, "assembly": asm}),
        simulator=_passthrough_simulator,
    )
    buckling = [v for v in report.verdicts if v.rule.startswith("column_buckling")]
    assert len(buckling) == 1
    assert buckling[0].severity is Severity.BLOCK


def test_pressure_annotation_drives_check(tmp_path):
    tank = tmp_path / "tank.stl"
    asm = tmp_path / "asm.stl"
    _box().export(tank)
    _box().export(asm)

    scad = tmp_path / "design.scad"
    # 50 bar / 1mm wall / 50mm radius → 250 MPa hoop stress, BLOCK
    scad.write_text(
        "// part: tank\n"
        "// pressure: part=tank internal_pa=5000000 wall_thickness_mm=1 radius_mm=50\n"
    )

    report = run_pipeline(
        scad,
        work_dir=tmp_path / "work",
        renderer=_stl_dispatcher({"tank": tank, "assembly": asm}),
        simulator=_passthrough_simulator,
    )
    pressure = [v for v in report.verdicts if v.rule.startswith("pressure_vessel_hoop")]
    assert len(pressure) == 1
    assert pressure[0].severity is Severity.BLOCK


def test_unknown_part_in_buckling_blocks(tmp_path):
    arm = tmp_path / "arm.stl"
    asm = tmp_path / "asm.stl"
    _box().export(arm)
    _box().export(asm)

    scad = tmp_path / "design.scad"
    scad.write_text(
        "// part: arm\n"
        "// buckling: part=ghost axial_n=10 length_mm=50 section=round:5\n"
    )

    report = run_pipeline(
        scad,
        work_dir=tmp_path / "work",
        renderer=_stl_dispatcher({"arm": arm, "assembly": asm}),
        simulator=_passthrough_simulator,
    )
    blockers = [v for v in report.verdicts
                if v.severity is Severity.BLOCK and v.rule.startswith("column_buckling")]
    assert len(blockers) == 1
    assert "ghost" in blockers[0].message
