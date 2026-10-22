"""Owned private-server unit tests: projection, HTTP bounds, real lifecycle.

No model is called. The lifecycle test launches a tiny Python HTTP server with
the production ``PrivateServer`` start/preflight/close machinery; the negative
HTTP tests use an in-process loopback handler.
"""

import json
import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from domains.providers import cli_runtime, private_server
from domains.providers.private_server import (MAX_RESPONSE_BYTES,
                                              PrivateServer,
                                              ServerPreflightError,
                                              evaluate_agent_projection,
                                              _owned_process_tree,
                                              _tcp_listeners)

from helpers_provider import python_executable


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    mode = "ok"
    body = b"{}"

    def log_message(self, *_args):
        pass

    def do_GET(self):
        mode = self.server.mode
        if mode == "redirect":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:1/elsewhere")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if mode in ("401", "403", "429", "500"):
            status = int(mode)
            raw = b'{"error":"synthetic"}'
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if mode == "oversize":
            raw = b"x" * (MAX_RESPONSE_BYTES + 10)
        elif mode == "malformed":
            raw = b"{not json"
        else:
            raw = self.server.body
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _server_with_mode(mode, body=b"{}"):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.mode = mode
    httpd.body = body
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def _unstarted_server(port):
    server = PrivateServer(python_executable(), Path.cwd(), {}, timeout=5)
    server._port = port
    server._password = "synthetic-not-a-secret"
    return server


@pytest.mark.parametrize("mode,code", [
    ("401", "server_auth_refused"),
    ("403", "server_auth_refused"),
    ("429", "server_rate_limited"),
    ("500", "server_non200"),
    ("redirect", "server_redirect_refused"),
    ("oversize", "server_response_oversize"),
    ("malformed", "server_response_malformed"),
])
def test_http_failures_are_bounded_and_sanitized(mode, code):
    httpd = _server_with_mode(mode)
    try:
        server = _unstarted_server(httpd.server_address[1])
        with pytest.raises(ServerPreflightError) as excinfo:
            server._request_json("/api/agent", (), time.monotonic() + 5)
        assert excinfo.value.code == code
        assert "synthetic-not-a-secret" not in str(excinfo.value)
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_http_success_returns_json_and_never_logs_the_password():
    envelope = {"location": {"directory": str(Path.cwd())}, "data": []}
    httpd = _server_with_mode("ok", json.dumps(envelope).encode())
    try:
        server = _unstarted_server(httpd.server_address[1])
        assert server._request_json(
            "/api/agent", (), time.monotonic() + 5) == envelope
        assert server._watchdog is None
        assert "synthetic-not-a-secret" not in repr(server.facts())
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_expired_deadline_refuses_before_connecting():
    server = _unstarted_server(9)
    with pytest.raises(ServerPreflightError) as excinfo:
        server._request_json("/api/info", (), time.monotonic() - 1)
    assert excinfo.value.code == "server_request_deadline"


class _SlowHttpListener:
    """Trickle headers or body without ever exceeding the socket idle timeout."""

    def __init__(self, mode):
        self.mode = mode
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(1)
        self.port = int(self._listener.getsockname()[1])
        self._stop = threading.Event()
        self._connection = None
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        try:
            connection, _ = self._listener.accept()
        except OSError:
            return
        self._connection = connection
        try:
            with connection:
                connection.settimeout(2)
                request = b""
                while b"\r\n\r\n" not in request:
                    chunk = connection.recv(4096)
                    if not chunk:
                        return
                    request += chunk
                if self.mode == "headers":
                    for line in (b"HTTP/1.1 200 OK\r\n",
                                 b"Content-Type: application/json\r\n",
                                 b"Content-Length: 2\r\n", b"\r\n"):
                        if self._stop.is_set():
                            return
                        connection.sendall(line)
                        time.sleep(0.15)
                    connection.sendall(b"{}")
                else:
                    connection.sendall(
                        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                        b"Content-Length: 40\r\n\r\n")
                    for _ in range(10):
                        if self._stop.is_set():
                            return
                        connection.sendall(b"x" * 4)
                        time.sleep(0.1)
        except OSError:
            return

    def close(self):
        self._stop.set()
        try:
            self._listener.close()
        except OSError:
            pass
        connection = self._connection
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass
        self._thread.join(timeout=1)


@pytest.mark.parametrize("mode", ["headers", "body"])
def test_total_deadline_covers_slow_headers_and_slow_body(mode):
    listener = _SlowHttpListener(mode)
    try:
        server = _unstarted_server(listener.port)
        started = time.monotonic()
        with pytest.raises(ServerPreflightError) as excinfo:
            server._request_json("/api/info", (), time.monotonic() + 0.25)
        elapsed = time.monotonic() - started
        assert excinfo.value.code == "server_request_deadline"
        assert elapsed < 0.85
        assert server._watchdog is None
    finally:
        listener.close()


def _refuse_popen(monkeypatch):
    calls = []

    def _popen(argv, **kwargs):
        calls.append((argv, kwargs))
        raise AssertionError("Popen must not be reached")

    monkeypatch.setattr(private_server.subprocess, "Popen", _popen)
    return calls


def test_cancelled_before_start_never_spawns(monkeypatch, tmp_path):
    calls = _refuse_popen(monkeypatch)
    server = PrivateServer(python_executable(), tmp_path, {}, timeout=2)
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(ServerPreflightError) as excinfo:
        server.start(cancelled)
    assert excinfo.value.code == "server_start_cancelled"
    assert calls == []


