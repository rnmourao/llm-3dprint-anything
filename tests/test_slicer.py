"""Slicer tests use a fake-slicer pattern, mirroring tests/test_pipeline.py.

Real PrusaSlicer is not required to run these tests — the integration just
verifies that slice_stl correctly composes the SliceRequest, calls the
injected slicer, and returns the path. CLI argument composition is unit-
tested directly via build_cli_args.
"""

from pathlib import Path

import pytest

from slicer import (
    SliceProfile,
    SliceRequest,
    build_cli_args,
    profile_for_material,
    slice_stl,
)


def _record_args() -> tuple[list[SliceRequest], callable]:
    """Build a fake slicer that records every call and writes a stub file."""
    calls: list[SliceRequest] = []

    def fake(req: SliceRequest) -> Path:
        calls.append(req)
        req.output_gcode.write_text("; fake gcode\n")
        return req.output_gcode

    return calls, fake


# ----- slice_stl orchestration -----


def test_slice_stl_invokes_slicer_and_returns_path(tmp_path):
    stl = tmp_path / "in.stl"
    stl.write_bytes(b"")  # contents irrelevant for fake slicer
    calls, fake = _record_args()

    out = slice_stl(stl, slicer=fake)
    assert out == stl.with_suffix(".gcode")
    assert out.exists()
    assert len(calls) == 1
    assert calls[0].stl_path == stl


def test_slice_stl_uses_default_profile_when_none_given(tmp_path):
    stl = tmp_path / "in.stl"
    stl.write_bytes(b"")
    calls, fake = _record_args()

    slice_stl(stl, slicer=fake)
    assert calls[0].profile == SliceProfile()  # PLA default


def test_slice_stl_passes_through_profile(tmp_path):
    stl = tmp_path / "in.stl"
    stl.write_bytes(b"")
    profile = profile_for_material("PETG", layer_height_mm=0.15)
    calls, fake = _record_args()

    slice_stl(stl, profile=profile, slicer=fake)
    assert calls[0].profile.material == "PETG"
    assert calls[0].profile.layer_height_mm == 0.15


def test_slice_stl_explicit_output_path(tmp_path):
    stl = tmp_path / "in.stl"
    stl.write_bytes(b"")
    out = tmp_path / "subdir" / "custom.gcode"
    out.parent.mkdir()
    calls, fake = _record_args()

    result = slice_stl(stl, output_gcode=out, slicer=fake)
    assert result == out
    assert out.exists()


def test_slice_stl_missing_stl_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        slice_stl(tmp_path / "nope.stl", slicer=lambda req: req.output_gcode)


# ----- CLI argument composition -----


def test_build_cli_args_includes_required_flags(tmp_path):
    req = SliceRequest(
        stl_path=tmp_path / "in.stl",
        output_gcode=tmp_path / "out.gcode",
        profile=profile_for_material("PLA"),
    )
    args = build_cli_args(req, "/usr/local/bin/prusa-slicer")

    # Required flags present
    assert "--export-gcode" in args
    assert "--layer-height" in args
    assert "--nozzle-diameter" in args
    assert "--temperature" in args
    assert "--bed-temperature" in args
    # STL is the last positional argument
    assert args[-1] == str(req.stl_path)
    # Output is preceded by -o
    o_idx = args.index("-o")
    assert args[o_idx + 1] == str(req.output_gcode)


def test_build_cli_args_temperature_matches_material():
    pla_req = SliceRequest(Path("/x/in.stl"), Path("/x/out.gcode"), profile_for_material("PLA"))
    abs_req = SliceRequest(Path("/x/in.stl"), Path("/x/out.gcode"), profile_for_material("ABS"))

    pla_args = build_cli_args(pla_req, "ps")
    abs_args = build_cli_args(abs_req, "ps")

    pla_temp = pla_args[pla_args.index("--temperature") + 1]
    abs_temp = abs_args[abs_args.index("--temperature") + 1]
    assert int(abs_temp) > int(pla_temp)


def test_build_cli_args_appends_extra_args(tmp_path):
    profile = profile_for_material("PLA", extra_args=("--support-material", "--brim-width", "5"))
    req = SliceRequest(tmp_path / "in.stl", tmp_path / "out.gcode", profile)
    args = build_cli_args(req, "ps")
    assert "--support-material" in args
    assert "--brim-width" in args
    assert "5" in args
    # Still ends with the STL path
    assert args[-1] == str(req.stl_path)


def test_build_cli_args_infill_percent_format(tmp_path):
    profile = profile_for_material("PLA", infill_percent=35)
    req = SliceRequest(tmp_path / "in.stl", tmp_path / "out.gcode", profile)
    args = build_cli_args(req, "ps")
    assert args[args.index("--fill-density") + 1] == "35%"


def test_build_cli_args_first_layer_temps_default_to_regular(tmp_path):
    """Without explicit first-layer temps, fall back to the non-first values
    (so PrusaSlicer never emits S0 for the first-layer bed/nozzle)."""
    profile = profile_for_material("PLA")
    req = SliceRequest(tmp_path / "in.stl", tmp_path / "out.gcode", profile)
    args = build_cli_args(req, "ps")
    fl_t = args[args.index("--first-layer-temperature") + 1]
    fl_b = args[args.index("--first-layer-bed-temperature") + 1]
    assert fl_t == str(profile.extruder_temp_c)
    assert fl_b == str(profile.bed_temp_c)


def test_build_cli_args_first_layer_temps_override(tmp_path):
    profile = profile_for_material("PLA",
                                   first_layer_extruder_temp_c=220,
                                   first_layer_bed_temp_c=65)
    req = SliceRequest(tmp_path / "in.stl", tmp_path / "out.gcode", profile)
    args = build_cli_args(req, "ps")
    assert args[args.index("--first-layer-temperature") + 1] == "220"
    assert args[args.index("--first-layer-bed-temperature") + 1] == "65"
