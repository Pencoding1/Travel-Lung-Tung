"""Pure projection tests for typed plans and actual service responses.

The Codex-authored ``parent_projection_fixture.py`` is imported read-only; its
literal timestamps and expected values are not modified. No HTTP, model or
network call is made.
"""

from __future__ import annotations

import json
import types
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from live_model import service_projection

from domains.planning.contracts import (Plan, PlannedDay, PlannedStop,
                                        ValidationReport, parse_instant)

SENTINEL = "PRIVATE_SENTINEL_MUST_NOT_PERSIST"
EXPECTED = [
    ("day-1", "p-a", "2026-10-18T09:00:00+07:00",
     "2026-10-18T09:20:00+07:00", None, None),
    ("day-1", "p-b", "2026-10-18T09:20:00+07:00",
     "2026-10-18T09:40:00+07:00", 0, "0.000"),
    ("day-2", "p-c", "2026-10-19T10:00:00+07:00",
     "2026-10-19T10:20:00+07:00", None, None),
    ("day-2", "p-d", "2026-10-19T10:23:00+07:00",
     "2026-10-19T10:43:00+07:00", 3, "2.627"),
]


def _typed_plan():
    days = []
    for day_id in ("day-1", "day-2"):
        stops = []
        for day, poi, arrival, departure, minutes, distance in EXPECTED:
            if day != day_id:
                continue
            stops.append(PlannedStop(
                poi_id=poi, arrival=parse_instant(arrival, "arrival"),
                departure=parse_instant(departure, "departure"),
                visit_minutes=20, travel_from_prev_minutes=minutes,
                travel_from_prev_distance_km=(
                    None if distance is None else Decimal(distance)),
                cost_party=None, cost_currency=None))
        days.append(PlannedDay(day_id=day_id, stops=tuple(stops)))
    return Plan(
        scenario_id="synthetic-two-days", status="unverifiable",
        no_plan_reason=None, days=tuple(days),
        sequence=tuple(item[1] for item in EXPECTED),
        total_cost_party=None, total_cost_currency=None,
        total_travel_minutes=3, total_distance_km=Decimal("2.627"),
        excluded=(), unsatisfied_required=(),
        unknown_reasons=("cost_unknown:p-a",), iterations=1, notes=())


def _typed_report():
    return ValidationReport(
        scenario_id="synthetic-two-days", status="unverifiable",
        no_plan_reason=None, known_violations=(),
        unknown_reasons=("cost_unknown:p-a",), unsatisfied_required=(),
        recomputed_total_cost_party=None, recomputed_total_travel_minutes=3,
        recomputed_total_distance_km=Decimal("2.627"), stop_count=4, checks={})


def _scenario_input():
    return {
        "pois": [{"poi_id": poi} for poi in
                 ("p-a", "p-b", "p-c", "p-d", "p-e")],
        "route_edges": [
            {"from_poi_id": "p-a", "to_poi_id": "p-b"},
            {"from_poi_id": "p-c", "to_poi_id": "p-d"},
        ],
        "unknowns": ["opening_hours_unknown"],
    }


def _parsed_proposal():
    return SimpleNamespace(days=(
        SimpleNamespace(day_id="day-1", stops=(
            SimpleNamespace(poi_id="p-b",
                            arrival="2026-10-18T08:00:00+07:00",
                            departure="2026-10-18T08:20:00+07:00"),
        )),
    ))


def _tuple_from_stops(schedule):
    actual = []
    for day in schedule["days"]:
        for stop in day["stops"]:
            actual.append((
                day["day_id"], stop["poi_id"], stop["arrival"],
                stop["departure"], stop["travel_from_prev_minutes"],
                stop["travel_from_prev_distance_km"]))
    return actual


def test_typed_projection_keeps_real_timestamps_and_separate_coverage():
    projection = service_projection.build_projection(
        condition="llm_only", parsed=_parsed_proposal(), plan=_typed_plan(),
        report=_typed_report(), mapping=None,
        scenario_input=_scenario_input())
    assert projection["source"] == service_projection.TYPED_SOURCE_LABEL
    assert projection["not_http_response"] is True
    assert _tuple_from_stops(projection["repaired_schedule"]) == EXPECTED
    for day in projection["repaired_schedule"]["days"]:
        for stop in day["stops"]:
            assert "visit_time" not in stop
            assert "end_time" not in stop
    first = projection["repaired_schedule"]["days"][0]["stops"]
    assert first[0]["travel_from_prev_minutes"] is None
    assert first[0]["travel_from_prev_distance_km"] is None
    assert first[1]["travel_from_prev_minutes"] == 0
    assert first[1]["travel_from_prev_distance_km"] == "0.000"
    assert first[0]["cost_party"] is None
    # The original proposal is preserved and remains different from the repair.
    proposal = projection["initial_proposal"]["days"][0]["stops"][0]
    assert proposal["arrival"] == "2026-10-18T08:00:00+07:00"
    assert proposal["arrival"] != first[0]["arrival"]
    assert projection["totals"]["total_cost_party"] is None
    assert projection["totals"]["total_distance_km"] == "2.627"
    coverage = projection["coverage"]
    assert coverage["selected_plan_route"]["coverage"] == "complete"
    assert coverage["candidate_pool_route"]["coverage"] == "partial"
    assert coverage["global_feasibility"] == "unverifiable"
    assert projection["validation"]["status"] == "unverifiable"


