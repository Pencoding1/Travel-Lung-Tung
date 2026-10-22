"""The actual CLI adapter against controlled runner/stream/export fixtures."""

import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest
from domains.providers import (ModelUnavailableError, OpenCodeCliProvider,
                               ProviderConfig, build_prompt, cli_runtime)
from domains.providers import process
from domains.providers.private_server import AgentProjectionError

from helpers_provider import (DEFAULT_TOKENS, FAKE_SERVER_URL, MODEL, PROVIDER,
                              REQUESTED, FakePrivateServer, FakeRunner,
                              _rebind_export_agent, call_fixture,
                              event_text, event_text_v2, export_payload,
                              export_payload_v2, python_executable, snapshot,
                              token_components, v2_fixture)


def _config(**overrides):
    values = {
        "provider": "opencode_cli",
        "model": REQUESTED,
        "cli_executable": python_executable(),
        "cli_agent": "oc040-test-agent",
        "cli_timeout_seconds": 5.0,
        "cli_max_output_bytes": 1_000_000,
        "cli_max_prompt_chars": 50_000,
        "cli_max_attempts": 1,
        "cli_max_concurrency": 1,
        "cli_pure": False,
    }
    values.update(overrides)
    return ProviderConfig(**values)


def _payload(text="hello", tools=None):
    payload = {"model": REQUESTED,
               "messages": [{"role": "system", "content": "sys"},
                            {"role": "user", "content": text}]}
    if tools is not None:
        payload["tools"] = tools
    return payload


def _tool_spec(name="get_poi_details"):
    return {"type": "function", "function": {
        "name": name,
        "description": "details",
        "parameters": {
            "type": "object",
            "properties": {"poi_id": {"type": "string"}},
            "required": ["poi_id"],
            "additionalProperties": False,
        },
    }}


def _run(provider, payload):
    return asyncio.run(provider.complete(payload))


def _error(code, runner, payload=None, config=None):
    provider = OpenCodeCliProvider(config or _config(), runner=runner)
    with pytest.raises(ModelUnavailableError) as excinfo:
        _run(provider, payload or _payload())
    assert excinfo.value.code == code
    return excinfo.value


def test_plain_text_response_and_usage_mapping():
    events, export = call_fixture("Hello there")
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    payload = _payload()
    before = snapshot(payload)

    result = _run(OpenCodeCliProvider(_config(), runner=runner), payload)

    assert payload == before
    assert result["choices"][0]["message"] == {
        "role": "assistant", "content": "Hello there"}
    assert result["model"] == REQUESTED
    assert result["usage"]["prompt_tokens"] == 11
    assert result["usage"]["completion_tokens"] == 5
    assert result["usage"]["total_tokens"] == 16
    assert result["usage"]["provider_components"]["cache_read"] == 1
    assert result["usage"]["completion_tokens_details"]["reasoning_tokens"] == 3
    meta = result["_provider"]
    assert meta["observed_model"] == REQUESTED
    assert meta["identity_source"] == "opencode_session_export"
    assert meta["attempts"] == 1


def test_argv_is_an_argument_array_with_model_agent_and_no_unsupported_flag():
    events, export = call_fixture("ok")
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    _run(OpenCodeCliProvider(_config(), runner=runner), _payload("do not shell"))

    run = runner.runs[0]
    argv = run["argv"]
    assert argv[0] == python_executable()
    assert argv[1] == "run"
    # V2: the same owned private server is explicit; no standalone fallback.
    assert argv[2] == "--server"
    assert argv[3] == FAKE_SERVER_URL
    assert "--standalone" not in argv
    assert "--pure" not in argv
    assert argv[argv.index("--model") + 1] == REQUESTED
    assert argv[argv.index("--agent") + 1].startswith("oc040-test-agent-")
    assert argv[argv.index("--format") + 1] == "json"
    assert "--file" not in argv
    assert argv[-1] == build_prompt(_payload("do not shell"))
    assert "do not shell" in argv[-1]
    assert not any("--auto" == part or "--share" == part for part in argv)


def test_export_uses_the_installed_v2_session_route():
    events, export = call_fixture("ok")
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    _run(OpenCodeCliProvider(_config(), runner=runner), _payload())

    export_call = runner.exports[0]
    assert export_call["argv"][1:] == [
        "session", "export", "--server", FAKE_SERVER_URL,
        "ses_test0001"]
    assert "export" != export_call["argv"][1]


