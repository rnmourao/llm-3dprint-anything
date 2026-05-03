"""Aggregate Verdicts from multiple validators into a single Report.

The orchestrator hands the Report back to the LLM after each render-then-
verify cycle (study 05). Every Verdict comes from a tool — the entire
report is deterministic, and the LLM should surface it verbatim rather
than ad-libbing numerical claims on top (study 04 routing rules).

Severity precedence for the rolled-up status:
  BLOCK > WARN > AUTO_REPAIRED > PASS
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from .types import Severity, Verdict

_SEVERITY_RANK: dict[Severity, int] = {
    Severity.PASS: 0,
    Severity.AUTO_REPAIRED: 1,
    Severity.WARN: 2,
    Severity.BLOCK: 3,
}

_SEVERITY_GLYPH: dict[Severity, str] = {
    Severity.PASS: "[OK]",
    Severity.AUTO_REPAIRED: "[FIX]",
    Severity.WARN: "[WARN]",
    Severity.BLOCK: "[BLOCK]",
}


@dataclass(frozen=True)
class Report:
    verdicts: list[Verdict] = field(default_factory=list)

    @property
    def status(self) -> Severity:
        if not self.verdicts:
            return Severity.PASS
        return max(self.verdicts, key=lambda v: _SEVERITY_RANK[v.severity]).severity

    @property
    def has_blockers(self) -> bool:
        return any(v.severity is Severity.BLOCK for v in self.verdicts)

    @property
    def has_warnings(self) -> bool:
        return any(v.severity is Severity.WARN for v in self.verdicts)

    def by_severity(self) -> dict[Severity, list[Verdict]]:
        grouped: dict[Severity, list[Verdict]] = defaultdict(list)
        for v in self.verdicts:
            grouped[v.severity].append(v)
        return dict(grouped)

    def counts(self) -> dict[str, int]:
        result = {sev.value: 0 for sev in Severity}
        for v in self.verdicts:
            result[v.severity.value] += 1
        return result

    def to_text(self) -> str:
        """Human-readable summary for the LLM to surface verbatim.

        Sorted worst-first so blockers float to the top, then by rule name
        for stable output across runs.
        """
        if not self.verdicts:
            return "No checks ran.\n"

        ordered = sorted(
            self.verdicts,
            key=lambda v: (-_SEVERITY_RANK[v.severity], v.rule),
        )

        counts = self.counts()
        counts_str = ", ".join(
            f"{sev.value}={counts[sev.value]}"
            for sev in (Severity.BLOCK, Severity.WARN, Severity.AUTO_REPAIRED, Severity.PASS)
            if counts[sev.value] > 0
        )

        lines = [f"Status: {self.status.value}", f"Counts: {counts_str}", ""]
        for v in ordered:
            lines.append(f"{_SEVERITY_GLYPH[v.severity]} {v.rule}")
            lines.append(f"   {v.message}")
            if v.suggested_action:
                lines.append(f"   -> {v.suggested_action}")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "counts": self.counts(),
            "verdicts": [
                {
                    "rule": v.rule,
                    "severity": v.severity.value,
                    "message": v.message,
                    "evidence": v.evidence,
                    "suggested_action": v.suggested_action,
                }
                for v in self.verdicts
            ],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


def aggregate(*verdict_iterables: Iterable[Verdict]) -> Report:
    """Combine verdicts from one or more validators into a single Report."""
    combined: list[Verdict] = []
    for it in verdict_iterables:
        combined.extend(it)
    return Report(verdicts=combined)
