"""CORE-069 owned native launcher for the POI MCP and AI services.

R2 lifecycle contract
---------------------
* The child is the installed **base** interpreter, never the Windows venv
  redirector, so the Popen PID is the interpreter that can own the listener.
* A fixed, non-secret ``-c`` bootstrap puts the primary venv site-packages,
  the service root, the repo root and ``shared_lib`` on ``sys.path`` (primary
  venv first); the older project ``.venv`` site-packages is appended last for
  packages missing from the primary venv.
* A start records the exact Popen PID, OS creation time, image path/SHA,
  module/args and bootstrap hash. Readiness requires the listener to belong to
  **that exact PID**. There is no freshness-based listener adoption.
* Before any signal, the helper re-verifies creation time, image path/SHA,
  fixed command tail and (when present) exact listener ownership. A reused PID,
  missing/ambiguous identity or foreign listener receives zero signals.
* Failure cleanup only targets processes spawned by this invocation. A state
  record that cannot be proven is preserved, not erased and not signalled.
* Legacy R1 records are reconciled only when every field proves out (exact
  child creation time, base image/SHA, fixed command tail, listener PID and
  recorded launcher); otherwise they are left untouched and reported.

Environment
-----------
Only the OS allowlist is inherited. The two ambient OpenCode guard carriers are
forwarded byte-exactly (including an empty string); a service override raises a
constant error before spawn. The helper never reads, prints or stores a
credential, token, header or raw ``.env``.
"""

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MCP_PORT = 19101
DEFAULT_AI_PORT = 19102
DEFAULT_ALIAS = "aibox/ds/deepseek-flash"
DEFAULT_EXECUTABLE = Path(
    "C:/Users/duyan/AppData/Roaming/npm/node_modules/@opencode/cli/bin/opencode.exe")
_VALIDATION_VENV = REPO_ROOT / ".venv-mcp-validation"
_ACTIVE_VENV = _VALIDATION_VENV if _VALIDATION_VENV.is_dir() else (REPO_ROOT / ".venv")


# The venv redirector is kept only as a legacy-parent reference. Children are
# always launched through the base interpreter resolved below.
DEFAULT_VENV_PYTHON = _ACTIVE_VENV / "Scripts" / "python.exe"
DEFAULT_STATE_FILE = REPO_ROOT / ".runtime-native" / "state" / "core_service.json"
DEFAULT_TIMEOUT_SECONDS = 60.0

PRIMARY_SITE = _ACTIVE_VENV / "Lib" / "site-packages"
FALLBACK_SITE = REPO_ROOT / ".venv" / "Lib" / "site-packages"
SHARED_LIB = REPO_ROOT / "shared_lib"

EXPECTED_BASE_PYTHON_SHA256 = (
    "467014615a5255aca450ae88100dd2caf887da87657f00e3c2171ec44a685aec"
    if _VALIDATION_VENV.is_dir()
    else ""
)
EXPECTED_PYTHON_PREFIX = (
    "3.14."
    if _VALIDATION_VENV.is_dir()
    else f"{sys.version_info.major}.{sys.version_info.minor}."
)
EXPECTED_MCP_VERSION = "1.26.0"
EXPECTED_NEO4J_VERSION = "6.4.0" if _VALIDATION_VENV.is_dir() else "6.1.0"


BASE_URL = "http://127.0.0.1"
GRAPHHOPPER_URL = "http://127.0.0.1:18989/route"
MEMGRAPH_HOST = "127.0.0.1"
MEMGRAPH_PORT = "17687"

# Explicit, literal settings selector. Absence keeps the historical env-file
# behaviour. ``process_only`` disables the class-level .env source for this
# process; any other value fails before the file would be loaded.
DB_SETTINGS_SOURCE_ENV = "POI_DB_SETTINGS_SOURCE"
DB_SETTINGS_SOURCE_PROCESS_ONLY = "process_only"

SERVICE_MCP = "mcp"
SERVICE_AI = "ai"

# Only these OS variables are inherited by the children. Everything else,
# including any credential or token, stays out of the child environment.
INHERITED_ENV_KEYS: Tuple[str, ...] = (
    "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "PATH", "PATHEXT", "COMSPEC",
    "TEMP", "TMP", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME",
    "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
    "PYTHONIOENCODING", "PYTHONUTF8", "PYTHONUNBUFFERED",
    "PYTHONDONTWRITEBYTECODE",
)

# Ambient OpenCode guard carriers. They are forwarded byte-exactly (including
# an empty string) so the provider's own refusal contract stays intact. This
# helper never reads, prints or interprets their values.
GUARD_CARRIER_KEYS: Tuple[str, ...] = (
    "OPENCODE_CONFIG_CONTENT", "OPENCODE_CONFIG")

GUARD_CARRIER_OVERRIDE = "guard_carrier_override"


class GuardCarrierOverride(ValueError):
    """A caller tried to replace a guard carrier; spawn must not happen."""

    def __init__(self) -> None:
        super().__init__(GUARD_CARRIER_OVERRIDE)
        self.code = GUARD_CARRIER_OVERRIDE


