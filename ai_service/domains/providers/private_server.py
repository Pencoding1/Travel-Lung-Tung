"""Owned, loopback-only private OpenCode server for one transport call.

The installed CLI (v2.0.32) can host the v2 API itself in a foreground process:

``opencode serve --stdio --hostname 127.0.0.1 --port <ephemeral>``

``--stdio`` keeps the server alive while the parent holds the child's stdin and
removes the lease password from the tool environment. The parent creates a fresh
random password for this child only and authenticates HTTP requests as the
``opencode`` Basic user. Nothing global is read, written or registered.

This module owns one such server instance. It proves, before any model request,
that the API answers on the port we launched, that the TCP listener belongs to
the owned process tree, that ``/api/info`` reports the owned server pid and that
the exact per-call agent is projected at the exact Location with the restrict
contract.

Failure is always a sanitized :class:`ServerPreflightError`. Passwords, URLs,
headers, response bodies, prompts and provider configuration are never logged.
"""

from __future__ import annotations

import base64
import ctypes
import http.client
import json
import os
import secrets
import socket
import struct
import subprocess
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import process

DEFAULT_STARTUP_SECONDS = 10.0
DEFAULT_HTTP_TIMEOUT_SECONDS = 2.0
MAX_RESPONSE_BYTES = 262_144
CLOSE_GRACE_SECONDS = process.CLEANUP_TIMEOUT_SECONDS
_AUTH_USERNAME = "opencode"
_POLL_SECONDS = 0.1
_AGENT_POLL_SECONDS = 0.2
_PASSWORD_ENV = "OPENCODE_PASSWORD"
_SERVER_PASSWORD_ENV = "OPENCODE_SERVER_PASSWORD"


