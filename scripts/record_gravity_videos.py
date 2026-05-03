#!/usr/bin/env python3
"""Record a small GIF of each example's gravity simulation.

For each `examples/*.scad` we:
  1. Use the orchestrator's default OpenSCAD renderer to produce one STL
     per `// part:` annotation (centered on each part's COM, mirroring
     what `validators.physics.default_simulator` does).
  2. Build an MJCF that mirrors the simulator's body layout but adds a
     visible ground tile, a directional light, and a camera framing the
     assembly's bounding box.
  3. Step MuJoCo for `duration_s`, snapshotting every Nth frame via
     `mujoco.Renderer`, and write the frames out as a GIF with Pillow.

Outputs land under `skill/examples/videos/` so they ship with the
skill bundle and are picked up by the README.

Usage:
    .venv/bin/python scripts/record_gravity_videos.py
    .venv/bin/python scripts/record_gravity_videos.py lamp_stand     # one example
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

# Allow `python scripts/record_gravity_videos.py` to import the project's
# packages without requiring an editable install — same pattern as conftest.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skill"))

import mujoco
import numpy as np
import trimesh
from PIL import Image

from orchestrator import parse_annotations
from orchestrator.pipeline import RenderRequest, default_renderer

REPO = Path(__file__).resolve().parent.parent
EXAMPLES = REPO / "skill" / "examples"
OUT_DIR = EXAMPLES / "videos"

DURATION_S = 2.0
TIMESTEP = 0.002        # match validators.physics.default_simulator
FRAME_EVERY_N_STEPS = 17  # 0.034 s per frame ≈ 30 fps
WIDTH, HEIGHT = 480, 360


def render_parts(scad_path: Path, work_dir: Path) -> dict[str, Path]:
    """Run real OpenSCAD on each `// part:` module."""
    intent = parse_annotations(scad_path.read_text())
    out: dict[str, Path] = {}
    for name in intent.parts:
        stl = work_dir / f"{name}.stl"
        default_renderer(RenderRequest(scad_path, f"{name}();", stl))
        out[name] = stl
    return out


def build_mjcf(part_stls: dict[str, Path], stl_dir: Path) -> tuple[str, dict[str, np.ndarray]]:
    """Mirror validators.physics.default_simulator's body layout, but add a
    visible ground, a key light, and a tracking camera.

    Returns (xml, initial_coms_m).
    """
    coms_m: dict[str, np.ndarray] = {}
    asset_lines: list[str] = []
    body_lines: list[str] = []
    bounds_min_mm = np.array([np.inf, np.inf, np.inf])
    bounds_max_mm = np.array([-np.inf, -np.inf, -np.inf])

    for name, stl_path in part_stls.items():
        mesh = trimesh.load(str(stl_path), force="mesh")
        com_mm = np.array(mesh.center_mass, dtype=float)
        centered = mesh.copy()
        centered.apply_translation(-com_mm)
        centered_path = stl_dir / f"{name}_centered.stl"
        centered.export(centered_path)
        coms_m[name] = com_mm * 1e-3
        bounds_min_mm = np.minimum(bounds_min_mm, mesh.bounds[0])
        bounds_max_mm = np.maximum(bounds_max_mm, mesh.bounds[1])

        asset_lines.append(
            f'    <mesh name="{name}" file="{centered_path}" scale="0.001 0.001 0.001"/>'
        )
        c = coms_m[name]
        body_lines.append(
            f'    <body name="{name}" pos="{c[0]} {c[1]} {c[2]}">\n'
            f'      <freejoint/>\n'
            f'      <geom type="mesh" mesh="{name}" density="1240" '
            f'rgba="0.8 0.6 0.3 1" contype="2" conaffinity="1"/>\n'
            f'    </body>'
        )

    # Frame the scene from the actual assembly bounds, not the spread of COMs
    # (which is zero for a single-part assembly).
    bbox_center_m = (bounds_min_mm + bounds_max_mm) * 0.5e-3
    extent_m = float(np.max(bounds_max_mm - bounds_min_mm)) * 1e-3
    distance = max(0.20, 2.2 * extent_m)
    # Iso-ish view: offset in +x, -y, +z, looking back at bbox centre.
    cam_pos = bbox_center_m + np.array([0.7, -0.9, 0.6]) * distance

    # Build a proper look-at. MuJoCo cameras look down their -Z axis, so the
    # camera's local +Z is the *back* direction (cam_pos - target). `xyaxes`
    # is "right up" in world coords; right × up must equal local +Z.
    world_up = np.array([0.0, 0.0, 1.0])
    back = cam_pos - bbox_center_m
    back /= np.linalg.norm(back)
    right = np.cross(world_up, back)
    right /= np.linalg.norm(right)
    up = np.cross(back, right)
    xyaxes = " ".join(f"{v:.6f}" for v in (*right, *up))

    xml = f"""<mujoco>
  <option gravity="0 0 -9.81" timestep="{TIMESTEP}"/>
  <visual>
    <headlight diffuse="0.6 0.6 0.6" ambient="0.3 0.3 0.3" specular="0 0 0"/>
    <rgba haze="0.15 0.25 0.35 1"/>
    <global azimuth="120" elevation="-20"/>
  </visual>
  <asset>
    <texture type="skybox" builtin="gradient" rgb1="0.3 0.5 0.7" rgb2="0 0 0"
             width="32" height="512"/>
    <texture type="2d" name="grid" builtin="checker" rgb1=".15 .15 .15" rgb2=".25 .25 .25"
             width="300" height="300" mark="edge" markrgb=".8 .8 .8"/>
    <material name="grid" texture="grid" texrepeat="4 4" texuniform="true" reflectance="0.0"/>
{chr(10).join(asset_lines)}
  </asset>
  <worldbody>
    <light pos="0.3 0.3 1.0" dir="-0.3 -0.3 -1.0" diffuse="0.7 0.7 0.7"/>
    <geom name="ground" type="plane" pos="0 0 0" size="1 1 0.01"
          material="grid" contype="1" conaffinity="1"/>
    <camera name="track" pos="{cam_pos[0]} {cam_pos[1]} {cam_pos[2]}"
            xyaxes="{xyaxes}" mode="fixed"/>
{chr(10).join(body_lines)}
  </worldbody>
