# Study 01 — BIM clash detection

**Discipline:** Architecture / construction (Building Information Modelling)
**Why we care:** This is the most mature discipline (~20 years) for catching "two volumes occupy the same space" and "this assembly step is impossible" before fabrication. The taxonomy, the rule-based vs. geometry-intersect split, and the false-positive problem all transfer directly.

## Sources distilled

- **Navisworks clash detection — United-BIM** ([article](https://www.united-bim.com/get-to-know-all-about-clash-detection-with-navisworks/))
- **MEP coordination with Revit / Navisworks / Solibri — Vavetek** ([article](https://vavetek.ai/blog/mep-coordination-in-bim-revit-navisworks-solibri/)) — content was thin; only confirmed Solibri "specialises in clash detection and model checking" alongside Navisworks. Treat as a pointer, not a primary source.
- **ML-based clash relevance filtering — ScienceDirect 2025** ([article](https://www.sciencedirect.com/science/article/pii/S0926580525006843)) — paywall blocked direct fetch; topic confirmed via README and abstract metadata.

## Concepts to internalize

### The clash taxonomy (Navisworks)

| Type | Definition | Direct analog in our skill |
|---|---|---|
| **Hard clash** | "Two components of a building intersect or pass through each other" — geometric intersection. | Two solid volumes from one OpenSCAD file overlap. |
| **Soft clash** (clearance) | Distance between elements falls below a tolerance threshold. *No specific values given* — set per project. | Two parts that need to mate but lack the FDM clearance gap (~0.2 mm typical). Insulation-wrap analog. |
| **Workflow / 4D clash** | Temporal: install order, equipment delivery, sequencing conflicts. | "Can this be assembled?" — does the sequence the user described actually allow each part to enter its final position without passing through another? |

### Inputs / outputs of a clash run

- Inputs: federated 3D model (multiple disciplines aggregated into NWF/NWC).
- Process: load primary, append secondary, define **Selection Sets** (static, project-specific) or **Search Sets** (dynamic, reusable rules over metadata), run intersection, tag results as **New / Active / Approved / Resolved**.
- Outputs: clash spheres marking intersection volumes, exportable reports (HTML / PDF / XML), saved viewpoints.

### Where the false positives come from

The single most useful piece of operational wisdom in the source:

- **Cut openings** are the leading false-positive source — penetrations that *look* like clashes but are intentional.
- **Pipes under 3″** are typically **excluded by BEP** (BIM Execution Plan) agreement, because chasing them creates noise without value.
- **Parallel / "half-embedded" elements** at the wrong level produce non-penetrating adjacency errors that are flagged but harmless.
- **Geometry alterations** during model export (e.g. Revit → Navisworks) silently change shapes and produce phantom clashes.

The signal: raw geometric intersection is necessary but not sufficient. You need a *whitelist* of intentional intersections and a *size threshold* below which you suppress noise. This is why the field is now layering ML "clash relevance" classifiers on top of raw boolean intersection.

### Solibri's rule-based model (vs. Navisworks's geometry-intersect)

Navisworks asks "do these meshes overlap?" Solibri asks "does this model satisfy a *named rule* defined over geometry **and metadata**?" — e.g. "every door must have at least 800 mm clear width; no structural element may pass through an MEP shaft."

The Solibri model is a much better fit for an LLM-driven checklist: rules are linguistic, named, and operate over metadata an LLM can describe — not just over raw triangles.

## What to borrow

1. **Adopt the hard / soft / workflow taxonomy verbatim** as the top-level structure of the SKILL.md checklist. It is well-tested, easy to explain to users, and maps cleanly onto the validator/tool boundary:
   - Hard → tool (boolean intersection).
   - Soft → tool (boolean with offset).
   - Workflow → LLM (verbal walkthrough).
2. **Plan for false positives from day one.** A naive "are these two volumes overlapping?" check will fire on intentional features (the screw inserted into the boss; the dovetail joint). The skill needs:
   - A *whitelist* concept ("these two parts are *meant* to interpenetrate at this feature") expressed in the OpenSCAD intent metadata.
   - A *minimum-volume* threshold (e.g. ignore intersections under N mm³) to suppress numerical-precision artefacts.
3. **Name rules, don't just run booleans.** A rule like "stability: COM must project inside the support polygon" is far easier for a user to understand and override than a raw geometric error. Solibri's rule-naming pattern is the model.
4. **Tag and persist results.** New / Active / Approved / Resolved is overkill for a one-shot run, but having an explicit "user has approved this clash as intentional" status lets the skill iterate without re-flagging the same dovetail twice.

## Concrete implications for our code

- `validators/clash.py` should produce a structured result: `{rule_name, severity, intersecting_volumes[], suggested_action, is_whitelisted}` — not a boolean. The taxonomy goes in `severity` or `category`.
- `SKILL.md`'s checklist categories should mirror **Hard clash**, **Clearance / fit**, **Assembly / workflow**, with the hard and clearance ones explicitly noted as "tool-owned — don't try to compute these in chat."
- The OpenSCAD intent metadata (proposed) should carry a `clearance_mm` field per mating-pair so the soft-clash check knows what gap to expect, not a global default.
- **Defer ML "clash relevance"** until we have a corpus. It would be premature.

## Gaps these sources don't fill

- No numeric tolerance values for clearance. We will need to source these from an FDM-printing reference (typical FDM hole-shaft clearance is 0.2–0.4 mm; not from the BIM literature).
- No discussion of how clash detection composes with parametric regeneration — when the user revises the design, do we re-run all rules or only ones touching changed geometry? (Answer is probably "all" for v1; document explicitly.)
