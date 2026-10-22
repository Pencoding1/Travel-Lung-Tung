"""Working-memory scope boundary and memory_enabled=false behaviour.

Same-selection conversation may persist; a changed (or unknown) explicit
selection must not carry the previous scope's text or tool evidence into the
new turn. No durable/tenant contract is exercised or changed here.
"""

from uuid import uuid4

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
    source_explore_record,
    tool_call,
)

import main

TOOLS = ("explore_pois", "get_poi_details", "get_itinerary_route")


def _wire(monkeypatch, responses, session_handlers=None, intent="TRAVEL"):
    session = FakeMCPSession(TOOLS, session_handlers or {})
    model = ScriptedModel(responses)
    monkeypatch.setattr(main, "open_mcp_session", mcp_seam(session))
    monkeypatch.setattr(main, "gemini_chat_completion", model)
    install_fake_jev(intent)
    return session, model


def _texts(messages):
    return [message.get("content") or "" for message in messages
            if isinstance(message, dict)]


def _explore_handler(args):
    selection = args.get("source_scope") or SELECTION_A
    poi_id = "poi_a" if selection == SELECTION_A else "poi_b"
    return ok_json({
        "success": True,
        "source_scope": dict(selection),
        "results": [source_explore_record(poi_id, f"Quán {poi_id}",
                                          selection)],
    })


def test_same_selection_keeps_the_conversation(monkeypatch):
    session_key = f"same-{uuid4().hex}"
    _, model = _wire(monkeypatch, [
        model_message(tool_calls=[tool_call("explore_pois", {}, "c1")]),
        model_message(content="A1: quán A đang mở."),
        model_message(content="A2: mình vẫn đang trong vùng đã chọn."),
    ], {"explore_pois": _explore_handler})

    first = http_call("POST", "/chat", body=chat_body(
        session=session_key, source=SELECTION_A))
    second = http_call("POST", "/chat", body=chat_body(
        session=session_key, source=SELECTION_A))

    assert first.json()["memory"]["context_reset"] is False
    assert second.json()["memory"]["context_reset"] is False
    assert any("A1: quán A đang mở." in text
               for text in _texts(model.payloads[2]["messages"]))


def test_selection_switch_drops_previous_text_and_tool_evidence(monkeypatch):
    session_key = f"switch-{uuid4().hex}"
    _, model = _wire(monkeypatch, [
        model_message(tool_calls=[tool_call("explore_pois", {}, "c1")]),
        model_message(content="SCOPE_A_ANSWER: quán A."),
        model_message(content="SCOPE_B_ANSWER: chưa có dữ liệu cho vùng B."),
    ], {"explore_pois": _explore_handler})

    first = http_call("POST", "/chat", body=chat_body(
        session=session_key, source=SELECTION_A))
    assert first.json()["status"] == "success"

    second = http_call("POST", "/chat", body=chat_body(
        session=session_key, source=SELECTION_B))
    body = second.json()

    assert body["memory"]["context_reset"] is True
    second_messages = model.payloads[2]["messages"]
    joined = "\n".join(_texts(second_messages))
    assert "SCOPE_A_ANSWER" not in joined
    assert "poi_a" not in joined
    # The new turn's own server bootstrap may carry the generic source-mode
    # label; only the previous scope's data must be absent.
    # The new turn still carries its own explicit context.
    assert body["source_scope"] == SELECTION_B
    assert body["scope_mode"] == "source_snapshot_area"


def test_unknown_previous_marker_fails_closed(monkeypatch):
    session_key = f"unknown-{uuid4().hex}"
    _, model = _wire(monkeypatch, [
        model_message(content="A: nội dung cũ."),
        model_message(content="B: nội dung mới."),
    ], intent="CHITCHAT")

    http_call("POST", "/chat", body=chat_body(
        session=session_key, source=SELECTION_A))
    main._SCOPE_MARKERS.pop(main._memory_key(None, session_key), None)

    second = http_call("POST", "/chat", body=chat_body(
        session=session_key, source=SELECTION_A))
    assert second.json()["memory"]["context_reset"] is True
    assert not any("A: nội dung cũ." in text
                   for text in _texts(model.payloads[1]["messages"]))


def test_memory_disabled_never_reads_write_or_injects(monkeypatch):
    session_key = f"disabled-{uuid4().hex}"
    _, model = _wire(monkeypatch, [
        model_message(content="Không lưu gì cả."),
        model_message(content="Vẫn không lưu gì."),
    ], intent="CHITCHAT")

    first = http_call("POST", "/chat", body=chat_body(
        session=session_key, source=SELECTION_A, memory=False))
    second = http_call("POST", "/chat", body=chat_body(
        session=session_key, source=SELECTION_A, memory=False))

    assert first.json()["reply"] == "Không lưu gì cả."
    assert first.json()["memory"]["enabled"] is False
    assert second.json()["memory"]["enabled"] is False
    assert not any("Không lưu gì cả." in text
                   for text in _texts(model.payloads[1]["messages"]))
    key = main._memory_key(None, session_key)
    assert main.WORKING_MEMORY.snapshot(key)["completed_turns"] == 0
    assert key not in main._SCOPE_MARKERS
