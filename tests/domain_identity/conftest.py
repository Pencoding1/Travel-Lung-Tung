"""Import-path bootstrap for the OC-002 focused domain tests.

Mirrors ``tests/audit/conftest.py``: only the POI service source roots are added
to ``sys.path`` so ``app.core.domain.graph_entities`` can be imported without
touching application source or installing the service packages.
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
