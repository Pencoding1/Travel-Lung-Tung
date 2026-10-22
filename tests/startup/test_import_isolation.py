"""Subprocess proof of import isolation and JWT fail-closed semantics.

These run in a fresh interpreter so ``sys.modules`` and process environment are
genuinely clean. ``dotenv.load_dotenv`` is neutralised before any app import so
no real ``.env`` is ever read.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
POI_SERVICE = REPO_ROOT / "POI_service"
SHARED_LIB = REPO_ROOT / "shared_lib"

_IMPORT_CONNECTOR_SCRIPT = f"""
import sys, os
sys.path.insert(0, {str(POI_SERVICE)!r})
sys.path.insert(0, {str(SHARED_LIB)!r})
os.environ.setdefault("MEMGRAPH_HOST", "localhost")
os.environ.setdefault("MEMGRAPH_PORT", "7687")
os.environ.setdefault("MEMGRAPH_USER", "synthetic")
os.environ.setdefault("MEMGRAPH_PASSWORD", "synthetic")
os.environ.pop("FIRESTORE_ENABLED", None)
import app.core.infrastructure.db.database.connector as c
assert not any("firebase" in m for m in sys.modules), "firebase imported at module import"
assert c.firestore_enabled() is False
c.firestore_db.connect()  # graph-only default: no-op
assert not any("firebase" in m for m in sys.modules), "firebase imported by disabled connect"
print("CLEAN")
"""

_AUTH_SCRIPT = f"""
import sys, os, dotenv
dotenv.load_dotenv = lambda *a, **k: False
sys.path.insert(0, {str(POI_SERVICE)!r})
sys.path.insert(0, {str(SHARED_LIB)!r})
try:
    import app.core.security.auth
except RuntimeError as exc:
    assert "JWT_SECRET" in str(exc), str(exc)
    print("FAIL_CLOSED")
else:
    print("IMPORT_SUCCEEDED")
"""


def _run(script: str, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


def test_default_mcp_uow_factory_path_needs_no_firebase():
    from app.core.infrastructure.db.database.connector import memgraph_db
    from app.core.infrastructure.db.uow import MemgraphUnitOfWork

    uow = MemgraphUnitOfWork(memgraph_db)

    assert uow.connector is memgraph_db
    assert "firebase_admin" not in sys.modules


def test_connector_import_and_disabled_connect_never_touch_firebase():
    env = {k: v for k, v in os.environ.items() if k != "FIRESTORE_ENABLED"}
    result = _run(_IMPORT_CONNECTOR_SCRIPT, REPO_ROOT, env)
    assert result.returncode == 0, result.stderr
    assert "CLEAN" in result.stdout


def test_absent_jwt_secret_still_fails_closed(tmp_path):
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("JWT_SECRET", "JWT_ALGORITHM")
    }
    result = _run(_AUTH_SCRIPT, tmp_path, env)
    assert result.returncode == 0, result.stderr
    assert "FAIL_CLOSED" in result.stdout


def test_present_jwt_secret_allows_import(tmp_path):
    env = dict(os.environ)
    env["JWT_SECRET"] = "synthetic-present-secret-0123456789abcdef"
    env["JWT_ALGORITHM"] = "HS256"
    result = _run(_AUTH_SCRIPT, tmp_path, env)
    assert result.returncode == 0, result.stderr
    assert "IMPORT_SUCCEEDED" in result.stdout
