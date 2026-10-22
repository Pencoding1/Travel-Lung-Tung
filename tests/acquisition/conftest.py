"""Import-path bootstrap for the OC-006 acquisition tests.

Only the repository root is added to ``sys.path`` so the package imports as
``crawler_service.app.acquisition`` and never collides with the unrelated
top-level ``app`` package used by the POI service.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
