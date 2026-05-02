import json

import pytest

from validators import Report, Severity, Verdict, aggregate


def _v(rule, severity, msg="msg", action="", **evidence) -> Verdict:
    return Verdict(rule=rule, severity=severity, message=msg, evidence=evidence,
                   suggested_action=action)


# ----- status / has_blockers / has_warnings -----


def test_empty_report_status_is_pass():
    r = Report()
    assert r.status is Severity.PASS
    assert r.has_blockers is False
    assert r.has_warnings is False


def test_all_pass_status_is_pass():
    r = Report([_v("a", Severity.PASS), _v("b", Severity.PASS)])
    assert r.status is Severity.PASS


def test_block_dominates_pass_and_warn():
    r = Report([
        _v("a", Severity.PASS),
        _v("b", Severity.WARN),
        _v("c", Severity.BLOCK),
        _v("d", Severity.AUTO_REPAIRED),
    ])
    assert r.status is Severity.BLOCK
    assert r.has_blockers is True
    assert r.has_warnings is True


def test_warn_without_block_is_warn():
    r = Report([_v("a", Severity.PASS), _v("b", Severity.WARN)])
    assert r.status is Severity.WARN
    assert r.has_blockers is False


def test_auto_repaired_outranks_pass():
    r = Report([_v("a", Severity.PASS), _v("b", Severity.AUTO_REPAIRED)])
    assert r.status is Severity.AUTO_REPAIRED


# ----- aggregation -----


def test_aggregate_concatenates_lists():
    r = aggregate(
        [_v("a", Severity.PASS)],
        [_v("b", Severity.WARN), _v("c", Severity.BLOCK)],
        [_v("d", Severity.PASS)],
    )
    assert isinstance(r, Report)
    assert [v.rule for v in r.verdicts] == ["a", "b", "c", "d"]
    assert r.status is Severity.BLOCK


def test_aggregate_no_args_is_empty_report():
    r = aggregate()
    assert r.verdicts == []
    assert r.status is Severity.PASS


# ----- by_severity / counts -----


def test_by_severity_groups_correctly():
    verdicts = [
        _v("a", Severity.PASS),
        _v("b", Severity.PASS),
        _v("c", Severity.WARN),
        _v("d", Severity.BLOCK),
    ]
    grouped = Report(verdicts).by_severity()
    assert len(grouped[Severity.PASS]) == 2
    assert len(grouped[Severity.WARN]) == 1
    assert len(grouped[Severity.BLOCK]) == 1
    assert Severity.AUTO_REPAIRED not in grouped


def test_counts_includes_zero_for_absent_severities():
    r = Report([_v("a", Severity.WARN)])
    counts = r.counts()
    assert counts == {"PASS": 0, "AUTO_REPAIRED": 0, "WARN": 1, "BLOCK": 0}


# ----- to_text -----


def test_to_text_orders_worst_first():
    r = Report([
        _v("aaa", Severity.PASS),
        _v("zzz", Severity.BLOCK),
        _v("mmm", Severity.WARN),
    ])
    text = r.to_text()
    block_idx = text.index("zzz")
    warn_idx = text.index("mmm")
    pass_idx = text.index("aaa")
    assert block_idx < warn_idx < pass_idx


def test_to_text_includes_status_header_and_counts():
    r = Report([_v("a", Severity.BLOCK), _v("b", Severity.WARN)])
    text = r.to_text()
    assert "Status: BLOCK" in text
    assert "BLOCK=1" in text
    assert "WARN=1" in text


def test_to_text_includes_suggested_action_when_present():
    r = Report([_v("a", Severity.BLOCK, action="thicken the wall")])
    assert "thicken the wall" in r.to_text()


def test_to_text_omits_arrow_when_no_action():
    r = Report([_v("a", Severity.PASS, action="")])
    assert "->" not in r.to_text()


def test_to_text_empty_report():
    assert "No checks ran" in Report().to_text()


# ----- to_dict / to_json -----


def test_to_dict_structure():
    r = Report([_v("a", Severity.BLOCK, msg="bad", action="fix it", count=3)])
    d = r.to_dict()
    assert d["status"] == "BLOCK"
    assert d["counts"]["BLOCK"] == 1
    assert d["verdicts"] == [
        {
            "rule": "a",
            "severity": "BLOCK",
            "message": "bad",
            "evidence": {"count": 3},
            "suggested_action": "fix it",
        }
    ]


def test_to_json_round_trips_to_to_dict():
    r = Report([_v("a", Severity.WARN, msg="x")])
    parsed = json.loads(r.to_json())
    assert parsed == r.to_dict()