class ServerPreflightError(RuntimeError):
    """A bounded, sanitized reason the owned server cannot be trusted."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class AgentProjectionError(RuntimeError):
    """The engine projection differs from the requested transport contract."""

    def __init__(self, code: str, *, retryable: bool = False):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


# ---------------------------------------------------------------------------
# Windows ownership inspection (the same mechanisms already accepted for
# CLI-065); no process is inspected outside the tree we launched.
# ---------------------------------------------------------------------------
def _tcp_listeners(port: int) -> Optional[List[Tuple[str, int]]]:
    """Return ``(host, pid)`` for every TCP listener on ``port``.

    ``None`` means this platform offers no ownership inspection. On Windows a
    failure raises: accepting an unknown listener would defeat the ownership
    proof.
    """
    if os.name != "nt":
        return None
    try:
        size = ctypes.c_ulong(0)
        get_table = ctypes.windll.iphlpapi.GetExtendedTcpTable
        get_table(None, ctypes.byref(size), False, socket.AF_INET, 3, 0)
        buffer = ctypes.create_string_buffer(size.value)
        if get_table(buffer, ctypes.byref(size), False, socket.AF_INET, 3, 0) != 0:
            raise OSError("tcp_table_unavailable")
        raw = buffer.raw
        count = struct.unpack_from("<I", raw)[0]
        rows: List[Tuple[str, int]] = []
        for index in range(count):
            state, address, local_port, _remote, _remote_port, pid = (
                struct.unpack_from("<6I", raw, 4 + 24 * index))
            if socket.ntohs(local_port & 0xFFFF) != port:
                continue
            host = socket.inet_ntoa(struct.pack("<I", address))
            rows.append((host, int(pid)))
        return rows
    except (OSError, ValueError, struct.error) as exc:
        raise ServerPreflightError("server_ownership_unverified") from exc


def _owned_process_tree(root_pid: int) -> set:
    """PIDs in the process tree rooted at ``root_pid`` (bounded depth)."""
    if os.name != "nt":
        return {root_pid}
    try:
        class Entry(ctypes.Structure):
            _fields_ = [
                ("size", ctypes.c_ulong), ("usage", ctypes.c_ulong),
                ("pid", ctypes.c_ulong), ("heap", ctypes.c_size_t),
                ("module", ctypes.c_ulong), ("threads", ctypes.c_ulong),
                ("ppid", ctypes.c_ulong), ("priority", ctypes.c_long),
                ("flags", ctypes.c_ulong), ("exe", ctypes.c_wchar * 260),
            ]

        kernel = ctypes.windll.kernel32
        kernel.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        kernel.Process32FirstW.argtypes = [ctypes.c_void_p,
                                           ctypes.POINTER(Entry)]
        kernel.Process32NextW.argtypes = [ctypes.c_void_p,
                                          ctypes.POINTER(Entry)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.CreateToolhelp32Snapshot(2, 0)
        if handle in (None, ctypes.c_void_p(-1).value):
            raise OSError("process_table_unavailable")
        entry = Entry()
        entry.size = ctypes.sizeof(entry)
        tree: Dict[int, int] = {}
        try:
            more = kernel.Process32FirstW(handle, ctypes.byref(entry))
            while more:
                tree[int(entry.pid)] = int(entry.ppid)
                more = kernel.Process32NextW(handle, ctypes.byref(entry))
        finally:
            kernel.CloseHandle(handle)
        owned = {int(root_pid)}
        for _ in range(12):
            expanded = owned | {pid for pid, ppid in tree.items()
                                if ppid in owned}
            if expanded == owned:
                break
            owned = expanded
        return owned
    except (OSError, ValueError, ctypes.ArgumentError) as exc:
        raise ServerPreflightError("server_ownership_unverified") from exc


def _same_directory(left: Any, right: Path) -> bool:
    if not isinstance(left, str) or not left.strip():
        return False
    try:
        return (os.path.normcase(os.path.realpath(left))
                == os.path.normcase(os.path.realpath(str(right))))
    except (OSError, ValueError):
        return False


def _permission_rules(agent: Mapping[str, Any]) -> List[Dict[str, Any]]:
    rules = agent.get("permissions")
    if not isinstance(rules, list) or not rules:
        raise AgentProjectionError("agent_permissions_missing")
    clean: List[Dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {
                "action", "resource", "effect"}:
            raise AgentProjectionError("agent_permissions_malformed")
        if (not isinstance(rule.get("action"), str)
                or not rule.get("action")
                or not isinstance(rule.get("resource"), str)
                or not rule.get("resource")
                or rule.get("effect") not in ("allow", "deny", "ask")):
            raise AgentProjectionError("agent_permissions_malformed")
        clean.append(rule)
    deny_indexes = [
        index for index, rule in enumerate(clean)
        if rule["action"] == "*" and rule["resource"] == "*"
        and rule["effect"] == "deny"]
    if not deny_indexes:
        raise AgentProjectionError("agent_wildcard_deny_missing")
    # Permission matching is "last matching rule wins" and agent rules append
    # after base rules, so the effective contract is the last universal deny.
    # An earlier deny followed by allow and a final deny is still restrictive.
    deny_index = deny_indexes[-1]
    if any(rule["effect"] in ("allow", "ask") for rule in clean[deny_index + 1:]):
        raise AgentProjectionError("agent_permission_after_deny")
    return clean


def evaluate_agent_projection(envelope: Any, *, agent_id: str, workdir: Path,
                              alias: str) -> Dict[str, Any]:
    """Validate the engine's same-Location agent projection.

    Only the exact requested agent may be present. The effective ruleset must
    contain a universal deny and no allow/ask after it. Unknown shapes fail
    closed. Nothing from ``agent.request`` (headers/body) is returned.
    """
    if not isinstance(envelope, dict):
        raise AgentProjectionError("agent_envelope_malformed")
    location = envelope.get("location")
    if not isinstance(location, dict) or not _same_directory(
            location.get("directory"), workdir):
        raise AgentProjectionError("agent_location_mismatch")
    data = envelope.get("data")
    if not isinstance(data, list):
        raise AgentProjectionError("agent_envelope_malformed")
    matches = [row for row in data
               if isinstance(row, dict) and row.get("id") == agent_id]
    if not matches:
        raise AgentProjectionError("agent_absent", retryable=True)
    if len(matches) != 1:
        raise AgentProjectionError("agent_ambiguous")
    agent = matches[0]
    if agent.get("mode") != "primary":
        raise AgentProjectionError("agent_mode_mismatch")
    from .cli_runtime import AGENT_MAX_STEPS

    steps = agent.get("steps")
    if (isinstance(steps, bool) or not isinstance(steps, int)
            or steps != AGENT_MAX_STEPS):
        raise AgentProjectionError("agent_steps_mismatch")

    system = agent.get("system")
    if not isinstance(system, str):
        request = agent.get("request")
        system = request.get("system") if isinstance(request, dict) else None
    if system != _transport_prompt():
        raise AgentProjectionError("agent_system_mismatch")

    provider_id, model_id = alias.split("/", 1)
    model = agent.get("model")
    model_present = model is not None
    if model_present:
        if not isinstance(model, dict) or set(model) - {
                "id", "providerID", "variant"}:
            raise AgentProjectionError("agent_model_malformed")
        if (model.get("providerID") != provider_id
                or model.get("id") != model_id):
            raise AgentProjectionError("agent_model_mismatch")

    rules = _permission_rules(agent)
    return {
        "status": "agent_projection_verified",
        "agent_id": agent_id,
        "location_verified": True,
        "mode": "primary",
        "steps": AGENT_MAX_STEPS,
        "system_matches": True,
        "model_ref_present": model_present,
        "model_matches": True,
        "wildcard_deny": True,
        "no_allow_after_deny": True,
        "permission_rule_count": len(rules),
    }


def _transport_prompt() -> str:
    from .cli_runtime import TRANSPORT_SYSTEM_PROMPT

    return TRANSPORT_SYSTEM_PROMPT


def _reserve_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reserve:
        reserve.bind(("127.0.0.1", 0))
        return int(reserve.getsockname()[1])


class PrivateServer:
    """One owned private server instance with a bounded lifecycle."""

    def __init__(self, executable: str, workdir: Path,
                 env: Mapping[str, str], *, timeout: float,
                 command: Optional[Sequence[str]] = None):
        self._executable = str(executable)
        self._workdir = Path(workdir)
        self._base_env = dict(env)
        self._timeout = max(0.5, float(timeout))
        self._command = list(command) if command is not None else None
        self._password = ""
        self._child: Optional[subprocess.Popen] = None
        self._port: Optional[int] = None
        self._version: Optional[str] = None
        self._tree: set = set()
        self._ownership_verified = False
        self._started = False
        self._closed = False
        self._closing = False
        self._lock = threading.Lock()
        self._close_event = threading.Event()
        self._close_facts: Optional[Dict[str, Any]] = None
        self._watchdog: Optional[threading.Timer] = None

    # -- lifecycle ---------------------------------------------------------
    def start(self, cancel_event=None) -> None:
        with self._lock:
            if self._started:
                return
            if self._closed or self._closing:
                raise ServerPreflightError("server_closed")
            if cancel_event is not None and cancel_event.is_set():
                raise ServerPreflightError("server_start_cancelled")
            self._port = _reserve_loopback_port()
            self._password = secrets.token_urlsafe(32)
            env = dict(self._base_env)
            env.pop(_SERVER_PASSWORD_ENV, None)
            env[_PASSWORD_ENV] = self._password
            if self._command is not None:
                argv = [str(part).replace("{port}", str(self._port))
                        for part in self._command]
            else:
                argv = [
                    self._executable, "serve", "--stdio",
                    "--hostname", "127.0.0.1", "--port", str(self._port),
                ]
            kwargs: Dict[str, Any] = {
                "cwd": str(self._workdir), "env": env, "shell": False,
                "stdin": subprocess.PIPE, "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if os.name == "nt":
                kwargs["creationflags"] = (
                    subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
            try:
                # Spawn under the lifecycle lock: a delayed worker cannot create
                # a child after close() has begun, and close() either observes
                # this child or start() observes close first.
                self._child = subprocess.Popen(argv, **kwargs)
            except OSError as exc:
                raise ServerPreflightError("server_start_failed") from exc
        self._tree = _owned_process_tree(self._child.pid)
        deadline = time.monotonic() + min(DEFAULT_STARTUP_SECONDS, self._timeout)
        self._await_listener(deadline, cancel_event)
        info = self._await_info(deadline, cancel_event)
        self._version = info
        self._started = True

    def _await_listener(self, deadline: float, cancel_event) -> None:
        assert self._child is not None and self._port is not None
        while time.monotonic() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                raise ServerPreflightError("server_start_cancelled")
            if self._child.poll() is not None:
                raise ServerPreflightError("owned_server_exited")
            # A launcher may spawn the real listener just after Popen; expand
            # the owned tree on each bounded poll (always descendants of root).
            self._tree |= _owned_process_tree(self._child.pid)
            rows = _tcp_listeners(self._port)
            if rows is None:
                return  # no ownership inspection on this platform
            if rows:
                if any(host != "127.0.0.1" for host, _ in rows):
                    raise ServerPreflightError("server_bind_not_loopback")
                if any(pid not in self._tree for _, pid in rows):
                    raise ServerPreflightError("server_listener_not_owned")
                self._ownership_verified = True
                return
            time.sleep(_POLL_SECONDS)
        raise ServerPreflightError("server_startup_deadline")

    def _await_info(self, deadline: float, cancel_event) -> str:
        assert self._child is not None and self._port is not None
        while time.monotonic() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                raise ServerPreflightError("server_start_cancelled")
            if self._child.poll() is not None:
                raise ServerPreflightError("owned_server_exited")
            try:
                info = self._request_json("/api/info", (), deadline,
                                          retry_non200=True)
            except _RetryableHttp:
                time.sleep(_POLL_SECONDS)
                continue
            pid = info.get("pid") if isinstance(info, dict) else None
            if isinstance(pid, bool) or not isinstance(pid, int):
                raise ServerPreflightError("server_identity_malformed")
            if pid not in self._tree or pid != self._child.pid:
                raise ServerPreflightError("server_identity_not_owned")
            if self._ownership_verified:
                rows = _tcp_listeners(self._port) or []
                if not rows or any(owner != pid for _, owner in rows):
                    raise ServerPreflightError("server_identity_not_owned")
            version = info.get("version")
            if not isinstance(version, str) or not version.strip():
                raise ServerPreflightError("server_identity_malformed")
            return version.strip()[:64]
        raise ServerPreflightError("server_startup_deadline")

    def preflight(self, agent_id: str, workdir: Path, alias: str,
                  *, cancel_event=None) -> Dict[str, Any]:
        """Poll the same instance until the exact agent is projected."""
        if not self._started:
            raise ServerPreflightError("server_not_started")
        deadline = time.monotonic() + min(DEFAULT_STARTUP_SECONDS, self._timeout)
        params = (("location[directory]", str(Path(workdir))),)
        while time.monotonic() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                raise ServerPreflightError("server_preflight_cancelled")
            if self._child is not None and self._child.poll() is not None:
                raise ServerPreflightError("owned_server_exited")
            try:
                envelope = self._request_json("/api/agent", params, deadline)
            except _RetryableHttp:
                time.sleep(_AGENT_POLL_SECONDS)
                continue
            try:
                return evaluate_agent_projection(
                    envelope, agent_id=agent_id, workdir=Path(workdir),
                    alias=alias)
            except AgentProjectionError as exc:
                if not exc.retryable:
                    raise
                time.sleep(_AGENT_POLL_SECONDS)
        raise ServerPreflightError("agent_projection_deadline")

    # -- HTTP --------------------------------------------------------------
    def _request_json(self, path: str, params: Sequence[Tuple[str, str]],
                      deadline: float, *, retry_non200: bool = False) -> Any:
        assert self._port is not None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ServerPreflightError("server_request_deadline")
        target = path
        if params:
            target += "?" + urllib.parse.urlencode(list(params))
        authorization = "Basic " + base64.b64encode(
            f"{_AUTH_USERNAME}:{self._password}".encode("utf-8")).decode("ascii")
        connection = http.client.HTTPConnection(
            "127.0.0.1", self._port,
            timeout=min(DEFAULT_HTTP_TIMEOUT_SECONDS, remaining))
        socket_holder: Dict[str, socket.socket] = {}
        aborted = threading.Event()

        def _abort() -> None:
            aborted.set()
            sock = socket_holder.get("sock")
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            try:
                connection.close()
            except OSError:
                pass

        watchdog: Optional[threading.Timer] = None
        try:
            # Connect explicitly so the watchdog can own the actual socket.
            connection.connect()
            sock = connection.sock
            if sock is not None:
                socket_holder["sock"] = sock
                self._watchdog = threading.Timer(
                    max(0.001, deadline - time.monotonic()), _abort)
                self._watchdog.daemon = True
                watchdog = self._watchdog
                watchdog.start()
            connection.request("GET", target, headers={
                "Accept": "application/json",
                "Authorization": authorization,
            })
            response = connection.getresponse()
            if aborted.is_set() or time.monotonic() >= deadline:
                raise ServerPreflightError("server_request_deadline")
            status = int(response.status)
            if status in (301, 302, 303, 307, 308):
                raise ServerPreflightError("server_redirect_refused")
            if status in (401, 403):
                raise ServerPreflightError("server_auth_refused")
            if status == 429:
                raise ServerPreflightError("server_rate_limited")
            if status == 404 or 500 <= status <= 599:
                # The listener can answer before the API routes are ready.
                if retry_non200:
                    raise _RetryableHttp()
            if status != 200:
                raise ServerPreflightError("server_non200")
            chunks: List[bytes] = []
            total = 0
            while True:
                if aborted.is_set() or time.monotonic() >= deadline:
                    raise ServerPreflightError("server_request_deadline")
                # read1 returns as soon as some body bytes arrive, so a slow
                # trickle cannot consume the budget one recv() at a time.
                chunk = response.read1(MAX_RESPONSE_BYTES + 1 - total)
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise ServerPreflightError("server_response_oversize")
            if aborted.is_set() or time.monotonic() >= deadline:
                raise ServerPreflightError("server_request_deadline")
            raw = b"".join(chunks)
        except ServerPreflightError:
            raise
        except (OSError, http.client.HTTPException):
            if aborted.is_set() or time.monotonic() >= deadline:
                raise ServerPreflightError("server_request_deadline")
            raise _RetryableHttp()
        finally:
            if watchdog is not None:
                watchdog.cancel()
                watchdog.join(timeout=0.2)
                self._watchdog = None
            connection.close()
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ServerPreflightError("server_response_malformed")

    # -- client/cleanup ----------------------------------------------------
    @property
    def url(self) -> str:
        if self._port is None:
            raise ServerPreflightError("server_not_started")
        return f"http://127.0.0.1:{self._port}"

    def client_env(self, base: Optional[Mapping[str, str]] = None
                   ) -> Dict[str, str]:
        env = dict(self._base_env if base is None else base)
        env.pop(_SERVER_PASSWORD_ENV, None)
        env[_PASSWORD_ENV] = self._password
        return env

    def facts(self) -> Dict[str, Any]:
        return {
            "pid": int(self._child.pid) if self._child is not None else None,
            "version": self._version,
            "listener_ownership_verified": self._ownership_verified,
        }

    def close(self) -> Dict[str, Any]:
        """Close stdin, wait, terminate the owned tree if needed, verify port."""
        with self._lock:
            if self._closed:
                return dict(self._close_facts or {})
            if self._closing:
                wait_for_close = True
                child = None
            else:
                wait_for_close = False
                self._closing = True
                child = self._child
        if wait_for_close:
            self._close_event.wait(timeout=CLOSE_GRACE_SECONDS * 2)
            return dict(self._close_facts or {})
        facts: Dict[str, Any] = {
            "stdin_closed": False,
            "process_terminal": False,
            "port_closed": False if self._port is not None else None,
        }
        if child is None:
            with self._lock:
                self._closed = True
                self._close_facts = facts
            self._close_event.set()
            return facts
        if child.stdin is not None:
            try:
                child.stdin.close()
                facts["stdin_closed"] = True
            except OSError:
                pass
        try:
            child.wait(timeout=CLOSE_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            pass
        if child.poll() is None:
            process._terminate_tree(child)
            try:
                child.wait(timeout=CLOSE_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                pass
        facts["process_terminal"] = child.poll() is not None
        if self._port is not None:
            deadline = time.monotonic() + CLOSE_GRACE_SECONDS
            while time.monotonic() < deadline:
                try:
                    rows = _tcp_listeners(self._port)
                except ServerPreflightError:
                    facts["port_closed"] = None
                    break
                if rows is None:
                    facts["port_closed"] = None
                    break
                if not rows:
                    facts["port_closed"] = True
                    break
                time.sleep(_POLL_SECONDS)
        with self._lock:
            self._closed = True
            self._close_facts = facts
        self._close_event.set()
        return facts


class _RetryableHttp(Exception):
    """The server is not answering yet (bounded retry until the deadline)."""


def default_server_factory(executable: str, workdir: Path,
                           env: Mapping[str, str], *, timeout: float,
                           command: Optional[Sequence[str]] = None
                           ) -> PrivateServer:
    return PrivateServer(executable, workdir, env, timeout=timeout,
                         command=command)
