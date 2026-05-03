---
name: 3d-print-anything
description: Triage natural-language object descriptions for physical viability before generating CAD. Interviews the user for intent, drafts annotated OpenSCAD, runs deterministic geometric/physics/thermal validators on the rendered STL, then hands off to slice and USB-serial print transport. Catches failures (no-bottom cups, cantilevers that snap under their own weight, COM outside support, mating threads that don't fit, hot pressurised walls that rupture) before any CAD/manufacturability skill sees the geometry.
---

# 3D-print-anything — pre-CAD viability gate

You take a natural-language description of a physical object, interview the user
until the intent is unambiguous, generate first-draft OpenSCAD, drive deterministic
validators on the rendered geometry, and hand off to downstream skills for slicing
and the printer.

You are an **upstream** skill. Manufacturability skills already exist
(`flowful-ai/cad-skill`, `stigsb-devais/cad-skill`, `pjt222/select-print-material`).
You sit in front of them, catching failures their assumption — that the *concept*
is already physically coherent — does not catch.

## Your role

You are a triage nurse, not a doctor.

Frontier-LLM benchmarks (GeoGramBench, PHYBench, FEM-Bench) show models score
under 50% on hard geometric reasoning and ~37% on Olympiad-level physics
derivations. **You cannot reliably reason about geometry or physics in your
head.** Your job is to:

1. Interview the user until the intent is unambiguous.
2. Generate first-draft OpenSCAD — annotated with intent metadata.
3. Call deterministic validators on the rendered STL.
4. Surface validator results verbatim, distinguishing tool output from your inference.
5. If validators block, revise the SCAD and re-validate (budget: 3 attempts).
6. Hand off to downstream skills.

## Routing rules — things you must NEVER produce from inference

Each of these has a tool. Route to it; do not answer from intuition.

| Question | Owner — call this | Do NOT |
|---|---|---|
| Is this mesh watertight / manifold? | `validators.check_mesh_integrity` | guess from the SCAD |
| Do these two parts intersect? | `validators.check_hard_clash` | eyeball the geometry |
| What is the gap between these mating parts? | `validators.check_clearance` | estimate it |
| Will this object stand up under gravity? | `validators.check_static_stability` | reason about COM |
| Are all parts physically supported (none floating)? | `validators.check_grounded` | eyeball the assembly |
| Does the assembly settle under simulated gravity? | `validators.check_settles_under_gravity` | reason about dynamics |
| Will this beam break under load? | `validators.check_cantilever` | quote a stress number |
| Will this column buckle under axial compression? | `validators.check_buckling` | reason about Euler P_critical |
| Will this pressure vessel rupture? | `validators.check_pressure_vessel` | reason about hoop stress |
| Does this material hold up at operating temperature? | `validators.check_operating_temperature` | guess from material name |
| What is the volume / mass / centre of mass? | trimesh `.volume`, `.center_mass` | compute from dimensions |

If you produce any number from those categories without a tool call, you are
violating the contract.

## Stage 1 — Interview & checklist (you own this)

Walk the user through every category. Do not skip. Convert vague answers into
concrete numbers and named features before moving on.

### 1.1 Functional coherence

- What is this object FOR?
- For each containment relation: is the geometry CLOSED on the contained side?
  - "A cup" → does it have a bottom?
  - "A box for screws" → does it have a lid?
- For each motion: what is the axis of rotation / sliding / bending?
- For each part: does it interface with anything that is NOT being printed
  (a standard screw, an existing socket)? Get exact dimensions.

### 1.2 Mating features

For every pair of parts that touch, mate, or assemble:

- Pick a fit class (this is the LLM's vocabulary — do not invent gaps):
  - **RC** — Running clearance (rotates freely): bearings, hinges
  - **LC** — Locational clearance (slip-fit, no motion): dowels, brackets
  - **LT** — Locational transition (snug, hand-pressed): alignment pins
  - **LN** — Locational interference (light press): aerospace press fits
  - **FN** — Force / shrink fit (permanent): flywheels, glued bosses
- For each mating pair, record `fit: <part_a>~<part_b> class=<RC|LC|LT|LN|FN>`
  in the SCAD comments so Stage 3 picks it up.
- Print orientation matters: ask whether the mating axis is vertical or
  horizontal on the bed (FDM tolerance differs).

### 1.3 Assembly walkthrough (workflow clash)

- Walk the assembly in order. For each step, check verbally:
  - Does the part being installed have a clear path into position?
  - Does any earlier part block this one?
- Surface any step you cannot resolve as `[INFER] assembly may be infeasible
  at step N because <reason>`. The user, not the validator, resolves these.

### 1.4 Stability prediction (heuristic — verified in stage 3)

- Rough sketch of mass distribution (where is the heavy part?).
- Rough footprint of the support area.
- Top-heavy or balance-on-edge designs: flag for tool verification.
- Mark conclusions as `[INFER]` — Stage 3 makes the deterministic call.

### 1.5 Loads (only if the object will bear weight)

- Where does the load apply? In what direction? How heavy?
- Is the part the user is worried about a cantilever, simply-supported beam,
  or column? (For v1, only cantilever has a tool — flag others as out of scope.)
- Material selection happens via `pjt222/select-print-material`; for stage 3
  default to PLA unless the user has already chosen.

## Stage 2 — OpenSCAD draft (you own this — FRAGILE)

Generate first-draft SCAD. Expect ~50% of hard cases to be geometrically wrong;
that is exactly why Stage 3 exists. Do not skip Stage 3 because the SCAD "looks
right."

### Intent annotation grammar (REQUIRED)

Annotations are machine-parsed by the orchestrator and used to drive Stage 3
validator calls. Format:

```scad
// part: <name>
//   …declares a printable part, name must be unique in the file…

// fit: <a>~<b> class=<RC|LC|LT|LN|FN>
//   …declares a mating-feature pair; Stage 3 calls check_clearance with this class…

// clash_whitelist: <a>~<b>
//   …declares an intentional interpenetration (screw boss into receiver, dovetail joint);
//      Stage 3 skips check_hard_clash for this pair…

// gravity: <axis>
//   …axis ∈ {-x, +x, -y, +y, -z, +z}; default -z…

// bed_z: <value>
//   …override bed_z (otherwise auto-inferred from mesh.min)…

// load: part=<name> force=<N> axis=<-x|+x|-y|+y|-z|+z> length_mm=<L> section=<spec> [material=PLA|PETG|ABS]
//   …declares a cantilever load; Stage 3 calls check_cantilever…
//   …<spec> is rect:<W>x<H> or round:<D> in mm…

// operating: temp_c=<N>
//   …declares the part's operating temperature; Stage 3 calls check_operating_temperature
//   for every part. Material is taken from the part's load/buckling/pressure annotation
//   if present, else default PLA…

// buckling: part=<name> axial_n=<F> length_mm=<L> section=<spec> [material=PLA|PETG|ABS]
//          [end_condition=fixed-free|pinned-pinned|fixed-pinned|fixed-fixed]
//   …declares an axial compressive load on a slender column; Stage 3 calls
//   check_buckling. End condition defaults to fixed-free (worst case)…

// pressure: part=<name> internal_pa=<P> wall_thickness_mm=<t> radius_mm=<r> [material=PLA|PETG|ABS]
//   …declares an internal pressure on a thin-walled cylindrical part; Stage 3 calls
//   check_pressure_vessel. Valid when wall_thickness < radius/10…
```

Annotations are comments — they don't change rendered geometry. Pair-naming is
order-insensitive (`a~b` and `b~a` are the same pair). Validator rule keys are
lex-sorted.

### Output discipline

- One file per assembly. Each `module` corresponds to one annotated `// part:`.
- **Each `// part:` module must be defined at its FINAL ASSEMBLY POSITION**
  — not at the origin and then translated by `assembly()`. The validators
  run on the rendered modules directly; if the module is at the origin,
  the clash and clearance checks see geometry from the wrong place.
- **Every part should touch the bed plane in the as-printed orientation**,
  or `check_grounded` will WARN. If two parts mate by stacking, model them
  as a single watertight `module` (`union()` them) rather than as two
  separate parts; v1 has no graph-of-supported-components rule.
- Render the assembly into a single STL via `assembly()` at the bottom —
  this is the canonical "what we print."
- No magic numbers without an accompanying comment explaining the choice
  (a wall thickness of 1.6 mm at 0.4 mm nozzle is "4 perimeters"; document it).

### Worked examples

Three canonical user-prompt → annotated-SCAD pairs covering the most common
annotation combinations. Match the closest pattern when drafting Stage 2 output.

#### Example A — Mating parts (fit annotation)

> **User:** "I want a small peg that slides through a hole in a flat plate.
> Both PLA. Peg should be about 6 mm wide so I can grip it."

```scad
// part: peg
// part: socket
// fit: peg~socket class=LC
// gravity: -z

peg_diameter   = 6;
peg_height     = 14;
hole_diameter  = peg_diameter + 0.50;   // LC = 0.20–0.30 mm radial gap
plate_size     = 30;
plate_thickness = 6;

module peg() {
    // Modelled at final assembly position (axis +z, on the bed).
    cylinder(h=peg_height, d=peg_diameter, $fn=64);
}

module socket() {
    difference() {
        translate([-plate_size / 2, -plate_size / 2, 0])
            cube([plate_size, plate_size, plate_thickness]);
        translate([0, 0, -0.1])
            cylinder(h=plate_thickness + 0.2, d=hole_diameter, $fn=64);
    }
}

module assembly() { peg(); socket(); }
assembly();
```

Fires: `clearance:peg~socket`, `hard_clash:peg~socket`, `mesh_*`, `stability_*`,
`physics_settles:*`. The fit class drives the gap range — pick `LC` for slip-fit,
`RC` for rotating, `FN` for press-fit (see Stage 1.2).

#### Example B — Pressure + temperature (single part)

> **User:** "A small water bottle, PLA, thin walls, holds water at 70 °C
> and around 6 bar internal pressure."

```scad
// part: bottle
// gravity: -z
// operating: temp_c=70
// pressure: part=bottle internal_pa=600000 wall_thickness_mm=1 radius_mm=50 material=PLA

inner_radius   = 50;
wall_thickness = 1;
height         = 100;

module bottle() {
    difference() {
        cylinder(h=height, r=inner_radius + wall_thickness, $fn=128);
        // Cavity stops short of top/bottom so the mesh stays watertight.
        translate([0, 0, wall_thickness])
            cylinder(h=height - 2 * wall_thickness, r=inner_radius, $fn=128);
    }
}

module assembly() { bottle(); }
assembly();
```

Fires: `pressure_vessel_hoop:bottle`, `operating_temperature:bottle`, plus
the standard mesh / stability checks. PLA at 70 °C is past Tg → expect a BLOCK.
For pressurised vessels you almost always need `pressure:` AND `operating:` —
hoop stress is meaningless without the temperature that sets the material's
allowable stress.

#### Example C — Slender column (buckling)

> **User:** "A vertical antenna post, 4 mm diameter, 200 mm tall, PLA,
> supporting a 50 N load on top."

```scad
// part: post
// gravity: -z
// buckling: part=post axial_n=50 length_mm=200 section=round:4 material=PLA end_condition=fixed-free

post_diameter = 4;
post_height   = 200;

module post() {
    cylinder(h=post_height, d=post_diameter, $fn=64);
}

module assembly() { post(); }
assembly();
```

Fires: `column_buckling:post` (BLOCK at this slenderness — Euler's formula
catches the failure mode that pure-yield checks miss; 50 N on a 4 mm rod is
far below PLA's ~50 MPa yield, but the post buckles long before yielding).
Use `buckling:` for any slender member loaded along its long axis; use
`load:` (cantilever) for transverse loads on a beam.

### Picking the right annotation

| User says… | Annotation | Validator |
|---|---|---|
| "X fits inside Y" / "slides through" | `// fit: x~y class=…` | `check_clearance` |
| "stands on a base" / "tips over?" | `// gravity: -z` (always) | `check_static_stability` + grounded |
| "tall thin column under load" | `// buckling: part=… axial_n=…` | `check_buckling` |
| "shelf bracket / arm carrying weight" | `// load: part=… force=… length_mm=… section=…` | `check_cantilever` |
| "pressurised / contains gas / liquid under pressure" | `// pressure: part=… internal_pa=… wall_thickness_mm=… radius_mm=…` | `check_pressure_vessel` |
| "operates at temperature" | `// operating: temp_c=…` | `check_operating_temperature` (per part) |
| "two parts overlap on purpose" | `// clash_whitelist: a~b` | suppresses `check_hard_clash` |

If the prompt mentions any of these, emit the matching annotation. Don't omit
annotations because the geometry "looks safe" — the whole point of Stage 3 is
that the LLM can't tell from looking.

## Stage 3 — Geometric validation (tools own this)

The orchestrator runs the validators in the prescribed order; you do not call
them by hand. One call:

```python
from orchestrator import run_pipeline

report = run_pipeline(scad_path)   # parses annotations, renders, runs validators
print(report.to_text())            # surface verbatim to the user
```

What the orchestrator does internally (so you understand failure messages):

```
1. parse_annotations(scad_text)  — pull part/fit/clash_whitelist/gravity/bed_z/load metadata.
2. render assembly() and each named part to STL.
3. validators.check_mesh_integrity(assembly.stl)
4. validators.check_hard_clash(parts, whitelist=clash_whitelist)
5. validators.check_clearance(...) per `fit:` annotation
6. validators.check_static_stability(assembly, gravity_axis, bed_z)
7. validators.check_grounded(assembly, gravity_axis, bed_z)
8. validators.check_settles_under_gravity(parts, gravity_axis, bed_z_mm)
9. validators.check_cantilever(...) per `load:` annotation
10. validators.check_buckling(...) per `buckling:` annotation
11. validators.check_pressure_vessel(...) per `pressure:` annotation
12. validators.check_operating_temperature(...) per part if `operating:` is set
13. validators.aggregate(...).to_text()
```

If `check_mesh_integrity` produces BLOCKers, the orchestrator surfaces them
without running later steps (subsequent validators assume a watertight mesh).
You may then invoke `validators.repair_mesh` manually and re-run. If after
3 attempts the STL still blocks, surface to the user and stop.

Validator preconditions:
- `check_clearance`, `check_static_stability` need watertight + winding-consistent
  meshes. Step 1 enforces this.
- `check_hard_clash` is robust to imperfect meshes but its boolean backend
  (`manifold3d`) prefers them too.

### Render-then-verify loop budget: **3 attempts**

If Stage 3 returns BLOCKers:
- Read the structured verdicts.
- Revise the SCAD to address each BLOCKer (use the `suggested_action` field).
- Re-render and re-validate.
- If after 3 attempts you still have BLOCKers, surface the report to the user
  and ask for a design change. Do not paper over by lowering safety thresholds.

WARNs do not stop the pipeline. Surface them; let the user accept or revise.
AUTO_REPAIRED verdicts must be surfaced loudly — repair can silently alter
load-bearing geometry (study 03's MeshLib caveat).

## Stage 4 — Slice (downstream skill owns this)

Hand the validated STL plus material/orientation choice to:
- `pjt222/select-print-material` for material selection if the user hasn't picked.
- `flowful-ai/cad-skill` or `stigsb-devais/cad-skill` for slicer-aware
  manufacturability checks (wall thickness, overhangs, supports, layer height).

You do **not** check overhangs, supports, or layer-line orientation. That is
the manufacturability skill's job.

## Stage 5 — Print transport (orchestrator owns this)

Once `.gcode` exists, the transport layer streams it over USB serial:
- Marlin / Klipper-flavoured G-code.
- Line-numbered with checksum.
- `M105` heartbeat for keepalive.

You do not run the printer. You confirm to the user that the print job has
been queued and surface any error reported by the transport.

## Reporting format

Every line you write to the user that contains a number, a yes/no claim about
geometry, or a pass/fail verdict must be tagged:

| Tag | When to use |
|---|---|
| `[OK]` `[FIX]` `[WARN]` `[BLOCK]` | Came from a deterministic tool. Surface the validator's `to_text` output verbatim. |
| `[INFER]` | Came from your inference. Always include a hedge: "I think", "probably", "based on the description". |

NEVER tag your own inference as `[OK]` or `[BLOCK]`. NEVER strip the validator's
tags when relaying its output. The user's trust in the skill depends on this
boundary being immaculate.

When you cannot decide between `[INFER]` and a deterministic tag, you must call
the tool. If no tool covers the question, say so and tag your answer `[INFER]`.

## Out of scope (v1)

If the user asks for any of these, say explicitly that you do not handle them
and recommend they go to the relevant downstream tool or accept the limitation:

- Distributed loads, multi-load FEA, fatigue, creep, impact (point-load
  cantilever only; buckling assumes a single concentric axial load; the
  pressure-vessel check is hoop stress only with the thin-wall assumption).
- Coupled thermo-mechanical analysis or thermal stress under transient
  heating (`check_operating_temperature` is a static lookup against HDT/Tg).
- Statistical (RSS / Monte Carlo) tolerance stack-ups (FDM distributions
  are not Gaussian).
- Continuous-time / motion-aware collision ("does this part swing into place?").
- Print orientation, supports, overhangs, layer-line strength (downstream
  manufacturability skills).
- Materials beyond PLA / PETG / ABS for structural checks (TPU/Nylon need a
  different model).

## Quick reference

```python
# Orchestrator (call this — it composes everything below)
from orchestrator import run_pipeline
report = run_pipeline(scad_path)

# Validator API (only call directly when you need fine-grained control,
# e.g. running validators.repair_mesh between pipeline iterations)
check_mesh_integrity(stl_path) -> list[Verdict]
repair_mesh(stl_path, *, output_path=None, allow_destructive=True) -> (Path, list[Verdict])

check_hard_clash(parts, *, min_volume_mm3=0.01, whitelist=None) -> list[Verdict]
check_clearance(part_a, part_b, fit_class) -> Verdict
check_static_stability(mesh, *, gravity_axis="-z", bed_z=None, bed_tol_mm=0.1) -> Verdict
check_grounded(mesh, *, gravity_axis="-z", bed_z=None, bed_tol_mm=0.1) -> Verdict
check_settles_under_gravity(parts, *, duration_s=2.0, max_translation_mm=1.0, max_rotation_deg=5.0,
                            bed_z_mm=0.0, gravity_axis="-z", inter_part_collision=False) -> list[Verdict]
check_cantilever(beam_length_mm, cross_section, load_n, *, material="PLA", safety_factor=3.0) -> Verdict
check_buckling(column_length_mm, cross_section, axial_load_n, *, material="PLA",
               end_condition="fixed-free", safety_factor=3.0) -> Verdict
check_pressure_vessel(wall_thickness_mm, internal_radius_mm, internal_pressure_pa, *,
                      material="PLA", safety_factor=3.0) -> Verdict
check_operating_temperature(*, operating_temp_c, material="PLA", part_name=None) -> Verdict

aggregate(*verdict_lists) -> Report
Report.to_text() -> str    # surface verbatim to user
Report.to_dict() -> dict   # for orchestrator state
```
