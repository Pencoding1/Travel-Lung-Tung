from __future__ import annotations

import json
from pathlib import Path

import pytest

from live_model import capture, runner
from live_model.constants import (DATASET_CLASS_PRIMARY, DATASET_CLASS_SYNTHETIC,
                                  V2_METHOD_VERSION, V2_MODEL_ID)
from live_model.export import build_h2_records, build_h2_manifest
from live_model.util import sha256_text

import fake_events as fe

MODEL = fe.MODEL
SCENARIOS = runner.load_scenario_inputs(runner.DEFAULT_SCENARIOS)
LEGACY = ("--transport", "legacy-v1")


@pytest.fixture(autouse=True)
def deny_real_production_v2(monkeypatch):
    """No unit test may construct/complete the real V2 provider.

    Tests that exercise the V2 seam install their own scripted fake (which
    overrides this denial); every other test is forced onto explicit legacy-v1
    or a dry run.
    """
    def _deny(*args, **kwargs):
        raise AssertionError("real production-v2 provider/capability/network denied")

    monkeypatch.setattr(runner.v2_transport, "complete_factory", _deny)
    monkeypatch.setattr(runner.v2_transport, "provider_factory", _deny)
    monkeypatch.setattr(runner.capture, "resolve_executable", _deny)


def _make_executor(events, exit_code=0, timed_out=False):
    def _run(prompt, raw_path, stderr_path):
        Path(raw_path).write_text("\n".join(events) + "\n", encoding="utf-8")
        Path(stderr_path).write_text("", encoding="utf-8")
        return capture.CallResult(
            argv=["opencode", "run", "--model", MODEL], exit_code=exit_code,
            duration_seconds=0.5, timed_out=timed_out, raw_stdout_path=str(raw_path),
            stderr_path=str(stderr_path), started_at_epoch=0.0, finished_at_epoch=0.5)
    return _run


def _run_obs(tmp_path, scenario_id, condition, events, **kwargs):
    prompt = runner.prompts.build_prompt(condition, SCENARIOS[scenario_id])
    return runner.run_observation(
        SCENARIOS[scenario_id], condition, 0, scenario_id=scenario_id, model=MODEL,
        agent="h2-live-collector", dataset_id="ds", prompt=prompt,
        raw_stdout_path=tmp_path / "e.jsonl", stderr_path=tmp_path / "e.err",
        executor=_make_executor(events, **kwargs))


PLAN_TEXT = json.dumps({
    "status": "plan", "no_plan_reason": None,
    "days": [{"day_id": "d1", "stops": [
        {"poi_id": "p_food", "arrival": "2026-11-01T09:00:00+07:00",
         "departure": "2026-11-01T10:00:00+07:00"}]}]})
HYBRID_TEXT = json.dumps({"ordered_poi_ids": ["p_food", "p_cafe"]})


def test_valid_llm_only_observation(tmp_path):
    obs = _run_obs(tmp_path, "S01", "llm_only",
                   fe.stream(fe.step_start(), fe.model_event(), fe.text(value=PLAN_TEXT),
                             fe.step_finish()))
    assert obs.provenance_ok and obs.output_ok
    assert obs.run_status == "completed"
    assert obs.selected_poi_ids == ("p_food",)
    assert obs.provider_usage["input_tokens"] == 60


def test_valid_hybrid_observation(tmp_path):
    obs = _run_obs(tmp_path, "S01", "hybrid",
                   fe.stream(fe.step_start(), fe.model_event(), fe.text(value=HYBRID_TEXT),
                             fe.step_finish()))
    assert obs.output_ok
    assert obs.selected_poi_ids == ("p_food", "p_cafe")


