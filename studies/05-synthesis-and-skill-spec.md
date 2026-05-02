# Study 05 — Synthesis: from research to validators and SKILL.md

This study is the bridge from the discipline research (studies 01–04) to executable design. It produces three concrete artefacts:

1. **Routing table** — every check we will run, who owns it (LLM vs. tool), what it costs.
2. **`validators/` module shape** — Python interfaces we should build, in dependency order.
3. **`SKILL.md` skeleton** — the LLM-facing structure: interview script, checklist categories, red-line rules.

References to upstream studies appear inline as **(→ NN)**.

---

## 1. Routing table — every check, with owner and tool

This is the operational version of the README's "Check / Owner / How" table, calibrated against the studies. The taxonomy (Hard / Clearance / Workflow / Integrity / Stability / Structural / Functional) is borrowed from BIM clash-detection (→ 01) and mechanical fit/hold separation (→ 02).

| # | Check | Category | Owner | Tool / formula | Stage | Severity if fails |
|---|---|---|---|---|---|---|
| 1 | Functional coherence ("cup with closed bottom?") | Functional | LLM | Checklist questioning | 1 | Block |
| 2 | Scale / proportion sanity (wall thickness ≥ 2× nozzle, etc.) | Functional | LLM | Lookup heuristics | 1 | Warn |
| 3 | Mesh non-manifold edges / vertices | Integrity | **Tool** | Trimesh `is_watertight` + MeshLib defect counts (→ 03) | 3 | Block (slicer rejects) |
| 4 | Inconsistent normals / winding | Integrity | **Tool** | Trimesh `is_winding_consistent`, `fix_normals` (→ 03) | 3 | Auto-repair, log loudly |
| 5 | Self-intersections | Integrity | **Tool** | Trimesh / `manifold3d` (→ 03) | 3 | Block |
| 6 | Holes / non-watertight | Integrity | **Tool** | Trimesh `fill_holes` with size cap (→ 03) | 3 | Auto-repair below cap, block above |
| 7 | Hard clash — two part-volumes interpenetrate unintentionally | Hard clash | **Tool** | AABB pre-filter → boolean intersection, `min_volume_mm3` threshold (→ 01, → 03) | 3 | Block |
| 8 | Soft clash — mating clearance under fit-class minimum | Clearance | **Tool** | Boolean with offset by fit-class gap (→ 01, → 02) | 3 | Block (if class is RC/LC and gap insufficient) |
| 9 | Static stability — COM over support polygon | Stability | **Tool** | Project COM onto print bed; check vs. convex hull of contact points | 3 | Warn (designer may want it deliberately tippy) |
| 10 | Cantilever / structural load (PLA, gravity only) | Structural | **Tool** (beam stub) or punt | Euler–Bernoulli back-of-envelope; flag if σ > σ_yield/safety | 3 | Warn |
| 11 | Assembly feasibility (verbal walkthrough) | Workflow | LLM | Verbal step-through interview (→ 01, → 03) | 1 | Warn |
| 12 | Print-orientation choice / overhangs / supports | Manufacturability | Existing skills (`flowful-ai/cad-skill` etc.) — **integrate, don't reimplement** | — | 4 | — |

**Red-line rules** (→ 04): the LLM must never produce numerical answers for items 3–10 from inference alone. Each numerical output is a tool result, tagged "deterministic" in the report.

---

## 2. `validators/` module shape

Build order is bottom-up — earlier modules have no dependencies on later ones.

```
validators/
├── __init__.py        # re-exports public API; documents non-goals
├── types.py           # Verdict, Severity, MeshReport, FitResult, etc. — pure dataclasses
├── mesh.py            # check_mesh_integrity, repair_mesh                  (→ 03)
├── clash.py           # check_hard_clash (AABB → boolean, threshold)       (→ 01, → 03)
├── fit.py             # check_clearance(part_a, part_b, fit_class)         (→ 02)
├── stability.py       # check_static_stability (COM over support polygon) (→ 04 punts; we still implement)
├── structural.py      # check_cantilever (Euler-Bernoulli stub)            (→ 02 fit-vs-hold)
└── report.py          # aggregate per-rule results into a single Report consumable by the LLM
```

