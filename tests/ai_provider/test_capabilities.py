"""T051: flag capability negotiation, usage mapping and fail-closed behavior.

The installed CLI (v2.0.32) advertises no ``--pure`` flag in ``run --help``, so
the adapter must not send it. These tests use the verbatim observed help text
and a fake probe runner: no real CLI process and no model call is involved.
"""

import asyncio
import json

import pytest
from domains.providers import (ModelUnavailableError, OpenCodeCliProvider,
                               ProviderConfig, openai_usage,
                               probe_cli_capabilities, reset_capability_cache)
from domains.providers import process

from helpers_provider import (CLI_VERSION_TEXT, HELP_EXPORT_NO_SERVER,
                              HELP_RUN_NO_PURE, HELP_RUN_NO_SERVER,
                              HELP_RUN_WITH_PURE, FakeHelpRunner, FakeRunner,
                              call_fixture, python_executable)

REQUESTED = "aibox/ds/deepseek-flash"


def _config(**overrides):
    values = {
        "provider": "opencode_cli",
        "model": REQUESTED,
        "cli_executable": python_executable(),
        "cli_agent": "t051-test-agent",
        "cli_timeout_seconds": 5.0,
        "cli_max_prompt_chars": 50_000,
        "cli_max_attempts": 1,
        "cli_max_concurrency": 1,
        "cli_pure": True,
    }
    values.update(overrides)
    return ProviderConfig(**values)


def _payload():
    return {"model": REQUESTED,
            "messages": [{"role": "system", "content": "sys"},
                         {"role": "user", "content": "hello"}]}


def _run(provider, payload=None):
    return asyncio.run(provider.complete(payload or _payload()))


def _provider(runner, *, capability_runner, config=None):
    return OpenCodeCliProvider(config or _config(), runner=runner,
                               capability_runner=capability_runner)


def _fixtures(text="Hello there", tokens=None):
    return call_fixture(text, tokens=tokens,
                        export_kwargs={"agent": "t051-test-agent"})


# ---------------------------------------------------------------------------
# Capability negotiation for --pure (absent in the installed CLI)
# ---------------------------------------------------------------------------
def test_pure_request_fails_closed_when_the_cli_does_not_advertise_it():
    events, export = _fixtures()
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    probe = FakeHelpRunner(HELP_RUN_NO_PURE)

    with pytest.raises(ModelUnavailableError) as excinfo:
        _run(_provider(runner, capability_runner=probe))

    # Omission would silently drop the requested plugin isolation.
    assert excinfo.value.code == "cli_pure_unsupported"
    assert runner.runs == []
    assert probe.help_probes[0][1:] == ["run", "--help"]
    assert all("do not shell" not in part for call in probe.calls for part in call)


def test_explicit_opt_out_discloses_that_plugin_isolation_is_unavailable():
    events, export = _fixtures()
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    probe = FakeHelpRunner(HELP_RUN_NO_PURE)

    result = _run(_provider(runner, capability_runner=probe,
                            config=_config(cli_pure=False)))

    argv = runner.runs[0]["argv"]
    assert "--pure" not in argv
    assert argv[2] == "--server"
    capabilities = result["_provider"]["cli_capabilities"]
    assert capabilities["version"] == CLI_VERSION_TEXT
    assert capabilities["capability_source"] == "help_probe"
    assert capabilities["pure_supported"] is False
    assert capabilities["pure_requested"] is False
    assert capabilities["pure_applied"] is False
    assert capabilities["plugin_isolation"] == "not_requested"
    assert capabilities["reason"] == "unsupported"
    assert result["choices"][0]["message"]["content"] == "Hello there"


def test_pure_is_applied_when_the_cli_advertises_it():
    events, export = _fixtures()
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    probe = FakeHelpRunner(HELP_RUN_WITH_PURE)

    result = _run(_provider(runner, capability_runner=probe))

    argv = runner.runs[0]["argv"]
    assert argv[2] == "--pure"
    capabilities = result["_provider"]["cli_capabilities"]
    assert capabilities["pure_supported"] is True
    assert capabilities["pure_applied"] is True
    assert capabilities["plugin_isolation"] == "applied"
    assert capabilities["reason"] == "supported"


def test_capability_probe_runs_once_per_process():
    events, export = _fixtures()
    probe = FakeHelpRunner(HELP_RUN_NO_PURE)

    def once():
        runner = FakeRunner(run_fixture=events, export_fixture=export)
        _run(_provider(runner, capability_runner=probe,
                       config=_config(cli_pure=False)))
        return runner

    first, second = once(), once()
    assert len(probe.help_probes) == 2          # run help + session export help
    assert len(probe.export_help_probes) == 1
    assert len(probe.version_probes) == 1
    assert len(first.runs) == 1 and len(second.runs) == 1


