from __future__ import annotations

import json
import sys
from pathlib import Path

from live_model import capture, runner
from live_model.util import sha256_bytes

import fake_events as fe
import fake_session_export as fx

SCENARIOS = runner.load_scenario_inputs(runner.DEFAULT_SCENARIOS)
LEGACY = ("--transport", "legacy-v1")


def _main(args):
    """The V1 session-export contract is retained only on the legacy path."""
    return runner.main([*args, *LEGACY])

PLAN_TEXT = json.dumps({
    "status": "plan", "no_plan_reason": None,
    "days": [{"day_id": "d1", "stops": [
        {"poi_id": "p_food", "arrival": "2026-11-01T09:00:00+07:00",
         "departure": "2026-11-01T10:00:00+07:00"}]}]})

PARTIAL_SCRIPT = "import time; print('EXPORT_PARTIAL', flush=True); time.sleep(30)"


def _raw_executor(lines, exit_code=0, timed_out=False):
    def _run(prompt, raw_path, stderr_path):
        Path(raw_path).write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
        Path(stderr_path).write_bytes(b"")
        return capture.CallResult(
            argv=["opencode", "run"], exit_code=exit_code, duration_seconds=0.5,
            timed_out=timed_out, raw_stdout_path=str(raw_path),
            stderr_path=str(stderr_path), started_at_epoch=0.0, finished_at_epoch=0.5)
    return _run


def _export_executor(payload: bytes, seen: list, exit_code=0, timed_out=False):
    def _run(session_id, export_path, stderr_path):
        seen.append(session_id)
        Path(export_path).write_bytes(payload)
        Path(stderr_path).write_bytes(b"")
        return capture.CallResult(
            argv=["opencode", "export", session_id], exit_code=exit_code,
            duration_seconds=0.2, timed_out=timed_out, raw_stdout_path=str(export_path),
            stderr_path=str(stderr_path), started_at_epoch=0.0, finished_at_epoch=0.2)
    return _run


def _run(tmp_path, lines, model, export_executor=None):
    prompt = runner.prompts.build_prompt("llm_only", SCENARIOS["S01"])
    return runner.run_observation(
        SCENARIOS["S01"], "llm_only", 0, scenario_id="S01", model=model,
        agent="h2-live-collector", dataset_id="ds", prompt=prompt,
        raw_stdout_path=tmp_path / "e.jsonl", stderr_path=tmp_path / "e.err",
        executor=_raw_executor(lines), export_executor=export_executor)


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------
def test_build_export_argv_is_exact_and_read_only():
    assert capture.build_export_argv("oc", "ses_x") == ["oc", "export", "ses_x"]


def test_build_argv_pure_adds_only_the_pure_flag():
    argv = capture.build_argv("oc", "m", "a", "p", pure=True)
    assert argv == ["oc", "run", "--pure", "--model", "m", "--agent", "a",
                    "--format", "json", "p"]
    assert "--auto" not in argv


def test_run_export_uses_bounded_process_tree_capture(monkeypatch, tmp_path):
    monkeypatch.setattr(capture, "build_export_argv",
                        lambda exe, sid: [sys.executable, "-c", PARTIAL_SCRIPT])
    result = capture.run_export("ignored", "ses_x", raw_stdout_path=tmp_path / "out.txt",
                                stderr_path=tmp_path / "err.txt", cwd=tmp_path, timeout=1.0)
    assert result.timed_out is True
    assert "EXPORT_PARTIAL" in (tmp_path / "out.txt").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Authoritative sidecar path (raw stream omits model identity, DS-004 style)
# ---------------------------------------------------------------------------
def test_export_supplies_provenance_and_preserves_raw_bytes(tmp_path):
    lines = fx.raw_events(text=PLAN_TEXT)
    expected_raw = ("\n".join(lines) + "\n").encode("utf-8")
    seen: list = []
    payload = fx.build_export_bytes(text=PLAN_TEXT)
    obs = _run(tmp_path, lines, fx.REQUESTED,
               export_executor=_export_executor(payload, seen))

    assert seen == [fx.SESSION]                       # only the observed session id
    assert obs.provenance_ok and obs.output_ok
    assert obs.provenance_source == "session_export"
    assert obs.observed_model_ids == (fx.REQUESTED,)
    assert obs.observed_provider_ids == (fx.PROVIDER,)
    assert obs.session_export_sha256 == sha256_bytes(payload)
    assert obs.session_export_source == "OpenCode session metadata"
    assert obs.session_export_message_id == fx.MESSAGE
    assert obs.session_export_path.endswith(".session-export.json")
    # The raw capture is byte-for-byte identical (no injected model hints).
    assert (tmp_path / "e.jsonl").read_bytes() == expected_raw