def _load_parent_fixture():
    path = (Path(__file__).resolve().parents[2] / "docs" / "project" /
            "handoffs" / "EXP-074" / "parent_projection_fixture.py")
    # Execute the read-only source without importlib's bytecode cache write, so
    # the parent-owned handoff directory is never modified by this test.
    source = path.read_text(encoding="utf-8")
    module = types.ModuleType("exp074_parent_projection_fixture_readonly")
    module.__file__ = str(path)
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def test_actual_response_projection_preserves_fixture_contract():
    fixture = _load_parent_fixture()
    response = fixture.assert_render_contract()
    projected = service_projection.project_service_response(
        response, http_status=200, elapsed_seconds=1.25)

    assert projected["projection_complete"] is True
    assert projected["source"] == service_projection.RESPONSE_SOURCE_LABEL
    assert projected["http_ok"] is True
    assert projected["response_status"] == "success"
    assert projected["model"] == "opencode-go/deepseek-v4.1-flash"
    assert projected["usage"] is None
    assert projected["provider"] == {
        "selected": "opencode_cli",
        "observed_model": "opencode-go/deepseek-v4.1-flash"}
    assert _tuple_from_stops(projected["planning"]["repaired_schedule"]) \
        == fixture.EXPECTED
    for day in projected["planning"]["repaired_schedule"]["days"]:
        for stop in day["stops"]:
            assert "visit_time" not in stop
            assert "end_time" not in stop
    proposal = projected["planning"]["initial_proposal"]
    assert proposal["sequence"] == ["p-b", "p-a"]
    assert proposal["stops"][0]["poi"]["id"] == "p-b"
    assert proposal["stops"][0]["visit_time"] == "2026-10-18T08:00:00+07:00"
    assert projected["planning"]["validation"]["status"] == "unverifiable"
    assert projected["planning"]["cost"]["known_party_subtotal"] is None
    assert projected["planning"]["cost"]["currency"] == "VND"
    assert projected["planning"]["totals"]["distance_km"] == "2.627"
    assert projected["planning"]["totals"]["stop_count"] == 4
    assert projected["planning"]["model_usage"] is None
    assert projected["planning"]["request_constraints"]["transport_mode"] == "car"
    assert projected["planning"]["selected_plan_route"]["coverage"] == "complete"
    assert projected["planning"]["selected_plan_route"]["verified"] is True
    assert projected["planning"]["route_evidence"]["coverage"] == "partial"
    assert projected["planning"]["route_evidence"]["coverage_scope"] \
        == "candidate_pool"
    assert projected["planning"]["route_evidence"]["attempted"] == 2
    assert projected["global_feasibility"] == "unverifiable"
    dumped = json.dumps(projected, sort_keys=True)
    assert SENTINEL not in dumped
    assert "headers" not in dumped
    assert "untrusted_debug" not in dumped


def test_missing_non_dict_and_error_responses_are_explicit():
    missing = service_projection.project_service_response(
        None, http_status=200, elapsed_seconds=0.1)
    assert missing["response_status"] == "missing_response"
    assert missing["projection_complete"] is False
    assert missing["error"] == {"code": "missing_response"}
    assert missing["planning"] is None

    invalid = service_projection.project_service_response(
        ["not", "a", "mapping"], http_status=200, elapsed_seconds=0.1)
    assert invalid["response_status"] == "invalid_response"
    assert invalid["projection_complete"] is False

    error = service_projection.project_service_response(
        {"status": "error",
         "error": {"code": "validation_error", "message": SENTINEL},
         "headers": {"Authorization": SENTINEL}},
        http_status=422, elapsed_seconds=0.1)
    assert error["http_ok"] is False
    assert error["error"] == {"code": "validation_error"}
    assert error["projection_complete"] is False
    assert SENTINEL not in json.dumps(error, sort_keys=True)

    no_schedule = service_projection.project_service_response(
        {"status": "success", "planning": {}},
        http_status=200, elapsed_seconds=0.1)
    assert no_schedule["planning"]["repaired_schedule"] is None
    assert "planning.repaired_schedule" in no_schedule["missing_fields"]
    assert no_schedule["projection_complete"] is False

    bad_usage = service_projection.project_service_response(
        {"status": "success", "planning": {},
         "usage": {"prompt_tokens": -1, "completion_tokens": True,
                   "total_tokens": {"nested": SENTINEL}}},
        http_status=200, elapsed_seconds=0.1)
    assert bad_usage["usage"] == {
        "prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
    assert SENTINEL not in json.dumps(bad_usage, sort_keys=True)

    fixture = _load_parent_fixture()
    http_error = service_projection.project_service_response(
        fixture.response_fixture(), http_status=500, elapsed_seconds=0.1)
    assert http_error["http_ok"] is False
    assert http_error["projection_complete"] is False
    assert _tuple_from_stops(http_error["planning"]["repaired_schedule"]) \
        == fixture.EXPECTED
    assert http_error["global_feasibility"] == "unverifiable"
