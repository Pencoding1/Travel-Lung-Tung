"""Process-only POI settings and configurable MCP listen address.

The explicit factory must never open the class-level ``.env``; the default
constructor keeps its previous operator behaviour. No value is printed.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_settings import SettingsConfigDict

from app.core.config import settings as poi_settings

MEMGRAPH_FIELDS = ("MEMGRAPH_HOST", "MEMGRAPH_PORT",
                   "MEMGRAPH_USER", "MEMGRAPH_PASSWORD")


def test_explicit_process_only_settings_do_not_read_the_env_file(tmp_path,
                                                                monkeypatch):
    env_file = tmp_path / "synthetic.env"
    env_file.write_text(
        "MEMGRAPH_HOST=synthetic-file-host\n"
        "MEMGRAPH_PORT=7687\n"
        "MEMGRAPH_USER=synthetic-file-user\n"
        "MEMGRAPH_PASSWORD=synthetic-file-pass\n",
        encoding="utf-8",
    )

    class HermeticMemgraph(poi_settings.MemgraphDB):
        model_config = SettingsConfigDict(
            env_file=str(env_file), env_file_encoding="utf-8", extra="ignore")

    # File-only values are invisible to the process-only factory.
    for key in MEMGRAPH_FIELDS:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValidationError):
        HermeticMemgraph.from_process_env()

    # The same class still reads an explicitly supplied file: the test proves
    # absence of the class-level file source, not a broken settings model.
    from_file = HermeticMemgraph(_env_file=str(env_file))
    assert from_file.MEMGRAPH_HOST == "synthetic-file-host"


def test_explicit_process_only_settings_use_process_values(monkeypatch):
    monkeypatch.setenv("MEMGRAPH_HOST", "127.0.0.1")
    monkeypatch.setenv("MEMGRAPH_PORT", "17687")
    monkeypatch.setenv("MEMGRAPH_USER", "synthetic-user")
    monkeypatch.setenv("MEMGRAPH_PASSWORD", "synthetic-pass")

    configured = poi_settings.MemgraphDB.from_process_env()
    assert configured.MEMGRAPH_HOST == "127.0.0.1"
    assert configured.MEMGRAPH_PORT == 17687
    assert configured.memgraph_uri == "bolt://127.0.0.1:17687"


def test_default_settings_behaviour_is_unchanged():
    default = poi_settings.MemgraphDB()
    assert isinstance(default.MEMGRAPH_HOST, str) and default.MEMGRAPH_HOST
    assert 1 <= default.MEMGRAPH_PORT <= 65535


def test_selector_absent_or_explicit_legacy_uses_legacy_factory():
    calls = []

    def legacy():
        calls.append("legacy")
        return "legacy"

    def process():
        calls.append("process")
        return "process"

    assert poi_settings.select_db_settings(None, process, legacy) == "legacy"
    assert poi_settings.select_db_settings(
        "", process, legacy) == "legacy"
    assert poi_settings.select_db_settings(
        "legacy_env_file", process, legacy) == "legacy"
    assert calls == ["legacy", "legacy", "legacy"]


def test_selector_process_only_does_not_call_legacy_factory():
    calls = []

    def legacy():
        calls.append("legacy")
        return "legacy"

    def process():
        calls.append("process")
        return "process"

    assert poi_settings.select_db_settings(
        "process_only", process, legacy) == "process"
    assert calls == ["process"]


def test_selector_invalid_fails_before_either_factory():
    calls = []

    def legacy():
        calls.append("legacy")
        return "legacy"

    def process():
        calls.append("process")
        return "process"

    with pytest.raises(ValueError) as raised:
        poi_settings.select_db_settings("synthetic-invalid", process, legacy)
    assert str(raised.value) == "invalid_db_settings_source"
    assert calls == []


def _settings_subprocess_env(**extra):
    env = {
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONIOENCODING": "utf-8",
    }
    env.update(extra)
    return env


def test_invalid_selector_fails_at_module_initialization_before_file_load():
    repo_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [sys.executable, "-c", "from app.core.config import settings"],
        cwd=str(repo_root / "POI_service"),
        env=_settings_subprocess_env(POI_DB_SETTINGS_SOURCE="synthetic-invalid"),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, timeout=30, check=False)
    assert completed.returncode != 0
    assert "invalid_db_settings_source" in completed.stderr


def test_process_only_module_initialization_uses_process_values():
    repo_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [sys.executable, "-c",
         "import json; from app.core.config import settings; "
         "print(json.dumps({'host': settings.db_settings.MEMGRAPH_HOST, "
         "'port': settings.db_settings.MEMGRAPH_PORT, "
         "'uri': settings.db_settings.memgraph_uri}))"],
        cwd=str(repo_root / "POI_service"),
        env=_settings_subprocess_env(
            POI_DB_SETTINGS_SOURCE="process_only",
            MEMGRAPH_HOST="127.0.0.1",
            MEMGRAPH_PORT="19999",
            MEMGRAPH_USER="",
            MEMGRAPH_PASSWORD="",
        ),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, timeout=30, check=False)
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["host"] == "127.0.0.1"
    assert payload["port"] == 19999
    assert payload["uri"] == "bolt://127.0.0.1:19999"


def test_mcp_listen_port_is_env_driven(monkeypatch):
    from app.api.mcp import tools

    monkeypatch.setenv("MCP_PORT", "19101")
    assert tools._listen_port() == 19101
    assert tools.DEFAULT_MCP_PORT == 8001
    assert tools.DEFAULT_MCP_HOST == "0.0.0.0"
    assert tools.MCP_HOST_ENV == "MCP_HOST"

    monkeypatch.setenv("MCP_PORT", "not-a-port")
    with pytest.raises(ValueError):
        tools._listen_port()
    monkeypatch.setenv("MCP_PORT", "70000")
    with pytest.raises(ValueError):
        tools._listen_port()
    monkeypatch.delenv("MCP_PORT", raising=False)
    assert tools._listen_port() == 8001
