"""Console entry point for the OC-018 offline evaluator.

Run directly (no installation required), from the repository root::

    python benchmarks/evaluation/evaluator.py --help

The ``benchmarks`` directory is put on ``sys.path`` so the ``evaluation`` package
imports without installing anything. No AI/POI/provider module is imported.
"""

from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_PARENT = Path(__file__).resolve().parent.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from evaluation.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
