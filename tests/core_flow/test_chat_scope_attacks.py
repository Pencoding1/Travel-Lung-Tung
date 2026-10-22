"""Source/mode attack scenarios through the real /chat endpoint.

The MCP session and model are faked, but the endpoint, scope gate, chat loop,
working memory and response shaping are real. Assertions cover the arguments
actually sent to MCP and the evidence actually shown to the model.
"""

import json

from domains import grounding
from helpers_core_flow import (
    SELECTION_A,
    SELECTION_B,
    FakeMCPSession,
    ScriptedModel,
    chat_body,
    http_call,
    install_fake_jev,
    mcp_seam,
    model_message,
    ok_json,
    source_detail,
    source_explore_record,
    tool_call,
)

import main

TOOLS = ("explore_pois", "get_poi_details", "get_itinerary_route",
         "resolve_geographic_id")


def _wire(monkeypatch, responses, handlers):
    session = FakeMCPSession(TOOLS, handlers)
    model = ScriptedModel(responses)
    monkeypatch.setattr(main, "open_mcp_session", mcp_seam(session))
    monkeypatch.setattr(main, "gemini_chat_completion", model)
    install_fake_jev("TRAVEL")
    return session, model


def _tool_messages(payload):
    return [message for message in payload.get("messages") or []
            if message.get("role") == "tool"]


def _error_payloads(payload):
    errors = []
    for message in _tool_messages(payload):
        parsed = json.loads(message["content"])
        if isinstance(parsed, dict) and "error" in parsed:
            errors.append(parsed)
    return errors


def _bootstrap_explore(args):
    selection = args["source_scope"]
    return ok_json({
        "success": True,
        "source_scope": dict(selection),
        "results": [
            source_explore_record("poi_a", "Quan A", selection),
            source_explore_record("poi_b", "Quan B", selection),
        ],
    })


def test_explore_arguments_carry_the_exact_request_selection(monkeypatch):
    def explore(_args):
        return ok_json({
            "success": True,
            "source_scope": dict(SELECTION_A),
            "results": [source_explore_record("poi_a", "Quán A", SELECTION_A)],
        })

    session, model = _wire(monkeypatch, [
        model_message(tool_calls=[tool_call("explore_pois", {"limit": 5}, "c1")]),
        model_message(content="Gợi ý quán A."),
    ], {"explore_pois": explore})

    response = http_call("POST", "/chat", body=chat_body(session="scope-args"))
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "success"
    assert len(session.calls) == 2
    assert session.calls[0]["tool"] == "explore_pois"
    assert session.calls[0]["args"]["source_scope"] == SELECTION_A
    assert session.calls[1]["args"]["source_scope"] == SELECTION_A
    assert body["source_scope"] == SELECTION_A
    assert body["scope_mode"] == grounding.SOURCE_SCOPE_CONTRACT
    assert body["scope_gate"]["discovered_poi_count"] == 1
    assert body["bootstrap"]["origin"] == "server_bootstrap"
    assert body["tool_chain"][0]["origin"] == "server_bootstrap"
    second = _tool_messages(model.payloads[1])
    assert second and "poi_a" in second[0]["content"]


def test_server_bootstrap_evidence_is_present_before_the_first_model_turn(monkeypatch):
    session, model = _wire(monkeypatch, [
        model_message(content="Hai điểm phù hợp trong vùng đã chọn."),
    ], {"explore_pois": _bootstrap_explore})

    response = http_call("POST", "/chat", body=chat_body(session="bootstrap-first"))
    body = response.json()

    assert len(model.payloads) == 1
    first_tools = _tool_messages(model.payloads[0])
    assert len(first_tools) == 1
    assert "poi_a" in first_tools[0]["content"]
    assert "poi_b" in first_tools[0]["content"]
    assert body["status"] == "success"
    assert body["bootstrap"] == {
        "origin": "server_bootstrap",
        "requested_tool_calls": 1,
        "evidence_count": 2,
    }
    assert body["tool_chain"][0]["origin"] == "server_bootstrap"
    assert set(body["source_evidence_ids"]) == {"poi_a", "poi_b"}
    assert session.calls[0]["args"]["limit"] == 6


def test_empty_bootstrap_does_not_call_the_model(monkeypatch):
    def empty(_args):
        return ok_json({"success": True, "source_scope": dict(SELECTION_A),
                        "results": []})

    session, model = _wire(monkeypatch, [], {"explore_pois": empty})
    response = http_call("POST", "/chat", body=chat_body(session="empty-bootstrap"))
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "insufficient_data"
    assert body["bootstrap"]["evidence_count"] == 0
    assert body["source_evidence_ids"] == []
    assert model.payloads == []
    assert len(session.calls) == 1
    assert body["tool_chain"][0]["origin"] == "server_bootstrap"


