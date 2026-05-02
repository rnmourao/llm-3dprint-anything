import pytest

from validators import Severity, check_operating_temperature


def test_room_temp_passes_for_pla():
    v = check_operating_temperature(operating_temp_c=22.0, material="PLA")
    assert v.severity is Severity.PASS
    assert v.evidence["margin_to_hdt_c"] > 30


def test_above_hdt_below_tg_warns():
    """PLA HDT≈55°C, Tg≈60°C — between them is the WARN band."""
    v = check_operating_temperature(operating_temp_c=57.0, material="PLA")
    assert v.severity is Severity.WARN
    assert "sag" in v.message
    assert "advisory" in v.message


def test_above_tg_blocks():
    """PLA Tg≈60°C — sustained operation at 80°C destroys structural strength."""
    v = check_operating_temperature(operating_temp_c=80.0, material="PLA")
    assert v.severity is Severity.BLOCK
    assert "deform freely" in v.message


def test_pla_blocks_where_petg_passes():
    """PETG Tg≈80°C; same operating temp that BLOCKs PLA passes for PETG."""
    pla = check_operating_temperature(operating_temp_c=70.0, material="PLA")
    petg = check_operating_temperature(operating_temp_c=70.0, material="PETG")
    assert pla.severity is Severity.BLOCK
    assert petg.severity is not Severity.BLOCK


def test_part_name_appears_in_rule():
    v = check_operating_temperature(
        operating_temp_c=22.0, material="PLA", part_name="bracket"
    )
    assert v.rule == "operating_temperature:bracket"
    assert "bracket" in v.message


def test_unknown_material_raises():
    with pytest.raises(ValueError, match="Unknown material"):
        check_operating_temperature(operating_temp_c=22.0, material="kryptonite")


def test_evidence_includes_margins():
    v = check_operating_temperature(operating_temp_c=20.0, material="PLA")
    assert v.evidence["margin_to_hdt_c"] == pytest.approx(35.0)
    assert v.evidence["margin_to_tg_c"] == pytest.approx(40.0)
