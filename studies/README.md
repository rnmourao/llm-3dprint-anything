# Studies

Background research that turns the README's design rationale into concrete inputs for the implementation. Each study distils a discipline cited in the project [README](../README.md) and ends with **what to borrow** + **concrete implications for code / SKILL.md**.

| # | Study | Discipline | Feeds into |
|---|---|---|---|
| 01 | [BIM clash detection](01-bim-clash-detection.md) | Architecture / construction | `validators/clash.py`, SKILL.md hard/soft/workflow taxonomy |
| 02 | [Tolerance analysis & engineering fits](02-tolerance-and-fits.md) | Mechanical design | `validators/fit.py`, mating-feature interview script |
| 03 | [Mesh integrity & collision detection](03-mesh-integrity-and-collision.md) | Computer graphics / games | `validators/mesh.py`, broad/narrow-phase pattern in `clash.py` |
| 04 | [LLM physical-reasoning limits](04-llm-physical-reasoning-limits.md) | ML evaluation (2025–2026) | SKILL.md routing rules, deterministic-vs-judgement reporting |
| 05 | [Synthesis & SKILL.md spec](05-synthesis-and-skill-spec.md) | (cross-cutting) | Routing table, `validators/` module shape, SKILL.md skeleton |

## How to read

If you have time for one document, read [05](05-synthesis-and-skill-spec.md) — it carries the conclusions of the others into a routing table, validator API sketches, and a SKILL.md skeleton.

If you're about to implement one of the validators, read its source-discipline study first (01 for clash, 02 for fit, 03 for mesh) — the rationale lives there, not in the synthesis.

## Source-fetch status

Of the 11 URLs cited in the README, 9 fetched cleanly. Two were unavailable: the **Vavetek** post returned promotional content with no technical detail, and the **ScienceDirect** ML-clash-relevance paper and the **Autodesk Inventor** post both returned 403. Where those gaps matter, the affected studies say so explicitly.
