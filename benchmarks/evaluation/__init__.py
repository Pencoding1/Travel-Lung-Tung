"""OC-018 reproducible offline evaluator for paired H2 / H3 outcomes.

This package is **stdlib-only** and imports no AI/planning/POI source and no
provider, database, graph or network client. It consumes *recorded* outcomes
(JSONL) against a frozen manifest and produces reproducible metrics plus
machine-readable diagnostics. It never executes a live experiment and never
fabricates raw records.
"""

EVALUATOR_VERSION = "oc18.eval.v1"

__all__ = ["EVALUATOR_VERSION"]
