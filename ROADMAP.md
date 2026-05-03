# Roadmap

Single source of truth for project status. The `Roadmap` sections in [README.md](README.md) and [skill/README.md](skill/README.md) carry an inline copy of the checklist; this file keeps the canonical list plus context — what was learned, what's left, and why.

## Done

- [x] **`SKILL.md`** — interview prompts, checklist categories, decision rules, OpenSCAD intent-annotation grammar, and worked examples covering the most common annotation combinations.
- [x] **`validators/`** — twelve deterministic checks (mesh integrity, clash, fit, static stability, grounded, gravity-settle, cantilever, buckling, pressure-vessel hoop stress, operating temperature) plus aggregated `Report` output.
- [x] **`orchestrator/`** — SCAD intent-annotation parser + render-then-validate pipeline driving the validator sequence.
- [x] **`slicer/`** — PrusaSlicer CLI invocation with per-material profiles (PLA, PETG, ABS) and explicit first-layer temperature fields.
- [x] **`transport/`** — Marlin/Klipper line-numbered streamer over USB serial (pyserial-backed), with `M109`/`M190`/`M191` getting a separate `long_block_timeout_s` so they don't time out waiting for cold heaters.
- [x] **End-to-end smoke test against real OpenSCAD** — validators pass on every example design.
- [x] **End-to-end smoke test against real PrusaSlicer** (2026-05-03) — sliced the canonical peg-in-hole assembly with the default PLA profile; surfaced and fixed the missing first-layer-bed-temperature CLI flag.
- [x] **First print on a real Marlin/Klipper printer over USB** (2026-05-03) — Ender-3 S1 Pro running Marlin 2.0.8.28F4, 14,543 G-code lines streamed in 25 m 7 s with zero resends. Surfaced and fixed the streamer's M109/M190 ack-timeout gap. The printed parts mated as predicted by the LC fit annotation (pliers required to separate — at the upper-tightness edge of the LC range, exactly as the validator's verdict said).

## Pending

- [ ] **M105 keepalive thread in the streamer.** Today, long heat-up commands rely on `long_block_timeout_s` (default 600 s). A real heartbeat thread would let the host detect a stalled or unresponsive printer mid-print rather than waiting out the full timeout.
- [ ] **Per-part STL slicing.** The orchestrator currently unions all parts into one `assembly.stl` before slicing, so co-printed mating parts can fuse if their gap is below the slicer's extrusion-width threshold. Pairs naturally with per-part validation: each separated part should be tested for gravity stability AND support-economy in its standalone print orientation (see [memory note](.claude/projects/-Users-rnmourao-github-com-rnmourao-llm-3dprint-anything/memory/multi_part_slicing_intent.md)).
- [ ] **Calibration-print routine for FDM clearance values.** The fit table in [skill/validators/fit.py](skill/validators/fit.py) is FDM-tuned but generic. A per-printer calibration object (a strip of varying-clearance peg-in-hole pairs) would let users dial in their machine's actual gap behavior.
- [ ] **Vision-augmented stage-3 secondary check.** Render the assembly from multiple angles, hand the images back to the LLM, and have it spot anything the deterministic validators missed (hidden floating components, mis-modeled features, unintuitive failure modes). A safety net for gaps in the rule set.

## Out of scope (v1)

These are intentional non-goals — extending them belongs in a sibling module per [study 02](studies/02-tolerance-and-fits.md)'s fit-vs-hold split, not by overloading existing checks:

- Statistical (RSS / Monte Carlo) tolerance stack-ups — FDM tolerance distributions aren't Gaussian.
- Real FEA — `check_cantilever`/`check_buckling`/`check_pressure_vessel` are closed-form back-of-envelope. A `validators/fea.py` would be the right place.
- Transient thermal stress, creep over time, coupled thermo-mechanical analysis — `check_operating_temperature` is a static lookup against HDT and Tg only.
- Part-on-part support detection — `check_grounded` flags components that don't touch the bed; doesn't yet detect a screw resting on a flange. Workaround: model interlocking parts as a single watertight mesh.