def test_foreign_only_bootstrap_does_not_call_the_model(monkeypatch):
    def foreign(_args):
        return ok_json({
            "success": True,
            "source_scope": dict(SELECTION_A),
            "results": [source_explore_record("poi_foreign", "Ngoài vùng",
                                               SELECTION_B)],
        })

    session, model = _wire(monkeypatch, [], {"explore_pois": foreign})
    response = http_call("POST", "/chat", body=chat_body(session="foreign-bootstrap"))
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "insufficient_data"
    assert body["source_evidence_ids"] == []
    assert body["scope_gate"]["filtered_out_of_scope"] == 1
    assert model.payloads == []
    assert len(session.calls) == 1


def test_mixed_source_bootstrap_is_filtered_before_the_model(monkeypatch):
    def mixed(_args):
        return ok_json({
            "success": True,
            "source_scope": dict(SELECTION_A),
            "results": [
                source_explore_record("poi_a", "Quán A", SELECTION_A),
                source_explore_record("poi_foreign", "Ngoài vùng", SELECTION_B),
            ],
        })

    _, model = _wire(monkeypatch, [
        model_message(content="Chỉ dùng dữ liệu trong vùng."),
    ], {"explore_pois": mixed})
    body = http_call("POST", "/chat", body=chat_body(session="mixed-bootstrap")).json()

    first_tools = _tool_messages(model.payloads[0])
    assert len(first_tools) == 1
    assert "poi_a" in first_tools[0]["content"]
    assert "poi_foreign" not in first_tools[0]["content"]
    assert body["source_evidence_ids"] == ["poi_a"]
    assert body["scope_gate"]["filtered_out_of_scope"] == 1


def test_malformed_bootstrap_does_not_call_the_model(monkeypatch):
    def malformed(_args):
        return ok_json({"success": False, "code": "synthetic", "detail": "bad"})

    session, model = _wire(monkeypatch, [], {"explore_pois": malformed})
    body = http_call("POST", "/chat", body=chat_body(session="bad-bootstrap")).json()

    assert body["status"] == "insufficient_data"
    assert body["source_evidence_ids"] == []
    assert model.payloads == []
    assert len(session.calls) == 1


def test_model_cannot_swap_the_selection(monkeypatch):
    session, model = _wire(monkeypatch, [
        model_message(tool_calls=[tool_call(
            "explore_pois", {"source_scope": dict(SELECTION_B)}, "c1")]),
        model_message(content="Không có dữ liệu."),
    ], {"explore_pois": _bootstrap_explore})

    response = http_call("POST", "/chat", body=chat_body(session="scope-swap"))
    body = response.json()

    assert len(session.calls) == 1  # only the server bootstrap reached MCP
    assert session.calls[0]["args"]["source_scope"] == SELECTION_A
    errors = _error_payloads(model.payloads[1])
    assert [item["error"] for item in errors] == ["source_selection_mismatch"]
    assert response.status_code == 200
    assert body["scope_gate"]["rejections"][0]["code"] == "source_selection_mismatch"


def test_model_cannot_use_current_geography_or_discovery(monkeypatch):
    session, model = _wire(monkeypatch, [
        model_message(tool_calls=[
            tool_call("explore_pois", {"city_id": "hcmc"}, "c1"),
            tool_call("resolve_geographic_id", {"keyword": "Quận 1"}, "c2"),
        ]),
        model_message(content="Không thể lấy dữ liệu ngoài vùng đã chọn."),
    ], {"explore_pois": _bootstrap_explore})

    http_call("POST", "/chat", body=chat_body(session="scope-geo"))
    assert len(session.calls) == 1  # only the server bootstrap reached MCP
    errors = _error_payloads(model.payloads[1])
    codes = {item["error"] for item in errors}
    assert codes == {"source_scope_violation", "current_geography_blocked"}


def test_model_cannot_fetch_an_inferred_detail_id(monkeypatch):
    session, model = _wire(monkeypatch, [
        model_message(tool_calls=[tool_call(
            "get_poi_details", {"poi_id": "poi_doan_duong"}, "c1")]),
        model_message(content="Không có dữ liệu cho điểm này."),
    ], {"explore_pois": _bootstrap_explore})

    http_call("POST", "/chat", body=chat_body(session="scope-detail"))
    assert len(session.calls) == 1  # only the server bootstrap reached MCP
    errors = _error_payloads(model.payloads[1])
    assert [item["error"] for item in errors] == ["unverified_poi_id"]


