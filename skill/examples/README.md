# examples/

Canonical SCAD designs that exercise the validator pipeline. Each file
declares its expected failure mode in a header comment; running it through
`orchestrator.run_pipeline` produces the verdicts listed below. These
double as a regression suite — if a validator's behaviour drifts, the
verdict shape on one of these examples will change first.

```bash
.venv/bin/python -c "
from pathlib import Path
from orchestrator import run_pipeline
report = run_pipeline(Path('examples/<name>.scad'),
                     work_dir=Path(f'scratch/{name}'))
print(report.to_text())
"
```

## The corpus

| File | Status | Demonstrates |
|---|---|---|
| [peg_in_hole.scad](peg_in_hole.scad) | **PASS** (9/9) | Canonical positive case: LC clearance fit, multi-part assembly, all rules green |
| [wall_mount_bracket.scad](wall_mount_bracket.scad) | **BLOCK** (1B / 2W / 4P) | `cantilever_stress` BLOCK + `stability_com_over_support` WARN + `physics_settles` WARN |
| [lamp_stand.scad](lamp_stand.scad) | **WARN** (2W / 4P) | `stability_com_over_support` WARN + `physics_settles` WARN (top-heavy, asymmetric) |
| [slender_antenna_post.scad](slender_antenna_post.scad) | **BLOCK** (1B / 6P) | `column_buckling` BLOCK — geometry that passes a yield-stress check but fails the Euler buckling check |
| [pressure_bottle.scad](pressure_bottle.scad) | **BLOCK** (1B / 1W / 6P) | `operating_temperature` BLOCK + `pressure_vessel_hoop` WARN (hot pressurised PLA) |
| [press_fit_insert.scad](press_fit_insert.scad) | **PASS** (9/9) | FN interference fit within spec + `clash_whitelist` annotation suppressing what would otherwise be a hard-clash BLOCK |

Verdict counts captured 2026-05-02 against MuJoCo 3.8.0, Trimesh 4.x,
manifold3d 2.5+, and OpenSCAD 2021.01.

## What each example exercises

### peg_in_hole.scad

A vertical peg passes up through a flat plate's hole with a 0.25 mm
radial clearance fit (LC class). Both parts are grounded.

- ✓ `clearance:peg~socket` — actual gap measured at **0.250 mm**, in spec
  (0.200 to 0.300 mm). The validator measures the clearance from
  rendered geometry, not from the SCAD constants.
- ✓ `hard_clash:peg~socket` — boolean intersection 0 mm³ (the peg fits
  inside the socket's hole; no material overlap).
- ✓ All mesh integrity rules.
- ✓ `stability_com_over_support`, `stability_grounded`, `physics_settles`
  for both parts.

### wall_mount_bracket.scad

L-shape: vertical mounting plate fixes to a wall (modeled as the bed),
horizontal arm extends forward. A 30 N load at the tip of the arm
generates 168.8 MPa bending stress in the 4×4 mm cross-section — three
times the PLA yield strength.

- ✗ `cantilever_stress:bracket` BLOCK — σ = 168.8 MPa > 50 MPa yield.
- ⚠ `stability_com_over_support` — COM projects to (0, 8.74), outside
  the 30×4 mm base footprint. The arm pulls the COM into the air.
- ⚠ `physics_settles:bracket` — MuJoCo confirms: bracket drifts 7.7 mm
  and rotates 23.3° in 2 s. (Independent corroboration of the
  rule-based stability WARN.)

### lamp_stand.scad

Small base (20×20 mm), tall thin column (4×4×80 mm), heavy head
(30×30×30 mm) offset to one side so the COM hangs outside the base.

- ⚠ `stability_com_over_support` — COM at (13.74, 0), outside base.
- ⚠ `physics_settles:stand` — MuJoCo confirms: 120.7 mm drift and 76.5°
  rotation. The thing falls over.

### slender_antenna_post.scad

A 4 mm diameter, 200 mm tall PLA cylinder under a 50 N axial load. The
compressive yield stress would be only 4 MPa (well within PLA's 50 MPa)
— but Euler buckling kicks in first.

- ✗ `column_buckling:post` BLOCK — P_critical = **2.7 N**, applied = 50 N.
  This is the validator catching a failure mode that `check_cantilever`
  alone would miss.
- ✓ Stability and grounded — perfectly symmetric vertical post.

### pressure_bottle.scad

Thin-walled (1 mm) cylindrical bottle, internal pressure 6 bar (600 kPa),
operating at 70 °C — above PLA's 60 °C glass transition.

- ✗ `operating_temperature:bottle` BLOCK — 70 °C ≥ Tg 60 °C.
- ⚠ `pressure_vessel_hoop:bottle` — σ = 30 MPa hoop stress (below yield
  50 MPa but above the 16.7 MPa safety threshold).
- ✓ `stability_grounded` correctly reports **1 component**, not 2 — the
  inner cavity surface is recognised as a void (negative signed volume)
  rather than a floating part. *This is the reason this example is in
  the corpus: it caught a false-positive in `check_grounded` that the
  unit tests didn't exercise.*

### press_fit_insert.scad

A printed boss (OD 12 mm, ID 5.7 mm) with an interference-fit insert
(OD 6 mm). Radial interference = 0.15 mm, mid-band of the FN spec
(−0.20 to −0.10 mm).

- ✓ `clearance:boss~insert` — FN actual gap **−0.150 mm**, in spec.
- ✓ `hard_clash:boss~insert` — "intersect by design (whitelisted)". The
  `// clash_whitelist:` annotation suppresses what would otherwise be a
  ~16 mm³ BLOCK.
- ✓ Both parts grounded.

## Adding new examples

When adding a design, follow the conventions in
[SKILL.md](../SKILL.md):

1. Each `// part:` module must be defined at its **final assembly position**,
   not at the origin and translated by `assembly()`.
2. Every part should touch the bed plane (z=0) or `check_grounded` will WARN.
   For parts that mate by stacking, `union()` them into a single module.
3. Bottom of the file must call `assembly();` so the file renders standalone.

Then capture the verdict shape with:

```bash
rm -rf scratch/<name> && .venv/bin/python -c "
from pathlib import Path; from orchestrator import run_pipeline
print(run_pipeline(Path('examples/<name>.scad'),
                  work_dir=Path('scratch/<name>')).to_text())
"
```

…and add a row to the table above with the actual counts.
