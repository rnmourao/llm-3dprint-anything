# Study 02 — Tolerance analysis and engineering fits

**Discipline:** Industrial / mechanical design
**Why we care:** Two distinct lessons. (1) **"Will it fit?" and "will it hold?" are different checks** with different tools — interference checking (boolean geometry) vs. structural analysis (FEA). The skill must keep these stages separate. (2) Mating parts have a long-established **fit taxonomy** (RC / LC / LT / LN / FN) that gives us off-the-shelf vocabulary for the LLM to use when interviewing the user, instead of inventing one.

## Sources distilled

- **Tolerance analysis — Wikipedia** ([article](https://en.wikipedia.org/wiki/Tolerance_analysis))
- **Tolerance analysis in Autodesk Inventor — Autodesk blog** ([article](https://www.autodesk.com/blogs/design-and-manufacturing/tolerance-analysis-autodesk-inventor/)) — fetch blocked (403); content largely overlaps Wikipedia.
- **Types of engineering fits — Alibre** ([article](https://www.alibre.com/blog/types-of-engineering-fits-clearance-interference-transition-explained/))

## Concepts to internalize

### The two stack-up methods

| Method | What it does | When to use |
|---|---|---|
| **Worst-case (arithmetic)** | Place every variable at its tolerance limit to maximise/minimise the assembly measurement. Guarantees 100% assembly success but forces tighter (more expensive) component tolerances. | Safety-critical / one-off. Conservative. |
| **Statistical (RSS / Monte Carlo)** | Treat each component variation as a distribution (often Gaussian); sum distributions to predict the assembly distribution. Allows looser tolerances at acceptable defect rates. | High-volume manufacturing where ppm defect rates are tolerable. |

Wikipedia notes the analysis takes **specified dimensions and tolerances**, **expected statistical distributions**, and **geometric multipliers** as inputs. It catches: out-of-spec parts that pass individual inspection, temperature/pressure-induced drift, wear, deflection, and **stack sensitivity** (consequences when conditions deviate from nominal). The article references **1D, 2D, and 3D** stack-ups and notes "modeling rules for vector loops will vary depending on" dimensionality but doesn't enumerate the differences.

### The fit taxonomy (Alibre)

Five named families (ANSI / ASME B4.1 conventions):

| Class | Name | Definition | Example use |
|---|---|---|---|
| **RC** | Running Clearance | Controlled clearance for free rotation, minimised wobble. | Bearings, guide rails, rotating shafts. |
| **LC** | Locational Clearance | Easy assembly, no tight motion. | Dowel pins, mounting brackets. |
| **LT** | Locational Transition | Borderline — may have slight clearance or slight interference. | Press-in alignment dowels. |
| **LN** | Locational Interference | Slight interference for precise positioning. | Gears on shafts, aerospace press fits. |
| **FN** | Force / Shrink Fit | Shaft larger than hole; press-fit or thermal assembly. Permanent. | Flywheels, railroad wheels. |

The Alibre article acknowledges numeric values come from the **ANSI B4.1 / AmesWeb fits calculator** — it does not reproduce them. We will need a small lookup table.

### What this discipline explicitly does *not* cover

The Wikipedia article is clear: **stress and structural viability is a separate tool (FEA)**, not part of tolerance / interference checking. This is the most important architectural takeaway from the entire discipline — bigger than any single rule.

## What to borrow

1. **The fit taxonomy is the LLM's vocabulary for clearance.** When the skill interviews the user about a mating feature, it should ask in these terms — "is this an RC fit (rotates), an LC fit (just slides in), or an FN fit (press-fit, permanent)?" — instead of asking the user to invent a clearance gap. That maps a free-form ask onto a small decision tree.
2. **"Fit" and "hold" are separate stages.** The skill must not bundle them. Stage 3 (geometric validation) checks fit. Stage 3.5 (structural — currently a "punt or beam-equation back-of-envelope" item) checks hold. Conflating them produces the same failure mode the mechanical-design discipline already learned to avoid.
3. **For FDM, only worst-case stack-ups make sense in v1.** FDM tolerance distributions are not Gaussian and are dominated by anisotropic warp, layer-line stairstepping, and elephant's-foot — all systematic, not statistical. Pretending we can do RSS / Monte Carlo on FDM parts would be theatre.
4. **Stack-up sensitivity matters for assemblies.** Even with worst-case-only, the analysis should still flag *which* dimension is the dominant contributor to stack — that tells the user where to tighten the model. This corresponds to the "geometric multipliers" Wikipedia mentions.

## Concrete implications for our code

- `validators/fit.py`:
  - Function `check_clearance(part_a, part_b, fit_class) -> FitResult` where `fit_class ∈ {"RC","LC","LT","LN","FN"}` — uses a hard-coded FDM-adjusted lookup of nominal gap per class, then runs a boolean intersection with that offset.
  - Suggested initial values (FDM, PLA, 0.4 mm nozzle):
    - `RC`: 0.30–0.50 mm radial
    - `LC`: 0.20–0.30 mm
    - `LT`: 0.10–0.20 mm
    - `LN`: −0.05 to 0.05 mm (transition)
    - `FN`: −0.10 to −0.20 mm (interference)
  - These supersede ANSI B4.1 because metric / FDM, not imperial / machined.
- `SKILL.md`'s mating-feature interview should walk the user through the fit-class decision tree before generating geometry. Don't ask "what's the gap" until *after* you have a class.
- Defer Monte Carlo / RSS entirely from v1. Document this as an explicit non-goal in `validators/fit.py` to prevent drift.
- **Structural ("hold") goes in a sibling module**, not `fit.py`. Even a stub `validators/structural.py` with a single `check_cantilever(beam_length, cross_section, material) -> Verdict` function makes the boundary visible.

## Gaps these sources don't fill

- No FDM-specific clearance numbers. Standard practice values (0.2 mm minimum hole-shaft clearance for PLA, 0.4 mm for ABS due to shrinkage) come from FDM operator lore, not the cited mechanical-design literature. Sources to add later: Prusa knowledge base, hubs.com 3D-printing handbook.
- No discussion of orientation-dependent tolerance — FDM hole tolerances differ on the print bed vs. on a vertical face. The skill will need to ask about print orientation in stage 2 (slicer profile).
- No discussion of post-print fitting (sanding, reaming) which is sometimes the right answer. The skill should be allowed to recommend "leave 0.1 mm interference and ream after print."
