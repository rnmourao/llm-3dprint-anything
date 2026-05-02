# Study 04 — LLM physical reasoning limits

**Discipline:** ML evaluation / benchmarks (2025–2026)
**Why we care:** This is the load-bearing argument for the **hybrid skill, not pure prompt** design. If the LLM could reason reliably about geometry and physics, we wouldn't need validators — we'd write a clever prompt. The benchmarks below say it can't, and quantify how badly. They draw the LLM-vs-tool boundary for us.

## Sources distilled

- **GeoGramBench** ([OpenReview](https://openreview.net/forum?id=8wEQLCSfCT))
- **PHYBench** ([arXiv abstract](https://arxiv.org/abs/2504.16074))
- **FEM-Bench** ([arXiv abstract](https://arxiv.org/abs/2512.20732))
- **EquiLLM** — referenced in README rationale; not separately fetched. Notable for *bolting E(3)-equivariant encoders onto LLMs precisely because raw LLMs are weak at 3D* — i.e. the field's research-side response to this same problem.

## Concepts to internalize

### GeoGramBench — "program-to-geometry" reasoning

- **Task:** translate procedural drawing code (programs that produce geometry) into "accurate and abstract geometric reasoning" — i.e. given the code, what does the shape *look like* and what are its spatial properties?
- **Scale:** 500 problems, **three abstraction levels** organised by *geometric* complexity (not mathematical-reasoning complexity).
- **Result:** 17 frontier LLMs evaluated. **"Even the most advanced models achieve less than 50% accuracy at the highest abstraction level."**
- **Implication:** the inverse problem (write OpenSCAD that produces a target geometry) is at least as hard. The LLM is *unreliable* at the very task we're asking it to do in stage 2 of our pipeline. Therefore stage 3 (geometric validation) is not optional — it's the safety net for a known-fragile stage.

### PHYBench — physics symbolic derivation

- **Task:** 500 original physics problems, "high school to Physics Olympiad difficulty." Tests multi-step, multi-condition reasoning about physical systems.
- **Result:** **Best model (Gemini 2.5 Pro): 36.9%. Human experts: 61.9%.** Gap of 25 percentage points to expert humans, and the best model fails ~63% of problems.
- **Failure-mode detail:** the abstract introduces an "Expression Edit Distance (EED) Score" but doesn't enumerate failure categories. The signal is the headline gap, not a taxonomy.
- **Implication:** any numerical physical claim ("this beam will support 5 kg," "this part won't tip over") that comes from the LLM has a >60% probability of being wrong on Olympiad-grade problems. Real-world FDM strength estimation is *less* well-trained, not more. Numbers must come from a formula or a solver.

### FEM-Bench — finite-element-method coding

- **Task:** "introductory but nontrivial" tasks from a first graduate course on computational mechanics. Tests building physical-system models in code; reasoning about geometry, spatial relationships, and material behavior.
- **Headline numbers:**
  - Gemini 3 Pro (function writing): **30/33 tasks completed at least once; 26/33 all five times.**
  - GPT-4o (unit-test writing): **73.8% Average Joint Success Rate.**
- **The interesting nuance:** these are *introductory* tasks and "state-of-the-art LLMs do not reliably solve all of them." The gap is in enforcing "strict physical and numerical constraints" — exactly the thing we need for stability and structural checks.
- **Implication:** asking an LLM to *generate FEA setup code* is plausible (~80% on intro tasks). Asking it to *simulate the FEA in its head and tell you the answer* is not. If we ever do structural validation, the right move is LLM writes the FEA input deck, traditional solver runs it.

### EquiLLM (referenced, not fetched in detail)

The mere existence of this research line is a data point. When a frontier-research effort spends compute on "bolting equivariant encoders onto LLMs" specifically to handle 3D, it's because the unaugmented architecture doesn't get there. We're not doing that augmentation; we're doing the cheap-but-correct alternative — call deterministic geometry tools.

## What to borrow

1. **The triage-nurse, not doctor framing is empirically supported.** The benchmarks justify the LLM-as-checklist-runner / tool-as-kernel split that the README already commits to. Studies 01–03 each found a tool the LLM should call. This study found the *reason* — the LLM is benchmark-confirmed unreliable at every category of geometric / physical computation we care about.
2. **A red-line list belongs in SKILL.md.** Make explicit, in the prompt, the things the LLM must not attempt and instead delegate:
   - Compute volume of any geometry in mm³.
   - Compute centre of mass.
   - Decide whether two volumes intersect (yes/no, even visually).
   - Estimate stress, deflection, factor of safety.
   - Predict whether a print will warp.
   - Confirm a mesh is manifold/watertight.
   Each of these has a tool. The prompt should *route to the tool*, not produce the answer.
3. **What the LLM is good at — and we should keep using it for:**
   - Asking clarifying questions in natural language ("you said cup — does it have a closed bottom?").
   - Pattern-matching descriptions to known categories ("this is a cantilever load case").
   - Walking a verbal assembly sequence and noticing impossible steps.
   - Naming and explaining results from tools to the user.
   - Generating *first-draft* OpenSCAD that a downstream geometry validator can check (GeoGramBench says it'll be wrong sometimes — that's why stage 3 exists).
4. **Benchmark scores should anchor expectations in user-facing copy.** When the skill produces a stability assessment, it should distinguish "verified by tool" from "LLM judgement". The user (and any future contributor) should never be confused about which is which.

## Concrete implications for our code

- `SKILL.md` should include an explicit **Routing rules** section, with a table mapping check-type → owner (LLM | tool | LLM-then-tool). This is the operationalisation of the README's existing Owner table — but stricter. The benchmark evidence is the justification.
- Every tool-call result that returns to the conversation should be tagged as *deterministic* in the assistant's report ("✓ Mesh is watertight (Trimesh)"). LLM-only conclusions should be explicitly hedged ("I think the assembly order works, but this hasn't been mechanically verified").
- The OpenSCAD-generation step (stage 2) should be wrapped in a **render-then-verify** loop: LLM emits SCAD → render to STL → run `validators/mesh.py` and `validators/clash.py` → if violations, LLM gets the structured error and revises. **Do not** ship a path where SCAD goes directly to slicer without geometric validation. GeoGramBench's <50% accuracy tells us why.
- For any future structural check: LLM writes the FEA input deck, tool runs it, LLM interprets the numerical output. Don't ask the LLM to predict the result.

## Gaps these sources don't fill

- The benchmarks don't tell us the **failure shape** — whether errors are systematic (always overestimating volume) or random. That would change mitigation strategy. (Random errors → retry with different prompt. Systematic errors → calibration offset.) Worth a literature follow-up.
- They don't cover **vision-augmented** evaluation — would a multimodal model that sees an STL render reason better than one with text only? Plausibly yes, and the skill could exploit this in stage 3 (show the LLM a multi-view render of the candidate STL).
- No data on **agentic / tool-augmented** scores. The benchmarks test the bare model. With deterministic tools available, the effective accuracy is the tools' accuracy — which is the entire architectural premise. We should measure this ourselves once the skill exists (eventual evaluation harness: prompt → final printed object → human grade).
