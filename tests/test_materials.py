import pytest

from validators import (
    MATERIALS_FDM,
    YIELD_MPA_FDM,
    Material,
    get_material,
    supported_materials,
)


def test_supported_materials_set():
    assert set(supported_materials()) == {"PLA", "PETG", "ABS"}


def test_get_material_returns_dataclass():
    m = get_material("PLA")
    assert isinstance(m, Material)
    assert m.name == "PLA"


def test_unknown_material_raises():
    with pytest.raises(ValueError, match="Unknown material"):
        get_material("kryptonite")


def test_yield_mpa_alias_matches_table():
    """YIELD_MPA_FDM (back-compat alias) is derived from MATERIALS_FDM."""
    for name, mat in MATERIALS_FDM.items():
        assert YIELD_MPA_FDM[name] == mat.yield_mpa


def test_glass_transition_ordering():
    """PLA softens earliest; ABS holds up to highest temperature."""
    assert (
        MATERIALS_FDM["PLA"].glass_transition_c
        < MATERIALS_FDM["PETG"].glass_transition_c
        < MATERIALS_FDM["ABS"].glass_transition_c
    )


def test_hdt_below_glass_transition():
    """HDT is the temperature where the part starts to sag under load — always
    below Tg, where the polymer transitions out of the glassy state."""
    for mat in MATERIALS_FDM.values():
        assert mat.hdt_c < mat.glass_transition_c


def test_youngs_modulus_in_realistic_range():
    """All FDM hobby plastics fall in 1–4 GPa for in-plane modulus."""
    for mat in MATERIALS_FDM.values():
        assert 1.0 < mat.youngs_modulus_gpa < 5.0
