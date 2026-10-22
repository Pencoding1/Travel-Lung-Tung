"""Exact OpenCode Go binding and narrow credential loader.

These are synthetic tests: the only key values are literals created here and
never the project credential. No network, real CLI or real ``.env`` is read.
"""

import asyncio
import json
from pathlib import Path

import pytest
from domains.providers import (ModelUnavailableError, OpenCodeCliProvider,
                               ProviderConfig, cli_runtime, go_credentials,
                               opencode_cli)

from helpers_provider import FakeRunner, python_executable, v2_fixture


def _go_config(**overrides):
    values = dict(
        provider="opencode_cli",
        model=go_credentials.GO_ALIAS,
        cli_executable=python_executable(),
        cli_agent="go-qa-agent",
        cli_pure=False,
        cli_timeout_seconds=5,
        cli_max_attempts=1,
    )
    values.update(overrides)
    return ProviderConfig(**values)


def _go_payload():
    return {
        "model": go_credentials.GO_ALIAS,
        "messages": [{"role": "user", "content": "synthetic"}],
    }


def _go_fixture():
    events, export = v2_fixture(
        "Go answer", model=go_credentials.GO_MODEL_ID,
        provider=go_credentials.GO_PROVIDER_ID)
    return FakeRunner(run_fixture=events, export_fixture=export)


def _run(provider):
    return asyncio.run(provider.complete(_go_payload()))


def test_exact_go_config_has_env_reference_not_a_value(tmp_path):
    config = _go_config()
    paths = cli_runtime.create_transport(config, base_dir=tmp_path)
    document = json.loads(paths.config.read_text(encoding="utf-8"))

    assert document["providers"] == {
        go_credentials.GO_PROVIDER_ID: {
            "settings": {"apiKey": go_credentials.GO_KEY_REF},
        }
    }
    assert "synthetic" not in paths.config.read_text(encoding="utf-8")
    proof = cli_runtime.validate_transport_config(paths, config)
    assert proof["status"] == "generated_config_validated"


def test_go_config_keeps_model_scoped_controls():
    config = _go_config()
    document = cli_runtime.transport_config(
        config, {"temperature": 0.2, "top_p": 0.9})

    assert document["providers"] == {
        go_credentials.GO_PROVIDER_ID: {
            "settings": {"apiKey": go_credentials.GO_KEY_REF},
            "models": {
                go_credentials.GO_MODEL_ID: {
                    "body": {"temperature": 0.2, "top_p": 0.9},
                }
            },
        }
    }


@pytest.mark.parametrize("mutation", [
    lambda provider: provider["settings"].__setitem__(
        "apiKey", "sk-synthetic-literal"),
    lambda provider: provider.__setitem__(
        "headers", {"Authorization": "synthetic"}),
    lambda provider: provider.__setitem__("baseURL", "https://synthetic.invalid"),
    lambda provider: provider["models"][go_credentials.GO_MODEL_ID].__setitem__(
        "body", {"temperature": 9}),
])
def test_unexpected_go_overlay_is_refused(tmp_path, mutation):
    config = _go_config()
    paths = cli_runtime.create_transport(
        config, {"temperature": 0.2}, base_dir=tmp_path)
    document = json.loads(paths.config.read_text(encoding="utf-8"))
    mutation(document["providers"][go_credentials.GO_PROVIDER_ID])
    paths.config.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(cli_runtime.TransportConfigError) as excinfo:
        cli_runtime.validate_transport_config(
            paths, config, {"temperature": 0.2})
    assert excinfo.value.code == "transport_go_binding_mismatch"


def test_process_credential_takes_priority_and_stays_in_child_only(
        monkeypatch, tmp_path):
    synthetic = "sk-synthetic-go-process"
    monkeypatch.setenv(go_credentials.GO_ENV_VAR, synthetic)
    config = _go_config()
    runner = _go_fixture()

    result = _run(OpenCodeCliProvider(config, runner=runner))

    assert runner.runs[0]["env"][go_credentials.GO_ENV_VAR] == synthetic
    assert synthetic not in json.dumps(result, ensure_ascii=False)
    assert synthetic not in runner.runs[0]["transport_config"]
    assert synthetic not in json.dumps(runner.runs[0]["argv"])
    assert synthetic not in repr(config)
    assert result["_provider"]["observed_model"] == go_credentials.GO_ALIAS
    assert result["_provider"]["requested_model"] == go_credentials.GO_ALIAS


