"""T051 follow-up: resolve the native CLI across npm package layouts.

The installed CLI is the npm wrapper (``opencode``/``opencode.cmd``); the adapter
must never launch a wrapper, only the native binary it delegates to. The npm
layout moved from ``node_modules/opencode-ai/bin`` to
``node_modules/@opencode/cli/bin``, which made resolution fail on this host even
though the CLI is installed.
"""

import sys
from pathlib import Path

import pytest
from domains.providers import process

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = REPO_ROOT / "ai_service"
if str(AI_ROOT) not in sys.path:  # pragma: no cover - conftest already does this
    sys.path.insert(0, str(AI_ROOT))


def _make_layout(root: Path, parts) -> Path:
    native = root.joinpath(*parts)
    native.parent.mkdir(parents=True, exist_ok=True)
    native.write_bytes(b"stub")
    wrapper = root / "opencode.cmd"
    wrapper.write_text("@echo off\n", encoding="utf-8")
    return native


def test_legacy_opencode_ai_layout_resolves(tmp_path):
    native = _make_layout(
        tmp_path, ("node_modules", "opencode-ai", "bin", "opencode.exe"))
    resolved = process._native_from_wrapper(str(tmp_path / "opencode.cmd"))
    assert resolved is not None
    assert Path(resolved) == native


def test_scoped_opencode_cli_layout_resolves(tmp_path):
    native = _make_layout(
        tmp_path,
        ("node_modules", "@opencode", "cli", "bin", "opencode.exe"))
    resolved = process._native_from_wrapper(str(tmp_path / "opencode.cmd"))
    assert resolved is not None
    assert Path(resolved) == native


def test_missing_native_keeps_wrapper_refused(tmp_path):
    wrapper = tmp_path / "opencode.cmd"
    wrapper.write_text("@echo off\n", encoding="utf-8")
    assert process._native_from_wrapper(str(wrapper)) is None
    with pytest.raises(process.ModelUnavailableError) as excinfo:
        process._accept_native(str(wrapper))
    assert "cli_unsafe_executable" in str(excinfo.value) or \
        getattr(excinfo.value, "code", "") == "cli_unsafe_executable"


def test_installed_cli_resolves_to_a_native_binary():
    """The host's real installation must resolve; skip when not installed."""
    try:
        resolved = process.resolve_executable()
    except process.ModelUnavailableError as exc:
        pytest.skip(f"opencode CLI not installed here: {exc}")
    assert Path(resolved).is_file()
    assert Path(resolved).suffix.lower() == ".exe"