def test_same_server_agent_preflight_runs_before_the_model_call():
    events, export = call_fixture("ok")
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    server = FakePrivateServer()
    result = _run(OpenCodeCliProvider(_config(), runner=runner,
                                     server_factory=lambda *a, **k: server),
                  _payload())

    # The fake CLI never received a models-listing probe.
    assert runner.calls[0]["argv"][1] == "run"
    run_argv = runner.runs[0]["argv"]
    assert run_argv[2:4] == ["--server", server.url]
    assert result["_provider"]["readiness_gate"] == \
        "same_server_agent_projection_verified"
    assert result["_provider"]["agent_preflight"]["status"] == \
        "agent_projection_verified"
    assert result["_provider"]["agent_preflight"]["engine"][
        "location_verified"] is True
    assert result["_provider"]["agent_preflight"]["engine"]["agent_id"] == \
        run_argv[run_argv.index("--agent") + 1]
    assert len(server.starts) == 1
    assert server.preflights[0]["agent_id"] == result["_provider"]["agent_id"]
    assert server.preflights[0]["alias"] == REQUESTED
    assert server.closed and server.closed[0]["port_closed"] is True
    assert result["_provider"]["owned_server"]["cleanup"][
        "process_terminal"] is True


def test_preflight_failure_sends_no_prompt():
    events, export = call_fixture("unused")
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    server = FakePrivateServer(
        preflight_error=AgentProjectionError("agent_system_mismatch"))
    provider = OpenCodeCliProvider(
        _config(), runner=runner, server_factory=lambda *a, **k: server)
    with pytest.raises(ModelUnavailableError) as excinfo:
        _run(provider, _payload())
    assert excinfo.value.code == "cli_agent_preflight_failed"
    assert runner.runs == []
    assert server.closed


def test_transport_config_is_a_unique_deny_only_v2_agent():
    events, export = call_fixture("ok")
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    _run(OpenCodeCliProvider(_config(), runner=runner), _payload())

    env = runner.runs[0]["env"]
    # The V1 inline mechanism is gone; a real file carries the config.
    assert "OPENCODE_CONFIG_CONTENT" not in env
    config = json.loads(runner.runs[0]["transport_config"])
    agent_id = next(iter(config["agents"]))
    assert agent_id.startswith("oc040-test-agent-")
    assert config["default_agent"] == agent_id
    assert config["model"] == REQUESTED
    assert config["share"] == "disabled"
    agent = config["agents"][agent_id]
    assert agent["mode"] == "primary"
    assert agent["hidden"] is False
    # One step: a tool-asking model cannot loop.
    assert agent["steps"] == 2
    assert agent["system"].startswith("You are a text-only model transport")
    assert {"action": "*", "resource": "*", "effect": "deny"} in agent["permissions"]
    for name in ("read", "write", "bash", "shell", "webfetch", "question",
                 "task", "subagent"):
        assert {"action": name, "resource": "*", "effect": "deny"} in agent["permissions"]
    assert config["permissions"] == [
        {"action": "*", "resource": "*", "effect": "deny"}]
    assert "GEMINI_API_KEY" not in env
    assert "JWT_SECRET" not in env
    assert "MEMORY_DB_PATH" not in env


def test_sampling_controls_bind_to_the_exact_alias_request_body():
    events, export = call_fixture("ok")
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    payload = _payload()
    payload["temperature"] = 0.9
    payload["top_p"] = 0.8
    before = snapshot(payload)

    result = _run(OpenCodeCliProvider(_config(), runner=runner), payload)

    config = json.loads(runner.runs[0]["transport_config"])
    body = config["providers"]["aibox"]["models"]["ds/deepseek-flash"]["body"]
    assert body == {"temperature": 0.9, "top_p": 0.8}
    # The alias is split on the FIRST "/" only.
    assert config["providers"]["aibox"]["models"].keys() == {"ds/deepseek-flash"}
    assert result["_provider"]["controls"] == {
        "requested": {"temperature": 0.9, "top_p": 0.8},
        "configured": {"temperature": 0.9, "top_p": 0.8},
        "applied": False,
        "verification": "not_observable_from_transport",
        "binding": "provider_model_request_body",
        "unsupported": [],
    }
    assert payload == before


@pytest.mark.parametrize("name,value,code", [
    ("temperature", -0.1, "invalid_sampling_control"),
    ("temperature", 2.1, "invalid_sampling_control"),
    ("temperature", "0.5", "invalid_sampling_control"),
    ("temperature", True, "invalid_sampling_control"),
    ("temperature", float("nan"), "invalid_sampling_control"),
    ("temperature", float("inf"), "invalid_sampling_control"),
    ("temperature", 10 ** 400, "invalid_sampling_control"),
    ("top_p", -0.1, "invalid_sampling_control"),
    ("top_p", 1.1, "invalid_sampling_control"),
    ("max_completion_tokens", 20, "unsupported_model_control"),
    ("max_tokens", 20, "unsupported_model_control"),
    ("top_k", 5, "unsupported_model_control"),
])
def test_unsupported_or_invalid_controls_fail_before_launch(name, value, code):
    events, export = call_fixture("unused")
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    payload = _payload()
    payload[name] = value
    _error(code, runner, payload)
    assert runner.calls == []


