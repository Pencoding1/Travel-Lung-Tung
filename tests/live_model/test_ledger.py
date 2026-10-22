"""Lossless, fail-closed run-state persistence tests (fake events only)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from live_model import capture, ledger, runner

import fake_events as fe

MODEL = fe.MODEL
HYBRID_TEXT = json.dumps({"ordered_poi_ids": ["p_food", "p_cafe"]})
LEGACY = ("--transport", "legacy-v1")


def _main(args):
    """All ledger behaviour here is the preserved legacy-v1 path."""
    return runner.main([*args, *LEGACY])


def _fake_hybrid_executor(prompt, raw_path, stderr_path):
    events = [fe.step_start(), fe.model_event(), fe.text(value=HYBRID_TEXT),
              fe.step_finish()]
    Path(raw_path).write_text("\n".join(events) + "\n", encoding="utf-8")
    Path(stderr_path).write_text("", encoding="utf-8")
    return capture.CallResult(
        argv=["opencode", "run"], exit_code=0, duration_seconds=0.1, timed_out=False,
        raw_stdout_path=str(raw_path), stderr_path=str(stderr_path),
        started_at_epoch=0.0, finished_at_epoch=0.1)


def _patch(monkeypatch, executor):
    monkeypatch.setattr(runner, "default_executor", lambda *a, **k: executor)
    monkeypatch.setattr(runner.capture, "resolve_executable", lambda *a, **k: "opencode")
    monkeypatch.setattr(runner.capture, "cli_version", lambda *a, **k: "1.0")


def _must_not_call(*args, **kwargs):
    raise AssertionError("must not call the model")


def test_load_ledger_rejects_malformed(tmp_path):
    path = tmp_path / "calls.jsonl"
    path.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(ledger.LedgerError):
        ledger.load_ledger(path)


def test_load_ledger_rejects_duplicate_key(tmp_path):
    path = tmp_path / "calls.jsonl"
    record = json.dumps({"scenario_id": "S01", "condition": "hybrid", "repetition": 0})
    path.write_text(record + "\n" + record + "\n", encoding="utf-8")
    with pytest.raises(ledger.LedgerError):
        ledger.load_ledger(path)


def test_ledger_append_is_durable_and_rejects_duplicate(tmp_path):
    path = tmp_path / "calls.jsonl"
    run = ledger.RunLedger.open(path)
    run.append({"scenario_id": "S01", "condition": "hybrid", "repetition": 0})
    assert path.exists()
    with pytest.raises(ledger.LedgerError):
        run.append({"scenario_id": "S01", "condition": "hybrid", "repetition": 0})


def test_noop_resume_preserves_bytes(monkeypatch, tmp_path):
    out = tmp_path / "out"
    assert _main(["--out", str(out), "--scenario-ids", "S01",
                        "--conditions", "hybrid"]) == 0
    calls = out / "calls.jsonl"
    calls.write_text(json.dumps({
        "scenario_id": "S01", "condition": "hybrid", "repetition": 0,
        "provenance_ok": False, "rejection_reason": "provenance_unproven"}) + "\n",
        encoding="utf-8")
    before = calls.read_bytes()
    _patch(monkeypatch, _must_not_call)
    rc = _main(["--out", str(out), "--execute", "--resume", "--max-calls", "0",
                      "--scenario-ids", "S01", "--conditions", "hybrid"])
    assert rc == 0
    assert calls.read_bytes() == before
    assert len(before) > 0  # the historical record was NOT truncated to 0 bytes
    assert not (out / "run_manifest.json").exists()
    assert not (out / "collector.lock").exists()


def test_partial_continuation_preserves_prefix(monkeypatch, tmp_path):
    out = tmp_path / "out"
    assert _main(["--out", str(out), "--scenario-ids", "S01,S02",
                        "--conditions", "hybrid"]) == 0
    calls = out / "calls.jsonl"
    calls.write_text(json.dumps({
        "scenario_id": "S01", "condition": "hybrid", "repetition": 0,
        "provenance_ok": False}) + "\n", encoding="utf-8")
    prefix = calls.read_bytes()
    _patch(monkeypatch, _fake_hybrid_executor)
    rc = _main(["--out", str(out), "--execute", "--resume", "--max-calls", "1",
                      "--scenario-ids", "S01,S02", "--conditions", "hybrid"])
    assert rc == 0
    data = calls.read_bytes()
    assert data.startswith(prefix)
    lines = [line for line in data.splitlines() if line.strip()]
    keys = [(json.loads(line)["scenario_id"], json.loads(line)["condition"],
             json.loads(line)["repetition"]) for line in lines]
    assert keys == [("S01", "hybrid", 0), ("S02", "hybrid", 0)]


def test_malformed_ledger_fails_closed_unchanged(monkeypatch, tmp_path):
    out = tmp_path / "out"
    assert _main(["--out", str(out), "--scenario-ids", "S01",
                        "--conditions", "hybrid"]) == 0
    calls = out / "calls.jsonl"
    calls.write_text("{broken\n", encoding="utf-8")
    before = calls.read_bytes()
    _patch(monkeypatch, _must_not_call)
    rc = _main(["--out", str(out), "--execute", "--resume",
                      "--scenario-ids", "S01", "--conditions", "hybrid"])
    assert rc == 2
    assert calls.read_bytes() == before
    assert not (out / "collector.lock").exists()


def test_source_drift_fails_before_writes(monkeypatch, tmp_path):
    out = tmp_path / "out"
    assert _main(["--out", str(out), "--scenario-ids", "S01",
                        "--conditions", "hybrid"]) == 0
    manifest = out / "manifest.json"
    before = manifest.read_bytes()
    _patch(monkeypatch, _must_not_call)
    rc = _main(["--out", str(out), "--execute", "--resume",
                      "--model", "someone/other-model",
                      "--scenario-ids", "S01", "--conditions", "hybrid"])
    assert rc == 2
    assert manifest.read_bytes() == before
    assert not (out / "calls.jsonl").exists()


def test_interruption_retains_first_observation(monkeypatch, tmp_path):
    out = tmp_path / "out"
    counter = {"n": 0}

    def _flaky(prompt, raw_path, stderr_path):
        counter["n"] += 1
        if counter["n"] == 2:
            raise RuntimeError("simulated interruption")
        return _fake_hybrid_executor(prompt, raw_path, stderr_path)

    _patch(monkeypatch, _flaky)
    with pytest.raises(RuntimeError):
        _main(["--out", str(out), "--execute", "--scenario-ids", "S01,S02",
                     "--conditions", "hybrid"])
    calls = out / "calls.jsonl"
    first_lines = [line for line in calls.read_text(encoding="utf-8").splitlines()
                   if line.strip()]
    assert len(first_lines) == 1
    assert json.loads(first_lines[0])["scenario_id"] == "S01"
    assert not (out / "collector.lock").exists()

    _patch(monkeypatch, _fake_hybrid_executor)
    rc = _main(["--out", str(out), "--execute", "--resume",
                      "--scenario-ids", "S01,S02", "--conditions", "hybrid"])
    assert rc == 0
    final_lines = [line for line in calls.read_text(encoding="utf-8").splitlines()
                   if line.strip()]
    assert len(final_lines) == 2
    assert final_lines[0] == first_lines[0]


def test_dry_run_over_existing_evidence_does_not_replace_manifest(monkeypatch, tmp_path):
    out = tmp_path / "out"
    manifest_ok = _main(["--out", str(out), "--scenario-ids", "S01",
                               "--conditions", "hybrid"])
    assert manifest_ok == 0
    manifest = out / "manifest.json"
    before = manifest.read_bytes()
    (out / "calls.jsonl").write_text(json.dumps({
        "scenario_id": "S01", "condition": "hybrid", "repetition": 0}) + "\n",
        encoding="utf-8")
    rc = _main(["--out", str(out), "--scenario-ids", "S01", "--conditions",
                      "hybrid"])  # dry run, no --resume
    assert rc == 2
    assert manifest.read_bytes() == before


def test_concurrent_writer_excluded(monkeypatch, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    foreign = out / "collector.lock"
    foreign.write_text("held", encoding="utf-8")
    _patch(monkeypatch, _must_not_call)
    rc = _main(["--out", str(out), "--scenario-ids", "S01",
                      "--conditions", "hybrid"])
    assert rc == 2
    assert foreign.read_text(encoding="utf-8") == "held"


def _seed_ledger(out, record):
    (out / "calls.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")


def test_scenario_selection_drift_rejected(monkeypatch, tmp_path):
    out = tmp_path / "out"
    assert _main(["--out", str(out), "--scenario-ids", "S01",
                        "--conditions", "hybrid"]) == 0
    manifest = out / "manifest.json"
    before = manifest.read_bytes()
    _patch(monkeypatch, _must_not_call)
    rc = _main(["--out", str(out), "--execute", "--resume",
                      "--scenario-ids", "S02", "--conditions", "hybrid"])
    assert rc == 2
    assert manifest.read_bytes() == before
    assert not (out / "calls.jsonl").exists()


def test_reordered_scenario_ids_rejected(monkeypatch, tmp_path):
    out = tmp_path / "out"
    assert _main(["--out", str(out), "--scenario-ids", "S01,S02",
                        "--conditions", "hybrid"]) == 0
    _patch(monkeypatch, _must_not_call)
    rc = _main(["--out", str(out), "--execute", "--resume",
                      "--scenario-ids", "S02,S01", "--conditions", "hybrid"])
    assert rc == 2


def test_duplicate_scenario_ids_rejected(tmp_path):
    out = tmp_path / "out"
    with pytest.raises(SystemExit):
        _main(["--out", str(out), "--scenario-ids", "S01,S01",
                     "--conditions", "hybrid"])
    assert not out.exists()


def test_duplicate_conditions_rejected(tmp_path):
    out = tmp_path / "out"
    with pytest.raises(SystemExit):
        _main(["--out", str(out), "--scenario-ids", "S01",
                     "--conditions", "hybrid,hybrid"])
    assert not out.exists()


@pytest.mark.parametrize("record,code", [
    ({"scenario_id": "S99", "condition": "hybrid", "repetition": 0}, "rogue_scenario"),
    ({"scenario_id": "S01", "condition": "bogus", "repetition": 0}, "rogue_condition"),
    ({"scenario_id": "S01", "condition": "hybrid", "repetition": -1}, "negative_repetition"),
    ({"scenario_id": "S01", "condition": "hybrid", "repetition": 5}, "out_of_range"),
])
def test_rogue_ledger_keys_rejected_unchanged(monkeypatch, tmp_path, record, code):
    out = tmp_path / "out"
    assert _main(["--out", str(out), "--scenario-ids", "S01",
                        "--conditions", "hybrid"]) == 0
    _seed_ledger(out, record)
    calls = out / "calls.jsonl"
    before = calls.read_bytes()
    _patch(monkeypatch, _must_not_call)
    rc = _main(["--out", str(out), "--execute", "--resume",
                      "--scenario-ids", "S01", "--conditions", "hybrid"])
    assert rc == 2, code
    assert calls.read_bytes() == before


@pytest.mark.parametrize("timeout", ["0", "-1", "nan", "inf"])
def test_invalid_timeout_rejected_before_write(tmp_path, timeout):
    out = tmp_path / "out"
    with pytest.raises(SystemExit):
        _main(["--out", str(out), "--scenario-ids", "S01",
                     "--conditions", "hybrid", "--timeout", timeout])
    assert not out.exists()


def test_negative_max_calls_rejected_before_write(tmp_path):
    out = tmp_path / "out"
    with pytest.raises(SystemExit):
        _main(["--out", str(out), "--scenario-ids", "S01",
                     "--conditions", "hybrid", "--max-calls", "-1"])
    assert not out.exists()

