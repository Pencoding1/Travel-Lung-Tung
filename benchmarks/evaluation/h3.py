"""H3 (two-tier memory / personalization) offline evaluator.

Preferred share follows the protocol denominator: **all selected stops**, not the
resolved subset. When some selected stops have an unknown category or an unknown
authored preference, an exact share is not claimed: the share is ``null`` with a
coverage interval (``lower``..``upper``) and the resolved-subset share is a
separately labelled diagnostic. Duplicate selected IDs do not inflate the share
unless the manifest explicitly permits repeated visits.

Paired profile effects are computed across **matching scenario/repetition units**
(condition minus baseline for the same unit), never by pooling unmatched
selections. A missing comparator cannot produce an effect. Comparative effects
require H2-style provenance consistency (dataset/candidate/model/settings/input
identifiers) across conditions; labels alone are not trusted.
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .common import (
    EVIDENCE_LEVELS,
    H3_BASELINE_CONDITION,
    H3_CONDITIONS,
    INCONCLUSIVE_LABEL,
    LIVE_LABEL,
    SYNTHETIC_LABEL,
    assert_unique,
    require_bool,
    require_bool_or_null,
    require_enum,
    require_int,
    require_int_or_null,
    require_mapping,
    require_nonblank_str,
    require_number_or_null,
    require_str_list,
)
from .errors import ManifestError, RecordError, SchemaError
from .usage import parse_provider_usage

H3_SCHEMA_VERSION = "oc18.h3.v1"
H3_RUN_STATUSES = ("completed", "failed", "error")
H3_VALIDATION_STATUSES = ("feasible", "partial", "unverifiable", "no_plan", "failed", "unknown")
H3_PROVENANCE_COMMON_FIELDS = (
    "candidate_id", "route_id", "prompt_information_id",
    "dataset_id", "model_id", "settings_id",
)
H3_PROVENANCE_FIELDS = H3_PROVENANCE_COMMON_FIELDS + ("method_instruction_hash",)
H3_DELIVERY_STATES = ("delivered", "failed", "error", "refused", "empty", "missing")
MIN_THESIS_PROFILES = 5


def parse_h3_manifest(raw: Any) -> Dict[str, Any]:
    data = require_mapping(raw, "h3_manifest")
    manifest_version = require_nonblank_str(data.get("manifest_version"), "manifest_version")
    task = require_nonblank_str(data.get("task"), "task")
    if task != "H3":
        raise ManifestError(f"manifest task must be 'H3', found '{task}'")
    thesis_mode = require_bool(data.get("thesis_mode"), "thesis_mode")
    label = require_nonblank_str(data.get("label", "unnamed"), "label")
    allow_repeated_visits = require_bool(data.get("allow_repeated_visits", False),
                                         "allow_repeated_visits")

    conditions = require_str_list(data.get("conditions"), "conditions")
    if set(conditions) != set(H3_CONDITIONS) or len(conditions) != len(H3_CONDITIONS):
        raise ManifestError(
            f"conditions must distinguish exactly {H3_CONDITIONS}, found {tuple(conditions)}")
    baseline = require_nonblank_str(data.get("baseline_condition"), "baseline_condition")
    if baseline != H3_BASELINE_CONDITION:
        raise ManifestError(f"baseline_condition must be '{H3_BASELINE_CONDITION}'")

    repetitions = require_int(data.get("repetitions_per_case"), "repetitions_per_case",
                              minimum=1, maximum=1000)

    raw_profiles = data.get("profiles")
    if not isinstance(raw_profiles, list) or not raw_profiles:
        raise ManifestError("profiles must be a non-empty list")
    profile_ids: List[str] = []
    for index, entry in enumerate(raw_profiles):
        item = require_mapping(entry, f"profiles[{index}]")
        profile_ids.append(require_nonblank_str(item.get("profile_id"),
                                                f"profiles[{index}].profile_id"))
    assert_unique(profile_ids, "profiles.profile_id")
    if thesis_mode and len(profile_ids) < MIN_THESIS_PROFILES:
        raise ManifestError(
            f"thesis_mode requires >= {MIN_THESIS_PROFILES} declared profiles, "
            f"found {len(profile_ids)}")

    raw_scenarios = data.get("scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise ManifestError("scenarios must be a non-empty list")
    scenario_ids: List[str] = []
    for index, entry in enumerate(raw_scenarios):
        item = require_mapping(entry, f"scenarios[{index}]")
        scenario_ids.append(require_nonblank_str(item.get("scenario_id"),
                                                 f"scenarios[{index}].scenario_id"))
    assert_unique(scenario_ids, "scenarios.scenario_id")

    category_truth_raw = require_mapping(data.get("category_truth"), "category_truth")
    category_truth: Dict[str, Tuple[str, ...]] = {}
    for poi_id, categories in category_truth_raw.items():
        key = require_nonblank_str(poi_id, "category_truth.<key>")
        category_truth[key] = tuple(require_str_list(categories, f"category_truth.{key}"))

    active_raw = require_mapping(data.get("active_preference_truth"), "active_preference_truth")
    active_truth: Dict[str, Dict[str, Tuple[str, ...]]] = {}
    for profile_id, per_scenario in active_raw.items():
        profile_key = require_nonblank_str(profile_id, "active_preference_truth.<key>")
        if profile_key not in profile_ids:
            raise ManifestError(f"active_preference_truth references unknown profile "
                                f"'{profile_key}'")
        per_scenario_map = require_mapping(per_scenario,
                                           f"active_preference_truth.{profile_key}")
        mapped: Dict[str, Tuple[str, ...]] = {}
        for scenario_id, categories in per_scenario_map.items():
            scenario_key = require_nonblank_str(
                scenario_id, f"active_preference_truth.{profile_key}.<key>")
            if scenario_key not in scenario_ids:
                raise ManifestError(
                    f"active_preference_truth.{profile_key} references unknown scenario "
                    f"'{scenario_key}'")
            mapped[scenario_key] = tuple(require_str_list(
                categories, f"active_preference_truth.{profile_key}.{scenario_key}"))
        active_truth[profile_key] = mapped

    expected_keys = {
        (profile_id, scenario_id, condition, repetition)
        for profile_id in profile_ids
        for scenario_id in scenario_ids
        for condition in conditions
        for repetition in range(repetitions)
    }
    return {
        "manifest_version": manifest_version,
        "task": task,
        "thesis_mode": thesis_mode,
        "label": label,
        "conditions": tuple(conditions),
        "baseline_condition": baseline,
        "allow_repeated_visits": allow_repeated_visits,
        "repetitions_per_case": repetitions,
        "profile_ids": tuple(profile_ids),
        "scenario_ids": tuple(scenario_ids),
        "category_truth": category_truth,
        "active_preference_truth": active_truth,
        "expected_keys": expected_keys,
    }


def _normalise_provenance(raw: Any, field: str) -> Optional[Dict[str, Optional[str]]]:
    if raw is None:
        return None
    data = require_mapping(raw, field)
    result: Dict[str, Optional[str]] = {}
    for key in H3_PROVENANCE_FIELDS:
        value = data.get(key)
        if value is None:
            result[key] = None
        else:
            result[key] = require_nonblank_str(value, f"{field}.{key}")
    return result


def normalise_h3_record(raw: Mapping[str, Any], manifest: Mapping[str, Any]) -> Dict[str, Any]:
    schema_version = require_nonblank_str(raw.get("schema_version"), "schema_version")
    if schema_version != H3_SCHEMA_VERSION:
        raise RecordError(f"record schema_version must be '{H3_SCHEMA_VERSION}', "
                          f"found '{schema_version}'")
    if require_nonblank_str(raw.get("task"), "task") != "H3":
        raise RecordError("record task must be 'H3'")

    evidence_level = require_enum(raw.get("evidence_level"), "evidence_level", EVIDENCE_LEVELS)
    dataset_kind = require_nonblank_str(raw.get("dataset_kind"), "dataset_kind")
    profile_id = require_nonblank_str(raw.get("profile_id"), "profile_id")
    scenario_id = require_nonblank_str(raw.get("scenario_id"), "scenario_id")
    condition = require_nonblank_str(raw.get("condition"), "condition")
    repetition = require_int(raw.get("repetition"), "repetition", minimum=0)

    if profile_id not in manifest["profile_ids"]:
        raise RecordError(f"record references undeclared profile_id '{profile_id}'")
    if scenario_id not in manifest["scenario_ids"]:
        raise RecordError(f"record references unknown scenario_id '{scenario_id}'")
    if condition not in manifest["conditions"]:
        raise RecordError(f"record references undeclared condition '{condition}'")
    if repetition >= manifest["repetitions_per_case"]:
        raise RecordError(f"record repetition {repetition} exceeds declared "
                          f"repetitions_per_case {manifest['repetitions_per_case']}")

    run_status = require_enum(raw.get("run_status"), "run_status", H3_RUN_STATUSES)
    plan_present = require_bool(raw.get("plan_present"), "plan_present")
    empty_plan = require_bool(raw.get("empty_plan"), "empty_plan")
    validation_status = require_enum(raw.get("validation_status"), "validation_status",
                                     H3_VALIDATION_STATUSES)
    unverifiable = require_bool(raw.get("unverifiable", False), "unverifiable")
    constraint_valid = require_bool_or_null(raw.get("constraint_valid"), "constraint_valid")
    selected_poi_ids = require_str_list(raw.get("selected_poi_ids", []), "selected_poi_ids")

    usage = parse_provider_usage(raw.get("usage"), "usage")
    latency = require_number_or_null(raw.get("latency_seconds"), "latency_seconds")
    failure_retries = require_int_or_null(raw.get("failure_retries", None),
                                          "failure_retries", minimum=0)
    provenance = _normalise_provenance(raw.get("provenance"), "provenance")

    delivery = _delivery_state(run_status, plan_present, empty_plan, validation_status)
    return {
        "profile_id": profile_id,
        "scenario_id": scenario_id,
        "condition": condition,
        "repetition": repetition,
        "evidence_level": evidence_level,
        "dataset_kind": dataset_kind,
        "run_status": run_status,
        "delivery": delivery,
        "validation_status": validation_status,
        "unverifiable": unverifiable,
        "constraint_valid": constraint_valid,
        "selected_poi_ids": selected_poi_ids,
        "usage": usage,
        "latency_seconds": latency,
        "failure_retries": failure_retries,
        "provenance": provenance,
        "source_line": raw.get("_source_line"),
    }


def _delivery_state(run_status: str, plan_present: bool, empty_plan: bool,
                    validation_status: str) -> str:
    if run_status in ("failed", "error"):
        return run_status
    if (not plan_present) or empty_plan:
        return "empty"
    if validation_status == "no_plan":
        return "refused"
    if validation_status == "failed":
        return "failed"
    return "delivered"


def load_h3_records(raw_records: Sequence[Mapping[str, Any]],
                    manifest: Mapping[str, Any]
                    ) -> Dict[Tuple[str, str, str, int], Dict[str, Any]]:
    loaded: Dict[Tuple[str, str, str, int], Dict[str, Any]] = {}
    for raw in raw_records:
        record = normalise_h3_record(raw, manifest)
        key = (record["profile_id"], record["scenario_id"], record["condition"],
               record["repetition"])
        if key in loaded:
            previous = loaded[key]["source_line"]
            raise RecordError(
                f"duplicate H3 record key {key} (already recorded at line {previous}); "
                "duplicates are errors, not silent overwrites")
        loaded[key] = record
    return loaded


def _resolve_stops(record: Mapping[str, Any],
                   category_truth: Mapping[str, Tuple[str, ...]],
                   active_truth: Mapping[str, Mapping[str, Tuple[str, ...]]],
                   allow_repeated_visits: bool) -> Dict[str, Any]:
    id_list = list(record["selected_poi_ids"])
    duplicates = 0
    if not allow_repeated_visits:
        seen = set()
        deduped = []
        for poi_id in id_list:
            if poi_id in seen:
                duplicates += 1
                continue
            seen.add(poi_id)
            deduped.append(poi_id)
        id_list = deduped
    active_ids = active_truth.get(record["profile_id"], {}).get(record["scenario_id"])
    preferred = 0
    non_preferred = 0
    unknown_category = 0
    unknown_preference = 0
    for poi_id in id_list:
        categories = category_truth.get(poi_id)
        if categories is None:
            unknown_category += 1
            continue
        if active_ids is None:
            unknown_preference += 1
            continue
        if set(categories) & set(active_ids):
            preferred += 1
        else:
            non_preferred += 1
    selected_total = preferred + non_preferred + unknown_category + unknown_preference
    return {
        "selected_total": selected_total,
        "preferred": preferred,
        "non_preferred": non_preferred,
        "unknown_category": unknown_category,
        "unknown_preference": unknown_preference,
        "unknown_total": unknown_category + unknown_preference,
        "duplicate_selected_ids": duplicates,
    }


def _share_from_pool(pool: Mapping[str, int], empty_plan_records: int) -> Dict[str, Any]:
    selected_total = pool["selected_total"]
    unknown = pool["unknown_total"]
    if selected_total == 0:
        reason = "empty_plan" if empty_plan_records > 0 else "no_selected_stops"
        return {"share": None, "reason": reason, "lower": None, "upper": None,
                "resolved_subset_share": _safe_div(pool["preferred"],
                                                   pool["preferred"] + pool["non_preferred"])}
    if unknown == 0:
        exact = pool["preferred"] / selected_total
        return {"share": exact, "reason": None, "lower": exact, "upper": exact,
                "resolved_subset_share": exact}
    return {
        "share": None,
        "reason": "coverage_gap",
        "lower": pool["preferred"] / selected_total,
        "upper": (pool["preferred"] + unknown) / selected_total,
        "resolved_subset_share": _safe_div(pool["preferred"],
                                           pool["preferred"] + pool["non_preferred"]),
    }


def _safe_div(numerator: int, denominator: int) -> Optional[float]:
    if denominator == 0:
        return None
    return numerator / denominator


def _share_detail(group: Mapping[str, Any]) -> Dict[str, Any]:
    """Unambiguous per-condition preferred-share report block.

    ``value`` is the exact all-selected-stops share (``None`` on a coverage gap);
    ``lower``/``upper`` bound the share when unknown stops exist, ``coverage``
    is the resolved fraction of selected stops, and ``resolved_subset_share`` is
    a separately labelled diagnostic that must never be read as the headline.
    """
    pool = group["selected_stop_pool"]
    return {
        "value": group["preferred_share"],
        "reason": group["preferred_share_reason"],
        "lower": group["preferred_share_lower"],
        "upper": group["preferred_share_upper"],
        "resolved_subset_share": group["resolved_subset_share"],
        "selected_total": pool["selected_total"],
        "preferred": pool["preferred_hits"],
        "non_preferred": pool["non_preferred"],
        "resolved_total": pool["resolved_denominator"],
        "unknown_total": pool["unknown_total"],
        "coverage": _safe_div(pool["resolved_denominator"], pool["selected_total"]),
    }


def _unit_share(record: Mapping[str, Any],
                category_truth: Mapping[str, Tuple[str, ...]],
                active_truth: Mapping[str, Mapping[str, Tuple[str, ...]]],
                allow_repeated_visits: bool) -> Tuple[Optional[float], Optional[str]]:
    if record["delivery"] != "delivered":
        return None, "not_delivered"
    pool = _resolve_stops(record, category_truth, active_truth, allow_repeated_visits)
    if pool["selected_total"] == 0:
        return None, "no_selected_stops"
    if pool["unknown_total"] > 0:
        return None, "coverage_gap"
    return pool["preferred"] / pool["selected_total"], None


def _median(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return float(statistics.median(values))


def _group_metrics(records: Sequence[Mapping[str, Any]], planned: int,
                   category_truth: Mapping[str, Tuple[str, ...]],
                   active_truth: Mapping[str, Mapping[str, Tuple[str, ...]]],
                   allow_repeated_visits: bool) -> Dict[str, Any]:
    delivery_states = {state: 0 for state in H3_DELIVERY_STATES}
    pool = {"selected_total": 0, "preferred": 0, "non_preferred": 0,
            "unknown_category": 0, "unknown_preference": 0, "unknown_total": 0,
            "duplicate_selected_ids": 0}
    empty_plan_records = 0
    validity_evaluated = 0
    validity_valid = 0
    latency_values: List[float] = []
    retries_values: List[int] = []
    usage_known_total = 0
    usage_unknown = 0
    cold = {"supplied_records": 0, "interpretable_total": None}
    amortized = {"supplied_records": 0, "interpretable_total": None}
    for record in records:
        delivery = record["delivery"]
        delivery_states[delivery] += 1
        if delivery == "empty":
            empty_plan_records += 1
        if delivery == "delivered":
            resolved = _resolve_stops(record, category_truth, active_truth,
                                      allow_repeated_visits)
            for key in pool:
                pool[key] += resolved[key]
            if record["constraint_valid"] is not None:
                validity_evaluated += 1
                if record["constraint_valid"]:
                    validity_valid += 1
        if record["latency_seconds"] is not None:
            latency_values.append(record["latency_seconds"])
        if record["failure_retries"] is not None:
            retries_values.append(record["failure_retries"])
        usage = record["usage"]
        if usage["known"]:
            usage_known_total += usage["total"]
        else:
            usage_unknown += 1
        if usage["cold"] is not None:
            cold["supplied_records"] += 1
            cold_total = _extra_cost_total(usage["cold"])
            if cold_total is not None:
                cold["interpretable_total"] = (cold["interpretable_total"] or 0) + cold_total
        if usage["amortized"] is not None:
            amortized["supplied_records"] += 1
            amortized_total = _extra_cost_total(usage["amortized"])
            if amortized_total is not None:
                amortized["interpretable_total"] = \
                    (amortized["interpretable_total"] or 0) + amortized_total

    share = _share_from_pool(pool, empty_plan_records)
    delivery_states["missing"] = planned - len(records)
    return {
        "planned": planned,
        "observed": len(records),
        "missing": planned - len(records),
        "states": delivery_states,
        "delivered": delivery_states["delivered"],
        "selected_stop_pool": {
            "selected_total": pool["selected_total"],
            "preferred_hits": pool["preferred"],
            "non_preferred": pool["non_preferred"],
            "resolved_denominator": pool["preferred"] + pool["non_preferred"],
            "unknown_category_stops": pool["unknown_category"],
            "unknown_preference_stops": pool["unknown_preference"],
            "unknown_total": pool["unknown_total"],
            "duplicate_selected_ids": pool["duplicate_selected_ids"],
            "empty_plan_records": empty_plan_records,
        },
        "preferred_share": share["share"],
        "preferred_share_reason": share["reason"],
        "preferred_share_lower": share["lower"],
        "preferred_share_upper": share["upper"],
        "resolved_subset_share": share["resolved_subset_share"],
        "reported_share_basis": "selected_stops_with_coverage_interval",
        "constraint_validity": {
            "evaluated": validity_evaluated,
            "valid": validity_valid,
            "rate": (validity_valid / validity_evaluated) if validity_evaluated else None,
        },
        "usage": {
            "known_records": len(records) - usage_unknown,
            "unknown_records": usage_unknown,
            "known_total_provider_tokens": usage_known_total,
            "cold": cold,
            "amortized": amortized,
            "no_inferred_time_savings": True,
        },
        "latency_seconds": {
            "unit": "seconds",
            "n": len(latency_values),
            "min": min(latency_values) if latency_values else None,
            "median": _median(latency_values),
            "max": max(latency_values) if latency_values else None,
        },
        "failure_retries": {
            "n": len(retries_values),
            "total": sum(retries_values),
            "max": max(retries_values) if retries_values else None,
        },
    }


def _extra_cost_total(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, dict):
        total = value.get("total")
        if isinstance(total, int) and not isinstance(total, bool):
            return total
        stages = value.get("stages")
        if isinstance(stages, dict):
            required = ("summary", "extraction", "retrieval", "final")
            if all(isinstance(stages.get(stage), int) and not isinstance(stages.get(stage), bool)
                   for stage in required):
                computed = sum(stages[stage] for stage in required)
                retries = stages.get("retries")
                if isinstance(retries, int) and not isinstance(retries, bool):
                    computed += retries
                return computed
    return None


def _provenance_key(record: Mapping[str, Any]) -> Optional[Tuple[Optional[str], ...]]:
    provenance = record["provenance"]
    if not provenance:
        return None
    return tuple(provenance.get(field) for field in H3_PROVENANCE_COMMON_FIELDS)


def _pair_provenance_status(profile_id: str, cond_a: str, cond_b: str,
                            scenario_ids: Sequence[str], repetitions: int,
                            loaded: Mapping[Tuple[str, str, str, int], Mapping[str, Any]]
                            ) -> Dict[str, Any]:
    """Provenance consistency for one condition pair (not across all conditions)."""
    for scenario_id in scenario_ids:
        keys_by_condition: Dict[str, Optional[Tuple[Optional[str], ...]]] = {}
        missing = False
        for condition in (cond_a, cond_b):
            keys = set()
            had_record = False
            for repetition in range(repetitions):
                record = loaded.get((profile_id, scenario_id, condition, repetition))
                if record is None:
                    continue
                had_record = True
                key = _provenance_key(record)
                if key is None or any(part is None for part in key):
                    missing = True
                    continue
                keys.add(key)
            keys_by_condition[condition] = next(iter(keys)) if len(keys) == 1 else None
            if not had_record:
                keys_by_condition[condition] = None
                missing = True
        values = [keys_by_condition[cond_a], keys_by_condition[cond_b]]
        if any(value is None for value in values) or values[0] != values[1]:
            reason = "missing_provenance" if missing else "inconsistent_provenance"
            return {"status": "blocked", "reason": reason, "scenario_id": scenario_id}
    return {"status": "compatible", "reason": None, "scenario_id": None}


def evaluate_h3(manifest: Mapping[str, Any],
                loaded: Mapping[Tuple[str, str, str, int], Mapping[str, Any]],
                *,
                manifest_sha256: Optional[str] = None,
                records_sha256: Optional[str] = None) -> Dict[str, Any]:
    conditions = manifest["conditions"]
    baseline = manifest["baseline_condition"]
    repetitions = manifest["repetitions_per_case"]
    profile_ids = manifest["profile_ids"]
    scenario_ids = manifest["scenario_ids"]
    category_truth = manifest["category_truth"]
    active_truth = manifest["active_preference_truth"]
    allow_repeated_visits = manifest["allow_repeated_visits"]

    all_records = list(loaded.values())
    evidence_levels = sorted({record["evidence_level"] for record in all_records})
    dataset_kinds = sorted({record["dataset_kind"] for record in all_records})
    planned_per_group = len(scenario_ids) * repetitions

    diagnostics: List[str] = []
    groups: Dict[str, Dict[str, Any]] = {}
    for profile_id in profile_ids:
        groups[profile_id] = {}
        for condition in conditions:
            group_records = [
                loaded.get((profile_id, scenario_id, condition, repetition))
                for scenario_id in scenario_ids
                for repetition in range(repetitions)
            ]
            present = [record for record in group_records if record is not None]
            groups[profile_id][condition] = _group_metrics(
                present, planned_per_group, category_truth, active_truth,
                allow_repeated_visits)

    profile_effects: List[Dict[str, Any]] = []
    for profile_id in profile_ids:
        effect_entry: Dict[str, Any] = {
            "profile_id": profile_id,
            "baseline_condition": baseline,
            "preferred_share_by_condition": {
                condition: groups[profile_id][condition]["preferred_share"]
                for condition in conditions
            },
            "resolved_subset_share_by_condition": {
                condition: groups[profile_id][condition]["resolved_subset_share"]
                for condition in conditions
            },
            "preferred_share_detail_by_condition": {
                condition: _share_detail(groups[profile_id][condition])
                for condition in conditions
            },
            "constraint_validity_by_condition": {
                condition: groups[profile_id][condition]["constraint_validity"]["rate"]
                for condition in conditions
            },
            "token_reduction_by_condition": {},
            "paired_effect_details": {},
        }
        profile_blocked = False
        for condition in conditions:
            if condition == baseline:
                continue
            prov = _pair_provenance_status(profile_id, baseline, condition,
                                           scenario_ids, repetitions, loaded)
            if prov["status"] != "compatible":
                profile_blocked = True
                diagnostics.append(
                    f"{profile_id}: {baseline} vs {condition} effects blocked "
                    f"({prov['reason']} at {prov['scenario_id']})")
            detail = _paired_unit_effect(
                profile_id, condition, baseline, scenario_ids, repetitions, loaded,
                category_truth, active_truth, allow_repeated_visits)
            if prov["status"] != "compatible":
                detail["effect"] = None
                detail["reason"] = ("provenance_missing" if prov["reason"] == "missing_provenance"
                                    else "provenance_inconsistent")
            detail["provenance_status"] = prov["status"]
            effect_entry[f"preferred_share_effect_{condition}_minus_baseline"] = detail["effect"]
            effect_entry["paired_effect_details"][condition] = detail
            effect_entry["token_reduction_by_condition"][condition] = detail["token_reduction"]
        effect_entry["provenance_status"] = "blocked" if profile_blocked else "compatible"
        profile_effects.append(effect_entry)

    for profile_id in profile_ids:
        for condition in conditions:
            group = groups[profile_id][condition]
            pool = group["selected_stop_pool"]
            if pool["unknown_category_stops"]:
                diagnostics.append(
                    f"{profile_id}/{condition}: {pool['unknown_category_stops']} selected "
                    "stop(s) had no frozen category (coverage gap, not preference)")
            if pool["unknown_preference_stops"]:
                diagnostics.append(
                    f"{profile_id}/{condition}: {pool['unknown_preference_stops']} selected "
                    "stop(s) had no authored active-preference truth (coverage gap)")
            if pool["duplicate_selected_ids"]:
                diagnostics.append(
                    f"{profile_id}/{condition}: {pool['duplicate_selected_ids']} duplicate "
                    "selected stop id(s) deduplicated (repeated visits not permitted)")

    planned_runs = len(profile_ids) * len(scenario_ids) * len(conditions) * repetitions
    if evidence_levels and evidence_levels == ["synthetic_engineering"]:
        conclusion_label = SYNTHETIC_LABEL
    elif evidence_levels and evidence_levels == ["live_model"]:
        conclusion_label = LIVE_LABEL
    else:
        conclusion_label = INCONCLUSIVE_LABEL

    return {
        "task": "H3",
        "schema_version": H3_SCHEMA_VERSION,
        "manifest_version": manifest["manifest_version"],
        "manifest_label": manifest["label"],
        "thesis_mode": manifest["thesis_mode"],
        "allow_repeated_visits": allow_repeated_visits,
        "label": conclusion_label,
        "conclusion_label": conclusion_label,
        "thesis_conclusion": False,
        "data_classification": (
            "synthetic_engineering_fixture" if evidence_levels == ["synthetic_engineering"]
            else ("mixed" if len(evidence_levels) > 1 else "live_evidence")),
        "evidence_levels": evidence_levels,
        "dataset_kinds": dataset_kinds,
        "input": {"manifest_sha256": manifest_sha256, "records_sha256": records_sha256},
        "conditions": list(conditions),
        "baseline_condition": baseline,
        "repetitions_per_case": repetitions,
        "profiles": list(profile_ids),
        "planned_runs": planned_runs,
        "observed_runs": len(all_records),
        "missing_runs": planned_runs - len(all_records),
        "groups": groups,
        "profile_effects": profile_effects,
        "diagnostics": diagnostics,
    }


def _paired_unit_effect(profile_id: str, condition: str, baseline: str,
                        scenario_ids: Sequence[str], repetitions: int,
                        loaded: Mapping[Tuple[str, str, str, int], Mapping[str, Any]],
                        category_truth: Mapping[str, Tuple[str, ...]],
                        active_truth: Mapping[str, Mapping[str, Tuple[str, ...]]],
                        allow_repeated_visits: bool) -> Dict[str, Any]:
    deltas: List[float] = []
    excluded: List[Dict[str, Any]] = []
    base_tokens = 0
    cond_tokens = 0
    token_units = 0
    token_unknown_units = 0
    for scenario_id in scenario_ids:
        for repetition in range(repetitions):
            base_record = loaded.get((profile_id, scenario_id, baseline, repetition))
            cond_record = loaded.get((profile_id, scenario_id, condition, repetition))
            unit = {"scenario_id": scenario_id, "repetition": repetition}
            if base_record is None or cond_record is None:
                excluded.append({**unit, "reason": "missing_comparator"})
                continue
            base_share, base_reason = _unit_share(base_record, category_truth, active_truth,
                                                  allow_repeated_visits)
            cond_share, cond_reason = _unit_share(cond_record, category_truth, active_truth,
                                                  allow_repeated_visits)
            if base_share is None or cond_share is None:
                excluded.append({**unit, "reason": f"share_undetermined:"
                                 f"{base_reason or cond_reason}"})
                continue
            deltas.append(cond_share - base_share)
            if base_record["usage"]["known"] and cond_record["usage"]["known"]:
                base_tokens += base_record["usage"]["total"]
                cond_tokens += cond_record["usage"]["total"]
                token_units += 1
            else:
                token_unknown_units += 1

    if deltas:
        effect: Optional[float] = sum(deltas) / len(deltas)
        effect_reason: Optional[str] = None
    else:
        effect = None
        effect_reason = "no_paired_units"

    if token_unknown_units:
        reduction = {"value": None, "reason": "unknown_usage_present",
                     "baseline_total": base_tokens, "condition_total": cond_tokens}
    elif token_units == 0:
        reduction = {"value": None, "reason": "no_paired_units",
                     "baseline_total": base_tokens, "condition_total": cond_tokens}
    elif base_tokens == 0:
        reduction = {"value": None, "reason": "undefined_zero_baseline",
                     "baseline_total": 0, "condition_total": cond_tokens}
    else:
        reduction = {"value": (base_tokens - cond_tokens) / base_tokens, "reason": None,
                     "baseline_total": base_tokens, "condition_total": cond_tokens}

    return {
        "condition": condition,
        "baseline_condition": baseline,
        "effect": effect,
        "reason": effect_reason,
        "paired_units": len(deltas),
        "excluded_units": excluded,
        "unit_effect_definition": "share(condition) - share(baseline) within the same unit",
        "token_reduction": reduction,
    }
