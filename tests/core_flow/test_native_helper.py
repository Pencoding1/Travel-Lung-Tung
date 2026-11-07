"""CORE-069 R2 launcher identity: base interpreter, exact PID, no adoption.

The tests spawn only short-lived test-owned helper children. No service, model,
MCP or GraphHopper process is started here. A foreign listener is never
signalled; the stop failure path must preserve its state evidence.
"""

import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "scripts" / "native_runtime" / "core_service.py"


def _load_helper():
    spec = importlib.util.spec_from_file_location("core069_native_helper", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = _load_helper()
CARRIER = "synthetic-carrier-value"
CARRIER_MARKER = "CARRIER_MARKER_8K1"
BASE_PYTHON = helper.resolve_base_python()


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _wait_for_file(path, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.05)
    return False


def _spawn_listener(port, ready):
    code = (
        "import socket,sys,time\n"
        "s=socket.socket()\n"
        "s.bind(('127.0.0.1',int(sys.argv[1])))\n"
        "s.listen()\n"
        "open(sys.argv[2],'w').write('ready')\n"
        "time.sleep(30)\n"
    )
    process = subprocess.Popen(
        [str(BASE_PYTHON), "-c", code, str(port), str(ready)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
    if not _wait_for_file(ready):
        process.terminate()
        process.wait(timeout=5)
        pytest.fail("test listener did not become ready")
    return process


def _spawn_sleeper():
    return subprocess.Popen(
        [str(BASE_PYTHON), "-c", "import time; time.sleep(30)"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)


def _kill(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _record_for(process, port, service="mcp"):
    return {
        "service": service,
        "pid": process.pid,
        "port": port,
        "creation_time": helper._windows_creation_time(process.pid),
        "image": str(BASE_PYTHON),
        "image_sha256": helper._file_sha256(BASE_PYTHON),
    }


# ---------------------------------------------------------------------------
# Guard carriers and fixed service environment
# ---------------------------------------------------------------------------
def test_each_guard_carrier_is_preserved_byte_exact():
    base = {
        "OPENCODE_CONFIG_CONTENT": CARRIER_MARKER,
        "OPENCODE_CONFIG": "",
        "PATH": "/usr/bin",
    }
    env = helper.child_environment({"MCP_PORT": "19101"}, base=base)

    assert env["OPENCODE_CONFIG_CONTENT"] == CARRIER_MARKER
    assert env["OPENCODE_CONFIG"] == ""
    assert env["MCP_PORT"] == "19101"
    assert env["PATH"] == "/usr/bin"


def test_absent_carriers_stay_absent_and_os_allowlist_still_applies():
    base = {"PATH": "/usr/bin", "UNRELATED_SECRET": "nope"}
    env = helper.child_environment({}, base=base)

    assert "OPENCODE_CONFIG_CONTENT" not in env
    assert "OPENCODE_CONFIG" not in env
    assert "UNRELATED_SECRET" not in env
    assert env["PATH"] == "/usr/bin"


@pytest.mark.parametrize("key", helper.GUARD_CARRIER_KEYS)
def test_override_of_a_guard_carrier_fails_before_spawn(key):
    with pytest.raises(helper.GuardCarrierOverride) as raised:
        helper.child_environment({key: CARRIER}, base={})

    assert raised.value.code == "guard_carrier_override"
    assert str(raised.value) == "guard_carrier_override"
    assert CARRIER not in str(raised.value)


def test_synthetic_environment_secret_is_not_inherited():
    base = {
        "TYPESAFE_API_KEY": "synthetic-secret",
        "MEMGRAPH_PASSWORD": "synthetic-secret",
        "JWT_SECRET": "synthetic-secret",
    }
    env = helper.child_environment({}, base=base)
    assert env == {}


def test_fixed_service_environment_is_loopback_graph_only_and_process_settings():
    mcp = helper.mcp_environment(19101)
    ai = helper.ai_environment(19101, "aibox/ds/deepseek-flash",
                               Path("C:/cli/opencode.exe"))

    assert mcp["MCP_HOST"] == "127.0.0.1"
    assert mcp["MCP_PORT"] == "19101"
    assert mcp["FIRESTORE_ENABLED"] == "false"
    assert mcp["GRAPHHOPPER_PROFILES"] == "car,foot"
    assert mcp["GRAPHHOPPER_CH_PROFILES"] == "car"
    assert mcp[helper.DB_SETTINGS_SOURCE_ENV] == "process_only"
    assert mcp["MEMGRAPH_HOST"] == "127.0.0.1"
    assert mcp["MEMGRAPH_PORT"] == "17687"
    assert mcp["MEMGRAPH_USER"] == ""
    assert mcp["MEMGRAPH_PASSWORD"] == ""
    assert "PYTHONPATH" not in mcp

    assert ai["MCP_SERVER_URL"] == "http://127.0.0.1:19101/sse"
    assert ai["AI_LLM_PROVIDER"] == "opencode_cli"
    assert ai["AI_CLI_MODEL"] == "aibox/ds/deepseek-flash"
    assert ai["AI_CLI_EXECUTABLE"] == "C:\\cli\\opencode.exe"
    assert ai["AI_CLI_PURE"] == "false"
    assert ai["AI_CLI_MAX_ATTEMPTS"] == "1"
    assert ai["JEV_MODEL"] == "jev-1.13.0"
    assert ai["JEV_MIN_CONFIDENCE"] == "0.69"
    assert ai["JEV_MAX_ATTEMPTS"] == "1"
    for env in (mcp, ai):
        assert "OPENCODE_CONFIG_CONTENT" not in env
        assert "OPENCODE_CONFIG" not in env
        for key in ("TYPESAFE_API_KEY", "TYPESAFE_API_TOKEN", "JWT_SECRET"):
            assert key not in env
        assert env.get("MEMGRAPH_PASSWORD", "") == ""


# ---------------------------------------------------------------------------
# Fixed base interpreter and bootstrap
# ---------------------------------------------------------------------------
def test_venv_redirector_resolves_to_direct_base_interpreter():
    assert helper.is_venv_redirector(helper.DEFAULT_VENV_PYTHON) is True
    resolved = helper.resolve_base_python(str(helper.DEFAULT_VENV_PYTHON))
    assert resolved == BASE_PYTHON
    assert resolved != helper.DEFAULT_VENV_PYTHON.resolve()
    assert helper.is_venv_redirector(resolved) is False
    assert resolved.is_file()


def test_fixed_bootstrap_argv_never_runs_the_venv_redirector():
    service_root = REPO_ROOT / "POI_service"
    argv = helper.build_service_argv(
        service_root, "app.api.mcp.tools", [], BASE_PYTHON)
    code = helper.bootstrap_code(service_root)

    assert argv[0] == str(BASE_PYTHON)
    assert argv[1] == "-s"
    assert argv[2] == "-c"
    assert argv[4] == "app.api.mcp.tools"
    assert "runpy.run_module" in code
    readable_code = code.replace("\\\\", "\\")
    assert str(helper.PRIMARY_SITE) in readable_code
    assert str(helper.SHARED_LIB) in readable_code
    assert str(helper.FALLBACK_SITE) in readable_code
    assert "Scripts\\python.exe" not in argv[0]


def test_runtime_fingerprint_proves_primary_versions_and_path_order():
    result = helper.probe_runtime_fingerprint(BASE_PYTHON)
    assert result["python"].startswith(helper.EXPECTED_PYTHON_PREFIX)
    assert result["mcp"] == helper.EXPECTED_MCP_VERSION
    assert result["neo4j"] == helper.EXPECTED_NEO4J_VERSION
    assert result["site_packages"] == str(helper.PRIMARY_SITE)
    assert result["base_python_sha256"] == helper.EXPECTED_BASE_PYTHON_SHA256



# ---------------------------------------------------------------------------
# Exact listener ownership and no-adoption rules
# ---------------------------------------------------------------------------
def test_listener_is_owned_only_by_the_exact_spawned_pid(tmp_path):
    port = _free_port()
    process = _spawn_listener(port, tmp_path / "ready.txt")
    try:
        assert helper.listener_pids(port) == (process.pid,)
        assert helper.listener_matches_pid(port, process.pid) is True
        assert helper.listener_matches_pid(port, os.getpid()) is False
    finally:
        _kill(process)


def test_failure_cleanup_uses_only_the_spawned_process_handle(tmp_path):
    port = _free_port()
    process = _spawn_listener(port, tmp_path / "ready.txt")
    record = _record_for(process, port)
    try:
        result = helper._stop_spawned_process(process, record)
        assert result["stopped"] is True
        assert process.wait(timeout=5) is not None
    finally:
        _kill(process)


def test_failure_cleanup_does_not_signal_on_changed_creation_time(tmp_path):
    port = _free_port()
    process = _spawn_listener(port, tmp_path / "ready.txt")
    record = _record_for(process, port)
    record["creation_time"] += 1
    try:
        result = helper._stop_spawned_process(process, record)
        assert result["stopped"] is False
        assert result["reason"] == "spawn_identity_changed"
        assert process.poll() is None
    finally:
        _kill(process)


def test_foreign_listener_is_not_signalled_by_a_forged_record(tmp_path):
    port = _free_port()
    foreign = _spawn_listener(port, tmp_path / "ready.txt")
    record = _record_for(foreign, port, service="mcp")
    try:
        # The foreign process is a sleep/listener child, not the fixed MCP
        # command. Even with its exact PID/creation/image, stop refuses.
        result = helper._terminate_verified_record(record, BASE_PYTHON)
        assert result["stopped"] is False
        assert result["reason"] == "command_mismatch"
        assert foreign.poll() is None
        assert helper.listener_pids(port) == (foreign.pid,)
    finally:
        _kill(foreign)


def test_invalid_missing_and_changed_identity_fails_closed():
    assert helper.verify_record(
        {"pid": "12", "port": 1, "creation_time": 3}
    )["reason"] == "invalid_record"
    assert helper.verify_record(
        {"pid": 999999, "port": 19101, "creation_time": 1}
    )["reason"] == "process_gone"
    assert helper.verify_record({
        "pid": os.getpid(), "port": 19101, "creation_time": 1,
        "image": str(BASE_PYTHON), "service": "mcp",
    })["reason"] == "creation_time_mismatch"
    assert helper.verify_record({
        "pid": os.getpid(), "port": 19101,
        "creation_time": helper._windows_creation_time(os.getpid()),
    })["reason"] == "missing_image_identity"


def test_pid_reuse_and_wrong_image_are_unowned():
    creation = helper._windows_creation_time(os.getpid())
    assert helper.verify_record({
        "pid": os.getpid(), "port": 19101, "creation_time": creation,
        "image": "C:/does/not/exist-python.exe", "service": "mcp",
    })["reason"] == "image_mismatch"


# ---------------------------------------------------------------------------
# Start refusal / legacy reconciliation
# ---------------------------------------------------------------------------
def _start_args(tmp_path, mcp_port, ai_port):
    executable = tmp_path / "fake-opencode.exe"
    executable.write_bytes(b"")
    parser = helper.build_parser()
    return parser.parse_args([
        "start",
        "--python", str(helper.DEFAULT_VENV_PYTHON),
        "--executable", str(executable),
        "--state-file", str(tmp_path / "state.json"),
        "--mcp-port", str(mcp_port),
        "--ai-port", str(ai_port),
        "--timeout", "1",
    ])


def test_occupied_port_is_refused_without_touching_the_listener(
        tmp_path, capsys):
    import socketserver
    import threading

    class _Handler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.recv(1)

    server = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    occupied = server.server_address[1]
    try:
        assert helper.port_in_use(occupied) is True
        code = helper.command_start(_start_args(tmp_path, occupied, occupied + 1))
        output = capsys.readouterr().out.strip()
        payload = json.loads(output)

        assert code == 3, payload
        assert payload["error"] == "port_occupied"
        assert payload["port"] == occupied
        assert helper.port_in_use(occupied) is True
        assert not (tmp_path / "state.json").exists()
        assert not list(tmp_path.glob("core069-*"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_invalid_port_pair_is_refused(tmp_path, capsys):
    code = helper.command_start(_start_args(tmp_path, 19101, 19101))
    payload = json.loads(capsys.readouterr().out.strip())
    assert code == 2
    assert payload["error"] == "invalid_port_pair"


def test_legacy_state_with_changed_creation_is_not_signalled_or_erased(
        tmp_path, capsys):
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({
        "run_id": "legacy-test",
        "services": {
            "mcp": {
                "pid": os.getpid(),
                "port": _free_port(),
                "creation_time": 1,
                "launcher_pid": 999999,
            },
        },
    }), encoding="utf-8")
    code = helper.command_start(_start_args(tmp_path, _free_port(), _free_port()))
    payload = json.loads(capsys.readouterr().out.strip())
    assert code == 3, payload
    assert payload["error"] == "legacy_state_unverified"
    assert state_file.exists()


# ---------------------------------------------------------------------------
# Stop is idempotent, but unproven state is preserved
# ---------------------------------------------------------------------------
def test_stop_without_state_is_idempotent(tmp_path, capsys):
    parser = helper.build_parser()
    args = parser.parse_args([
        "stop", "--state-file", str(tmp_path / "missing.json")])
    code = helper.command_stop(args)
    payload = json.loads(capsys.readouterr().out.strip())
    assert code == 0
    assert payload["status"] == "not_started"


def test_stop_archives_an_already_gone_process(tmp_path, capsys):
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({
        "run_id": "gone-test",
        "services": {
            "mcp": {
                "pid": 999999,
                "port": _free_port(),
                "creation_time": 1,
                "image": str(BASE_PYTHON),
                "image_sha256": helper._file_sha256(BASE_PYTHON),
                "service": "mcp",
            },
        },
    }), encoding="utf-8")
    parser = helper.build_parser()
    args = parser.parse_args([
        "stop", "--state-file", str(state_file)])
    code = helper.command_stop(args)
    payload = json.loads(capsys.readouterr().out.strip())
    assert code == 0, payload
    assert payload["status"] == "stopped"
    assert not state_file.exists()
    assert list((tmp_path / "history").glob("gone-test.stopped.json"))


def test_stop_preserves_unproven_process_and_state(tmp_path, capsys):
    process = _spawn_sleeper()
    port = _free_port()
    record = _record_for(process, port, service="mcp")
    record["command_tail"] = ["app.api.mcp.tools"]
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({
        "run_id": "unproven-test",
        "services": {"mcp": record},
    }), encoding="utf-8")
    parser = helper.build_parser()
    args = parser.parse_args([
        "stop", "--state-file", str(state_file)])
    try:
        code = helper.command_stop(args)
        payload = json.loads(capsys.readouterr().out.strip())
        assert code == 1, payload
        assert payload["status"] == "partial"
        assert process.poll() is None
        assert state_file.exists()
    finally:
        _kill(process)
