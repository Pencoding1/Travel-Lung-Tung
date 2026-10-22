"""H2 evaluator tests: honest denominators, pairing gates, exact inference."""

import pytest

from evaluation.errors import ManifestError, RecordError, SchemaError
from evaluation.h2 import load_h2_records, parse_h2_manifest

from helpers_evaluation import (
    h2_manifest,
    h2_provenance,
    h2_record,
    h2_provider_usage,
)


def _all_failed(scenarios=("S01",), repetitions=1, conditions=("hybrid", "llm_only")):
    return [
        h2_record(s, c, r, run_status="failed", plan_present=False,
                  validation_status="failed", temporal_violation=None)
        for s in scenarios for c in conditions for r in range(repetitions)
    ]


def test_all_failures_are_retained_and_never_success(run_h2):
    records = _all_failed(("S01", "S02"), repetitions=2)
    metrics = run_h2(h2_manifest(scenarios=("S01", "S02"), repetitions=2), records)

    assert metrics["planned_runs"] == 8
    assert metrics["observed_runs"] == 8
    assert metrics["missing_runs"] == 0
    for condition in ("hybrid", "llm_only"):
        block = metrics["conditions"][condition]
        assert block["planned"] == 4
        assert block["delivered"] == 0
        assert block["delivery_rate"] == 0.0
        assert block["failure_rate"] == 1.0
        assert block["states"]["failed"] == 4
        # No delivered plan -> no violation denominator, must be null not zero.
        assert block["verified_violation_rate_among_delivered"] is None
    paired = metrics["paired_inference"]
    assert paired["eligible_scenarios"] == 0
    assert paired["inferential_available"] is False
    assert "no_eligible_pairs" in paired["blocked_reasons"]


def test_all_refusals_are_not_delivery_success(run_h2):
    records = [
        h2_record(s, c, r, run_status="refused", plan_present=False, empty_plan=True,
                  validation_status="no_plan", temporal_violation=None)
        for s in ("S01",) for c in ("hybrid", "llm_only") for r in range(2)
    ]
    metrics = run_h2(h2_manifest(scenarios=("S01",), repetitions=2), records)

    for condition in ("hybrid", "llm_only"):
        block = metrics["conditions"][condition]
        assert block["refusal_rate"] == 1.0
        assert block["delivery_rate"] == 0.0
        assert block["states"]["refused"] == 2
    assert metrics["paired_inference"]["eligible_scenarios"] == 0


def test_empty_plan_is_not_a_delivered_success(run_h2):
    records = [
        h2_record(s, c, r, plan_present=False, empty_plan=True,
                  validation_status="no_plan", temporal_violation=None,
                  known_temporal_violations=None, violation_count_complete=False)
        for s in ("S01",) for c in ("hybrid", "llm_only") for r in range(1)
    ]
    metrics = run_h2(h2_manifest(scenarios=("S01",), repetitions=1), records)

    for condition in ("hybrid", "llm_only"):
        block = metrics["conditions"][condition]
        assert block["states"]["empty"] == 1
        assert block["delivered"] == 0
        assert block["delivery_rate"] == 0.0
        assert block["empty_rate"] == 1.0


def test_unknown_hours_is_delivered_but_unverifiable_not_clean(run_h2):
    records = [
        h2_record("S01", "hybrid", 0, unverifiable=True,
                  validation_status="unverifiable", temporal_violation=None,
                  unknown_reasons=["hours_unknown"]),
        h2_record("S01", "llm_only", 0, unverifiable=True,
                  validation_status="unverifiable", temporal_violation=None,
                  unknown_reasons=["hours_unknown"]),
    ]
    metrics = run_h2(h2_manifest(scenarios=("S01",), repetitions=1), records)

    for condition in ("hybrid", "llm_only"):
        block = metrics["conditions"][condition]
        # A real non-empty unverifiable plan is delivered, not a refusal.
        assert block["delivered"] == 1
        assert block["outcome_states"]["unverifiable"] == 1
        assert block["delivered_clean"] == 0
        assert block["delivered_with_verified_violation"] == 0
        assert block["unverifiable_rate"] == 1.0
        assert block["verified_violation_rate_among_delivered"] is None
    scenario = metrics["scenario_outcomes"][0]
    assert scenario["conditions"]["hybrid"]["scenario_outcome"] is None
    assert metrics["paired_inference"]["eligible_scenarios"] == 0


