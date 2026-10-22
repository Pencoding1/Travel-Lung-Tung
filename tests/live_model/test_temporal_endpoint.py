"""EXP-077 timing-only companion acceptance tests (pure fixtures only).

No live model, HTTP, database or engine call is made here.  The runner
integration uses the same scripted CLI seam as the existing collector tests.
"""

from __future__ import annotations

import copy
import json
import socket
import subprocess
from pathlib import Path

import pytest

from evaluation.h2 import load_h2_records, parse_h2_manifest
from live_model import export, runner, temporal_endpoint
from live_model.constants import V2_MANIFEST_VERSION, V2_METHOD_VERSION
from live_model.util import canonical_json

import fake_events as fe

P1 = "hcm_primary_geojson_internal:028e7931c327b776ef68b5eb1782c8b2"
P2 = "hcm_primary_geojson_internal:033dd327cc9b86b52c8768151afad7f2"
MODEL = fe.MODEL
LEGACY = ("--transport", "legacy-v1")


def _report(**overrides):
    value = {
        "status": "unverifiable",
        "no_plan_reason": None,
        "known_violations": [],
        "unknown_reasons": [f"cost_unknown:{P1}", f"cost_unknown:{P2}"],
        "unsatisfied_required": [],
        "stop_count": 2,
        "recomputed_total_travel_minutes": 20,
        "recomputed_total_cost_party": None,
        "recomputed_total_distance_km": "2.5",
    }
    value.update(overrides)
    return value


def _log(**overrides):
    value = {
        "scenario_id": "P01",
        "condition": "hybrid",
        "repetition": 0,
        "provenance_ok": True,
        "output_ok": True,
        "run_status": "completed",
        "dataset_kind": "real_supplied_primary_snapshot",
        "dataset_id": "primary:fixture",
        "transport": "production-v2",
        "selected_poi_ids": [P1, P2],
        "candidate_ids": [P1, P2],
        "unknown_reasons": [f"cost_unknown:{P1}", f"cost_unknown:{P2}"],
        "duration_seconds": 1.25,
        "provider_usage": {"input_tokens": 10, "output_tokens": 20},
        "requested_model_id": MODEL,
        "observed_model_ids": [MODEL],
        "observed_provider_ids": ["opencode-go"],
        "session_id": "ses_synthetic_exp077",
        "cli_version": "2.0.32",
        "provenance_source": "provider_export",
        "identity_source": "opencode_session_export",
        "provenance": {
            "candidate_id": "candidate", "route_id": "route",
            "prompt_information_id": "prompt", "dataset_id": "primary:fixture",
            "model_id": MODEL, "settings_id": "settings",
            "method_instruction_hash": "method",
        },
        "plan": {
            "status": "unverifiable", "no_plan_reason": None,
            "sequence": [P1, P2], "total_travel_minutes": 20,
            "total_distance_km": "2.5", "total_cost_party": None,
        },
        "report": _report(),
        "budget_deviation": None,
    }
    value.update(overrides)
    return value


def _global(log):
    return export.build_h2_record_from_log(log)


def _companion(log):
    return temporal_endpoint.build_temporal_h2_record(log, _global(log))


# ---------------------------------------------------------------------------
# T1: real-source witness shape — cost-only unknown is temporally clean.
# ---------------------------------------------------------------------------
def test_t1_cost_unknown_only_is_temporally_clean_and_global_stays_unchanged():
    log = _log()
    global_record = _global(log)
    snapshot = copy.deepcopy(global_record)

    assert global_record["temporal_violation"] is None
    assert global_record["known_temporal_violations"] == 0
    assert global_record["violation_count_complete"] is False
    assert global_record["unverifiable"] is True
    assert global_record["validation_status"] == "unverifiable"
    assert global_record["unknown_reasons"] == [
        f"cost_unknown:{P1}", f"cost_unknown:{P2}"]

    record = temporal_endpoint.build_temporal_h2_record(log, global_record)
    assert record is not None
    assert record["endpoint"] == "temporal_only"
    assert record["endpoint_method_version"] == "exp077.temporal.v1"
    assert record["unverifiable_scope"] == "temporal_only"
    assert record["temporal_violation"] is False
    assert record["known_temporal_violations"] == 0
    assert record["violation_count_complete"] is True
    assert record["unverifiable"] is False
    assert record["global_unverifiable"] is True
    assert record["global_validation_status"] == "unverifiable"
    assert record["global_unknown_reasons"] == global_record["unknown_reasons"]
    assert record["unknown_reasons"] == global_record["unknown_reasons"]
    assert record["global_validity_assessed"] is False

    # The original global record and exporter path are untouched.
    assert global_record == snapshot
    assert _global(log) == snapshot


