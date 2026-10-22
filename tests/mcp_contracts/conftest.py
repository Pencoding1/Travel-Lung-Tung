"""Import-path bootstrap for the OC-007 isolated MCP contract tests.

Mirrors ``tests/spatial/conftest.py``: only the POI service source roots are
added to ``sys.path`` so ``app.*`` can be imported without installing the
service packages. No database connector, settings reader, Firebase credential or
network call is triggered by importing the modules under test; the concrete
UnitOfWork/connector is only imported lazily when a test does not inject a fake
factory.
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
