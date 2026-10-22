"""Import-path bootstrap for the CORE-069 end-to-end flow tests.

Only source roots are added to ``sys.path`` (no install, no package copy):
``ai_service`` for the AI service, and ``POI_service`` + ``shared_lib`` for the
POI service modules exercised by the exception-log and launcher tests.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOTS = (
    REPO_ROOT / "ai_service",
    REPO_ROOT / "POI_service",
    REPO_ROOT / "shared_lib",
)

for root in SERVICE_ROOTS:
    if root.is_dir() and str(root) not in sys.path:
        sys.path.insert(0, str(root))

# DATA-068 precedent: the MCP validation venv intentionally lacks ``tenacity``.
# Append (never prepend) the existing project site-packages so only packages
# missing from the primary venv resolve there; no install or package copy.
FALLBACK_SITE = REPO_ROOT / ".venv" / "Lib" / "site-packages"
if FALLBACK_SITE.is_dir() and str(FALLBACK_SITE) not in sys.path:
    sys.path.append(str(FALLBACK_SITE))


@pytest.fixture(autouse=True)
def reset_intent_router_and_scope_markers():
    """Hermetic Jev state and a clean working-memory scope marker map."""
    import main

    main.configure_intent_router({})
    main._SCOPE_MARKERS.clear()
    yield
