"""Import bootstrap for the AI063 Jev intent adapter/caller tests."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = REPO_ROOT / "ai_service"
CHAT_HELPERS = REPO_ROOT / "tests" / "ai_chat_memory"
for path in (AI_ROOT, CHAT_HELPERS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


@pytest.fixture(autouse=True)
def reset_router():
    from domains import jev_intent

    jev_intent.configure_intent_router({})
    yield
    jev_intent.configure_intent_router({})
