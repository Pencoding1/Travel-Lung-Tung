"""Upstream failure text never reaches the model, trace, response or memory.

The server gate speaks only in its own fixed machine codes. Any other
``success:false`` code/detail pair is opaque and must collapse to a generic
constant, in both source-scoped and legacy turns.
"""

import json

from domains import grounding
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
    source_explore_record,
    tool_call,
)

import main

TOOLS = ("explore_pois", "get_poi_details", "get_itinerary_route")
OPAQUE_CODE = "XYZ_OPAQUE_9F3"
OPAQUE_DETAIL = "opaque marker 7Q1"


def _wire(monkeypatch, responses, handlers):
    session = FakeMCPSession(TOOLS, handlers)
    model = ScriptedModel(responses)
    monkeypatch.setattr(main, "open_mcp_session", mcp_seam(session))
    monkeypatch.setattr(main, "gemini_chat_completion", model)
    install_fake_jev("TRAVEL")
    return session, model


def _failed(_args):
    return ok_json({"success": False, "code": OPAQUE_CODE,
                    "detail": OPAQUE_DETAIL})


def _bootstrap_ok(args):
    selection = args["source_scope"]
    return ok_json({
        "success": True,
        "source_scope": dict(selection),
        "results": [source_explore_record("poi_a", "Quán A", selection)],
    })


def _assert_opaque_is_absent(body, model):
    rendered = json.dumps(body, ensure_ascii=False)
    assert OPAQUE_CODE not in rendered
    assert OPAQUE_DETAIL not in rendered
    for payload in model.payloads:
        for message in payload.get("messages") or []:
            text = json.dumps(message, ensure_ascii=False)
            assert OPAQUE_CODE not in text
            assert OPAQUE_DETAIL not in text


def test_source_mode_upstream_error_is_replaced_by_a_generic_constant(monkeypatch):
    bootstrap_calls = []

    def explore(args):
        bootstrap_calls.append(args)
        if len(bootstrap_calls) == 1:
            return _bootstrap_ok(args)
        return _failed(args)

    session, model = _wire(monkeypatch, [
        model_message(tool_calls=[tool_call("explore_pois", {}, "c1")]),
        model_message(content="Không lấy được dữ liệu trong vùng đã chọn."),
    ], {"explore_pois": explore})

    response = http_call("POST", "/chat", body=chat_body(session="opaque-source"))
    body = response.json()

    tool_messages = [message for message in model.payloads[1]["messages"]
                     if message.get("role") == "tool"]
    payload = next(item for item in (json.loads(message["content"])
                                     for message in tool_messages)
                   if item.get("error") == "tool_error")
    assert payload["detail"] == "The tool call did not return usable evidence."
    _assert_opaque_is_absent(body, model)
    assert OPAQUE_CODE not in json.dumps(
        main.WORKING_MEMORY.snapshot(main._memory_key(None, "opaque-source")),
        ensure_ascii=False)
    assert len(session.calls) == 2
    assert session.calls[0]["args"]["source_scope"] == SELECTION_A
    assert session.calls[1]["args"]["source_scope"] == SELECTION_A


def test_legacy_mode_upstream_error_is_replaced_by_a_generic_constant(monkeypatch):
    session, model = _wire(monkeypatch, [
        model_message(tool_calls=[tool_call("explore_pois", {}, "c1")]),
        model_message(content="Không lấy được dữ liệu."),
    ], {"explore_pois": _failed})

    response = http_call("POST", "/chat", body={
        "session_id": "opaque-legacy", "message": "quán cà phê"})
    body = response.json()

    tool_messages = [message for message in model.payloads[1]["messages"]
                     if message.get("role") == "tool"]
    payload = json.loads(tool_messages[0]["content"])
    assert payload["error"] == "tool_error"
    _assert_opaque_is_absent(body, model)
    assert body["scope_mode"] == grounding.SCOPE_MODE_CURRENT


def test_gate_rejection_keeps_its_own_code_and_fixed_message(monkeypatch):
    session, model = _wire(monkeypatch, [
        model_message(tool_calls=[tool_call(
            "get_poi_details", {"poi_id": "poi_invented"}, "c1")]),
        model_message(content="Không có điểm này trong vùng đã chọn."),
    ], {"explore_pois": _bootstrap_ok})

    http_call("POST", "/chat", body=chat_body(session="gate-fixed"))

    tool_messages = [message for message in model.payloads[1]["messages"]
                     if message.get("role") == "tool"]
    payload = next(item for item in (json.loads(message["content"])
                                     for message in tool_messages)
                   if item.get("error") == "unverified_poi_id")
    assert payload["detail"] == (
        "The POI id was not verified inside the selected source area.")
    assert len(session.calls) == 1  # only the server bootstrap reached MCP
    assert session.calls[0]["tool"] == "explore_pois"
