# llm-3dprint-anything

A generic Claude skill that takes a natural-language description of any object,
validates whether it is physically and geometrically viable, generates OpenSCAD
source, slices it to G-code, and sends the job to a 3D printer over USB serial.

> Status: **end-to-end on real hardware as of 2026-05-03.** 196/196 tests
> pass. Full pipeline ran against an Ender-3 S1 Pro (Marlin 2.0.8.28F4):
> SCAD → validators → real PrusaSlicer → 14,543 G-code lines streamed
> over USB in 25 m, producing a peg-in-hole assembly that mated as
> predicted by the LC fit annotation. See [Pending](#pending) for the
> remaining v1 limitations.

---

## Why this exists

Existing 3D-printing skills on the marketplace (e.g. `flowful-ai/cad-skill`,
`stigsb-devais/cad-skill`, `select-print-material`) handle **manufacturability**
— wall thickness, overhangs, watertight mesh, material choice. They assume the
*concept* is already physically coherent.

The gap: nothing checks whether the **object as described** obeys real-world
physics and design viability *before* CAD work begins. Examples of failures a
manufacturability skill won't catch:

- A "cup" with no closed bottom.
- A hinge with no defined axis of rotation.
- A cantilever that would snap under its own weight in PLA.
- Two parts described as separate but occupying the same volume.
- A center of mass outside the support footprint (object falls over).
- Threads that don't mate; assembly steps that aren't physically possible.
- A plastic part loaded above its glass-transition temperature.
- A pressurized vessel whose hoop stress exceeds yield.
- A slender column buckling under axial load before it yields.

This skill sits **upstream** of existing CAD skills as a pre-CAD viability
gate, then drives the full pipeline through to the physical print.

---

## Pipeline

```
natural-language description
        │
        ▼
┌───────────────────────────────┐
│ 1. Interview & Checklist      │  ← LLM (SKILL.md)
│    physical viability         │
└──────────┬────────────────────┘
           │ pass / revise
           ▼
┌───────────────────────────────┐
│ 2. OpenSCAD generation        │  ← LLM + intent annotations
└──────────┬────────────────────┘
           │ .scad
           ▼
┌───────────────────────────────┐
│ 3. Geometric + physics + heat │  ← orchestrator + validators/
│    & pressure validation      │     (real OpenSCAD, MuJoCo, trimesh)
└──────────┬────────────────────┘
           │ STL + Report
           ▼
┌───────────────────────────────┐
│ 4. Slice to G-code            │  ← slicer/ → PrusaSlicer CLI
└──────────┬────────────────────┘
           │ .gcode
           ▼
┌───────────────────────────────┐
│ 5. USB serial transport       │  ← transport/ → pyserial / Marlin protocol
└───────────────────────────────┘
```

---

## What's implemented

| Layer | Module | Purpose |
|---|---|---|
| Stage 1 (rule book) | [SKILL.md](SKILL.md) | LLM-facing interview script, intent-annotation grammar, render-then-verify loop, deterministic-vs-`[INFER]` reporting discipline |
| Stage 2 → 3 (orchestration) | [orchestrator/](orchestrator/) | Parses SCAD intent annotations, renders modules to STL via real OpenSCAD, drives the validator sequence, returns a `Report` |
| Stage 3 (validators) | [validators/](validators/) | Twelve deterministic checks across mesh integrity, clash, fit, stability, physics, structural, thermal — each returns `Verdict` objects with stable rule keys |
| Stage 4 (slice) | [slicer/](slicer/) | PrusaSlicer CLI wrapper with per-material profiles (PLA, PETG, ABS); pluggable for testing |
| Stage 5 (transport) | [transport/](transport/) | Marlin/Klipper line-numbered protocol with checksum, pluggable Transport (pyserial-backed `SerialTransport` or fake) |

### Validator catalogue

Every validator below returns a `Verdict` (or list of them); the
`Report.to_text()` aggregator the LLM surfaces verbatim is in
[validators/report.py](validators/report.py).

| Validator | What it answers | Key formula / approach |
|---|---|---|
| `check_mesh_integrity` | Is the STL slicer-ready? | Watertight, winding-consistent, non-manifold-edge counts (Trimesh) |
| `check_hard_clash` | Do any two parts interpenetrate unintentionally? | AABB pre-filter → boolean intersection (manifold3d), with whitelist & noise threshold |
| `check_clearance` | Do mating parts have the right gap for their fit class (RC/LC/LT/LN/FN)? | Vertex-sampled signed distance, FDM-adjusted clearance table |
| `check_static_stability` | Will the assembly tip over? | COM projection vs. convex hull of bed-contact vertices |
| `check_grounded` | Is every connected component supported? | Per-component lowest-vertex distance from bed plane |
| `check_settles_under_gravity` | Does each part stay put in a real physics sim? | MuJoCo headless rigid-body sim, drift > 1 mm or rotation > 5° → WARN |
| `check_cantilever` | Will a beam yield under a tip load? | Euler–Bernoulli σ = F·L / S |
| `check_buckling` | Will a slender column collapse under axial compression? | Euler P_critical = π²·E·I / (K·L)² |
| `check_pressure_vessel` | Will a printed container rupture? | Thin-wall hoop stress σ = P·r / t |
| `check_operating_temperature` | Does the material hold up at the operating temperature? | Static lookup vs. material's HDT and Tg |

### Material data

Single source of truth at [validators/materials.py](validators/materials.py).
PLA, PETG, ABS, with yield, Young's modulus, glass transition (Tg), heat
deflection (HDT), CTE, density. New materials are a one-line addition.

### Annotations the LLM writes into SCAD

```scad
// part: <name>
// fit: <a>~<b> class=<RC|LC|LT|LN|FN>
// clash_whitelist: <a>~<b>
// gravity: <-x|+x|-y|+y|-z|+z>
// bed_z: <value>
// operating: temp_c=<N>
// load: part=<name> force=<N> axis=<axis> length_mm=<L> section=<spec> [material=...]
// buckling: part=<name> axial_n=<F> length_mm=<L> section=<spec> [material=...] [end_condition=...]
// pressure: part=<name> internal_pa=<P> wall_thickness_mm=<t> radius_mm=<r> [material=...]
```

`<spec>` is `rect:<W>x<H>` or `round:<D>` in mm. The orchestrator's parser
([orchestrator/annotations.py](orchestrator/annotations.py)) maps each
annotation to a validator call automatically — the LLM never invokes
validators directly.

---

## Quick start

```bash
# one-time setup (Python 3.10+; the three external binaries below are
# required by stages 3–5 but are pluggable, so the test suite passes
# without any of them).
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
brew install openscad                    # macOS; Linux/Windows: use your package manager
brew install --cask prusaslicer          # ~150 MB; needed for stage 4
ln -s /Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer \
      /opt/homebrew/bin/prusa-slicer    # cask installs the .app; expose the CLI

# end-to-end smoke test on the canonical peg-in-hole assembly
.venv/bin/python -c "
from pathlib import Path
from orchestrator import run_pipeline
print(run_pipeline(Path('examples/peg_in_hole.scad'),
                   work_dir=Path('scratch/smoke')).to_text())
"
```

The smoke test prints a deterministic Report. The
[examples/peg_in_hole.scad](examples/peg_in_hole.scad) design is a peg
that goes up through a flat plate's hole with a 0.25 mm radial clearance
fit (LC class). The validator measures that clearance from the rendered
geometry, not from the SCAD constants.

For stage 5 (USB streaming), connect a Marlin/Klipper printer over USB
and pass the resulting `/dev/cu.usb*` (or `/dev/ttyUSB*` on Linux) device
to `transport.SerialTransport`. The first end-to-end run validated against
an Ender-3 S1 Pro at 115200 baud.

---

## Design principle

Recent benchmarks (2025–2026) show frontier LLMs are unreliable at 3D
geometric and physical computation:

- **GeoGramBench** — frontier LLMs score **<50%** on the hardest abstraction
  level of geometric-program reasoning.
- **PHYBench** — best model 36.9% vs. expert humans 61.9% on Olympiad-grade
  physics problems.
- **FEM-Bench** — consistent deficiencies in scientific computing.

Therefore the skill is a **triage nurse, not a doctor**: the LLM runs the rule
book and the interview; deterministic tools do the geometry kernel work. Every
numerical claim that flows back to the user is tagged `[OK]`/`[WARN]`/`[BLOCK]`
(came from a tool) or `[INFER]` (LLM judgement) — never both.

A second invariant runs through the codebase: every external-binary boundary
(OpenSCAD, PrusaSlicer, MuJoCo, pyserial) is **pluggable** so unit tests run
without the binary installed, and so future contributors can swap engines
(e.g., CuraEngine instead of PrusaSlicer) without touching the validator core.

The "fit vs. hold" split (interference checking is a different stage from
structural analysis) and the studies-driven research — distilled in
[studies/](studies/) — are the load-bearing architectural decisions; read those
before changing a validator.

---

## Pending

### Recently completed (2026-05-03)

- ✅ **Real printer end-to-end run.** Ender-3 S1 Pro on `/dev/cu.usbserial-110`
  at 115200 baud. 14,543 G-code lines streamed cleanly, zero resends, no errors.
  Surfaced two production gaps that are now fixed: `SliceProfile` lacked
  first-layer temperature fields (PrusaSlicer was emitting `S0` for layer-1 bed),
  and the streamer's `response_timeout_s` was applied uniformly to `M109`/`M190`
  (block-until-temp) commands that legitimately take minutes from cold.
- ✅ **Real PrusaSlicer slice.** Stage 4 against the actual binary, default
  PLA profile, 22 m PrusaSlicer estimate / 25 m actual streamed time.

### Documented v1 limitations (each pinned in module docstrings)

- `check_mesh_integrity` — non-manifold *vertex* and *self-intersection* detection
  deferred until a MeshLib / manifold3d backend is wired in. Edges are covered.
- `check_grounded` — flags components that don't touch the bed; doesn't yet
  detect a component supported by *another part* (a screw resting on a
  flange). Work-around: model interlocking parts as a single watertight mesh.
- `check_settles_under_gravity` — convex-hull collision for dynamic bodies
  (lossy on non-convex parts). Default `inter_part_collision=False` to avoid
  false positives on peg-in-hole geometry. `default_simulator` is z-axis-only.
- `check_cantilever` — point load at the tip only.
- `check_buckling` — single concentric axial load, ideal columns.
- `check_pressure_vessel` — thin-wall hoop stress only (valid when wall < radius/10).
- `check_operating_temperature` — static lookup against HDT and Tg only;
  transient thermal stress, creep over time, and coupled thermo-mechanical
  analysis are out of scope (need real FEA).
- `transport/` — no M105 keepalive thread (long heat-up commands now use a
  separate `long_block_timeout_s` default of 600 s instead). No flow control
  beyond the per-line ack. No pause/resume. Multi-part designs are still
  unioned into one STL before slicing, so co-printed mating parts may fuse
  if their gap is below the slicer's extrusion-width threshold.

### Open questions tracked in [studies/05](studies/05-synthesis-and-skill-spec.md)

- FDM-specific clearance calibration kit so users can dial in their printer's actual gap behavior.
- Vision-augmented validation (multi-view render → LLM consistency check).
- Boolean library robustness comparison (Trimesh / CadQuery / manifold3d) for production workloads.
- End-to-end evaluation harness: prompt → final printed object → human grade.

### Development notes

- **PyBullet did not build** on Python 3.12 + macOS arm64 (`_stdio.h:322`
  macro clash in the Apple SDK; PyBullet ships no wheels). Switched to
  **MuJoCo** which has prebuilt arm64 wheels and is genuinely a better fit
  (DeepMind quality contact dynamics). If PyBullet ever ships wheels for this
  platform, the pluggable-simulator pattern means swapping back is a one-file
  change in [validators/physics.py](validators/physics.py).
- **OpenSCAD module isolation** — initially the renderer used `include
  <file>`, which executes top-level code. Per-part renders therefore included
  the file's `assembly();` call and produced full-assembly STLs every time.
  Fixed by switching to `use <file>` (definitions only). Convention: every
  `// part:` module must be defined at its **final assembly position** —
  documented in [SKILL.md](SKILL.md) and the
  [example file header](examples/peg_in_hole.scad).
- **Test counts**: 196/196 passing as of 2026-05-03, runtime ~1 s. Real-MuJoCo
  integration tests run in `tests/test_physics.py`; everything else uses
  injected fakes for the external-binary boundaries.

---

## Research

A discipline-by-discipline survey informed every validator's design. The full
distillation lives in [studies/](studies/); a one-line summary per discipline:

- **BIM clash detection** ([studies/01](studies/01-bim-clash-detection.md))
  → hard / clearance / workflow taxonomy; named-rule structure; false-positive whitelisting.
- **Mechanical tolerance & fits** ([studies/02](studies/02-tolerance-and-fits.md))
  → fit-class vocabulary (RC/LC/LT/LN/FN); fit-vs-hold split; FDM-adjusted clearance table.
- **Mesh integrity & collision** ([studies/03](studies/03-mesh-integrity-and-collision.md))
  → broad/narrow-phase; non-manifold defect taxonomy; loud auto-repair.
- **LLM physical-reasoning limits** ([studies/04](studies/04-llm-physical-reasoning-limits.md))
  → empirical justification for the LLM-as-checklist split; routing rules.
- **Synthesis** ([studies/05](studies/05-synthesis-and-skill-spec.md))
  → routing table, validator API sketches, SKILL.md skeleton, open-questions list.

### Sources

- [All About Clash Detection with Navisworks (United-BIM)](https://www.united-bim.com/get-to-know-all-about-clash-detection-with-navisworks/)
- [MEP Coordination in BIM Using Revit, Navisworks, and Solibri (Vavetek)](https://vavetek.ai/blog/mep-coordination-in-bim-revit-navisworks-solibri/)
- [Automating clash relevance filtering using ML (ScienceDirect, 2025)](https://www.sciencedirect.com/science/article/pii/S0926580525006843)
- [Tolerance Analysis (Wikipedia)](https://en.wikipedia.org/wiki/Tolerance_analysis)
- [Essentials of Tolerance Analysis for Modern CAD Workflow (Autodesk)](https://www.autodesk.com/blogs/design-and-manufacturing/tolerance-analysis-autodesk-inventor/)
- [Types of Engineering Fits (Alibre)](https://www.alibre.com/blog/types-of-engineering-fits-clearance-interference-transition-explained/)
- [What Is Non-Manifold Geometry? (MeshLib)](https://meshlib.io/blog/non-manifold-meshes/)
- [3D Collision Detection (MDN)](https://developer.mozilla.org/en-US/docs/Games/Techniques/3D_collision_detection)
- [Collision Detection (Wikipedia)](https://en.wikipedia.org/wiki/Collision_detection)
- [GeoGramBench: Geometric Program Reasoning in LLMs (OpenReview)](https://openreview.net/forum?id=8wEQLCSfCT)
- [PHYBench: Holistic Evaluation of Physical Perception (arXiv)](https://arxiv.org/pdf/2504.16074)
- [FEM-Bench: Scientific Reasoning Benchmark (arXiv, 2025)](https://arxiv.org/html/2512.20732)

### Related skills (downstream — integrate, don't reimplement)

- [pjt222/select-print-material](https://skillsmp.com/skills/pjt222-agent-almanac-i18n-wenyan-ultra-skills-select-print-material-skill-md) — material selection (PLA, PETG, ABS, ASA, TPU, Nylon, SLA resins).
- [stigsb-devais/cad-skill](https://skillsmp.com/skills/stigsb-devais-claude-skills-cad-skill-skill-md) — parametric CadQuery generation with printability checks.
- [flowful-ai/cad-skill](https://skillsmp.com/skills/flowful-ai-cad-skill-skill-md) — same family; CadQuery + STL + multi-view previews.

---

## Hardware target

- Printer transport: **USB serial**, Marlin / Klipper-flavored G-code,
  line-numbered with checksum. `M109`/`M190`/`M191` (block-until-temperature)
  use a separate `long_block_timeout_s` (default 600 s); a true `M105`
  heartbeat thread is still pending — see [Pending](#pending).
- Slicer: **PrusaSlicer CLI** (headless), pluggable.
- Verified firmware: **Marlin 2.0.8.28F4** on a Creality Ender-3 S1 Pro
  (build volume 220×220×270 mm, CR Touch auto-level) — first end-to-end
  print on 2026-05-03. Klipper has not been exercised yet but uses the
  same line-numbered protocol.

## Roadmap

- [x] `SKILL.md` — interview prompts, checklist categories, decision rules.
- [x] `validators/` — mesh integrity, clash, fit, stability, grounded, physics, structural, buckling, pressure-vessel, thermal, plus aggregated reporting.
- [x] `orchestrator/` — SCAD intent-annotation parser + render-then-validate pipeline.
- [x] `slicer/` — PrusaSlicer CLI invocation with per-material profiles.
- [x] `transport/` — Marlin/Klipper line-numbered streamer over USB serial (pyserial-backed).
- [x] End-to-end smoke test against real OpenSCAD: validators pass on the example design.
- [x] End-to-end smoke test against real PrusaSlicer (2026-05-03).
- [x] First print on a real Marlin/Klipper printer over USB (2026-05-03, Ender-3 S1 Pro).
- [ ] M105 keepalive thread in the streamer.
- [ ] Per-part STL slicing so co-printed mating parts don't fuse (today's pipeline unions the assembly into one STL).
- [ ] Calibration-print routine for FDM clearance values.
- [ ] Vision-augmented stage-3 secondary check.

## License

TBD.
