import pytest
import trimesh

from validators import Part, Severity, check_hard_clash


def _box(name: str, *, extents=(10, 10, 10), translation=(0, 0, 0)) -> Part:
    m = trimesh.creation.box(extents=extents)
    m.apply_translation(translation)
    return Part(name=name, mesh=m)


def _verdict(verdicts, rule):
    matches = [v for v in verdicts if v.rule == rule]
    assert len(matches) == 1, f"expected 1 verdict for {rule}, got {len(matches)}"
    return matches[0]


def test_disjoint_pair_passes_at_broad_phase():
    a = _box("a")
    b = _box("b", translation=(100, 0, 0))
    verdicts = check_hard_clash([a, b])
    v = _verdict(verdicts, "hard_clash:a~b")
    assert v.severity is Severity.PASS
    assert v.evidence["phase"] == "broad"
    assert v.evidence["aabb_overlap"] is False


def test_overlapping_pair_blocks():
    a = _box("a")
    b = _box("b", translation=(5, 0, 0))  # 5×10×10 = 500 mm³ overlap
    verdicts = check_hard_clash([a, b])
    v = _verdict(verdicts, "hard_clash:a~b")
    assert v.severity is Severity.BLOCK
    assert v.evidence["phase"] == "narrow"
    assert v.evidence["intersection_volume_mm3"] == pytest.approx(500.0, rel=1e-3)


def test_whitelisted_intersection_passes():
    a = _box("a")
    b = _box("b", translation=(5, 0, 0))
    verdicts = check_hard_clash([a, b], whitelist={("a", "b")})
    v = _verdict(verdicts, "hard_clash:a~b")
    assert v.severity is Severity.PASS
    assert v.evidence["whitelisted"] is True


def test_whitelist_order_invariant():
    a = _box("a")
    b = _box("b", translation=(5, 0, 0))
    verdicts = check_hard_clash([a, b], whitelist={("b", "a")})
    assert _verdict(verdicts, "hard_clash:a~b").severity is Severity.PASS


def test_overlap_below_threshold_passes():
    """Real geometric overlap, but below `min_volume_mm3` → suppressed as noise."""
    a = _box("a")
    b = _box("b", translation=(5, 0, 0))  # 500 mm³ real overlap
    verdicts = check_hard_clash([a, b], min_volume_mm3=10_000.0)
    v = _verdict(verdicts, "hard_clash:a~b")
    assert v.severity is Severity.PASS
    assert v.evidence["phase"] == "narrow"
    assert v.evidence["intersection_volume_mm3"] > 0


def test_three_disjoint_parts_yields_three_pair_verdicts():
    parts = [
        _box("a"),
        _box("b", translation=(100, 0, 0)),
        _box("c", translation=(200, 0, 0)),
    ]
    verdicts = check_hard_clash(parts)
    rules = {v.rule for v in verdicts}
    assert rules == {"hard_clash:a~b", "hard_clash:a~c", "hard_clash:b~c"}
    for v in verdicts:
        assert v.severity is Severity.PASS


def test_duplicate_part_names_raises():
    a = _box("dup")
    b = _box("dup", translation=(100, 0, 0))
    with pytest.raises(ValueError, match="unique"):
        check_hard_clash([a, b])


def test_pair_rule_key_is_lex_sorted():
    """Regardless of input order, rule key uses sorted names."""
    a = _box("z")
    b = _box("a", translation=(100, 0, 0))
    verdicts = check_hard_clash([a, b])
    assert verdicts[0].rule == "hard_clash:a~z"
