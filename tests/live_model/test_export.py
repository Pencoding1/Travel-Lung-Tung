from __future__ import annotations

from live_model.export import Observation, build_h2_manifest, build_h2_record, export_gaps


def _observation(**overrides):
    base = dict(
        scenario_id="S01", condition="llm_only", repetition=0,
        provenance_ok=True, rejection_reason=None, output_ok=True,
        run_status="completed", requested_model_id="opencode-go/deepseek-v4.1-flash",
        observed_model_ids=("opencode-go/deepseek-v4.1-flash",),
        observed_provider_ids=("opencode-go",), session_id="ses_x",
        provenance={"candidate_id": "c", "route_id": "r", "prompt_information_id": "p",
                    "dataset_id": "d", "model_id": "opencode-go/deepseek-v4.1-flash",
                    "settings_id": "s", "method_instruction_hash": "m"},
    )
    base.update(overrides)
    return Observation(**base)


def test_manifest_is_not_thesis_mode():
    manifest = build_h2_manifest(["S01", "S02"], repetitions=1)
    assert manifest["thesis_mode"] is False
    assert manifest["paired_conditions"] == ["hybrid", "llm_only"]
    assert manifest["repetitions_per_case"] == 1


def test_unproven_provenance_is_a_gap_not_a_record():
    obs = _observation(provenance_ok=False, rejection_reason="unknown_model_provenance")
    assert build_h2_record(obs) is None
    gaps = export_gaps([obs])
    assert gaps and gaps[0]["reason"] == "unknown_model_provenance"


def test_failed_output_record_has_no_usage_and_is_error_status():
    obs = _observation(output_ok=False, invalid_output_reason="malformed_model_output:x",
                       run_status="failed", plan=None, report=None)
    record = build_h2_record(obs)
    assert record is not None
    assert record["run_status"] == "failed"
    assert record["plan_present"] is False
    assert record["validation_status"] == "failed"
    assert record["unverifiable"] is True
    assert "usage" not in record
    assert record["provider_usage"] is None


def test_record_carries_distinct_requested_and_observed_ids():
    obs = _observation()
    record = build_h2_record(obs)
    assert record["model_provenance"]["requested_model_id"] == \
        record["model_provenance"]["observed_model_ids"][0]
    assert record["evidence_level"] == "live_model"
    assert record["schema_version"] == "oc18.h2.v1"
