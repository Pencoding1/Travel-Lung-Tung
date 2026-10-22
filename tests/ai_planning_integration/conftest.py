"""Import-path bootstrap for the OC-016 planner-integration contract tests.

Adds the ``ai_service`` source root and the existing ``tests/ai_grounding``
helper directory to ``sys.path`` so the real ``main``/``domains`` modules and
the established MCP/Gemini fakes are reused without installing anything. No
network, live model, MCP, graph or database call is made anywhere here.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (REPO_ROOT / "ai_service", REPO_ROOT / "tests" / "ai_grounding"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
