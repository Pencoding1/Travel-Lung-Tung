from __future__ import annotations

import json
import sys
import time

import pytest

from live_model import capture


TRANSPORT_SCRIPT = "import sys, json; print(json.dumps(sys.argv[1:]))"
PARTIAL_SCRIPT = (
    "import time; print('PARTIAL_MARKER', flush=True); time.sleep(30)")
GRANDCHILD_SCRIPT = (
    "import subprocess, sys, time; print('PARENT_MARKER', flush=True); "
    "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
    "time.sleep(30)")


def test_agent_config_denies_all_tools_and_disables_share():
    config = json.loads(capture.agent_config_content())
    assert config["share"] == "disabled"
    assert config["agent"]["h2-live-collector"]["permission"] == {"*": "deny"}


def test_resolve_prefers_native_exe(monkeypatch):
    monkeypatch.setattr(capture.shutil, "which",
                        lambda name: "C:\\fake\\opencode.exe" if name == "opencode.exe" else None)
    assert capture.resolve_executable() == "C:\\fake\\opencode.exe"


def test_resolve_derives_native_from_cmd_sibling(monkeypatch, tmp_path):
    native = tmp_path / "node_modules" / "opencode-ai" / "bin" / "opencode.exe"
    native.parent.mkdir(parents=True)
    native.write_text("")
    cmd = tmp_path / "opencode.cmd"
    cmd.write_text("@echo off\n")

    def _which(name):
        return {"opencode.exe": None, "opencode.cmd": str(cmd)}.get(name)

    monkeypatch.setattr(capture.shutil, "which", _which)
    assert capture.resolve_executable() == str(native)


def test_resolve_rejects_unsafe_wrapper(monkeypatch, tmp_path):
    cmd = tmp_path / "opencode.cmd"
    cmd.write_text("@echo off\n")
    monkeypatch.setattr(capture.shutil, "which",
                        lambda name: str(cmd) if name == "opencode.cmd" else None)
    with pytest.raises(capture.CaptureError):
        capture.resolve_executable()


def test_resolve_rejects_explicit_cmd(tmp_path):
    if sys.platform != "win32":
        pytest.skip("windows-only transport rule")
    cmd = tmp_path / "opencode.cmd"
    cmd.write_text("@echo off\n")
    with pytest.raises(capture.CaptureError):
        capture.resolve_executable(str(cmd))


def test_literal_metacharacter_prompt_transport(tmp_path):
    tricky = "a&b|c<d>e^f\"g'h\\i%j\nk & calc"
    result = capture.run_command(
        [sys.executable, "-c", TRANSPORT_SCRIPT, tricky],
        raw_stdout_path=tmp_path / "out.txt", stderr_path=tmp_path / "err.txt",
        cwd=tmp_path, timeout=30)
    assert result.exit_code == 0
    received = json.loads((tmp_path / "out.txt").read_text(encoding="utf-8"))
    assert received == [tricky]


def test_timeout_bounds_duration_and_preserves_partial_output(tmp_path):
    started = time.time()
    result = capture.run_command(
        [sys.executable, "-c", PARTIAL_SCRIPT],
        raw_stdout_path=tmp_path / "out.txt", stderr_path=tmp_path / "err.txt",
        cwd=tmp_path, timeout=1.0)
    elapsed = time.time() - started
    assert result.timed_out is True
    assert elapsed < 1.0 + capture.CLEANUP_TIMEOUT_SECONDS + 6.0
    assert "PARTIAL_MARKER" in (tmp_path / "out.txt").read_text(encoding="utf-8")


def test_tree_cleanup_does_not_block_on_grandchild(tmp_path):
    started = time.time()
    result = capture.run_command(
        [sys.executable, "-c", GRANDCHILD_SCRIPT],
        raw_stdout_path=tmp_path / "out.txt", stderr_path=tmp_path / "err.txt",
        cwd=tmp_path, timeout=1.0)
    elapsed = time.time() - started
    assert result.timed_out is True
    assert elapsed < 1.0 + capture.CLEANUP_TIMEOUT_SECONDS + 6.0
    assert "PARENT_MARKER" in (tmp_path / "out.txt").read_text(encoding="utf-8")
