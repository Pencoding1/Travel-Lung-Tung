"""SYS098 bounded system/adversarial HTTP collector (OFFLINE, dry-run default).

The collector plans exactly nine fixed cases over one future local controlled
HTTP fault-injection study plus a natural native control.  It never starts a
service, opens a socket, resolves a credential or calls a provider unless the
operator explicitly passes ``--execute`` *and* a parent-approved frozen manifest
binds the current source/helper/provider/runtime and dataset hashes.

Injected responses are synthetic, controlled evidence.  They are not graph
facts, not natural graph-error frequency, not hallucination-rate/H1 evidence and
not proof of administrative truth.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple
import urllib.error
import urllib.request

try:  # accepted, reviewed closed-error utilities (read-only reuse)
    from benchmarks.memory_live.runner import (  # noqa: PLC0415
        BoundedError, NativeBackend, HTTP_TIMEOUT_SECONDS,
        _FATAL_PROVIDER_CODES, _closed_error_code, _provider_receipts,
    )
except ImportError:  # benchmark-local import
    from memory_live.runner import (  # type: ignore  # noqa: PLC0415
        BoundedError, NativeBackend, HTTP_TIMEOUT_SECONDS,
        _FATAL_PROVIDER_CODES, _closed_error_code, _provider_receipts,
    )

try:  # shared pure address helper; imports no application module
    from benchmarks.system_adversarial.qa_runtime import (  # noqa: PLC0415
        compare_source_address,
    )
except ImportError:  # benchmark-local import
    from qa_runtime import compare_source_address  # type: ignore  # noqa: PLC0415

ROOT = Path(__file__).resolve().parents[2]
AI_SERVICE_ROOT = ROOT / "ai_service"
HELPER_PATH = ROOT / "scripts/native_runtime/core_service.py"
DATASET_PATH = ROOT / "data/primary_20261016/graph_ready_v2/prepared_pois.jsonl"
DEFAULT_MANIFEST = ROOT / "docs/project/handoffs/SYS-098/executor/frozen-manifest.json"

TASK = "SYS098"
SCHEMA = "sys098.system_adversarial.v1"
CASE_HEADER = "X-TVLT-QA-Case"
ENDPOINT = "/generate_itinerary"
MCP_PORT = 19601
AI_PORT = 19602
FORBIDDEN_PORTS = frozenset({19101, 19102})
MODEL = "opencode-go/deepseek-v4.1-flash"
MAX_HTTP_REQUESTS = 9
MAX_GENERATIVE_REQUESTS = 3
MAX_CLI_ATTEMPTS = 15

SOURCE = {
    "dataset_namespace": "hcm_primary_geojson",
    "input_sha256": "713b07a62cf89bd2cad9093abaad2a4c5f01e23853321764b3d66bf9f7eee43c",
    "source_area_id": (
        "source_area_v1:e9eb7238f81d8d56f2d5931f86e38d6b3b318147426191bd2c57d131e1500e1d"
    ),
}
DATASET_SHA256 = "37340a8021ca7e8b37efc1053718c4c87879f95fa9937d8c53e1a0218f080dd1"

CASE_ORDER = (
    "A_empty",
    "A_enrichment_failed",
    "C_no_match_native",
    "C_ambiguous",
    "C_wrong_parent",
    "C_partial_collision",
    "B_unknown_id",
    "B_unsupported_fields",
    "S_native_control",
)
GENERATIVE_CASES = frozenset({"B_unknown_id", "B_unsupported_fields", "S_native_control"})
SOURCE_CASES = frozenset({
    "A_empty", "A_enrichment_failed", "B_unknown_id", "B_unsupported_fields",
    "S_native_control",
})

CASES: Dict[str, Dict[str, Any]] = {
    "A_empty": {"mode": "source", "injection": "all explore_pois -> valid empty",
                "expected_error": "insufficient_data", "provider_calls": 0},
    "A_enrichment_failed": {"mode": "source",
                            "injection": "get_poi_details -> controlled isError",
                            "expected_error": "insufficient_data", "provider_calls": 0},
    "C_no_match_native": {"mode": "current_admin", "injection": None,
                          "expected_error": "location_not_resolved", "provider_calls": 0},
    "C_ambiguous": {"mode": "current_admin",
                    "injection": "resolver -> two authored District 1 matches",
                    "expected_error": "location_ambiguous", "provider_calls": 0},
    "C_wrong_parent": {"mode": "current_admin",
                       "injection": "resolver -> conflicting parent city",
                       "expected_error": "scope_conflict", "provider_calls": 0},
    "C_partial_collision": {"mode": "current_admin",
                            "injection": "resolver -> only District 10 fixture",
                            "expected_error": "location_not_resolved", "provider_calls": 0},
    "B_unknown_id": {"mode": "source",
                     "injection": "valid plan first POI id -> SYS098_GHOST_ID",
                     "expected_error": "unknown_poi", "provider_calls": 1},
    "B_unsupported_fields": {"mode": "source",
                             "injection": "valid plan poi name/address/price/hours/description",
                             "expected_error": None, "provider_calls": 1},
    "S_native_control": {"mode": "source", "injection": None,
                         "expected_error": None, "provider_calls": 1},
}

_FATAL_CODES = frozenset(set(_FATAL_PROVIDER_CODES) | {
    "auth_error", "authority_denied", "permission_denied", "forbidden",
    "quota_exceeded", "guard_rejected", "provider_identity_mismatch",
    "secret_error", "credential_error", "unauthorized", "authentication_failed",
    "provider_mismatch", "model_mismatch", "model_config_mismatch",
    "cli_ambient_config_refused", "cli_unsafe_executable", "cli_tool_use_denied",
    "cli_agent_unavailable", "invalid_provider_config",
})
_STOP_GENERATIVE_CODES = frozenset({
    "transport_error", "timeout", "model_unavailable", "provider_transport_error",
    "provider_unavailable", "provider_busy", "cli_timeout",
})
# A dead/uncertain transport is not a business outcome.  Once observed, the
# remaining batch is missing regardless of whether the current case itself is
# generative, and no retry/resume is attempted.
_TRANSPORT_FAILURE_CODES = frozenset(set(_STOP_GENERATIVE_CODES) | {"model_unavailable"})
_CLOSED_CLEANUP_CODES = frozenset({
    "cleanup_unverified", "stop_failed", "transport_error",
})
_COLLECTOR_FAILURE_CODES = frozenset({
    "startup_failed", "response_failed", "journal_write_failed", "stop_failed",
    "internal_error",
})

# ---------------------------------------------------------------------------
# Manifest (candidate vs parent-approved frozen binding)
# ---------------------------------------------------------------------------
def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_source_hashes() -> Dict[str, str]:
    files = {
        "qa_runtime": ROOT / "benchmarks/system_adversarial/qa_runtime.py",
        "runner": ROOT / "benchmarks/system_adversarial/runner.py",
        "ai_main": AI_SERVICE_ROOT / "main.py",
        "native_helper": HELPER_PATH,
        "provider_config": AI_SERVICE_ROOT / "domains/providers/config.py",
        "provider_opencode_cli": AI_SERVICE_ROOT / "domains/providers/opencode_cli.py",
        "provider_provenance": AI_SERVICE_ROOT / "domains/providers/provenance.py",
    }
    return {key: _sha256_file(path) for key, path in files.items()}


def _case_body(case: str) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "session_id": f"sys098-synthetic-{case.lower()}",
        "current_city": "Ho Chi Minh City",
        "travel_type": "self-explore, relaxing",
        "num_travelers": 1,
        "start_date": "2026-11-03",
        "target_district": None,
        "duration_days": 1,
        "budget_range": "unknown",
        "user_description": (
            "Synthetic SYS098 request: one day 2026-11-03, 09:00-16:00 +07, "
            "one traveler, car, two stops, 45-minute visits, budget unknown."
        ),
        "memory_enabled": False,
        "transport_mode": "car",
        "minimum_stops": 2,
        "maximum_stops": 2,
        "visit_minutes": 45,
        "day_windows": [{
            "date": "2026-11-03",
            "start": "2026-11-03T09:00:00+07:00",
            "end": "2026-11-03T16:00:00+07:00",
        }],
    }
    if case in SOURCE_CASES:
        body["source_scope"] = dict(SOURCE)
    else:
        body["current_city"] = "Ho Chi Minh City"
        body["target_district"] = (
            "SYS098_NoSuchDistrict" if case == "C_no_match_native" else "District 1"
        )
    return body


def build_requests() -> List[Dict[str, Any]]:
    return [{
        "case": case,
        "order": index + 1,
        "method": "POST",
        "path": ENDPOINT,
        "generative": case in GENERATIVE_CASES,
        "headers": {CASE_HEADER: case},
        "body": _case_body(case),
    } for index, case in enumerate(CASE_ORDER)]


def build_candidate_manifest() -> Dict[str, Any]:
    """Unfrozen candidate only; constructing it touches no backend/socket."""
    return {
        "schema": SCHEMA,
        "task_id": TASK,
        "frozen": False,
        "review": {"decision": "not_reviewed", "reviewer": None},
        "mode": "offline_candidate",
        "source": dict(SOURCE),
        "dataset": {"path": DATASET_PATH.relative_to(ROOT).as_posix(),
                    "sha256": DATASET_SHA256, "records": 6367},
        "runtime": {
            "model": MODEL,
            "mcp_port": MCP_PORT,
            "ai_port": AI_PORT,
            "forbidden_ports": sorted(FORBIDDEN_PORTS),
            "endpoint": ENDPOINT,
            "fresh_state": True,
            "memory_enabled": False,
            "cli_timeout_seconds": 30,
            "max_attempts_per_call": 1,
        },
        "cases": [dict(case=case, **CASES[case]) for case in CASE_ORDER],
        "requests": build_requests(),
        "limits": {
            "http_requests": MAX_HTTP_REQUESTS,
            "generative_requests": MAX_GENERATIVE_REQUESTS,
            "cli_attempts": MAX_CLI_ATTEMPTS,
            "repetitions": 1,
        },
        "source_hashes": current_source_hashes(),
    }


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise BoundedError(code)


def validate_execution_manifest(manifest: Mapping[str, Any]) -> None:
    """Fail before backend construction unless every binding matches exactly."""
    _require(manifest.get("schema") == SCHEMA, "manifest_schema_mismatch")
    _require(manifest.get("task_id") == TASK, "manifest_task_mismatch")
    _require(manifest.get("frozen") is True, "manifest_not_frozen")
    review = manifest.get("review")
    _require(isinstance(review, Mapping)
             and review.get("decision") == "approved"
             and isinstance(review.get("reviewer"), str)
             and review["reviewer"].strip() != "", "manifest_not_approved")
    runtime = manifest.get("runtime")
    _require(isinstance(runtime, Mapping), "manifest_runtime_missing")
    _require(runtime.get("model") == MODEL, "manifest_model_mismatch")
    _require(runtime.get("mcp_port") == MCP_PORT, "manifest_mcp_port_mismatch")
    _require(runtime.get("ai_port") == AI_PORT, "manifest_ai_port_mismatch")
    _require(runtime.get("endpoint") == ENDPOINT, "manifest_endpoint_mismatch")
    _require(runtime.get("fresh_state") is True, "manifest_state_not_fresh")
    _require(runtime.get("memory_enabled") is False, "manifest_memory_not_disabled")
    _require(runtime.get("cli_timeout_seconds") == 30, "manifest_timeout_mismatch")
    _require(runtime.get("max_attempts_per_call") == 1, "manifest_attempt_mismatch")
    _require(set(runtime.get("forbidden_ports") or []) == set(FORBIDDEN_PORTS),
             "manifest_forbidden_ports_mismatch")
    _require(manifest.get("source") == SOURCE, "manifest_source_mismatch")

    dataset = manifest.get("dataset")
    _require(isinstance(dataset, Mapping), "manifest_dataset_missing")
    _require(dataset.get("sha256") == DATASET_SHA256, "manifest_dataset_hash_mismatch")
    _require(dataset.get("records") == 6367, "manifest_dataset_records_mismatch")
    _require(Path(ROOT / str(dataset.get("path"))).resolve() == DATASET_PATH.resolve(),
             "manifest_dataset_path_mismatch")

    limits = manifest.get("limits")
    expected_limits = {"http_requests": MAX_HTTP_REQUESTS,
                       "generative_requests": MAX_GENERATIVE_REQUESTS,
                       "cli_attempts": MAX_CLI_ATTEMPTS, "repetitions": 1}
    _require(limits == expected_limits, "manifest_limits_mismatch")

    cases = manifest.get("cases")
    _require(isinstance(cases, list) and len(cases) == len(CASE_ORDER),
             "manifest_case_count_mismatch")
    _require(tuple(item.get("case") for item in cases
                   if isinstance(item, Mapping)) == CASE_ORDER,
             "manifest_case_order_mismatch")
    for expected, item in zip(CASE_ORDER, cases):
        fixed = CASES[expected]
        _require(item.get("mode") == fixed["mode"], "manifest_case_mode_mismatch")
        _require(item.get("injection") == fixed["injection"],
                 "manifest_case_injection_mismatch")
        _require(item.get("expected_error") == fixed["expected_error"],
                 "manifest_case_expectation_mismatch")
        _require(item.get("provider_calls") == fixed["provider_calls"],
                 "manifest_case_provider_mismatch")

    requests = manifest.get("requests")
    _require(isinstance(requests, list) and len(requests) == len(CASE_ORDER),
             "manifest_request_count_mismatch")
    _require(requests == build_requests(), "manifest_request_mismatch")

    source_hashes = manifest.get("source_hashes")
    _require(isinstance(source_hashes, Mapping), "manifest_hashes_missing")
    _require(dict(source_hashes) == current_source_hashes(),
             "manifest_source_hash_mismatch")
    _require(DATASET_PATH.is_file(), "manifest_dataset_absent")
    _require(_sha256_file(DATASET_PATH) == DATASET_SHA256,
             "manifest_dataset_digest_mismatch")


# ---------------------------------------------------------------------------
# Sanitized receipt / outcome classification
# ---------------------------------------------------------------------------
def _top_error(payload: Any) -> Optional[str]:
    if not isinstance(payload, Mapping):
        return None
    error = payload.get("error")
    if isinstance(error, Mapping):
        return _closed_error_code(error.get("code"))
    return _closed_error_code(payload.get("error_code"))


def _provider_evidence(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    block = payload.get("provider")
    if not isinstance(block, Mapping):
        return []
    return _provider_receipts({"provider": {"calls": block.get("calls") or []}})


def _sys_block(payload: Any, counters: Mapping[str, Any]) -> Dict[str, Any]:
    value = payload.get("_sys098") if isinstance(payload, Mapping) else None
    keys = (
        "case", "real_tool_calls", "real_provider_calls", "provider_ok_calls",
        "injection_exercised", "injection_counts", "not_exercised",
        "controlled_response_used", "field_comparisons", "control_checks",
    )
    if isinstance(value, Mapping):
        return {key: value.get(key) for key in keys}
    return {key: counters.get(key) for key in keys}


def _selected_ids(payload: Any) -> List[str]:
    """Selected IDs from the actual repaired schedule, never the proposal only."""
    planning = payload.get("planning") if isinstance(payload, Mapping) else None
    schedule = (planning.get("repaired_schedule")
                if isinstance(planning, Mapping) else None)
    if isinstance(schedule, Mapping):
        sequence = schedule.get("sequence")
        if isinstance(sequence, list):
            return [item for item in sequence if isinstance(item, str)][:16]
        days = schedule.get("days")
        if isinstance(days, list):
            ids: List[str] = []
            for day in days:
                stops = day.get("stops") if isinstance(day, Mapping) else None
                for stop in stops if isinstance(stops, list) else []:
                    if isinstance(stop, Mapping) and isinstance(stop.get("poi_id"), str):
                        ids.append(stop["poi_id"])
            return ids[:16]
    return []


def _route_complete(payload: Any) -> Optional[bool]:
    planning = payload.get("planning") if isinstance(payload, Mapping) else None
    if not isinstance(planning, Mapping):
        return None
    selected = planning.get("selected_plan_route")
    if isinstance(selected, Mapping):
        return selected.get("coverage") == "complete" \
            and selected.get("verified") is True
    evidence = planning.get("route_evidence")
    if not isinstance(evidence, Mapping):
        return None
    return evidence.get("coverage") == "complete"


def _delivered(payload: Any) -> bool:
    return isinstance(payload, Mapping) and payload.get("status") == "success" \
        and isinstance(payload.get("reply"), Mapping)


def _parse_aware(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def analyze_native_control(payload: Any, source_ids: Any = None) -> Dict[str, Any]:
    """Inspect the actual repaired-schedule/route shape; booleans only."""
    checks: Dict[str, bool] = {"delivered": _delivered(payload)}
    if not checks["delivered"]:
        return checks
    planning = payload.get("planning") if isinstance(payload, Mapping) else None
    if not isinstance(planning, Mapping):
        return {"delivered": True, "schedule_shape": False}
    schedule = planning.get("repaired_schedule")
    checks["schedule_is_object"] = isinstance(schedule, Mapping)
    if not isinstance(schedule, Mapping):
        return checks
    sequence = schedule.get("sequence")
    days = schedule.get("days")
    checks["sequence_two_unique"] = (
        isinstance(sequence, list) and len(sequence) == 2
        and len({item for item in sequence if isinstance(item, str)}) == 2
        and all(isinstance(item, str) and item for item in sequence))
    checks["days_one"] = isinstance(days, list) and len(days) == 1
    if not checks["days_one"]:
        return checks
    stops = days[0].get("stops") if isinstance(days[0], Mapping) else None
    checks["stops_two"] = isinstance(stops, list) and len(stops) == 2
    if not checks["stops_two"]:
        return checks
    ids = [stop.get("poi_id") if isinstance(stop, Mapping) else None
           for stop in stops]
    checks["stops_match_sequence"] = ids == sequence
    checks["ids_unique_two"] = (len(set(ids)) == 2
                                and all(isinstance(item, str) and item for item in ids))

    window_start = datetime.fromisoformat("2026-11-03T09:00:00+07:00")
    window_end = datetime.fromisoformat("2026-11-03T16:00:00+07:00")
    previous_departure: Optional[datetime] = None
    times_ok = True
    for stop in stops:
        if not isinstance(stop, Mapping):
            times_ok = False
            break
        arrival = _parse_aware(stop.get("arrival"))
        departure = _parse_aware(stop.get("departure"))
        if arrival is None or departure is None or departure <= arrival:
            times_ok = False
            break
        if arrival.date().isoformat() != "2026-11-03" \
                or departure.date().isoformat() != "2026-11-03":
            times_ok = False
            break
        if arrival < window_start or departure > window_end:
            times_ok = False
            break
        if previous_departure is not None and arrival < previous_departure:
            times_ok = False
            break
        previous_departure = departure
    checks["times_aware_positive_ordered_in_window"] = times_ok

    route = planning.get("selected_plan_route")
    checks["selected_route_complete_verified"] = (
        isinstance(route, Mapping)
        and route.get("coverage") == "complete"
        and route.get("verified") is True
        and route.get("transport_mode") == "car")
    evidence = planning.get("route_evidence")
    checks["route_evidence_car"] = (
        isinstance(evidence, Mapping)
        and evidence.get("transport_mode") == "car")
    checks["unknowns_not_globally_verified"] = planning.get("verified") is not True
    if isinstance(source_ids, (list, tuple, set)):
        qualified = {item for item in source_ids if isinstance(item, str)}
        checks["source_candidates_match"] = (len(qualified) >= 2
                                             and set(ids) <= qualified)
    elif isinstance(source_ids, Mapping):
        qualified = {item for item in source_ids.keys() if isinstance(item, str)}
        checks["source_candidates_match"] = (len(qualified) >= 2
                                             and set(ids) <= qualified)
    else:
        checks["source_candidates_match"] = None
    return checks


def _control_passed(checks: Mapping[str, Any]) -> bool:
    required = {
        "delivered", "schedule_is_object", "sequence_two_unique", "days_one",
        "stops_two", "stops_match_sequence", "ids_unique_two",
        "times_aware_positive_ordered_in_window",
        "selected_route_complete_verified", "route_evidence_car",
        "unknowns_not_globally_verified", "source_candidates_match",
    }
    return required <= set(checks) and all(checks.get(key) is True
                                           for key in required)


NEUTRAL_DESCRIPTION = (
    "Stop selected from the verified candidate set retrieved for the requested area."
)


def _merge_boolean(target: Dict[str, bool], key: str, value: bool) -> None:
    target[key] = bool(target.get(key, True)) and bool(value)


def compare_injected_fields(payload: Any, evidence: Mapping[str, Any]
                            ) -> Dict[str, bool]:
    """RAM-only boolean comparison; one bad/missing stop keeps the aggregate false."""
    reply = payload.get("reply") if isinstance(payload, Mapping) else None
    stops = reply.get("stops") if isinstance(reply, Mapping) else None
    if not isinstance(stops, list) or not stops:
        return {"all_stops_covered": False}
    authored = {"SYS098 authored venue name", "SYS098 authored address, not source truth",
                "SYS098 authored price (unverified)",
                "SYS098 authored hours (unverified)",
                "SYS098 authored description (not source truth)"}
    result: Dict[str, bool] = {"all_stops_covered": True}
    for stop in stops:
        if not isinstance(stop, Mapping):
            _merge_boolean(result, "all_stops_covered", False)
            continue
        poi = stop.get("poi")
        if not isinstance(poi, Mapping):
            _merge_boolean(result, "all_stops_covered", False)
            continue
        pid = poi.get("id")
        actual = evidence.get(pid) if isinstance(evidence, Mapping) else None
        if not isinstance(actual, Mapping):
            # Missing evidence is not truth and cannot be skipped.
            _merge_boolean(result, "all_stops_covered", False)
            continue
        for field in ("name",):
            observed = poi.get(field)
            _merge_boolean(
                result, field,
                bool(observed) and observed not in authored
                and observed == actual.get(field))
        # Shared helper: structured production address or legacy flat fixture;
        # invented/missing/extra address shapes stay false.
        _merge_boolean(
            result, "address",
            compare_source_address(poi.get("address"), actual))
        if "operation_time" in poi or "operation_time" in actual:
            _merge_boolean(
                result, "operation_time",
                poi.get("operation_time") == actual.get("operation_time")
                and poi.get("operation_time") not in authored)
        for field in ("price", "hours"):
            _merge_boolean(result, field,
                           poi.get(field) in (None, "", "unknown")
                           and poi.get(field) not in authored)
        _merge_boolean(
            result, "description",
            stop.get("description") == NEUTRAL_DESCRIPTION
            and (stop.get("description_grounded") is False
                 if "description_grounded" in stop else True)
            and poi.get("description") in (None, NEUTRAL_DESCRIPTION))
        _merge_boolean(result, "authored_text_absent",
                       all(value not in authored
                           for value in list(poi.values()) + list(stop.values())
                           if isinstance(value, str)))
    return result


def classify_case(case: str, response: Mapping[str, Any],
                  counters: Mapping[str, Any],
                  evidence: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Classify observed test outcome without promoting missing to pass."""
    payload = response.get("payload")
    status = response.get("status")
    code = _top_error(payload)
    if code is None and isinstance(response.get("error_code"), str):
        code = _closed_error_code(response.get("error_code"))
    sys_block = _sys_block(payload if isinstance(payload, Mapping) else {},
                           counters)
    provider_calls = int(sys_block.get("real_provider_calls") or 0)
    injection = bool(sys_block.get("injection_exercised"))
    expected = CASES[case]
    checks: List[str] = []
    outcome = "observed_pass"
    not_exercised = False

    def fail(reason: str) -> None:
        nonlocal outcome
        outcome = "observed_failure"
        checks.append(reason)

    if status is None:
        return {"case": case, "status": "missing", "error_code": code,
                "checks": ["transport_missing"], "sys098": sys_block}
    if status != 200 and code is None:
        return {"case": case, "status": "missing", "error_code": None,
                "checks": ["http_error_without_closed_code"], "sys098": sys_block}

    if case == "A_empty":
        if not (code == "insufficient_data" and injection and provider_calls == 0):
            fail("expected_insufficient_data_with_injection_and_zero_provider")
        if isinstance(payload, Mapping) and payload.get("reply") is not None:
            fail("unexpected_stops")
    elif case == "A_enrichment_failed":
        if not (code == "insufficient_data" and injection and provider_calls == 0):
            fail("expected_insufficient_data_with_iserror_injection")
    elif case in ("C_no_match_native", "C_ambiguous", "C_wrong_parent",
                  "C_partial_collision"):
        if code != expected["expected_error"] or provider_calls != 0:
            fail("expected_business_rejection_with_zero_provider")
        if case != "C_no_match_native" and not injection:
            fail("injection_not_exercised")
        if case == "C_no_match_native" and injection:
            fail("native_control_must_not_inject")
    elif case in ("B_unknown_id", "B_unsupported_fields"):
        # A generated plan is only a robustness probe after the intended
        # injection actually happened.  A malformed/absent upstream plan is an
        # unexercised case, never a passed/failed robustness observation.
        exercised = (injection and provider_calls >= 1
                     and int(sys_block.get("provider_ok_calls") or 0) >= 1)
        if not exercised:
            not_exercised = True
            if not injection:
                checks.append("plan_injection_not_exercised")
            if provider_calls < 1 or int(sys_block.get("provider_ok_calls") or 0) < 1:
                checks.append("real_generation_not_proven")
        elif case == "B_unknown_id":
            if code != "unknown_poi":
                fail("expected_unknown_poi")
        else:
            if _delivered(payload):
                comparisons = (sys_block.get("field_comparisons")
                               or compare_injected_fields(payload, evidence or {}))
                if not comparisons:
                    fail("missing_field_comparison_evidence")
                elif not all(comparisons.values()):
                    fail("injected_fields_leaked_as_source_truth")
                if comparisons.get("all_stops_covered") is not True:
                    fail("not_every_selected_stop_covered")
            elif code not in {"plan_invalid", "unknown_poi", "time_order_invalid"}:
                fail("unexpected_unsupported_field_outcome")
    elif case == "S_native_control":
        if injection:
            fail("native_control_must_not_inject")
        if provider_calls != 1 or int(sys_block.get("provider_ok_calls") or 0) != 1:
            fail("expected_exactly_one_real_generation")
        if not _delivered(payload):
            fail("native_control_not_delivered")
        else:
            checks_map = sys_block.get("control_checks")
            if not isinstance(checks_map, Mapping):
                checks_map = analyze_native_control(payload)
            for key, value in checks_map.items():
                if value is not True:
                    fail("native_control_unproven:%s" % key)
            if not _control_passed(checks_map):
                fail("native_control_checks_incomplete_or_false")

    if outcome == "observed_pass" and not_exercised:
        outcome = "not_exercised"
    return {"case": case, "status": outcome, "error_code": code,
            "checks": checks, "sys098": sys_block,
            "http_status": status,
            "provider_receipts": _provider_evidence(payload),
            "selected_poi_ids": _selected_ids(payload),
            "route_complete": _route_complete(payload)}


