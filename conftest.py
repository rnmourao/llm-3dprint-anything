import sys
from pathlib import Path

# Skill source root is skill/; tests import its modules without a `skill.` prefix
# so the package layout stays simple and matches what consumers see at runtime.
sys.path.insert(0, str(Path(__file__).parent / "skill"))
