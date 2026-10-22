"""H2 (hybrid itinerary vs LLM-only) offline evaluator.

The evaluator consumes a frozen manifest and explicit JSONL outcome records. It
never executes a live experiment. Delivery and outcome are modelled as two
**orthogonal** dimensions: a real non-empty plan that is unverifiable is still a
delivered plan (not a refusal), and an independently known violation is retained
even when some facts are unknown. Failed/refused/empty/unverifiable/missing runs
stay inside the planned denominator and are reported separately.

Completeness contracts (OC-018-R1):

* ``temporal_violation``, ``known_temporal_violations``,
  ``violation_count_complete`` and ``unverifiable`` are all required and are
  never defaulted to a verified zero.
* A contradiction is rejected: ``feasible`` with any known violation; a
  ``false`` flag with a nonzero/absent count; a ``true`` flag with a
  *complete* count of zero; ``unverifiable`` with a ``false`` flag.
* A scenario is only credited with "no verified violation" when **all** planned
  repetitions are complete valid observations. A known violation stays true even
  with incomplete coverage; anything else stays unknown.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .common import (
    EVIDENCE_LEVELS,
    H2_PRIMARY_BINARY_OUTCOME,
    INCONCLUSIVE_LABEL,
    LIVE_LABEL,
    SYNTHETIC_LABEL,
    assert_unique,
    require_bool,
    require_enum,
    require_int,
    require_mapping,
    require_nonblank_str,
    require_number_or_null,
    require_str_list,
)
from .errors import ManifestError, RecordError, SchemaError
from .stats import (
    DEFAULT_BOOTSTRAP_DRAWS,
    DEFAULT_BOOTSTRAP_SEED,
    exact_mcnemar_two_sided,
    paired_effect_bootstrap_ci,
)
from .usage import parse_provider_usage

H2_SCHEMA_VERSION = "oc18.h2.v1"
H2_RUN_STATUSES = ("completed", "failed", "error", "refused")
H2_VALIDATION_STATUSES = ("feasible", "partial", "unverifiable", "no_plan", "failed", "unknown")
H2_PROVENANCE_COMMON_FIELDS = (
    "candidate_id", "route_id", "prompt_information_id",
    "dataset_id", "model_id", "settings_id",
)
H2_PROVENANCE_FIELDS = H2_PROVENANCE_COMMON_FIELDS + ("method_instruction_hash",)

# Delivery is about whether a usable plan was produced; outcome is about the
# independent verdict on that plan. They are reported separately so a delivered
# but unverifiable plan is never miscounted as a refusal or as a clean success.
H2_DELIVERY_STATES = ("delivered", "failed", "error", "refused", "empty", "missing")
H2_OUTCOME_STATES = ("violation", "clean", "unverifiable", "unknown", "not_delivered")

MIN_THESIS_SCENARIOS = 20


def parse_h2_manifest(raw: Any) -> Dict[str, Any]:
    data = require_mapping(raw, "h2_manifest")
    manifest_version = require_nonblank_str(data.get("manifest_version"), "manifest_version")
    task = require_nonblank_str(data.get("task"), "task")
    if task != "H2":
        raise ManifestError(f"manifest task must be 'H2', found '{task}'")
    thesis_mode = require_bool(data.get("thesis_mode"), "thesis_mode")
    label = require_nonblank_str(data.get("label", "unnamed"), "label")

    conditions = require_str_list(data.get("paired_conditions"), "paired_conditions")
    if len(conditions) != 2:
        raise ManifestError("paired_conditions must declare exactly two conditions")
    if conditions[0] == conditions[1]:
        raise ManifestError("paired_conditions must be two distinct conditions")

    repetitions = require_int(data.get("repetitions_per_case"), "repetitions_per_case",
                              minimum=1, maximum=1000)

    raw_scenarios = data.get("scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise ManifestError("scenarios must be a non-empty list")
    scenario_ids: List[str] = []
    for index, entry in enumerate(raw_scenarios):
        item = require_mapping(entry, f"scenarios[{index}]")
        scenario_ids.append(require_nonblank_str(item.get("scenario_id"),
                                                 f"scenarios[{index}].scenario_id"))
    assert_unique(scenario_ids, "scenarios.scenario_id")

    if thesis_mode and len(scenario_ids) < MIN_THESIS_SCENARIOS:
        raise ManifestError(
            f"thesis_mode requires >= {MIN_THESIS_SCENARIOS} frozen scenario IDs, "
            f"found {len(scenario_ids)}")

    expected_keys = {
        (scenario_id, condition, repetition)
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
        "repetitions_per_case": repetitions,
        "scenario_ids": tuple(scenario_ids),
        "expected_keys": expected_keys,
    }


def _normalise_provenance(raw: Any, field: str) -> Optional[Dict[str, Optional[str]]]:
    if raw is None:
        return None
    data = require_mapping(raw, field)
    result: Dict[str, Optional[str]] = {}
    for key in H2_PROVENANCE_FIELDS:
        value = data.get(key)
        if value is None:
            result[key] = None
        else:
            result[key] = require_nonblank_str(value, f"{field}.{key}")
    return result


def _validate_outcome_consistency(validation_status: str, temporal_violation: Optional[bool],
                                  known: Optional[int], complete: bool,
                                  unverifiable: bool) -> None:
    """Reject contradictory outcome fields; never silently coerce them."""
    if known is None and complete:
        raise RecordError(
            "violation_count_complete is true but known_temporal_violations is null")
    if validation_status == "feasible":
        if temporal_violation is not False:
            raise RecordError(
                "contradiction: validation_status=feasible requires temporal_violation=false")
        if known not in (0,):
            raise RecordError(
                "contradiction: validation_status=feasible cannot carry known violations")
        if unverifiable:
            raise RecordError(
                "contradiction: validation_status=feasible cannot be unverifiable")
    if temporal_violation is False:
        if known != 0:
            raise RecordError(
                "contradiction: temporal_violation=false with a nonzero or unknown "
                "known_temporal_violations")
        if unverifiable:
            raise RecordError(
                "contradiction: temporal_violation=false while unverifiable=true")
    if temporal_violation is True and complete and known == 0:
        raise RecordError(
            "contradiction: temporal_violation=true with a complete count of zero")
    if temporal_violation is True and known is not None and known == 0 and not complete:
        # Allowed: a violation is known but the count is explicitly incomplete.
        pass


def normalise_h2_record(raw: Mapping[str, Any], manifest: Mapping[str, Any]) -> Dict[str, Any]:
    schema_version = require_nonblank_str(raw.get("schema_version"), "schema_version")
    if schema_version != H2_SCHEMA_VERSION:
        raise RecordError(f"record schema_version must be '{H2_SCHEMA_VERSION}', "
                          f"found '{schema_version}'")
    if require_nonblank_str(raw.get("task"), "task") != "H2":
        raise RecordError("record task must be 'H2'")

    evidence_level = require_enum(raw.get("evidence_level"), "evidence_level", EVIDENCE_LEVELS)
    dataset_kind = require_nonblank_str(raw.get("dataset_kind"), "dataset_kind")
    scenario_id = require_nonblank_str(raw.get("scenario_id"), "scenario_id")
    condition = require_nonblank_str(raw.get("condition"), "condition")
    repetition = require_int(raw.get("repetition"), "repetition", minimum=0)

    if scenario_id not in manifest["scenario_ids"]:
        raise RecordError(f"record references unknown scenario_id '{scenario_id}'")
    if condition not in manifest["conditions"]:
        raise RecordError(f"record references undeclared condition '{condition}'")
    if repetition >= manifest["repetitions_per_case"]:
        raise RecordError(
            f"record repetition {repetition} exceeds declared repetitions_per_case "
            f"{manifest['repetitions_per_case']} for scenario '{scenario_id}'")

    run_status = require_enum(raw.get("run_status"), "run_status", H2_RUN_STATUSES)
    plan_present = require_bool(raw.get("plan_present"), "plan_present")
    empty_plan = require_bool(raw.get("empty_plan"), "empty_plan")
    validation_status = require_enum(raw.get("validation_status"), "validation_status",
                                     H2_VALIDATION_STATUSES)
    unverifiable = require_bool(raw.get("unverifiable"), "unverifiable")

    violation = raw.get("temporal_violation")
    if violation is not None and not isinstance(violation, bool):
        raise SchemaError("temporal_violation: expected a boolean or null")
    known_raw = raw.get("known_temporal_violations")
    known = None if known_raw is None else require_int(known_raw, "known_temporal_violations",
                                                       minimum=0)
    complete = require_bool(raw.get("violation_count_complete"), "violation_count_complete")
    _validate_outcome_consistency(validation_status, violation, known, complete, unverifiable)

    unknown_reasons = require_str_list(raw.get("unknown_reasons", []), "unknown_reasons")
    provenance = _normalise_provenance(raw.get("provenance"), "provenance")
    usage = parse_provider_usage(raw.get("usage"), "usage")

    delivery = _delivery_state(run_status, plan_present, empty_plan, validation_status)
    outcome = _outcome_state(delivery, validation_status, violation, unverifiable)

    return {
        "scenario_id": scenario_id,
        "condition": condition,
        "repetition": repetition,
        "evidence_level": evidence_level,
        "dataset_kind": dataset_kind,
        "run_status": run_status,
        "delivery": delivery,
        "outcome": outcome,
        "temporal_violation": violation,
        "known_temporal_violations": known,
        "violation_count_complete": complete,
        "unverifiable": unverifiable,
        "validation_status": validation_status,
        "unknown_reasons": unknown_reasons,
        "provenance": provenance,
        "usage": usage,
        # Optional secondary outcome fields (never invented):
        "selected_poi_ids": _optional_str_list(raw.get("selected_poi_ids"), "selected_poi_ids"),
        "grounded_source_poi_ids": _optional_str_list(
            raw.get("grounded_source_poi_ids"), "grounded_source_poi_ids"),
        "budget_deviation": _normalise_budget(raw.get("budget_deviation")),
        "route_travel_minutes": _optional_int(raw.get("route_travel_minutes"),
                                              "route_travel_minutes"),
        "route_distance_km": require_number_or_null(raw.get("route_distance_km"),
                                                    "route_distance_km"),
        "latency_seconds": require_number_or_null(raw.get("latency_seconds"), "latency_seconds"),
        "source_line": raw.get("_source_line"),
    }


def _optional_str_list(value: Any, field: str) -> Optional[List[str]]:
    if value is None:
        return None
    return require_str_list(value, field)


def _optional_int(value: Any, field: str) -> Optional[int]:
    if value is None:
        return None
    return require_int(value, field, minimum=0)


def _normalise_budget(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    data = require_mapping(value, "budget_deviation")
    amount = data.get("amount")
    if amount is None:
        raise SchemaError("budget_deviation.amount: required")
    currency = require_nonblank_str(data.get("currency"), "budget_deviation.currency")
    unit = require_nonblank_str(data.get("unit"), "budget_deviation.unit")
    comparable = require_bool(data.get("comparable"), "budget_deviation.comparable")
    if isinstance(amount, bool) or not isinstance(amount, (int, float, str)):
        raise SchemaError("budget_deviation.amount: expected a number or decimal string")
    return {"amount": amount, "currency": currency, "unit": unit, "comparable": comparable}


def _delivery_state(run_status: str, plan_present: bool, empty_plan: bool,
                    validation_status: str) -> str:
    if run_status in ("failed", "error"):
        return run_status
    if run_status == "refused":
        return "refused"
    if (not plan_present) or empty_plan:
        return "empty"
    if validation_status == "no_plan":
        return "refused"
    if validation_status == "failed":
        return "failed"
    return "delivered"


def _outcome_state(delivery: str, validation_status: str,
                   violation: Optional[bool], unverifiable: bool) -> str:
    if delivery != "delivered":
        return "not_delivered"
    # A known violation is retained even when other facts are unknown.
    if violation is True:
        return "violation"
    if violation is False:
        return "clean"
    if unverifiable or validation_status == "unverifiable":
        return "unverifiable"
    return "unknown"


def load_h2_records(raw_records: Sequence[Mapping[str, Any]],
                    manifest: Mapping[str, Any]) -> Dict[Tuple[str, str, int], Dict[str, Any]]:
    loaded: Dict[Tuple[str, str, int], Dict[str, Any]] = {}
    for raw in raw_records:
        record = normalise_h2_record(raw, manifest)
        key = (record["scenario_id"], record["condition"], record["repetition"])
        if key in loaded:
            previous = loaded[key]["source_line"]
            raise RecordError(
                f"duplicate H2 record key {key} (already recorded at line {previous}); "
                "duplicates are errors, not silent overwrites")
        loaded[key] = record
    return loaded


def _rate(numerator: int, denominator: int) -> Optional[float]:
    if denominator == 0:
        return None
    return numerator / denominator


def _condition_descriptives(records: Sequence[Mapping[str, Any]], planned: int) -> Dict[str, Any]:
    delivery_states = {state: 0 for state in H2_DELIVERY_STATES}
    outcome_states = {state: 0 for state in H2_OUTCOME_STATES}
    validation_status_counts: Dict[str, int] = {}
    delivered_violation = 0
    delivered_clean = 0
    delivered_unverifiable = 0
    delivered_unknown = 0
    delivered_partial = 0
    validated_feasible = 0
    known_total = 0
    known_unknown_records = 0
    for record in records:
        delivery = record["delivery"]
        delivery_states[delivery] += 1
        status = record["validation_status"]
        validation_status_counts[status] = validation_status_counts.get(status, 0) + 1
        if delivery == "delivered":
            outcome = record["outcome"]
            outcome_states[outcome] = outcome_states.get(outcome, 0) + 1
            if outcome == "violation":
                delivered_violation += 1
            elif outcome == "clean":
                delivered_clean += 1
            elif outcome == "unverifiable":
                delivered_unverifiable += 1
            elif outcome == "unknown":
                delivered_unknown += 1
            if status == "partial":
                delivered_partial += 1
            if status == "feasible":
                validated_feasible += 1
        if record["known_temporal_violations"] is None:
            known_unknown_records += 1
        else:
            known_total += record["known_temporal_violations"]

    delivered = delivery_states["delivered"]
    delivery_states["missing"] = planned - len(records)
    # A delivered plan has a *determined* outcome only when it is clean or has a
    # known violation. Unverifiable/unknown delivered plans stay outside the
    # numerator and denominator of the determined-subset rate (reported as a
    # coverage fraction instead of being silently treated as clean).
    determined_delivered = delivered_clean + delivered_violation
    determined_coverage = _rate(determined_delivered, delivered)
    return {
        "planned": planned,
        "observed": len(records),
        "missing": planned - len(records),
        "states": delivery_states,
        "outcome_states": outcome_states,
        "validation_status_counts": validation_status_counts,
        "delivered": delivered,
        "delivered_with_verified_violation": delivered_violation,
        "delivered_clean": delivered_clean,
        "delivered_unverifiable": delivered_unverifiable,
        "delivered_unknown": delivered_unknown,
        "delivered_partial": delivered_partial,
        "delivered_determined": determined_delivered,
        "validated_feasible": validated_feasible,
        "known_temporal_violations_total": known_total,
        "known_temporal_violations_unknown_records": known_unknown_records,
        "delivery_rate": _rate(delivered, planned),
        "validated_feasibility_rate": _rate(validated_feasible, planned),
        # Clearly named primary rate: numerator/denominator over the determined
        # delivered subset, with the coverage of that subset over all delivered.
        # An unverifiable-only delivered set reports value=None, never 0.0.
        "determined_violation_rate": {
            "value": _rate(delivered_violation, determined_delivered),
            "numerator": delivered_violation,
            "denominator": determined_delivered,
            "delivered_denominator": delivered,
            "coverage": determined_coverage,
            "label": "verified_violation_rate_among_determined_delivered_plans",
            "note": ("denominator excludes delivered plans whose outcome is not "
                     "determined (unverifiable/unknown); coverage = determined/delivered"),
        },
        # All-delivered variant is a *lower bound*: unknown delivered plans are
        # not clean, so the true rate may be higher; it is never an exact rate.
        "observed_known_violation_lower_bound": {
            "value": _rate(delivered_violation, delivered),
            "numerator": delivered_violation,
            "denominator": delivered,
            "label": "observed_known_violation_lower_bound_among_all_delivered_plans",
            "note": ("lower bound only: undetermined delivered plans are not counted "
                     "as clean"),
        },
        # Legacy key kept for compatibility. Its value already equals the
        # determined-subset rate; the name is ambiguous, so use the named blocks
        # above for any reported metric. Semantics are unchanged, not silently
        # redefined.
        "verified_violation_rate_among_delivered": _rate(delivered_violation,
                                                          determined_delivered),
        "deprecated_metrics": {
            "verified_violation_rate_among_delivered": (
                "ambiguous name; equals determined_violation_rate.value "
                "(determined delivered subset). Prefer determined_violation_rate "
                "or observed_known_violation_lower_bound."),
        },
        "unverifiable_rate": _rate(delivered_unverifiable, planned),
        "refusal_rate": _rate(delivery_states["refused"], planned),
        "failure_rate": _rate(delivery_states["failed"] + delivery_states["error"], planned),
        "empty_rate": _rate(delivery_states["empty"], planned),
    }


def _scenario_condition_outcome(records_by_rep: Sequence[Optional[Mapping[str, Any]]],
                                planned: int) -> Dict[str, Any]:
    delivery_states = {state: 0 for state in H2_DELIVERY_STATES}
    outcome_states = {state: 0 for state in H2_OUTCOME_STATES}
    known_violation = False
    valid_observations = 0
    for repetition in range(planned):
        record = records_by_rep[repetition]
        if record is None:
            delivery_states["missing"] += 1
            continue
        delivery = record["delivery"]
        delivery_states[delivery] += 1
        if delivery != "delivered":
            continue
        outcome = record["outcome"]
        outcome_states[outcome] = outcome_states.get(outcome, 0) + 1
        if outcome == "violation":
            known_violation = True
        if outcome in ("clean", "violation"):
            valid_observations += 1

    coverage_complete = delivery_states["missing"] == 0
    complete_valid = valid_observations == planned
    if known_violation:
        scenario_outcome: Optional[bool] = True
    elif complete_valid:
        scenario_outcome = False
    else:
        scenario_outcome = None
    return {
        "scenario_outcome": scenario_outcome,
        "planned": planned,
        "observed": planned - delivery_states["missing"],
        "missing": delivery_states["missing"],
        "states": delivery_states,
        "outcome_states": outcome_states,
        "valid_observations": valid_observations,
        "coverage_complete": coverage_complete,
        "complete_valid": complete_valid,
    }


def _provenance_key(record: Mapping[str, Any]) -> Optional[Tuple[Optional[str], ...]]:
    provenance = record["provenance"]
    if not provenance:
        return None
    return tuple(provenance.get(field) for field in H2_PROVENANCE_COMMON_FIELDS)


def _scenario_provenance_status(scenario_id: str, conditions: Sequence[str],
                                repetitions: int,
                                loaded: Mapping[Tuple[str, str, int], Mapping[str, Any]]
                                ) -> Dict[str, Any]:
    per_condition: Dict[str, Optional[Tuple[Optional[str], ...]]] = {}
    detail_parts: List[str] = []
    for condition in conditions:
        keys = set()
        had_record = False
        missing = False
        for repetition in range(repetitions):
            record = loaded.get((scenario_id, condition, repetition))
            if record is None:
                continue
            had_record = True
            key = _provenance_key(record)
            if key is None or any(part is None for part in key):
                missing = True
                continue
            keys.add(key)
        if not had_record:
            per_condition[condition] = None
            detail_parts.append(f"{condition}:no_records")
        elif missing and not keys:
            per_condition[condition] = None
            detail_parts.append(f"{condition}:missing_fields")
        elif len(keys) > 1:
            per_condition[condition] = None
            detail_parts.append(f"{condition}:mixed_within_condition")
        elif missing:
            per_condition[condition] = None
            detail_parts.append(f"{condition}:some_records_missing_fields")
        else:
            per_condition[condition] = next(iter(keys))

    values = [per_condition[c] for c in conditions]
    if any(value is None for value in values):
        return {"status": "missing", "detail": "; ".join(detail_parts) or "provenance absent"}
    if values[0] != values[1]:
        return {"status": "incompatible",
                "detail": "; ".join(detail_parts) or "shared identifiers differ across conditions"}
    return {"status": "compatible", "detail": None}


def _usage_totals(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    known = 0
    unknown = 0
    for record in records:
        if record["usage"]["known"]:
            known += 1
        else:
            unknown += 1
    return {"known": known, "unknown": unknown}


def _secondary_metrics(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Optional secondary outcome table. Unknowns and units are preserved.

    Fields are only aggregated when present in the raw records; nothing is
    invented. A field absent from every record is reported as ``available: false``.
    """
    selected_total = 0
    grounded_total = 0
    grounding_records = 0
    budget_groups: Dict[Tuple[str, str], List[float]] = {}
    budget_non_comparable = 0
    route_minutes: List[float] = []
    route_distance: List[float] = []
    latency: List[float] = []
    for record in records:
        selected = record["selected_poi_ids"]
        grounded = record["grounded_source_poi_ids"]
        if selected is not None and grounded is not None:
            grounding_records += 1
            selected_total += len(selected)
            grounded_total += len(set(selected) & set(grounded))
        budget = record["budget_deviation"]
        if budget is not None:
            if budget["comparable"]:
                try:
                    amount = float(budget["amount"])
                except (TypeError, ValueError):
                    budget_non_comparable += 1
                else:
                    budget_groups.setdefault((budget["currency"], budget["unit"]), []).append(amount)
            else:
                budget_non_comparable += 1
        if record["route_travel_minutes"] is not None:
            route_minutes.append(float(record["route_travel_minutes"]))
        if record["route_distance_km"] is not None:
            route_distance.append(float(record["route_distance_km"]))
        if record["latency_seconds"] is not None:
            latency.append(float(record["latency_seconds"]))

    budget_table = {
        "available": bool(budget_groups) or budget_non_comparable > 0,
        "non_comparable_records": budget_non_comparable,
        "groups": [
            {"currency": currency, "unit": unit, "n": len(values),
             "median": _median(values), "mean": sum(values) / len(values),
             "min": min(values), "max": max(values)}
            for (currency, unit), values in sorted(budget_groups.items())
        ],
        "pooled_across_units": False,
    }
    return {
        "poi_grounding": {
            "available": grounding_records > 0,
            "records_with_ids": grounding_records,
            "selected_total": selected_total,
            "grounded_total": grounded_total,
            "grounded_rate": _rate(grounded_total, selected_total),
        },
        "budget_deviation": budget_table,
        "route_travel_minutes": _series(route_minutes, "minutes"),
        "route_distance_km": _series(route_distance, "km"),
        "latency_seconds": _series(latency, "seconds"),
    }


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    if n % 2 == 1:
        return ordered[n // 2]
    return (ordered[n // 2 - 1] + ordered[n // 2]) / 2


def _series(values: Sequence[float], unit: str) -> Dict[str, Any]:
    if not values:
        return {"available": False, "unit": unit, "n": 0, "median": None,
                "mean": None, "min": None, "max": None}
    return {"available": True, "unit": unit, "n": len(values), "median": _median(values),
            "mean": sum(values) / len(values), "min": min(values), "max": max(values)}


def evaluate_h2(manifest: Mapping[str, Any],
                loaded: Mapping[Tuple[str, str, int], Mapping[str, Any]],
                *,
                manifest_sha256: Optional[str] = None,
                records_sha256: Optional[str] = None,
                bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
                bootstrap_draws: int = DEFAULT_BOOTSTRAP_DRAWS) -> Dict[str, Any]:
    conditions = manifest["conditions"]
    condition_a, condition_b = conditions
    repetitions = manifest["repetitions_per_case"]
    scenario_ids = manifest["scenario_ids"]
    planned_per_condition = len(scenario_ids) * repetitions

    all_records = list(loaded.values())
    evidence_levels = sorted({record["evidence_level"] for record in all_records})
    dataset_kinds = sorted({record["dataset_kind"] for record in all_records})

    condition_records: Dict[str, List[Mapping[str, Any]]] = {c: [] for c in conditions}
    for record in all_records:
        condition_records[record["condition"]].append(record)

    descriptives = {
        condition: _condition_descriptives(condition_records[condition], planned_per_condition)
        for condition in conditions
    }

    diagnostics: List[str] = []
    scenario_records: List[Dict[str, Any]] = []
    eligible: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    provenance_incompatible = False
    provenance_missing = False
    incomplete_coverage = False

    for scenario_id in scenario_ids:
        entry: Dict[str, Any] = {"scenario_id": scenario_id, "conditions": {}}
        per_condition: Dict[str, Dict[str, Any]] = {}
        records_by_rep: Dict[str, List[Optional[Mapping[str, Any]]]] = {}
        for condition in conditions:
            reps = [loaded.get((scenario_id, condition, repetition))
                    for repetition in range(repetitions)]
            records_by_rep[condition] = reps
            per_condition[condition] = _scenario_condition_outcome(reps, repetitions)
            entry["conditions"][condition] = per_condition[condition]

        coverage_complete = (per_condition[condition_a]["coverage_complete"]
                             and per_condition[condition_b]["coverage_complete"])
        outcome_none = (per_condition[condition_a]["scenario_outcome"] is None
                        or per_condition[condition_b]["scenario_outcome"] is None)

        # Comparability first: both conditions need complete observation coverage
        # so one observed run is never compared against the planned repetition count.
        if not coverage_complete:
            incomplete_coverage = True
            entry["pair_eligible"] = False
            entry["pair_exclusion_reason"] = "incomplete_coverage"
            excluded.append({"scenario_id": scenario_id, "reason": "incomplete_coverage"})
            scenario_records.append(entry)
            continue

        if outcome_none:
            entry["pair_eligible"] = False
            entry["pair_exclusion_reason"] = "missing_or_unknown_outcome"
            excluded.append({"scenario_id": scenario_id,
                             "reason": "missing_or_unknown_outcome"})
            scenario_records.append(entry)
            continue

        prov_status = _scenario_provenance_status(scenario_id, conditions, repetitions, loaded)
        entry["provenance"] = prov_status
        if prov_status["status"] == "incompatible":
            provenance_incompatible = True
            diagnostics.append(
                f"scenario {scenario_id}: paired conditions carry incompatible provenance "
                f"({prov_status['detail']})")
        elif prov_status["status"] == "missing":
            provenance_missing = True
            diagnostics.append(
                f"scenario {scenario_id}: provenance missing for pairing ({prov_status['detail']})")
        if prov_status["status"] != "compatible":
            reason = f"provenance_{prov_status['status']}"
            entry["pair_eligible"] = False
            entry["pair_exclusion_reason"] = reason
            excluded.append({"scenario_id": scenario_id, "reason": reason})
            scenario_records.append(entry)
            continue

        outcome_a = per_condition[condition_a]["scenario_outcome"]
        outcome_b = per_condition[condition_b]["scenario_outcome"]
        delta = (1.0 if outcome_a else 0.0) - (1.0 if outcome_b else 0.0)
        entry["pair_eligible"] = True
        entry["pair_exclusion_reason"] = None
        entry["pair_effect"] = delta
        eligible.append({"scenario_id": scenario_id, "a": bool(outcome_a), "b": bool(outcome_b),
                         "effect": delta})
        scenario_records.append(entry)

    discordant_a_only = sum(1 for item in eligible if item["a"] and not item["b"])
    discordant_b_only = sum(1 for item in eligible if item["b"] and not item["a"])
    deltas = [item["effect"] for item in eligible]
    a_rate = _rate(sum(1 for item in eligible if item["a"]), len(eligible))
    b_rate = _rate(sum(1 for item in eligible if item["b"]), len(eligible))
    mcnemar = exact_mcnemar_two_sided(discordant_a_only, discordant_b_only)
    bootstrap = paired_effect_bootstrap_ci(deltas, seed=bootstrap_seed, draws=bootstrap_draws)

    blocked_reasons: List[str] = []
    if provenance_incompatible:
        blocked_reasons.append("incompatible_provenance")
    if provenance_missing:
        blocked_reasons.append("missing_provenance")
    if incomplete_coverage:
        blocked_reasons.append("incomplete_coverage")
    if not eligible:
        blocked_reasons.append("no_eligible_pairs")
    if evidence_levels and evidence_levels != ["live_model"]:
        blocked_reasons.append("synthetic_evidence_only")
    if not evidence_levels:
        blocked_reasons.append("no_evidence_records")

    inferential_available = not blocked_reasons and len(eligible) >= 1

    if "synthetic_evidence_only" in blocked_reasons or not all_records:
        conclusion_label = SYNTHETIC_LABEL if all_records else INCONCLUSIVE_LABEL
    elif inferential_available:
        conclusion_label = LIVE_LABEL
    else:
        conclusion_label = INCONCLUSIVE_LABEL

    paired_inference = {
        "declared_binary_outcome": H2_PRIMARY_BINARY_OUTCOME,
        "condition_a": condition_a,
        "condition_b": condition_b,
        "effect_definition": "violation_rate(A) - violation_rate(B) over eligible scenarios",
        "eligible_scenarios": len(eligible),
        "excluded_scenarios": excluded,
        "condition_a_positive_rate": a_rate,
        "condition_b_positive_rate": b_rate,
        "discordant": {
            "a_positive_b_negative": discordant_a_only,
            "b_positive_a_negative": discordant_b_only,
            "total": discordant_a_only + discordant_b_only,
        },
        "mcnemar_exact": mcnemar,
        "paired_effect": {
            "point": (sum(deltas) / len(deltas)) if deltas else None,
            "n": len(deltas),
        },
        "bootstrap": bootstrap,
        "clustered_repetitions_aggregated": True,
        "complete_coverage_required": True,
        "n_scenarios_used_as_independent_units": len(eligible),
        "inferential_available": inferential_available,
        "blocked_reasons": blocked_reasons,
        "gate_policy": ("inference requires live_model evidence, compatible provenance, "
                        "complete comparable coverage and >= 1 eligible pair"),
    }

    return {
        "task": "H2",
        "schema_version": H2_SCHEMA_VERSION,
        "manifest_version": manifest["manifest_version"],
        "manifest_label": manifest["label"],
        "thesis_mode": manifest["thesis_mode"],
        "label": conclusion_label,
        "conclusion_label": conclusion_label,
        "thesis_conclusion": False,
        "data_classification": (
            "synthetic_engineering_fixture" if evidence_levels == ["synthetic_engineering"]
            else ("mixed" if len(evidence_levels) > 1 else "live_evidence")),
        "evidence_levels": evidence_levels,
        "dataset_kinds": dataset_kinds,
        "input": {"manifest_sha256": manifest_sha256, "records_sha256": records_sha256},
        "paired_conditions": list(conditions),
        "repetitions_per_case": repetitions,
        "planned_runs": planned_per_condition * 2,
        "observed_runs": len(all_records),
        "missing_runs": (planned_per_condition * 2) - len(all_records),
        "conditions": descriptives,
        "usage_provenance": _usage_totals(all_records),
        "secondary_outcomes": _secondary_metrics(all_records),
        "scenario_outcomes": scenario_records,
        "paired_inference": paired_inference,
        "diagnostics": diagnostics,
    }
