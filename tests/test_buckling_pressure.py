"""Tests for the new pressure-related structural checks.

  P_critical (Euler) = π² · E · I / (K · L)²
  σ_hoop = P · r / t
"""

import math

import pytest

from validators import (
    RectSection,
    RoundSection,
    Severity,
    check_buckling,
    check_pressure_vessel,
)


# ----- check_buckling -----


def test_short_thick_column_passes():
    """L=20mm, square 5x5, axial 10N — far below Euler critical."""
    v = check_buckling(20, RectSection(5, 5), 10.0, end_condition="fixed-free")
    assert v.severity is Severity.PASS
    assert v.evidence["P_critical_n"] > v.evidence["axial_load_n"] * 100


def test_long_slender_column_blocks():
    """L=200mm, round 3mm dia, axial 100N — way above critical."""
    v = check_buckling(200, RoundSection(3), 100.0, end_condition="fixed-free")
    assert v.severity is Severity.BLOCK
    assert "buckle" in v.message


def test_borderline_warns():
    """Stress between safety threshold and critical → WARN."""
    # E (PLA) = 3.5 GPa = 3500 N/mm². I (round d=4) = π·4⁴/64 ≈ 12.566 mm⁴.
    # K=2 (fixed-free), L=80mm → effective length 160mm.
    # P_cr = π² · 3500 · 12.566 / 160² ≈ 16.96 N
    # P_allowable (SF=3) ≈ 5.65 N. WARN band is 5.65–16.96 N.
    v = check_buckling(80, RoundSection(4), 10.0, end_condition="fixed-free")
    assert v.severity is Severity.WARN, v.message
    assert v.evidence["margin"] < 1.0


def test_end_condition_changes_capacity():
    """Fixed-fixed (K=0.5) is 16× stiffer than fixed-free (K=2.0):
    P_critical scales as 1/K²."""
    section = RoundSection(4)
    fixed_free = check_buckling(80, section, 0.0, end_condition="fixed-free")
    fixed_fixed = check_buckling(80, section, 0.0, end_condition="fixed-fixed")
    assert (
        fixed_fixed.evidence["P_critical_n"]
        == pytest.approx(16.0 * fixed_free.evidence["P_critical_n"], rel=1e-6)
    )


def test_unknown_end_condition_raises():
    with pytest.raises(ValueError, match="Unknown end_condition"):
        check_buckling(50, RoundSection(5), 1.0, end_condition="rolling-skating")


def test_negative_inputs_raise():
    with pytest.raises(ValueError):
        check_buckling(-50, RoundSection(5), 1.0)
    with pytest.raises(ValueError):
        check_buckling(50, RoundSection(5), -1.0)


def test_round_and_rect_section_modulus_consistent():
    """For comparable cross-sectional 'thickness', I is correctly computed."""
    rect = check_buckling(100, RectSection(5, 5), 0.0)
    rect_I = rect.evidence["second_moment_of_area_mm4"]
    assert rect_I == pytest.approx(5 * 5**3 / 12)

    rd = check_buckling(100, RoundSection(5), 0.0)
    rd_I = rd.evidence["second_moment_of_area_mm4"]
    assert rd_I == pytest.approx(math.pi * 5**4 / 64)


# ----- check_pressure_vessel -----


def test_low_pressure_thin_wall_passes():
    """1 bar (~100 kPa) on a 50mm radius / 5mm wall — well below PLA yield."""
    v = check_pressure_vessel(
        wall_thickness_mm=5, internal_radius_mm=50, internal_pressure_pa=100_000
    )
    assert v.severity is Severity.PASS
    # σ = 0.1 MPa · 50 / 5 = 1.0 MPa, well under PLA yield 50 MPa
    assert v.evidence["hoop_stress_mpa"] == pytest.approx(1.0, rel=1e-3)


def test_high_pressure_blocks():
    """50 bar on a 50mm radius / 1mm wall: σ = 5·50/1 = 250 MPa >> yield."""
    v = check_pressure_vessel(
        wall_thickness_mm=1, internal_radius_mm=50, internal_pressure_pa=5_000_000
    )
    assert v.severity is Severity.BLOCK
    assert "rupture" in v.message
    assert v.evidence["hoop_stress_mpa"] == pytest.approx(250.0, rel=1e-3)


def test_borderline_warns():
    """σ between allowable (50/3 ≈ 16.67) and yield (50)."""
    # σ = 30 target. wall=1mm, r=50mm → P = 30 · 1 / 50 = 0.6 MPa = 600_000 Pa
    v = check_pressure_vessel(
        wall_thickness_mm=1, internal_radius_mm=50, internal_pressure_pa=600_000
    )
    assert v.severity is Severity.WARN
    assert v.evidence["hoop_stress_mpa"] == pytest.approx(30.0, rel=1e-3)


def test_thick_wall_assumption_flag():
    """When wall >= radius/10, the thin-wall formula is too optimistic."""
    v = check_pressure_vessel(
        wall_thickness_mm=10, internal_radius_mm=50, internal_pressure_pa=100_000
    )
    assert v.evidence["thin_wall_assumption_valid"] is False
    assert "lower bound" in v.message


def test_thin_wall_assumption_valid_when_t_below_threshold():
    v = check_pressure_vessel(
        wall_thickness_mm=4, internal_radius_mm=50, internal_pressure_pa=100_000
    )
    assert v.evidence["thin_wall_assumption_valid"] is True
    assert "lower bound" not in v.message


def test_zero_pressure_passes_with_inf_margin():
    v = check_pressure_vessel(
        wall_thickness_mm=2, internal_radius_mm=50, internal_pressure_pa=0
    )
    assert v.severity is Severity.PASS
    assert v.evidence["hoop_stress_mpa"] == 0.0
    assert v.evidence["margin"] == math.inf


def test_negative_pressure_raises():
    with pytest.raises(ValueError):
        check_pressure_vessel(
            wall_thickness_mm=2, internal_radius_mm=50, internal_pressure_pa=-1.0
        )


def test_petg_holds_higher_pressure_than_pla_at_yield_boundary():
    """Same geometry: pressure that BLOCKs PLA may merely WARN PETG... but
    PETG actually has lower yield (45 vs 50). Use this as a regression check
    that material lookup wires through correctly."""
    pla = check_pressure_vessel(1, 50, 600_000, material="PLA")
    petg = check_pressure_vessel(1, 50, 600_000, material="PETG")
    assert pla.evidence["yield_mpa"] == 50.0
    assert petg.evidence["yield_mpa"] == 45.0