def test_error_event_despite_exit_zero(tmp_path):
    obs = _run_obs(tmp_path, "S01", "llm_only",
                   fe.stream(fe.step_start(), fe.model_event(), fe.error("provider failed"),
                             fe.text(value=PLAN_TEXT), fe.step_finish()), exit_code=0)
    assert obs.provenance_ok
    assert not obs.output_ok
    assert "error_event" in obs.invalid_output_reason
    # Provenance is intact, so this is exported as a retained failed run.
    record = build_h2_records([obs])
    assert record and record[0]["run_status"] == "failed"


def test_tool_attempt_rejected(tmp_path):
    obs = _run_obs(tmp_path, "S01", "llm_only",
                   fe.stream(fe.step_start(), fe.model_event(), fe.tool_use("bash"),
                             fe.text(value=PLAN_TEXT), fe.step_finish()))
    assert not obs.output_ok
    assert "tool_use_event" in obs.invalid_output_reason


def test_timeout_rejected(tmp_path):
    obs = _run_obs(tmp_path, "S01", "llm_only",
                   fe.stream(fe.step_start(), fe.model_event()),
                   timed_out=True, exit_code=-1)
    assert not obs.output_ok
    assert "timeout" in obs.invalid_output_reason
    assert obs.run_status == "error"


def test_missing_terminal_rejected(tmp_path):
    obs = _run_obs(tmp_path, "S01", "llm_only",
                   fe.stream(fe.step_start(), fe.model_event(), fe.text(value=PLAN_TEXT)))
    assert "no_terminal_completion" in obs.invalid_output_reason


def test_malformed_model_output_is_failed_run(tmp_path):
    obs = _run_obs(tmp_path, "S01", "llm_only",
                   fe.stream(fe.step_start(), fe.model_event(), fe.text(value="not json"),
                             fe.step_finish()))
    assert not obs.output_ok
    assert obs.run_status == "failed"
    assert obs.invalid_output_reason.startswith("malformed_model_output")


def test_model_mismatch_is_gap(tmp_path):
    obs = _run_obs(tmp_path, "S01", "llm_only",
                   fe.stream(fe.step_start(), fe.model_event(model="someone/else"),
                             fe.text(value=PLAN_TEXT), fe.step_finish()))
    assert not obs.provenance_ok
    assert obs.rejection_reason == "model_mismatch"
    assert build_h2_records([obs]) == []


def test_missing_model_metadata_is_gap(tmp_path):
    obs = _run_obs(tmp_path, "S01", "llm_only",
                   fe.stream(fe.step_start(), fe.text(value=PLAN_TEXT), fe.step_finish()))
    assert obs.rejection_reason == "unknown_model_provenance"


def test_identical_source_hashes_across_arms():
    dataset_id = "ds"
    hyb = runner._provenance(SCENARIOS["S01"], "S01", "hybrid", MODEL, "a", dataset_id)
    llm = runner._provenance(SCENARIOS["S01"], "S01", "llm_only", MODEL, "a", dataset_id)
    for key in ("candidate_id", "route_id", "prompt_information_id", "dataset_id",
                "model_id", "settings_id"):
        assert hyb[key] == llm[key]
    assert hyb["method_instruction_hash"] != llm["method_instruction_hash"]


def test_export_is_oc18_compatible():
    from evaluation.h2 import load_h2_records, parse_h2_manifest

    manifest = parse_h2_manifest(build_h2_manifest(["S01"], 1))
    record = {
        "schema_version": "oc18.h2.v1", "task": "H2", "evidence_level": "live_model",
        "dataset_kind": "synthetic_live_engineering", "scenario_id": "S01",
        "condition": "llm_only", "repetition": 0, "run_status": "completed",
        "plan_present": True, "empty_plan": False, "validation_status": "feasible",
        "unverifiable": False, "temporal_violation": False,
        "known_temporal_violations": 0, "violation_count_complete": True,
        "unknown_reasons": [],
        "provenance": {"candidate_id": "c", "route_id": "r", "prompt_information_id": "p",
                       "dataset_id": "d", "model_id": MODEL, "settings_id": "s",
                       "method_instruction_hash": "m"},
    }
    loaded = load_h2_records([record], manifest)
    assert ("S01", "llm_only", 0) in loaded