</mujoco>"""
    return xml, coms_m


def record(scad_name: str) -> Path:
    scad_path = EXAMPLES / f"{scad_name}.scad"
    if not scad_path.exists():
        raise SystemExit(f"no such example: {scad_path}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_gif = OUT_DIR / f"{scad_name}.gif"

    with tempfile.TemporaryDirectory(prefix=f"vid_{scad_name}_") as tmp_str:
        tmp = Path(tmp_str)
        part_stls = render_parts(scad_path, tmp)
        xml, _ = build_mjcf(part_stls, tmp)
        model = mujoco.MjModel.from_xml_string(xml)
        data = mujoco.MjData(model)
        # Propagate the initial body poses into data.xpos / data.xquat — without
        # this the first rendered frame puts every body at the world origin.
        mujoco.mj_forward(model, data)
        renderer = mujoco.Renderer(model, height=HEIGHT, width=WIDTH)

        n_steps = int(round(DURATION_S / TIMESTEP))
        cam_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "track")

        frames: list[Image.Image] = []
        for step in range(n_steps):
            if step % FRAME_EVERY_N_STEPS == 0:
                renderer.update_scene(data, camera=cam_id)
                rgb = renderer.render()
                frames.append(Image.fromarray(rgb))
            mujoco.mj_step(model, data)
        # one last frame at the end so the still-frame is visible
        renderer.update_scene(data, camera=cam_id)
        frames.append(Image.fromarray(renderer.render()))

    # Save as GIF. Quantize to 256-color palette to keep size down.
    quantized = [f.quantize(colors=128, method=Image.Quantize.MEDIANCUT) for f in frames]
    duration_ms = int(1000 * FRAME_EVERY_N_STEPS * TIMESTEP)
    quantized[0].save(
        out_gif,
        save_all=True,
        append_images=quantized[1:],
        duration=duration_ms,
        loop=0,
        optimize=True,
        disposal=2,
    )
    return out_gif


def main() -> int:
    if len(sys.argv) > 1:
        targets = sys.argv[1:]
    else:
        targets = sorted(p.stem for p in EXAMPLES.glob("*.scad"))

    for name in targets:
        gif_path = record(name)
        size_kb = gif_path.stat().st_size / 1024
        print(f"  {name:25s} -> {gif_path}  ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
