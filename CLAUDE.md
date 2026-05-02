# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

End-to-end pipeline implemented except the final hardware handoff. 191/191 tests pass. Real OpenSCAD drives Stages 1–3 against the smoke-test design ([examples/peg_in_hole.scad](examples/peg_in_hole.scad)); stages 4 (PrusaSlicer slice) and 5 (USB Marlin transport) are implemented with pluggable backends but the real binaries / real printer have not been exercised. See [README.md](README.md) for the public-facing description and the full Pending list.

### Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # one-time
.venv/bin/pytest tests/                                              # full suite (~1 s)
.venv/bin/pytest tests/test_mesh.py -v                               # one module verbose
.venv/bin/python -c "from pathlib import Path; from orchestrator import run_pipeline; \
    print(run_pipeline(Path('examples/peg_in_hole.scad'), \
                       work_dir=Path('scratch/smoke')).to_text())"   # live smoke test
```

## What this project is

A Claude skill that takes a natural-language description of an object and drives the full pipeline through to a physical 3D print:

```
NL description → viability interview → OpenSCAD → orchestrator+validators → slice → USB serial to printer
```

The novel contribution is **stage 3 (and parts of stage 1)**: a pre-CAD physical-viability gate that catches failures existing CAD/manufacturability skills (e.g. `flowful-ai/cad-skill`, `stigsb-devais/cad-skill`) miss because they assume the concept is already coherent — e.g. "cup with no bottom," cantilever that snaps under its own weight, COM outside the support footprint, mating threads that don't fit, parts that float when they should rest, hot pressurized walls that rupture.

## Load-bearing architectural principles

### 1. The LLM is the interviewer and rule-book reader, not the geometry kernel

This is informed by 2025–2026 benchmarks (GeoGramBench, PHYBench, FEM-Bench) showing frontier LLMs score <50% on hard geometric-program reasoning. Every numerical or geometric answer must be delegated to a deterministic tool.

When adding a new check, decide its owner using this split — and keep the split honest:

| Check type | Owner | Tool |
|---|---|---|
| Functional coherence (interview-style) | LLM | Checklist questioning in [SKILL.md](SKILL.md) |
| Scale / proportion sanity | LLM | Lookup-table heuristics |
| Mesh integrity (non-manifold, watertight) | Tool | `validators.check_mesh_integrity` |
| Interpenetration of described volumes | Tool | `validators.check_hard_clash` |
| Clearance / fit between mating parts | Tool | `validators.check_clearance` |
| Static stability (COM over support polygon) | Tool | `validators.check_static_stability` |
| Every part grounded? | Tool | `validators.check_grounded` |
| Does it stay put under simulated gravity? | Tool | `validators.check_settles_under_gravity` (MuJoCo) |
| Cantilever / structural load | Tool | `validators.check_cantilever` |
| Slender column buckling under axial compression | Tool | `validators.check_buckling` |
| Pressure-vessel hoop stress | Tool | `validators.check_pressure_vessel` |
| Operating-temperature material limits | Tool | `validators.check_operating_temperature` |
| Assembly feasibility / motion | LLM | Verbal walkthrough |

If you find yourself prompting the LLM to compute geometry, that is a bug. Move it to a tool.

The "fit vs. hold" split (interference checking and structural analysis are separate stages with separate tools — borrowed from mechanical-design tolerance analysis vs. FEA) is also load-bearing. Don't conflate them.

### 2. Every external-binary boundary is pluggable

OpenSCAD, PrusaSlicer, MuJoCo, pyserial — each is wrapped behind a `Renderer` / `Slicer` / `Simulator` / `Transport` callable, with a `default_*` production impl and tests that inject fakes. This pattern lets unit tests run without the binary installed and lets future contributors swap engines (CuraEngine instead of PrusaSlicer; Bullet instead of MuJoCo) without touching the validator core. **Preserve this when adding a new external dependency.**

## Directory layout

All directories below are implemented:

- [SKILL.md](SKILL.md) — LLM-facing rule book. Interview script, OpenSCAD intent-annotation grammar, render-then-verify orchestration, deterministic-vs-`[INFER]` reporting discipline.
- [validators/](validators/) — twelve deterministic checks, single-source material data ([validators/materials.py](validators/materials.py)), report aggregation. Each check returns `Verdict` objects with stable rule keys; `validators.aggregate(...)` combines them into a `Report` the LLM surfaces verbatim.
- [orchestrator/](orchestrator/) — parses SCAD intent annotations ([orchestrator/annotations.py](orchestrator/annotations.py)), renders modules to STL via real OpenSCAD, drives the validator sequence ([orchestrator/pipeline.py](orchestrator/pipeline.py)). Pluggable renderer + simulator parameters for testing.
- [slicer/](slicer/) — PrusaSlicer CLI wrapper ([slicer/cli.py](slicer/cli.py)) with per-material profiles ([slicer/profile.py](slicer/profile.py)).
- [transport/](transport/) — Marlin/Klipper line-numbered protocol with checksum ([transport/protocol.py](transport/protocol.py)) + streaming machine ([transport/streamer.py](transport/streamer.py)). Pluggable Transport (pyserial-backed `SerialTransport` or fake).
- [tests/](tests/) — pytest, one file per validator/orchestrator/slicer/transport module. Run from repo root.
- [studies/](studies/) — discipline research (BIM, mechanical fits, mesh/collision, LLM benchmarks, synthesis) that justifies the LLM-vs-tool split. **Read the matching study before changing a validator.**
- [examples/](examples/) — canonical SCAD designs that exercise the pipeline. Currently: `peg_in_hole.scad`.

## Hardware / output target

- Printer transport: **USB serial**, Marlin / Klipper-flavored G-code, line-numbered with checksum, `M105` heartbeat for keepalive. The protocol is implemented in `transport/`; the M105 keepalive thread is documented as a v1 limitation in [transport/streamer.py](transport/streamer.py) and is open future work.
- Slicer: **PrusaSlicer CLI** (headless). Implemented in `slicer/`; the binary itself has not been installed/run during development (the brew cask install was declined as out-of-scope when offered during a smoke test).

## Pending (full list in README.md)

- Connect to a real printer (user said "soon"). Until then the streamer's only contact with the world is its programmable fake transport.
- Run real PrusaSlicer (binary install pending).
- v1 limitations documented in module docstrings — read the docstring before extending: `check_grounded` doesn't model part-on-part support; `check_settles_under_gravity` uses convex-hull collision; `check_cantilever`/`check_buckling`/`check_pressure_vessel` are closed-form back-of-envelope rather than FEA; `check_operating_temperature` is a static lookup. These are intentional v1 boundaries — extending them belongs in a sibling module (`validators/fea.py`) per [study 02](studies/02-tolerance-and-fits.md)'s fit-vs-hold split, not by overloading the existing checks.

## Downstream skills to integrate, not reimplement

This skill is meant to sit *upstream* of existing marketplace skills, not replace them. When work overlaps these areas, prefer integration over reinvention:

- `pjt222/select-print-material` — material selection (PLA, PETG, ABS, ASA, TPU, Nylon, SLA resins).
- `stigsb-devais/cad-skill`, `flowful-ai/cad-skill` — parametric CadQuery generation with printability checks (wall thickness, overhangs, watertight mesh).
