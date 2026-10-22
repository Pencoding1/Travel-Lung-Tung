"""Bootstrap for the OC-011 isolated startup/connector-lifecycle tests.

Responsibilities:
- add the POI service / shared source roots to ``sys.path`` (no installed
  packages) and this test package for its fakes;
- provide a fully synthetic environment (JWT + Memgraph) so the connector and
  auth modules can be imported without touching real configuration;
- neutralise ``dotenv.load_dotenv`` so importing the app never reads a real
  ``.env`` file (the brief forbids reading credentials);
- ensure ``FIRESTORE_ENABLED`` is absent so graph-only is the default.

Only import-path and environment setup happens here; no database connector,
Firebase import, external call or credential is used.
"""

import os
import sys
from pathlib import Path

os.environ["JWT_SECRET"] = "oc011-isolated-test-secret-0123456789abcdef"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["MEMGRAPH_HOST"] = "localhost"
os.environ["MEMGRAPH_PORT"] = "7687"
os.environ["MEMGRAPH_USER"] = "isolated"
os.environ["MEMGRAPH_PASSWORD"] = "isolated"
os.environ.pop("FIRESTORE_ENABLED", None)

# No-op patch of ``dotenv.load_dotenv`` (not a fake sys.modules entry) so the
# auth module's import-time call cannot read the repository's real .env.
try:  # pragma: no cover - defensive, dotenv is a declared dependency
    import dotenv

    dotenv.load_dotenv = lambda *args, **kwargs: False
except Exception:  # pragma: no cover
    pass

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOTS = (
    REPO_ROOT / "POI_service",
    REPO_ROOT / "shared_lib",
    REPO_ROOT / "tests" / "startup",
)

for root in SERVICE_ROOTS:
    if root.is_dir() and str(root) not in sys.path:
        sys.path.insert(0, str(root))
