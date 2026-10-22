"""Import-path bootstrap for the OC-034 primary dataset tests.

Only the repository root is added so the capability imports as
``crawler_service.app.primary_dataset`` and never collides with the unrelated
top-level ``app`` package used by the POI service. The POI model itself is
bootstrapped in isolation by ``primary_dataset.validation``.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