def test_probe_failure_never_permits_a_run_and_is_disclosed():
    events, export = _fixtures()
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    probe = FakeHelpRunner(fail=True)

    with pytest.raises(ModelUnavailableError) as excinfo:
        _run(_provider(runner, capability_runner=probe,
                       config=_config(cli_pure=False)))

    # No readable help => the V2 standalone route is unproven => fail closed.
    assert excinfo.value.code == "cli_runtime_unsupported"
    assert runner.runs == []
    assert probe.version_probes[0][0] == python_executable()


def test_unreadable_help_is_not_treated_as_support():
    # A non-zero help exit means the text cannot be trusted, even if it prints
    # the flag name.
    events, export = _fixtures()
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    probe = FakeHelpRunner(HELP_RUN_WITH_PURE, help_exit=1)

    with pytest.raises(ModelUnavailableError) as excinfo:
        _run(_provider(runner, capability_runner=probe))

    assert excinfo.value.code == "cli_runtime_unsupported"
    assert runner.runs == []


def test_missing_server_export_support_fails_closed():
    events, export = _fixtures()
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    probe = FakeHelpRunner(HELP_RUN_NO_PURE,
                           export_help_text=HELP_EXPORT_NO_SERVER)

    with pytest.raises(ModelUnavailableError) as excinfo:
        _run(_provider(runner, capability_runner=probe,
                       config=_config(cli_pure=False)))

    assert excinfo.value.code == "cli_runtime_unsupported"
    assert runner.runs == []


def test_missing_server_run_support_fails_closed():
    events, export = _fixtures()
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    probe = FakeHelpRunner(HELP_RUN_NO_SERVER)

    with pytest.raises(ModelUnavailableError) as excinfo:
        _run(_provider(runner, capability_runner=probe,
                       config=_config(cli_pure=False)))

    assert excinfo.value.code == "cli_runtime_unsupported"
    assert runner.runs == []


def test_pure_disabled_still_probes_the_runtime_flags():
    events, export = _fixtures()
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    probe = FakeHelpRunner(HELP_RUN_WITH_PURE)

    result = _run(_provider(runner, capability_runner=probe,
                            config=_config(cli_pure=False)))

    assert len(probe.version_probes) == 1
    assert "--pure" not in runner.runs[0]["argv"]
    capabilities = result["_provider"]["cli_capabilities"]
    assert capabilities["capability_source"] == "help_probe"
    assert capabilities["pure_requested"] is False
    assert capabilities["standalone"] is True
    assert capabilities["session_export"] is True
    assert capabilities["standalone_export"] is True


def test_omitting_pure_does_not_relax_tool_denial():
    events, export = _fixtures()
    runner = FakeRunner(run_fixture=events, export_fixture=export)

    _run(_provider(runner, capability_runner=FakeHelpRunner(HELP_RUN_NO_PURE),
                   config=_config(cli_pure=False)))

    config = json.loads(runner.runs[0]["transport_config"])
    agent_id = next(iter(config["agents"]))
    assert agent_id.startswith("t051-test-agent-")
    agent = config["agents"][agent_id]
    assert {"action": "*", "resource": "*", "effect": "deny"} in agent["permissions"]
    assert agent["mode"] == "primary"
    assert agent["steps"] == 2


def test_probe_helper_reports_capabilities_without_a_provider():
    probe = FakeHelpRunner(HELP_RUN_NO_PURE)
    config = _config()
    result = probe_cli_capabilities(python_executable(), config, runner=probe)
    assert result.supports_pure is False
    assert result.source == "help_probe"
    assert result.version == CLI_VERSION_TEXT
    assert result.runtime_ready is True

    reset_capability_cache()
    supported = probe_cli_capabilities(python_executable(), config,
                                       runner=FakeHelpRunner(HELP_RUN_WITH_PURE))
    assert supported.supports_pure is True
    assert supported.reason == "supported"


def test_probe_is_bounded_and_shell_free():
    """The probe passes an argument array, a bounded timeout and no prompt."""
    calls = []

    class Recorder:
        def __call__(self, argv, *, cwd, timeout, env, max_output_bytes,
                     cancel_event=None):
            calls.append({"argv": [str(part) for part in argv],
                          "timeout": timeout,
                          "max_output_bytes": max_output_bytes})
            return process.CommandResult(argv=list(argv), exit_code=0,
                                         duration_seconds=0.0, timed_out=False,
                                         output_overflow=False,
                                         stdout=HELP_RUN_NO_PURE.encode(),
                                         stderr=b"")

    probe_cli_capabilities(python_executable(), _config(), runner=Recorder())
    assert calls[0]["argv"] == [python_executable(), "--version"]
    assert calls[1]["argv"] == [python_executable(), "run", "--help"]
    assert calls[2]["argv"] == [
        python_executable(), "session", "export", "--help"]
    assert all(0 < call["timeout"] <= 60 for call in calls)
    assert all(0 < call["max_output_bytes"] <= 1_000_000 for call in calls)


