"""Stage 4: STL → G-code via PrusaSlicer CLI.

The slicer is a mechanical bridge — material selection lives in upstream
skills (`pjt222/select-print-material`), and overhang/support analysis lives
in the manufacturability skills downstream from this module. We just produce
G-code given an already-validated STL and a profile.
"""

from .cli import (
    SliceRequest,
    Slicer,
    build_cli_args,
    default_slicer,
    slice_stl,
)
from .profile import SliceProfile, profile_for_material, supported_materials

__all__ = [
    "SliceProfile",
    "SliceRequest",
    "Slicer",
    "build_cli_args",
    "default_slicer",
    "profile_for_material",
    "slice_stl",
    "supported_materials",
]