# ---------------------------------------------------------------------------
# T2: all non-cost unknowns and malformed/new reasons fail closed.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("reason", [
    f"hours_unknown:{P1}",
    f"route_unknown:{P1}->{P2}",
    "interday_origin_unknown",
    "novel_reason:new_endpoint",
    "cost_unknown:not_a_known_poi",
    f"cost_unknown:{P1}:extra",
    f"prefix_cost_unknown:{P1}",
])
def test_t2_non_cost_or_malformed_unknown_is_never_a_clean_zero(reason):
    log = _log(report=_report(unknown_reasons=[reason]),
               unknown_reasons=[reason])
    record = _companion(log)
    assert record is not None
    assert record["temporal_violation"] is None
    assert record["known_temporal_violations"] == 0
    assert record["violation_count_complete"] is False
    assert record["unverifiable"] is True


# ---------------------------------------------------------------------------
# T3: known timing badness is retained even with unknown facts.
# ---------------------------------------------------------------------------
def test_t3_known_temporal_violation_with_unknown_is_true_incomplete():
    violations = [{"code": "travel_infeasible", "day_id": "d1", "poi_id": P2,
                   "detail": "arrival precedes travel"}]
    log = _log(
        report=_report(status="partial", known_violations=violations,
                       unknown_reasons=[f"hours_unknown:{P1}"]),
        unknown_reasons=[f"hours_unknown:{P1}"])
    record = _companion(log)
    assert record["temporal_violation"] is True
    assert record["known_temporal_violations"] == 1
    assert record["violation_count_complete"] is False
    assert record["unverifiable"] is True


def test_t3_known_temporal_violation_complete_is_true_complete():
    violations = [{"code": "opening_violation", "day_id": "d1", "poi_id": P1,
                   "detail": "outside window"}]
    log = _log(report=_report(status="partial", known_violations=violations,
                              unknown_reasons=[]),
               unknown_reasons=[])
    record = _companion(log)
    assert record["temporal_violation"] is True
    assert record["known_temporal_violations"] == 1
    assert record["violation_count_complete"] is True
    assert record["unverifiable"] is False


# ---------------------------------------------------------------------------
# T4: refusal / empty / malformed / failure / absent provenance never clean.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("case", ["refusal", "empty", "malformed", "timeout"])
def test_t4_non_delivery_and_failure_are_not_clean(case):
    if case == "refusal":
        log = _log(run_status="refused",
                   plan={"status": "no_plan", "no_plan_reason": "infeasible",
                         "sequence": []},
                   report=_report(status="no_plan", unknown_reasons=[]),
                   unknown_reasons=[])
        expected_known = 0
    elif case == "empty":
        log = _log(plan={"status": "no_plan", "no_plan_reason": "empty",
                         "sequence": []},
                   report=_report(status="no_plan", unknown_reasons=[]),
                   unknown_reasons=[])
        expected_known = 0
    elif case == "malformed":
        log = _log(output_ok=False, run_status="failed",
                   plan=None, report=None)
        expected_known = None
    else:  # provider timeout/failure
        log = _log(output_ok=False, run_status="error",
                   plan=None, report=None,
                   provider_failure={"code": "provider_timeout",
                                     "attempts": 1, "failed_attempts": 1,
                                     "retryable": True})
        expected_known = None

    record = _companion(log)
    assert record is not None
    assert record["temporal_violation"] is None
    assert record["known_temporal_violations"] == expected_known
    assert record["violation_count_complete"] is False
    assert record["unverifiable"] is True


def test_t4_absent_report_is_unknown():
    log = _log(plan={"status": "unverifiable", "sequence": [P1, P2]},
               report=None, unknown_reasons=[])
    record = _companion(log)
    assert record["temporal_violation"] is None
    assert record["violation_count_complete"] is False
    assert record["unverifiable"] is True


def test_t4_absent_provenance_is_not_a_companion_record():
    log = _log(provenance_ok=False, rejection_reason="unknown_model_provenance")
    assert _global(log) is None
    assert temporal_endpoint.build_temporal_h2_record(log, _global(log)) is None
    assert temporal_endpoint.build_temporal_h2_records_from_logs([log]) == []


