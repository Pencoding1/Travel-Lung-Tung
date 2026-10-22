"""Test bootstrap for the OC-001 isolated audit.

Adds the POI service source root to sys.path so the domain modules can be
imported as ``app.core...`` without touching application source or installing
the service packages. Only import-path setup happens here; no runtime state,
no database connectors, no external calls.
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
