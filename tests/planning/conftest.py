"""Import-path bootstrap for the OC-010 planning tests.

Only the ``ai_service`` source root is added to ``sys.path`` so the stdlib-only
``domains.planning`` package imports without installing the service. No
provider, database, graph or network module is imported anywhere in this suite.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = REPO_ROOT / "ai_service"
if str(AI_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_ROOT))
