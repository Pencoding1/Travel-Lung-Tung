"""OC-021 live-model paired H2 engineering collector.

A stdlib-only, dry-run-by-default collector that drives the OpenCode CLI with an
explicit model/agent for the two H2 conditions (``hybrid`` and ``llm_only``),
captures each observation's raw event stream, and exports ``oc18.h2.v1`` records
without fabricating provenance, usage or outcomes.
"""

from __future__ import annotations
