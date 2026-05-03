"""Package the deployable skill bundle into dist/skill.tar.gz.

The bundle contains everything under skill/ — SKILL.md, the four
runtime modules (validators, orchestrator, slicer, transport),
examples, and skill/requirements.txt — and nothing else. Tests,
studies, scripts, scratch outputs, and dev configuration are
intentionally excluded.

Run from the repo root:

    .venv/bin/python scripts/build_skill.py

Output: dist/skill.tar.gz (with a top-level skill/ directory inside,
so unpackers see `skill/SKILL.md` etc., matching the source layout).

The output also gets a manifest line printed to stdout so CI can
verify the bundle contents without unpacking.
"""

from __future__ import annotations

import sys
import tarfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / "skill"
DIST_DIR = REPO_ROOT / "dist"
OUTPUT = DIST_DIR / "skill.tar.gz"

# Anything matching one of these path components is excluded from the bundle.
EXCLUDED_NAMES = {"__pycache__", ".pytest_cache", ".DS_Store"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def _should_include(path: Path) -> bool:
    if path.name in EXCLUDED_NAMES:
        return False
    if path.suffix in EXCLUDED_SUFFIXES:
        return False
    return True


def _walk_skill() -> list[Path]:
    """Return every file under skill/ that should ship, sorted for determinism."""
    files: list[Path] = []
    for p in sorted(SKILL_DIR.rglob("*")):
        if not p.is_file():
            continue
        if any(part in EXCLUDED_NAMES for part in p.relative_to(SKILL_DIR).parts):
            continue
        if not _should_include(p):
            continue
        files.append(p)
    return files


def main() -> int:
    if not SKILL_DIR.is_dir():
        print(f"error: skill/ directory not found at {SKILL_DIR}", file=sys.stderr)
        return 1

    files = _walk_skill()
    if not files:
        print("error: skill/ contained no shippable files", file=sys.stderr)
        return 1

    DIST_DIR.mkdir(exist_ok=True)
    with tarfile.open(OUTPUT, "w:gz") as tar:
        for f in files:
            arcname = f.relative_to(REPO_ROOT)  # keeps the leading skill/ prefix
            tar.add(f, arcname=str(arcname))

    size_kb = OUTPUT.stat().st_size / 1024
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)} ({len(files)} files, {size_kb:.1f} KB)")
    for f in files:
        print(f"  {f.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
