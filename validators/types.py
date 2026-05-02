from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import trimesh


class Severity(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    BLOCK = "BLOCK"
    AUTO_REPAIRED = "AUTO_REPAIRED"


@dataclass(frozen=True)
class Verdict:
    rule: str
    severity: Severity
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)
    suggested_action: str = ""


@dataclass
class Part:
    """A named volume in a multi-part assembly.

    name is used in verdict messages and the clash whitelist. Different parts
    must have distinct names — the clash check uses pair-of-names as the rule key.
    """

    name: str
    mesh: "trimesh.Trimesh"
