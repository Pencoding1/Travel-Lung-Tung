"""Import-path bootstrap for the OC-043 snapshot adapter tests.

Only the POI service and shared source roots are added. The adapter is offline:
no database connector, credential, model, graph or network call is started.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOTS = (
    REPO_ROOT / "POI_service",
    REPO_ROOT / "shared_lib",
    Path(__file__).resolve().parent,
)

for root in SERVICE_ROOTS:
    if root.is_dir() and str(root) not in sys.path:
        sys.path.insert(0, str(root))


@pytest.fixture(scope="session")
def real_plan():
    from app.core.utils.primary_snapshot import REAL_EXPECTATIONS, REPO_ROOT as adapter_root, prepare_snapshot

    return prepare_snapshot(adapter_root, REAL_EXPECTATIONS)
