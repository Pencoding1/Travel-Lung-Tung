"""Bounded, shell-free subprocess execution for the opt-in CLI transport.

This is a focused production helper (it does not import the development-only
``benchmarks/`` tree). It preserves the accepted transport guarantees:

* ``shell=False`` and an argument array; prompt text is never interpolated into
  PowerShell/cmd;
* on Windows only a native ``.exe`` is accepted (a ``.cmd``/``.bat``/``.ps1``
  wrapper re-parses arguments through cmd.exe and is refused);
* the whole process tree is terminated on timeout/output overflow, bounded by a
  cleanup deadline, and reader threads are joined/closed so a surviving
  grandchild cannot block forever;
* stdio is capped in memory; raw bytes are only persisted by the caller when
  evidence storage is explicitly enabled.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .errors import ModelUnavailableError

CLEANUP_TIMEOUT_SECONDS = 5.0
_POLL_SECONDS = 0.02
_READ_SIZE = 65536
_UNSAFE_SUFFIXES = (".cmd", ".bat", ".ps1")

# The native Windows CreateProcess command line is limited to 32767 UTF-16
# code units including the terminating NUL. Keep a conservative margin below
# the hard limit, and send an oversized prompt through the CLI's documented
# file attachment instead of relying on an OS error.
COMMAND_LINE_SAFE_UTF16_UNITS = 16000
COMMAND_LINE_MAX_UTF16_UNITS = 30000


def command_line_utf16_units(argv: Sequence[str]) -> int:
    """Return the UTF-16 code units of the exact argv Windows would launch."""
    rendered = subprocess.list2cmdline([str(part) for part in argv])
    return len(rendered.encode("utf-16-le")) // 2


def ensure_command_line_size(argv: Sequence[str]) -> int:
    """Fail closed before Popen when argv cannot fit the native limit."""
    units = command_line_utf16_units(argv)
    if units > COMMAND_LINE_MAX_UTF16_UNITS:
        raise ModelUnavailableError(
            "cli_command_line_too_long",
            "The CLI command line exceeds the native Windows limit; no "
            "model call was made.")
    return units


class _Budget:
    """A single shared byte budget for stdout+stderr."""

    def __init__(self, maximum: int):
        self._remaining = maximum
        self._lock = threading.Lock()

    def take(self, count: int) -> int:
        with self._lock:
            allowed = max(0, min(count, self._remaining))
            self._remaining -= allowed
            return allowed


def _pump(stream, sink: List[bytes], budget: _Budget,
          overflow: threading.Event) -> None:
    try:
        read = getattr(stream, "read1", None) or stream.read
        while True:
            chunk = read(_READ_SIZE)
            if not chunk:
                break
            allowed = budget.take(len(chunk))
            if allowed:
                sink.append(chunk[:allowed])
            if allowed < len(chunk):
                overflow.set()
    except (ValueError, OSError):
        pass
    finally:
        try:
            stream.close()
        except Exception:  # noqa: BLE001 - best-effort pipe cleanup
            pass


def _group_kwargs() -> Dict[str, object]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _terminate_tree(proc: "subprocess.Popen[bytes]") -> None:
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=CLEANUP_TIMEOUT_SECONDS,
                           shell=False)
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


_NATIVE_RELATIVE_CANDIDATES = (
    # Legacy npm layout (package "opencode-ai").
    ("node_modules", "opencode-ai", "bin", "opencode.exe"),
    # Current npm layout as installed on this host (opencode v2.0.32).
    ("node_modules", "@opencode", "cli", "bin", "opencode.exe"),
)


def _native_from_wrapper(wrapper: str) -> Optional[str]:
    """Resolve the native binary a Windows command wrapper delegates to.

    The npm package layout changes between releases (``opencode-ai`` ->
    ``@opencode/cli``), so every known layout is tried in order. Returning
    ``None`` keeps the caller's fail-closed refusal: a wrapper is never run.
    """
    parent = Path(wrapper).resolve().parent
    for parts in _NATIVE_RELATIVE_CANDIDATES:
        sibling = parent.joinpath(*parts)
        if sibling.is_file():
            return str(sibling)
    return None


def _accept_native(path: str) -> str:
    if os.name != "nt":
        return path
    suffix = Path(path).suffix.lower()
    if suffix == ".exe":
        return path
    if suffix in _UNSAFE_SUFFIXES:
        native = _native_from_wrapper(path)
        if native:
            return native
        raise ModelUnavailableError(
            "cli_unsafe_executable",
            "Refusing to launch a Windows command wrapper; provide the native "
            "opencode.exe.")
    if suffix == "":
        native = _native_from_wrapper(path)
        if native:
            return native
        raise ModelUnavailableError(
            "cli_unsafe_executable",
            "Refusing to launch an extensionless Windows wrapper; provide the "
            "native opencode.exe.")
    raise ModelUnavailableError("cli_unsafe_executable",
                                "Refusing to launch an unusual executable.")


def resolve_executable(preferred: Optional[str] = None) -> str:
    """Resolve an existing executable without a shell or global config change."""
    if preferred:
        candidate = preferred
        if not Path(candidate).is_file():
            found = shutil.which(candidate)
            if not found:
                raise ModelUnavailableError(
                    "cli_not_found", "The configured OpenCode CLI was not found.")
            candidate = found
        return _accept_native(str(candidate))

    if os.name == "nt":
        found = shutil.which("opencode.exe")
        if found:
            return _accept_native(found)
        for wrapper_name in ("opencode.cmd", "opencode.bat"):
            wrapper = shutil.which(wrapper_name)
            if wrapper:
                native = _native_from_wrapper(wrapper)
                if native:
                    return native
        bare = shutil.which("opencode")
        if bare and Path(bare).suffix.lower() == ".exe":
            return bare
        raise ModelUnavailableError(
            "cli_not_found",
            "The native opencode.exe was not found on PATH; the CLI provider "
            "is unavailable in this runtime.")

    found = shutil.which("opencode")
    if found:
        return _accept_native(found)
    raise ModelUnavailableError(
        "cli_not_found",
        "The opencode CLI executable was not found on PATH; the CLI provider "
        "is unavailable in this runtime.")


@dataclass(frozen=True)
class CommandResult:
    argv: List[str]
    exit_code: int
    duration_seconds: float
    timed_out: bool
    output_overflow: bool
    stdout: bytes
    stderr: bytes
    cancelled: bool = False


def run_command(argv: Sequence[str], *, cwd: Path, timeout: float,
                env: Dict[str, str], max_output_bytes: int,
                cancel_event: Optional[threading.Event] = None) -> CommandResult:
    """Run one bounded command and return captured bytes.

    ``argv`` must already be an argument array (never a shell string). The
    caller is responsible for passing a controlled environment.
    """
    args = [str(part) for part in argv]
    if not args:
        raise ModelUnavailableError("cli_launch_failed",
                                    "The CLI command was empty.")
    ensure_command_line_size(args)
    cwd = Path(cwd)
    if not cwd.is_dir():
        raise ModelUnavailableError("cli_launch_failed",
                                    "The CLI working directory is unavailable.")

    started = time.monotonic()
    try:
        proc = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(cwd), env=env, shell=False, **_group_kwargs())
    except OSError as exc:
        # Never embed argv, a prompt, an environment value or the raw OS
        # exception in the surfaced error. WinError 206 is the native
        # command-line-length failure; all other launch failures stay generic.
        if (getattr(exc, "winerror", None) == 206
                or getattr(exc, "errno", None) == 206):
            raise ModelUnavailableError(
                "cli_command_line_too_long",
                "The CLI command line exceeds the native Windows limit; no "
                "model call completed.") from None
        raise ModelUnavailableError("cli_launch_failed",
                                    "Failed to launch the OpenCode CLI.") from None

    budget = _Budget(max(1, int(max_output_bytes)))
    overflow = threading.Event()
    out_chunks: List[bytes] = []
    err_chunks: List[bytes] = []
    reader_out = threading.Thread(target=_pump,
                                  args=(proc.stdout, out_chunks, budget, overflow),
                                  daemon=True)
    reader_err = threading.Thread(target=_pump,
                                  args=(proc.stderr, err_chunks, budget, overflow),
                                  daemon=True)
    reader_out.start()
    reader_err.start()

    timed_out = False
    output_overflow = False
    cancelled = False
    deadline = time.monotonic() + max(0.001, float(timeout))
    while proc.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            _terminate_tree(proc)
            break
        if overflow.is_set():
            output_overflow = True
            _terminate_tree(proc)
            break
        if time.monotonic() >= deadline:
            timed_out = True
            _terminate_tree(proc)
            break
        time.sleep(_POLL_SECONDS)

    try:
        proc.wait(timeout=CLEANUP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _terminate_tree(proc)

    reader_out.join(CLEANUP_TIMEOUT_SECONDS)
    reader_err.join(CLEANUP_TIMEOUT_SECONDS)
    for stream in (proc.stdout, proc.stderr):
        try:
            stream.close()
        except Exception:  # noqa: BLE001 - best-effort unblock
            pass
    reader_out.join(1.0)
    reader_err.join(1.0)

    return CommandResult(
        argv=args,
        exit_code=int(proc.returncode if proc.returncode is not None else -1),
        duration_seconds=time.monotonic() - started,
        timed_out=timed_out,
        output_overflow=output_overflow or overflow.is_set(),
        stdout=b"".join(out_chunks),
        stderr=b"".join(err_chunks),
        cancelled=cancelled,
    )