def test_distinct_temperatures_change_agent_config_but_not_prompt_text():
    events, export = call_fixture("ok")
    payload_cold = _payload()
    payload_cold["temperature"] = 0.0
    payload_warm = _payload()
    payload_warm["temperature"] = 0.9

    runner_cold = FakeRunner(run_fixture=events, export_fixture=export)
    _run(OpenCodeCliProvider(_config(), runner=runner_cold), payload_cold)
    runner_warm = FakeRunner(run_fixture=events, export_fixture=export)
    _run(OpenCodeCliProvider(_config(), runner=runner_warm), payload_warm)

    config_cold = json.loads(runner_cold.runs[0]["transport_config"])
    config_warm = json.loads(runner_warm.runs[0]["transport_config"])
    cold_body = config_cold["providers"]["aibox"]["models"]["ds/deepseek-flash"]["body"]
    warm_body = config_warm["providers"]["aibox"]["models"]["ds/deepseek-flash"]["body"]
    assert cold_body == {"temperature": 0.0}
    assert warm_body == {"temperature": 0.9}
    assert runner_cold.runs[0]["argv"][-1] == runner_warm.runs[0]["argv"][-1]


def test_router_json_stays_plain_assistant_content():
    events, export = call_fixture('{"intent": "CHITCHAT"}')
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    result = _run(OpenCodeCliProvider(_config(), runner=runner), _payload())
    assert result["choices"][0]["message"]["content"] == '{"intent": "CHITCHAT"}'
    assert "tool_calls" not in result["choices"][0]["message"]


def test_valid_tool_envelope_becomes_openai_tool_calls():
    envelope = json.dumps({"tool_calls": [{
        "id": "call_1", "name": "get_poi_details",
        "arguments": {"poi_id": "poi_a"}}]})
    events, export = call_fixture(envelope)
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    result = _run(OpenCodeCliProvider(_config(), runner=runner),
                  _payload(tools=[_tool_spec()]))
    message = result["choices"][0]["message"]
    assert message["content"] is None
    assert message["tool_calls"][0]["id"] == "call_1"
    assert message["tool_calls"][0]["function"]["name"] == "get_poi_details"
    assert json.loads(message["tool_calls"][0]["function"]["arguments"]) == {
        "poi_id": "poi_a"}
    assert result["choices"][0]["finish_reason"] == "tool_calls"


def test_tool_content_envelope_is_final_content():
    events, export = call_fixture(json.dumps({"content": "All done."}))
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    result = _run(OpenCodeCliProvider(_config(), runner=runner),
                  _payload(tools=[_tool_spec()]))
    assert result["choices"][0]["message"]["content"] == "All done."


@pytest.mark.parametrize("envelope,code", [
    (json.dumps({"tool_calls": [{"id": "call_1", "name": "not_a_tool",
                                 "arguments": {}}]}), "unknown_tool"),
    (json.dumps({"tool_calls": [{"id": "call_1", "name": "get_poi_details",
                                 "arguments": {"poi_id": 5}}]}),
     "invalid_tool_arguments"),
    (json.dumps({"tool_calls": [{"id": "call_1", "name": "get_poi_details",
                                 "arguments": {}}]}),
     "invalid_tool_arguments"),
    (json.dumps({"tool_calls": [{"id": "bad id", "name": "get_poi_details",
                                 "arguments": {"poi_id": "x"}}]}),
     "invalid_tool_call_id"),
    (json.dumps({"tool_calls": [], "extra": 1}), "invalid_tool_envelope"),
    ("{not json", "invalid_tool_envelope"),
])
def test_invalid_tool_envelopes_fail_closed(envelope, code):
    events, export = call_fixture(envelope)
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    _error(code, runner, _payload(tools=[_tool_spec()]))


def test_duplicate_tool_call_ids_are_rejected():
    envelope = json.dumps({"tool_calls": [
        {"id": "call_1", "name": "get_poi_details",
         "arguments": {"poi_id": "a"}},
        {"id": "call_1", "name": "get_poi_details",
         "arguments": {"poi_id": "b"}},
    ]})
    events, export = call_fixture(envelope)
    _error("invalid_tool_call_id",
           FakeRunner(run_fixture=events, export_fixture=export),
           _payload(tools=[_tool_spec()]))


def test_native_cli_tool_event_is_denied():
    events, export = call_fixture("should not be used", tool_use=True)
    _error("cli_tool_use_denied",
           FakeRunner(run_fixture=events, export_fixture=export))


def test_cli_error_event_is_rejected():
    events, export = call_fixture("error", error=True)
    _error("cli_error_event",
           FakeRunner(run_fixture=events, export_fixture=export))


