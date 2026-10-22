"""Import bootstrap for the OC-040 opt-in provider tests.

Only ``ai_service`` is added to ``sys.path``; every external collaborator
(subprocess transport, capability probe, MCP session, Gemini HTTP) is faked. No
live model call, network, database, graph or credential is used.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = REPO_ROOT / "ai_service"
if str(AI_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_ROOT))


@pytest.fixture(autouse=True)
def hermetic_private_server_seam(monkeypatch):
    """Explicit interaction seam for the owned-server preflight in unit tests.

    The production adapter defaults to the real installed CLI (see
    ``opencode_cli.default_private_server_factory``). Unit tests replace it with
    :class:`FakePrivateServer`, so no test process is launched and no unit test
    is treated as engine/native proof. Tests that exercise the real lifecycle
    call ``PrivateServer`` directly or live in the task-owned native QA script.
    """
    from domains.providers import opencode_cli

    from helpers_provider import FakePrivateServer

    monkeypatch.setattr(opencode_cli, "default_private_server_factory",
                        FakePrivateServer)
    yield


@pytest.fixture(autouse=True)
def hermetic_cli_capability_probe(monkeypatch):
    """Never launch a real CLI from a test.

    The default probe runner is replaced with a canned ``run --help`` answer
    (the v2.0.32 text, which does not advertise ``--pure``) and the per-process
    capability cache is reset, so each test starts from an observed state.
    """
    from domains.providers import opencode_cli

    from helpers_provider import FakeHelpRunner

    opencode_cli.reset_capability_cache()
    monkeypatch.setattr(opencode_cli, "capability_probe_runner",
                        FakeHelpRunner())
    yield
    opencode_cli.reset_capability_cache()