# ---------------------------------------------------------------------------
# Usage mapping: reasoning/cache components, no double counting
# ---------------------------------------------------------------------------
S01_TOKENS = {"input": 397, "output": 129, "reasoning": 926,
              "cache": {"read": 512}, "total": 1964}


def test_usage_maps_the_s01_components_without_double_counting():
    usage = openai_usage({"input": 397, "output": 129, "reasoning": 926,
                          "cache_read": 512, "cache_write": None,
                          "total": 1964})
    assert usage["prompt_tokens"] == 909
    assert usage["completion_tokens"] == 1055
    assert usage["total_tokens"] == 1964
    assert usage["prompt_tokens"] + usage["completion_tokens"] == 1964
    assert usage["usage_consistent"] is True
    assert usage["prompt_tokens_details"] == {"cached_tokens": 512}
    assert usage["completion_tokens_details"] == {"reasoning_tokens": 926}
    # Raw observed values stay visible; nothing is recomputed away.
    assert usage["provider_components"] == {
        "input": 397, "output": 129, "reasoning": 926,
        "cache_read": 512, "cache_write": None, "total": 1964}


def test_usage_through_the_adapter_reports_all_components():
    events, export = _fixtures(tokens=S01_TOKENS)
    runner = FakeRunner(run_fixture=events, export_fixture=export)
    result = _run(_provider(runner, capability_runner=FakeHelpRunner(),
                            config=_config(cli_pure=False)))

    usage = result["usage"]
    assert usage["prompt_tokens"] == 909
    assert usage["completion_tokens"] == 1055
    assert usage["total_tokens"] == 1964
    assert usage["usage_consistent"] is True
    assert usage["provider_components"]["cache_read"] == 512
    assert result["_provider"]["usage_consistent"] is True


def test_absent_components_are_zero_in_sums_but_stay_disclosed():
    usage = openai_usage({"input": 10, "output": 2, "total": 12})
    assert usage["prompt_tokens"] == 10
    assert usage["completion_tokens"] == 2
    assert usage["usage_consistent"] is True
    assert "prompt_tokens_details" not in usage
    assert "completion_tokens_details" not in usage
    assert usage["provider_components"]["reasoning"] is None
    assert usage["provider_components"]["cache_read"] is None


def test_unknown_input_is_not_invented():
    usage = openai_usage({"output": 5, "reasoning": 1, "cache_read": 7})
    assert usage["prompt_tokens"] is None      # cannot know input
    assert usage["completion_tokens"] == 6
    assert usage["total_tokens"] is None
    assert usage["usage_consistent"] is None


def test_total_mismatch_is_observable_and_not_corrected():
    usage = openai_usage({"input": 10, "output": 2, "reasoning": 3,
                          "cache_read": 1, "cache_write": 0, "total": 999})
    assert usage["usage_consistent"] is False
    assert usage["total_tokens"] == 999        # preserved verbatim


@pytest.mark.parametrize("components", [
    {"input": -1},
    {"input": True},
    {"output": 1.5},
    {"total": "16"},
])
def test_invalid_usage_components_are_an_observable_error(components):
    with pytest.raises(ModelUnavailableError) as excinfo:
        openai_usage(components)
    assert excinfo.value.code == "invalid_usage"


# ---------------------------------------------------------------------------
# No silent fallback: malformed/absent transport is an error, not a response
# ---------------------------------------------------------------------------
def test_malformed_stream_raises_instead_of_returning_text():
    runner = FakeRunner(run_fixture=b"{not json\n", export_fixture=b"{}")
    provider = _provider(runner, capability_runner=FakeHelpRunner(),
                         config=_config(cli_pure=False))
    with pytest.raises(ModelUnavailableError) as excinfo:
        _run(provider)
    assert excinfo.value.code == "cli_malformed_stream"
    assert excinfo.value.attempts == 1


def test_missing_cli_cannot_produce_a_fabricated_response(tmp_path):
    missing = str(tmp_path / "definitely-missing-cli")
    runner = FakeRunner()
    probe = FakeHelpRunner()
    provider = _provider(runner, capability_runner=probe,
                         config=_config(cli_executable=missing))

    with pytest.raises(ModelUnavailableError) as excinfo:
        _run(provider)

    assert excinfo.value.code == "cli_not_found"
    assert runner.calls == []
    assert probe.calls == []