def test_unfinished_response_is_rejected():
    events, export = call_fixture("partial", reason="length")
    _error("unfinished_response",
           FakeRunner(run_fixture=events, export_fixture=export))


def test_event_model_hint_mismatch_is_rejected():
    events, export = call_fixture("text", model_hint="other/model")
    _error("model_mismatch",
           FakeRunner(run_fixture=events, export_fixture=export))


def test_export_model_mismatch_is_rejected():
    events, export = call_fixture("text")
    mismatch = json.dumps(export_payload("text", "ses_test0001",
                                         "msg_test0001", model="other/model",
                                         provider="other")).encode()
    _error("model_mismatch",
           FakeRunner(run_fixture=events, export_fixture=mismatch))


def test_export_text_and_usage_conflicts_are_rejected():
    events, _export = call_fixture("text")
    wrong_text = json.dumps(export_payload("different", "ses_test0001",
                                           "msg_test0001")).encode()
    _error("text_conflict",
           FakeRunner(run_fixture=events, export_fixture=wrong_text))

    wrong_tokens = dict(DEFAULT_TOKENS, total=999)
    wrong_usage = json.dumps(export_payload("text", "ses_test0001",
                                            "msg_test0001",
                                            tokens=wrong_tokens)).encode()
    _error("usage_conflict",
           FakeRunner(run_fixture=events, export_fixture=wrong_usage))


def test_negative_export_usage_is_rejected():
    events, _export = call_fixture("text")
    negative = {"input": -1, "output": 2, "reasoning": 3,
                "cache": {"read": 0, "write": 0}, "total": 4}
    export = json.dumps(export_payload("text", "ses_test0001",
                                       "msg_test0001",
                                       tokens=negative)).encode()
    _error("invalid_usage",
           FakeRunner(run_fixture=events, export_fixture=export))


def test_export_session_mismatch_is_rejected():
    events, _export = call_fixture("text")
    export = json.dumps(export_payload("text", "ses_other0001",
                                       "msg_test0001")).encode()
    _error("export_session_mismatch",
           FakeRunner(run_fixture=events, export_fixture=export))


def test_malformed_export_is_rejected():
    events, _export = call_fixture("text")
    _error("session_export_malformed",
           FakeRunner(run_fixture=events, export_fixture=b"{not json"))


@pytest.mark.parametrize("result,code", [
    (process.CommandResult(argv=[], exit_code=-1, duration_seconds=1.0,
                           timed_out=True, output_overflow=False,
                           stdout=b"", stderr=b""), "cli_timeout"),
    (process.CommandResult(argv=[], exit_code=-1, duration_seconds=1.0,
                           timed_out=False, output_overflow=True,
                           stdout=b"", stderr=b""), "cli_output_overflow"),
    (process.CommandResult(argv=[], exit_code=2, duration_seconds=1.0,
                           timed_out=False, output_overflow=False,
                           stdout=b"", stderr=b"secret"), "cli_nonzero_exit"),
])
def test_transport_failures_are_observable(result, code):
    class StaticRunner:
        def __call__(self, argv, **kwargs):
            if len(argv) > 1 and argv[1] == "models":
                return process.CommandResult(
                    argv=list(argv), exit_code=0, duration_seconds=0.01,
                    timed_out=False, output_overflow=False,
                    stdout=(REQUESTED + "\n").encode(), stderr=b"")
            return result

    _error(code, StaticRunner())


def test_retry_attempts_are_retained_in_provider_metadata():
    events, export = call_fixture("ok")
    timeout = process.CommandResult(argv=[], exit_code=-1,
                                    duration_seconds=0.1, timed_out=True,
                                    output_overflow=False, stdout=b"",
                                    stderr=b"")
    state = {"count": 0, "models": 0}

    class RetryRunner:
        def __call__(self, argv, **kwargs):
            if len(argv) > 1 and argv[1] == "models":
                state["models"] += 1
                return process.CommandResult(
                    argv=list(argv), exit_code=0, duration_seconds=0.01,
                    timed_out=False, output_overflow=False,
                    stdout=(REQUESTED + "\n").encode(), stderr=b"")
            state["count"] += 1
            if state["count"] == 1:
                return timeout
            if argv[1:3] == ["session", "export"]:
                return process.CommandResult(
                    argv=list(argv), exit_code=0, duration_seconds=0.01,
                    timed_out=False, output_overflow=False,
                    stdout=_rebind_export_agent(export, kwargs["cwd"]),
                    stderr=b"")
            return process.CommandResult(
                argv=list(argv), exit_code=0, duration_seconds=0.01,
                timed_out=False, output_overflow=False, stdout=events,
                stderr=b"")

    result = _run(OpenCodeCliProvider(
        _config(cli_max_attempts=2), runner=RetryRunner()), _payload())
    assert result["_provider"]["attempts"] == 2
    assert result["_provider"]["failed_attempts"] == 1
    assert state["models"] == 0        # no models-listing fallback exists
    assert state["count"] == 3         # failed run, successful run, export


