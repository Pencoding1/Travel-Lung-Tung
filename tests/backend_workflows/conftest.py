"""Import-path bootstrap for the OC-027 backend itinerary-draft tests.

Adds the ``backend_service`` source root to ``sys.path`` so the real
``app.main``/``app.core`` modules import without installing anything. No network,
live database, Firebase or model call is made anywhere here.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend_service"
for _path in (BACKEND_ROOT, Path(__file__).resolve().parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
