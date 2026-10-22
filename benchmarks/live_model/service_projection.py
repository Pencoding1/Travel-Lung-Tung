"""Pure service-response projection for collector observations.

The projection mirrors the *existing* service contract:

* ``planning.initial_proposal`` is the strictly parsed model proposal;
* ``planning.repaired_schedule`` is the production
  :func:`ai_service.domains.planning_adapter.render_plan` output (``arrival`` /
  ``departure`` — never the historical ``visit_time`` / ``end_time`` aliases);
* ``planning.validation`` is the independent validator summary.

Everything here is derived from an observed completion. It is explicitly
labelled as a service projection, not a raw provider transcript and not an
evaluator result.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AI_ROOT = _REPO_ROOT / "ai_service"
if str(_AI_ROOT) not in sys.path:
    sys.path.insert(0, str(_AI_ROOT))

from domains import planning_adapter  # noqa: E402

PROJECTION_VERSION = "exp074.service-projection.v1"
RESPONSE_PROJECTION_VERSION = "exp074.service-response-projection.v1"
TYPED_SOURCE_LABEL = "derived_typed_planning_projection"
RESPONSE_SOURCE_LABEL = "derived_service_response_projection"
SOURCE_LABEL = TYPED_SOURCE_LABEL


def _candidate_ids(scenario_input: Mapping[str, Any]) -> List[str]:
    pois = scenario_input.get("pois") or []
    ids = sorted(
        str(poi.get("poi_id"))
        for poi in pois
        if isinstance(poi, Mapping) and poi.get("poi_id")
    )
    return ids


def _route_pairs(scenario_input: Mapping[str, Any]) -> set:
    pairs = set()
    for edge in scenario_input.get("route_edges") or []:
        if not isinstance(edge, Mapping):
            continue
        start = edge.get("from_poi_id")
        end = edge.get("to_poi_id")
        if isinstance(start, str) and isinstance(end, str):
            pairs.add((start, end))
    return pairs


def initial_proposal(condition: str, parsed: Any) -> Dict[str, Any]:
    """Strictly parsed model proposal, kept distinct from any repair."""
    if condition == "llm_only":
        days = []
        for day in getattr(parsed, "days", ()):
            days.append({
                "day_id": day.day_id,
                "stops": [
                    {"poi_id": stop.poi_id, "arrival": stop.arrival,
                     "departure": stop.departure}
                    for stop in day.stops
                ],
            })
        return {
            "source": "strictly_parsed_assistant_text",
            "mode": condition,
            "status": getattr(parsed, "status", None),
            "no_plan_reason": getattr(parsed, "no_plan_reason", None),
            "days": days,
        }
    if condition == "hybrid":
        return {
            "source": "strictly_parsed_assistant_text",
            "mode": condition,
            "ordered_poi_ids": list(getattr(parsed, "ordered_poi_ids", ())),
            "day_assignment": dict(getattr(parsed, "day_assignment", {}) or {}),
            "day_assignment_honored": False,
        }
    return {"source": "strictly_parsed_assistant_text", "mode": condition,
            "unknown_condition": True}


def _legs_for_plan(plan: Any, scenario_input: Mapping[str, Any]
                   ) -> List[Tuple[str, str, Optional[str]]]:
    """Directed legs of the delivered schedule, per actual day.

    Depot legs are added only when the scenario declares depots. Flattening
    across days is never used (it would invent a day-N-last -> day-N+1-first
    leg).
    """
    start_depot = scenario_input.get("start_depot_id")
    end_depot = scenario_input.get("end_depot_id")
    legs: List[Tuple[str, str, Optional[str]]] = []
    for day in getattr(plan, "days", ()) or ():
        ids = [stop.poi_id for stop in day.stops]
        if not ids:
            continue
        if start_depot and ids[0] != start_depot:
            legs.append((str(start_depot), ids[0], day.day_id))
        for left, right in zip(ids, ids[1:]):
            legs.append((left, right, day.day_id))
        if end_depot and ids[-1] != end_depot:
            legs.append((ids[-1], str(end_depot), day.day_id))
    return legs


def route_coverage(plan: Any, scenario_input: Mapping[str, Any]) -> Dict[str, Any]:
    """Selected-plan coverage stays separate from candidate-pool coverage."""
    pairs = _route_pairs(scenario_input)
    legs = _legs_for_plan(plan, scenario_input)
    selected_legs = []
    missing = []
    for start, end, day_id in legs:
        ok = (start, end) in pairs
        selected_legs.append({
            "day_id": day_id,
            "from_poi_id": start,
            "to_poi_id": end,
            "route_evidence_present": ok,
        })
        if not ok:
            missing.append({"from_poi_id": start, "to_poi_id": end})
    if not selected_legs:
        selected_status = "not_applicable"
    elif missing:
        selected_status = "partial"
    else:
        selected_status = "complete"

    candidates = _candidate_ids(scenario_input)
    candidate_set = set(candidates)
    total_pairs = len(candidates) * (len(candidates) - 1)
    verified = {(left, right) for (left, right) in pairs
                if left in candidate_set and right in candidate_set and left != right}
    if total_pairs == 0:
        pool_status = "not_applicable"
    elif len(verified) >= total_pairs:
        pool_status = "complete"
    elif verified:
        pool_status = "partial"
    else:
        pool_status = "missing"

    return {
        "scope_note": ("selected-plan coverage is the delivered schedule's own "
                       "directed legs; it never promotes global feasibility"),
        "selected_plan_route": {
            "coverage": selected_status,
            "scope": "selected_plan",
            "legs": selected_legs,
            "missing_legs": missing,
        },
        "candidate_pool_route": {
            "coverage": pool_status,
            "scope": "candidate_pool",
            "verified_pairs": len(verified),
            "total_pairs": total_pairs,
            "candidate_count": len(candidates),
        },
        # No global attestation is available to this collector.
        "global_feasibility": "unverifiable",
    }


def build_projection(*, condition: str, parsed: Any, plan: Any, report: Any,
                     mapping: Optional[Mapping[str, Any]],
                     scenario_input: Mapping[str, Any]) -> Dict[str, Any]:
    """JSON-safe projection preserving initial proposal and repaired plan."""
    repaired = planning_adapter.render_plan(plan) if plan is not None else None
    validation = (planning_adapter.render_validation(report)
                  if report is not None else None)
    totals = None
    if repaired is not None:
        totals = {
            "total_cost_party": repaired.get("total_cost_party"),
            "total_cost_currency": repaired.get("total_cost_currency"),
            "total_travel_minutes": repaired.get("total_travel_minutes"),
            "total_distance_km": repaired.get("total_distance_km"),
            "selected_stop_count": len(repaired.get("sequence") or []),
            "candidate_pool_size": len(_candidate_ids(scenario_input)),
        }
    unknowns = {
        "plan_unknown_reasons": list(getattr(plan, "unknown_reasons", ()) or ()),
        "validation_unknown_reasons": list(getattr(report, "unknown_reasons", ()) or ()),
        "unsatisfied_required": list(getattr(report, "unsatisfied_required", ()) or ()),
        "scenario_declared": list(scenario_input.get("unknowns") or []),
    }
    return {
        "schema_version": PROJECTION_VERSION,
        "source": TYPED_SOURCE_LABEL,
        "derived": True,
        "raw_cli_transcript": False,
        "not_http_response": True,
        "not_evaluator_result": True,
        "mode": condition,
        "declared_source": (
            "model_completion+production_scheduler+independent_validator"
            if condition == "hybrid" else
            "model_completion+collector_plan_builder+independent_validator"),
        "initial_proposal": initial_proposal(condition, parsed),
        "repaired_schedule": repaired,
        "validation": validation,
        "totals": totals,
        "unknowns": unknowns,
        "coverage": route_coverage(plan, scenario_input) if plan is not None else None,
        "selected_poi_ids": list(repaired.get("sequence") or []) if repaired else [],
        "candidate_poi_ids": _candidate_ids(scenario_input),
        "hybrid_mapping": dict(mapping) if isinstance(mapping, Mapping) else None,
    }


# ---------------------------------------------------------------------------
# Actual /generate_itinerary HTTP response projection
#
# The typed builder above accepts scheduler/validator objects. This second,
# independent projection accepts the literal observed response mapping and
# keeps only contract fields. It never retains headers, config, debug, raw error
# bodies or arbitrary subtrees, and it never turns selected-route coverage into
# global feasibility.
# ---------------------------------------------------------------------------
def _safe_str(value: Any) -> Optional[str]:
    return value if isinstance(value, str) else None


def _safe_bool(value: Any) -> Optional[bool]:
    return value if isinstance(value, bool) else None


def _safe_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _safe_decimal(value: Any) -> Any:
    """Preserve decimal strings and finite numbers exactly (no coercion)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return None


