"""Import-path bootstrap for the OC-014 graph-lifecycle tests.

Mirrors ``tests/spatial/conftest.py`` and ``tests/mcp_contracts/conftest.py``:
only the POI service source roots are added to ``sys.path``. No database
connector is started, no credentials are read and no graph/network call is made
anywhere in this package. Every transaction here is a fake; the real Cypher is
captured and inspected, never executed.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOTS = (
    REPO_ROOT / "POI_service",
    REPO_ROOT / "shared_lib",
)

for root in SERVICE_ROOTS:
    if root.is_dir() and str(root) not in sys.path:
        sys.path.insert(0, str(root))