class RuntimeCheckError(ValueError):
    """A fixed runtime identity check failed before any child was spawned."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _emit(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Fixed per-run service configuration (no ambient/secret values)
# ---------------------------------------------------------------------------
def mcp_environment(port: int) -> Dict[str, str]:
    return {
        "MCP_HOST": "127.0.0.1",
        "MCP_PORT": str(port),
        # The native run must not fall back to the class-level POI .env.
        DB_SETTINGS_SOURCE_ENV: DB_SETTINGS_SOURCE_PROCESS_ONLY,
        "MEMGRAPH_HOST": MEMGRAPH_HOST,
        "MEMGRAPH_PORT": MEMGRAPH_PORT,
        # The owned loopback engine has no authentication enabled.
        "MEMGRAPH_USER": "",
        "MEMGRAPH_PASSWORD": "",
        "FIRESTORE_ENABLED": "false",
        "GRAPHHOPPER_URL": GRAPHHOPPER_URL,
        "GRAPHHOPPER_PROFILES": "car,foot",
        "GRAPHHOPPER_CH_PROFILES": "car",
        "PYTHONUNBUFFERED": "1",
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def ai_environment(mcp_port: int, alias: str, executable: Path) -> Dict[str, str]:
    return {
        "MCP_SERVER_URL": f"{BASE_URL}:{mcp_port}/sse",
        "AI_LLM_PROVIDER": "opencode_cli",
        "AI_CLI_MODEL": alias,
        "AI_CLI_EXECUTABLE": str(executable),
        # Explicit opt-out for the native diagnostic run: the installed CLI
        # cannot apply --pure. The provider default stays True (fail closed).
        "AI_CLI_PURE": "false",
        # One attempt per call for the bounded pilot; failed attempts are still
        # recorded by the provider.
        "AI_CLI_MAX_ATTEMPTS": "1",
        "JEV_MODEL": "jev-1.13.0",
        "JEV_MIN_CONFIDENCE": "0.69",
        "JEV_MAX_ATTEMPTS": "1",
        "PYTHONUNBUFFERED": "1",
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def child_environment(overrides: Dict[str, str],
                      base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Build the child environment without dropping a guard carrier.

    The two ambient OpenCode carriers are copied *byte-exactly* from ``base``
    (the process environment by default), including an empty string, because
    the provider itself must decide whether a nonempty carrier is acceptable.
    Service overrides may never replace them: an attempted override fails with
    a constant error before any child process is spawned. Values are never
    logged, stored or inspected.
    """
    source = os.environ if base is None else base
    for key in GUARD_CARRIER_KEYS:
        if key in overrides:
            raise GuardCarrierOverride()
    env: Dict[str, str] = {}
    for key in GUARD_CARRIER_KEYS:
        if key in source:
            env[key] = source[key]
    for key in INHERITED_ENV_KEYS:
        if key in source:
            env[key] = source[key]
    env.update(overrides)
    return env


# ---------------------------------------------------------------------------
# Interpreter and bootstrap identity
# ---------------------------------------------------------------------------
def _venv_base_python(candidate: Path) -> Optional[Path]:
    """Return the base interpreter named by a venv redirector, if any."""
    cfg = candidate.parent.parent / "pyvenv.cfg"
    try:
        lines = cfg.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.strip().lower().startswith("home"):
            _, _, value = line.partition("=")
            home = value.strip()
            if not home:
                continue
            name = "python.exe" if os.name == "nt" else "python3"
            base = Path(home) / name
            return base if base.is_file() else None
    return None


def is_venv_redirector(path: Path) -> bool:
    return (path.parent.name.lower() == "scripts"
            and (path.parent.parent / "pyvenv.cfg").is_file())


def resolve_base_python(explicit: Optional[str] = None) -> Path:
    """Resolve a direct base interpreter, never a Windows venv redirector."""
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        if not candidate.is_file():
            raise RuntimeCheckError("base_interpreter_missing")
        if is_venv_redirector(candidate):
            base = _venv_base_python(candidate)
            if base is None:
                raise RuntimeCheckError("base_interpreter_missing")
            return base.resolve()
        return candidate
    base = getattr(sys, "_base_executable", None)
    if base:
        candidate = Path(base)
        if candidate.is_file():
            return candidate.resolve()
    candidate = Path(sys.base_prefix) / ("python.exe" if os.name == "nt" else "python3")
    if candidate.is_file():
        return candidate.resolve()
    candidate = Path("C:/Python314/python.exe")
    if candidate.is_file():
        return candidate.resolve()
    raise RuntimeCheckError("base_interpreter_missing")


def validate_runtime(base_python: Path,
                     expected_sha256: Optional[str] = None) -> Dict[str, Any]:
    """Validate the fixed interpreter/site-packages identity before spawn."""
    if not base_python.is_file():
        raise RuntimeCheckError("base_interpreter_missing")
    sha = _file_sha256(base_python)
    expected = expected_sha256 or EXPECTED_BASE_PYTHON_SHA256
    if expected and sha != expected:
        raise RuntimeCheckError("base_interpreter_mismatch")
    if not PRIMARY_SITE.is_dir():
        raise RuntimeCheckError("primary_site_missing")
    return {
        "base_python": str(base_python),
        "base_python_sha256": sha,
        "primary_site_packages": str(PRIMARY_SITE),
        "fallback_site_packages": (str(FALLBACK_SITE)
                                   if FALLBACK_SITE.is_dir() else None),
    }


if not EXPECTED_BASE_PYTHON_SHA256:
    try:
        EXPECTED_BASE_PYTHON_SHA256 = _file_sha256(resolve_base_python())
    except Exception:
        EXPECTED_BASE_PYTHON_SHA256 = ""



def _path_setup_code(service_root: Path) -> str:
    paths = []
    for item in (PRIMARY_SITE, service_root, REPO_ROOT, SHARED_LIB):
        value = str(item)
        if value not in paths:
            paths.append(value)
    return "\n".join([
        "import sys",
        f"_paths = {paths!r}",
        "sys.path[:0] = [p for p in _paths if p not in sys.path]",
        f"_fallback = {str(FALLBACK_SITE)!r}",
        "if _fallback not in sys.path:",
        "    sys.path.append(_fallback)",
        # pywin32's .pth entries are not processed for a foreign site dir.
        f"_win32 = {str(PRIMARY_SITE / 'win32')!r}",
        f"_win32_lib = {str(PRIMARY_SITE / 'win32' / 'lib')!r}",
        f"_pythonwin = {str(PRIMARY_SITE / 'pythonwin')!r}",
        "for _p in (_win32, _win32_lib, _pythonwin):",
        "    if _p not in sys.path:",
        "        sys.path.append(_p)",
        "try:",
        "    import pywin32_bootstrap",
        "except ImportError:",
        "    pass",
    ])


def bootstrap_code(service_root: Path) -> str:
    return _path_setup_code(service_root) + "\n" + "\n".join([
        "import runpy",
        "module = sys.argv[1]",
        "args = sys.argv[2:]",
        "sys.argv = [module] + args",
        "runpy.run_module(module, run_name='__main__')",
    ])


