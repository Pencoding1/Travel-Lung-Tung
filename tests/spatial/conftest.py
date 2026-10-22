"""Import-path bootstrap for the OC-003 isolated spatial tests.

Mirrors ``tests/audit/conftest.py`` and ``tests/domain_identity/conftest.py``:
only the POI service source roots are added to ``sys.path`` so
``app.core.utils.spatial`` can be imported without touching application source
or installing the service packages. No database connector is imported and no
graph/network call is made anywhere in this package.
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
