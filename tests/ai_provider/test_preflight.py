"""R1 guard-carrier and pre-model agent-policy gates."""

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from domains.providers import (ModelUnavailableError, OpenCodeCliProvider,
                               ProviderConfig)
from domains.providers import cli_runtime
from domains.providers import private_server
from domains.providers.private_server import (AgentProjectionError,
                                              ServerPreflightError,
                                              evaluate_agent_projection)

from helpers_provider import (FakeHelpRunner, FakePrivateServer, FakeRunner,
                              call_fixture, python_executable, REQUESTED)


def _config(**overrides):
    values = dict(
        provider="opencode_cli", model=REQUESTED,
        cli_executable=python_executable(), cli_agent="r1-test-agent",
        cli_pure=False, cli_timeout_seconds=5, cli_max_attempts=1)
    values.update(overrides)
    return ProviderConfig(**values)


def _payload():
    return {"model": REQUESTED,
            "messages": [{"role": "user", "content": "synthetic"}]}


def _run(provider):
    return asyncio.run(provider.complete(_payload()))


def _fixture():
    events, export = call_fixture("ok")
    return FakeRunner(run_fixture=events, export_fixture=export)


def test_child_environment_preserves_a_nonempty_inline_guard():
    guard = '{"policies":[{"action":"tool.use","resource":"*","effect":"deny"}]}'
    env = cli_runtime.child_environment(
        _config(), base={"OPENCODE_CONFIG_CONTENT": guard})
    assert env["OPENCODE_CONFIG_CONTENT"] == guard


def test_nonempty_inline_carrier_is_refused_before_any_runner(monkeypatch):
    guard = "R1_SYNTHETIC_GUARD_VALUE"
    runner = _fixture()
    monkeypatch.setenv("OPENCODE_CONFIG_CONTENT", guard)

    with pytest.raises(ModelUnavailableError) as excinfo:
        _run(OpenCodeCliProvider(_config(), runner=runner,
                                 capability_runner=FakeHelpRunner()))

    assert excinfo.value.code == "cli_ambient_config_refused"
    assert guard not in str(excinfo.value)
    assert runner.calls == []


def test_explicit_config_path_is_refused_before_any_runner(monkeypatch):
    runner = _fixture()
    monkeypatch.setenv("OPENCODE_CONFIG", "R1_SYNTHETIC_PATH")

    with pytest.raises(ModelUnavailableError) as excinfo:
        _run(OpenCodeCliProvider(_config(), runner=runner,
                                 capability_runner=FakeHelpRunner()))

    assert excinfo.value.code == "cli_ambient_config_refused"
    assert runner.calls == []


def test_allow_policy_mismatch_is_refused_before_the_model_runner():
    runner = _fixture()
    original = cli_runtime.transport_config

    def allowing(config, controls=None):
        document = original(config, controls)
        document["agents"][config.cli_agent]["permissions"] = [
            {"action": "*", "resource": "*", "effect": "allow"}]
        return document

    with patch.object(cli_runtime, "transport_config", allowing):
        with pytest.raises(ModelUnavailableError) as excinfo:
            _run(OpenCodeCliProvider(_config(), runner=runner,
                                     capability_runner=FakeHelpRunner()))

    assert excinfo.value.code == "cli_agent_preflight_failed"
    assert runner.runs == []


def test_each_call_uses_a_fresh_restrictive_agent():
    runner = _fixture()
    provider = OpenCodeCliProvider(_config(), runner=runner)
    _run(provider)
    _run(provider)

    agents = [call["argv"][call["argv"].index("--agent") + 1]
              for call in runner.runs]
    assert len(agents) == 2
    assert agents[0] != agents[1]
    for call, agent_id in zip(runner.runs, agents):
        config = json.loads(call["transport_config"])
        assert config["default_agent"] == agent_id
        assert set(config["agents"]) == {agent_id}
        assert config["agents"][agent_id]["mode"] == "primary"
        assert config["agents"][agent_id]["steps"] == 2
        assert config["agents"][agent_id]["permissions"][0] == {
            "action": "*", "resource": "*", "effect": "deny"}
        assert config["permissions"] == [
            {"action": "*", "resource": "*", "effect": "deny"}]