def test_closed_before_start_never_spawns(monkeypatch, tmp_path):
    calls = _refuse_popen(monkeypatch)
    server = PrivateServer(python_executable(), tmp_path, {}, timeout=2)
    server.close()
    with pytest.raises(ServerPreflightError) as excinfo:
        server.start()
    assert excinfo.value.code == "server_closed"
    assert calls == []


def test_delayed_start_worker_after_close_never_spawns(monkeypatch, tmp_path):
    calls = _refuse_popen(monkeypatch)
    server = PrivateServer(python_executable(), tmp_path, {}, timeout=2)
    release = threading.Event()
    outcome = {}

    def delayed_worker():
        release.wait(timeout=2)
        try:
            server.start()
        except ServerPreflightError as exc:
            outcome["code"] = exc.code

    worker = threading.Thread(target=delayed_worker)
    worker.start()
    server.close()
    release.set()
    worker.join(timeout=2)
    assert outcome.get("code") == "server_closed"
    assert calls == []


_FAKE_SERVER = r"""
import json, os, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

port = int(sys.argv[1])

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *_args):
        pass
    def do_GET(self):
        if self.path.split("?")[0] == "/api/info":
            payload = {"pid": os.getpid(), "version": "2.0.32-lifecycle-test"}
        else:
            payload = {
                "location": {"directory": os.getcwd()},
                "data": [{
                    "id": "lifecycle-agent",
                    "name": "lifecycle-agent",
                    "request": {"settings": {}, "headers": {}, "body": {}},
                    "mode": "primary",
                    "hidden": False,
                    "steps": 2,
                    "system": %r,
                    "model": {"providerID": "aibox",
                              "id": "ds/deepseek-flash"},
                    "permissions": %r,
                }],
            }
        raw = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
thread = threading.Thread(target=httpd.serve_forever, daemon=True)
thread.start()
sys.stdin.read()  # the parent's stdin is the lease
httpd.shutdown()
httpd.server_close()
""" % (cli_runtime.TRANSPORT_SYSTEM_PROMPT, cli_runtime.deny_permissions())


def test_real_lifecycle_start_preflight_close(tmp_path):
    direct_python = getattr(sys, "_base_executable", sys.executable)
    server = PrivateServer(
        direct_python, tmp_path, dict(os.environ), timeout=10,
        command=[direct_python, "-c", _FAKE_SERVER, "{port}"])
    server.start()
    try:
        assert server.url.startswith("http://127.0.0.1:")
        facts = server.facts()
        assert isinstance(facts["pid"], int) and facts["pid"] > 0
        if os.name == "nt":
            assert facts["listener_ownership_verified"] is True
            assert _tcp_listeners(int(server.url.rsplit(":", 1)[1]))
            assert facts["pid"] in _owned_process_tree(facts["pid"])
        proof = server.preflight("lifecycle-agent", tmp_path,
                                 "aibox/ds/deepseek-flash")
        assert proof["status"] == "agent_projection_verified"
        assert proof["location_verified"] is True
        assert proof["model_matches"] is True
    finally:
        cleanup = server.close()
    assert cleanup["stdin_closed"] is True
    assert cleanup["process_terminal"] is True
    assert cleanup["port_closed"] is True


def test_projection_rejects_an_empty_or_foreign_location(tmp_path):
    envelope = {"location": {"directory": "C:\\elsewhere"}, "data": []}
    with pytest.raises(Exception) as excinfo:
        evaluate_agent_projection(
            envelope, agent_id="lifecycle-agent", workdir=tmp_path,
            alias="aibox/ds/deepseek-flash")
    assert getattr(excinfo.value, "code", "") == "agent_location_mismatch"


def test_earlier_deny_then_allow_and_final_deny_is_accepted(tmp_path):
    agent = {
        "id": "lifecycle-agent", "name": "lifecycle-agent", "mode": "primary",
        "steps": 2, "system": cli_runtime.TRANSPORT_SYSTEM_PROMPT,
        "permissions": [
            {"action": "*", "resource": "*", "effect": "deny"},
            {"action": "read", "resource": "*", "effect": "allow"},
            {"action": "*", "resource": "*", "effect": "deny"},
        ],
    }
    envelope = {"location": {"directory": str(tmp_path)}, "data": [agent]}
    proof = evaluate_agent_projection(
        envelope, agent_id="lifecycle-agent", workdir=tmp_path,
        alias="aibox/ds/deepseek-flash")
    assert proof["wildcard_deny"] is True
    assert proof["no_allow_after_deny"] is True


def test_later_allow_after_the_final_deny_is_still_refused(tmp_path):
    agent = {
        "id": "lifecycle-agent", "name": "lifecycle-agent", "mode": "primary",
        "steps": 2, "system": cli_runtime.TRANSPORT_SYSTEM_PROMPT,
        "permissions": [
            {"action": "*", "resource": "*", "effect": "deny"},
            {"action": "*", "resource": "*", "effect": "deny"},
            {"action": "read", "resource": "*", "effect": "allow"},
        ],
    }
    envelope = {"location": {"directory": str(tmp_path)}, "data": [agent]}
    with pytest.raises(Exception) as excinfo:
        evaluate_agent_projection(
            envelope, agent_id="lifecycle-agent", workdir=tmp_path,
            alias="aibox/ds/deepseek-flash")
    assert getattr(excinfo.value, "code", "") == "agent_permission_after_deny"
