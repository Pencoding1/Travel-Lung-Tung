"""Import-path bootstrap for the OC-009 chat/memory contract tests.

Only the ``ai_service`` source root is added to ``sys.path`` so ``main`` and
``domains`` import without installing the service package. Collaborator fakes
live in ``helpers_chat_memory.py``.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = REPO_ROOT / "ai_service"
if str(AI_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_ROOT))


@pytest.fixture(autouse=True)
def reset_intent_router():
    """Start every chat/memory test from an explicit unconfigured Jev state.

    Tests that exercise routing inject a canned Jev transport (never a Gemini /
    CLI fake) through ``install_fake_jev`` after this reset.
    """
    import main
    main.configure_intent_router({})
    yield
