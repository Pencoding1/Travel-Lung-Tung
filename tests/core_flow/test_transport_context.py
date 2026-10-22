"""The validated travel mode reaches generation context and route arguments.

A generic message carries no mode words. The only source is the typed request
field; the system context and the MCP route call must both use it, including
when earlier history used the other mode.
"""

import pytest

from helpers_core_flow import (
    SELECTION_A,
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

TOOLS = ("explore_pois", "get_poi_details", "get_itinerary_route")
MESSAGE = "Gợi ý một buổi chiều nhẹ nhàng."


def _handlers(route_calls):
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
        route_calls.append(dict(args))
        return ok_json({"success": True, "distance_km": 1.2,
                        "time_minutes": 17.0,
                        "stops": [{"id": pid}
                                  for pid in args["ordered_poi_ids"]]})

    return {"explore_pois": explore, "get_poi_details": details,
            "get_itinerary_route": route}


def _turn_responses(call_offset=0):
    return [
        model_message(tool_calls=[tool_call("explore_pois", {}, f"c1{call_offset}")]),
        model_message(tool_calls=[
            tool_call("get_poi_details", {"poi_id": "poi_a"}, f"c2{call_offset}"),
            tool_call("get_poi_details", {"poi_id": "poi_b"}, f"c3{call_offset}"),
        ]),
        model_message(tool_calls=[tool_call(
            "get_itinerary_route",
            {"ordered_poi_ids": ["poi_a", "poi_b"]}, f"c4{call_offset}")]),
        model_message(content="Đã chuẩn bị tuyến."),
    ]


def _wire(monkeypatch, responses, route_calls):
    session = FakeMCPSession(TOOLS, _handlers(route_calls))
    model = ScriptedModel(responses)
    monkeypatch.setattr(main, "open_mcp_session", mcp_seam(session))
    monkeypatch.setattr(main, "gemini_chat_completion", model)
    install_fake_jev("TRAVEL")
    return session, model


def _system(model, index=0):
    return model.payloads[index]["messages"][0]["content"]


@pytest.mark.parametrize("mode", ["car", "foot"])
def test_generic_message_binds_mode_to_context_and_route(monkeypatch, mode):
    route_calls = []
    session, model = _wire(monkeypatch, _turn_responses(), route_calls)

    body = http_call("POST", "/chat", body=chat_body(
        message=MESSAGE, mode=mode, session=f"mode-{mode}")).json()

    assert body["status"] == "success"
    assert body["transport_mode"] == mode
    assert body["transport_mode_source"] == "explicit"
    assert (f"Travel mode for this request: {mode} "
            "(explicitly selected in this request).") in _system(model)
    assert len(route_calls) == 1
    assert route_calls[0]["vehicle"] == mode
    # The selector stays server-side; only the fixed rules reach generation.
    assert SELECTION_A["source_area_id"] not in _system(model)


def test_previous_car_history_cannot_override_a_foot_turn(monkeypatch):
    route_calls = []
    session, model = _wire(
        monkeypatch, _turn_responses(0) + _turn_responses(1), route_calls)

    first = http_call("POST", "/chat", body=chat_body(
        message=MESSAGE, mode="car", session="mode-history")).json()
    second = http_call("POST", "/chat", body=chat_body(
        message=MESSAGE, mode="foot", session="mode-history")).json()

    assert first["transport_mode"] == "car"
    assert second["transport_mode"] == "foot"
    assert "Travel mode for this request: foot " in _system(model, 4)
    assert [call["vehicle"] for call in route_calls] == ["car", "foot"]
    # Same selection keeps the conversation, but the system context is rebuilt
    # per request and only the current mode is authoritative.
    assert second["memory"]["context_reset"] is False
    current_system = _system(model, 4)
    assert "Travel mode for this request: foot " in current_system
    assert "Travel mode for this request: car " not in current_system
    history = "\n".join(
        message.get("content") or ""
        for message in model.payloads[4]["messages"])
    assert "Đã chuẩn bị tuyến." in history
