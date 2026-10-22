"""AI063 /chat intent gate: actual ASGI path with fake Jev/MCP/generation.

No live model, network, database server or credential is used.
"""

import asyncio
import copy
import json

import httpx
import main
import pytest
from domains.memory import SQLiteProfileStore
from httpx import ASGITransport, AsyncClient

from helpers_chat_memory import (
    FakeMCPSession,
    auth_header,
    hub_llm,
    install_fake_jev,
    jev_choice_response,
    make_token,
    mcp_seam,
    model_message,
    ok_json,
    tool_call,
)

SECRET = "jev-gate-synthetic-secret-0123456789"


def _call(method, path, body=None, headers=None):
    async def run():
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport,
                               base_url="http://test") as client:
            return await client.request(method, path, json=body,
                                        headers=headers)

    return asyncio.run(run())


def _body(message="cafes in District 1", memory=False, session="s1"):
    return {"session_id": session, "message": message,
            "memory_enabled": memory}


def _forbid_downstream(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("downstream work must not run for unresolved intent")

    monkeypatch.setattr(main, "get_profile_store", boom)
    monkeypatch.setattr(main, "open_mcp_session", boom)
    monkeypatch.setattr(main, "gemini_chat_completion", boom)
    monkeypatch.setattr(main.WORKING_MEMORY, "lease", boom)
    monkeypatch.setattr(main.WORKING_MEMORY, "compose", boom)
    monkeypatch.setattr(main.WORKING_MEMORY, "commit", boom)


def _memory_snapshot():
    """Serializable working-memory snapshot (entries themselves have no __eq__)."""
    return {
        key: {
            "completed": copy.deepcopy(entry.session.completed),
            "summary_lines": list(entry.session.summary_lines),
            "discarded": entry.session.discarded,
        }
        for key, entry in main.WORKING_MEMORY._entries.items()
    }


def _travel_wire(monkeypatch, agent_responses):
    session = FakeMCPSession(
        ("get_poi_details",),
        {"get_poi_details": lambda args: ok_json({
            "success": True, "result": {"POI_ID": "poi_a", "POI_Name": "A"}})})
    monkeypatch.setattr(main, "open_mcp_session", mcp_seam(session))
    install_fake_jev(choice="TRAVEL")
    llm = hub_llm(agent_responses=agent_responses)
    monkeypatch.setattr(main, "gemini_chat_completion", llm)
    return session, llm


# ---------------------------------------------------------------------------
# D. Executable outcomes
# ---------------------------------------------------------------------------
def test_confident_travel_uses_real_tool_and_generation_paths(monkeypatch):
    session, llm = _travel_wire(monkeypatch, [
        model_message(tool_calls=[
            tool_call("get_poi_details", {"poi_id": "poi_a"}, "c1")],
            usage={"prompt_tokens": 11, "completion_tokens": 5,
                   "total_tokens": 16}),
        model_message(content="Here is the cafe.",
                      usage={"prompt_tokens": 11, "completion_tokens": 5,
                             "total_tokens": 16}),
    ])

    response = _call("POST", "/chat", _body())
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "TRAVEL"
    assert body["status"] == "success"
    assert body["reply"] == "Here is the cafe."
    assert body["tool_chain"][0]["tool"] == "get_poi_details"
    assert body["source_evidence_ids"] == ["poi_a"]
    assert [call["args"] for call in session.calls] == [{"poi_id": "poi_a"}]
    assert body["router"]["status"] == "ok"
    assert body["router"]["provider"] == "typesafe"
    assert body["router"]["requested_model"] == "jev-latest"
    assert body["router"]["observed_model"] == "jev-test-1"
    assert body["usage"]["model_calls"] == 3
    assert body["usage"]["input_tokens"] == 4 + 11 + 11
    assert body["usage"]["output_tokens"] == 1 + 5 + 5
    # Jev has no documented total: never infer it from input+output.
    assert body["usage"]["total_tokens"] is None
    assert body["usage"]["token_completeness"]["total_tokens"] is False


def test_confident_chitchat_bypasses_tools(monkeypatch):
    install_fake_jev(choice="CHITCHAT")

    def boom(*args, **kwargs):
        raise AssertionError("chitchat must not open MCP/profile/memory")

    monkeypatch.setattr(main, "open_mcp_session", boom)
    monkeypatch.setattr(main, "get_profile_store", boom)
    llm = hub_llm([model_message(content="Xin chào!")])
    monkeypatch.setattr(main, "gemini_chat_completion", llm)

    response = _call("POST", "/chat", _body("xin chào", memory=False))
    body = response.json()
    assert response.status_code == 200
    assert body["intent"] == "CHITCHAT"
    assert body["reply"] == "Xin chào!"
    assert body["tool_chain"] == []
    assert body["source_evidence_ids"] == []
    assert body["usage"]["model_calls"] == 2
    assert llm.state["agent_calls"] == 1


@pytest.mark.parametrize("install", [
    lambda: install_fake_jev(
        response=jev_choice_response(
            choice="TRAVEL", probabilities={
                "CHITCHAT": 1 / 3, "TRAVEL": 1 / 3, "UNCERTAIN": 1 / 3})),
    lambda: install_fake_jev(choice="TRAVEL", confidence=0.1,
                             env={"TYPESAFE_API_KEY": "dummy-test-key",
                                  "JEV_MIN_CONFIDENCE": "0.6"}),
    lambda: install_fake_jev(choice="UNCERTAIN"),
])
def test_ambiguous_tied_lowconfidence_or_uncertain_returns_clarification(
        monkeypatch, install):
    _forbid_downstream(monkeypatch)
    install()
    entries_before = _memory_snapshot()

    response = _call("POST", "/chat", _body("Đà Nẵng"))
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] is None
    assert body["status"] == "needs_clarification"
    assert body["clarification_required"] is True
    assert body["reply"] == main.INTENT_CLARIFY_REPLY_VN
    assert body["tool_chain"] == []
    assert body["source_evidence_ids"] == []
    assert body["router"]["status"] == "ambiguous"
    assert body["router"]["fallback"] is False
    assert body["usage"]["model_calls"] == 1
    assert body["usage"]["token_completeness"]["total_tokens"] is False
    assert _memory_snapshot() == entries_before


