"""EXP089 read-only live E2 collector package.

The collector is deliberately separate from the historical synthetic
``benchmarks/spatial`` benchmark.  Nothing in this package connects to the
graph at import time; the only live driver is constructed by an explicit
``--execute`` invocation after a reviewed frozen manifest has been accepted.
"""

from __future__ import annotations

__all__ = ["runner"]
