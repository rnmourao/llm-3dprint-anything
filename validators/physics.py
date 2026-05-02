"""Drop the assembly into a rigid-body sim and verify each part settles in
its starting pose.

Approach: each part becomes a dynamic body in MuJoCo with its mesh as the
collision shape (convex-hulled for dynamic-vs-dynamic contact), gravity is
applied for `duration_s` seconds, and the body's final pose is compared
against its starting pose. Translation > `max_translation_mm` or rotation
> `max_rotation_deg` → WARN with the drift in the verdict's evidence.

Pluggable simulator (matches orchestrator.Renderer / slicer.Slicer /
transport.Transport): the default uses MuJoCo; tests inject fakes.

v1 limits documented honestly:
  * Mesh-mesh collision uses convex hulls. Non-convex parts (a plate with a
    hole, a socket, a cradle) collide as their convex hulls — the hole
    "fills in." For peg-in-hole geometry, set inter_part_collision=False
    so each part is simulated against the bed only.
  * Supports only z-axis gravity in the default simulator (the project-wide
    default; other axes are achievable with a custom simulator).
  * No restitution / damping tuning. Default MuJoCo contact dynamics.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import trimesh

from .types import Part, Severity, Verdict


@dataclass(frozen=True)
class Pose:
    """World-frame pose of a body's COM in mm + quaternion (x, y, z, w)."""

    translation_mm: tuple[float, float, float]
    rotation_quat: tuple[float, float, float, float]


@dataclass(frozen=True)
class SimRequest:
    parts: list[Part]
    duration_s: float
    bed_z_mm: float
    gravity_axis: str
    inter_part_collision: bool


@dataclass(frozen=True)
class SimResult:
    final_poses: dict[str, Pose]


Simulator = Callable[[SimRequest], SimResult]


_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


def _parse_axis(axis: str) -> tuple[int, int]:
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


def _quat_angle_deg(quat: tuple[float, float, float, float]) -> float:
    """Magnitude of rotation in degrees from a unit quaternion (x,y,z,w)."""
    qw = quat[3]
    angle_rad = 2.0 * float(np.arccos(np.clip(abs(qw), 0.0, 1.0)))
    return float(np.degrees(angle_rad))


def default_simulator(req: SimRequest) -> SimResult:
    """MuJoCo-backed rigid-body simulator. Headless.

    Saves a temporary STL per part with the COM translated to the origin,
    builds an MJCF model with one freejoint body per part placed at its
    world-frame COM, steps for req.duration_s, and reads back final poses.
    """
    import mujoco

    if req.gravity_axis != "-z":
        raise NotImplementedError(
            f"default_simulator v1 only supports gravity_axis='-z' (got "
            f"{req.gravity_axis!r}); supply a custom simulator for other axes."
        )

    with tempfile.TemporaryDirectory(prefix="3dprint_sim_") as tmp:
        tmp = Path(tmp)
        mesh_files: dict[str, Path] = {}
        coms_m: dict[str, np.ndarray] = {}
        for part in req.parts:
            com_mm = np.array(part.mesh.center_mass, dtype=float)
            centered = part.mesh.copy()
            centered.apply_translation(-com_mm)
            stl_path = tmp / f"{part.name}.stl"
            centered.export(stl_path)
            mesh_files[part.name] = stl_path
            coms_m[part.name] = com_mm * 1e-3  # mm → m

        bed_z_m = req.bed_z_mm * 1e-3
        ground_contype, ground_conaffinity = 1, 1
        if req.inter_part_collision:
            part_contype, part_conaffinity = 1, 1  # collide with everything
        else:
            part_contype, part_conaffinity = 2, 1  # collide only with ground

        asset_xml = "\n".join(
            f'    <mesh name="{name}" file="{path}" scale="0.001 0.001 0.001"/>'
            for name, path in mesh_files.items()
        )
        body_xml = "\n".join(
            f'    <body name="{name}" pos="{c[0]} {c[1]} {c[2]}">\n'
            f'      <freejoint/>\n'
            f'      <geom type="mesh" mesh="{name}" density="1240" '
            f'contype="{part_contype}" conaffinity="{part_conaffinity}"/>\n'
            f'    </body>'
            for name, c in coms_m.items()
        )
        xml = f"""<mujoco>
  <option gravity="0 0 -9.81" timestep="0.002"/>
  <asset>
{asset_xml}
  </asset>
  <worldbody>
    <geom name="ground" type="plane" pos="0 0 {bed_z_m}" size="10 10 0.1"
          contype="{ground_contype}" conaffinity="{ground_conaffinity}"/>
{body_xml}
  </worldbody>
</mujoco>"""

        model = mujoco.MjModel.from_xml_string(xml)
        data = mujoco.MjData(model)

        n_steps = int(round(req.duration_s / model.opt.timestep))
        for _ in range(n_steps):
            mujoco.mj_step(model, data)

        final_poses: dict[str, Pose] = {}
        for part in req.parts:
            body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, part.name)
            pos_m = np.array(data.xpos[body_id], dtype=float)
            quat_wxyz = np.array(data.xquat[body_id], dtype=float)  # MuJoCo: (w,x,y,z)
            quat_xyzw = (
                float(quat_wxyz[1]),
                float(quat_wxyz[2]),
                float(quat_wxyz[3]),
                float(quat_wxyz[0]),
            )
            final_poses[part.name] = Pose(
                translation_mm=tuple(float(x) for x in (pos_m * 1e3)),
                rotation_quat=quat_xyzw,
            )

    return SimResult(final_poses=final_poses)