def test_missing_repetition_is_retained_and_blocks_pairing(run_h2):
    records = [
        h2_record("S01", "hybrid", 0, temporal_violation=False),
        h2_record("S01", "llm_only", 0, temporal_violation=False),
    ]
    metrics = run_h2(h2_manifest(scenarios=("S01",), repetitions=3), records)

    assert metrics["planned_runs"] == 6
    assert metrics["observed_runs"] == 2
    assert metrics["missing_runs"] == 4
    for condition in ("hybrid", "llm_only"):
        block = metrics["conditions"][condition]
        assert block["planned"] == 3
        assert block["observed"] == 1
        assert block["missing"] == 2
        assert block["states"]["missing"] == 2
        assert block["delivery_rate"] == pytest.approx(1 / 3)
    # One clean run must never stand in for three planned repetitions.
    assert metrics["paired_inference"]["eligible_scenarios"] == 0
    assert any(item["reason"] == "incomplete_coverage"
               for item in metrics["paired_inference"]["excluded_scenarios"])
    assert "incomplete_coverage" in metrics["paired_inference"]["blocked_reasons"]


def test_duplicate_key_is_an_error_not_overwrite():
    manifest = parse_h2_manifest(h2_manifest(scenarios=("S01",), repetitions=1))
    duplicate = [h2_record("S01", "hybrid", 0), h2_record("S01", "hybrid", 0)]
    with pytest.raises(RecordError) as excinfo:
        load_h2_records(duplicate, manifest)
    assert "duplicate" in str(excinfo.value).lower()


def test_unknown_scenario_condition_and_repetition_are_errors():
    manifest = parse_h2_manifest(h2_manifest(scenarios=("S01",), repetitions=1))
    with pytest.raises(RecordError):
        load_h2_records([h2_record("S99", "hybrid", 0)], manifest)
    with pytest.raises(RecordError):
        load_h2_records([h2_record("S01", "magic", 0)], manifest)
    with pytest.raises(RecordError):
        load_h2_records([h2_record("S01", "hybrid", 5)], manifest)


def test_mixed_provenance_blocks_inference_with_diagnostics(run_h2):
    records = [
        h2_record("S01", "hybrid", 0,
                  provenance=h2_provenance("S01", "hybrid", model_id="model-a")),
        h2_record("S01", "llm_only", 0,
                  provenance=h2_provenance("S01", "llm_only", model_id="model-b")),
    ]
    metrics = run_h2(h2_manifest(scenarios=("S01",), repetitions=1), records)

    paired = metrics["paired_inference"]
    assert paired["inferential_available"] is False
    assert "incompatible_provenance" in paired["blocked_reasons"]
    assert paired["eligible_scenarios"] == 0
    assert any("incompatible provenance" in note for note in metrics["diagnostics"])


def test_clustered_repetitions_are_not_independent_scenarios(run_h2):
    records = [
        h2_record("S01", c, r, validation_status="partial",
                  temporal_violation=True, known_temporal_violations=1)
        for c in ("hybrid", "llm_only") for r in range(5)
    ]
    metrics = run_h2(h2_manifest(scenarios=("S01",), repetitions=5), records)

    paired = metrics["paired_inference"]
    assert paired["eligible_scenarios"] == 1
    assert paired["n_scenarios_used_as_independent_units"] == 1
    assert paired["discordant"]["total"] == 0
    assert metrics["planned_runs"] == 10


