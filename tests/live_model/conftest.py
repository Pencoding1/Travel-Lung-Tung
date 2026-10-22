"""Import bootstrap for the OC-021 live-model collector tests.

Only the repository ``benchmarks`` directory (for ``live_model`` and
``evaluation``) and the repository root are added to ``sys.path``. No live call
is performed by any test.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks"
HERE = Path(__file__).resolve().parent
for path in (str(HERE), str(BENCHMARKS), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)