def build_service_argv(service_root: Path, module: str,
                       module_args: Sequence[str],
                       base_python: Optional[Path] = None) -> list:
    base = (base_python or resolve_base_python()).resolve()
    return [str(base), "-s", "-c", bootstrap_code(service_root),
            module, *list(module_args)]


def _fingerprint_code(service_root: Path) -> str:
    return _path_setup_code(service_root) + "\n" + "\n".join([
        "import importlib.metadata as md",
        "import json",
        "def ver(name):",
        "    try:",
        "        return md.version(name)",
        "    except md.PackageNotFoundError:",
        "        return None",
        "print(json.dumps({",
        "  'python': sys.version.split()[0],",
        "  'mcp': ver('mcp'),",
        "  'neo4j': ver('neo4j'),",
        "  'fastapi': ver('fastapi'),",
        "  'tenacity': ver('tenacity'),",
        "  'site_packages': next((p for p in sys.path",
        "                         if p.endswith('site-packages')), None),",
        "}))",
    ])


def probe_runtime_fingerprint(base_python: Optional[Path] = None,
                              timeout: float = 30.0) -> Dict[str, Any]:
    """Prove the actual base-interpreter import paths and package versions."""
    base = (base_python or resolve_base_python()).resolve()
    env = child_environment({})
    completed = subprocess.run(
        [str(base), "-s", "-c", _fingerprint_code(REPO_ROOT)],
        cwd=str(REPO_ROOT), env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=timeout, check=False)
    if completed.returncode != 0:
        raise RuntimeCheckError("runtime_fingerprint_failed")
    try:
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        raise RuntimeCheckError("runtime_fingerprint_invalid")
    if not isinstance(payload, dict):
        raise RuntimeCheckError("runtime_fingerprint_invalid")
    if payload.get("mcp") != EXPECTED_MCP_VERSION:
        raise RuntimeCheckError("mcp_version_mismatch")
    if payload.get("neo4j") != EXPECTED_NEO4J_VERSION:
        raise RuntimeCheckError("neo4j_version_mismatch")
    if not str(payload.get("python", "")).startswith(EXPECTED_PYTHON_PREFIX):
        raise RuntimeCheckError("python_version_mismatch")
    if payload.get("site_packages") != str(PRIMARY_SITE):
        raise RuntimeCheckError("primary_site_not_first")
    payload["base_python"] = str(base)
    payload["base_python_sha256"] = _file_sha256(base)
    return payload


# ---------------------------------------------------------------------------
# Windows process identity, image and listener ownership
# ---------------------------------------------------------------------------
class _FilTime(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.c_uint32),
                ("dwHighDateTime", ctypes.c_uint32)]


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
SYNCHRONIZE = 0x00100000


def _handle_creation_time(handle: int) -> Optional[int]:
    creation = _FilTime()
    exit_time = _FilTime()
    kernel_time = _FilTime()
    user_time = _FilTime()
    ok = ctypes.windll.kernel32.GetProcessTimes(
        handle, ctypes.byref(creation), ctypes.byref(exit_time),
        ctypes.byref(kernel_time), ctypes.byref(user_time))
    if not ok:
        return None
    return (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)


def _windows_creation_time(pid: int) -> Optional[int]:
    """Return the process creation time in 100ns units, or None if gone."""
    if os.name != "nt":
        return _posix_creation_time(pid)
    handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        return _handle_creation_time(handle)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _posix_creation_time(pid: int) -> Optional[int]:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        fields = stat.rsplit(") ", 1)[1].split()
        return int(fields[19])
    except (OSError, IndexError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        return _windows_creation_time(pid) is not None
    return Path(f"/proc/{pid}").exists()


def _process_image_path(pid: int) -> Optional[str]:
    if os.name != "nt":
        try:
            return os.readlink(f"/proc/{pid}/exe")
        except OSError:
            return None
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = ctypes.c_ulong(len(buffer))
        ok = kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(size))
        return buffer.value if ok else None
    finally:
        kernel32.CloseHandle(handle)


def _process_command_line(pid: int) -> Optional[str]:
    if os.name != "nt":
        try:
            raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        except OSError:
            return None
        return raw.replace(b"\x00", b" ").decode("utf-8", "replace").strip()
    command = ("(Get-CimInstance Win32_Process -Filter \"ProcessId = "
               f"{int(pid)}\").CommandLine")
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
             command],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value or None


class _TcpRowOwnerPid(ctypes.Structure):
    _fields_ = [("dwState", ctypes.c_uint32),
                ("dwLocalAddr", ctypes.c_uint32),
                ("dwLocalPort", ctypes.c_uint32),
                ("dwRemoteAddr", ctypes.c_uint32),
                ("dwRemotePort", ctypes.c_uint32),
                ("dwOwningPid", ctypes.c_uint32)]


TCP_TABLE_OWNER_PID_LISTENER = 3
AF_INET = 2
ERROR_INSUFFICIENT_BUFFER = 122


def listener_pids(port: int) -> Tuple[int, ...]:
    """PIDs with a TCP listener on ``port`` (IPv4 loopback included)."""
    if os.name != "nt":
        return _posix_listener_pids(port)
    iphlpapi = ctypes.windll.iphlpapi
    size = ctypes.c_ulong(0)
    result = iphlpapi.GetExtendedTcpTable(
        None, ctypes.byref(size), False, AF_INET,
        TCP_TABLE_OWNER_PID_LISTENER, 0)
    if result not in (0, ERROR_INSUFFICIENT_BUFFER):
        return ()
    if size.value == 0:
        return ()
    buffer = ctypes.create_string_buffer(size.value)
    result = iphlpapi.GetExtendedTcpTable(
        buffer, ctypes.byref(size), False, AF_INET,
        TCP_TABLE_OWNER_PID_LISTENER, 0)
    if result != 0:
        return ()
    count = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_uint32)).contents.value
    header = ctypes.sizeof(ctypes.c_uint32)
    row_size = ctypes.sizeof(_TcpRowOwnerPid)
    pids = []
    base = ctypes.addressof(buffer) + header
    for index in range(count):
        row = _TcpRowOwnerPid.from_address(base + index * row_size)
        local_port = ((row.dwLocalPort & 0xFF) << 8) | (
            (row.dwLocalPort >> 8) & 0xFF)
        if local_port == port:
            pids.append(int(row.dwOwningPid))
    return tuple(sorted(set(pids)))


