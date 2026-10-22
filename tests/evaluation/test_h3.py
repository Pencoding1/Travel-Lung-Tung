"""H3 evaluator tests: preferred share, coverage gaps, usage honesty."""

import pytest

from evaluation.errors import ManifestError, RecordError
from evaluation.h3 import load_h3_records, parse_h3_manifest
from evaluation.usage import parse_provider_usage

from helpers_evaluation import (
    h3_manifest,
    h3_provenance,
    h3_provider_usage,
    h3_record,
)


def _find_effect(metrics, profile_id):
    for effect in metrics["profile_effects"]:
        if effect["profile_id"] == profile_id:
            return effect
    raise AssertionError(f"profile {profile_id} not reported")


def test_preferred_share_denominator_is_all_selected_stops(run_h3):
    records = [
        h3_record("P1", "S01", "two_tier", 0,
                  selected_poi_ids=["p_food", "p_cafe", "p_unknown"]),
    ]
    metrics = run_h3(h3_manifest(profiles=("P1",), scenarios=("S01",)), records)
    group = metrics["groups"]["P1"]["two_tier"]
    pool = group["selected_stop_pool"]
    assert pool["selected_total"] == 3
    assert pool["preferred_hits"] == 1
    assert pool["non_preferred"] == 1
    assert pool["unknown_category_stops"] == 1
    # Unknown coverage means no exact share is claimed: null plus a bound.
    assert group["preferred_share"] is None
    assert group["preferred_share_reason"] == "coverage_gap"
    assert group["preferred_share_lower"] == pytest.approx(1 / 3)
    assert group["preferred_share_upper"] == pytest.approx(2 / 3)
    # The old resolved-subset number is kept only as a labelled diagnostic.
    assert group["resolved_subset_share"] == pytest.approx(0.5)


def test_one_preferred_plus_one_unknown_is_null_with_half_to_one_bounds(run_h3):
    records = [
        h3_record("P1", "S01", "two_tier", 0, selected_poi_ids=["p_food", "p_unknown"]),
    ]
    metrics = run_h3(h3_manifest(profiles=("P1",), scenarios=("S01",)), records)
    group = metrics["groups"]["P1"]["two_tier"]
    # Never an unqualified 100%: the exact share is withheld on a coverage gap.
    assert group["preferred_share"] is None
    assert group["preferred_share_reason"] == "coverage_gap"
    assert group["preferred_share_lower"] == pytest.approx(0.5)
    assert group["preferred_share_upper"] == pytest.approx(1.0)
    # The resolved-subset diagnostic is reported separately, still labelled.
    assert group["resolved_subset_share"] == pytest.approx(1.0)
    detail = _find_effect(metrics, "P1")["preferred_share_detail_by_condition"]["two_tier"]
    assert detail["value"] is None
    assert detail["lower"] == pytest.approx(0.5)
    assert detail["upper"] == pytest.approx(1.0)
    assert detail["resolved_subset_share"] == pytest.approx(1.0)
    assert detail["coverage"] == pytest.approx(0.5)
    assert detail["selected_total"] == 2 and detail["preferred"] == 1


def test_duplicate_selected_ids_do_not_inflate_share(run_h3):
    records = [
        h3_record("P1", "S01", "two_tier", 0,
                  selected_poi_ids=["p_food", "p_food", "p_cafe"]),
    ]
    metrics = run_h3(h3_manifest(profiles=("P1",), scenarios=("S01",)), records)
    group = metrics["groups"]["P1"]["two_tier"]
    assert group["selected_stop_pool"]["duplicate_selected_ids"] == 1
    assert group["selected_stop_pool"]["selected_total"] == 2
    assert group["preferred_share"] == pytest.approx(0.5)


def test_empty_plan_share_is_null_not_zero(run_h3):
    records = [
        h3_record("P1", "S01", "two_tier", 0, plan_present=True, empty_plan=True,
                  validation_status="feasible", selected_poi_ids=[]),
    ]
    metrics = run_h3(h3_manifest(profiles=("P1",), scenarios=("S01",)), records)
    group = metrics["groups"]["P1"]["two_tier"]
    assert group["states"]["empty"] == 1
    assert group["preferred_share"] is None
    assert group["preferred_share_reason"] == "empty_plan"
    assert group["selected_stop_pool"]["empty_plan_records"] == 1


