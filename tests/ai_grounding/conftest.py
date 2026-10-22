"""Import-path bootstrap for the OC-005 grounded-itinerary contract tests.

Only the ``ai_service`` source root is added to ``sys.path`` so ``main`` and
``domains`` import without installing the service package. Collaborator fakes
live in ``helpers_ai_grounding.py`` to avoid conftest module-name collisions.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = REPO_ROOT / "ai_service"
if str(AI_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_ROOT))