def _safe_seconds(value: Any) -> Any:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return None


def _safe_str_list(value: Any) -> List[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, str)]


def _safe_mapping_of_strings(value: Any) -> Dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()
            if isinstance(item, str)}


def _safe_token(value: Any) -> Optional[int]:
    """Token counts are non-negative integers; everything else is unknown."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _safe_usage(value: Any) -> Optional[Dict[str, Any]]:
    """Nullable usage: only non-negative integer token counts survive."""
    if not isinstance(value, Mapping):
        return None
    return {
        "prompt_tokens": _safe_token(value.get("prompt_tokens")),
        "completion_tokens": _safe_token(value.get("completion_tokens")),
        "total_tokens": _safe_token(value.get("total_tokens")),
    }


def _safe_source_scope(value: Any) -> Optional[Dict[str, str]]:
    if not isinstance(value, Mapping):
        return None
    out: Dict[str, str] = {}
    for key in ("dataset_namespace", "input_sha256", "source_area_id"):
        item = value.get(key)
        if not isinstance(item, str):
            return None
        out[key] = item
    return out


def _safe_proposal_stop(stop: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(stop, Mapping):
        return None
    out: Dict[str, Any] = {}
    for key in ("poi_id", "arrival", "departure", "visit_time", "end_time",
                "cost_currency"):
        if key in stop:
            out[key] = _safe_str(stop.get(key))
    poi = stop.get("poi")
    if isinstance(poi, Mapping):
        out["poi"] = {"id": _safe_str(poi.get("id"))}
    for key in ("visit_minutes", "travel_from_prev_minutes"):
        if key in stop:
            out[key] = _safe_int(stop.get(key))
    for key in ("travel_from_prev_distance_km", "cost_party"):
        if key in stop:
            out[key] = _safe_decimal(stop.get(key))
    return out


def _safe_initial_proposal(value: Any) -> Optional[Dict[str, Any]]:
    """Original proposal is preserved, but only as whitelisted literals."""
    if not isinstance(value, Mapping):
        return None
    out: Dict[str, Any] = {}
    for key in ("status", "no_plan_reason"):
        if key in value:
            out[key] = _safe_str(value.get(key))
    for key in ("sequence", "ordered_poi_ids"):
        if key in value:
            out[key] = _safe_str_list(value.get(key))
    if "day_assignment" in value:
        out["day_assignment"] = _safe_mapping_of_strings(value.get("day_assignment"))
    if "days" in value:
        days = []
        for day in value.get("days") or []:
            if not isinstance(day, Mapping):
                continue
            days.append({
                "day_id": _safe_str(day.get("day_id")),
                "stops": [item for item in
                          (_safe_proposal_stop(stop)
                           for stop in (day.get("stops") or []))
                          if item is not None],
            })
        out["days"] = days
    if "stops" in value:
        out["stops"] = [item for item in
                        (_safe_proposal_stop(stop)
                         for stop in (value.get("stops") or []))
                        if item is not None]
    return out


def _safe_repaired_stop(stop: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(stop, Mapping):
        return None
    out: Dict[str, Any] = {}
    for key in ("poi_id", "arrival", "departure", "cost_currency"):
        if key in stop:
            out[key] = _safe_str(stop.get(key))
    for key in ("visit_minutes", "travel_from_prev_minutes"):
        if key in stop:
            out[key] = _safe_int(stop.get(key))
    for key in ("travel_from_prev_distance_km", "cost_party"):
        if key in stop:
            out[key] = _safe_decimal(stop.get(key))
    # visit_time/end_time are never aliases here: only actual arrival/departure.
    return out


def _safe_exclusion(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    return {
        "poi_id": _safe_str(value.get("poi_id")),
        "day_id": _safe_str(value.get("day_id")),
        "reason": _safe_str(value.get("reason")),
    }


def _safe_repaired_schedule(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    out: Dict[str, Any] = {}
    for key in ("scenario_id", "scheduler_status", "no_plan_reason",
                "total_cost_currency"):
        if key in value:
            out[key] = _safe_str(value.get(key))
    for key in ("sequence", "unsatisfied_required", "unknown_reasons", "notes"):
        if key in value:
            out[key] = _safe_str_list(value.get(key))
    if "days" in value:
        days = []
        for day in value.get("days") or []:
            if not isinstance(day, Mapping):
                continue
            days.append({
                "day_id": _safe_str(day.get("day_id")),
                "stops": [item for item in
                          (_safe_repaired_stop(stop)
                           for stop in (day.get("stops") or []))
                          if item is not None],
            })
        out["days"] = days
    for key in ("total_cost_party", "total_distance_km"):
        if key in value:
            out[key] = _safe_decimal(value.get(key))
    if "total_travel_minutes" in value:
        out["total_travel_minutes"] = _safe_int(value.get("total_travel_minutes"))
    if "iterations" in value:
        out["iterations"] = _safe_int(value.get("iterations"))
    if "excluded" in value:
        out["excluded"] = [item for item in
                           (_safe_exclusion(entry)
                            for entry in (value.get("excluded") or []))
                           if item is not None]
    return out


def _safe_violation(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    return {
        "code": _safe_str(value.get("code")),
        "day_id": _safe_str(value.get("day_id")),
        "poi_id": _safe_str(value.get("poi_id")),
        "detail": _safe_str(value.get("detail")),
    }


def _safe_validation(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    out: Dict[str, Any] = {}
    for key in ("status", "no_plan_reason"):
        if key in value:
            out[key] = _safe_str(value.get(key))
    if "known_violations" in value:
        out["known_violations"] = [item for item in
                                   (_safe_violation(entry)
                                    for entry in (value.get("known_violations") or []))
                                   if item is not None]
    for key in ("unknown_reasons", "unsatisfied_required"):
        if key in value:
            out[key] = _safe_str_list(value.get(key))
    for key in ("recomputed_total_cost_party", "recomputed_total_distance_km"):
        if key in value:
            out[key] = _safe_decimal(value.get(key))
    for key in ("recomputed_total_travel_minutes", "stop_count"):
        if key in value:
            out[key] = _safe_int(value.get(key))
    checks = value.get("checks")
    if isinstance(checks, Mapping):
        out["checks"] = {str(key): _safe_int(item)
                         for key, item in checks.items()
                         if _safe_int(item) is not None}
    return out


def _safe_route_leg(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    return {
        "day_id": _safe_str(value.get("day_id")),
        "from_poi_id": _safe_str(value.get("from_poi_id")),
        "to_poi_id": _safe_str(value.get("to_poi_id")),
        "route_evidence_present": _safe_bool(value.get("route_evidence_present")),
    }


def _safe_selected_plan_route(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    out: Dict[str, Any] = {}
    for key in ("coverage", "scope"):
        if key in value:
            out[key] = _safe_str(value.get(key))
    if "verified" in value:
        out["verified"] = _safe_bool(value.get("verified"))
    if "legs" in value:
        out["legs"] = [item for item in
                       (_safe_route_leg(leg) for leg in (value.get("legs") or []))
                       if item is not None]
    if "missing_legs" in value:
        out["missing_legs"] = [{"from_poi_id": _safe_str(leg.get("from_poi_id")),
                                "to_poi_id": _safe_str(leg.get("to_poi_id"))}
                               for leg in (value.get("missing_legs") or [])
                               if isinstance(leg, Mapping)]
    return out


def _safe_route_evidence(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    out: Dict[str, Any] = {}
    for key in ("coverage", "coverage_scope", "transport_mode"):
        if key in value:
            out[key] = _safe_str(value.get(key))
    for key in ("attempted", "succeeded", "verified_pairs", "total_pairs",
                "candidate_count"):
        if key in value:
            out[key] = _safe_int(value.get(key))
    return out


def _safe_cost(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    return {
        "status": _safe_str(value.get("status")),
        "known_party_subtotal": _safe_decimal(value.get("known_party_subtotal")),
        "currency": _safe_str(value.get("currency")),
    }


def _safe_totals(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    out: Dict[str, Any] = {}
    for key in ("travel_minutes", "stop_count"):
        if key in value:
            out[key] = _safe_int(value.get(key))
    if "distance_km" in value:
        out["distance_km"] = _safe_decimal(value.get("distance_km"))
    return out


def _safe_request_constraints(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    out: Dict[str, Any] = {}
    for key in ("transport_mode", "transport_mode_source", "source_mode",
                "scope_mode"):
        if key in value:
            out[key] = _safe_str(value.get(key))
    scope = _safe_source_scope(value.get("source_scope"))
    if scope is not None:
        out["source_scope"] = scope
    return out


def _project_planning(value: Any) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    if not isinstance(value, Mapping):
        return None, ["planning"]
    missing: List[str] = []
    repaired = _safe_repaired_schedule(value.get("repaired_schedule"))
    if repaired is None:
        missing.append("planning.repaired_schedule")
    projected = {
        "initial_proposal": _safe_initial_proposal(value.get("initial_proposal")),
        "repaired_schedule": repaired,
        "validator_status": _safe_str(value.get("validator_status")),
        "verified": _safe_bool(value.get("verified")),
        "facts_fully_known": _safe_bool(value.get("facts_fully_known")),
        "validation": _safe_validation(value.get("validation")),
        "selected_plan_route": _safe_selected_plan_route(
            value.get("selected_plan_route")),
        "route_evidence": _safe_route_evidence(value.get("route_evidence")),
        "cost": _safe_cost(value.get("cost")),
        "totals": _safe_totals(value.get("totals")),
        "model_usage": _safe_usage(value.get("model_usage")),
        "request_constraints": _safe_request_constraints(
            value.get("request_constraints")),
    }
    return projected, missing


def project_service_response(payload: Any, *, http_status: int,
                             elapsed_seconds: Any) -> Dict[str, Any]:
    """Project an observed ``/generate_itinerary`` response, closed and pure.

    The producer is the actual HTTP response mapping; this function performs no
    call itself. Unknown keys, headers, config, model reasoning, raw error bodies
    and debug subtrees are never copied. Selected-plan route coverage is kept
    separate from candidate-pool evidence, and global feasibility is never
    promoted to verified.
    """
    status = _safe_int(http_status)
    http_ok = None if status is None else 200 <= status < 300
    base: Dict[str, Any] = {
        "schema_version": RESPONSE_PROJECTION_VERSION,
        "source": RESPONSE_SOURCE_LABEL,
        "derived": True,
        "raw_cli_transcript": False,
        "raw_http_response_retained": False,
        "not_evaluator_result": True,
        "http_status": status,
        "http_ok": http_ok,
        "elapsed_seconds": _safe_seconds(elapsed_seconds),
        "global_feasibility": "unverifiable",
    }

    if payload is None:
        base.update({
            "response_status": "missing_response",
            "error": {"code": "missing_response"},
            "model": None,
            "usage": None,
            "provider": None,
            "planning": None,
            "projection_complete": False,
            "missing_fields": ["payload"],
        })
        return base
    if not isinstance(payload, Mapping):
        base.update({
            "response_status": "invalid_response",
            "error": {"code": "invalid_response"},
            "model": None,
            "usage": None,
            "provider": None,
            "planning": None,
            "projection_complete": False,
            "missing_fields": ["payload"],
        })
        return base

    response_status = _safe_str(payload.get("status")) or "unknown"
    error_code = None
    error = payload.get("error")
    if isinstance(error, Mapping):
        error_code = _safe_str(error.get("code"))
    planning, missing = _project_planning(payload.get("planning"))

    provider_value = payload.get("provider")
    provider = None
    if isinstance(provider_value, Mapping):
        provider = {
            "selected": _safe_str(provider_value.get("selected")),
            "observed_model": _safe_str(provider_value.get("observed_model")),
        }

    complete = (planning is not None and not missing and error_code is None
                and response_status != "error" and http_ok is not False)
    base.update({
        "response_status": response_status,
        "error": {"code": error_code} if error_code is not None else None,
        "model": _safe_str(payload.get("model")),
        "usage": _safe_usage(payload.get("usage")),
        "provider": provider,
        "planning": planning,
        "projection_complete": complete,
        "missing_fields": missing,
    })
    return base