def _sanitize_receipts(receipts: Any) -> List[Dict[str, Any]]:
    """Keep closed fields; observed_model only when it is the exact Go alias.

    Identity is compared before the arbitrary string is scrubbed so a wrong
    nonempty model still stops execution.  Missing identity stays unknown and
    is never filled from the requested model.
    """
    safe: List[Dict[str, Any]] = []
    for item in receipts or []:
        if not isinstance(item, Mapping):
            continue
        row = dict(item)
        observed = row.get("observed_model")
        mismatch = isinstance(observed, str) and bool(observed) and observed != MODEL
        row["model_identity_mismatch"] = mismatch
        if observed != MODEL:
            row["observed_model"] = None
        safe.append(row)
    return safe


def build_case_receipt(*, case: str, response: Mapping[str, Any],
                       counters: Mapping[str, Any],
                       evidence: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Sanitized durable receipt: closed codes, counters, booleans and IDs only."""
    classification = classify_case(case, response, counters, evidence)
    payload = response.get("payload")
    receipt = {
        "case": case,
        "http_status": response.get("status"),
        "status": classification.pop("status"),
        # Classification already closed the transport error_code; retain it
        # even when status/payload are absent.
        "top_error_code": classification.get("error_code"),
        "elapsed_seconds": response.get("elapsed_seconds"),
        "provider_receipts": _sanitize_receipts(
            classification.get("provider_receipts")),
        "selected_poi_ids": classification.get("selected_poi_ids") or [],
        "route_complete": classification.get("route_complete"),
        "checks": classification.get("checks") or [],
        "sys098": classification.get("sys098") or {},
        "controlled_injection": bool((classification.get("sys098") or {})
                                     .get("injection_exercised")),
        "not_source_truth": True,
    }
    return receipt


def _append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def _prepare_output(out: Path) -> None:
    if out.exists():
        raise BoundedError("output_directory_exists")
    out.mkdir(parents=True)
    for relative in ("native_state", "qa_cases"):
        (out / relative).mkdir()


# ---------------------------------------------------------------------------
# Owned backend: accepted NativeBackend + one test-only QA bootstrap
# ---------------------------------------------------------------------------
QA_INSTALL_STATEMENT = (
    "from benchmarks.system_adversarial.qa_runtime import install; install()"
)
BOOTSTRAP_MARKER = "runpy.run_module(module, run_name='__main__')"


def qa_bootstrap_code(original_code: str, service_root: Path) -> str:
    """Insert the explicit opt-in install before the exact known marker once."""
    code = original_code
    if Path(service_root).resolve() != AI_SERVICE_ROOT.resolve():
        return code
    if code.count(BOOTSTRAP_MARKER) != 1:
        raise BoundedError("qa_bootstrap_marker_changed")
    return code.replace(BOOTSTRAP_MARKER,
                        QA_INSTALL_STATEMENT + "\n" + BOOTSTRAP_MARKER)


def _ports_have_no_owners(ports_after: Any) -> bool:
    """Closed no-owner check; rejects any nonempty/truthy owner evidence."""
    if not isinstance(ports_after, Mapping):
        return False
    for value in ports_after.values():
        if value is False or value is None:
            continue
        if isinstance(value, (list, tuple, set, dict)) and not value:
            continue
        return False
    return True



class SystemAdversarialBackend(NativeBackend):
    """Reuse accepted ownership/transport; add only the SYS098 QA bootstrap."""

    def __init__(self, manifest: Mapping[str, Any], output_dir: Path):
        super().__init__(manifest, output_dir)
        self._original_bootstrap: Any = None
        self.evidence: Dict[str, Any] = {}
        # True only when a partial (start-raised) cleanup was verified through
        # the existing helper's ownership check and a clear listener set.
        self.partial_cleanup_verified = False


    def request(self, method: str, path: str, body: Any = None,
                owner: Optional[str] = None,
                headers: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
        """One registered QA header on the exact POST; otherwise inherit."""
        if headers is None:
            return super().request(method, path, body=body, owner=owner)
        if method != "POST" or path != ENDPOINT:
            raise BoundedError("qa_header_endpoint_rejected")
        if not isinstance(headers, Mapping) or set(headers) != {CASE_HEADER}:
            raise BoundedError("qa_header_rejected")
        case = headers.get(CASE_HEADER)
        if case not in CASE_ORDER:
            raise BoundedError("qa_case_unregistered")
        out_headers = {"Content-Type": "application/json", CASE_HEADER: case}
        token = self._owner_token(owner)
        if token is not None:
            out_headers["Authorization"] = "Bearer " + token
        data = None if body is None else json.dumps(
            body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{AI_PORT}{path}", data=data,
            headers=out_headers, method=method)
        started = time.monotonic()
        try:
            with urllib.request.urlopen(
                    request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                payload = json.load(response)
            return {"status": 200, "payload": payload,
                    "elapsed_seconds": round(time.monotonic() - started, 6)}
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read())
            except (ValueError, UnicodeError):
                payload = None
            return {"status": exc.code, "payload": payload,
                    "elapsed_seconds": round(time.monotonic() - started, 6)}
        except (urllib.error.URLError, TimeoutError, OSError):
            return {"status": None, "payload": None,
                    "elapsed_seconds": round(time.monotonic() - started, 6),
                    "error_code": "transport_error"}

    def _configure_helper(self) -> None:
        super()._configure_helper()
        helper = self.helper
        if self._original_bootstrap is None:
            self._original_bootstrap = helper.bootstrap_code
        original_bootstrap = self._original_bootstrap
        original_environment = helper.ai_environment

        def qa_environment(*args: Any, **kwargs: Any) -> Dict[str, str]:
            env = original_environment(*args, **kwargs)
            env["SYS098_ENABLE_QA"] = "1"
            return env

        def qa_bootstrap(service_root: Path) -> str:
            return qa_bootstrap_code(original_bootstrap(service_root),
                                     Path(service_root))

        helper.ai_environment = qa_environment
        helper.bootstrap_code = qa_bootstrap

    def _restore_helper(self) -> None:
        try:
            super()._restore_helper()
        finally:
            if self.helper is not None and self._original_bootstrap is not None:
                self.helper.bootstrap_code = self._original_bootstrap

    def stop(self) -> None:
        try:
            if self.started:
                super().stop()
                return
            if (self.helper is not None and self.stop_args is not None
                    and self.state_file.exists()):
                # A partial start may have created this task's owned state even
                # though started was never set.  Let the existing helper
                # re-verify creation/image/command/listener ownership.
                try:
                    result = self._helper_lifecycle(
                        self.helper.command_stop, self.stop_args)
                except Exception as exc:
                    raise BoundedError("partial_cleanup_unverified") from exc
                ports_after = result.get("ports_after")
                if result.get("status") == "stopped" \
                        and _ports_have_no_owners(ports_after):
                    self.partial_cleanup_verified = True
                    return
                raise BoundedError("partial_cleanup_unverified")
            # No started process and no owned state: make no cleanup claim.
        finally:
            self._restore_helper()



# ---------------------------------------------------------------------------
# Execution (never run by the offline executor; parent seals first)
# ---------------------------------------------------------------------------
def _run_case_request(response: Mapping[str, Any], counters: Mapping[str, Any],
                      evidence: Mapping[str, Any]) -> Dict[str, Any]:
    return build_case_receipt(case=str(counters.get("case")),
                              response=response, counters=counters,
                              evidence=evidence)


def stop_reason_for(receipt: Mapping[str, Any], *, generative: bool,
                    cli_attempts: int) -> Optional[str]:
    """Only fixed fatal/transport/identity classes stop future requests."""
    code = receipt.get("top_error_code")
    codes = [code] if isinstance(code, str) else []
    rows = receipt.get("provider_receipts")
    contributing = [row for row in rows if isinstance(row, Mapping)] \
        if isinstance(rows, list) else []
    # Identity is a closed guard independent of provider error codes.  Inspect
    # every contributing row, including ok=True/error_code=None rows.
    for row in contributing:
        observed = row.get("observed_model")
        if row.get("model_identity_mismatch") is True or (
                isinstance(observed, str) and observed and observed != MODEL):
            return "model_identity_mismatch_stop"
    for row in contributing:
        if isinstance(row.get("error_code"), str):
            codes.append(row["error_code"])
    # Inspect every contributing receipt, not just the top business code.
    fatal = _FATAL_CODES - _STOP_GENERATIVE_CODES - {"model_unavailable"}
    if any(item in fatal for item in codes):
        return "fatal_closed_code_stop"
    if generative and any(item in _STOP_GENERATIVE_CODES
                          or item == "model_unavailable" for item in codes):
        return "generative_transport_stop"
    if cli_attempts > MAX_CLI_ATTEMPTS:
        return "cli_attempt_budget_exceeded"
    return None


def _transport_failure(receipt: Mapping[str, Any]) -> bool:
    """True only for reviewed transport/timeout classes, never business codes."""
    codes = []
    top = receipt.get("top_error_code")
    if isinstance(top, str):
        codes.append(top)
    rows = receipt.get("provider_receipts")
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, Mapping) and isinstance(row.get("error_code"), str):
            codes.append(row["error_code"])
    return any(item in _TRANSPORT_FAILURE_CODES for item in codes)



def execute(manifest: Mapping[str, Any], out: Path) -> Dict[str, Any]:
    validate_execution_manifest(manifest)
    _prepare_output(out)
    backend: Any = None
    ledger = out / "qa_cases" / "case-receipts.jsonl"
    receipts: List[Dict[str, Any]] = []
    start = time.time()
    start_attempted = False
    start_completed = False
    generative_blocked = False
    stop_reason: Optional[str] = None
    failure_code: Optional[str] = None
    cleanup: Dict[str, Any] = {"attempted": False, "ok": None, "error_code": None}

    try:
        try:
            backend = SystemAdversarialBackend(manifest, out)
            start_attempted = True
            backend.start()
            start_completed = True
        except Exception:
            failure_code = "startup_failed"
            if backend is not None:
                start_attempted = True
        requests_to_run = manifest["requests"] if failure_code is None else []
        for request in requests_to_run:
            case = request["case"]
            # A non-generative transport failure latches the block; readonly
            # A/C probes may continue, but no later model work is issued.
            if request["generative"] and generative_blocked:
                stop_reason = "earlier_transport_stop"
                break
            try:
                response = backend.request(
                    "POST", request["path"], body=request["body"],
                    headers={CASE_HEADER: case})
            except Exception:
                failure_code = "response_failed"
                break
            try:
                # The child service attaches _sys098; never invented here.
                payload = response.get("payload")
                counters = (payload.get("_sys098") if isinstance(payload, Mapping)
                            else None) or {"case": case}
                receipt = build_case_receipt(
                    case=case, response=response, counters=counters,
                    evidence=getattr(backend, "evidence", {}) or {})
                receipts.append(receipt)
                attempts = sum(int(item.get("attempts") or 0)
                               for row in receipts
                               for item in row.get("provider_receipts") or []
                               if isinstance(item, Mapping)
                               and isinstance(item.get("attempts"), int))
                if _transport_failure(receipt):
                    generative_blocked = True
                policy_stop = stop_reason_for(
                    receipt, generative=request["generative"],
                    cli_attempts=attempts)
                if policy_stop is not None:
                    stop_reason = policy_stop
            except Exception:
                failure_code = "internal_error"
                break
            try:
                _append_jsonl(ledger, receipt)
            except Exception:
                failure_code = "journal_write_failed"
                break
            if stop_reason is not None:
                break
    finally:
        if start_attempted:
            cleanup["attempted"] = True
            try:
                backend.stop()
                if start_completed:
                    # Preserve the accepted successful-start stop behavior.
                    cleanup["ok"] = True
                else:
                    # A no-op/generic stop return proves nothing after a
                    # partial start; only the helper-backed verification can.
                    verified = getattr(
                        backend, "partial_cleanup_verified", False) is True
                    cleanup["ok"] = True if verified else False
                    if not verified:
                        cleanup["error_code"] = "partial_cleanup_unverified"
            except Exception:
                cleanup["ok"] = False
                if start_completed:
                    cleanup["error_code"] = "stop_failed"
                    if failure_code is None:
                        failure_code = "stop_failed"
                else:
                    # Keep startup_failed and the partial result intact.
                    cleanup["error_code"] = "partial_cleanup_unverified"

        try:
            _append_jsonl(out / "qa_cases" / "run-journal.jsonl", {
                "event": "finished", "stop_reason": stop_reason,
                "failure_code": failure_code,
                "cleanup": cleanup,
                "cases_retained": [row["case"] for row in receipts],
            })
        except Exception:
            if failure_code is None:
                failure_code = "journal_write_failed"

    planned = list(CASE_ORDER)
    observed = [row["case"] for row in receipts]
    result = {
        "schema": SCHEMA,
        "task_id": TASK,
        "status": ("completed_awaiting_codex_qa" if failure_code is None
                   else "partial"),
        "collector_error_code": failure_code,
        "cleanup": cleanup,
        "generated_at_unix": int(time.time()),
        "started_at_unix": int(start),
        "stop_reason": stop_reason,
        "cases": {row["case"]: row for row in receipts},
        "missing_cases": [case for case in planned if case not in observed],
        "counts": {
            "planned": len(planned), "observed": len(observed),
            "observed_pass": sum(1 for row in receipts
                                 if row["status"] == "observed_pass"),
            "observed_failure": sum(1 for row in receipts
                                    if row["status"] == "observed_failure"),
            "not_exercised": sum(1 for row in receipts
                                 if row["status"] == "not_exercised"),
            "missing": sum(1 for row in receipts if row["status"] == "missing"),
        },
        "not_claimed": [
            "natural graph-error frequency", "hallucination rate / H1 evidence",
            "real administrative truth", "live evaluation acceptance",
        ],
    }
    with open(out / "result.json", "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(result, ensure_ascii=False, indent=2))
        handle.flush()
        os.fsync(handle.fileno())
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _load_manifest(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BoundedError("manifest_not_object")
    return payload


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="SYS098 offline collector")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    if not args.execute:
        candidate = build_candidate_manifest()
        print(json.dumps({
            "mode": "dry_run",
            "backend_constructed": False,
            "sockets_opened": False,
            "provider_calls": 0,
            "manifest": candidate,
        }, ensure_ascii=False, indent=2))
        return 0

    if args.out is None:
        raise SystemExit("--out is required with --execute")
    manifest = _load_manifest(Path(args.manifest))
    execute(manifest, Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