### Public API contracts (sketches)

```python
# types.py
@dataclass(frozen=True)
class Verdict:
    rule: str               # "hard_clash", "stability_com_over_support", ...
    severity: Severity      # PASS | WARN | BLOCK | AUTO_REPAIRED
    message: str            # human-readable, LLM will surface verbatim
    evidence: dict          # numbers, file paths, screenshots — typed per rule
    suggested_action: str   # "thicken wall to >=1.6mm", etc.

# mesh.py
def check_mesh_integrity(stl_path: Path) -> list[Verdict]: ...
def repair_mesh(stl_path: Path, *, allow_destructive: bool = True) -> tuple[Path, list[Verdict]]: ...

# clash.py
def check_hard_clash(parts: list[Part], *, min_volume_mm3: float = 0.01,
                     whitelist: set[tuple[str, str]] = ()) -> list[Verdict]: ...

# fit.py
FIT_CLEARANCES_MM_FDM_PLA = {  # (→ 02 — FDM-adjusted, not ANSI B4.1)
    "RC": (0.30, 0.50),
    "LC": (0.20, 0.30),
    "LT": (0.10, 0.20),
    "LN": (-0.05, 0.05),
    "FN": (-0.20, -0.10),
}
def check_clearance(part_a: Part, part_b: Part, fit_class: str) -> Verdict: ...

# stability.py
def check_static_stability(mesh: Mesh, *, gravity_axis: str = "-z",
                           bed_z: float = 0.0) -> Verdict: ...

# structural.py
def check_cantilever(beam_length_mm: float, cross_section: CrossSection,
                     load_n: float, material: str = "PLA") -> Verdict: ...
```

**Non-goals — write into `__init__.py` so they don't drift** (→ 02, → 03, → 04):

- No statistical (RSS / Monte Carlo) tolerance analysis. FDM distributions aren't Gaussian.
- No continuous-time / motion-aware collision. Static intersection only.
- No FEA. `structural.py` is a beam-equation back-of-envelope. If the user needs FEA, the skill writes the input deck and shells out to CalculiX — separate workstream.
- No print-orientation / overhang / support analysis. That belongs to existing manufacturability skills downstream.

### Build order

1. `types.py` + `report.py` first — schemas are cheap, change everything if wrong.
2. `mesh.py` — required by every later validator (a non-watertight mesh fails all of them silently).
3. `clash.py` — depends on `mesh.py` for inputs.
4. `fit.py` — depends on `clash.py` (boolean-with-offset is just clash with inflation).
5. `stability.py` — independent of clash/fit, depends only on mesh + COM.
6. `structural.py` — last; the most likely to be punted in v1.

### Library choices (best current guess)

- **Trimesh** — primary; mesh integrity, COM, AABB.
- **manifold3d** — boolean robustness backend for Trimesh.
- **CadQuery / OpenCascade** — when boolean-with-offset / shell operations get fragile in Trimesh.
- **MeshLib (Python)** — fallback for hard repair cases (→ 03).
- **NumPy / SciPy** — beam equations, convex hull for stability.
- **No FEA dep in v1.** If we add one later: CalculiX (Linux-friendly, free, Abaqus-syntax input decks).

---

## 3. `SKILL.md` skeleton

The LLM-facing rule book. Each section has a one-sentence intent and the actual content the LLM should follow.