def check_settles_under_gravity(
    parts: list[Part],
    *,
    duration_s: float = 2.0,
    max_translation_mm: float = 1.0,
    max_rotation_deg: float = 5.0,
    bed_z_mm: float = 0.0,
    gravity_axis: str = "-z",
    inter_part_collision: bool = False,
    simulator: Simulator = default_simulator,
) -> list[Verdict]:
    """For each part, drop it into a sim and emit a Verdict on whether it
    stayed put. One Verdict per part, rule key `physics_settles:<name>`.

    Default `inter_part_collision=False` because v1 collision is convex-hull
    only — a peg sitting in a hole would be falsely flagged as overlapping
    a solid socket. Set True for assemblies whose parts genuinely rest on
    each other (and whose convex hulls don't lie about contact).
    """
    if not parts:
        return []

    request = SimRequest(
        parts=parts,
        duration_s=duration_s,
        bed_z_mm=bed_z_mm,
        gravity_axis=gravity_axis,
        inter_part_collision=inter_part_collision,
    )
    result = simulator(request)

    verdicts: list[Verdict] = []
    for part in parts:
        if part.name not in result.final_poses:
            verdicts.append(Verdict(
                rule=f"physics_settles:{part.name}",
                severity=Severity.BLOCK,
                message=f"simulator returned no pose for {part.name!r}",
            ))
            continue

        initial_com = np.array(part.mesh.center_mass, dtype=float)
        final = result.final_poses[part.name]
        final_com = np.array(final.translation_mm, dtype=float)

        translation = float(np.linalg.norm(final_com - initial_com))
        rotation_deg = _quat_angle_deg(final.rotation_quat)

        evidence = {
            "translation_mm": translation,
            "rotation_deg": rotation_deg,
            "duration_s": duration_s,
            "max_translation_mm": max_translation_mm,
            "max_rotation_deg": max_rotation_deg,
            "initial_com_mm": initial_com.tolist(),
            "final_com_mm": final_com.tolist(),
            "inter_part_collision": inter_part_collision,
        }

        rule = f"physics_settles:{part.name}"
        if translation > max_translation_mm or rotation_deg > max_rotation_deg:
            verdicts.append(Verdict(
                rule=rule,
                severity=Severity.WARN,
                message=(
                    f"{part.name} drifted {translation:.2f} mm and rotated "
                    f"{rotation_deg:.1f}° during {duration_s} s of simulated gravity. "
                    "Not stable in this configuration."
                ),
                evidence=evidence,
                suggested_action=(
                    "Reposition the part to rest on the bed or another part, "
                    "or model interlocking parts as a single connected mesh."
                ),
            ))
        else:
            verdicts.append(Verdict(
                rule=rule,
                severity=Severity.PASS,
                message=(
                    f"{part.name} settled with {translation:.2f} mm drift and "
                    f"{rotation_deg:.1f}° rotation after {duration_s} s."
                ),
                evidence=evidence,
            ))

    return verdicts