# ---------------------------------------------------------------------------
# T5: structural/unknown violations cannot conclude clean; closed non-temporal
# violations are retained separately and never imply request compliance.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("code", [
    "unknown_poi", "unknown_day", "sequence_mismatch", "no_plan_with_stops",
    "novel_violation",
])
def test_t5_unrecognised_or_structural_violation_blocks_absence_certainty(code):
    violations = [{"code": code, "day_id": "d1", "poi_id": P1,
                   "detail": "structural"}]
    log = _log(report=_report(status="partial", known_violations=violations,
                              unknown_reasons=[]),
               unknown_reasons=[])
    record = _companion(log)
    assert record["temporal_violation"] is None
    assert record["violation_count_complete"] is False
    assert record["unverifiable"] is True


@pytest.mark.parametrize("code", sorted(temporal_endpoint.NON_TEMPORAL_VIOLATION_CODES))
def test_t5_closed_non_temporal_violation_is_separate_and_not_compliant(code):
    violations = [{"code": code, "day_id": "d1", "poi_id": P1,
                   "detail": "non-temporal"}]
    log = _log(report=_report(status="partial", known_violations=violations,
                              unknown_reasons=[]),
               unknown_reasons=[])
    record = _companion(log)
    # Timing itself is complete, but the request is explicitly not compliant.
    assert record["temporal_violation"] is False
    assert record["known_temporal_violations"] == 0
    assert record["violation_count_complete"] is True
    assert record["global_validation_status"] == "partial"
    assert record["non_temporal_violation_count"] == 1
    assert record["non_temporal_known_violations"][0]["code"] == code
    assert record["request_compliant"] is False
    assert record["whole_plan_compliance_claimed"] is False


def test_t5_unsatisfied_requirements_are_preserved_separately():
    unsatisfied = ["cat_museum", "minimum_stops:2>=3"]
    log = _log(
        report=_report(status="partial", known_violations=[],
                       unknown_reasons=[], unsatisfied_required=unsatisfied),
        unknown_reasons=[])
    record = _companion(log)
    assert record["temporal_violation"] is False
    assert record["violation_count_complete"] is True
    assert record["request_unsatisfied_required"] == unsatisfied
    assert record["request_compliant"] is False
    assert record["global_validation_status"] == "partial"


def test_t5_inconsistent_report_structure_fails_closed():
    log = _log(
        report=_report(status="feasible", known_violations=[],
                       unknown_reasons=[f"cost_unknown:{P1}"],
                       unsatisfied_required=[]),
        unknown_reasons=[f"cost_unknown:{P1}"])
    record = _companion(log)
    assert record["temporal_violation"] is None
    assert record["violation_count_complete"] is False
    assert record["unverifiable"] is True


# ---------------------------------------------------------------------------
# T6: scope labels, evaluator compatibility and reproducibility.
# ---------------------------------------------------------------------------
def _global_manifest():
    return export.build_h2_manifest(
        ["P01", "P02"], 3, manifest_version=V2_MANIFEST_VERSION,
        dataset_kind="real_supplied_primary_snapshot",
        dataset_id="primary:fixture", label="primary-fixture", thesis_mode=False)


def test_t6_manifest_and_evaluator_keep_scope_and_original_fields():
    log = _log()
    record = _companion(log)
    global_manifest = _global_manifest()
    temporal_manifest = temporal_endpoint.build_temporal_h2_manifest(global_manifest)

    parsed_global = parse_h2_manifest(global_manifest)
    parsed_temporal = parse_h2_manifest(temporal_manifest)
    assert temporal_manifest["endpoint"] == "temporal_only"
    assert temporal_manifest["endpoint_method_version"] == "exp077.temporal.v1"
    assert temporal_manifest["global_validity_assessed"] is False
    assert parsed_temporal["scenario_ids"] == parsed_global["scenario_ids"]
    assert parsed_temporal["conditions"] == parsed_global["conditions"]
    assert (parsed_temporal["repetitions_per_case"]
            == parsed_global["repetitions_per_case"])
    assert parsed_temporal["label"] != parsed_global["label"]

    loaded = load_h2_records([record], parsed_temporal)
    assert ("P01", "hybrid", 0) in loaded
    assert record["global_validation_status"] == "unverifiable"
    assert record["global_unverifiable"] is True
    assert record["global_unknown_reasons"]