```markdown
# 3D-Print-Anything: pre-CAD viability gate

## Role
You are a triage nurse, not a doctor. (→ 04)
Your job is to (a) interview the user until the object's intent is unambiguous,
(b) generate first-draft OpenSCAD, (c) call validators on the rendered STL,
(d) report verified results to the user with clear deterministic-vs-judgement labels.

## Routing rules — MUST NOT DO IN YOUR HEAD
[... the red-line list from study 04 verbatim ...]

## Stage 1 — Interview & checklist (LLM-owned)

For every object, walk the user through these categories. Do not move on
until each is answered or explicitly skipped. Borrow the BIM hard/soft/workflow
taxonomy. (→ 01)

### 1.1 Functional coherence
- What is this object FOR?
- Does it hold something / contain something / connect to something?
- For each containment relation: is the geometry CLOSED on the contained side?
  ("a cup with no bottom")
- For each motion: what is the axis of rotation / sliding?
- For each load: where is it applied, in what direction, how much?

### 1.2 Mating features (use fit taxonomy from → 02)
For every two parts that touch or thread together:
- Is this RC (rotates), LC (slides in), LT (snug), LN (tight), or FN (press fit)?
- Print-direction-aware: is the mating axis vertical or horizontal on the bed?

### 1.3 Assembly walkthrough (workflow clash, → 01)
- Walk through the assembly in order. For each step, check:
  - Does the part being installed have a clear path into position?
  - Does any prior step block this one?

### 1.4 Stability prediction (LLM heuristic; tool will verify in stage 3)
- Where is the heaviest mass?
- What is the support footprint?
- If user describes balance-on-edge or top-heavy designs, flag for tool check.

## Stage 2 — OpenSCAD draft (LLM-owned, FRAGILE — → 04)
Generate first-draft SCAD. Expect ~50% to be geometrically wrong on hard cases.
Annotate every part with `// part_name: ...` and every mating feature with
`// fit_class: RC|LC|LT|LN|FN, gap_mm: <value>`.

## Stage 3 — Geometric validation (TOOL-owned)
Render SCAD → STL. Call:
1. validators.mesh.check_mesh_integrity
2. validators.clash.check_hard_clash
3. validators.fit.check_clearance (per mating-feature annotation)
4. validators.stability.check_static_stability
5. validators.structural.check_cantilever (only if a load was specified)

If any BLOCK-severity verdict: report to user, propose revision, return to stage 2.
If only WARN: report and ask user to confirm.

## Stage 4 — Slice (TOOL-owned)
Hand off to existing material-selection + manufacturability skill.

## Stage 5 — Print transport (TOOL-owned)
USB serial, line-numbered Marlin/Klipper G-code with checksum.

## Reporting format
Tag every result line:
  ✓ deterministic — tool name in parentheses
  ⚠ judgement   — your inference; explicitly hedge

Never invert these labels. Never produce a deterministic-tagged number you didn't get from a tool.
```

---

## 4. End-to-end open questions worth tracking

These came up in studies 01–04 and don't have answers yet. They aren't blockers for v1 but should be visible in the repo so they aren't forgotten.

- **FDM-specific clearance numbers** beyond fit-class lookup. Need: a small calibration print kit shipped with the skill so users can dial in *their* printer's actual clearance. (→ 02)
- **Clash whitelist UX.** When the user *intends* an intersection (e.g. screw boss into a part), how do they tell the validator? Probably an OpenSCAD comment annotation. (→ 01)
- **Repair-loud reporting.** What's the right user-facing message when the mesh validator silently deletes triangles? MeshLib's own warning is the template. (→ 03)
- **Render-then-verify loop budget.** How many SCAD revision attempts before we surface failure to the user? (→ 04 — given <50% LLM accuracy at hard tasks, retries are expected; but unbounded retry burns tokens.)
- **Vision-augmented validation.** Show the LLM a multi-view render of the candidate STL and ask "does this match what the user described?" — separate from the deterministic checks. Untested but cheap to add. (→ 04)
- **Boolean library robustness comparison.** Trimesh vs. CadQuery vs. manifold3d for the workloads we'll throw at them. (→ 03)
- **End-to-end evaluation harness.** A small test set of (description → expected verdicts) so we can measure our own accuracy and not just trust upstream benchmarks. (→ 04)
