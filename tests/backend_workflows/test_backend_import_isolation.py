"""Subprocess proof of import isolation and fail-loud storage selection (OC-027).

Importing the backend app must not import ``firebase_admin``, open a socket or
require a credential, and a Firebase selection with no package must fail loudly
rather than silently falling back to SQLite.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend_service"

_IMPORT_APP = (
    "import sys\n"
    "import app.main\n"
    "assert 'firebase_admin' not in sys.modules, sorted(sys.modules)\n"
    "print('ok', app.main.app.title)\n"
)

_FIREBASE_FAILS_LOUD = (
    "from app.core.settings import BackendSettings, build_repository\n"
    "try:\n"
    "    build_repository(BackendSettings(storage='firebase'))\n"
    "except Exception as exc:\n"
    "    print('raised', type(exc).__name__)\n"
    "else:\n"
    "    raise SystemExit('firebase selection unexpectedly succeeded')\n"
)


def _run(code: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(BACKEND_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env.pop("ITINERARY_STORAGE", None)
    env.pop("FIREBASE_KEY_PATH", None)
    return subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, env=env, cwd=str(REPO_ROOT))


def test_importing_app_does_not_import_firebase():
    result = _run(_IMPORT_APP)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().startswith("ok")


def test_firebase_selection_without_package_fails_loudly():
    result = _run(_FIREBASE_FAILS_LOUD)
    assert result.returncode == 0, result.stderr
    assert "raised" in result.stdout
