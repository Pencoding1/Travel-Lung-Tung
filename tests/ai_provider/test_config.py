"""Explicit provider selection/config validation (no I/O)."""

import pytest
from domains.providers import (DEFAULT_CLI_MODEL, PROVIDER_GEMINI,
                               PROVIDER_OPENCODE_CLI, ProviderConfigError,
                               load_provider_config)


def test_default_is_gemini_and_unchanged():
    config = load_provider_config({})
    assert config.provider == PROVIDER_GEMINI
    assert config.model == "gemini-2.5-pro"
    assert not config.is_cli


def test_cli_requires_explicit_selection_and_defaults_exact_alias():
    config = load_provider_config({"AI_LLM_PROVIDER": "opencode_cli"})
    assert config.provider == PROVIDER_OPENCODE_CLI
    assert config.model == DEFAULT_CLI_MODEL == "aibox/ds/deepseek-flash"
    assert config.cli_pure is True
    assert config.cli_max_attempts == 1
    assert config.evidence_dir is None


def test_cli_options_are_validated_and_parsed(tmp_path):
    evidence = tmp_path / "evidence"
    env = {
        "AI_LLM_PROVIDER": "opencode_cli",
        "AI_CLI_MODEL": "aibox/ds/deepseek-flash",
        "AI_CLI_EXECUTABLE": "opencode.exe",
        "AI_CLI_AGENT": "oc040-transport",
        "AI_CLI_TIMEOUT_SECONDS": "30",
        "AI_CLI_MAX_OUTPUT_BYTES": "4096",
        "AI_CLI_MAX_PROMPT_CHARS": "5000",
        "AI_CLI_MAX_ATTEMPTS": "2",
        "AI_CLI_MAX_CONCURRENCY": "1",
        "AI_CLI_PURE": "false",
        "AI_CLI_EVIDENCE_DIR": str(evidence),
    }
    config = load_provider_config(env)
    assert config.cli_executable == "opencode.exe"
    assert config.cli_agent == "oc040-transport"
    assert config.cli_timeout_seconds == 30
    assert config.cli_max_output_bytes == 4096
    assert config.cli_max_prompt_chars == 5000
    assert config.cli_max_attempts == 2
    assert config.cli_max_concurrency == 1
    assert config.cli_pure is False
    assert config.evidence_dir == evidence


def test_empty_optional_cli_values_are_absent():
    config = load_provider_config({
        "AI_LLM_PROVIDER": "opencode_cli",
        "AI_CLI_EXECUTABLE": "   ",
        "AI_CLI_EVIDENCE_DIR": "",
    })
    assert config.cli_executable is None
    assert config.evidence_dir is None


@pytest.mark.parametrize("env", [
    {"AI_LLM_PROVIDER": "bogus"},
    {"AI_LLM_PROVIDER": ""},
    {"AI_LLM_PROVIDER": "gemini", "GEMINI_MODEL": "has space"},
    {"AI_LLM_PROVIDER": "opencode_cli", "AI_CLI_MODEL": "not a model"},
    {"AI_LLM_PROVIDER": "opencode_cli", "AI_CLI_TIMEOUT_SECONDS": "0"},
    {"AI_LLM_PROVIDER": "opencode_cli", "AI_CLI_TIMEOUT_SECONDS": "nan"},
    {"AI_LLM_PROVIDER": "opencode_cli", "AI_CLI_MAX_ATTEMPTS": "9"},
    {"AI_LLM_PROVIDER": "opencode_cli", "AI_CLI_PURE": "maybe"},
    {"AI_LLM_PROVIDER": "opencode_cli", "AI_CLI_AGENT": "bad agent"},
])
def test_invalid_configuration_is_rejected(env):
    with pytest.raises(ProviderConfigError) as excinfo:
        load_provider_config(env)
    assert excinfo.value.code == "invalid_provider_config"


def test_config_does_not_mutate_the_supplied_mapping():
    env = {"AI_LLM_PROVIDER": "opencode_cli"}
    before = dict(env)
    load_provider_config(env)
    assert env == before
