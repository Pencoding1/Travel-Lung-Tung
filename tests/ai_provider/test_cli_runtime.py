"""Ownership boundary for the per-call V2 transport directory."""

from types import SimpleNamespace

import pytest
from domains.providers import cli_runtime, process
from domains.providers.errors import ModelUnavailableError


def _config():
    return SimpleNamespace(model="tvlt_qa/synthetic", cli_agent="t051-test-agent")


def test_cleanup_removes_the_directory_it_created(tmp_path):
    paths = cli_runtime.create_transport(_config(), base_dir=tmp_path)
    assert paths.root.is_dir()
    assert (paths.root / cli_runtime.CONFIG_FILENAME).is_file()

    cli_runtime.cleanup_transport(paths)

    assert not paths.root.exists()


def test_cleanup_refuses_a_same_prefix_directory_without_the_owner_marker(tmp_path):
    foreign = tmp_path / (cli_runtime.TRANSPORT_DIR_PREFIX + "foreign")
    foreign.mkdir()
    keep = foreign / "keep.txt"
    keep.write_text("not ours", encoding="utf-8")
    paths = cli_runtime.TransportPaths(
        root=foreign, config=foreign / cli_runtime.CONFIG_FILENAME,
        workdir=foreign)

    cli_runtime.cleanup_transport(paths)

    assert keep.exists()


def test_cleanup_refuses_a_replaced_owner_marker(tmp_path):
    paths = cli_runtime.create_transport(_config(), base_dir=tmp_path)
    keep = paths.root / "keep.txt"
    keep.write_text("still here", encoding="utf-8")
    (paths.root / cli_runtime.OWNER_FILENAME).write_text(
        "someone-else", encoding="utf-8")

    cli_runtime.cleanup_transport(paths)

    assert keep.exists()


def test_cleanup_refuses_a_symlinked_transport_directory(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    keep = target / "keep.txt"
    keep.write_text("target", encoding="utf-8")
    link = tmp_path / (cli_runtime.TRANSPORT_DIR_PREFIX + "link")
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("creating a directory symlink is not permitted here")
    paths = cli_runtime.TransportPaths(
        root=link, config=link / cli_runtime.CONFIG_FILENAME, workdir=link)

    cli_runtime.cleanup_transport(paths)

    assert keep.exists()


def test_prompt_file_writes_exact_utf8_bytes_and_cleanup_removes_it(tmp_path):
    paths = cli_runtime.create_transport(_config(), base_dir=tmp_path)
    prompt = "unicode: \u65e5\u672c\u8a9e \U0001f600\nquotes: \"' backslash: \\\\\n"
    prompt = (prompt * 4000)[:41000]

    target = cli_runtime.write_prompt_file(paths, prompt)

    assert target.name == cli_runtime.PROMPT_FILENAME
    assert target.read_bytes() == prompt.encode("utf-8")
    assert target.read_text(encoding="utf-8") == prompt
    cli_runtime.cleanup_transport(paths)
    assert not target.exists()


def test_prompt_file_owner_tamper_fails_without_writing(tmp_path):
    paths = cli_runtime.create_transport(_config(), base_dir=tmp_path)
    (paths.root / cli_runtime.OWNER_FILENAME).write_text(
        "someone-else", encoding="utf-8")

    with pytest.raises(cli_runtime.PromptFileError) as excinfo:
        cli_runtime.write_prompt_file(paths, "synthetic prompt")

    assert excinfo.value.code == "cli_prompt_file_owner_mismatch"
    assert not (paths.root / cli_runtime.PROMPT_FILENAME).exists()


def test_prompt_file_unavailable_is_a_stable_code(tmp_path):
    paths = cli_runtime.create_transport(_config(), base_dir=tmp_path)
    (paths.root / cli_runtime.PROMPT_FILENAME).mkdir()

    with pytest.raises(cli_runtime.PromptFileError) as excinfo:
        cli_runtime.write_prompt_file(paths, "synthetic prompt")

    assert excinfo.value.code == "cli_prompt_file_unavailable"


def test_winerror_206_is_classified_without_echoing_the_exception(tmp_path,
                                                                  monkeypatch):
    def fail(*_args, **_kwargs):
        raise OSError(206, "synthetic command line error")

    monkeypatch.setattr(process.subprocess, "Popen", fail)
    with pytest.raises(ModelUnavailableError) as excinfo:
        process.run_command(["synthetic.exe", "run"], cwd=tmp_path,
                            timeout=1.0, env={}, max_output_bytes=1024)

    assert excinfo.value.code == "cli_command_line_too_long"
    assert "synthetic command line error" not in str(excinfo.value)


def test_command_line_precheck_rejects_oversize_before_popen(tmp_path,
                                                             monkeypatch):
    called = {"popen": False}

    def fail(*_args, **_kwargs):
        called["popen"] = True
        raise AssertionError("Popen must not be reached")

    monkeypatch.setattr(process.subprocess, "Popen", fail)
    with pytest.raises(ModelUnavailableError) as excinfo:
        process.run_command(["synthetic.exe", "x" * 32000], cwd=tmp_path,
                            timeout=1.0, env={}, max_output_bytes=1024)

    assert excinfo.value.code == "cli_command_line_too_long"
    assert called["popen"] is False
