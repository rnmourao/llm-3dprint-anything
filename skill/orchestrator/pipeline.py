"""Stage 3 orchestration: render a SCAD file → run validators → return Report.

The pipeline is the operational realisation of SKILL.md's Stage 3. It is
*not* a validator itself — it composes them, driven by the intent
annotations parsed out of the SCAD source.

The renderer is pluggable so the pipeline is testable without OpenSCAD
installed. Production code uses `default_renderer` (shells out to the
`openscad` CLI). Tests inject fakes that map call-expressions to
pre-built STLs.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import trimesh

from validators import (
    Part,
    Report,
    Severity,
    Simulator,
    Verdict,
    aggregate,
    check_buckling,
    check_cantilever,
    check_clearance,
    check_grounded,
    check_hard_clash,
    check_mesh_integrity,
    check_operating_temperature,
    check_pressure_vessel,
    check_settles_under_gravity,
    check_static_stability,
    default_simulator,
)

from .annotations import Intent, Load, parse_annotations


@dataclass(frozen=True)
class RenderRequest:
    scad_path: Path
    call_expression: str   # e.g. "shaft();" or "assembly();"
    output_stl: Path


Renderer = Callable[[RenderRequest], Path]


def default_renderer(req: RenderRequest) -> Path:
    """Invoke the `openscad` CLI to render `call_expression` into an STL.

    Writes a tiny wrapper SCAD that includes the user's file and invokes
    the requested call, then runs `openscad -o <stl> <wrapper>`.
    """
    openscad = shutil.which("openscad")
    if openscad is None:
        raise FileNotFoundError(
            "openscad CLI not found in PATH. Install OpenSCAD or pass a custom renderer."
        )

    wrapper = req.output_stl.with_suffix(".wrapper.scad")
    # `use` imports module/function definitions but skips top-level code, so a
    # SCAD file with `assembly();` at the bottom can still be rendered standalone
    # while letting us request individual modules cleanly.
    wrapper.write_text(
        f'use <{req.scad_path.absolute()}>\n{req.call_expression}\n'
    )
    result = subprocess.run(
        [openscad, "-o", str(req.output_stl), str(wrapper)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"OpenSCAD render failed (rc={result.returncode}): {result.stderr.strip()}"
        )
    return req.output_stl


def _verdict(rule: str, severity: Severity, message: str, **evidence) -> Verdict:
    return Verdict(rule=rule, severity=severity, message=message, evidence=evidence)


def _load_part(name: str, stl_path: Path) -> Part:
    mesh = trimesh.load(str(stl_path), force="mesh")
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError(f"{stl_path} did not load as a Trimesh ({type(mesh).__name__})")
    return Part(name=name, mesh=mesh)


def _run_loads(intent: Intent, parts_by_name: dict[str, Part]) -> list[Verdict]:
    verdicts: list[Verdict] = []
    for load in intent.loads:
        if load.part not in parts_by_name:
            verdicts.append(_verdict(
                f"cantilever_stress:{load.part}",
                Severity.BLOCK,
                f"load annotation references unknown part {load.part!r}",
                load_part=load.part,
            ))
            continue
        v = check_cantilever(
            load.length_mm,
            load.section,
            load.force_n,
            material=load.material,
        )
        # Re-key so multiple loads on different parts don't collide.
        verdicts.append(Verdict(
            rule=f"{v.rule}:{load.part}",
            severity=v.severity,
            message=f"({load.part}) {v.message}",
            evidence=v.evidence,
            suggested_action=v.suggested_action,
        ))
    return verdicts


def _run_bucklings(intent: Intent, parts_by_name: dict[str, Part]) -> list[Verdict]:
    verdicts: list[Verdict] = []
    for b in intent.bucklings:
        if b.part not in parts_by_name:
            verdicts.append(_verdict(
                f"column_buckling:{b.part}",
                Severity.BLOCK,
                f"buckling annotation references unknown part {b.part!r}",
                load_part=b.part,
            ))
            continue
        v = check_buckling(
            b.length_mm,
            b.section,
            b.axial_n,
            material=b.material,
            end_condition=b.end_condition,
        )
        verdicts.append(Verdict(
            rule=f"{v.rule}:{b.part}",
            severity=v.severity,
            message=f"({b.part}) {v.message}",
            evidence=v.evidence,
            suggested_action=v.suggested_action,
        ))
    return verdicts


def _run_pressures(intent: Intent, parts_by_name: dict[str, Part]) -> list[Verdict]:
    verdicts: list[Verdict] = []
    for p in intent.pressures:
        if p.part not in parts_by_name:
            verdicts.append(_verdict(
                f"pressure_vessel_hoop:{p.part}",
                Severity.BLOCK,
                f"pressure annotation references unknown part {p.part!r}",
                load_part=p.part,
            ))
            continue
        v = check_pressure_vessel(
            p.wall_thickness_mm,
            p.radius_mm,
            p.internal_pa,
            material=p.material,
        )
        verdicts.append(Verdict(
            rule=f"{v.rule}:{p.part}",
            severity=v.severity,
            message=f"({p.part}) {v.message}",
            evidence=v.evidence,
            suggested_action=v.suggested_action,
        ))
    return verdicts


def _run_operating_temp(intent: Intent, parts_by_name: dict[str, Part]) -> list[Verdict]:
    if intent.operating_temp_c is None:
        return []
    # Material per part: use loads/bucklings/pressures hints if a part appears;
    # otherwise default to PLA. v1 keeps this lookup simple — first annotation
    # mentioning a material for the part wins.
    materials: dict[str, str] = {}
    for src in (intent.loads, intent.bucklings, intent.pressures):
        for item in src:
            materials.setdefault(item.part, item.material)
    return [
        check_operating_temperature(
            operating_temp_c=intent.operating_temp_c,
            material=materials.get(name, "PLA"),
            part_name=name,
        )
        for name in parts_by_name
    ]


def run_pipeline(
    scad_path: Path,
    *,
    work_dir: Optional[Path] = None,
    renderer: Renderer = default_renderer,
    simulator: Simulator = default_simulator,
) -> Report:
    """Execute Stage 3 on a SCAD file and return the aggregated Report.

    Steps (per SKILL.md):
        0. Parse intent annotations.
        1. Render the assembly STL and one STL per declared part.
        2. check_mesh_integrity on the assembly.
        3. check_hard_clash on every part pair (with whitelist).
        4. check_clearance per fit annotation.
        5. check_static_stability on the assembly.
        6. check_cantilever per load annotation.
        7. aggregate(...) → Report.

    The renderer is injectable; default uses the openscad CLI.
    """
    scad_path = Path(scad_path)
    work_dir = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="3dprint_"))
    work_dir.mkdir(parents=True, exist_ok=True)

    intent = parse_annotations(scad_path.read_text())

    if not intent.parts:
        return Report([_verdict(
            "annotations",
            Severity.BLOCK,
            "No `// part:` annotations found. Stage 3 cannot run without declared parts.",
        )])

    # Render
    assembly_stl = work_dir / "assembly.stl"
    try:
        renderer(RenderRequest(scad_path, "assembly();", assembly_stl))
    except Exception as e:
        return Report([_verdict(
            "render:assembly",
            Severity.BLOCK,
            f"Failed to render assembly(): {e}",
        )])

    part_stls: dict[str, Path] = {}
    render_failures: list[Verdict] = []
    for name in intent.parts:
        out = work_dir / f"part_{name}.stl"
        try:
            renderer(RenderRequest(scad_path, f"{name}();", out))
            part_stls[name] = out
        except Exception as e:
            render_failures.append(_verdict(
                f"render:{name}",
                Severity.BLOCK,
                f"Failed to render part {name!r}: {e}",
            ))

    if render_failures:
        return Report(render_failures)

    parts = [_load_part(n, p) for n, p in part_stls.items()]
    parts_by_name = {p.name: p for p in parts}

    # Validators
    mesh_verdicts = check_mesh_integrity(assembly_stl)

    clash_verdicts: list[Verdict] = []
    if len(parts) >= 2:
        clash_verdicts = check_hard_clash(parts, whitelist=intent.clash_whitelist)

    fit_verdicts: list[Verdict] = []
    for a, b, fit_class in intent.fits:
        if a not in parts_by_name or b not in parts_by_name:
            pair = tuple(sorted((a, b)))
            fit_verdicts.append(_verdict(
                f"clearance:{pair[0]}~{pair[1]}",
                Severity.BLOCK,
                f"fit annotation references unknown part(s): missing "
                f"{[p for p in (a, b) if p not in parts_by_name]}",
            ))
            continue
        fit_verdicts.append(
            check_clearance(parts_by_name[a], parts_by_name[b], fit_class)
        )

    assembly_mesh = trimesh.load(str(assembly_stl), force="mesh")
    stability_verdict = check_static_stability(
        assembly_mesh,
        gravity_axis=intent.gravity_axis,
        bed_z=intent.bed_z,
    )
    grounded_verdict = check_grounded(
        assembly_mesh,
        gravity_axis=intent.gravity_axis,
        bed_z=intent.bed_z,
    )

    physics_verdicts = check_settles_under_gravity(
        parts,
        bed_z_mm=intent.bed_z if intent.bed_z is not None else 0.0,
        gravity_axis=intent.gravity_axis,
        simulator=simulator,
    )

    load_verdicts = _run_loads(intent, parts_by_name)
    buckling_verdicts = _run_bucklings(intent, parts_by_name)
    pressure_verdicts = _run_pressures(intent, parts_by_name)
    operating_temp_verdicts = _run_operating_temp(intent, parts_by_name)

    return aggregate(
        mesh_verdicts,
        clash_verdicts,
        fit_verdicts,
        [stability_verdict, grounded_verdict],
        physics_verdicts,
        load_verdicts,
        buckling_verdicts,
        pressure_verdicts,
        operating_temp_verdicts,
    )
