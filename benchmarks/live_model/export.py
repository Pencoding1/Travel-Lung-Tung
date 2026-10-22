"""Convert collected observations into ``oc18.h2.v1`` records and a manifest.

Honesty rules enforced here:

* Only observations whose **model/session provenance is proven** are admitted as
  live evidence records. An attempt with no observable session id, or whose
  observed model id is absent or does not match the requested model, is retained
  as a raw capture and listed as an explicit **gap**, never as a live record.
* A model output that is malformed is a *failed observed run* with valid
  provenance — it stays in the denominator, never repaired into a clean baseline.
* Usage is never fabricated: the evaluator's fixed four-stage token object cannot
  be filled from an aggregate ``step_finish`` count, so the detailed provider
  usage is preserved under a separate ``provider_usage`` key and ``usage`` is
  omitted (unknown), never zero-filled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .constants import (
    CONDITIONS,
    DATASET_KIND,
    EVIDENCE_LEVEL,
    H2_SCHEMA_VERSION,
    MANIFEST_VERSION,
    RUN_LABEL,
)
from .util import canonical_hash

# Violation codes that represent an observed temporal infeasibility.
TEMPORAL_VIOLATION_CODES = frozenset({
    "travel_infeasible", "opening_violation", "day_bounds", "visit_too_short",
    "return_depot_infeasible", "nonpositive_visit",
})


@dataclass
class Observation:
    scenario_id: str
    condition: str
    repetition: int
    provenance_ok: bool
    rejection_reason: Optional[str]
    output_ok: bool
    invalid_output_reason: Optional[str] = None
    run_status: str = "error"
    exit_code: int = -1
    timed_out: bool = False
    duration_seconds: Optional[float] = None
    session_id: Optional[str] = None
    requested_model_id: str = ""
    observed_model_ids: Sequence[str] = field(default_factory=tuple)
    observed_provider_ids: Sequence[str] = field(default_factory=tuple)
    cli_version: Optional[str] = None
    argv: Sequence[str] = field(default_factory=tuple)
    prompt_sha256: Optional[str] = None
    raw_event_path: Optional[str] = None
    stderr_path: Optional[str] = None
    provider_usage: Optional[Dict[str, Any]] = None
    total_usage: Optional[int] = None
    # Authoritative session-export sidecar (hashed metadata; the raw JSONL is
    # never rewritten). Empty when no export was captured.
    session_export_path: Optional[str] = None
    session_export_sha256: Optional[str] = None
    session_export_source: Optional[str] = None
    session_export_message_id: Optional[str] = None
    provenance_source: Optional[str] = None
    plan: Any = None
    report: Any = None
    selected_poi_ids: Sequence[str] = field(default_factory=tuple)
    candidate_ids: Sequence[str] = field(default_factory=tuple)
    unknown_reasons: Sequence[str] = field(default_factory=tuple)
    budget_deviation: Optional[Dict[str, Any]] = None
    provenance: Dict[str, Optional[str]] = field(default_factory=dict)
    notes: Sequence[str] = field(default_factory=tuple)
    hybrid_mapping: Optional[Dict[str, Any]] = None
    # EXP-074 transport/service evidence. Derived, whitelisted and hashed.
    transport: str = "legacy-v1"
    dataset_kind: str = DATASET_KIND
    dataset_id: Optional[str] = None
    assistant_text_path: Optional[str] = None
    assistant_text_sha256: Optional[str] = None
    provider_receipt_path: Optional[str] = None
    provider_receipt_sha256: Optional[str] = None
    provider_failure: Optional[Dict[str, Any]] = None
    provider_metadata: Optional[Dict[str, Any]] = None
    service_projection: Optional[Dict[str, Any]] = None
    initial_proposal: Optional[Dict[str, Any]] = None
    identity_source: Optional[str] = None


def build_h2_manifest(scenario_ids: Sequence[str], repetitions: int,
                      manifest_version: str = MANIFEST_VERSION,
                      *, dataset_kind: str = DATASET_KIND,
                      dataset_id: Optional[str] = None,
                      label: str = RUN_LABEL,
                      thesis_mode: bool = False) -> Dict[str, Any]:
    return {
        "manifest_version": manifest_version,
        "task": "H2",
        "label": label,
        "dataset_kind": dataset_kind,
        "dataset_id": dataset_id,
        "thesis_mode": bool(thesis_mode),
        "paired_conditions": list(CONDITIONS),
        "repetitions_per_case": repetitions,
        "scenarios": [{"scenario_id": scenario_id} for scenario_id in scenario_ids],
    }


def _temporal_counts(report) -> int:
    if report is None:
        return 0
    return sum(1 for v in report.known_violations if v.code in TEMPORAL_VIOLATION_CODES)


def _outcome_fields(report, plan_present: bool, empty_plan: bool, output_ok: bool):
    unknown = tuple(getattr(report, "unknown_reasons", ()) or ())
    if not output_ok or report is None:
        return {"temporal_violation": None, "known_temporal_violations": None,
                "violation_count_complete": False, "unverifiable": True}
    if report.status == "no_plan":
        return {"temporal_violation": None, "known_temporal_violations": 0,
                "violation_count_complete": False, "unverifiable": True}
    temporal_known = _temporal_counts(report)
    has_unknown = len(unknown) > 0
    if temporal_known > 0:
        return {"temporal_violation": True, "known_temporal_violations": temporal_known,
                "violation_count_complete": not has_unknown, "unverifiable": has_unknown}
    if has_unknown:
        return {"temporal_violation": None, "known_temporal_violations": 0,
                "violation_count_complete": False, "unverifiable": True}
    return {"temporal_violation": False, "known_temporal_violations": 0,
            "violation_count_complete": True, "unverifiable": False}


def build_h2_record(obs: Observation) -> Optional[Dict[str, Any]]:
    """Return an ``oc18.h2.v1`` record, or ``None`` when provenance is unproven."""
    if not obs.provenance_ok:
        return None

    plan_present = obs.plan is not None
    empty_plan = plan_present and len(getattr(obs.plan, "sequence", ()) or ()) == 0

    if not obs.output_ok:
        outcome = {"temporal_violation": None, "known_temporal_violations": None,
                   "violation_count_complete": False, "unverifiable": True}
        validation_status = "failed" if obs.run_status in ("failed", "refused") else "unknown"
        run_status = obs.run_status if obs.run_status in ("failed", "error", "refused") else "error"
    elif not plan_present:
        outcome = {"temporal_violation": None, "known_temporal_violations": None,
                   "violation_count_complete": False, "unverifiable": True}
        validation_status = "unknown"
        run_status = "error"
    else:
        report = obs.report
        outcome = _outcome_fields(report, plan_present, empty_plan, obs.output_ok)
        validation_status = report.status if report is not None else "unknown"
        run_status = "refused" if validation_status == "no_plan" else "completed"

    record: Dict[str, Any] = {
        "schema_version": H2_SCHEMA_VERSION,
        "task": "H2",
        "evidence_level": EVIDENCE_LEVEL,
        "dataset_kind": obs.dataset_kind or DATASET_KIND,
        "dataset_id": obs.dataset_id,
        "transport": obs.transport,
        "scenario_id": obs.scenario_id,
        "condition": obs.condition,
        "repetition": obs.repetition,
        "run_status": run_status,
        "plan_present": bool(plan_present),
        "empty_plan": bool(empty_plan),
        "validation_status": validation_status,
        "unverifiable": outcome["unverifiable"],
        "temporal_violation": outcome["temporal_violation"],
        "known_temporal_violations": outcome["known_temporal_violations"],
        "violation_count_complete": outcome["violation_count_complete"],
        "unknown_reasons": list(obs.unknown_reasons),
        "provenance": dict(obs.provenance),
        "selected_poi_ids": list(obs.selected_poi_ids),
        "grounded_source_poi_ids": list(obs.candidate_ids),
        "latency_seconds": obs.duration_seconds,
        # Preserved separately; never merged into the evaluator's usage object.
        "provider_usage": obs.provider_usage,
        "model_provenance": {
            "requested_model_id": obs.requested_model_id,
            "observed_model_ids": list(obs.observed_model_ids),
            "observed_provider_ids": list(obs.observed_provider_ids),
            "observed_session_id": obs.session_id,
            "cli_version": obs.cli_version,
            "provenance_source": obs.provenance_source,
            "identity_source": obs.identity_source,
            "transport": obs.transport,
            "assistant_text_path": obs.assistant_text_path,
            "assistant_text_sha256": obs.assistant_text_sha256,
            "provider_receipt_path": obs.provider_receipt_path,
            "provider_receipt_sha256": obs.provider_receipt_sha256,
            "provider_failure": obs.provider_failure,
            "session_export_path": obs.session_export_path,
            "session_export_sha256": obs.session_export_sha256,
            "session_export_source": obs.session_export_source,
            "session_export_message_id": obs.session_export_message_id,
        },
    }
    if obs.budget_deviation is not None:
        record["budget_deviation"] = obs.budget_deviation
    if obs.report is not None:
        record["route_travel_minutes"] = obs.report.recomputed_total_travel_minutes
        distance = obs.report.recomputed_total_distance_km
        record["route_distance_km"] = float(distance) if distance is not None else None
    return record


def build_h2_records(observations: Sequence[Observation]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for obs in observations:
        record = build_h2_record(obs)
        if record is not None:
            records.append(record)
    return records


def _temporal_counts_log(report: Optional[Dict[str, Any]]) -> int:
    if not report:
        return 0
    return sum(1 for v in report.get("known_violations", [])
               if isinstance(v, dict) and v.get("code") in TEMPORAL_VIOLATION_CODES)


def _outcome_fields_log(report: Optional[Dict[str, Any]], output_ok: bool):
    unknown = tuple((report or {}).get("unknown_reasons") or ())
    if not output_ok or report is None:
        return {"temporal_violation": None, "known_temporal_violations": None,
                "violation_count_complete": False, "unverifiable": True}
    if report.get("status") == "no_plan":
        return {"temporal_violation": None, "known_temporal_violations": 0,
                "violation_count_complete": False, "unverifiable": True}
    temporal_known = _temporal_counts_log(report)
    has_unknown = len(unknown) > 0
    if temporal_known > 0:
        return {"temporal_violation": True, "known_temporal_violations": temporal_known,
                "violation_count_complete": not has_unknown, "unverifiable": has_unknown}
    if has_unknown:
        return {"temporal_violation": None, "known_temporal_violations": 0,
                "violation_count_complete": False, "unverifiable": True}
    return {"temporal_violation": False, "known_temporal_violations": 0,
            "violation_count_complete": True, "unverifiable": False}


def build_h2_record_from_log(log: Any) -> Optional[Dict[str, Any]]:
    """Rebuild an ``oc18.h2.v1`` record from a persisted ``calls.jsonl`` line.

    Mirrors :func:`build_h2_record` over the serialized observation log so a
    resumed run can regenerate aggregate exports without re-invoking the model.
    """
    if not isinstance(log, dict) or not log.get("provenance_ok"):
        return None

    plan = log.get("plan")
    report = log.get("report")
    plan_present = plan is not None
    empty_plan = plan_present and len((plan or {}).get("sequence") or []) == 0
    output_ok = bool(log.get("output_ok"))
    run_status = log.get("run_status") or "error"

    if not output_ok:
        outcome = {"temporal_violation": None, "known_temporal_violations": None,
                   "violation_count_complete": False, "unverifiable": True}
        validation_status = "failed" if run_status in ("failed", "refused") else "unknown"
        run_status = run_status if run_status in ("failed", "error", "refused") else "error"
    elif not plan_present:
        outcome = {"temporal_violation": None, "known_temporal_violations": None,
                   "violation_count_complete": False, "unverifiable": True}
        validation_status = "unknown"
        run_status = "error"
    else:
        outcome = _outcome_fields_log(report, True)
        validation_status = (report or {}).get("status") or "unknown"
        run_status = "refused" if validation_status == "no_plan" else "completed"

    record: Dict[str, Any] = {
        "schema_version": H2_SCHEMA_VERSION,
        "task": "H2",
        "evidence_level": EVIDENCE_LEVEL,
        "dataset_kind": log.get("dataset_kind") or DATASET_KIND,
        "dataset_id": log.get("dataset_id"),
        "transport": log.get("transport") or "legacy-v1",
        "scenario_id": log.get("scenario_id"),
        "condition": log.get("condition"),
        "repetition": log.get("repetition"),
        "run_status": run_status,
        "plan_present": bool(plan_present),
        "empty_plan": bool(empty_plan),
        "validation_status": validation_status,
        "unverifiable": outcome["unverifiable"],
        "temporal_violation": outcome["temporal_violation"],
        "known_temporal_violations": outcome["known_temporal_violations"],
        "violation_count_complete": outcome["violation_count_complete"],
        "unknown_reasons": list(log.get("unknown_reasons") or []),
        "provenance": dict(log.get("provenance") or {}),
        "selected_poi_ids": list(log.get("selected_poi_ids") or []),
        "grounded_source_poi_ids": list(log.get("candidate_ids") or []),
        "latency_seconds": log.get("duration_seconds"),
        "provider_usage": log.get("provider_usage"),
        "model_provenance": {
            "requested_model_id": log.get("requested_model_id"),
            "observed_model_ids": list(log.get("observed_model_ids") or []),
            "observed_provider_ids": list(log.get("observed_provider_ids") or []),
            "observed_session_id": log.get("session_id"),
            "cli_version": log.get("cli_version"),
            "provenance_source": log.get("provenance_source"),
            "identity_source": log.get("identity_source"),
            "transport": log.get("transport") or "legacy-v1",
            "assistant_text_path": log.get("assistant_text_path"),
            "assistant_text_sha256": log.get("assistant_text_sha256"),
            "provider_receipt_path": log.get("provider_receipt_path"),
            "provider_receipt_sha256": log.get("provider_receipt_sha256"),
            "provider_failure": log.get("provider_failure"),
            "session_export_path": log.get("session_export_path"),
            "session_export_sha256": log.get("session_export_sha256"),
            "session_export_source": log.get("session_export_source"),
            "session_export_message_id": log.get("session_export_message_id"),
        },
    }
    if log.get("budget_deviation") is not None:
        record["budget_deviation"] = log.get("budget_deviation")
    if report is not None:
        record["route_travel_minutes"] = report.get("recomputed_total_travel_minutes")
        distance = report.get("recomputed_total_distance_km")
        record["route_distance_km"] = float(distance) if distance is not None else None
    return record


def build_h2_records_from_logs(logs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for log in logs:
        record = build_h2_record_from_log(log)
        if record is not None:
            records.append(record)
    return records


def export_gaps(observations: Sequence[Observation]) -> List[Dict[str, Any]]:
    gaps: List[Dict[str, Any]] = []
    for obs in observations:
        if obs.provenance_ok:
            continue
        gaps.append({
            "scenario_id": obs.scenario_id,
            "condition": obs.condition,
            "repetition": obs.repetition,
            "reason": obs.rejection_reason or "provenance_unproven",
            "requested_model_id": obs.requested_model_id,
            "observed_model_ids": list(obs.observed_model_ids),
            "observed_session_id": obs.session_id,
            "raw_event_path": obs.raw_event_path,
        })
    return gaps


def export_gaps_from_logs(logs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Same shape as :func:`export_gaps` but over persisted observation logs."""
    gaps: List[Dict[str, Any]] = []
    for log in logs:
        if not isinstance(log, dict) or log.get("provenance_ok"):
            continue
        gaps.append({
            "scenario_id": log.get("scenario_id"),
            "condition": log.get("condition"),
            "repetition": log.get("repetition"),
            "reason": log.get("rejection_reason") or "provenance_unproven",
            "requested_model_id": log.get("requested_model_id"),
            "observed_model_ids": list(log.get("observed_model_ids") or []),
            "observed_session_id": log.get("session_id"),
            "raw_event_path": log.get("raw_event_path"),
        })
    return gaps


def settings_id(requested_model_id: str, agent: str, system_prompt: str) -> str:
    return canonical_hash({
        "model_id": requested_model_id,
        "agent": agent,
        "format": "json",
        "share": "disabled",
        "permission": "*:deny",
        "system_prompt": system_prompt,
        "flags_forbidden": ["--continue", "--session", "--share", "--auto", "--fork"],
    })