def test_prompt_bound_and_model_mismatch_fail_before_launch():
    events, export = call_fixture("ok")
    runner = FakeRunner(run_fixture=events, export_fixture=export)

    provider = OpenCodeCliProvider(_config(cli_max_prompt_chars=1024),
                                   runner=runner)
    with pytest.raises(ModelUnavailableError) as excinfo:
        _run(provider, _payload("x" * 5000))
    assert excinfo.value.code == "prompt_too_large"
    assert runner.calls == []

    provider = OpenCodeCliProvider(_config(), runner=runner)
    with pytest.raises(ModelUnavailableError) as excinfo:
        _run(provider, {"model": "other/model",
                        "messages": [{"role": "user", "content": "hi"}]})
    assert excinfo.value.code == "model_config_mismatch"
    assert runner.calls == []


def test_evidence_is_opt_in(tmp_path):
    events, export = call_fixture("evidence")
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    result = _run(OpenCodeCliProvider(_config(evidence_dir=tmp_path),
                                      runner=runner), _payload())
    assert result["_provider"]["evidence"] == "stored"
    files = sorted(path.name for path in tmp_path.iterdir())
    assert files and files[0].startswith("oc040-")
    call_dir = next(tmp_path.iterdir())
    names = {path.name for path in call_dir.iterdir()}
    assert "attempt-1.events.jsonl" in names
    assert "attempt-1.session-export.json" in names
    assert "meta.json" in names


def test_missing_unsafe_cli_is_a_bounded_error(tmp_path):
    provider = OpenCodeCliProvider(
        _config(cli_executable=str(tmp_path / "definitely-missing.exe")),
        runner=FakeRunner())
    with pytest.raises(ModelUnavailableError) as excinfo:
        _run(provider, _payload())
    assert excinfo.value.code == "cli_not_found"


@pytest.mark.skipif(os.name != "nt", reason="Windows wrapper rule only")
def test_windows_command_wrappers_are_refused(tmp_path):
    wrapper = tmp_path / "opencode.cmd"
    wrapper.write_text("@echo off\n", encoding="utf-8")
    with pytest.raises(ModelUnavailableError) as excinfo:
        process.resolve_executable(str(wrapper))
    assert excinfo.value.code == "cli_unsafe_executable"


def test_real_bounded_process_timeout_and_overflow():
    timeout = process.run_command(
        [python_executable(), "-c", "import time; time.sleep(2)"],
        cwd=Path.cwd(), timeout=0.3,
        env=dict(os.environ), max_output_bytes=1024)
    assert timeout.timed_out is True
    assert timeout.duration_seconds < 5.0

    overflow = process.run_command(
        [python_executable(), "-c", "print('x' * 100000)"],
        cwd=Path.cwd(), timeout=10.0,
        env=dict(os.environ), max_output_bytes=512)
    assert overflow.output_overflow is True
    assert len(overflow.stdout) + len(overflow.stderr) <= 512


def test_task_cancellation_sets_the_process_cleanup_event():
    captured = {}

    class BlockingRunner:
        def __call__(self, argv, *, cwd, timeout, env, max_output_bytes,
                     cancel_event=None):
            captured["cancel_event"] = cancel_event
            while not cancel_event.is_set():
                time.sleep(0.01)
            return process.CommandResult(
                argv=list(argv), exit_code=-1, duration_seconds=0.1,
                timed_out=False, output_overflow=False, stdout=b"",
                stderr=b"", cancelled=True)

    provider = OpenCodeCliProvider(_config(), runner=BlockingRunner())

    async def _run_and_cancel():
        task = asyncio.create_task(provider.complete(_payload()))
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return

    asyncio.run(_run_and_cancel())
    assert captured["cancel_event"].is_set()


def test_real_process_cancellation_terminates_and_returns_quickly():
    cancel_event = threading.Event()

    async def _run():
        task = asyncio.create_task(asyncio.to_thread(
            process.run_command,
            [python_executable(), "-c", "import time; time.sleep(5)"],
            cwd=Path.cwd(), timeout=30.0, env=dict(os.environ),
            max_output_bytes=1024, cancel_event=cancel_event))
        await asyncio.sleep(0.3)
        cancel_event.set()
        return await task

    started = time.monotonic()
    result = asyncio.run(_run())
    assert result.cancelled is True
    assert time.monotonic() - started < 5.0