def test_t6_route_travel_minutes_stays_integer_and_admitted():
    from evaluation.h2 import load_h2_records

    manifest = parse_h2_manifest(_global_manifest())
    for value in (0, 17):
        log = _log(report=_report(recomputed_total_travel_minutes=value))
        record = _companion(log)
        assert record["route_travel_minutes"] == value
        assert isinstance(record["route_travel_minutes"], int)
        loaded = load_h2_records([record], manifest)
        assert ("P01", "hybrid", 0) in loaded

    for bad in (True, 1.5, -1, {"private": "sentinel"}):
        log = _log(report=_report(recomputed_total_travel_minutes=bad))
        record = _companion(log)
        assert record["route_travel_minutes"] is None


def test_t6_same_logs_reproduce_companion_bytes_without_provider():
    logs = [_log(), _log(condition="llm_only", repetition=0)]
    first = temporal_endpoint.build_temporal_h2_records_from_logs(logs)
    second = temporal_endpoint.build_temporal_h2_records_from_logs(copy.deepcopy(logs))
    assert canonical_json(first) == canonical_json(second)
    assert [r["scenario_id"] for r in first] == ["P01", "P01"]


def test_t6_v2_identity_is_exp077_and_old_resume_fails_closed(monkeypatch, tmp_path):
    out = tmp_path / "out"
    assert runner.main(["--out", str(out), "--scenario-ids", "S01",
                        "--conditions", "hybrid"]) == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["method_version"] == V2_METHOD_VERSION == "exp077.live.v1"
    assert manifest["manifest_version"] == V2_MANIFEST_VERSION == "exp077.live.v1"
    assert manifest["task_id"] == "EXP-077"

    # Simulate a run created before EXP-077: the stored fingerprint must refuse.
    manifest["method_version"] = "exp074.live.v1"
    manifest["manifest_version"] = "exp074.live.v1"
    manifest["fingerprint"]["method_version"] = "exp074.live.v1"
    manifest["fingerprint"]["manifest_version"] = "exp074.live.v1"
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    def _deny(*args, **kwargs):
        raise AssertionError("provider/resolver must not be reached on drift")

    monkeypatch.setattr(runner.v2_transport, "complete_factory", _deny)
    monkeypatch.setattr(runner.v2_transport, "provider_factory", _deny)
    monkeypatch.setattr(runner.capture, "resolve_executable", _deny)
    rc = runner.main(["--out", str(out), "--scenario-ids", "S01",
                      "--conditions", "hybrid", "--resume", "--execute"])
    assert rc == 2
    assert not (out / "calls.jsonl").exists()


# ---------------------------------------------------------------------------
# T7: unknown metadata/subtrees and sentinels are not persisted; no mutation.
# ---------------------------------------------------------------------------
def test_t7_sentinel_in_unknown_metadata_is_not_persisted_and_inputs_are_pure():
    sentinel = "SYNTHETIC_SENTINEL_EXP077_MUST_NOT_PERSIST"
    log = _log(
        metadata={"private": sentinel},
        provider_metadata={"headers": {"Authorization": sentinel}},
        headers={"Authorization": sentinel},
        config={"OPENCODE_CONFIG_CONTENT": sentinel},
        error_body=sentinel,
        reasoning=sentinel,
        untrusted_debug={"private": sentinel},
        report=_report(debug={"private": sentinel}),
    )
    log["provenance"]["unknown_extra"] = sentinel
    global_record = _global(log)
    log_before = copy.deepcopy(log)
    global_before = copy.deepcopy(global_record)

    record = temporal_endpoint.build_temporal_h2_record(log, global_record)
    dumped = json.dumps(record, sort_keys=True)
    assert sentinel not in dumped
    assert "unknown_extra" not in record["provenance"]
    assert set(record["model_provenance"]).isdisjoint(
        {"headers", "config", "error_body", "reasoning", "untrusted_debug"})
    assert log == log_before
    assert global_record == global_before


