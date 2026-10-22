"""Import-path bootstrap for the OC-038 provenance tests.

Only the POI service / shared source roots are added. No database connector is
started, no credentials are read and no graph/network call is made. Repository
tests use a recording transaction unless they explicitly skip.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOTS = (
    REPO_ROOT / "POI_service",
    REPO_ROOT / "shared_lib",
    Path(__file__).resolve().parent,
)

for root in SERVICE_ROOTS:
    if root.is_dir() and str(root) not in sys.path:
        sys.path.insert(0, str(root))
