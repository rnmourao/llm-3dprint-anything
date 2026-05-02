"""Stress numbers used in these tests come from σ = F · L / S, where:

  S_rect = b · h² / 6
  S_round = π · d³ / 32

PLA yield is 50 MPa. Default safety factor 3.0 → allowable 16.67 MPa.
"""

import math

import pytest

from validators import (
    YIELD_MPA_FDM,
    RectSection,
    RoundSection,
    Severity,
    check_cantilever,
)


# ----- section modulus correctness -----


def test_rect_section_modulus_formula():
    s = RectSection(width_mm=10, height_mm=5).section_modulus_mm3
    assert s == pytest.approx(10 * 5**2 / 6)


def test_round_section_modulus_formula():
    s = RoundSection(diameter_mm=5).section_modulus_mm3
    assert s == pytest.approx(math.pi * 5**3 / 32)


# ----- verdict thresholds -----


def test_strong_beam_passes():
    # Rect 10×5, L=20mm, F=1N: σ = 1·20/(10·25/6) = 120/250 = 0.48 MPa.
    # Allowable for PLA = 50/3 ≈ 16.67 MPa. Comfortable margin.
    v = check_cantilever(20, RectSection(10, 5), 1.0)
    assert v.severity is Severity.PASS
    assert v.evidence["applied_stress_mpa"] == pytest.approx(0.48, rel=1e-2)
    assert v.evidence["margin"] > 30


def test_overloaded_beam_blocks():
    # Rect 1×1, L=100mm, F=10N: σ = 10·100/(1·1/6) = 6000 MPa, way > yield 50.
    v = check_cantilever(100, RectSection(1, 1), 10.0)
    assert v.severity is Severity.BLOCK
    assert "exceeds" in v.message and "yield" in v.message


def test_borderline_warns():
    # Rect 5×5, L=100mm, F=1N: σ = 100/(5·25/6) = 100/20.83 = 4.8 MPa.
    # Below yield but well within margin → PASS. Need a load that puts stress
    # between allowable (16.67) and yield (50). σ = 30 MPa target.
    # 30 = F·100/20.83 → F = 6.25 N.
    v = check_cantilever(100, RectSection(5, 5), 6.25)
    assert v.severity is Severity.WARN
    assert v.evidence["applied_stress_mpa"] == pytest.approx(30.0, rel=1e-2)
    assert v.evidence["margin"] < 1.0


def test_round_section_works():
    # d=10, L=50, F=5: σ = 250/(π·1000/32) = 250/98.17 = 2.55 MPa → PASS
    v = check_cantilever(50, RoundSection(10), 5.0)
    assert v.severity is Severity.PASS
    assert v.evidence["section_modulus_mm3"] == pytest.approx(math.pi * 1000 / 32, rel=1e-3)


# ----- material lookup -----


def test_petg_has_lower_yield_than_pla():
    assert YIELD_MPA_FDM["PETG"] < YIELD_MPA_FDM["PLA"]


def test_unknown_material_raises():
    with pytest.raises(ValueError, match="Unknown material"):
        check_cantilever(10, RectSection(5, 5), 1.0, material="kryptonite")


def test_safety_factor_changes_threshold():
    """Same load, looser safety factor → can move from WARN to PASS."""
    section = RectSection(5, 5)
    # σ = 30 MPa (from earlier calc): WARN at SF=3, PASS at SF=1.5 (allowable 33.3).
    warn = check_cantilever(100, section, 6.25, safety_factor=3.0)
    looser = check_cantilever(100, section, 6.25, safety_factor=1.5)
    assert warn.severity is Severity.WARN
    assert looser.severity is Severity.PASS


def test_negative_inputs_raise():
    with pytest.raises(ValueError):
        check_cantilever(-10, RectSection(5, 5), 1.0)
    with pytest.raises(ValueError):
        check_cantilever(10, RectSection(5, 5), -1.0)
    with pytest.raises(ValueError):
        check_cantilever(10, RectSection(5, 5), 1.0, safety_factor=0)
