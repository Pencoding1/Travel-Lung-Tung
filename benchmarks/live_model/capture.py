"""Subprocess execution of the OpenCode CLI, scoped to a single observation.

Design guarantees (repair OC-021-R1):

* On Windows the **native ``opencode.exe``** is preferred. ``.cmd``/``.bat``/``.ps1``
  and extensionless shims are rejected by default, because ``shell=False`` alone
  does not make a batch wrapper safe: the wrapper re-parses the command line
  through ``cmd.exe``, where metacharacters (``& | < > ^ %``) in an argument are
  expanded. A native PE executable receives the argument array verbatim from
  CreateProcess, so the prompt is transported exactly.
* The child environment adds only a per-process ``OPENCODE_CONFIG_CONTENT``
  restricting a unique primary experiment agent to ``permission {'*': 'deny'}``
  (no tools). Global config is never read or written.
* A hard per-call timeout terminates the whole process **tree**, reader threads
  capture partial output, and cleanup is bounded so a surviving grandchild holding
  the pipe can never block indefinitely.
* Raw stdout and stderr are always persisted, including on timeout.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .constants import AGENT_SYSTEM_PROMPT, EXPERIMENT_AGENT

# Bounded seconds to wait for the process tree to die and the reader threads.
CLEANUP_TIMEOUT_SECONDS = 5.0
_READ_SIZE = 65536
_UNSAFE_SUFFIXES = (".cmd", ".bat", ".ps1")


class CaptureError(RuntimeError):
    """The CLI could not be located/launched, or the target is unsafe."""


@dataclass
class CallResult:
    argv: List[str]
    exit_code: int
    duration_seconds: float
    timed_out: bool
    raw_stdout_path: str
    stderr_path: str
    started_at_epoch: float
    finished_at_epoch: float

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def agent_config_content(agent_name: str = EXPERIMENT_AGENT) -> str:
    payload = {
        "$schema": "https://opencode.ai/config.json",
        "share": "disabled",
        "agent": {
            agent_name: {
                "description": "OC-021 controlled text-only live-model H2 experiment",
                "mode": "primary",
                "permission": {"*": "deny"},
                "prompt": AGENT_SYSTEM_PROMPT,
            }
        },
    }
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def child_environment(base: Optional[Dict[str, str]] = None,
                      agent_name: str = EXPERIMENT_AGENT) -> Dict[str, str]:
    env = dict(base if base is not None else os.environ)
    env["OPENCODE_CONFIG_CONTENT"] = agent_config_content(agent_name)
    return env


def _accept_executable(path: str, allow_unsafe_wrapper: bool) -> str:
    if os.name != "nt":
        return path
    suffix = Path(path).suffix.lower()
    if suffix == ".exe":
        return path
    if suffix in _UNSAFE_SUFFIXES or suffix == "":
        if allow_unsafe_wrapper:
            return path
        raise CaptureError(
            f"refusing to launch non-native CLI '{path}': a Windows command wrapper "
            "re-parses the command line and cannot transport arguments exactly. "
            "Provide the native opencode.exe (or pass allow_unsafe_wrapper=True).")
    if allow_unsafe_wrapper:
        return path
    raise CaptureError(f"refusing to launch unusual executable '{path}' on Windows")


def _native_from_wrapper(wrapper: str) -> Optional[str]:
    sibling = Path(wrapper).resolve().parent / "node_modules" / "opencode-ai" / "bin" / "opencode.exe"
    return str(sibling) if sibling.exists() else None


def resolve_executable(preferred: Optional[str] = None,
                       allow_unsafe_wrapper: bool = False) -> str:
    """Resolve an executable, preferring a native ``opencode.exe`` on Windows."""
    if preferred:
        path = preferred if Path(preferred).exists() else shutil.which(preferred)
        if not path:
            raise CaptureError(f"--cli not found: {preferred}")
        return _accept_executable(str(path), allow_unsafe_wrapper)

    if os.name == "nt":
        found = shutil.which("opencode.exe")
        if found:
            return found
        for wrapper_name in ("opencode.cmd", "opencode.bat"):
            wrapper = shutil.which(wrapper_name)
            if wrapper:
                native = _native_from_wrapper(wrapper)
                if native:
                    return native
        bare = shutil.which("opencode")
        if bare and Path(bare).suffix.lower() == ".exe":
            return bare
        wrapper = shutil.which("opencode.cmd") or shutil.which("opencode.bat")
        if wrapper:
            return _accept_executable(str(wrapper), allow_unsafe_wrapper)
        raise CaptureError("the native opencode.exe was not found on PATH")

    found = shutil.which("opencode")
    if found:
        return found
    raise CaptureError("the opencode CLI executable was not found on PATH")


def cli_version(executable: str, *, timeout: float = 30.0) -> Optional[str]:
    try:
        proc = subprocess.run([executable, "--version"], capture_output=True,
                              timeout=timeout, text=True, shell=False)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (proc.stdout or proc.stderr or "").strip()
    return text.splitlines()[0] if text else None


def build_argv(executable: str, model: str, agent: str, prompt: str,
               *, pure: bool = False) -> List[str]:
    """The exact CLI command as an argument array (never a shell string).

    ``pure`` adds only the supported ``run --pure`` flag ("run without external
    plugins"); it is not a permission relaxation and never enables ``--auto``.
    """
    argv = [executable, "run"]
    if pure:
        argv.append("--pure")
    argv += [
        "--model", model,
        "--agent", agent,
        "--format", "json",
        prompt,
    ]
    return argv


def build_export_argv(executable: str, session_id: str) -> List[str]:
    """The read-only ``opencode export <sessionID>`` command as an argument array.

    No model request is made. Only the exact observed session id is ever passed
    (never ``--continue``/``--session``/latest/list).
    """
    return [executable, "export", session_id]


def _group_kwargs() -> Dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _pump(stream, sink: List[bytes]) -> None:
    try:
        while True:
            chunk = stream.read(_READ_SIZE)
            if not chunk:
                break
            sink.append(chunk)
    except (ValueError, OSError):
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _terminate_tree(proc: subprocess.Popen) -> None:
    """Kill the whole process tree, bounded, without waiting indefinitely."""
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=CLEANUP_TIMEOUT_SECONDS)
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    try:
        proc.kill()
    except OSError:
        pass


def run_command(argv: Sequence[str], *, raw_stdout_path: Path, stderr_path: Path,
                cwd: Path, timeout: float,
                env: Optional[Dict[str, str]] = None) -> CallResult:
    argv = list(argv)
    raw_stdout_path = Path(raw_stdout_path)
    stderr_path = Path(stderr_path)
    raw_stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)

    started = time.time()
    try:
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=str(cwd), env=env or child_environment(), shell=False,
                                **_group_kwargs())
    except OSError as exc:
        raise CaptureError(f"failed to launch {argv[0]!r}: {exc}")

    out_chunks: List[bytes] = []
    err_chunks: List[bytes] = []
    reader_out = threading.Thread(target=_pump, args=(proc.stdout, out_chunks), daemon=True)
    reader_err = threading.Thread(target=_pump, args=(proc.stderr, err_chunks), daemon=True)
    reader_out.start()
    reader_err.start()

    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_tree(proc)
        try:
            proc.wait(timeout=CLEANUP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            pass

    reader_out.join(CLEANUP_TIMEOUT_SECONDS)
    reader_err.join(CLEANUP_TIMEOUT_SECONDS)
    # Unblock any reader still stuck on a pipe held by a surviving grandchild.
    for stream in (proc.stdout, proc.stderr):
        try:
            stream.close()
        except Exception:
            pass
    reader_out.join(1.0)
    reader_err.join(1.0)
    finished = time.time()

    stdout = b"".join(out_chunks)
    stderr = b"".join(err_chunks)
    raw_stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)

    return CallResult(
        argv=argv,
        exit_code=int(proc.returncode if proc.returncode is not None else -1),
        duration_seconds=finished - started,
        timed_out=timed_out,
        raw_stdout_path=str(raw_stdout_path),
        stderr_path=str(stderr_path),
        started_at_epoch=started,
        finished_at_epoch=finished,
    )


def run_opencode(executable: str, *, model: str, agent: str, prompt: str,
                 raw_stdout_path: Path, stderr_path: Path, cwd: Path,
                 timeout: float, env: Optional[Dict[str, str]] = None,
                 pure: bool = False) -> CallResult:
    argv = build_argv(executable, model, agent, prompt, pure=pure)
    return run_command(argv, raw_stdout_path=raw_stdout_path, stderr_path=stderr_path,
                       cwd=cwd, timeout=timeout, env=env)


def run_export(executable: str, session_id: str, *, raw_stdout_path: Path,
               stderr_path: Path, cwd: Path, timeout: float,
               env: Optional[Dict[str, str]] = None) -> CallResult:
    """Read-only session export through the bounded process-tree capture."""
    argv = build_export_argv(executable, session_id)
    return run_command(argv, raw_stdout_path=raw_stdout_path, stderr_path=stderr_path,
                       cwd=cwd, timeout=timeout, env=env)
