"""SEC-066: service-only secrets never reach the CLI child environment."""

from unittest.mock import patch

from domains.providers import cli_runtime

SERVICE_KEYS = (
    "TYPESAFE_API_TOKEN",
    "TYPESAFE_API_KEY",
    "GEMINI_API_KEY",
    "JWT_SECRET",
    "JWT_ALGORITHM",
    "MEMORY_DB_PATH",
    "MEMGRAPH_PASSWORD",
    "NGROK_AUTHTOKEN",
)


def _service_env():
    return {key: "SYNTHETIC_" + key + "_VALUE" for key in SERVICE_KEYS}


def test_service_keys_are_stripped_from_an_explicit_base():
    base = _service_env()
    base["OPENCODE_GO_API_KEY"] = "SYNTHETIC_PROVIDER_CREDENTIAL"

    child = cli_runtime.child_environment(None, base=base)

    assert all(key not in child for key in SERVICE_KEYS)


def test_explicit_base_is_not_mutated_and_plain_fields_survive():
    base = _service_env()
    base["PATH"] = "/synthetic/bin"
    before = dict(base)

    child = cli_runtime.child_environment(None, base=base)

    assert base == before
    assert child["PATH"] == "/synthetic/bin"


def test_provider_owned_credential_is_preserved():
    base = {"OPENCODE_GO_API_KEY": "SYNTHETIC_PROVIDER_CREDENTIAL"}

    child = cli_runtime.child_environment(None, base=base)

    assert child["OPENCODE_GO_API_KEY"] == base["OPENCODE_GO_API_KEY"]


def test_ambient_carriers_are_preserved_and_detected():
    base = {
        "OPENCODE_CONFIG_CONTENT": "SYNTHETIC_INLINE_GUARD",
        "OPENCODE_CONFIG": "SYNTHETIC_CONFIG_PATH",
    }

    child = cli_runtime.child_environment(None, base=base)

    assert child == base
    assert cli_runtime.ambient_config_carriers(child) == (
        "OPENCODE_CONFIG_CONTENT", "OPENCODE_CONFIG")


def test_default_environment_branch_uses_a_private_copy():
    ambient = _service_env()
    ambient["PATH"] = "/synthetic/bin"
    with patch.dict(cli_runtime.os.environ, ambient, clear=True):
        before = dict(cli_runtime.os.environ)
        child = cli_runtime.child_environment(None)
        assert dict(cli_runtime.os.environ) == before

    assert all(key not in child for key in SERVICE_KEYS)
    assert child["PATH"] == "/synthetic/bin"