def test_execution_order_alternates():
    order = runner.execution_order(["S01", "S02"], 1, ("hybrid", "llm_only"))
    assert order == [("S01", "hybrid", 0), ("S01", "llm_only", 0),
                     ("S02", "llm_only", 0), ("S02", "hybrid", 0)]


def test_dry_run_makes_no_call(monkeypatch, tmp_path):
    def _boom(*args, **kwargs):
        raise AssertionError("dry-run must not call the model")
    monkeypatch.setattr(runner, "default_executor", _boom)
    out = tmp_path / "out"
    rc = runner.main(["--out", str(out), "--scenario-ids", "S01"])
    assert rc == 0
    assert not (out / "calls.jsonl").exists()
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dry_run"] is True
    assert manifest["planned_denominator"] == 2


def _fake_cli_executor(prompt, raw_path, stderr_path):
    value = PLAN_TEXT if "LLM-only" in prompt else HYBRID_TEXT
    events = [fe.step_start(), fe.model_event(), fe.text(value=value), fe.step_finish()]
    Path(raw_path).write_text("\n".join(events) + "\n", encoding="utf-8")
    Path(stderr_path).write_text("", encoding="utf-8")
    return capture.CallResult(
        argv=["opencode", "run"], exit_code=0, duration_seconds=0.1, timed_out=False,
        raw_stdout_path=str(raw_path), stderr_path=str(stderr_path),
        started_at_epoch=0.0, finished_at_epoch=0.1)