def test_unknown_only_selection_is_null_with_full_interval(run_h3):
    records = [
        h3_record("P1", "S01", "two_tier", 0, selected_poi_ids=["p_unknown"]),
    ]
    metrics = run_h3(h3_manifest(profiles=("P1",), scenarios=("S01",)), records)
    group = metrics["groups"]["P1"]["two_tier"]
    assert group["preferred_share"] is None
    assert group["preferred_share_reason"] == "coverage_gap"
    assert group["preferred_share_lower"] == pytest.approx(0.0)
    assert group["preferred_share_upper"] == pytest.approx(1.0)
    assert group["selected_stop_pool"]["unknown_category_stops"] == 1
    assert group["resolved_subset_share"] is None


def test_negative_preference_effect_is_retained(run_h3):
    records = [
        h3_record("P1", "S01", "memory_disabled", 0, selected_poi_ids=["p_food"]),
        h3_record("P1", "S01", "two_tier", 0, selected_poi_ids=["p_cafe"]),
    ]
    metrics = run_h3(h3_manifest(profiles=("P1",), scenarios=("S01",)), records)
    assert metrics["groups"]["P1"]["memory_disabled"]["preferred_share"] == pytest.approx(1.0)
    assert metrics["groups"]["P1"]["two_tier"]["preferred_share"] == pytest.approx(0.0)
    effect = _find_effect(metrics, "P1")
    assert effect["preferred_share_effect_two_tier_minus_baseline"] == pytest.approx(-1.0)


def test_missing_stage_usage_is_unknown_never_zero(run_h3):
    records = [
        h3_record("P1", "S01", "memory_disabled", 0, selected_poi_ids=["p_food"]),
        h3_record("P1", "S01", "two_tier", 0, selected_poi_ids=["p_food"],
                  usage={"usage_basis": "provider_tokens",
                         "stages": {"summary": 10, "retrieval": 10, "final": 10}}),
    ]
    metrics = run_h3(h3_manifest(profiles=("P1",), scenarios=("S01",)), records)
    group = metrics["groups"]["P1"]["two_tier"]
    assert group["usage"]["unknown_records"] == 1
    assert group["usage"]["known_total_provider_tokens"] == 0
    effect = _find_effect(metrics, "P1")
    reduction = effect["token_reduction_by_condition"]["two_tier"]
    assert reduction["value"] is None
    assert reduction["reason"] == "unknown_usage_present"


def test_character_proxy_is_forbidden_as_provider_tokens(run_h3):
    parsed = parse_provider_usage({"usage_basis": "character_proxy",
                                   "stages": {"summary": 1, "extraction": 1,
                                              "retrieval": 1, "final": 1}})
    assert parsed["known"] is False
    assert parsed["total"] is None
    assert parsed["reason"] == "character_proxy_forbidden"

    records = [
        h3_record("P1", "S01", "two_tier", 0, selected_poi_ids=["p_food"],
                  usage=h3_provider_usage(basis="character_proxy")),
    ]
    metrics = run_h3(h3_manifest(profiles=("P1",), scenarios=("S01",)), records)
    group = metrics["groups"]["P1"]["two_tier"]
    assert group["usage"]["known_records"] == 0
    assert group["usage"]["unknown_records"] == 1
    assert group["usage"]["known_total_provider_tokens"] == 0


def test_undefined_token_ratio_on_zero_baseline(run_h3):
    records = [
        h3_record("P1", "S01", "memory_disabled", 0, selected_poi_ids=["p_food"],
                  usage=h3_provider_usage(0, 0, 0, 0, 0)),
        h3_record("P1", "S01", "two_tier", 0, selected_poi_ids=["p_food"],
                  usage=h3_provider_usage(10, 10, 10, 10, 0)),
    ]
    metrics = run_h3(h3_manifest(profiles=("P1",), scenarios=("S01",)), records)
    reduction = _find_effect(metrics, "P1")["token_reduction_by_condition"]["two_tier"]
    assert reduction["value"] is None
    assert reduction["reason"] == "undefined_zero_baseline"