def test_delivery_and_feasibility_rate_denominators(run_h2):
    records = [
        h2_record("S01", "hybrid", 0, validation_status="feasible"),
        h2_record("S01", "hybrid", 1, validation_status="feasible"),
        h2_record("S02", "hybrid", 0, run_status="failed", plan_present=False,
                  validation_status="failed", temporal_violation=None),
        h2_record("S02", "hybrid", 1, run_status="error", plan_present=False,
                  validation_status="failed", temporal_violation=None),
        h2_record("S01", "llm_only", 0, validation_status="partial",
                  temporal_violation=True, known_temporal_violations=1),
        h2_record("S01", "llm_only", 1, validation_status="feasible"),
        h2_record("S02", "llm_only", 0, validation_status="feasible"),
        h2_record("S02", "llm_only", 1, validation_status="feasible"),
    ]
    metrics = run_h2(h2_manifest(scenarios=("S01", "S02"), repetitions=2), records)

    hybrid = metrics["conditions"]["hybrid"]
    assert hybrid["planned"] == 4
    assert hybrid["delivered"] == 2
    assert hybrid["delivery_rate"] == pytest.approx(0.5)
    assert hybrid["validated_feasible"] == 2
    assert hybrid["validated_feasibility_rate"] == pytest.approx(0.5)
    assert hybrid["failure_rate"] == pytest.approx(0.5)

    assert hybrid["delivered_partial"] == 0
    assert hybrid["validation_status_counts"]["feasible"] == 2
    assert hybrid["validation_status_counts"]["failed"] == 2

    llm = metrics["conditions"]["llm_only"]
    assert llm["delivery_rate"] == pytest.approx(1.0)
    assert llm["validated_feasibility_rate"] == pytest.approx(0.75)
    assert llm["delivered_with_verified_violation"] == 1
    assert llm["verified_violation_rate_among_delivered"] == pytest.approx(0.25)
    assert llm["delivered_partial"] == 1
    assert llm["validation_status_counts"]["partial"] == 1


def test_seed_repeatability_of_paired_interval(run_h2):
    scenarios = ("S01", "S02", "S03", "S04")
    flags = {
        "S01": (False, True), "S02": (True, True),
        "S03": (False, False), "S04": (True, False),
    }
    records = []
    for scenario, (hybrid_flag, llm_flag) in flags.items():
        records.append(h2_record(
            scenario, "hybrid", 0, temporal_violation=hybrid_flag,
            validation_status="partial" if hybrid_flag else "feasible",
            known_temporal_violations=1 if hybrid_flag else 0))
        records.append(h2_record(
            scenario, "llm_only", 0, temporal_violation=llm_flag,
            validation_status="partial" if llm_flag else "feasible",
            known_temporal_violations=1 if llm_flag else 0))
    manifest = h2_manifest(scenarios=scenarios, repetitions=1)
    first = run_h2(manifest, records)["paired_inference"]["bootstrap"]
    second = run_h2(manifest, records)["paired_inference"]["bootstrap"]
    assert first["lower"] == second["lower"]
    assert first["upper"] == second["upper"]
    assert first["seed"] == 20261015


def test_synthetic_evidence_blocks_thesis_conclusion(run_h2):
    records = [
        h2_record("S01", "hybrid", 0, temporal_violation=False),
        h2_record("S01", "llm_only", 0, temporal_violation=False),
    ]
    metrics = run_h2(h2_manifest(scenarios=("S01",), repetitions=1), records)
    assert metrics["thesis_conclusion"] is False
    assert metrics["conclusion_label"] == "SYNTHETIC EVALUATOR TEST"
    assert metrics["paired_inference"]["inferential_available"] is False
    assert "synthetic_evidence_only" in metrics["paired_inference"]["blocked_reasons"]


def test_live_evidence_with_compatible_provenance_permits_inference(run_h2):
    records = [
        h2_record("S01", "hybrid", 0, temporal_violation=False, evidence_level="live_model",
                  dataset_kind="original_thesis_snapshot"),
        h2_record("S01", "llm_only", 0, validation_status="partial",
                  temporal_violation=True, known_temporal_violations=1,
                  evidence_level="live_model", dataset_kind="original_thesis_snapshot"),
        h2_record("S02", "hybrid", 0, temporal_violation=False, evidence_level="live_model",
                  dataset_kind="original_thesis_snapshot"),
        h2_record("S02", "llm_only", 0, temporal_violation=False, evidence_level="live_model",
                  dataset_kind="original_thesis_snapshot"),
    ]
    metrics = run_h2(h2_manifest(scenarios=("S01", "S02"), repetitions=1), records)
    paired = metrics["paired_inference"]
    assert paired["eligible_scenarios"] == 2
    assert paired["discordant"]["b_positive_a_negative"] == 1
    assert paired["inferential_available"] is True
    assert paired["blocked_reasons"] == []


def test_thesis_manifest_requires_twenty_scenarios():
    with pytest.raises(ManifestError):
        parse_h2_manifest(h2_manifest(scenarios=tuple(f"S{i:02d}" for i in range(19)),
                                      thesis_mode=True))
    ok = parse_h2_manifest(h2_manifest(scenarios=tuple(f"S{i:02d}" for i in range(20)),
                                       thesis_mode=True))
    assert ok["thesis_mode"] is True
    assert len(ok["scenario_ids"]) == 20


