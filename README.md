# llm-3dprint-anything

A generic Claude skill that takes a natural-language description of any object, validates whether it is physically and geometrically viable, generates OpenSCAD source, slices it to G-code, and sends the job to a 3D printer over USB serial.

> Status: **early scaffolding.** This README captures the design rationale and the research that informed it, so the implementation can be built against an explicit problem statement rather than improvised.

---

## Why this exists

Existing 3D-printing skills on the marketplace (e.g. `flowful-ai/cad-skill`, `stigsb-devais/cad-skill`, `select-print-material`) handle **manufacturability** — wall thickness, overhangs, watertight mesh, material choice. They assume the *concept* is already physically coherent.

The gap: nothing checks whether the **object as described** obeys real-world physics and design viability *before* CAD work begins. Examples of failures a manufacturability skill won't catch:

- A "cup" with no closed bottom.
- A hinge with no defined axis of rotation.
- A cantilever that would snap under its own weight in PLA.
- Two parts described as separate but occupying the same volume.
- A center of mass outside the support footprint (object falls over).
- Threads that don't mate; assembly steps that aren't physically possible.

This skill is meant to sit **upstream** of the existing CAD skills as a pre-CAD viability gate, then drive the full pipeline through to the physical print.

---

## Pipeline

```
natural-language description
        │
        ▼
┌─────────────────────────┐
│ 1. Interview & Checklist│  ← LLM (this skill)
│    physical viability   │
└──────────┬──────────────┘
           │ pass / revise
           ▼
┌─────────────────────────┐
│ 2. OpenSCAD generation  │  ← LLM + scad templates
└──────────┬──────────────┘
           │ .scad
           ▼
┌─────────────────────────┐
│ 3. Geometric validation │  ← deterministic tools
│    (Trimesh, CadQuery)  │     (interpenetration,
│                         │      mesh integrity, COM)
└──────────┬──────────────┘
           │ STL
           ▼
┌─────────────────────────┐
│ 4. Slice to G-code      │  ← PrusaSlicer / CuraEngine CLI
└──────────┬──────────────┘
           │ .gcode
           ▼
┌─────────────────────────┐
│ 5. USB serial transport │  ← pyserial / printrun
└─────────────────────────┘
```

---

## Design principle: hybrid skill, not pure prompt

Recent benchmarks (2025–2026) show frontier LLMs are unreliable at 3D geometric and physical computation:

- **GeoGramBench** — frontier LLMs score **<50%** on the hardest abstraction level of geometric-program reasoning.
- **PHYBench** — physics symbolic-derivation, similar gap.
- **FEM-Bench** — finite element method coding, exposes consistent deficiencies in scientific computing.

Therefore the skill is a **triage nurse, not a doctor**: the LLM runs the rule book and the interview; deterministic tools do the geometry kernel work.

| Check | Owner | How |
|---|---|---|
| Functional coherence ("cup with no bottom") | LLM | Checklist questioning |
| Scale / proportion sanity (wall vs. span, nozzle limits) | LLM | Lookup-table heuristics |
| Interpenetration of described volumes | **Tool** | CadQuery / Trimesh boolean intersection |
| Mesh integrity (non-manifold, watertight) | **Tool** | Trimesh / MeshLib |
| Static stability (COM over support polygon) | **Tool** | Python: project COM, check vs. convex hull of contacts |
| Cantilever / structural load | **Tool or punt** | Beam-equation back-of-envelope, or flag for FEA |
| Assembly feasibility / motion | LLM | Verbal walkthrough |
| Clearance / fit between mating parts | **Tool** | Boolean with offset (clearance distance) |

---

## Research: how other disciplines handle 3D-model validation

The following survey informed the skill's architecture. Every column of the table above borrows from a discipline that already solved a piece of the problem.

### 1. House architecture / construction — BIM clash detection

A ~20-year-old discipline. Tools (Navisworks, Solibri, Revizto) load a federated 3D model and run three types of checks:

- **Hard clash** — actual geometry intersection ("two volumes in the same space").
- **Soft / clearance clash** — within a tolerance distance (e.g. an insulated pipe needs N mm of gap).
- **Workflow clash** — temporal conflicts (installation order).

Solibri is **rule-based** (named rules over geometry+metadata); Navisworks is **geometry-intersect**. Active ML research on "clash relevance" filtering exists because raw clash detection produces thousands of false positives.

**Lesson borrowed:** the hard / clearance / workflow taxonomy maps directly onto our checklist categories. The rule-based model fits an LLM checklist well.

### 2. Industrial / mechanical design — tolerance analysis + interference fits

Validation is split into two passes:

- **Tolerance stack-ups** — worst-case (arithmetic) or statistical (RSS / Monte Carlo) to predict whether parts fit across manufacturing variation.
- **Interference detection** — boolean intersection between mating parts in CAD; classified as clearance / transition / interference fit.

Stress and structural viability is a *separate* tool (FEA — finite element analysis), not part of interference checking.

**Lesson borrowed:** "does it fit" and "will it hold" are **different checks** with different tools. The skill keeps them as distinct stages.

### 3. Video games — mesh integrity + runtime colliders

Two layers:

- **Mesh integrity** — non-manifold edges, duplicate vertices, isolated geometry, inconsistent normals. Done once at import; libraries (MeshLib, Open3D, Trimesh) do this deterministically.
- **Runtime collision** — uses simplified colliders (AABB, OBB, sphere, GJK, BVH) — *not* the visible mesh. Game "physics" is an approximation built from primitives, not real-world physics.

**Lesson borrowed:** mesh-integrity checks are cheap, deterministic, and 100% solvable — they belong in a tool call, not a prompt. The skill never asks the LLM to reason about non-manifold edges.

### 4. LLM physical reasoning — current limits

- **GeoGramBench** — frontier LLMs <50% on the hardest abstraction level of geometric-program reasoning.
- **PHYBench** — physics symbolic-derivation, similar gap.
- **FEM-Bench** — finite element coding, consistent deficiencies in scientific computing.
- **EquiLLM** — research bolting E(3)-equivariant encoders onto LLMs precisely because raw LLMs are weak at 3D.

**Lesson borrowed:** the LLM is the interviewer and rule-book reader, not the geometry kernel. Every numerical answer is delegated to a tool.

---

## Sources

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

### Related skills (already on skillsmp.com)

These solve adjacent problems and will plug into this pipeline downstream:

- [pjt222/select-print-material](https://skillsmp.com/skills/pjt222-agent-almanac-i18n-wenyan-ultra-skills-select-print-material-skill-md) — material selection (PLA, PETG, ABS, ASA, TPU, Nylon, SLA resins) given functional and environmental requirements.
- [stigsb-devais/cad-skill](https://skillsmp.com/skills/stigsb-devais-claude-skills-cad-skill-skill-md) — parametric CadQuery generation with printability checks (wall thickness, overhangs, watertight mesh).
- [flowful-ai/cad-skill](https://skillsmp.com/skills/flowful-ai-cad-skill-skill-md) — same family; CadQuery + STL + multi-view previews + print recommendations.

---

## Roadmap

- [ ] `SKILL.md` — interview prompts, checklist categories, decision rules.
- [ ] `validators/` — Python module: mesh integrity, interpenetration, COM stability, clearance.
- [ ] `scad/` — OpenSCAD templates and generator wrappers.
- [ ] `slicer/` — PrusaSlicer / CuraEngine CLI invocation with profile selection.
- [ ] `transport/` — `pyserial`-based G-code streamer over USB serial (target: any Marlin / Klipper printer accepting line-numbered G-code with checksum).
- [ ] End-to-end smoke test: prompt → printed object.

## Hardware target

- Printer transport: **USB serial** (Marlin / Klipper-flavored G-code, line-numbered with checksum, `M105` heartbeat for keepalive).
- Slicer: TBD (PrusaSlicer CLI is the leading candidate for headless invocation).

## License

TBD.
