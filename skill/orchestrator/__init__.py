"""SKILL.md Stage 3 orchestrator: parse SCAD intent → render → run validators.

This package is the operational glue between the LLM (which writes
annotated SCAD) and the deterministic validators (which return Verdicts).
The LLM never calls validators directly — it calls `run_pipeline` and
surfaces the resulting Report verbatim.
"""

from .annotations import Buckling, Intent, Load, Pressure, parse_annotations
from .pipeline import (
    RenderRequest,
    Renderer,
    default_renderer,
    run_pipeline,
)

__all__ = [
    "Buckling",
    "Intent",
    "Load",
    "Pressure",
    "RenderRequest",
    "Renderer",
    "default_renderer",
    "parse_annotations",
    "run_pipeline",
]