def test_out_of_scope_nearby_is_removed_before_the_model(monkeypatch):
    def explore(_args):
        return ok_json({
            "success": True,
            "source_scope": dict(SELECTION_A),
            "results": [source_explore_record("poi_a", "Quán A", SELECTION_A)],
        })

    detail = source_detail(
        "poi_a", "Quán A", SELECTION_A,
        nearby=[{"poi": {"id": "poi_a"}, "distance": 10.0},
                {"poi": {"id": "poi_foreign"}, "distance": 4.0}])

    def details(_args):
        return ok_json({"success": True, "result": detail})

    _, model = _wire(monkeypatch, [
        model_message(tool_calls=[tool_call("explore_pois", {}, "c1")]),
        model_message(tool_calls=[tool_call(
            "get_poi_details", {"poi_id": "poi_a"}, "c2")]),
        model_message(content="Quán A ở trong vùng đã chọn."),
    ], {"explore_pois": explore, "get_poi_details": details})

    http_call("POST", "/chat", body=chat_body(session="scope-nearby"))
    final_messages = model.payloads[2]["messages"]
    detail_messages = [message for message in final_messages
                       if message.get("role") == "tool"
                       and "poi_foreign" in message.get("content", "")]
    assert detail_messages == []
    assert any("poi_a" in message.get("content", "")
               for message in final_messages if message.get("role") == "tool")


def test_model_cannot_override_car_with_foot(monkeypatch):
    session, model = _wire(monkeypatch, [
        model_message(tool_calls=[tool_call(
            "get_itinerary_route",
            {"ordered_poi_ids": ["poi_a", "poi_b"], "vehicle": "foot"}, "c1")]),
        model_message(content="Không thể đổi cách di chuyển."),
    ], {"explore_pois": _bootstrap_explore})

    http_call("POST", "/chat", body=chat_body(mode="car", session="mode-car"))
    assert len(session.calls) == 1  # only the server bootstrap reached MCP
    errors = _error_payloads(model.payloads[1])
    assert [item["error"] for item in errors] == ["transport_mode_mismatch"]


def test_foot_mode_reaches_the_actual_route_arguments(monkeypatch):
    def explore(_args):
        return ok_json({
            "success": True,
            "source_scope": dict(SELECTION_A),
            "results": [
                source_explore_record("poi_a", "Quán A", SELECTION_A),
                source_explore_record("poi_b", "Quán B", SELECTION_A),
            ],
        })

    def details(args):
        pid = args["poi_id"]
        return ok_json({"success": True, "result": source_detail(
            pid, f"Quán {pid}", SELECTION_A)})

    def route(args):
        ids = args["ordered_poi_ids"]
        return ok_json({
            "success": True,
            "distance_km": 1.2,
            "time_minutes": 17.0,
            "stops_mapped": len(ids),
            "stops": [{"id": pid, "latitude": 10.77,
                       "longitude": 106.7} for pid in ids],
        })

    session, _ = _wire(monkeypatch, [
        model_message(tool_calls=[tool_call("explore_pois", {}, "c1")]),
        model_message(tool_calls=[
            tool_call("get_poi_details", {"poi_id": "poi_a"}, "c2"),
            tool_call("get_poi_details", {"poi_id": "poi_b"}, "c3"),
        ]),
        model_message(tool_calls=[tool_call(
            "get_itinerary_route",
            {"ordered_poi_ids": ["poi_a", "poi_b"], "vehicle": "foot"}, "c4")]),
        model_message(content="Tuyến đi bộ đã sẵn sàng."),
    ], {"explore_pois": explore, "get_poi_details": details,
        "get_itinerary_route": route})

    response = http_call("POST", "/chat",
                         body=chat_body(mode="foot", session="mode-foot"))
    route_calls = [call for call in session.calls
                   if call["tool"] == "get_itinerary_route"]
    assert len(route_calls) == 1
    assert route_calls[0]["args"]["vehicle"] == "foot"
    body = response.json()
    assert body["transport_mode"] == "foot"
    evidence = body["route_evidence"]
    assert evidence["success"] is True
    assert evidence["origin"] == "mcp"
    assert evidence["vehicle"] == "foot"
    assert evidence["ordered_poi_ids"] == ["poi_a", "poi_b"]
    assert evidence["distance_km"] == 1.2
    assert evidence["time_minutes"] == 17.0
    assert evidence["stops_mapped"] == 2
    assert [stop["id"] for stop in evidence["stops"]] == ["poi_a", "poi_b"]
    assert evidence["source_scope"] == SELECTION_A


def test_legacy_turn_refuses_model_supplied_source_arguments(monkeypatch):
    session, model = _wire(monkeypatch, [
        model_message(tool_calls=[tool_call(
            "explore_pois", {"source_scope": dict(SELECTION_A)}, "c1")]),
        model_message(content="Không có nguồn dữ liệu trong yêu cầu này."),
    ], {})

    response = http_call("POST", "/chat", body={
        "session_id": "legacy-source", "message": "quán cà phê"})
    assert session.calls == []
    message = _tool_messages(model.payloads[1])[0]
    assert json.loads(message["content"])["error"] == "source_discovery_blocked"
    assert response.json()["scope_mode"] == grounding.SCOPE_MODE_CURRENT