def test_real_process_arguments_are_not_shell_interpolated():
    marker = "a&b|c>d"
    result = process.run_command(
        [python_executable(), "-c",
         "import sys; print(sys.argv[1])", marker],
        cwd=Path.cwd(), timeout=10.0,
        env=dict(os.environ), max_output_bytes=1024)
    assert result.exit_code == 0
    assert result.stdout.decode().strip() == marker

# ---------------------------------------------------------------------------
# Installed V2 runtime: stream/export shapes, agent binding, isolation
# ---------------------------------------------------------------------------
def test_v2_stream_without_step_finish_is_bound_by_the_export():
    events, export = v2_fixture("Hello V2")
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    result = _run(OpenCodeCliProvider(_config(), runner=runner), _payload())

    assert result["choices"][0]["message"]["content"] == "Hello V2"
    assert result["_provider"]["stream_format"] == "v2"
    assert result["_provider"]["finish"] == "stop"
    run_argv = runner.runs[0]["argv"]
    assert result["_provider"]["observed_agent"] == \
        run_argv[run_argv.index("--agent") + 1]
    assert result["_provider"]["agent_preflight"]["status"] == \
        "agent_projection_verified"
    assert result["usage"]["total_tokens"] == 16


def test_v2_export_without_the_transport_agent_is_rejected():
    events, _export = v2_fixture("text")
    export = json.dumps(export_payload_v2(
        "text", agent="build")).encode()
    _error("agent_mismatch", FakeRunner(run_fixture=events,
                                        export_fixture=export))


def test_v2_export_without_an_observed_agent_is_rejected():
    events, _export = v2_fixture("text")
    payload = export_payload_v2("text")
    payload["info"].pop("agent")
    payload["messages"][2].pop("agent")
    _error("export_missing_agent",
           FakeRunner(run_fixture=events,
                      export_fixture=json.dumps(payload).encode()))


def test_v2_tool_use_event_is_denied_even_with_text():
    events = event_text_v2("partial", tool_use=True).encode()
    _, export = v2_fixture("partial")
    _error("cli_tool_use_denied",
           FakeRunner(run_fixture=events, export_fixture=export))


def test_v2_non_text_export_content_fails_closed():
    events, _export = v2_fixture("text")
    export = json.dumps(export_payload_v2(
        "text", content=[{"type": "tool", "name": "read"}])).encode()
    _error("export_non_text_content",
           FakeRunner(run_fixture=events, export_fixture=export))


def test_v2_non_stop_finish_is_rejected():
    events, _export = v2_fixture("text")
    export = json.dumps(export_payload_v2("text", finish="length")).encode()
    _error("completion_conflict",
           FakeRunner(run_fixture=events, export_fixture=export))


def test_v2_text_plus_documented_reasoning_is_separated_from_answer():
    marker = "REASONING_MARKER_NEVER_OUTPUT_71"
    events, _ = v2_fixture("Answer")
    content = [
        {"type": "reasoning", "text": marker,
         "state": {"opaque": "not interpreted"},
         "time": {"created": 1, "completed": 2}},
        {"type": "text", "text": "Answer"},
    ]
    export = json.dumps(export_payload_v2("Answer", content=content)).encode()
    result = _run(OpenCodeCliProvider(
        _config(), runner=FakeRunner(run_fixture=events,
                                     export_fixture=export)), _payload())

    assert result["choices"][0]["message"]["content"] == "Answer"
    assert result["_provider"]["observed_model"] == REQUESTED
    assert result["usage"]["total_tokens"] == 16
    assert marker not in json.dumps(result, ensure_ascii=False)


def test_v2_text_only_remains_unchanged():
    events, export = v2_fixture("plain")
    result = _run(OpenCodeCliProvider(
        _config(), runner=FakeRunner(run_fixture=events,
                                     export_fixture=export)), _payload())
    assert result["choices"][0]["message"]["content"] == "plain"


def test_v2_tool_beside_text_or_reasoning_is_still_denied():
    events, _ = v2_fixture("text")
    for content in (
        [{"type": "tool", "name": "read"}, {"type": "text", "text": "text"}],
        [{"type": "tool", "name": "read"},
         {"type": "reasoning", "text": "reason"}],
    ):
        export = json.dumps(export_payload_v2(
            "text", content=content)).encode()
        _error("export_non_text_content", FakeRunner(
            run_fixture=events, export_fixture=export))


@pytest.mark.parametrize("kind", ["file", "action", "unknown"])
def test_v2_unknown_file_and_action_parts_are_denied(kind):
    events, _ = v2_fixture("text")
    content = [{"type": kind},
               {"type": "text", "text": "text"}]
    export = json.dumps(export_payload_v2("text", content=content)).encode()
    _error("export_non_text_content", FakeRunner(
        run_fixture=events, export_fixture=export))