def test_token_reduction_arithmetic(run_h3):
    records = [
        h3_record("P1", "S01", "memory_disabled", 0, selected_poi_ids=["p_food"],
                  usage=h3_provider_usage(100, 100, 100, 100, 0)),
        h3_record("P1", "S01", "two_tier", 0, selected_poi_ids=["p_food"],
                  usage=h3_provider_usage(50, 50, 50, 50, 0)),
    ]
    metrics = run_h3(h3_manifest(profiles=("P1",), scenarios=("S01",)), records)
    reduction = _find_effect(metrics, "P1")["token_reduction_by_condition"]["two_tier"]
    assert reduction["baseline_total"] == 400
    assert reduction["condition_total"] == 200
    assert reduction["value"] == pytest.approx(0.5)


def test_constraint_validity_accompanies_share(run_h3):
    records = [
        h3_record("P1", "S01", "two_tier", 0, selected_poi_ids=["p_food"],
                  constraint_valid=True),
        h3_record("P1", "S01", "two_tier", 1, selected_poi_ids=["p_food"],
                  constraint_valid=False),
    ]
    metrics = run_h3(h3_manifest(profiles=("P1",), scenarios=("S01",), repetitions=2), records)
    group = metrics["groups"]["P1"]["two_tier"]
    assert group["preferred_share"] == pytest.approx(1.0)
    assert group["constraint_validity"]["evaluated"] == 2
    assert group["constraint_validity"]["valid"] == 1
    assert group["constraint_validity"]["rate"] == pytest.approx(0.5)


def test_active_preference_override_is_used_per_scenario(run_h3):
    active = {"P1": {"S01": ["cat_food"], "S02": ["cat_cafe"]}}
    records = [
        h3_record("P1", "S01", "two_tier", 0, selected_poi_ids=["p_food"]),
        h3_record("P1", "S02", "two_tier", 0, selected_poi_ids=["p_cafe"]),
    ]
    metrics = run_h3(
        h3_manifest(profiles=("P1",), scenarios=("S01", "S02"),
                    active_preference_truth=active),
        records)
    group = metrics["groups"]["P1"]["two_tier"]
    assert group["selected_stop_pool"]["preferred_hits"] == 2
    assert group["selected_stop_pool"]["resolved_denominator"] == 2
    assert group["preferred_share"] == pytest.approx(1.0)


def test_every_profile_reported_including_nulls(run_h3):
    records = [
        h3_record("P1", "S01", "two_tier", 0, selected_poi_ids=["p_food"]),
    ]
    metrics = run_h3(h3_manifest(profiles=("P1", "P2", "P3", "P4", "P5")), records)
    assert [effect["profile_id"] for effect in metrics["profile_effects"]] == \
        ["P1", "P2", "P3", "P4", "P5"]
    for profile in ("P2", "P3", "P4", "P5"):
        effect = _find_effect(metrics, profile)
        assert effect["preferred_share_by_condition"]["two_tier"] is None


def test_thesis_mode_requires_five_profiles():
    with pytest.raises(ManifestError):
        parse_h3_manifest(h3_manifest(profiles=("P1", "P2", "P3", "P4"), thesis_mode=True))
    ok = parse_h3_manifest(h3_manifest(profiles=("P1", "P2", "P3", "P4", "P5"),
                                       thesis_mode=True))
    assert ok["thesis_mode"] is True
    assert len(ok["profile_ids"]) == 5


def test_duplicate_and_unknown_h3_keys_are_errors():
    manifest = parse_h3_manifest(h3_manifest(profiles=("P1",), scenarios=("S01",),
                                             repetitions=1))
    duplicate = [h3_record("P1", "S01", "two_tier", 0),
                 h3_record("P1", "S01", "two_tier", 0)]
    with pytest.raises(RecordError):
        load_h3_records(duplicate, manifest)
    with pytest.raises(RecordError):
        load_h3_records([h3_record("P9", "S01", "two_tier", 0)], manifest)
    with pytest.raises(RecordError):
        load_h3_records([h3_record("P1", "S99", "two_tier", 0)], manifest)
    with pytest.raises(RecordError):
        load_h3_records([h3_record("P1", "S01", "magic", 0)], manifest)