def test_execute_end_to_end_export(monkeypatch, tmp_path):
    from evaluation.h2 import load_h2_records, parse_h2_manifest

    out = tmp_path / "out"
    monkeypatch.setattr(runner, "default_executor", lambda *a, **k: _fake_cli_executor)
    monkeypatch.setattr(runner.capture, "resolve_executable", lambda *a, **k: "opencode")
    monkeypatch.setattr(runner.capture, "cli_version", lambda *a, **k: "1.0")
    rc = runner.main(["--out", str(out), "--scenario-ids", "S01", "--execute",
                      *LEGACY])
    assert rc == 0

    lines = [json.loads(line) for line in
             (out / "calls.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2
    by_condition = {line["condition"]: line for line in lines}
    common = ("candidate_id", "route_id", "prompt_information_id", "dataset_id",
              "model_id", "settings_id")
    for key in common:
        assert (by_condition["hybrid"]["provenance"][key]
                == by_condition["llm_only"]["provenance"][key])

    manifest = parse_h2_manifest(json.loads(
        (out / "h2_manifest.json").read_text(encoding="utf-8")))
    records = [json.loads(line) for line in
               (out / "h2_records.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    loaded = load_h2_records(records, manifest)
    assert ("S01", "hybrid", 0) in loaded
    assert ("S01", "llm_only", 0) in loaded
    assert loaded[("S01", "llm_only", 0)]["evidence_level"] == "live_model"


def test_resume_never_overwrites(monkeypatch, tmp_path):
    out = tmp_path / "out"
    monkeypatch.setattr(runner, "default_executor", lambda *a, **k: _fake_cli_executor)
    monkeypatch.setattr(runner.capture, "resolve_executable", lambda *a, **k: "opencode")
    monkeypatch.setattr(runner.capture, "cli_version", lambda *a, **k: "1.0")
    assert runner.main(["--out", str(out), "--scenario-ids", "S01",
                        "--conditions", "hybrid", "--execute", *LEGACY]) == 0
    before = (out / "calls.jsonl").read_bytes()
    before_manifest = (out / "manifest.json").read_bytes()
    before_summary = (out / "run_manifest.json").read_bytes()

    seen = []

    def _fake_executor(*args, **kwargs):
        seen.append(1)
        raise AssertionError("existing evidence must not be re-run")

    monkeypatch.setattr(runner, "default_executor", lambda *a, **k: _fake_executor)
    rc = runner.main(["--out", str(out), "--execute", "--scenario-ids", "S01",
                      "--conditions", "hybrid", "--resume", *LEGACY])
    assert rc == 0
    assert seen == []
    assert (out / "calls.jsonl").read_bytes() == before
    assert (out / "manifest.json").read_bytes() == before_manifest
    # No-op resume writes nothing at all, including aggregates.
    assert (out / "run_manifest.json").read_bytes() == before_summary


def test_resume_requires_compatible_manifest(monkeypatch, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "calls.jsonl").write_text(
        json.dumps({"scenario_id": "S01", "condition": "hybrid", "repetition": 0}) + "\n",
        encoding="utf-8")
    monkeypatch.setattr(runner, "default_executor",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("must not call")))
    rc = runner.main(["--out", str(out), "--execute", "--scenario-ids", "S01",
                      "--conditions", "hybrid", "--resume", *LEGACY])
    assert rc == 2
    assert (out / "calls.jsonl").read_text(encoding="utf-8").strip()


def test_execute_without_resume_rejects_existing_evidence(monkeypatch, tmp_path):
    out = tmp_path / "out"
    monkeypatch.setattr(runner, "default_executor", lambda *a, **k: _fake_cli_executor)
    monkeypatch.setattr(runner.capture, "resolve_executable", lambda *a, **k: "opencode")
    monkeypatch.setattr(runner.capture, "cli_version", lambda *a, **k: "1.0")
    assert runner.main(["--out", str(out), "--scenario-ids", "S01",
                        "--conditions", "hybrid", "--execute", *LEGACY]) == 0
    before = (out / "calls.jsonl").read_bytes()
    rc = runner.main(["--out", str(out), "--scenario-ids", "S01",
                      "--conditions", "hybrid", "--execute", *LEGACY])
    assert rc == 2
    assert (out / "calls.jsonl").read_bytes() == before


# ---------------------------------------------------------------------------
# EXP-074 production-v2 path (scripted provider seam only)
# ---------------------------------------------------------------------------
V2_SENTINEL = "SYNTHETIC_SENTINEL_MUST_NOT_PERSIST"


def _v2_provider(**overrides):
    value = {
        "ok": True,
        "requested_model": V2_MODEL_ID,
        "observed_model": V2_MODEL_ID,
        "observed_provider_id": "opencode-go",
        "observed_model_id": "deepseek-v4.1-flash",
        "session_id": "ses_synthetic_v2",
        "identity_source": "opencode_session_export",
        "finish": "stop",
        "attempts": 1,
        "failed_attempts": 0,
        "usage_components": {"input": 10, "output": 20, "total": 30},
        "usage_total": 30,
        "usage_consistent": True,
        "cli_capabilities": {"version": "2.0.32", "pure_supported": False,
                             "reason": "installed_cli_has_no_pure"},
        "controls": {"requested": {"temperature": 0.2},
                     "configured": {"temperature": 0.2},
                     "applied": False,
                     "verification": "not_observable_from_transport",
                     "binding": "provider_model_request_body",
                     "unsupported": []},
        "transport": {"config_filename": "opencode.json",
                      "config_sha256": "a" * 64, "scope": "child_process"},
        "agent_preflight": {"status": "ok"},
        "headers": {"Authorization": f"Bearer {V2_SENTINEL}"},
        "config": {"OPENCODE_CONFIG_CONTENT": V2_SENTINEL},
        "error_body": V2_SENTINEL,
        "reasoning": V2_SENTINEL,
        "untrusted_debug": {"private": V2_SENTINEL},
    }
    value.update(overrides)
    return value


def _v2_completion(text, *, provider=None):
    return {
        "id": "chatcmpl-synthetic",
        "object": "chat.completion",
        "created": 0,
        "model": V2_MODEL_ID,
        "choices": [{"index": 0,
                     "message": {"role": "assistant", "content": text,
                                 "tool_calls": None},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20,
                  "total_tokens": 30},
        "_provider": _v2_provider() if provider is None else provider,
    }


def _install_v2_fake(monkeypatch, responder):
    calls = []

    def _complete(payload):
        calls.append(payload)
        return responder(payload)

    monkeypatch.setattr(runner.v2_transport, "complete_factory",
                        lambda config, cwd: _complete)
    monkeypatch.setattr(runner.capture, "resolve_executable",
                        lambda *args, **kwargs: "opencode")
    return calls


def _ok_responder(payload):
    prompt = payload["messages"][0]["content"]
    text = PLAN_TEXT if "LLM-only itinerary condition" in prompt else HYBRID_TEXT
    return _v2_completion(text)


def test_v2_dry_run_is_default_and_needs_no_provider(tmp_path):
    out = tmp_path / "out"
    assert runner.main(["--out", str(out), "--scenario-ids", "S01"]) == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["transport"] == "production-v2"
    assert manifest["task_id"] == "EXP-077"
    assert manifest["method_version"] == V2_METHOD_VERSION
    assert manifest["requested_model_id"] == V2_MODEL_ID
    assert manifest["dataset_kind"] == "synthetic_live_engineering"
    assert manifest["thesis_mode"] is False
    assert manifest["thesis_ready"] is False
    assert manifest["accepted_primary_study"] is False
    assert manifest["cli_version_declared_ignored"] is None
    fingerprint = manifest["fingerprint"]
    assert fingerprint["transport"]["version"] == "production-v2"
    assert fingerprint["transport"]["method"] == "OpenCodeCliProvider.complete"
    assert fingerprint["transport"]["cli_pure"] is False
    assert fingerprint["transport"]["system_prompt_sha256"] == sha256_text(
        runner.v2_transport.transport_system_prompt())
    assert fingerprint["planned_denominator"] == 2
    assert not (out / "calls.jsonl").exists()
    assert not (out / "events").exists()


def test_explicit_legacy_transport_is_preserved(tmp_path):
    out = tmp_path / "out"
    assert runner.main(["--out", str(out), "--scenario-ids", "S01",
                        *LEGACY]) == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["transport"] == "legacy-v1"
    assert manifest["task_id"] == "OC-023"
    assert manifest["method_version"] == "oc23.live.v2"
    assert manifest["fingerprint"]["method_version"] == "oc23.live.v2"


def test_v2_vs_legacy_fingerprint_cross_resume_is_rejected(tmp_path):
    out = tmp_path / "out"
    assert runner.main(["--out", str(out), "--scenario-ids", "S01",
                        "--conditions", "hybrid"]) == 0
    before = (out / "manifest.json").read_bytes()
    rc = runner.main(["--out", str(out), "--scenario-ids", "S01",
                      "--conditions", "hybrid", "--resume", "--execute",
                      *LEGACY])
    assert rc == 2
    assert (out / "manifest.json").read_bytes() == before
    assert not (out / "calls.jsonl").exists()


def test_v2_settings_drift_fails_before_provider_invocation(monkeypatch, tmp_path):
    out = tmp_path / "out"
    assert runner.main(["--out", str(out), "--scenario-ids", "S01",
                        "--conditions", "hybrid"]) == 0
    calls = _install_v2_fake(monkeypatch, _ok_responder)
    rc = runner.main(["--out", str(out), "--scenario-ids", "S01",
                      "--conditions", "hybrid", "--resume", "--execute",
                      "--timeout", "60"])
    assert rc == 2
    assert calls == []


def test_v2_scripted_provider_success_end_to_end(monkeypatch, tmp_path):
    from evaluation.h2 import load_h2_records, parse_h2_manifest

    out = tmp_path / "out"
    calls = _install_v2_fake(monkeypatch, _ok_responder)
    assert runner.main(["--out", str(out), "--scenario-ids", "S01",
                        "--execute"]) == 0
    assert len(calls) == 2
    assert calls[0]["model"] == V2_MODEL_ID
    assert calls[0]["messages"][0]["content"] == \
        runner.prompts.build_prompt("hybrid", SCENARIOS["S01"])
    assert calls[1]["messages"][0]["content"] == \
        runner.prompts.build_prompt("llm_only", SCENARIOS["S01"])

    logs = [json.loads(line) for line in
            (out / "calls.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    assert len(logs) == 2
    for log in logs:
        assert log["transport"] == "production-v2"
        assert log["provenance_ok"] is True
        assert log["run_status"] == "completed"
        assert log["identity_source"] == "opencode_session_export"
        assert log["raw_event_path"] is None
        assert log["stderr_path"] is None
        assert log["session_export_path"] is None
        assert log["observed_model_ids"] == [V2_MODEL_ID]
        assert Path(log["assistant_text_path"]).exists()
        assert Path(log["provider_receipt_path"]).exists()
        receipt = json.loads(
            Path(log["provider_receipt_path"]).read_text(encoding="utf-8"))
        assert receipt["kind"] == "derived_structured_service_provider_receipt"
        assert receipt["derived"] is True
        assert receipt["raw_cli_transcript_retained"] is False
        assert receipt["raw_session_export_retained"] is False
        assert receipt["provider"]["observed_model"] == V2_MODEL_ID
        assert V2_SENTINEL not in json.dumps(receipt, sort_keys=True)
        assert set(receipt["provider"]).isdisjoint(
            {"headers", "config", "error_body", "reasoning", "untrusted_debug"})

    assistant = (out / "events" /
                 "S01__hybrid__r0.assistant.txt").read_text(encoding="utf-8")
    assert assistant == HYBRID_TEXT
    assert not list((out / "events").glob("*.jsonl"))

    summary = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    assert summary["records_written"] == 2
    assert summary["gaps"] == []
    assert summary["accepted_primary_study"] is False

    manifest = parse_h2_manifest(json.loads(
        (out / "h2_manifest.json").read_text(encoding="utf-8")))
    records = [json.loads(line) for line in
               (out / "h2_records.jsonl").read_text(encoding="utf-8").splitlines()
               if line.strip()]
    loaded = load_h2_records(records, manifest)
    assert ("S01", "hybrid", 0) in loaded
    assert ("S01", "llm_only", 0) in loaded
    dumped = json.dumps(records, sort_keys=True)
    assert V2_SENTINEL not in dumped


def test_v2_contract_rejection_stays_in_denominator_and_resume_is_noop(
        monkeypatch, tmp_path):
    out = tmp_path / "out"
    calls = _install_v2_fake(
        monkeypatch,
        lambda payload: _v2_completion(
            HYBRID_TEXT, provider=_v2_provider(observed_model="other/model")))
    assert runner.main(["--out", str(out), "--scenario-ids", "S01",
                        "--conditions", "hybrid", "--execute"]) == 0
    assert len(calls) == 1
    logs = [json.loads(line) for line in
            (out / "calls.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    assert len(logs) == 1
    assert logs[0]["provenance_ok"] is False
    assert logs[0]["rejection_reason"] == "provider_contract:model_mismatch"
    assert logs[0]["provider_failure"]["code"] == "model_mismatch"
    summary = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    assert summary["records_written"] == 0
    assert len(summary["gaps"]) == 1

    resume_calls = _install_v2_fake(monkeypatch, _ok_responder)
    assert runner.main(["--out", str(out), "--scenario-ids", "S01",
                        "--conditions", "hybrid", "--execute", "--resume"]) == 0
    assert resume_calls == []
    assert len((out / "calls.jsonl").read_text(
        encoding="utf-8").splitlines()) == 1


def test_v2_provider_exception_keeps_constant_failure_and_no_raw_body(
        monkeypatch, tmp_path):
    from domains.providers.errors import ModelUnavailableError

    out = tmp_path / "out"

    def _boom(payload):
        exc = ModelUnavailableError("provider_timeout",
                                    f"raw {V2_SENTINEL}", retryable=True)
        exc.attempts = 1
        exc.failed_attempts = 1
        raise exc

    calls = _install_v2_fake(monkeypatch, _boom)
    assert runner.main(["--out", str(out), "--scenario-ids", "S01",
                        "--conditions", "hybrid", "--execute"]) == 0
    assert len(calls) == 1
    text = (out / "calls.jsonl").read_text(encoding="utf-8")
    log = json.loads(text.splitlines()[0])
    assert log["provenance_ok"] is False
    assert log["run_status"] == "error"
    assert log["rejection_reason"] == "provider_failure:provider_timeout"
    assert log["provider_failure"] == {
        "code": "provider_timeout", "attempts": 1, "failed_attempts": 1,
        "retryable": True}
    assert V2_SENTINEL not in text


def test_v2_malformed_output_remains_a_failed_denominator_record(
        monkeypatch, tmp_path):
    out = tmp_path / "out"
    calls = _install_v2_fake(
        monkeypatch, lambda payload: _v2_completion("not json"))
    assert runner.main(["--out", str(out), "--scenario-ids", "S01",
                        "--conditions", "hybrid", "--execute"]) == 0
    assert len(calls) == 1
    log = json.loads(
        (out / "calls.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert log["provenance_ok"] is True
    assert log["output_ok"] is False
    assert log["run_status"] == "failed"
    summary = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    assert summary["records_written"] == 1
    assert summary["gaps"] == []


# ---------------------------------------------------------------------------
# Explicit primary declaration (synthetic negative fixtures only)
# ---------------------------------------------------------------------------
PRIMARY_PAYLOAD = "1" * 64


def _selection(namespace="synthetic-negative-fixture"):
    return {
        "dataset_namespace": namespace,
        "input_sha256": "2" * 64,
        "source_area_id": "source_area_v1:" + "3" * 64,
    }


def _primary_entries(count=2):
    return [
        {"scenario_id": f"S{index:02d}",
         "input": {"scenario_id": f"S{index:02d}", "pois": [],
                   "route_edges": []}}
        for index in range(1, count + 1)
    ]


def _primary_manifest(**overrides):
    entries = overrides.pop("entries", None) or _primary_entries()
    manifest = {
        "manifest_version": "primary.synthetic-negative.v1",
        "dataset_kind": DATASET_CLASS_PRIMARY,
        "dataset_id": "primary:synthetic-negative",
        "label": "synthetic-negative-primary-contract-fixture",
        "frozen": True,
        "payload_sha256": PRIMARY_PAYLOAD,
        "source_scope": _selection(),
        "review": {
            "decision": "frozen_reviewed",
            "reviewed_by": "synthetic-negative-fixture",
            "scenario_entries_sha256": runner._scenario_entries_hash(entries),
        },
        "thesis_mode": False,
        "scenarios": entries,
    }
    manifest.update(overrides)
    return manifest


def _write_manifest(path, manifest):
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_valid_primary_declaration_is_readiness_only(tmp_path):
    path = _write_manifest(tmp_path / "primary.json", _primary_manifest())
    declaration = runner.load_dataset_declaration(path)
    assert declaration.is_primary is True
    assert declaration.kind == DATASET_CLASS_PRIMARY
    assert declaration.source_scope == _selection()
    assert declaration.payload_sha256 == PRIMARY_PAYLOAD
    assert declaration.thesis_mode is False
    assert declaration.thesis_ready is False

    out = tmp_path / "out"
    assert runner.main(["--out", str(out), "--scenarios", str(path)]) == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["transport"] == "production-v2"
    assert manifest["dataset_kind"] == DATASET_CLASS_PRIMARY
    assert manifest["dataset_source_scope"] == _selection()
    assert manifest["thesis_ready"] is False
    assert manifest["accepted_primary_study"] is False
    assert not (out / "calls.jsonl").exists()


def test_synthetic_default_is_never_auto_elevated():
    declaration = runner.load_dataset_declaration(runner.DEFAULT_SCENARIOS)
    assert declaration.is_primary is False
    assert declaration.thesis_mode is False
    assert declaration.thesis_ready is False


def _mutate_source_missing(manifest):
    manifest.pop("source_scope")


def _mutate_source_false(manifest):
    manifest["source_scope"] = False


def _mutate_source_string(manifest):
    manifest["source_scope"] = "HCMC"


def _mutate_source_empty(manifest):
    manifest["source_scope"] = {}


def _mutate_source_extra(manifest):
    value = dict(_selection())
    value["extra"] = "x"
    manifest["source_scope"] = value


def _mutate_source_hash(manifest):
    value = dict(_selection())
    value["input_sha256"] = "A" * 64
    manifest["source_scope"] = value


def _mutate_payload_missing(manifest):
    manifest.pop("payload_sha256")


def _mutate_payload_conflict(manifest):
    manifest["input_payload_sha256"] = "4" * 64


def _mutate_frozen_missing(manifest):
    manifest.pop("frozen")


def _mutate_frozen_string(manifest):
    manifest["frozen"] = "true"


def _mutate_review_missing(manifest):
    manifest.pop("review")


def _mutate_review_decision(manifest):
    manifest["review"]["decision"] = "pending"


def _mutate_reviewer_blank(manifest):
    manifest["review"]["reviewed_by"] = "   "


def _mutate_review_hash(manifest):
    manifest["review"]["scenario_entries_sha256"] = "0" * 64


def _mutate_thesis_nonbool(manifest):
    manifest["thesis_mode"] = "false"


def _mutate_class_contradiction(manifest):
    manifest["dataset_class"] = DATASET_CLASS_SYNTHETIC


def _mutate_duplicate(manifest):
    manifest["scenarios"][1]["scenario_id"] = "S01"
    manifest["scenarios"][1]["input"]["scenario_id"] = "S01"


def _mutate_entry_scope(manifest):
    manifest["scenarios"][0]["source_scope"] = _selection("other-namespace")


def _mutate_thesis_too_few(manifest):
    manifest["thesis_mode"] = True


@pytest.mark.parametrize("mutator", [
    _mutate_source_missing, _mutate_source_false, _mutate_source_string,
    _mutate_source_empty, _mutate_source_extra, _mutate_source_hash,
    _mutate_payload_missing, _mutate_payload_conflict,
    _mutate_frozen_missing, _mutate_frozen_string,
    _mutate_review_missing, _mutate_review_decision, _mutate_reviewer_blank,
    _mutate_review_hash, _mutate_thesis_nonbool, _mutate_class_contradiction,
    _mutate_duplicate, _mutate_entry_scope, _mutate_thesis_too_few,
])
def test_invalid_primary_declarations_fail_closed(tmp_path, mutator):
    manifest = _primary_manifest()
    mutator(manifest)
    path = _write_manifest(tmp_path / "primary.json", manifest)
    with pytest.raises(SystemExit):
        runner.load_dataset_declaration(path)


def test_primary_failure_happens_before_output_or_model(tmp_path):
    manifest = _primary_manifest()
    manifest["source_scope"] = False
    path = _write_manifest(tmp_path / "primary.json", manifest)
    out = tmp_path / "out"
    with pytest.raises(SystemExit):
        runner.main(["--out", str(out), "--scenarios", str(path)])
    assert not out.exists()


def test_synthetic_manifest_cannot_declare_thesis_mode(tmp_path):
    manifest = {"manifest_version": "synthetic.v1", "thesis_mode": True,
                "scenarios": _primary_entries(2)}
    path = _write_manifest(tmp_path / "synthetic.json", manifest)
    with pytest.raises(SystemExit):
        runner.load_dataset_declaration(path)