def test_v2_nondict_content_item_is_denied():
    events, _ = v2_fixture("text")
    export = json.dumps(export_payload_v2(
        "text", content=[{"type": "text", "text": "text"}, "nope"])).encode()
    _error("export_malformed_content", FakeRunner(
        run_fixture=events, export_fixture=export))


@pytest.mark.parametrize("content", [
    [{"type": "reasoning"}, {"type": "text", "text": "text"}],
    [{"type": "reasoning", "text": 7}, {"type": "text", "text": "text"}],
    [{"type": "text", "text": 7}],
])
def test_v2_missing_or_nonstring_text_is_denied(content):
    events, _ = v2_fixture("text")
    export = json.dumps(export_payload_v2("text", content=content)).encode()
    _error("export_malformed_content", FakeRunner(
        run_fixture=events, export_fixture=export))


@pytest.mark.parametrize("reasoning", [
    {"type": "reasoning", "text": "r", "state": "not-an-object"},
    {"type": "reasoning", "text": "r", "time": "not-an-object"},
    {"type": "reasoning", "text": "r", "time": {"completed": 2}},
    {"type": "reasoning", "text": "r", "time": {"created": "1"}},
    {"type": "reasoning", "text": "r", "time": {"created": True}},
    {"type": "reasoning", "text": "r", "time": {"created": 1, "completed": "2"}},
    {"type": "reasoning", "text": "r", "time": {"created": 1, "extra": 2}},
])
def test_v2_malformed_reasoning_state_or_time_is_denied(reasoning):
    events, _ = v2_fixture("text")
    content = [reasoning, {"type": "text", "text": "text"}]
    export = json.dumps(export_payload_v2("text", content=content)).encode()
    _error("export_malformed_content", FakeRunner(
        run_fixture=events, export_fixture=export))


def test_v2_reasoning_only_without_usable_text_is_denied():
    events, _ = v2_fixture("   ")
    content = [
        {"type": "reasoning", "text": "only reasoning"},
        {"type": "text", "text": "   "},
    ]
    export = json.dumps(export_payload_v2(
        "   ", content=content)).encode()
    # A V2 stream with no usable text has no clean terminal; the provider
    # denies it before export binding. Either way, no empty answer is returned.
    _error("unfinished_response", FakeRunner(
        run_fixture=events, export_fixture=export))


def test_unknown_agent_is_reported_without_fabricating_text():
    result = process.CommandResult(
        argv=[], exit_code=1, duration_seconds=0.1, timed_out=False,
        output_overflow=False,
        stdout=b'{"type":"error","error":{"message":"Agent not found: \\"x\\""}}',
        stderr=b"")

    class AgentRunner:
        def __call__(self, argv, **kwargs):
            if len(argv) > 1 and argv[1] == "models":
                return process.CommandResult(
                    argv=list(argv), exit_code=0, duration_seconds=0.01,
                    timed_out=False, output_overflow=False,
                    stdout=(REQUESTED + "\n").encode(), stderr=b"")
            return result

    _error("cli_agent_unavailable", AgentRunner())


def test_each_call_gets_an_isolated_transport_directory(tmp_path):
    directories = []

    class DirRunner(FakeRunner):
        def __call__(self, argv, **kwargs):
            if len(argv) > 1 and argv[1] == "run":
                directories.append(Path(kwargs["cwd"]))
            return super().__call__(argv, **kwargs)

    events, export = v2_fixture("one")
    first = DirRunner(run_fixture=events, export_fixture=export)
    _run(OpenCodeCliProvider(_config(), runner=first), _payload())
    events2, export2 = v2_fixture("two")
    second = DirRunner(run_fixture=events2, export_fixture=export2)
    _run(OpenCodeCliProvider(_config(), runner=second), _payload())

    assert len(directories) == 2 and directories[0] != directories[1]
    # The owned directory (and its config) is removed after the call.
    assert not directories[0].exists()
    assert not directories[1].exists()
    for directory in directories:
        assert not str(directory).lower().startswith(str(tmp_path).lower())


def test_concurrent_calls_do_not_share_transport_state():
    seen = []

    class SlowRunner(FakeRunner):
        def __call__(self, argv, **kwargs):
            if len(argv) > 1 and argv[1] == "run":
                seen.append((Path(kwargs["cwd"]),
                             json.loads((Path(kwargs["cwd"]) / "opencode.json")
                                        .read_text(encoding="utf-8"))["model"]))
            return super().__call__(argv, **kwargs)

    events, export = v2_fixture("a")
    runner_a = SlowRunner(run_fixture=events, export_fixture=export)
    events_b, export_b = v2_fixture("b")
    runner_b = SlowRunner(run_fixture=events_b, export_fixture=export_b)

    async def _both():
        provider_a = OpenCodeCliProvider(_config(), runner=runner_a)
        provider_b = OpenCodeCliProvider(_config(), runner=runner_b)
        return await asyncio.gather(provider_a.complete(_payload()),
                                    provider_b.complete(_payload()))

    asyncio.run(_both())
    assert len(seen) == 2
    assert seen[0][0] != seen[1][0]
    assert all(model == REQUESTED for _, model in seen)