# ---------------------------------------------------------------------------
# Same-engine agent projection (pure validation) and pre-model failure
# ---------------------------------------------------------------------------
def _projection(*, agent_id="qa-agent-1", directory=None, mode="primary",
                steps=2, system=cli_runtime.TRANSPORT_SYSTEM_PROMPT,
                model=None, permissions=None):
    rules = permissions if permissions is not None else (
        [{"action": "*", "resource": "*", "effect": "deny"}]
        + cli_runtime.deny_permissions()[1:])
    agent = {
        "id": agent_id,
        "name": agent_id,
        "request": {"settings": {}, "headers": {}, "body": {}},
        "mode": mode,
        "hidden": False,
        "steps": steps,
        "system": system,
        "permissions": rules,
    }
    if model is not None:
        agent["model"] = model
    return {
        "location": {"directory": directory or str(Path.cwd())},
        "data": [agent],
    }


def test_valid_projection_is_verified_without_returning_request_bodies(tmp_path):
    envelope = _projection(directory=str(tmp_path),
                           model={"providerID": "aibox",
                                  "id": "ds/deepseek-flash"})
    proof = evaluate_agent_projection(
        envelope, agent_id="qa-agent-1", workdir=tmp_path,
        alias="aibox/ds/deepseek-flash")
    assert proof["status"] == "agent_projection_verified"
    assert proof["location_verified"] is True
    assert proof["model_ref_present"] is True
    assert proof["wildcard_deny"] is True
    assert "request" not in proof and "headers" not in proof


def test_global_deny_before_the_agent_deny_is_accepted(tmp_path):
    rules = [{"action": "tool.use", "resource": "*", "effect": "deny"},
             {"action": "*", "resource": "*", "effect": "deny"}]
    envelope = _projection(directory=str(tmp_path), permissions=rules)
    assert evaluate_agent_projection(
        envelope, agent_id="qa-agent-1", workdir=tmp_path,
        alias=REQUESTED)["wildcard_deny"] is True


@pytest.mark.parametrize("mutation,code", [
    ({"directory": "C:\\elsewhere"}, "agent_location_mismatch"),
    ({"mode": "subagent"}, "agent_mode_mismatch"),
    ({"steps": 3}, "agent_steps_mismatch"),
    ({"steps": True}, "agent_steps_mismatch"),
    ({"system": "another prompt"}, "agent_system_mismatch"),
    ({"model": {"providerID": "other", "id": "ds/deepseek-flash"}},
     "agent_model_mismatch"),
    ({"model": {"providerID": "aibox", "id": "other"}},
     "agent_model_mismatch"),
    ({"model": "aibox/ds/deepseek-flash"}, "agent_model_malformed"),
    ({"permissions": [{"action": "read", "resource": "*",
                       "effect": "deny"}]}, "agent_wildcard_deny_missing"),
    ({"permissions": [{"action": "*", "resource": "*", "effect": "deny"},
                      {"action": "read", "resource": "*",
                       "effect": "allow"}]}, "agent_permission_after_deny"),
    ({"permissions": [{"action": "*", "resource": "*", "effect": "deny"},
                      {"action": "read", "resource": "*",
                       "effect": "ask"}]}, "agent_permission_after_deny"),
    ({"permissions": [{"action": "*", "resource": "*", "effect": "deny"},
                      {"action": "read", "effect": "deny"}]},
     "agent_permissions_malformed"),
    ({"permissions": []}, "agent_permissions_missing"),
])
def test_projection_mutations_fail_closed(tmp_path, mutation, code):
    values = {"directory": str(tmp_path),
              "model": {"providerID": "aibox", "id": "ds/deepseek-flash"}}
    values.update(mutation)
    envelope = _projection(**values)
    with pytest.raises(AgentProjectionError) as excinfo:
        evaluate_agent_projection(envelope, agent_id="qa-agent-1",
                                  workdir=tmp_path, alias=REQUESTED)
    assert excinfo.value.code == code


