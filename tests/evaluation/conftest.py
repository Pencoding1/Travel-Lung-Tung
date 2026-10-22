"""Import-path bootstrap for the OC-018 evaluator tests.

Only the repository ``benchmarks`` directory is added to ``sys.path`` so the
stdlib-only ``evaluation`` package imports without installing anything. No
provider, database, graph, network or AI source module is imported.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks"
if str(BENCHMARKS) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS))


import pytest

from evaluation.h2 import evaluate_h2, load_h2_records, parse_h2_manifest
from evaluation.h3 import evaluate_h3, load_h3_records, parse_h3_manifest


@pytest.fixture
def run_h2():
    def _run(manifest_raw, records_raw):
        manifest = parse_h2_manifest(manifest_raw)
        loaded = load_h2_records(records_raw, manifest)
        return evaluate_h2(manifest, loaded)
    return _run


@pytest.fixture
def run_h3():
    def _run(manifest_raw, records_raw):
        manifest = parse_h3_manifest(manifest_raw)
        loaded = load_h3_records(records_raw, manifest)
        return evaluate_h3(manifest, loaded)
    return _run
