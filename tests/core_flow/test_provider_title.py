"""Fixed CLI transport title and provider environment contract.

The title is a literal: it never carries the prompt, user text, a selector or a
credential. Ambient guard carriers survive; service secrets do not.
"""

from types import SimpleNamespace

from domains.providers import cli_runtime


def _config(**overrides):
    values = {
        "model": "openai/gpt-5",
        "cli_agent": "travel-planner",
        "cli_pure": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_run_argv_places_the_literal_title_before_the_prompt():
    prompt = "MESSAGE_MARKER_4T2: gợi ý quán"
    argv = cli_runtime.build_run_argv("C:/cli/opencode.exe", _config(), prompt)

    assert argv[-1] == prompt
    assert argv[-2] == cli_runtime.SESSION_TITLE
    assert argv[-3] == "--title"
    assert cli_runtime.SESSION_TITLE == "Travel Lung Tung text transport"
    assert "MESSAGE_MARKER_4T2" not in cli_runtime.SESSION_TITLE
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "openai/gpt-5"
    assert argv[argv.index("--agent") + 1] == "travel-planner"


def test_title_is_independent_of_the_prompt():
    first = cli_runtime.build_run_argv("cli", _config(), "prompt one")
    second = cli_runtime.build_run_argv("cli", _config(), "prompt two")
    assert first[first.index("--title") + 1] == second[second.index("--title") + 1]


def test_unsupported_pure_is_not_emitted_and_default_stays_failclosed():
    argv = cli_runtime.build_run_argv(
        "cli", _config(cli_pure=True), "prompt", cli_supports_pure=False)
    assert "--pure" not in argv
    assert cli_runtime.build_run_argv(
        "cli", _config(cli_pure=True), "prompt", cli_supports_pure=True
    ).count("--pure") == 1


def test_advertised_title_flag_is_only_reported_when_present():
    assert "--title" in cli_runtime.advertised_flags("run --title <title>")
    assert "--title" not in cli_runtime.advertised_flags("run --model <id>")
    assert cli_runtime.advertised_flags(None) == ()


def test_guard_carriers_survive_but_service_secrets_do_not():
    base = {
        "OPENCODE_CONFIG_CONTENT": "",
        "OPENCODE_CONFIG": "synthetic-carrier",
        "TYPESAFE_API_KEY": "synthetic-secret",
        "TYPESAFE_API_TOKEN": "synthetic-secret",
        "PATH": "/usr/bin",
    }
    env = cli_runtime.child_environment(_config(), base=base)

    assert env["OPENCODE_CONFIG_CONTENT"] == ""
    assert env["OPENCODE_CONFIG"] == "synthetic-carrier"
    assert "TYPESAFE_API_KEY" not in env
    assert "TYPESAFE_API_TOKEN" not in env
    assert env["PATH"] == "/usr/bin"


def test_carrier_probe_reports_names_only():
    base = {"OPENCODE_CONFIG_CONTENT": "synthetic", "OPENCODE_CONFIG": "   "}
    assert cli_runtime.ambient_config_carriers(base) == (
        "OPENCODE_CONFIG_CONTENT",)