def _posix_listener_pids(port: int) -> Tuple[int, ...]:
    inodes = set()
    hex_port = f"{port:04X}"
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lines = Path(table).read_text(encoding="utf-8").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 10 or fields[3] != "0A":
                continue
            if fields[1].rsplit(":", 1)[-1] != hex_port:
                continue
            inodes.add(fields[9])
    if not inodes:
        return ()
    pids = set()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            for fd in (entry / "fd").iterdir():
                target = os.readlink(fd)
                if target.startswith("socket:[") and target[8:-1] in inodes:
                    pids.add(int(entry.name))
                    break
        except (OSError, PermissionError):
            continue
    return tuple(sorted(pids))


def listener_matches_pid(port: int, pid: int) -> bool:
    """True only when the listener set for ``port`` is exactly ``(pid,)``."""
    return listener_pids(port) == (pid,)


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def command_matches_service(service: str, command_line: Optional[str],
                            port: int) -> bool:
    if not command_line:
        return False
    if service == SERVICE_MCP:
        return "app.api.mcp.tools" in command_line
    if service == SERVICE_AI:
        return all(token in command_line for token in (
            "uvicorn", "main:app", "--host 127.0.0.1", f"--port {port}"))
    return False


# ---------------------------------------------------------------------------
# Health probes
# ---------------------------------------------------------------------------
def _http_get(port: int, path: str, timeout: float = 2.0) -> Tuple[int, bytes]:
    import http.client

    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read(2048)
    finally:
        connection.close()


def probe_ai_health(port: int) -> Dict[str, Any]:
    try:
        status, body = _http_get(port, "/healthz", timeout=3.0)
    except OSError as exc:
        return {"ok": False, "reason": type(exc).__name__}
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        payload = None
    ok = (status == 200 and isinstance(payload, dict)
          and payload.get("status") == "ok"
          and payload.get("service") == "ai_service")
    return {"ok": ok, "http_status": status,
            "service": (payload or {}).get("service")}


def probe_mcp_sse(port: int, timeout: float = 3.0) -> Dict[str, Any]:
    """Read only the SSE response headers; never consume the stream."""
    request = (f"GET /sse HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
               "Accept: text/event-stream\r\nConnection: close\r\n\r\n")
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as conn:
            conn.sendall(request.encode("ascii"))
            conn.settimeout(timeout)
            raw = b""
            while b"\r\n\r\n" not in raw and len(raw) < 4096:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                raw += chunk
    except OSError as exc:
        return {"ok": False, "reason": type(exc).__name__}
    head = raw.split(b"\r\n\r\n", 1)[0].decode("latin-1", "replace")
    ok = head.startswith("HTTP/1.1 200") or head.startswith("HTTP/1.0 200")
    return {"ok": ok and "text/event-stream" in head.lower(),
            "http_status": head.split(" ", 2)[1] if " " in head else None,
            "content_type": ("text/event-stream"
                             if "text/event-stream" in head.lower() else None)}