def test_t7_usage_identity_and_failure_subtrees_are_closed_shapes():
    sentinel = "SYNTHETIC_SENTINEL_EXP077_USAGE"
    log = _log(
        provider_usage={
            "input_tokens": 5,
            "prompt_tokens": 5,
            "total_tokens": None,
            "usage_consistent": True,
            "provider_components": {
                "input": 5, "total": None,
                "private_config": {"token": sentinel},
            },
            "coverage": {"private": sentinel},
            "private_config": {"token": sentinel},
        },
        observed_model_ids=[MODEL, {"private": sentinel}],
        observed_provider_ids=["opencode-go", {"private": sentinel}],
        provider_failure={"code": {"private": sentinel}, "attempts": 1,
                          "failed_attempts": 0, "retryable": True,
                          "error_body": sentinel},
        budget_deviation={"amount": {"private": sentinel},
                          "currency": "VND", "unit": "per_party",
                          "comparable": True},
    )
    record = _companion(log)
    dumped = json.dumps(record, sort_keys=True)
    assert sentinel not in dumped

    usage = record["provider_usage"]
    assert usage["input_tokens"] == 5
    assert usage["prompt_tokens"] == 5
    assert usage["total_tokens"] is None
    assert usage["usage_consistent"] is True
    assert "private_config" not in usage
    assert usage["provider_components"] == {"input": 5, "total": None}
    assert usage["coverage"] is None

    assert record["model_provenance"]["observed_model_ids"] == [MODEL]
    assert record["model_provenance"]["observed_provider_ids"] == ["opencode-go"]
    failure = record["model_provenance"]["provider_failure"]
    assert failure == {"code": None, "attempts": 1, "failed_attempts": 0,
                       "retryable": True}
    assert "budget_deviation" not in record


def test_t7_truthy_string_flags_are_not_admitted_as_clean():
    malformed_provenance = _log(provenance_ok="false")
    assert temporal_endpoint.build_temporal_h2_record(
        malformed_provenance, _global(malformed_provenance)) is None

    for value in ("true", "false", 1):
        log = _log(output_ok=value)
        record = _companion(log)
        assert record is not None
        assert record["temporal_violation"] is None
        assert record["violation_count_complete"] is False
        assert record["unverifiable"] is True


def test_t7_known_bad_timing_survives_a_malformed_output_flag():
    violations = [{"code": "travel_infeasible", "day_id": "d1", "poi_id": P1,
                   "detail": "arrival precedes travel"}]
    log = _log(output_ok="true",
               report=_report(status="partial", known_violations=violations,
                              unknown_reasons=[]),
               unknown_reasons=[])
    record = _companion(log)
    assert record["temporal_violation"] is True
    assert record["known_temporal_violations"] == 1
    assert record["violation_count_complete"] is False


# ---------------------------------------------------------------------------
# T8: pure APIs perform no socket/subprocess I/O.
# ---------------------------------------------------------------------------
def test_t8_pure_apis_make_no_network_or_subprocess_call(monkeypatch):
    def _deny(*args, **kwargs):
        raise AssertionError("pure companion API must not perform I/O")

    monkeypatch.setattr(socket.socket, "connect", _deny)
    monkeypatch.setattr(subprocess, "run", _deny)
    monkeypatch.setattr(subprocess, "Popen", _deny)
    logs = [_log()]
    records = temporal_endpoint.build_temporal_h2_records_from_logs(logs)
    manifest = temporal_endpoint.build_temporal_h2_manifest(_global_manifest())
    assert len(records) == 1
    assert manifest["endpoint"] == "temporal_only"


# ---------------------------------------------------------------------------
# Runner sidecars: both endpoints from the same stored logs, no extra calls.
# ---------------------------------------------------------------------------
PLAN_TEXT = json.dumps({
    "status": "plan", "no_plan_reason": None,
    "days": [{"day_id": "d1", "stops": [
        {"poi_id": "p_food", "arrival": "2026-11-01T09:00:00+07:00",
         "departure": "2026-11-01T10:00:00+07:00"}]}]})
HYBRID_TEXT = json.dumps({"ordered_poi_ids": ["p_food", "p_cafe"]})


def _fake_executor(prompt, raw_path, stderr_path):
    value = PLAN_TEXT if "LLM-only" in prompt else HYBRID_TEXT
    events = [fe.step_start(), fe.model_event(), fe.text(value=value),
              fe.step_finish()]
    Path(raw_path).write_text("\n".join(events) + "\n", encoding="utf-8")
    Path(stderr_path).write_text("", encoding="utf-8")
    return runner.capture.CallResult(
        argv=["opencode", "run"], exit_code=0, duration_seconds=0.1,
        timed_out=False, raw_stdout_path=str(raw_path),
        stderr_path=str(stderr_path), started_at_epoch=0.0,
        finished_at_epoch=0.1)