def test_export_metadata_sidecar_is_persisted(tmp_path):
    lines = fx.raw_events(text=PLAN_TEXT)
    payload = fx.build_export_bytes(text=PLAN_TEXT)
    _run(tmp_path, lines, fx.REQUESTED, export_executor=_export_executor(payload, []))
    meta = json.loads((tmp_path / "e.session-meta.json").read_text(encoding="utf-8"))
    assert meta["source"] == "OpenCode session metadata"
    assert meta["export_sha256"] == sha256_bytes(payload)
    assert meta["qualified_model_id"] == fx.REQUESTED
    assert meta["assistant_message_id"] == fx.MESSAGE


def test_malformed_export_sidecar_records_gap(tmp_path):
    _run(tmp_path, fx.raw_events(text=PLAN_TEXT), fx.REQUESTED,
         export_executor=_export_executor(b"not json", []))
    meta = json.loads((tmp_path / "e.session-meta.json").read_text(encoding="utf-8"))
    assert meta["captured"] is True
    assert meta["reason"] == "malformed_session_export"
    assert meta["provenance_ok"] is False


def test_export_not_attempted_without_observed_session(tmp_path):
    lines = [
        json.dumps({"type": "text",
                    "part": {"id": fx.PART_TEXT, "messageID": fx.MESSAGE,
                             "type": "text", "text": PLAN_TEXT}}),
        json.dumps({"type": "step_finish",
                    "part": {"id": fx.PART_FINISH, "reason": "stop",
                             "messageID": fx.MESSAGE, "type": "step-finish",
                             "tokens": {"input": 1, "output": 1, "reasoning": 0,
                                        "total": 2, "cache": {"read": 0, "write": 0}}}}),
    ]

    def _boom(*args, **kwargs):
        raise AssertionError("must not export without an observed session")

    obs = _run(tmp_path, lines, fx.REQUESTED, export_executor=_boom)
    assert obs.rejection_reason == "unknown_session_provenance"
    assert obs.provenance_source is None


def test_failed_export_remains_gap_not_requested_model(tmp_path):
    seen: list = []
    obs = _run(tmp_path, fx.raw_events(text=PLAN_TEXT), fx.REQUESTED,
               export_executor=_export_executor(b"", seen, exit_code=1))
    assert not obs.provenance_ok
    assert obs.rejection_reason == "session_export_failed"
    assert obs.observed_model_ids == ()   # requested is never reported as observed


def test_malformed_export_remains_gap(tmp_path):
    seen: list = []
    obs = _run(tmp_path, fx.raw_events(text=PLAN_TEXT), fx.REQUESTED,
               export_executor=_export_executor(b"not json", seen))
    assert obs.rejection_reason == "malformed_session_export"
    assert obs.observed_model_ids == ()


def test_forged_export_model_remains_gap(tmp_path):
    seen: list = []
    payload = fx.build_export_bytes(text=PLAN_TEXT, model="ds/deepseek-flash-4.1")
    obs = _run(tmp_path, fx.raw_events(text=PLAN_TEXT), fx.REQUESTED,
               export_executor=_export_executor(payload, seen))
    assert obs.rejection_reason == "model_mismatch"
    assert obs.observed_model_ids == ()


# ---------------------------------------------------------------------------
# Existing event-stream path stays supported; conflicts fail closed
# ---------------------------------------------------------------------------
def _identity_raw(model: str) -> list:
    return [
        json.dumps({"type": "step_start", "sessionID": fx.SESSION,
                    "part": {"id": fx.PART_START, "messageID": fx.MESSAGE,
                             "sessionID": fx.SESSION, "type": "step-start"}}),
        fe.model_event(session=fx.SESSION, model=model, provider="aibox"),
        json.dumps({"type": "text", "sessionID": fx.SESSION,
                    "part": {"id": fx.PART_TEXT, "messageID": fx.MESSAGE,
                             "sessionID": fx.SESSION, "type": "text",
                             "text": PLAN_TEXT}}),
        json.dumps({"type": "step_finish", "sessionID": fx.SESSION,
                    "part": {"id": fx.PART_FINISH, "reason": "stop",
                             "messageID": fx.MESSAGE, "sessionID": fx.SESSION,
                             "type": "step-finish", "tokens": {"input": 194,
                             "output": 6, "reasoning": 13, "total": 213,
                             "cache": {"write": 0, "read": 0}}, "cost": 0}}),
    ]


def test_event_stream_path_supported_without_export(tmp_path):
    obs = _run(tmp_path, _identity_raw(fe.MODEL), fe.MODEL)
    assert obs.provenance_ok
    assert obs.provenance_source == "event_stream"
    assert obs.session_export_sha256 is None


