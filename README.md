# llm-3dprint-anything

Development repo for the **3d-print-anything** Claude skill — an upstream pre-CAD viability gate that interviews the user, drafts annotated OpenSCAD, runs deterministic geometric/physics/thermal validators, and hands off to slice + USB-serial print transport.

The deployable skill bundle lives under [skill/](skill/). Everything else here is dev-only (tests, background research, scripts, in-progress run outputs).

## For skill consumers

See [skill/README.md](skill/README.md) and [skill/SKILL.md](skill/SKILL.md).

## For contributors

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt   # runtime + pytest
.venv/bin/pytest tests/                         # full suite
```

Read [CLAUDE.md](CLAUDE.md) for the architectural principles (LLM-as-rule-book-reader, every-binary-pluggable) and the directory layout. Read [studies/](studies/) for the discipline research justifying the LLM-vs-tool split.
