"""Import-path bootstrap for the OC-044 runtime spatial tests.

Only the POI service source roots are added to ``sys.path``. The live tests
connect to the explicitly configured owned native Memgraph instance; the pure
tests never touch a database or the network.
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
