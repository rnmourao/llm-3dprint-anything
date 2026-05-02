"""STL → G-code via PrusaSlicer CLI.

Pluggable-slicer pattern, mirroring `orchestrator.pipeline.Renderer`:
`default_slicer` shells out to `prusa-slicer` (or `PrusaSlicer`); tests inject
fakes that produce stub G-code without the binary installed.

Usage:
    from slicer import slice_stl, profile_for_material
    gcode = slice_stl(stl, profile=profile_for_material("PLA"))
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .profile import SliceProfile


@dataclass(frozen=True)
class SliceRequest:
    stl_path: Path
    output_gcode: Path
    profile: SliceProfile


Slicer = Callable[[SliceRequest], Path]


_PRUSA_BINARY_NAMES = ("prusa-slicer", "PrusaSlicer", "prusa-slicer-console")


def _find_prusa_slicer() -> Optional[str]:
    for name in _PRUSA_BINARY_NAMES:
        path = shutil.which(name)
        if path:
            return path
    return None


def build_cli_args(req: SliceRequest, prusa_path: str) -> list[str]:
    """Compose the prusa-slicer command line.

    Pulled out as a separate function so it can be unit-tested without
    actually running PrusaSlicer.
    """
    p = req.profile
    args = [
        prusa_path,
        "--export-gcode",
        "-o", str(req.output_gcode),
        "--layer-height", str(p.layer_height_mm),
        "--nozzle-diameter", str(p.nozzle_diameter_mm),
        "--fill-density", f"{p.infill_percent}%",
        "--perimeters", str(p.perimeters),
        "--filament-type", p.material,
        "--temperature", str(p.extruder_temp_c),
        "--bed-temperature", str(p.bed_temp_c),
    ]
    args.extend(p.extra_args)
    args.append(str(req.stl_path))
    return args


def default_slicer(req: SliceRequest) -> Path:
    prusa = _find_prusa_slicer()
    if prusa is None:
        raise FileNotFoundError(
            "prusa-slicer not found in PATH. Install PrusaSlicer or pass a "
            f"custom slicer. Searched: {_PRUSA_BINARY_NAMES}"
        )
    args = build_cli_args(req, prusa)
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"PrusaSlicer failed (rc={result.returncode}): {result.stderr.strip()}"
        )
    if not req.output_gcode.exists():
        raise RuntimeError(
            f"PrusaSlicer reported success but {req.output_gcode} was not created."
        )
    return req.output_gcode


def slice_stl(
    stl_path: Path,
    *,
    output_gcode: Optional[Path] = None,
    profile: Optional[SliceProfile] = None,
    slicer: Slicer = default_slicer,
) -> Path:
    """Convert an STL to G-code.

    The STL must already be valid — run the orchestrator's Stage 3 first.
    The slicer does not re-validate geometry; bad STLs produce bad G-code
    or PrusaSlicer errors.
    """
    stl_path = Path(stl_path)
    if not stl_path.exists():
        raise FileNotFoundError(f"STL not found: {stl_path}")
    output_gcode = Path(output_gcode) if output_gcode else stl_path.with_suffix(".gcode")
    profile = profile or SliceProfile()
    return slicer(SliceRequest(stl_path=stl_path, output_gcode=output_gcode, profile=profile))