def test_runner_writes_both_endpoints_from_stored_logs(monkeypatch, tmp_path):
    out = tmp_path / "out"
    monkeypatch.setattr(runner, "default_executor", lambda *a, **k: _fake_executor)
    monkeypatch.setattr(runner.capture, "resolve_executable",
                        lambda *a, **k: "opencode")
    monkeypatch.setattr(runner.capture, "cli_version", lambda *a, **k: "1.0")
    assert runner.main(["--out", str(out), "--scenario-ids", "S01",
                        "--execute", *LEGACY]) == 0

    logs = [json.loads(line) for line in
            (out / "calls.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    expected_global = export.build_h2_records_from_logs(logs)
    expected_temporal = temporal_endpoint.build_temporal_h2_records_from_logs(logs)

    global_manifest = json.loads(
        (out / "h2_manifest.json").read_text(encoding="utf-8"))
    temporal_manifest = json.loads(
        (out / "h2_temporal_manifest.json").read_text(encoding="utf-8"))
    expected_temporal_manifest = temporal_endpoint.build_temporal_h2_manifest(
        global_manifest)

    assert (out / "h2_temporal_manifest.json").exists()
    assert (out / "h2_temporal_records.jsonl").exists()
    assert temporal_manifest == expected_temporal_manifest
    assert temporal_manifest["endpoint"] == "temporal_only"
    assert temporal_manifest["global_validity_assessed"] is False

    global_text = (out / "h2_records.jsonl").read_text(encoding="utf-8")
    temporal_text = (out / "h2_temporal_records.jsonl").read_text(encoding="utf-8")
    assert global_text == "\n".join(canonical_json(r) for r in expected_global) + "\n"
    assert temporal_text == "\n".join(canonical_json(r) for r in expected_temporal) + "\n"

    parsed_global = parse_h2_manifest(global_manifest)
    parsed_temporal = parse_h2_manifest(temporal_manifest)
    assert parsed_global["scenario_ids"] == parsed_temporal["scenario_ids"]
    assert parsed_global["conditions"] == parsed_temporal["conditions"]
    assert (parsed_global["repetitions_per_case"]
            == parsed_temporal["repetitions_per_case"])
    load_h2_records(expected_temporal, parsed_temporal)
    assert len(expected_temporal) == len(expected_global)

    summary = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    assert summary["temporal_endpoint"]["scope"] == "timing_only_not_global_validity"
    assert summary["temporal_endpoint"]["records_written"] == len(expected_temporal)
    assert summary["temporal_endpoint"]["global_validity_assessed"] is False


def test_runner_noop_resume_rebuilds_only_deleted_temporal_sidecars(
        monkeypatch, tmp_path):
    out = tmp_path / "out"
    args = ["--out", str(out), "--scenario-ids", "S01", "--execute", *LEGACY]
    monkeypatch.setattr(runner, "default_executor", lambda *a, **k: _fake_executor)
    monkeypatch.setattr(runner.capture, "resolve_executable",
                        lambda *a, **k: "opencode")
    monkeypatch.setattr(runner.capture, "cli_version", lambda *a, **k: "1.0")
    assert runner.main(args) == 0

    protected = {
        name: (out / name).read_bytes()
        for name in ("calls.jsonl", "manifest.json", "h2_manifest.json",
                     "h2_records.jsonl", "run_manifest.json")
    }
    logs = [json.loads(line) for line in
            (out / "calls.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    expected_temporal = temporal_endpoint.build_temporal_h2_records_from_logs(logs)
    global_manifest = json.loads(
        (out / "h2_manifest.json").read_text(encoding="utf-8"))

    for name in ("h2_temporal_manifest.json", "h2_temporal_records.jsonl"):
        (out / name).unlink()

    def _deny(*args, **kwargs):
        raise AssertionError("no resolver/provider/executor on no-op resume")

    monkeypatch.setattr(runner, "default_executor", _deny)
    monkeypatch.setattr(runner.capture, "resolve_executable", _deny)
    monkeypatch.setattr(runner.capture, "cli_version", _deny)
    assert runner.main(args + ["--resume"]) == 0

    for name, payload in protected.items():
        assert (out / name).read_bytes() == payload
    recreated_manifest = json.loads(
        (out / "h2_temporal_manifest.json").read_text(encoding="utf-8"))
    assert recreated_manifest == temporal_endpoint.build_temporal_h2_manifest(
        global_manifest)
    recreated_text = (out / "h2_temporal_records.jsonl").read_text(encoding="utf-8")
    assert recreated_text == "\n".join(
        canonical_json(r) for r in expected_temporal) + "\n"
    parsed = parse_h2_manifest(recreated_manifest)
    load_h2_records(expected_temporal, parsed)

