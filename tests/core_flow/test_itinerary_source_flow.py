"""Source-mode itinerary flow over the real HTTP pipeline.

The MCP session and model are faked, but request parsing, retrieval,
qualification, scheduling, route collection and response shaping are real.
The explicit selection and the car/foot mode must survive every tool call.
"""

import json

from domains import grounding
from helpers_core_flow import (
    SELECTION_A,
    FakeMCPSession,
    ScriptedModel,
    http_call,
    install_fake_jev,
    itinerary_body,
    mcp_seam,
    ok_json,
    source_detail,
    source_explore_record,
)

import main

TOOLS = ("get_available_categories", "explore_pois", "get_poi_details",
         "get_itinerary_route")


def _handlers(route_calls):
    records = [
        source_explore_record("poi_a", "Quán A", SELECTION_A),
        source_explore_record("poi_b", "Bảo tàng B", SELECTION_A,
                              category="Museum"),
    ]
    details = {
        "poi_a": source_detail("poi_a", "Quán A", SELECTION_A,
                               operation_time="08:00-22:00"),
        "poi_b": source_detail("poi_b", "Bảo tàng B", SELECTION_A,
                               category="Museum",
                               operation_time="08:00-22:00"),
    }

    def categories(_args):
        return ok_json({"success": True, "categories": [
            {"id": "cat_coffee", "name": "Cafe"}]})

    def explore(args):
        # Both the floor query and the category query carry the same tuple.
        return ok_json({"success": True, "count": len(records),
                        "source_scope": dict(args["source_scope"]),
                        "results": records})

    def detail(args):
        return ok_json({"success": True,
                        "result": details[args["poi_id"]]})

    def route(args):
        route_calls.append(dict(args))
        ids = args["ordered_poi_ids"]
        return ok_json({
            "success": True,
            "distance_km": 1.2,
            "time_minutes": 30.0,
            "stops_mapped": len(ids),
            "stops": [{"id": pid} for pid in ids],
            "turn_by_turn": [],
        })

    return {"get_available_categories": categories, "explore_pois": explore,
            "get_poi_details": detail, "get_itinerary_route": route}


def _plan(second_hour=10):
    """Model proposal; the scheduler repairs times from route evidence."""
    return {
        "start_poi_id": "poi_a",
        "end_poi_id": "poi_b",
        "total_estimated_budget": 300000.0,
        "stops": [
            {"date": "2026-01-01",
             "visit_time": "2026-01-01T09:00:00+07:00",
             "end_time": "2026-01-01T10:00:00+07:00",
             "description": "model text", "budget": 100000.0,
             "poi": {"id": "poi_a"}},
            {"date": "2026-01-01",
             "visit_time": f"2026-01-01T{second_hour:02d}:00:00+07:00",
             "end_time": f"2026-01-01T{second_hour + 1:02d}:00:00+07:00",
             "description": "model text", "budget": 200000.0,
             "poi": {"id": "poi_b"}},
        ],
    }


def _wire(monkeypatch, route_calls, plan=None):
    session = FakeMCPSession(TOOLS, _handlers(route_calls))
    model = ScriptedModel([{"choices": [{"message": {
        "content": json.dumps(plan or _plan())}}]}])
    monkeypatch.setattr(main, "open_mcp_session", mcp_seam(session))
    monkeypatch.setattr(main, "gemini_chat_completion", model)
    install_fake_jev("TRAVEL")
    return session, model


def _explore_calls(session):
    return [call for call in session.calls if call["tool"] == "explore_pois"]


def _assert_source_calls(session):
    assert not [call for call in session.calls
                if call["tool"] == "resolve_geographic_id"]
    for call in _explore_calls(session):
        assert call["args"]["source_scope"] == SELECTION_A
        assert "city_id" not in call["args"]
        assert "district_id" not in call["args"]


def test_car_itinerary_uses_exact_selection_and_qualified_details(monkeypatch):
    route_calls = []
    session, model = _wire(monkeypatch, route_calls)

    response = http_call("POST", "/generate_itinerary",
                         body=itinerary_body(mode="car", session="itin-car"))
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "success", body.get("error")
    _assert_source_calls(session)

    detail_calls = [call for call in session.calls
                    if call["tool"] == "get_poi_details"]
    assert {call["args"]["poi_id"] for call in detail_calls} == {"poi_a", "poi_b"}

    assert route_calls
    for call in route_calls:
        assert call["vehicle"] == "car"
        assert set(call["ordered_poi_ids"]) <= {"poi_a", "poi_b"}

    assert body["reply"]["stops"]
    for stop in body["reply"]["stops"]:
        poi = stop["poi"]
        assert poi["current_admin_status"] == "unverified_source_area"
        assert poi["source_snapshot_area"]["source_area_id"] == \
            SELECTION_A["source_area_id"]
        assert stop["description"] == grounding.NEUTRAL_DESCRIPTION
    assert body["grounding"]["scope_verification"] == "qualified_source_snapshot_area"
    assert body["grounding"]["source_scope"] == SELECTION_A
    assert "current_city" in body["grounding"]["unused_request_fields"]
    assert "target_district" in body["grounding"]["unused_request_fields"]
    assert body["planning"]["route_evidence"]["transport_mode"] == "car"
    assert body["planning"]["request_constraints"]["source_scope"] == SELECTION_A

    prompt = model.payloads[0]["messages"][0]["content"]
    assert "poi_a" in prompt and "poi_b" in prompt
    assert "lineage:test" not in prompt
    assert SELECTION_A["source_area_id"] not in prompt
    assert "UNVERIFIED" in prompt


def test_foot_itinerary_keeps_mode_through_route_calls(monkeypatch):
    route_calls = []
    session, _ = _wire(monkeypatch, route_calls, plan=_plan(second_hour=10))

    response = http_call("POST", "/generate_itinerary",
                         body=itinerary_body(mode="foot", session="itin-foot"))
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "success", body.get("error")
    _assert_source_calls(session)
    assert route_calls
    for call in route_calls:
        assert call["vehicle"] == "foot"
    assert body["planning"]["route_evidence"]["transport_mode"] == "foot"
    assert body["planning"]["request_constraints"]["transport_mode"] == "foot"
    planned = body["planning"]["repaired_schedule"]["days"][0]["stops"]
    assert planned[1]["travel_from_prev_minutes"] == 30
    assert float(planned[1]["travel_from_prev_distance_km"]) == 1.2


def test_mixed_area_detail_fails_closed_without_using_it(monkeypatch):
    from helpers_core_flow import SELECTION_B

    session = FakeMCPSession(TOOLS, _handlers([]))
    session.handlers["get_poi_details"] = lambda args: ok_json({
        "success": True,
        "result": source_detail(args["poi_id"], "X", SELECTION_B),
    })
    model = ScriptedModel([{"choices": [{"message": {
        "content": json.dumps(_plan())}}]}])
    monkeypatch.setattr(main, "open_mcp_session", mcp_seam(session))
    monkeypatch.setattr(main, "gemini_chat_completion", model)
    install_fake_jev("TRAVEL")

    response = http_call("POST", "/generate_itinerary",
                         body=itinerary_body(session="itin-conflict"))
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "failed"
    assert body["error"]["code"] in (grounding.SCOPE_CONFLICT,
                                     grounding.SOURCE_SCOPE_UNVERIFIED)
    assert body["grounding"]["excluded_source_conflict_count"] == 2
    assert "poi_a" not in (body.get("reply") or "")
    assert model.payloads == []