def test_usage_provenance_counts_known_and_unknown(run_h2):
    records = [
        h2_record("S01", "hybrid", 0, usage=h2_provider_usage()),
        h2_record("S01", "llm_only", 0, usage=None),
    ]
    metrics = run_h2(h2_manifest(scenarios=("S01",), repetitions=1), records)
    assert metrics["usage_provenance"] == {"known": 1, "unknown": 1}


@pytest.mark.parametrize("overrides", [
    # feasible cannot carry a known violation
    {"validation_status": "feasible", "temporal_violation": False,
     "known_temporal_violations": 2},
    # a false flag cannot carry a nonzero count
    {"validation_status": "partial", "temporal_violation": False,
     "known_temporal_violations": 1},
    # a true flag cannot carry a *complete* count of zero
    {"validation_status": "partial", "temporal_violation": True,
     "known_temporal_violations": 0, "violation_count_complete": True},
    # unverifiable cannot claim a false (clean) flag
    {"validation_status": "unverifiable", "temporal_violation": False,
     "unverifiable": True},
    # a complete count is impossible when the count itself is null
    {"validation_status": "partial", "temporal_violation": None,
     "known_temporal_violations": None, "violation_count_complete": True},
])
def test_contradictory_outcomes_are_rejected(overrides):
    manifest = parse_h2_manifest(h2_manifest(scenarios=("S01",), repetitions=1))
    record = h2_record("S01", "hybrid", 0)
    record.update(overrides)
    with pytest.raises(RecordError):
        load_h2_records([record], manifest)


@pytest.mark.parametrize("missing_field", [
    "known_temporal_violations", "violation_count_complete", "unverifiable",
    "temporal_violation",
])
def test_missing_outcome_fields_are_not_defaulted(missing_field):
    manifest = parse_h2_manifest(h2_manifest(scenarios=("S01",), repetitions=1))
    record = h2_record("S01", "hybrid", 0)
    del record[missing_field]
    with pytest.raises((RecordError, SchemaError)):
        load_h2_records([record], manifest)


def test_known_violation_is_retained_with_unknown_hours(run_h2):
    records = [
        h2_record("S01", "hybrid", 0, validation_status="partial", unverifiable=True,
                  temporal_violation=True, known_temporal_violations=1,
                  unknown_reasons=["hours_unknown"]),
        h2_record("S01", "llm_only", 0, temporal_violation=False),
    ]
    metrics = run_h2(h2_manifest(scenarios=("S01",), repetitions=1), records)
    hybrid = metrics["conditions"]["hybrid"]
    assert hybrid["outcome_states"]["violation"] == 1
    assert hybrid["delivered_with_verified_violation"] == 1
    assert hybrid["delivered_unverifiable"] == 0
    assert metrics["scenario_outcomes"][0]["conditions"]["hybrid"]["scenario_outcome"] is True


def test_secondary_outcome_table_preserves_units_and_unknowns(run_h2):
    records = [
        h2_record("S01", "hybrid", 0, temporal_violation=False,
                  selected_poi_ids=["p_a", "p_b", "p_foreign"],
                  grounded_source_poi_ids=["p_a", "p_b"],
                  route_travel_minutes=30, route_distance_km=5.0,
                  latency_seconds=1.2,
                  budget_deviation={"amount": "1000", "currency": "VND",
                                    "unit": "per_party", "comparable": True}),
        h2_record("S01", "llm_only", 0, temporal_violation=False,
                  selected_poi_ids=["p_a"], grounded_source_poi_ids=["p_a"],
                  route_travel_minutes=42, route_distance_km=7.0,
                  latency_seconds=2.0),
    ]
    metrics = run_h2(h2_manifest(scenarios=("S01",), repetitions=1), records)
    secondary = metrics["secondary_outcomes"]
    assert secondary["poi_grounding"]["selected_total"] == 4
    assert secondary["poi_grounding"]["grounded_total"] == 3
    assert secondary["poi_grounding"]["grounded_rate"] == pytest.approx(0.75)
    assert secondary["route_travel_minutes"]["unit"] == "minutes"
    assert secondary["route_travel_minutes"]["median"] == pytest.approx(36.0)
    assert secondary["route_distance_km"]["max"] == pytest.approx(7.0)
    assert secondary["latency_seconds"]["n"] == 2
    # Budget deviation is only pooled within one currency/unit and never across.
    groups = secondary["budget_deviation"]["groups"]
    assert len(groups) == 1
    assert groups[0]["currency"] == "VND" and groups[0]["unit"] == "per_party"
    assert secondary["budget_deviation"]["pooled_across_units"] is False


