"""Bootstrap for the OC-004 ingestion tests.

Responsibilities:
- add the POI service / shared source roots to ``sys.path`` (no installed packages);
- supply a synthetic ``JWT_SECRET`` for auth-aware HTTP tests;
- neutralise ``dotenv.load_dotenv`` so importing the app never reads a real
  ``.env`` file (the brief forbids reading credentials).

Only import-path and environment setup happens here; no database connector,
external call or credential is used.
"""

import os
import sys
from pathlib import Path

# Synthetic, non-secret auth material for the isolated runtime.
os.environ["JWT_SECRET"] = "oc004-isolated-test-secret-0123456789abcdef"
os.environ["JWT_ALGORITHM"] = "HS256"

# Prevent ``app.core.security.auth`` (which calls load_dotenv() at import) from
# reading the repository's real .env file. This is a no-op patch of a function,
# not a fake sys.modules entry.
try:  # pragma: no cover - defensive, dotenv is a declared test dependency
    import dotenv

    dotenv.load_dotenv = lambda *args, **kwargs: False
except Exception:  # pragma: no cover
    pass

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOTS = (
    REPO_ROOT / "POI_service",
    REPO_ROOT / "shared_lib",
    REPO_ROOT / "tests" / "ingestion",
)

for root in SERVICE_ROOTS:
    if root.is_dir() and str(root) not in sys.path:
        sys.path.insert(0, str(root))
