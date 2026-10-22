"""EXP-077 timing-only companion endpoint for H2 observations.

This module is a *pure projection* over an already-derived global ``oc18.h2.v1``
record and its stored collector log.  It never schedules, validates, repairs or
scores a plan, and it never invokes a provider.  The original conservative H2
exporter and its records are left byte-for-byte untouched.

The companion answers one narrow question: *given the validator report already
stored in the log, is the absence of a temporal violation independently certain?*
Only exact ``cost_unknown:<known-poi-id>`` reasons may be excluded from temporal
uncertainty.  Every other unknown reason, new code, malformed value and
structural/unknown violation fails closed.  Global validity is never promoted:
the original validation status, unverifiable flag and unknown reasons are carried
under explicit ``global_*`` fields.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence

from . import export

TEMPORAL_ENDPOINT = "temporal_only"
TEMPORAL_ENDPOINT_METHOD_VERSION = "exp077.temporal.v1"
TEMPORAL_ENDPOINT_LABEL = "TIMING-ONLY endpoint; not global validity"

# Closed list of violation codes that are independently non-temporal.  They may
# coexist with a temporally complete record, but they still keep the global
# record invalid and are reported as separate dimensions.
NON_TEMPORAL_VIOLATION_CODES = frozenset({
    "duplicate_poi",
    "max_stops_exceeded",
    "currency_mismatch",
    "unit_mismatch",
    "budget_exceeded",
})

_TEMPORAL_CODES = frozenset(export.TEMPORAL_VIOLATION_CODES)
_USABLE_REPORT_STATUSES = frozenset({"feasible", "partial", "unverifiable"})
_VALIDATION_STATUSES = frozenset({
    "feasible", "partial", "unverifiable", "no_plan", "failed", "unknown",
})

_PROVENANCE_FIELDS = (
    "candidate_id",
    "route_id",
    "prompt_information_id",
    "dataset_id",
    "model_id",
    "settings_id",
    "method_instruction_hash",
)
_MODEL_PROVENANCE_FIELDS = (
    "requested_model_id",
    "observed_model_ids",
    "observed_provider_ids",
    "observed_session_id",
    "cli_version",
    "provenance_source",
    "identity_source",
    "transport",
    "assistant_text_path",
    "assistant_text_sha256",
    "provider_receipt_path",
    "provider_receipt_sha256",
    "session_export_path",
    "session_export_sha256",
    "session_export_source",
    "session_export_message_id",
)
_USAGE_COMPONENT_NAMES = ("input", "output", "reasoning", "cache_read",
                          "cache_write", "total")
_USAGE_INT_FIELDS = (
    "input_tokens", "output_tokens", "reasoning_tokens", "cache_read_tokens",
    "cache_write_tokens", "total_tokens", "step_finish_count",
    "token_block_count", "prompt_tokens", "completion_tokens",
)
_USAGE_BOOL_FIELDS = ("complete", "partial", "usage_consistent")


def _nonblank_str(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _nonneg_int_or_none(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _int_or_none(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _bool_or_none(value: Any) -> Optional[bool]:
    return value if isinstance(value, bool) else None


def _number_or_none(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _safe_text(value: Any) -> Optional[str]:
    return value if isinstance(value, str) else None


def _closed_usage(value: Any) -> Optional[Dict[str, Any]]:
    """Whitelisted usage scalars only; nested unknown config is dropped.

    Known nullable counters stay present as ``None`` instead of being replaced
    with a fabricated zero, and a sentinel under ``private_config`` or any other
    unknown key never survives.
    """
    if value is None:
        return None
    if not isinstance(value, Mapping):
        return None
    result: Dict[str, Any] = {}
    for key in _USAGE_INT_FIELDS:
        if key in value:
            result[key] = _nonneg_int_or_none(value.get(key))
    if "provider_components" in value:
        components = value.get("provider_components")
        if isinstance(components, Mapping):
            result["provider_components"] = {
                name: _nonneg_int_or_none(components.get(name))
                for name in _USAGE_COMPONENT_NAMES if name in components
            }
        else:
            result["provider_components"] = {}
    for key in _USAGE_BOOL_FIELDS:
        if key in value:
            result[key] = _bool_or_none(value.get(key))
    if "coverage" in value:
        result["coverage"] = _safe_text(value.get("coverage"))
    if "lower_bounds" in value:
        lower = value.get("lower_bounds")
        if isinstance(lower, Mapping):
            result["lower_bounds"] = {
                name: count for name in _USAGE_COMPONENT_NAMES
                if name in lower
                for count in (_nonneg_int_or_none(lower.get(name)),)
                if count is not None
            }
        else:
            result["lower_bounds"] = {}
    if "invalid_fields" in value:
        invalid = value.get("invalid_fields")
        result["invalid_fields"] = (
            [item for item in invalid if isinstance(item, str)]
            if isinstance(invalid, (list, tuple)) else [])
    return result


def _strict_str_sequence(value: Any) -> Optional[List[str]]:
    """Return a list of nonblank strings, or ``None`` for malformed input."""
    if not isinstance(value, (list, tuple)):
        return None
    result: List[str] = []
    for item in value:
        text = _nonblank_str(item)
        if text is None:
            return None
        result.append(text)
    return result


def _optional_str_sequence(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    return _strict_str_sequence(value)


def _text_or_none(value: Any) -> Optional[str]:
    return value if isinstance(value, str) else None


def _closed_provenance(value: Any) -> Optional[Dict[str, Optional[str]]]:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        return None
    result: Dict[str, Optional[str]] = {}
    for key in _PROVENANCE_FIELDS:
        item = value.get(key)
        result[key] = item if isinstance(item, str) else None
    return result


def _closed_budget(value: Any) -> Optional[Dict[str, Any]]:
    if value is None or not isinstance(value, Mapping):
        return None
    amount = value.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, (int, float, str)):
        return None
    currency = _nonblank_str(value.get("currency"))
    unit = _nonblank_str(value.get("unit"))
    comparable = value.get("comparable")
    if currency is None or unit is None or not isinstance(comparable, bool):
        return None
    return {"amount": amount, "currency": currency, "unit": unit,
            "comparable": comparable}


def _closed_provider_failure(value: Any) -> Optional[Dict[str, Any]]:
    if value is None or not isinstance(value, Mapping):
        return None
    result: Dict[str, Any] = {}
    if "code" in value:
        result["code"] = _safe_text(value.get("code"))
    for key in ("attempts", "failed_attempts"):
        if key in value:
            result[key] = _nonneg_int_or_none(value.get(key))
    if "retryable" in value:
        result["retryable"] = _bool_or_none(value.get("retryable"))
    return result


def _closed_model_provenance(value: Any) -> Optional[Dict[str, Any]]:
    if value is None or not isinstance(value, Mapping):
        return None
    result: Dict[str, Any] = {}
    for key in _MODEL_PROVENANCE_FIELDS:
        item = value.get(key)
        if key in ("observed_model_ids", "observed_provider_ids"):
            result[key] = (
                [entry for entry in item if isinstance(entry, str)]
                if isinstance(item, (list, tuple)) else [])
        else:
            result[key] = _safe_text(item)
    result["provider_failure"] = _closed_provider_failure(
        value.get("provider_failure"))
    return result


def _known_poi_ids(log: Mapping[str, Any], global_record: Mapping[str, Any]) -> frozenset:
    """Known selected/source POI ids used only to validate cost-unknown reasons."""
    ids = set()
    for source in (global_record, log):
        for key in ("selected_poi_ids", "grounded_source_poi_ids", "candidate_ids"):
            value = source.get(key)
            if not isinstance(value, (list, tuple)):
                continue
            for item in value:
                text = _nonblank_str(item)
                if text is not None:
                    ids.add(text)
    return frozenset(ids)


def _is_excludable_cost_reason(reason: str, known_ids: frozenset) -> bool:
    """Only the exact ``cost_unknown:<known-poi-id>`` form is cost-only."""
    prefix = "cost_unknown:"
    if not reason.startswith(prefix):
        return False
    poi_id = reason[len(prefix):]
    # The suffix must be exactly a known selected/source POI id.  Source ids
    # themselves contain ':' (``hcm_primary_geojson_internal:...``), so no
    # substring/colon heuristic is used: an exact known-id match or fail closed.
    return bool(poi_id) and poi_id == poi_id.strip() and poi_id in known_ids


def _report_view(report: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(report, Mapping):
        return None
    status = _nonblank_str(report.get("status"))
    if status is None or status not in (_USABLE_REPORT_STATUSES | {"no_plan", "failed", "unknown"}):
        return None

    raw_violations = report.get("known_violations")
    if not isinstance(raw_violations, (list, tuple)):
        return None
    violations: List[Dict[str, Any]] = []
    for raw in raw_violations:
        if not isinstance(raw, Mapping):
            return None
        code = _nonblank_str(raw.get("code"))
        if code is None:
            return None
        violations.append({
            "code": code,
            "day_id": _text_or_none(raw.get("day_id")),
            "poi_id": _text_or_none(raw.get("poi_id")),
        })

    unknown_reasons = _strict_str_sequence(report.get("unknown_reasons"))
    if unknown_reasons is None:
        return None
    unsatisfied = _strict_str_sequence(report.get("unsatisfied_required", []))
    if unsatisfied is None:
        return None
    return {
        "status": status,
        "violations": violations,
        "unknown_reasons": unknown_reasons,
        "unsatisfied_required": unsatisfied,
    }


def _plan_view(plan: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(plan, Mapping):
        return None
    status = plan.get("status")
    if status is not None and _nonblank_str(status) is None:
        return None
    sequence = _strict_str_sequence(plan.get("sequence"))
    if sequence is None:
        return None
    return {"status": _nonblank_str(status), "sequence": sequence,
            "empty": len(sequence) == 0}


def _unknown_outcome(known: Optional[int],
                     non_temporal: Optional[List[Dict[str, Any]]] = None,
                     unsatisfied: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "temporal_violation": None,
        "known_temporal_violations": known,
        "violation_count_complete": False,
        "unverifiable": True,
        "non_temporal_violations": list(non_temporal or []),
        "request_unsatisfied_required": list(unsatisfied or []),
    }


def _temporal_outcome(log: Mapping[str, Any],
                      global_record: Mapping[str, Any]) -> Dict[str, Any]:
    """Recompute only the four temporal fields from the stored validator report.

    Exact boolean ``True`` is required for ``output_ok``; a truthy string cannot
    establish a clean timing absence.  Known temporal violations are still kept
    even when delivery/other evidence is incomplete.
    """
    report_view = _report_view(log.get("report"))
    temporal_count = 0
    non_temporal: List[Dict[str, Any]] = []
    unsatisfied: List[str] = []
    structural_uncertainty = report_view is None
    temporal_unknown = False

    if report_view is not None:
        unsatisfied = list(report_view["unsatisfied_required"])
        for violation in report_view["violations"]:
            code = violation["code"]
            if code in _TEMPORAL_CODES:
                temporal_count += 1
            elif code in NON_TEMPORAL_VIOLATION_CODES:
                non_temporal.append(dict(violation))
            else:
                # Unknown/new/structural violation: absence of a temporal
                # violation cannot be established.
                structural_uncertainty = True

        known_ids = _known_poi_ids(log, global_record)
        temporal_unknown = any(
            not _is_excludable_cost_reason(reason, known_ids)
            for reason in report_view["unknown_reasons"]
        )

        status = report_view["status"]
        if status == "feasible":
            structurally_consistent = (
                not report_view["violations"]
                and not report_view["unknown_reasons"]
                and not report_view["unsatisfied_required"]
            )
        elif status == "partial":
            structurally_consistent = bool(
                report_view["violations"] or report_view["unsatisfied_required"]
            )
        elif status == "unverifiable":
            structurally_consistent = bool(report_view["unknown_reasons"])
        else:  # no_plan / failed / unknown are never clean evidence
            structurally_consistent = False
        if not structurally_consistent:
            structural_uncertainty = True

    output_ok = log.get("output_ok") is True
    plan_view = _plan_view(log.get("plan"))
    delivered = (
        output_ok
        and plan_view is not None
        and plan_view["status"] != "no_plan"
        and not plan_view["empty"]
    )
    report_usable = (
        report_view is not None
        and report_view["status"] in _USABLE_REPORT_STATUSES
    )

    if not delivered:
        incomplete = True
        unknown_known = (
            0 if plan_view is not None
            and (plan_view["status"] == "no_plan" or plan_view["empty"])
            else None
        )
    elif not report_usable:
        incomplete = True
        unknown_known = None
    else:
        incomplete = structural_uncertainty or temporal_unknown
        unknown_known = 0

    if temporal_count > 0:
        # Known bad timing evidence is never discarded, even when other facts
        # are unknown.  Completeness stays false in that case.
        return {
            "temporal_violation": True,
            "known_temporal_violations": temporal_count,
            "violation_count_complete": not incomplete,
            "unverifiable": incomplete,
            "non_temporal_violations": non_temporal,
            "request_unsatisfied_required": unsatisfied,
        }
    if incomplete:
        return _unknown_outcome(unknown_known, non_temporal, unsatisfied)
    return {
        "temporal_violation": False,
        "known_temporal_violations": 0,
        "violation_count_complete": True,
        "unverifiable": False,
        "non_temporal_violations": non_temporal,
        "request_unsatisfied_required": unsatisfied,
    }


def build_temporal_h2_record(log: Any,
                             global_record: Any) -> Optional[Dict[str, Any]]:
    """Project one stored collector log into a timing-only H2 record.

    Returns ``None`` when the global record is absent/unusable (for example
    unproven provenance).  The inputs are never mutated.  Unknown global
    subtrees, headers, config, error bodies and reasoning are not copied.
    """
    if not isinstance(log, Mapping) or not isinstance(global_record, Mapping):
        return None
    # Exact boolean identity: a truthy string such as "false" must never be
    # admitted as proven provenance or as complete timing evidence.
    if log.get("provenance_ok") is not True:
        return None
    validation_status = _nonblank_str(global_record.get("validation_status"))
    if validation_status is None or validation_status not in _VALIDATION_STATUSES:
        return None

    # Closed identity/scalar fields only.  A nested object in any scalar slot is
    # nulled (or the record is refused below), never passed through wholesale.
    schema_version = _nonblank_str(global_record.get("schema_version"))
    task = _nonblank_str(global_record.get("task"))
    evidence_level = _nonblank_str(global_record.get("evidence_level"))
    dataset_kind = _nonblank_str(global_record.get("dataset_kind"))
    run_status = _nonblank_str(global_record.get("run_status"))
    transport = _nonblank_str(global_record.get("transport"))
    scenario_id = _nonblank_str(global_record.get("scenario_id"))
    condition = _nonblank_str(global_record.get("condition"))
    repetition = _int_or_none(global_record.get("repetition"))
    if None in (schema_version, task, evidence_level, dataset_kind, run_status,
                transport, scenario_id, condition, repetition):
        return None

    outcome = _temporal_outcome(log, global_record)
    global_unknowns = _strict_str_sequence(global_record.get("unknown_reasons", []))
    if global_unknowns is None:
        # A malformed global field must fail closed rather than be guessed.
        return None

    non_temporal = outcome["non_temporal_violations"]
    unsatisfied = outcome["request_unsatisfied_required"]
    request_compliant = (
        validation_status == "feasible"
        and not non_temporal
        and not unsatisfied
    )

    record: Dict[str, Any] = {
        "schema_version": schema_version,
        "task": task,
        "evidence_level": evidence_level,
        "dataset_kind": dataset_kind,
        "dataset_id": _safe_text(global_record.get("dataset_id")),
        "transport": transport,
        "scenario_id": scenario_id,
        "condition": condition,
        "repetition": repetition,
        "run_status": run_status,
        "plan_present": global_record.get("plan_present") is True,
        "empty_plan": global_record.get("empty_plan") is True,
        # Original global status is carried unchanged for the evaluator and for
        # provenance; it is never replaced by the temporal verdict.
        "validation_status": validation_status,
        "unknown_reasons": list(global_unknowns),
        "provenance": _closed_provenance(global_record.get("provenance")),
        "selected_poi_ids": _optional_str_sequence(
            global_record.get("selected_poi_ids")) or [],
        "grounded_source_poi_ids": _optional_str_sequence(
            global_record.get("grounded_source_poi_ids")) or [],
        "latency_seconds": _number_or_none(global_record.get("latency_seconds")),
        "provider_usage": _closed_usage(global_record.get("provider_usage")),
        "model_provenance": _closed_model_provenance(
            global_record.get("model_provenance")),
        "route_travel_minutes": _nonneg_int_or_none(
            global_record.get("route_travel_minutes")),
        "route_distance_km": _number_or_none(
            global_record.get("route_distance_km")),
        "endpoint": TEMPORAL_ENDPOINT,
        "endpoint_method_version": TEMPORAL_ENDPOINT_METHOD_VERSION,
        "endpoint_label": TEMPORAL_ENDPOINT_LABEL,
        "unverifiable_scope": "temporal_only",
        "global_unverifiable": global_record.get("unverifiable") is True,
        "global_validation_status": validation_status,
        "global_unknown_reasons": list(global_unknowns),
        "temporal_violation": outcome["temporal_violation"],
        "known_temporal_violations": outcome["known_temporal_violations"],
        "violation_count_complete": outcome["violation_count_complete"],
        "unverifiable": outcome["unverifiable"],
        "non_temporal_known_violations": non_temporal,
        "non_temporal_violation_count": len(non_temporal),
        "request_unsatisfied_required": unsatisfied,
        "request_compliant": request_compliant,
        "whole_plan_compliance_claimed": False,
        "global_validity_assessed": False,
    }
    budget = _closed_budget(global_record.get("budget_deviation"))
    if budget is not None:
        record["budget_deviation"] = budget
    return record


def build_temporal_h2_records_from_logs(
        logs: Sequence[Any]) -> List[Dict[str, Any]]:
    """Build the companion records from stored logs without re-running anything."""
    records: List[Dict[str, Any]] = []
    for log in logs:
        global_record = export.build_h2_record_from_log(log)
        if global_record is None:
            continue
        record = build_temporal_h2_record(log, global_record)
        if record is not None:
            records.append(record)
    return records


def build_temporal_h2_manifest(global_manifest: Any) -> Dict[str, Any]:
    """Scope the unchanged H2 manifest to the timing-only endpoint."""
    if not isinstance(global_manifest, Mapping):
        raise ValueError("global manifest must be an object")
    if _nonblank_str(global_manifest.get("task")) != "H2":
        raise ValueError("global manifest task must be 'H2'")
    manifest_version = _nonblank_str(global_manifest.get("manifest_version"))
    if manifest_version is None:
        raise ValueError("global manifest_version is required")
    label = _nonblank_str(global_manifest.get("label")) or "H2"
    dataset_kind = _nonblank_str(global_manifest.get("dataset_kind"))
    if dataset_kind is None:
        raise ValueError("global dataset_kind is required")

    conditions = _strict_str_sequence(global_manifest.get("paired_conditions"))
    if conditions is None or len(conditions) != 2 or conditions[0] == conditions[1]:
        raise ValueError("global paired_conditions must be two distinct strings")
    repetitions = global_manifest.get("repetitions_per_case")
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("global repetitions_per_case must be a positive integer")
    raw_scenarios = global_manifest.get("scenarios")
    if not isinstance(raw_scenarios, (list, tuple)) or not raw_scenarios:
        raise ValueError("global scenarios must be a non-empty list")
    scenario_ids: List[str] = []
    for entry in raw_scenarios:
        if not isinstance(entry, Mapping):
            raise ValueError("global scenario entries must be objects")
        scenario_id = _nonblank_str(entry.get("scenario_id"))
        if scenario_id is None:
            raise ValueError("global scenario_id is required")
        scenario_ids.append(scenario_id)
    if len(set(scenario_ids)) != len(scenario_ids):
        raise ValueError("global scenario_ids must be unique")

    return {
        "manifest_version": manifest_version,
        "task": "H2",
        "label": f"{label} [temporal_only]",
        "dataset_kind": dataset_kind,
        "dataset_id": global_manifest.get("dataset_id"),
        "thesis_mode": bool(global_manifest.get("thesis_mode")),
        "paired_conditions": conditions,
        "repetitions_per_case": repetitions,
        "scenarios": [{"scenario_id": scenario_id} for scenario_id in scenario_ids],
        "endpoint": TEMPORAL_ENDPOINT,
        "endpoint_method_version": TEMPORAL_ENDPOINT_METHOD_VERSION,
        "endpoint_label": TEMPORAL_ENDPOINT_LABEL,
        "global_manifest_version": manifest_version,
        "global_label": label,
        "denominator_policy": "same_planned_cases; failures_and_missing_retained",
        "inference": "none_in_coding_task",
        "global_validity_assessed": False,
    }
