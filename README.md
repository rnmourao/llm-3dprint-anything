# llm-3dprint-anything

Development repo for the **3d-print-anything** Claude skill — an upstream pre-CAD viability gate that interviews the user, drafts annotated OpenSCAD, runs deterministic geometric/physics/thermal validators, and hands off to slice + USB-serial print transport.

The deployable skill bundle lives under [skill/](skill/). Everything else here is dev-only (tests, background research, scripts, build tooling, in-progress run outputs).

First end-to-end run on real hardware completed 2026-05-03 against an Ender-3 S1 Pro: SCAD → validators → PrusaSlicer → 14,543 G-code lines streamed cleanly in 25m 7s, producing a peg-in-hole assembly that mates as predicted by the LC fit annotation.

## Repository layout

```
skill/                       ← deployable bundle (everything below ships)
  SKILL.md                   ← LLM-facing rule book (with YAML frontmatter)
  README.md                  ← skill marketplace page / consumer-facing docs
  requirements.txt           ← runtime Python deps
  validators/                ← 12 deterministic checks (mesh, fit, clash,
                                stability, gravity, structural, thermal, …)
  orchestrator/              ← parses SCAD intent annotations, renders STLs,
                                drives the validator sequence
  slicer/                    ← PrusaSlicer CLI wrapper, per-material profiles
  transport/                 ← Marlin/Klipper line-numbered streamer over USB
  examples/                  ← canonical SCAD designs + gravity-sim animations
    *.scad                   ← peg_in_hole, lamp_stand, pressure_bottle, …
    videos/                  ← MuJoCo gravity-settle GIFs, one per example

CLAUDE.md                    ← architectural principles and dev guidance
README.md                    ← this file
requirements-dev.txt         ← runtime deps + pytest
conftest.py                  ← inserts skill/ on sys.path for tests
tests/                       ← pytest suite (196 tests, ~1 s)
studies/                     ← background research justifying the LLM-vs-tool split
scripts/                     ← dev utilities (smoke print driver, video recorder,
                                skill-bundle packager)
scratch/                     ← run outputs (gitignored except for tracked
                                example renders that demo the orchestrator)
```

## Example animations

Each design in `skill/examples/` ships with a 2 s MuJoCo gravity simulation so you can see what `validators.check_settles_under_gravity` actually evaluates:

| Design | Animation |
|---|---|
| Peg in hole | [skill/examples/videos/peg_in_hole.gif](skill/examples/videos/peg_in_hole.gif) |
| Lamp stand | [skill/examples/videos/lamp_stand.gif](skill/examples/videos/lamp_stand.gif) |
| Pressure bottle | [skill/examples/videos/pressure_bottle.gif](skill/examples/videos/pressure_bottle.gif) |
| Slender antenna post | [skill/examples/videos/slender_antenna_post.gif](skill/examples/videos/slender_antenna_post.gif) |
| Press-fit insert | [skill/examples/videos/press_fit_insert.gif](skill/examples/videos/press_fit_insert.gif) |
| Wall-mount bracket | [skill/examples/videos/wall_mount_bracket.gif](skill/examples/videos/wall_mount_bracket.gif) |

Regenerate any of them with `.venv/bin/python scripts/record_gravity_videos.py [example_name]`.

## For contributors

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt   # runtime deps + pytest
.venv/bin/pytest tests/                         # full suite (~1 s)
```

The validator and transport pipelines need three external binaries that **are not** installed by `pip`:

| Binary | Why | macOS install |
|---|---|---|
| `openscad` | Renders SCAD → STL in Stage 3 | `brew install openscad` |
| `prusa-slicer` | Stage 4 STL → G-code | `brew install --cask prusaslicer` then `ln -s /Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer /opt/homebrew/bin/prusa-slicer` |
| Printer on USB | Stage 5 streaming | physical hardware (default driver paths: `/dev/cu.usb*`) |

All three are pluggable — tests inject fakes, so the suite passes without any of them. See [CLAUDE.md](CLAUDE.md) for the architectural principles (LLM-as-rule-book-reader, every-binary-pluggable) and read [studies/](studies/) for the discipline research justifying the LLM-vs-tool split.

### Live smoke commands

```bash
# Validator pipeline against the canonical smoke design
PYTHONPATH=skill .venv/bin/python -c "from pathlib import Path; from orchestrator import run_pipeline; \
    print(run_pipeline(Path('skill/examples/peg_in_hole.scad'), \
                       work_dir=Path('scratch/smoke')).to_text())"

# Slice the rendered assembly with the default PLA profile
PYTHONPATH=skill .venv/bin/python -c "from pathlib import Path; from slicer import slice_stl; \
    slice_stl(Path('scratch/smoke/assembly.stl'), \
              output_gcode=Path('scratch/smoke/assembly.gcode'))"

# Stream the G-code to a real printer (edit PORT in the script first)
.venv/bin/python scripts/print_smoke.py
```

## Deploying the skill

The skill is the contents of `skill/`. To produce a versioned deployable bundle:

```bash
.venv/bin/python scripts/build_skill.py
# → wrote dist/skill.tar.gz (30 files, ~7 MB with example animations)
```

The packager walks `skill/` deterministically and excludes `__pycache__`, `*.pyc`, `.pytest_cache`, and `.DS_Store`. The resulting tarball preserves the leading `skill/` directory, so unpackers see `skill/SKILL.md`, `skill/validators/`, etc. — matching the source layout. A manifest is printed to stdout for CI verification without unpacking. `dist/` is gitignored.

To install / use the skill (assuming the consumer's environment provides the three external binaries above):

```bash
tar xzf skill.tar.gz                    # unpacks into ./skill/
pip install -r skill/requirements.txt   # runtime Python deps
# point your Claude harness at skill/SKILL.md as the entry point
```

## For skill consumers

See [skill/README.md](skill/README.md) and [skill/SKILL.md](skill/SKILL.md).
