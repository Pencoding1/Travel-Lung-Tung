"""Repository-root runner for the acquisition dry-run CLI.

Allows ``python scripts/acquisition/run_acquisition.py ...`` without installing
the service packages by adding the repository root to ``sys.path`` first.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from crawler_service.app.acquisition.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
