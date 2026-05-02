"""Deterministic geometry validators — the tool side of the LLM/tool split.

The LLM does not call these directly in the prompt; the skill orchestrator does,
and the LLM only reads the structured Verdicts in the result.

v1 non-goals (kept here so they don't drift — see studies/05):
  * Statistical tolerance analysis (RSS / Monte Carlo). FDM distributions
    are not Gaussian; pretending otherwise is theatre.
  * Continuous-time / motion-aware collision. Static intersection only.
  * Finite-element analysis. structural.py (when added) is a beam back-of-
    envelope; real FEA is a separate workstream.
  * Print orientation, overhangs, support generation. That belongs to the
    downstream manufacturability skills (flowful-ai/cad-skill et al.).
"""

from .clash import check_hard_clash
from .fit import FIT_CLEARANCES_MM_FDM_PLA, check_clearance
from .materials import MATERIALS_FDM, Material, get_material, supported_materials
from .mesh import check_mesh_integrity, repair_mesh
from .physics import (
    Pose,
    SimRequest,
    SimResult,
    Simulator,
    check_settles_under_gravity,
    default_simulator,
)
from .report import Report, aggregate
from .stability import check_grounded, check_static_stability
from .structural import (
    YIELD_MPA_FDM,
    CrossSection,
    RectSection,
    RoundSection,
    check_buckling,
    check_cantilever,
    check_pressure_vessel,
)
from .thermal import check_operating_temperature
from .types import Part, Severity, Verdict

__all__ = [
    "FIT_CLEARANCES_MM_FDM_PLA",
    "MATERIALS_FDM",
    "Material",
    "YIELD_MPA_FDM",
    "CrossSection",
    "Part",
    "Pose",
    "RectSection",
    "Report",
    "RoundSection",
    "Severity",
    "SimRequest",
    "SimResult",
    "Simulator",
    "Verdict",
    "aggregate",
    "check_buckling",
    "check_cantilever",
    "check_clearance",
    "check_grounded",
    "check_hard_clash",
    "check_mesh_integrity",
    "check_operating_temperature",
    "check_pressure_vessel",
    "check_settles_under_gravity",
    "check_static_stability",
    "default_simulator",
    "get_material",
    "repair_mesh",
    "supported_materials",
]
