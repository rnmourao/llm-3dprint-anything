"""Geometry conventions for these fixtures:

  Clearance fits (RC/LC/LT) — two 1×1×1 boxes side-by-side. Box A at origin
  (spans -0.5 to 0.5 on x). Box B translated by (1.0 + gap, 0, 0) so its
  left face is at x = 0.5 + gap. min_signed_distance equals `gap`.

  Interference fits (LN/FN) — small 1×1×1 box B partially poking into a
  larger 10×10×10 box A. A spans -5..5. B translated by (5.0 + 0.5 - depth,
  0, 0) so B's left face is at x = 5 - depth (inside A by `depth`). The
  deepest interior B-vertex sits at signed distance -depth from A's right
  face. min_signed_distance equals -depth.
"""

import pytest
import trimesh

from validators import FIT_CLEARANCES_MM_FDM_PLA, Part, Severity, check_clearance


def _clearance_pair(name_a: str, name_b: str, *, gap: float) -> tuple[Part, Part]:
    a = trimesh.creation.box(extents=(1, 1, 1))
    b = trimesh.creation.box(extents=(1, 1, 1))
    b.apply_translation((1.0 + gap, 0, 0))
    return Part(name_a, a), Part(name_b, b)


def _interference_pair(name_a: str, name_b: str, *, depth: float) -> tuple[Part, Part]:
    a = trimesh.creation.box(extents=(10, 10, 10))
    b = trimesh.creation.box(extents=(1, 1, 1))
    b.apply_translation((5.0 + 0.5 - depth, 0, 0))
    return Part(name_a, a), Part(name_b, b)


# ----- clearance fits (positive gap) -----


def test_RC_within_spec_passes():
    a, b = _clearance_pair("shaft", "hole", gap=0.40)
    v = check_clearance(a, b, "RC")
    assert v.severity is Severity.PASS
    assert v.evidence["fit_class"] == "RC"
    assert v.evidence["actual_mm"] == pytest.approx(0.40, abs=1e-3)


def test_RC_too_tight_blocks():
    a, b = _clearance_pair("shaft", "hole", gap=0.10)
    v = check_clearance(a, b, "RC")
    assert v.severity is Severity.BLOCK
    assert "below spec minimum" in v.message
    assert "will not assemble" in v.message


def test_RC_too_loose_warns():
    a, b = _clearance_pair("shaft", "hole", gap=1.00)
    v = check_clearance(a, b, "RC")
    assert v.severity is Severity.WARN
    assert "rattle" in v.message


def test_LC_at_spec_midpoint_passes():
    a, b = _clearance_pair("dowel", "bracket", gap=0.25)
    v = check_clearance(a, b, "LC")
    assert v.severity is Severity.PASS


# ----- interference fits (negative gap = overlap) -----


def test_FN_within_spec_passes():
    a, b = _interference_pair("post", "boss", depth=0.15)
    v = check_clearance(a, b, "FN")
    assert v.severity is Severity.PASS
    assert v.evidence["actual_mm"] == pytest.approx(-0.15, abs=1e-3)


def test_FN_too_aggressive_blocks():
    a, b = _interference_pair("post", "boss", depth=0.40)
    v = check_clearance(a, b, "FN")
    assert v.severity is Severity.BLOCK
    assert "overlap too aggressively" in v.message


def test_FN_insufficient_interference_warns():
    a, b = _interference_pair("post", "boss", depth=0.05)
    v = check_clearance(a, b, "FN")
    assert v.severity is Severity.WARN
    assert "work loose" in v.message


def test_LN_borderline_zero_overlap_passes():
    """LN spec spans (-0.05, 0.05) — straddles zero. A near-zero gap is in spec."""
    a, b = _clearance_pair("a", "b", gap=0.02)
    v = check_clearance(a, b, "LN")
    assert v.severity is Severity.PASS


# ----- API edges -----


def test_unknown_fit_class_raises():
    a, b = _clearance_pair("a", "b", gap=0.4)
    with pytest.raises(ValueError, match="Unknown fit_class"):
        check_clearance(a, b, "XX")


def test_rule_key_is_lex_sorted():
    a, b = _clearance_pair("z", "a", gap=0.4)
    v = check_clearance(a, b, "RC")
    assert v.rule == "clearance:a~z"


def test_table_covers_all_documented_classes():
    assert set(FIT_CLEARANCES_MM_FDM_PLA) == {"RC", "LC", "LT", "LN", "FN"}
    for cls, (lo, hi) in FIT_CLEARANCES_MM_FDM_PLA.items():
        assert lo < hi, f"{cls}: spec_min must be < spec_max"