def _wait_until(predicate, timeout: float, interval: float = 0.25) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# State file and identity verification
# ---------------------------------------------------------------------------
def read_state(path: Path) -> Optional[Dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def write_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    os.replace(tmp, path)


def archive_state(state_file: Path, state: Dict[str, Any], kind: str,
                  detail: Optional[Dict[str, Any]] = None) -> Path:
    history = state_file.parent / "history"
    history.mkdir(parents=True, exist_ok=True)
    run_id = str(state.get("run_id") or "unknown")
    path = history / f"{run_id}.{kind}.json"
    payload = {
        "archived_at": _now_iso(),
        "kind": kind,
        "detail": detail or {},
        "state": state,
    }
    write_state(path, payload)
    return path


def verify_record(record: Dict[str, Any], *,
                  require_listener: bool = False,
                  expected_image: Optional[Path] = None,
                  service: Optional[str] = None) -> Dict[str, Any]:
    """Prove the recorded process/image/command/listener identity.

    No signal is sent here. A missing or ambiguous field is a failure.
    """
    pid = record.get("pid")
    port = record.get("port")
    creation = record.get("creation_time")
    image = record.get("image")
    if not isinstance(pid, int) or pid <= 0:
        return {"owned": False, "reason": "invalid_record"}
    if not isinstance(port, int) or not (1 <= port <= 65535):
        return {"owned": False, "reason": "invalid_record"}
    if not isinstance(creation, int) or creation <= 0:
        return {"owned": False, "reason": "missing_creation_time",
                "pid": pid, "port": port}
    live_creation = _windows_creation_time(pid)
    if live_creation is None:
        return {"owned": False, "reason": "process_gone",
                "pid": pid, "port": port}
    if live_creation != creation:
        return {"owned": False, "reason": "creation_time_mismatch",
                "pid": pid, "port": port}
    image_path = image or (str(expected_image) if expected_image else None)
    if not image_path:
        return {"owned": False, "reason": "missing_image_identity",
                "pid": pid, "port": port}
    live_image = _process_image_path(pid)
    if not live_image:
        return {"owned": False, "reason": "process_image_unreadable",
                "pid": pid, "port": port}
    if os.path.normcase(os.path.abspath(live_image)) != os.path.normcase(
            os.path.abspath(image_path)):
        return {"owned": False, "reason": "image_mismatch",
                "pid": pid, "port": port, "image": live_image}
    expected_sha = record.get("image_sha256")
    if not expected_sha:
        try:
            expected_sha = _file_sha256(Path(image_path))
        except OSError:
            return {"owned": False, "reason": "image_unreadable",
                    "pid": pid, "port": port}
    live_sha = _file_sha256(Path(live_image))
    if live_sha != expected_sha:
        return {"owned": False, "reason": "image_sha256_mismatch",
                "pid": pid, "port": port}
    service = record.get("service") or service
    if service not in (SERVICE_MCP, SERVICE_AI):
        return {"owned": False, "reason": "missing_service_identity",
                "pid": pid, "port": port}
    command_line = _process_command_line(pid)
    if not command_matches_service(service, command_line, port):
        return {"owned": False, "reason": ("command_unreadable"
                                          if command_line is None
                                          else "command_mismatch"),
                "pid": pid, "port": port}
    owners = listener_pids(port)
    if owners and owners != (pid,):
        return {"owned": False, "reason": "listener_owned_by_other_process",
                "pid": pid, "port": port, "listener_pids": list(owners)}
    if require_listener and not owners:
        return {"owned": False, "reason": "listener_missing",
                "pid": pid, "port": port}
    return {"owned": True, "pid": pid, "port": port,
            "creation_time": live_creation,
            "image": live_image,
            "image_sha256": live_sha,
            "listener_pids": list(owners),
            "listening": bool(owners)}


def _terminate_verified_record(record: Dict[str, Any],
                               expected_image: Path,
                               service: Optional[str] = None) -> Dict[str, Any]:
    """Terminate only after a fresh identity proof, via a new OS handle."""
    verification = verify_record(record, require_listener=False,
                                 expected_image=expected_image,
                                 service=service)
    if not verification.get("owned"):
        reason = verification.get("reason")
        if reason == "process_gone":
            owners = listener_pids(record.get("port", 0))
            if not owners or record.get("pid") not in owners:
                return {"pid": record.get("pid"), "stopped": True,
                        "already_gone": True, "reason": "process_gone",
                        "listener_pids_after": list(owners)}
            return {"pid": record.get("pid"), "stopped": False,
                    "reason": "listener_owned_by_other_process",
                    "listener_pids_after": list(owners)}
        return {"pid": record.get("pid"), "stopped": False, "reason": reason}
    pid = record["pid"]
    creation = record["creation_time"]
    if os.name != "nt":
        try:
            os.kill(pid, 15)
        except OSError:
            pass
        gone = _wait_until(lambda: not _pid_alive(pid), 10.0)
        return {"pid": pid, "stopped": gone, "terminate_sent": True,
                "listener_pids_after": list(listener_pids(record["port"]))}
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(
        PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE,
        False, pid)
    if not handle:
        return {"pid": pid, "stopped": False,
                "reason": "process_handle_unavailable"}
    try:
        if _handle_creation_time(handle) != creation:
            return {"pid": pid, "stopped": False,
                    "reason": "creation_time_changed_before_signal"}
        terminated = bool(kernel32.TerminateProcess(handle, 1))
        waited = kernel32.WaitForSingleObject(handle, 10_000)
    finally:
        kernel32.CloseHandle(handle)
    return {"pid": pid, "stopped": bool(terminated and waited == 0),
            "terminate_sent": terminated,
            "listener_pids_after": list(listener_pids(record["port"]))}


def _stop_spawned_process(process: subprocess.Popen,
                          record: Dict[str, Any]) -> Dict[str, Any]:
    """Failure cleanup for a process this invocation just spawned.

    It does not enumerate port owners: only the exact Popen PID/creation/image
    is a target, so a foreign listener on the same port is never signalled.
    """
    pid = process.pid
    creation = record.get("creation_time")
    live_creation = _windows_creation_time(pid)
    if live_creation is None or process.poll() is not None:
        return {"pid": pid, "stopped": True, "already_gone": True}
    if not isinstance(creation, int) or live_creation != creation:
        return {"pid": pid, "stopped": False,
                "reason": "spawn_identity_changed"}
    image = record.get("image")
    live_image = _process_image_path(pid)
    if not live_image and process.poll() is not None:
        return {"pid": pid, "stopped": True, "already_gone": True}
    if not image or not live_image or os.path.normcase(live_image) != os.path.normcase(image):
        return {"pid": pid, "stopped": False, "reason": "spawn_image_mismatch"}
    if os.name != "nt":
        try:
            process.terminate()
        except OSError:
            pass
    else:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(
            PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE,
            False, pid)
        if not handle:
            return {"pid": pid, "stopped": process.poll() is not None,
                    "reason": "process_handle_unavailable"}
        try:
            if _handle_creation_time(handle) != creation:
                return {"pid": pid, "stopped": False,
                        "reason": "creation_time_changed_before_signal"}
            kernel32.TerminateProcess(handle, 1)
            waited = kernel32.WaitForSingleObject(handle, 10_000)
        finally:
            kernel32.CloseHandle(handle)
        if waited != 0:
            return {"pid": pid, "stopped": False, "reason": "wait_timeout"}
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        return {"pid": pid, "stopped": False, "reason": "wait_timeout"}
    return {"pid": pid, "stopped": True, "terminate_sent": True}


def _spawn(name: str, argv: Sequence[str], cwd: Path, env: Dict[str, str],
           log_dir: Path, creationflags: int, service: str,
           module: str, module_args: Sequence[str],
           base_python: Path) -> Tuple[subprocess.Popen, Dict[str, Any]]:
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f"{name}.out.log"
    stderr_path = log_dir / f"{name}.err.log"
    stdout = open(stdout_path, "ab")
    stderr = open(stderr_path, "ab")
    try:
        process = subprocess.Popen(
            list(argv), cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
            stdout=stdout, stderr=stderr, creationflags=creationflags,
            close_fds=True)
    finally:
        stdout.close()
        stderr.close()
    creation = _windows_creation_time(process.pid)
    record = {
        "service": service,
        "pid": process.pid,
        "port": 0,
        "host": "127.0.0.1",
        "creation_time": creation,
        "parent_pid": os.getpid(),
        "image": str(base_python),
        "image_sha256": _file_sha256(base_python),
        "module": module,
        "module_args": list(module_args),
        "bootstrap_sha256": _sha256_text(bootstrap_code(cwd)),
        "argv_sha256": _sha256_text(json.dumps(list(argv))),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
    }
    return process, record


def _stop_legacy_launcher(record: Dict[str, Any],
                          service: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Stop a verified old venv redirector parent after its child is gone."""
    pid = record.get("launcher_pid")
    if not isinstance(pid, int) or pid <= 0:
        return None
    if not _pid_alive(pid):
        return {"pid": pid, "stopped": True, "already_gone": True}
    # The venv redirector normally exits as soon as its child is gone. Give it
    # that chance before reading its command line; a launcher that exits is a
    # successful cleanup, not a command mismatch.
    if _wait_until(lambda: not _pid_alive(pid), 3.0):
        return {"pid": pid, "stopped": True, "already_gone": True}
    image = _process_image_path(pid)
    if not image or os.path.normcase(os.path.abspath(image)) != os.path.normcase(
            os.path.abspath(str(DEFAULT_VENV_PYTHON))):
        if _wait_until(lambda: not _pid_alive(pid), 2.0):
            return {"pid": pid, "stopped": True, "already_gone": True}
        return {"pid": pid, "stopped": False, "reason": "launcher_image_mismatch"}
    command = _process_command_line(pid)
    if not command_matches_service(record.get("service") or service or "",
                                   command, int(record.get("port", 0))):
        if _wait_until(lambda: not _pid_alive(pid), 2.0):
            return {"pid": pid, "stopped": True, "already_gone": True}
        return {"pid": pid, "stopped": False, "reason": "launcher_command_mismatch"}
    creation = _windows_creation_time(pid)
    if creation is None:
        return {"pid": pid, "stopped": True, "already_gone": True}
    if os.name != "nt":
        try:
            os.kill(pid, 15)
        except OSError:
            pass
        return {"pid": pid, "stopped": _wait_until(lambda: not _pid_alive(pid), 10.0)}
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(
        PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE,
        False, pid)
    if not handle:
        return {"pid": pid, "stopped": False, "reason": "launcher_handle_unavailable"}
    try:
        if _handle_creation_time(handle) != creation:
            return {"pid": pid, "stopped": False,
                    "reason": "launcher_creation_changed"}
        terminated = bool(kernel32.TerminateProcess(handle, 1))
        waited = kernel32.WaitForSingleObject(handle, 10_000)
    finally:
        kernel32.CloseHandle(handle)
    return {"pid": pid, "stopped": bool(terminated and waited == 0),
            "terminate_sent": terminated}


def _legacy_verify(record: Dict[str, Any], base_python: Path,
                   service: str) -> Dict[str, Any]:
    """Verify an R1 record including its recorded venv launcher parent."""
    result = verify_record(record, require_listener=True,
                           expected_image=base_python, service=service)
    if not result.get("owned"):
        return result
    launcher = record.get("launcher_pid")
    if not isinstance(launcher, int):
        return {"owned": False, "reason": "missing_launcher_identity",
                "pid": record.get("pid"), "port": record.get("port")}
    if _windows_creation_time(launcher) is None:
        return {"owned": False, "reason": "launcher_gone",
                "pid": record.get("pid"), "port": record.get("port")}
    image = _process_image_path(launcher)
    if not image or os.path.normcase(os.path.abspath(image)) != os.path.normcase(
            os.path.abspath(str(DEFAULT_VENV_PYTHON))):
        return {"owned": False, "reason": "launcher_image_mismatch",
                "pid": record.get("pid"), "port": record.get("port")}
    command = _process_command_line(launcher)
    if not command_matches_service(service, command,
                                   int(record.get("port", 0))):
        return {"owned": False, "reason": "launcher_command_mismatch",
                "pid": record.get("pid"), "port": record.get("port")}
    result["launcher_pid"] = launcher
    result["launcher_image"] = image
    return result


def _reconcile_existing(state_file: Path, state: Dict[str, Any],
                        base_python: Path) -> Dict[str, Any]:
    """Stop a fully proven legacy stack; never signal an unproven record."""
    services = state.get("services") or {}
    if not services:
        archive_state(state_file, state, "stale-reconciled",
                      {"reason": "empty_services"})
        try:
            state_file.unlink()
        except OSError:
            pass
        return {"status": "stale_removed"}
    verifications: Dict[str, Any] = {}
    for name, record in services.items():
        verifications[name] = _legacy_verify(record, base_python, name)
    if not all(item.get("owned") for item in verifications.values()):
        all_gone = all(item.get("reason") == "process_gone"
                       for item in verifications.values())
        ports_free = all(not listener_pids(int(record.get("port", 0)))
                         for record in services.values())
        if all_gone and ports_free:
            archive_state(state_file, state, "stale-reconciled",
                          {"verifications": verifications})
            try:
                state_file.unlink()
            except OSError:
                pass
            return {"status": "stale_removed",
                    "verifications": verifications}
        return {"status": "unverified", "verifications": verifications}
    stop_results: Dict[str, Any] = {}
    for name, record in services.items():
        stop_results[name] = _terminate_verified_record(
            record, base_python, service=name)
    for name, record in services.items():
        launcher = _stop_legacy_launcher(record, service=name)
        if launcher is not None:
            stop_results[f"{name}_launcher"] = launcher
    # Wait for the ports to be free, but never signal a new foreign owner.
    for record in services.values():
        port = int(record.get("port", 0))
        _wait_until(lambda p=port: not listener_pids(p), 10.0)
    ports = {name: list(listener_pids(int(record.get("port", 0))))
             for name, record in services.items()}
    stopped_all = all(item.get("stopped") for item in stop_results.values()
                      if isinstance(item, dict))
    ports_free = all(not owners for owners in ports.values())
    detail = {"verifications": verifications, "stop_results": stop_results,
              "ports_after": ports}
    archive_state(state_file, state, "legacy-reconciled", detail)
    if stopped_all and ports_free:
        try:
            state_file.unlink()
        except OSError:
            pass
        return {"status": "reconciled", "detail": detail}
    return {"status": "partial", "detail": detail}


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def _cli_paths(args: argparse.Namespace) -> Dict[str, Any]:
    base_python = resolve_base_python(args.python or None)
    executable = Path(args.executable) if args.executable else DEFAULT_EXECUTABLE
    state_file = Path(args.state_file) if args.state_file else DEFAULT_STATE_FILE
    return {
        "base_python": base_python,
        "executable": executable,
        "state_file": state_file,
        "alias": args.alias or DEFAULT_ALIAS,
        "mcp_port": int(args.mcp_port),
        "ai_port": int(args.ai_port),
        "timeout": float(args.timeout),
    }


def command_start(args: argparse.Namespace) -> int:
    try:
        paths = _cli_paths(args)
        base_python: Path = paths["base_python"]
        runtime = validate_runtime(base_python)
    except RuntimeCheckError as exc:
        _emit({"status": "blocked", "error": exc.code})
        return 2

    executable: Path = paths["executable"]
    state_file: Path = paths["state_file"]
    mcp_port: int = paths["mcp_port"]
    ai_port: int = paths["ai_port"]
    timeout: float = paths["timeout"]

    if not executable.is_file():
        _emit({"status": "blocked", "error": "cli_executable_missing",
               "executable": str(executable)})
        return 2
    if (mcp_port == ai_port or not (1 <= mcp_port <= 65535)
            or not (1 <= ai_port <= 65535)):
        _emit({"status": "blocked", "error": "invalid_port_pair"})
        return 2

    existing = read_state(state_file)
    if existing is not None:
        reconciliation = _reconcile_existing(state_file, existing, base_python)
        if reconciliation.get("status") in ("unverified", "partial"):
            _emit({"status": "refused", "error": "legacy_state_unverified",
                   "detail": reconciliation.get("detail")
                   or reconciliation.get("verifications"),
                   "state_file": str(state_file)})
            return 3

    for port in (mcp_port, ai_port):
        if port_in_use(port):
            _emit({"status": "refused", "error": "port_occupied", "port": port})
            return 3

    try:
        fingerprint = probe_runtime_fingerprint(base_python)
    except RuntimeCheckError as exc:
        _emit({"status": "blocked", "error": exc.code})
        return 2
    except (OSError, subprocess.SubprocessError) as exc:
        _emit({"status": "blocked", "error": "runtime_fingerprint_failed",
               "detail": type(exc).__name__})
        return 2

    run_id = f"core069-{uuid.uuid4().hex[:12]}"
    run_dir = state_file.parent / run_id
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    started: Dict[str, Dict[str, Any]] = {}
    spawned: Dict[str, subprocess.Popen] = {}
    state: Dict[str, Any] = {
        "run_id": run_id,
        "created_at": _now_iso(),
        "host": "127.0.0.1",
        "ports": {"mcp": mcp_port, "ai": ai_port},
        "alias": paths["alias"],
        "runtime": {**runtime, "fingerprint": fingerprint},
        "services": started,
    }

    def fail(code: str, detail: Any = None) -> int:
        cleanup = {}
        for name, process in spawned.items():
            cleanup[name] = _stop_spawned_process(process, started[name])
        cleaned = all(item.get("stopped") for item in cleanup.values())
        detail_payload = {"code_check": detail, "cleanup": cleanup}
        if cleaned:
            archive_state(state_file, state, "start-failed", detail_payload)
        else:
            state["last_failure"] = detail_payload
            write_state(state_file, state)
        _emit({"status": "failed", "error": code, "detail": detail_payload,
               "run_id": run_id, "state_file": (str(state_file)
                                                 if not cleaned else None)})
        return 1

    # --- MCP first: the AI process resolves its SSE URL at import time. ---
    mcp_root = REPO_ROOT / "POI_service"
    mcp_argv = build_service_argv(
        mcp_root, "app.api.mcp.tools", [], base_python)
    try:
        mcp_env = child_environment(mcp_environment(mcp_port))
    except GuardCarrierOverride:
        return fail(GUARD_CARRIER_OVERRIDE)
    try:
        process, mcp_record = _spawn(
            SERVICE_MCP, mcp_argv, mcp_root, mcp_env, run_dir, flags,
            SERVICE_MCP, "app.api.mcp.tools", [], base_python)
    except OSError as exc:
        return fail("mcp_spawn_failed", type(exc).__name__)
    mcp_record["port"] = mcp_port
    started[SERVICE_MCP] = mcp_record
    spawned[SERVICE_MCP] = process
    if not isinstance(mcp_record.get("creation_time"), int):
        return fail("mcp_identity_missing")
    if not _wait_until(lambda: listener_matches_pid(mcp_port, process.pid),
                       timeout):
        return fail("listener_not_owned", {
            "pid": process.pid,
            "listener_pids": list(listener_pids(mcp_port)),
            "exit_code": process.poll()})
    sse = probe_mcp_sse(mcp_port)
    mcp_record["health"] = {"checked_at": _now_iso(), **sse}
    if not sse.get("ok"):
        return fail("mcp_sse_unhealthy", sse)

    # --- AI service ---
    ai_root = REPO_ROOT / "ai_service"
    ai_args = ["main:app", "--host", "127.0.0.1", "--port", str(ai_port),
               "--log-level", "info"]
    ai_argv = build_service_argv(ai_root, "uvicorn", ai_args, base_python)
    try:
        ai_env = child_environment(
            ai_environment(mcp_port, paths["alias"], executable))
    except GuardCarrierOverride:
        return fail(GUARD_CARRIER_OVERRIDE)
    try:
        process, ai_record = _spawn(
            SERVICE_AI, ai_argv, ai_root, ai_env, run_dir, flags,
            SERVICE_AI, "uvicorn", ai_args, base_python)
    except OSError as exc:
        return fail("ai_spawn_failed", type(exc).__name__)
    ai_record["port"] = ai_port
    started[SERVICE_AI] = ai_record
    spawned[SERVICE_AI] = process
    if not isinstance(ai_record.get("creation_time"), int):
        return fail("ai_identity_missing")
    if not _wait_until(lambda: (listener_matches_pid(ai_port, process.pid)
                                and probe_ai_health(ai_port).get("ok") is True),
                       timeout):
        return fail("ai_not_ready", {
            "pid": process.pid,
            "listener_pids": list(listener_pids(ai_port)),
            "exit_code": process.poll(),
            "health": probe_ai_health(ai_port)})
    ai_record["health"] = {"checked_at": _now_iso(), **probe_ai_health(ai_port)}

    write_state(state_file, state)
    _emit({
        "status": "started",
        "run_id": run_id,
        "host": "127.0.0.1",
        "ports": {"mcp": mcp_port, "ai": ai_port},
        "ui_url": f"{BASE_URL}:{ai_port}/travel",
        "runtime": {
            "python": fingerprint.get("python"),
            "base_python": fingerprint.get("base_python"),
            "base_python_sha256": fingerprint.get("base_python_sha256"),
            "mcp": fingerprint.get("mcp"),
            "neo4j": fingerprint.get("neo4j"),
            "site_packages": fingerprint.get("site_packages"),
        },
        "services": {
            name: {
                "pid": record["pid"],
                "creation_time": record.get("creation_time"),
                "image": record.get("image"),
                "image_sha256": record.get("image_sha256"),
                "port": record["port"],
                "health": record.get("health"),
                "stdout_log": record["stdout_log"],
                "stderr_log": record["stderr_log"],
            }
            for name, record in started.items()
        },
        "state_file": str(state_file),
        "stop_command": f"python {Path(__file__).name} stop --state-file {state_file}",
    })
    return 0


def command_status(args: argparse.Namespace) -> int:
    try:
        paths = _cli_paths(args)
        base_python = paths["base_python"]
    except RuntimeCheckError as exc:
        _emit({"status": "blocked", "error": exc.code})
        return 2
    state = read_state(paths["state_file"])
    if state is None:
        _emit({"status": "not_started", "state_file": str(paths["state_file"])})
        return 0
    services = {}
    all_owned = True
    for name, record in (state.get("services") or {}).items():
        ownership = verify_record(record, require_listener=True,
                                  expected_image=base_python, service=name)
        health: Dict[str, Any] = {}
        if ownership.get("owned"):
            health = (probe_mcp_sse(record["port"])
                      if name == SERVICE_MCP else probe_ai_health(record["port"]))
        else:
            all_owned = False
        services[name] = {
            "pid": record.get("pid"),
            "creation_time": record.get("creation_time"),
            "port": record.get("port"),
            "owned": ownership.get("owned"),
            "reason": ownership.get("reason"),
            "listener_pids": ownership.get("listener_pids"),
            "image_sha256": ownership.get("image_sha256"),
            "health": health,
        }
    _emit({"status": "running" if all_owned else "degraded",
           "run_id": state.get("run_id"),
           "ports": state.get("ports"),
           "runtime": state.get("runtime"),
           "services": services,
           "state_file": str(paths["state_file"])})
    return 0 if all_owned else 1


def command_stop(args: argparse.Namespace) -> int:
    try:
        paths = _cli_paths(args)
        base_python = paths["base_python"]
    except RuntimeCheckError as exc:
        _emit({"status": "blocked", "error": exc.code})
        return 2
    state_file: Path = paths["state_file"]
    state = read_state(state_file)
    if state is None:
        _emit({"status": "not_started", "state_file": str(state_file)})
        return 0

    results: Dict[str, Any] = {}
    remaining: Dict[str, Any] = {}
    for name, record in (state.get("services") or {}).items():
        result = _terminate_verified_record(record, base_python, service=name)
        results[name] = result
        if not result.get("stopped"):
            remaining[name] = record
    # A verified legacy launcher must not outlive its child.
    for name, record in (state.get("services") or {}).items():
        if results.get(name, {}).get("stopped"):
            launcher = _stop_legacy_launcher(record, service=name)
            if launcher is not None:
                results[f"{name}_launcher"] = launcher
                if not launcher.get("stopped"):
                    remaining.setdefault(name, record)
    ports_after = {name: list(listener_pids(int(record.get("port", 0))))
                   for name, record in (state.get("services") or {}).items()}
    foreign_ports = {name: owners for name, owners in ports_after.items()
                     if owners}
    if foreign_ports:
        for name, owners in foreign_ports.items():
            if name not in remaining:
                remaining[name] = (state.get("services") or {})[name]
            results[name] = {**results.get(name, {}),
                             "stopped": False,
                             "reason": "port_still_owned",
                             "listener_pids_after": owners}

    stopped_all = not remaining
    if stopped_all:
        archive_state(state_file, state, "stopped",
                      {"results": results, "ports_after": ports_after})
        try:
            state_file.unlink()
        except OSError:
            pass
    else:
        state["services"] = remaining
        state["last_stop"] = {"at": _now_iso(), "results": results,
                              "ports_after": ports_after}
        write_state(state_file, state)
    _emit({"status": "stopped" if stopped_all else "partial",
           "run_id": state.get("run_id"),
           "services": results,
           "ports_after": ports_after,
           "remaining_state_file": (None if stopped_all else str(state_file))})
    return 0 if stopped_all else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CORE-069 owned loopback launcher for the POI MCP and AI services.")
    parser.add_argument("action", choices=("start", "status", "stop"))
    parser.add_argument("--mcp-port", type=int, default=DEFAULT_MCP_PORT)
    parser.add_argument("--ai-port", type=int, default=DEFAULT_AI_PORT)
    parser.add_argument("--alias", default=DEFAULT_ALIAS)
    parser.add_argument("--executable", default="")
    parser.add_argument("--python", default="",
                        help="base interpreter or a venv redirector to resolve")
    parser.add_argument("--state-file", default="")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action == "start":
        return command_start(args)
    if args.action == "status":
        return command_status(args)
    return command_stop(args)


if __name__ == "__main__":
    sys.exit(main())
