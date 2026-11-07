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

for root in reversed(SERVICE_ROOTS):
    if root.is_dir():
        root_str = str(root)
        if root_str in sys.path:
            sys.path.remove(root_str)
        sys.path.insert(0, root_str)

_poi_app_root = str((REPO_ROOT / "POI_service" / "app").resolve())
_loaded_app = sys.modules.get("app")
if _loaded_app is not None and not str(getattr(_loaded_app, "__file__", "")).startswith(_poi_app_root):
    for _mod_name in [k for k in list(sys.modules) if k == "app" or k.startswith("app.")]:
        sys.modules.pop(_mod_name, None)