def _mixed_clean_violation_unknown(condition="hybrid"):
    return [
        h2_record("S01", condition, 0, temporal_violation=False),
        h2_record("S01", condition, 1, validation_status="partial",
                  temporal_violation=True, known_temporal_violations=1),
        h2_record("S01", condition, 2, validation_status="unverifiable", unverifiable=True,
                  temporal_violation=None, known_temporal_violations=None,
                  violation_count_complete=False, unknown_reasons=["hours_unknown"]),
    ]


def test_determined_violation_rate_and_lower_bound_are_explicit(run_h2):
    metrics = run_h2(h2_manifest(scenarios=("S01",), repetitions=3), _mixed_clean_violation_unknown())
    block = metrics["conditions"]["hybrid"]
    assert block["delivered"] == 3
    assert block["delivered_determined"] == 2

    determined = block["determined_violation_rate"]
    assert determined["numerator"] == 1
    assert determined["denominator"] == 2
    assert determined["value"] == pytest.approx(0.5)
    assert determined["delivered_denominator"] == 3
    assert determined["coverage"] == pytest.approx(2 / 3)
    assert determined["label"] == "verified_violation_rate_among_determined_delivered_plans"

    lower = block["observed_known_violation_lower_bound"]
    assert lower["numerator"] == 1
    assert lower["denominator"] == 3
    assert lower["value"] == pytest.approx(1 / 3)
    assert lower["label"] == ("observed_known_violation_lower_bound_among_all_delivered_plans")
    # The legacy key equals the determined-subset rate and is flagged deprecated.
    assert block["verified_violation_rate_among_delivered"] == pytest.approx(0.5)
    assert "verified_violation_rate_among_delivered" in block["deprecated_metrics"]


def test_all_unknown_delivered_has_null_determined_rate_not_clean(run_h2):
    records = [
        h2_record("S01", "hybrid", r, validation_status="unverifiable", unverifiable=True,
                  temporal_violation=None, known_temporal_violations=None,
                  violation_count_complete=False, unknown_reasons=["hours_unknown"])
        for r in range(3)
    ]
    metrics = run_h2(h2_manifest(scenarios=("S01",), repetitions=3), records)
    block = metrics["conditions"]["hybrid"]
    assert block["delivered"] == 3
    assert block["delivered_clean"] == 0
    assert block["delivered_determined"] == 0
    determined = block["determined_violation_rate"]
    assert determined["value"] is None
    assert determined["numerator"] == 0 and determined["denominator"] == 0
    assert determined["coverage"] == 0.0
    # A known violation plus unknowns would still be retained, but there is none.
    assert block["observed_known_violation_lower_bound"]["value"] == 0.0


def test_missing_runs_keep_planned_denominator_with_determined_subset(run_h2):
    records = [h2_record("S01", "hybrid", 0, temporal_violation=False)]
    metrics = run_h2(h2_manifest(scenarios=("S01",), repetitions=3), records)
    block = metrics["conditions"]["hybrid"]
    assert block["planned"] == 3
    assert block["observed"] == 1
    assert block["missing"] == 2
    assert block["states"]["missing"] == 2
    assert block["delivered"] == 1
    determined = block["determined_violation_rate"]
    assert determined["delivered_denominator"] == 1
    assert determined["denominator"] == 1
    assert determined["value"] == 0.0
    assert determined["coverage"] == 1.0


def test_secondary_fields_absent_reports_unavailable(run_h2):
    records = [
        h2_record("S01", "hybrid", 0, temporal_violation=False),
        h2_record("S01", "llm_only", 0, temporal_violation=False),
    ]
    metrics = run_h2(h2_manifest(scenarios=("S01",), repetitions=1), records)
    secondary = metrics["secondary_outcomes"]
    assert secondary["poi_grounding"]["available"] is False
    assert secondary["route_travel_minutes"] == {
        "available": False, "unit": "minutes", "n": 0, "median": None,
        "mean": None, "min": None, "max": None}