def test_missing_agent_preflight_is_not_retried():
    state = {"starts": 0, "runs": 0}

    class NoAgentServer(FakePrivateServer):
        def start(self, cancel_event=None):
            state["starts"] += 1
            return super().start(cancel_event=cancel_event)

        def preflight(self, agent_id, workdir, alias, *, cancel_event=None):
            raise AgentProjectionError("agent_absent", retryable=True)

    events, export = v2_fixture("text")
    provider = OpenCodeCliProvider(
        _config(cli_max_attempts=3),
        runner=FakeRunner(run_fixture=events, export_fixture=export),
        server_factory=lambda *a, **k: NoAgentServer())
    with pytest.raises(ModelUnavailableError) as excinfo:
        _run(provider, _payload())
    assert excinfo.value.code == "cli_agent_preflight_failed"
    assert state == {"starts": 1, "runs": 0}


def _long_payload(marker="LONG_PROMPT_MARKER_71"):
    text = (marker + " " + "x" * 40500
            + " unicode:\u65e5\u672c\u8a9e\U0001f600"
            + " quotes:\"' backslash:\\path\\to\\file\n")
    return _payload(text)


def test_oversized_prompt_uses_exact_owned_file_and_short_argv():
    events, export = call_fixture("oversize-ok")
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    payload = _long_payload()
    expected_prompt = build_prompt(payload)
    assert len(expected_prompt) > 40000

    result = _run(OpenCodeCliProvider(
        _config(cli_max_prompt_chars=100000), runner=runner), payload)

    run = runner.runs[0]
    argv = run["argv"]
    assert "--file" in argv
    assert argv[-2] == "--file"
    assert argv[-3] == cli_runtime.PROMPT_INSTRUCTION
    assert argv[-1].endswith(cli_runtime.PROMPT_FILENAME)
    assert process.command_line_utf16_units(argv) <= \
        process.COMMAND_LINE_SAFE_UTF16_UNITS
    assert run["prompt_file_bytes"] == expected_prompt.encode("utf-8")
    assert runner.prompts[0] == expected_prompt
    assert expected_prompt not in " ".join(argv)
    assert result["_provider"]["transport"]["prompt_input"] == {
        "kind": "file", "utf8_bytes": len(expected_prompt.encode("utf-8"))}
    assert "LONG_PROMPT_MARKER_71" not in json.dumps(result, ensure_ascii=False)
    assert not Path(run["prompt_file_path"]).exists()


def test_oversized_prompt_file_is_removed_after_failure():
    events, export = call_fixture("text", tool_use=True)
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    payload = _long_payload("LONG_FAILURE_MARKER_71")

    _error("cli_tool_use_denied", runner, payload,
           _config(cli_max_prompt_chars=100000))

    run = runner.runs[0]
    assert "--file" in run["argv"]
    assert not Path(run["prompt_file_path"]).exists()


def test_oversized_prompt_file_is_removed_after_cancellation():
    captured = {}

    class BlockingRunner:
        def __call__(self, argv, *, cwd, timeout, env, max_output_bytes,
                     cancel_event=None):
            if "--file" in argv:
                captured["prompt_path"] = argv[argv.index("--file") + 1]
            while not cancel_event.is_set():
                time.sleep(0.01)
            return process.CommandResult(
                argv=list(argv), exit_code=-1, duration_seconds=0.1,
                timed_out=False, output_overflow=False, stdout=b"",
                stderr=b"", cancelled=True)

    provider = OpenCodeCliProvider(
        _config(cli_max_prompt_chars=100000), runner=BlockingRunner())

    async def _run_and_cancel():
        task = asyncio.create_task(provider.complete(_long_payload(
            "LONG_CANCEL_MARKER_71")))
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return

    asyncio.run(_run_and_cancel())
    assert captured["prompt_path"]
    assert not Path(captured["prompt_path"]).exists()


def test_prompt_file_failure_is_a_constant_without_prompt_echo(monkeypatch):
    events, export = call_fixture("never-used")
    runner = FakeRunner(run_fixture=events, export_fixture=export)

    def fail(_paths, _prompt):
        raise cli_runtime.PromptFileError("cli_prompt_file_unavailable")

    monkeypatch.setattr(cli_runtime, "write_prompt_file", fail)
    exc = _error("cli_prompt_file_unavailable", runner, _long_payload(
        "PROMPT_ECHO_CANARY_71"), _config(cli_max_prompt_chars=100000))

    assert "PROMPT_ECHO_CANARY_71" not in str(exc)
    assert runner.runs == []