def test_refused_route_preserves_prior_history(monkeypatch):
    session, llm = _travel_wire(monkeypatch, [
        model_message(content="First answer.")])
    first = _call("POST", "/chat", _body("cafes", memory=True,
                                         session="history-s"))
    assert first.status_code == 200
    before = _memory_snapshot()
    agent_calls_before = llm.state["agent_calls"]

    _forbid_downstream(monkeypatch)
    install_fake_jev(choice="TRAVEL", confidence=0.1,
                     env={"TYPESAFE_API_KEY": "dummy-test-key",
                          "JEV_MIN_CONFIDENCE": "0.9"})
    second = _call("POST", "/chat", _body("Đà Nẵng", memory=True,
                                          session="history-s"))
    assert second.status_code == 200
    assert second.json()["status"] == "needs_clarification"
    assert second.json()["intent"] is None
    assert _memory_snapshot() == before
    assert llm.state["agent_calls"] == agent_calls_before


def test_refused_route_preserves_verified_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    db_path = str(tmp_path / "profiles.db")
    monkeypatch.setenv("MEMORY_DB_PATH", db_path)
    store = SQLiteProfileStore(db_path)
    store.put("user-9", {"preferred_categories": {"cat_coffee": 9.0}})
    before = copy.deepcopy(store.get("user-9"))

    _forbid_downstream(monkeypatch)
    install_fake_jev(choice="UNCERTAIN")

    response = _call("POST", "/chat",
                     _body("Đà Nẵng", memory=True),
                     headers=auth_header(make_token("user-9", SECRET)))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_clarification"
    assert body["memory"]["profile_injected"] is False
    assert store.get("user-9") == before


# ---------------------------------------------------------------------------
# D. Deterministic unavailable outcomes, zero downstream work
# ---------------------------------------------------------------------------
def test_malformed_choice_is_503_with_attempted_usage(monkeypatch):
    _forbid_downstream(monkeypatch)
    install_fake_jev(handler=lambda request: httpx.Response(200, json={
        "model": "jev-test-1",
        "answers": {"intent": {
            "type": "choice", "choice": "MAYBE",
            "probabilities": {"CHITCHAT": 0.2, "TRAVEL": 0.4,
                              "UNCERTAIN": 0.4},
            "confidence": 0.4}},
        "usage": {"input_tokens": 6, "output_tokens": 2},
    }))

    response = _call("POST", "/chat", _body())
    assert response.status_code == 503
    body = response.json()
    assert body["intent"] is None
    assert body["status"] == "unavailable"
    assert body["reply"] == main.INTENT_UNAVAILABLE_REPLY_VN
    assert body["error"]["code"] == "intent_unavailable"
    assert body["router"]["status"] == "malformed"
    assert body["usage"]["model_calls"] == 1
    assert body["usage"]["input_tokens"] == 6
    assert body["usage"]["output_tokens"] == 2
    assert body["usage"]["total_tokens"] is None


