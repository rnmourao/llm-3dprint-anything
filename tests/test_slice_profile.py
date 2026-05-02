from dataclasses import replace

import pytest

from slicer import SliceProfile, profile_for_material, supported_materials


def test_default_profile_has_pla_temps():
    p = SliceProfile()
    assert p.material == "PLA"
    assert p.extruder_temp_c == 215
    assert p.bed_temp_c == 60
    assert p.layer_height_mm == pytest.approx(0.20)


def test_petg_runs_hotter_than_pla():
    pla = profile_for_material("PLA")
    petg = profile_for_material("PETG")
    assert petg.extruder_temp_c > pla.extruder_temp_c
    assert petg.bed_temp_c > pla.bed_temp_c


def test_abs_runs_hottest():
    abs_p = profile_for_material("ABS")
    pla = profile_for_material("PLA")
    petg = profile_for_material("PETG")
    assert abs_p.extruder_temp_c > petg.extruder_temp_c > pla.extruder_temp_c


def test_profile_for_material_accepts_overrides():
    p = profile_for_material("PLA", layer_height_mm=0.15, infill_percent=50)
    assert p.material == "PLA"
    assert p.layer_height_mm == pytest.approx(0.15)
    assert p.infill_percent == 50
    # Untouched defaults stay
    assert p.extruder_temp_c == 215


def test_unknown_material_raises():
    with pytest.raises(ValueError, match="Unknown material"):
        profile_for_material("kryptonite")


def test_supported_materials_lists_all():
    assert set(supported_materials()) == {"PLA", "PETG", "ABS"}


def test_profile_is_frozen():
    p = SliceProfile()
    with pytest.raises(Exception):  # FrozenInstanceError
        p.layer_height_mm = 0.3  # type: ignore[misc]


def test_replace_returns_new_profile():
    base = profile_for_material("PLA")
    modified = replace(base, perimeters=4)
    assert modified.perimeters == 4
    assert base.perimeters == 2  # original unchanged