def test_explicit_blank_or_invalid_process_value_never_uses_the_file(
        monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENCODE_API=sk-synthetic-file\n", encoding="utf-8")
    for value in ("", " ", "\t", "bad\nvalue", "bad\x00value", 123):
        with pytest.raises(go_credentials.GoCredentialError) as excinfo:
            go_credentials.load_go_api_key(
                {go_credentials.GO_ENV_VAR: value}, project_root=tmp_path)
        assert excinfo.value.code == "go_credential_invalid"


def test_file_fallback_is_bounded_utf8_and_independent_of_cwd(
        monkeypatch, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env").write_text(
        "OTHER=synthetic\nOPENCODE_API=sk-synthetic-file\n", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.delenv(go_credentials.GO_ENV_VAR, raising=False)
    monkeypatch.chdir(elsewhere)

    value = go_credentials.load_go_api_key(project_root=project)

    assert value == "sk-synthetic-file"


def test_file_value_is_literal_not_interpolated(tmp_path):
    path = tmp_path / ".env"
    path.write_text("OPENCODE_API=prefix-${OTHER}-$HOME\n", encoding="utf-8")
    assert go_credentials.load_go_api_key_file(path) == (
        "prefix-${OTHER}-$HOME")


@pytest.mark.parametrize("content,code", [
    ("", "go_credential_missing"),
    ("OTHER=synthetic\n", "go_credential_missing"),
    ("OPENCODE_API\n", "go_credential_file_malformed"),
    ("OPENCODE_API=one\nOPENCODE_API=two\n", "go_credential_file_malformed"),
    ("OPENCODE_API=bad\x00value\n", "go_credential_file_malformed"),
    ("OPENCODE_API=bad\n", None),
])
def test_malformed_or_missing_file_fails_with_a_constant(tmp_path, content,
                                                         code):
    path = tmp_path / ".env"
    path.write_text(content, encoding="utf-8")
    if code is None:
        assert go_credentials.load_go_api_key_file(path) == "bad"
        return
    with pytest.raises(go_credentials.GoCredentialError) as excinfo:
        go_credentials.load_go_api_key_file(path)
    assert excinfo.value.code == code
    assert "sk-" not in str(excinfo.value)


def test_oversized_file_fails_before_value_parsing(tmp_path):
    path = tmp_path / ".env"
    path.write_text("OPENCODE_API=" + "A" * (
        go_credentials.MAX_ENV_BYTES + 1), encoding="utf-8")
    with pytest.raises(go_credentials.GoCredentialError) as excinfo:
        go_credentials.load_go_api_key_file(path)
    assert excinfo.value.code == "go_credential_file_too_large"


def test_ai_box_child_does_not_receive_the_go_credential():
    config = ProviderConfig(provider="opencode_cli", model="aibox/ds/deepseek-flash",
                            cli_agent="qa")
    env = opencode_cli.child_environment(
        config, base={go_credentials.GO_ENV_VAR: "sk-synthetic-only-go"})
    assert go_credentials.GO_ENV_VAR not in env


def test_missing_go_credential_fails_before_any_runner_without_echo(
        monkeypatch, tmp_path):
    monkeypatch.delenv(go_credentials.GO_ENV_VAR, raising=False)
    # Point the production fallback at an empty temporary project so this test
    # cannot read the real project credential.
    monkeypatch.setattr(go_credentials, "PROJECT_ROOT", tmp_path)
    runner = _go_fixture()
    with pytest.raises(ModelUnavailableError) as excinfo:
        _run(OpenCodeCliProvider(_go_config(), runner=runner))
    assert excinfo.value.code == "go_credential_missing"
    assert runner.runs == []
    assert "sk-" not in str(excinfo.value)
