"""Bootstrap for the Agent Chat MVP behaviour tests (FT-CHAT-MVP-001).

These tests encode the **behaviour contract**, not the current implementation.
A failure here means the feature does not yet behave as the contract says; it is
not evidence that the test was written against the wrong code.

Only ``ai_service`` is added to ``sys.path`` so ``main``/``domains`` import
without installing the service. Every collaborator (intent classifier, model,
MCP tools, clock) is replaced by a fake in ``mvp_harness.py``.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = REPO_ROOT / "ai_service"
if str(AI_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_ROOT))


@pytest.fixture(autouse=True)
def isolated_process_state(monkeypatch):
    """No durable profile store, no leftover router configuration."""
    import main

    monkeypatch.delenv("MEMORY_DB_PATH", raising=False)
    main.configure_intent_router({})
    yield