def test_consistent_export_with_event_stream_is_recorded(tmp_path):
    seen: list = []
    payload = fx.build_export_bytes(text=PLAN_TEXT, model="ds/deepseek-flash",
                                    provider="aibox")
    obs = _run(tmp_path, _identity_raw(fe.MODEL), fe.MODEL,
               export_executor=_export_executor(payload, seen))
    assert obs.provenance_ok
    assert obs.provenance_source == "event_stream+session_export"
    assert obs.session_export_sha256 == sha256_bytes(payload)


def test_conflicting_export_fails_closed(tmp_path):
    seen: list = []
    payload = fx.build_export_bytes(text=PLAN_TEXT, model="ds/deepseek-flash",
                                    provider="someone-else")
    lines = _identity_raw(fe.MODEL)
    expected_raw = ("\n".join(lines) + "\n").encode("utf-8")
    obs = _run(tmp_path, lines, fe.MODEL,
               export_executor=_export_executor(payload, seen))
    assert not obs.provenance_ok
    assert obs.rejection_reason == "provenance_conflict"
    assert (tmp_path / "e.jsonl").read_bytes() == expected_raw


# ---------------------------------------------------------------------------
# R1: mixed/contradictory raw identity hints fail closed
# ---------------------------------------------------------------------------
def test_raw_identity_reason_accepts_single_exact_match():
    assert runner._raw_identity_reason((fe.MODEL,), ("aibox",), fe.MODEL) is None


def test_raw_identity_reason_rejects_mixed_models():
    reason = runner._raw_identity_reason((fe.MODEL, "other/model"), ("aibox",), fe.MODEL)
    assert reason == "mixed_model_identity"


def test_raw_identity_reason_rejects_mixed_providers():
    reason = runner._raw_identity_reason((fe.MODEL,), ("aibox", "other"), fe.MODEL)
    assert reason == "mixed_provider_identity"


def test_raw_identity_reason_rejects_provider_mismatch():
    reason = runner._raw_identity_reason((fe.MODEL,), ("other",), fe.MODEL)
    assert reason == "provider_mismatch"


def test_raw_identity_reason_rejects_non_exact_model():
    reason = runner._raw_identity_reason(("aibox/ds/deepseek",), ("aibox",), fe.MODEL)
    assert reason == "model_mismatch"


def test_mixed_raw_model_stream_is_gap(tmp_path):
    lines = _identity_raw(fe.MODEL)
    lines.insert(2, fe.model_event(session=fx.SESSION, model="other/model",
                                   provider="aibox"))
    obs = _run(tmp_path, lines, fe.MODEL)
    assert not obs.provenance_ok
    assert obs.rejection_reason == "mixed_model_identity"


# ---------------------------------------------------------------------------
# Frozen fingerprint: old / drifted runs refuse before any write
# ---------------------------------------------------------------------------
def test_old_fingerprint_resume_refused_before_writes(monkeypatch, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    calls = out / "calls.jsonl"
    calls.write_text(json.dumps({"scenario_id": "S01", "condition": "hybrid",
                                 "repetition": 0}) + "\n", encoding="utf-8")
    before = calls.read_bytes()
    old_fp = runner._fingerprint("m", "h2-live-collector", ("hybrid",), 1, 120.0,
                                 "ds", "sha", ["S01"], 1)
    old_fp.pop("provenance_strategy")
    old_fp.pop("pure_mode")
    (out / "manifest.json").write_text(json.dumps({"fingerprint": old_fp}),
                                       encoding="utf-8")
    manifest_before = (out / "manifest.json").read_bytes()

    monkeypatch.setattr(runner, "default_executor",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no call")))
    rc = _main(["--out", str(out), "--execute", "--resume", "--session-export",
                      "--scenario-ids", "S01", "--conditions", "hybrid"])
    assert rc == 2
    assert calls.read_bytes() == before
    assert (out / "manifest.json").read_bytes() == manifest_before
    assert not list(out.rglob("*.session-export.json"))


def test_switching_session_export_refused_on_resume(tmp_path):
    out = tmp_path / "out"
    assert _main(["--out", str(out), "--scenario-ids", "S01"]) == 0
    manifest_before = (out / "manifest.json").read_bytes()
    rc = _main(["--out", str(out), "--scenario-ids", "S01", "--session-export"])
    assert rc == 2
    assert (out / "manifest.json").read_bytes() == manifest_before


def test_provenance_strategy_is_bound_in_manifest(tmp_path):
    out = tmp_path / "out"
    assert _main(["--out", str(out), "--scenario-ids", "S01"]) == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["provenance_strategy"] == "event_stream:v1"
    assert manifest["fingerprint"]["provenance_strategy"] == "event_stream:v1"
    assert manifest["fingerprint"]["pure_mode"] is False