def test_wrong_agent_is_retryable_absent_and_duplicates_are_refused(tmp_path):
    envelope = _projection(directory=str(tmp_path))
    with pytest.raises(AgentProjectionError) as excinfo:
        evaluate_agent_projection(envelope, agent_id="other-agent",
                                  workdir=tmp_path, alias=REQUESTED)
    assert excinfo.value.code == "agent_absent"
    assert excinfo.value.retryable is True

    duplicate = _projection(directory=str(tmp_path))
    duplicate["data"].append(dict(duplicate["data"][0]))
    with pytest.raises(AgentProjectionError) as excinfo:
        evaluate_agent_projection(duplicate, agent_id="qa-agent-1",
                                  workdir=tmp_path, alias=REQUESTED)
    assert excinfo.value.code == "agent_ambiguous"


def test_server_start_failure_makes_zero_model_runner_calls():
    events, export = call_fixture("unused")
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    server = FakePrivateServer(
        start_error=ServerPreflightError("server_listener_not_owned"))
    provider = OpenCodeCliProvider(
        _config(), runner=runner, server_factory=lambda *a, **k: server)
    with pytest.raises(ModelUnavailableError) as excinfo:
        _run(provider)
    assert excinfo.value.code == "cli_server_preflight_failed"
    assert runner.calls == []
    assert server.closed
    # The capacity permit was released after the bounded cleanup.
    assert provider._semaphore.acquire(blocking=False) is True
    provider._release()


def test_explicit_ambient_carrier_never_starts_the_server(monkeypatch):
    started = []

    def factory(*args, **kwargs):
        started.append(True)
        return FakePrivateServer(*args, **kwargs)

    monkeypatch.setenv("OPENCODE_CONFIG", "R1_SYNTHETIC_PATH")
    with pytest.raises(ModelUnavailableError) as excinfo:
        _run(OpenCodeCliProvider(_config(), runner=FakeRunner(),
                                 server_factory=factory))
    assert excinfo.value.code == "cli_ambient_config_refused"
    assert started == []


def test_guard_probe_keeps_service_keys_removed_and_provider_keys_kept():
    fake = cli_runtime.child_environment(
        _config(), base={"TYPESAFE_API_TOKEN": "SYNTHETIC_ONLY",
                         "TYPESAFE_API_KEY": "SYNTHETIC_ONLY",
                         "GEMINI_API_KEY": "SYNTHETIC_ONLY",
                         "AIBOX_API_KEY": "PROVIDER_CREDENTIAL"})
    assert "TYPESAFE_API_TOKEN" not in fake
    assert "TYPESAFE_API_KEY" not in fake
    assert "GEMINI_API_KEY" not in fake
    assert fake["AIBOX_API_KEY"] == "PROVIDER_CREDENTIAL"


def test_cancellation_during_preflight_runs_no_model_and_closes_server():
    events, export = call_fixture("unused")
    runner = FakeRunner(run_fixture=events, export_fixture=export)

    class BlockingServer(FakePrivateServer):
        def start(self, cancel_event=None):
            super().start(cancel_event=cancel_event)
            while not cancel_event.is_set():
                import time as _time
                _time.sleep(0.01)

    server = BlockingServer()
    provider = OpenCodeCliProvider(
        _config(), runner=runner, server_factory=lambda *a, **k: server)

    async def _cancel():
        task = asyncio.create_task(provider.complete(_payload()))
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return

    asyncio.run(_cancel())
    assert runner.runs == []
    assert server.closed


def test_pure_request_is_refused_before_the_server_is_started():
    from helpers_provider import HELP_RUN_NO_PURE
    events, export = call_fixture("unused")
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    server = FakePrivateServer()
    provider = OpenCodeCliProvider(
        _config(cli_pure=True), runner=runner,
        capability_runner=FakeHelpRunner(HELP_RUN_NO_PURE),
        server_factory=lambda *a, **k: server)
    with pytest.raises(ModelUnavailableError) as excinfo:
        _run(provider)
    assert excinfo.value.code == "cli_pure_unsupported"
    assert server.starts == []
    assert runner.runs == []
