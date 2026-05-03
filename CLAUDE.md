# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout (deploy-vs-dev split)

The repo is split into the **deployable skill bundle** under [skill/](skill/) and **dev-only** content at the root. Anything that ships to a skill consumer lives under `skill/`; anything used only for development, testing, or background research lives at the root.

```
skill/                      ← what the skill bundle ships
  SKILL.md                  ← LLM-facing rule book (with YAML frontmatter)
  README.md                 ← skill marketplace page / public docs
  requirements.txt          ← runtime Python deps
  validators/               ← 12 deterministic checks
  orchestrator/             ← pipeline that composes them
  slicer/                   ← PrusaSlicer CLI wrapper
  transport/                ← Marlin/Klipper streamer
  examples/                 ← canonical SCAD designs

CLAUDE.md                   ← this file (dev guidance)
README.md                   ← thin pointer to skill/README.md + dev quickstart
requirements-dev.txt        ← runtime deps + pytest
conftest.py                 ← puts skill/ on sys.path for tests
tests/                      ← pytest suite
studies/                    ← background research justifying the LLM-vs-tool split
scripts/                    ← dev utilities (smoke print, video recorder)
scratch/                    ← run outputs (gitignored)
```

## Repository status

End-to-end pipeline ran successfully on real hardware on 2026-05-03 (Ender-3 S1 Pro, full peg-in-hole print). 196/196 tests pass. See [skill/README.md](skill/README.md) for the public description.

### Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt   # one-time (runtime + pytest)
.venv/bin/pytest tests/                                                  # full suite (~1 s)
.venv/bin/pytest tests/test_mesh.py -v                                   # one module verbose
PYTHONPATH=skill .venv/bin/python -c "from pathlib import Path; from orchestrator import run_pipeline; \
    print(run_pipeline(Path('skill/examples/peg_in_hole.scad'), \
                       work_dir=Path('scratch/smoke')).to_text())"       # live smoke test
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
| Functional coherence (interview-style) | LLM | Checklist questioning in [skill/SKILL.md](skill/SKILL.md) |
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

## Module pointers (all under skill/)

- [skill/SKILL.md](skill/SKILL.md) — LLM-facing rule book. Interview script, OpenSCAD intent-annotation grammar, render-then-verify orchestration, deterministic-vs-`[INFER]` reporting discipline. Has YAML frontmatter for skill packaging.
- [skill/validators/](skill/validators/) — twelve deterministic checks, single-source material data ([skill/validators/materials.py](skill/validators/materials.py)), report aggregation. Each check returns `Verdict` objects with stable rule keys; `validators.aggregate(...)` combines them into a `Report` the LLM surfaces verbatim.
- [skill/orchestrator/](skill/orchestrator/) — parses SCAD intent annotations ([skill/orchestrator/annotations.py](skill/orchestrator/annotations.py)), renders modules to STL via real OpenSCAD, drives the validator sequence ([skill/orchestrator/pipeline.py](skill/orchestrator/pipeline.py)). Pluggable renderer + simulator parameters for testing.
- [skill/slicer/](skill/slicer/) — PrusaSlicer CLI wrapper ([skill/slicer/cli.py](skill/slicer/cli.py)) with per-material profiles ([skill/slicer/profile.py](skill/slicer/profile.py)).
- [skill/transport/](skill/transport/) — Marlin/Klipper line-numbered protocol with checksum ([skill/transport/protocol.py](skill/transport/protocol.py)) + streaming machine ([skill/transport/streamer.py](skill/transport/streamer.py)). Pluggable Transport (pyserial-backed `SerialTransport` or fake).
- [skill/examples/](skill/examples/) — canonical SCAD designs that exercise the pipeline (peg_in_hole, lamp_stand, pressure_bottle, slender_antenna_post, press_fit_insert, wall_mount_bracket).
- [tests/](tests/) — pytest, one file per validator/orchestrator/slicer/transport module. Run from repo root; `conftest.py` puts `skill/` on sys.path so test imports stay short (`from validators import ...`).
- [studies/](studies/) — discipline research (BIM, mechanical fits, mesh/collision, LLM benchmarks, synthesis) that justifies the LLM-vs-tool split. Dev-only. **Read the matching study before changing a validator.**

## Hardware / output target

- Printer transport: **USB serial**, Marlin / Klipper-flavored G-code, line-numbered with checksum. Protocol in [skill/transport/](skill/transport/). M105 keepalive thread is documented as a v1 limitation in [skill/transport/streamer.py](skill/transport/streamer.py); long-blocking M109/M190/M191 acks now use `long_block_timeout_s` (default 600 s) so they no longer time out waiting for cold heaters.
- Slicer: **PrusaSlicer CLI** (headless). Implemented in [skill/slicer/](skill/slicer/). Verified end-to-end against the real binary on 2026-05-03; `SliceProfile` carries explicit first-layer temperature fields so PrusaSlicer never emits `S0` for layer 1.

## Pending

- v1 limitations documented in module docstrings — read the docstring before extending: `check_grounded` doesn't model part-on-part support; `check_settles_under_gravity` uses convex-hull collision; `check_cantilever`/`check_buckling`/`check_pressure_vessel` are closed-form back-of-envelope rather than FEA; `check_operating_temperature` is a static lookup. These are intentional v1 boundaries — extending them belongs in a sibling module (`skill/validators/fea.py`) per [study 02](studies/02-tolerance-and-fits.md)'s fit-vs-hold split, not by overloading the existing checks.
- Multi-part slicing: today the orchestrator hands a single unioned `assembly.stl` to PrusaSlicer, so multi-part designs print as one piece. Future work: feed per-part STLs and let PrusaSlicer arrange them on the bed, with each part's print orientation validated against gravity stability AND support-economy.

## Downstream skills to integrate, not reimplement

This skill is meant to sit *upstream* of existing marketplace skills, not replace them. When work overlaps these areas, prefer integration over reinvention:

- `pjt222/select-print-material` — material selection (PLA, PETG, ABS, ASA, TPU, Nylon, SLA resins).
- `stigsb-devais/cad-skill`, `flowful-ai/cad-skill` — parametric CadQuery generation with printability checks (wall thickness, overhangs, watertight mesh).
