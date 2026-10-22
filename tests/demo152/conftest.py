"""Import bootstrap for the focused DEMO-152 checks."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SERVICE_ROOTS = (
    REPO_ROOT / "POI_service",
    REPO_ROOT / "shared_lib",
    REPO_ROOT / "ai_service",
    REPO_ROOT / "tests" / "source_snapshot_scope",
)

for root in SERVICE_ROOTS:
    if root.is_dir() and str(root) not in sys.path:
        sys.path.insert(0, str(root))