def test_service_failure_is_503_with_unknown_attempt_usage(monkeypatch):
    _forbid_downstream(monkeypatch)
    install_fake_jev(handler=lambda request: httpx.Response(500))

    response = _call("POST", "/chat", _body())
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "intent_unavailable"
    assert body["router"]["status"] == "unavailable"
    assert body["usage"]["model_calls"] == 1
    assert body["usage"]["input_tokens"] is None
    assert body["usage"]["output_tokens"] is None
    assert body["usage"]["total_tokens"] is None
    assert body["usage"]["token_completeness"]["input_tokens"] is False


def test_missing_usage_rejects_choice_and_keeps_attempt_unknown(monkeypatch):
    _forbid_downstream(monkeypatch)
    payload = jev_choice_response(choice="TRAVEL")
    payload.pop("usage")
    install_fake_jev(response=payload)

    response = _call("POST", "/chat", _body())
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["router"]["status"] == "malformed"
    assert body["usage"]["model_calls"] == 1
    assert body["usage"]["input_tokens"] is None


def test_unconfigured_router_is_503_with_zero_attempts(monkeypatch):
    _forbid_downstream(monkeypatch)
    main.configure_intent_router({})

    response = _call("POST", "/chat", _body())
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "intent_unavailable"
    assert body["router"]["status"] == "unconfigured"
    assert body["usage"]["model_calls"] == 0
    assert body["usage"]["calls"] == []


@pytest.mark.parametrize("injected", [
    {},
    {"status": "ok", "intent": "TRAVEL_MAYBE"},
    {"status": "ok", "intent": None},
    {"status": "bogus", "intent": "TRAVEL"},
    "not-a-dict",
])
def test_malformed_injected_router_never_lands_in_travel(monkeypatch, injected):
    _forbid_downstream(monkeypatch)

    async def fake_route(message, usage=None):
        return injected

    monkeypatch.setattr(main, "route_intent", fake_route)
    response = _call("POST", "/chat", _body())
    assert response.status_code == 503
    body = response.json()
    assert body["intent"] is None
    assert body["error"]["code"] == "intent_unavailable"
    assert body["usage"]["model_calls"] == 0


def test_analyze_intent_returns_none_without_manufacturing_travel():
    install_fake_jev(choice="UNCERTAIN")
    assert asyncio.run(main.analyze_intent("Đà Nẵng")) is None


def test_injected_ok_uncertain_is_clarification_not_travel(monkeypatch):
    _forbid_downstream(monkeypatch)

    async def fake_route(message, usage=None):
        return {"status": "ok", "intent": "UNCERTAIN", "fallback": False}

    monkeypatch.setattr(main, "route_intent", fake_route)
    response = _call("POST", "/chat", _body())
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] is None
    assert body["status"] == "needs_clarification"
    assert body["usage"]["model_calls"] == 0


def test_invalid_supplied_auth_is_401_before_classification(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json=jev_choice_response())

    install_fake_jev(handler=handler)
    monkeypatch.setenv("JWT_SECRET", SECRET)

    response = _call("POST", "/chat", _body(), headers={
        "Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
    assert calls["n"] == 0


# ---------------------------------------------------------------------------
# R1: per-attempt usage identity through the actual route_intent seam
# ---------------------------------------------------------------------------
def test_route_intent_usage_call_carries_typesafe_identity():
    install_fake_jev(choice="TRAVEL")
    usage = main.chat_agent.new_usage()
    router = asyncio.run(main.route_intent("cafes in District 1", usage))

    assert router["status"] == "ok"
    assert usage["model_calls"] == 1
    assert usage["calls"] == [{
        "input_tokens": 4,
        "output_tokens": 1,
        "total_tokens": None,
        "provider": "typesafe",
        "operation": "intent_routing",
        "requested_model": "jev-latest",
        "observed_model": "jev-test-1",
    }]


def test_malformed_choice_usage_keeps_independent_observed_identity():
    payload = jev_choice_response(choice="TRAVEL")
    payload["answers"]["intent"]["choice"] = "NOT_A_LABEL"
    install_fake_jev(response=payload)
    usage = main.chat_agent.new_usage()
    router = asyncio.run(main.route_intent("hello", usage))

    assert router["status"] == "malformed"
    assert usage["calls"][0]["requested_model"] == "jev-latest"
    assert usage["calls"][0]["observed_model"] == "jev-test-1"
    assert usage["calls"][0]["input_tokens"] == 4
    assert usage["calls"][0]["output_tokens"] == 1