def test_cold_and_amortized_costs_are_reported_separately(run_h3):
    usage = {
        "usage_basis": "provider_tokens",
        "stages": {"summary": 10, "extraction": 10, "retrieval": 10, "final": 10},
        "cold": {"total": 100},
        "amortized": {"total": 50},
    }
    records = [
        h3_record("P1", "S01", "two_tier", 0, selected_poi_ids=["p_food"], usage=usage),
    ]
    metrics = run_h3(h3_manifest(profiles=("P1",), scenarios=("S01",)), records)
    group_usage = metrics["groups"]["P1"]["two_tier"]["usage"]
    assert group_usage["cold"]["supplied_records"] == 1
    assert group_usage["cold"]["interpretable_total"] == 100
    assert group_usage["amortized"]["supplied_records"] == 1
    assert group_usage["amortized"]["interpretable_total"] == 50
    # No combined saving is ever derived from cold vs amortized.
    assert group_usage["no_inferred_time_savings"] is True


def test_paired_effect_uses_matched_units_not_pooled_selection(run_h3):
    records = [
        h3_record("P1", "S01", "memory_disabled", 0, selected_poi_ids=["p_food"]),
        h3_record("P1", "S01", "two_tier", 0, selected_poi_ids=["p_cafe"]),
        h3_record("P1", "S02", "memory_disabled", 0, selected_poi_ids=["p_food", "p_cafe"]),
        h3_record("P1", "S02", "two_tier", 0, selected_poi_ids=["p_food"]),
    ]
    metrics = run_h3(h3_manifest(profiles=("P1",), scenarios=("S01", "S02")), records)
    effect = _find_effect(metrics, "P1")
    detail = effect["paired_effect_details"]["two_tier"]
    assert detail["paired_units"] == 2
    # matched-unit mean = ((-1) + (0.5)) / 2 = -0.25
    assert effect["preferred_share_effect_two_tier_minus_baseline"] == pytest.approx(-0.25)


def test_unpaired_comparator_cannot_produce_effect(run_h3):
    records = [
        h3_record("P1", "S01", "two_tier", 0, selected_poi_ids=["p_food"]),
    ]
    metrics = run_h3(h3_manifest(profiles=("P1",), scenarios=("S01",)), records)
    detail = _find_effect(metrics, "P1")["paired_effect_details"]["two_tier"]
    assert detail["effect"] is None
    assert detail["paired_units"] == 0
    assert detail["reason"] in {"provenance_missing", "no_paired_units"}


def test_provenance_mismatch_blocks_profile_effects(run_h3):
    records = [
        h3_record("P1", "S01", "memory_disabled", 0, selected_poi_ids=["p_food"],
                  provenance=h3_provenance("S01", "memory_disabled", model_id="model-a")),
        h3_record("P1", "S01", "two_tier", 0, selected_poi_ids=["p_food"],
                  provenance=h3_provenance("S01", "two_tier", model_id="model-b")),
    ]
    metrics = run_h3(h3_manifest(profiles=("P1",), scenarios=("S01",)), records)
    effect = _find_effect(metrics, "P1")
    assert effect["preferred_share_effect_two_tier_minus_baseline"] is None
    assert effect["paired_effect_details"]["two_tier"]["reason"] == "provenance_inconsistent"
    assert any("blocked" in note for note in metrics["diagnostics"])


def test_synthetic_h3_is_labelled_not_a_conclusion(run_h3):
    metrics = run_h3(h3_manifest(profiles=("P1",), scenarios=("S01",)),
                     [h3_record("P1", "S01", "two_tier", 0, selected_poi_ids=["p_food"])])
    assert metrics["label"] == "SYNTHETIC EVALUATOR TEST"
    assert metrics["thesis_conclusion"] is False
