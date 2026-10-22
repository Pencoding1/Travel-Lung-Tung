"""In-process HTTP contract tests for /chat and the memory endpoints (OC-009).

The MCP session and model seam are faked; the HTTP layer is real.
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx
import main
import pytest
from domains import payloads
from httpx import ASGITransport, AsyncClient

from helpers_chat_memory import (
    FakeMCPSession,
    auth_header,
    hub_llm,
    install_fake_jev,
    make_token,
    mcp_seam,
    model_message,
    ok_json,
    tool_call,
)

SECRET = "synthetic-test-secret"


def _call(method, path, body=None, headers=None):
    async def _run():
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, json=body, headers=headers)

    return asyncio.run(_run())


def _wire_chat(monkeypatch, intent="TRAVEL", agent_responses=None,
               tools=("get_poi_details",), handlers=None):
    session = FakeMCPSession(
        tools, handlers or {"get_poi_details": lambda a: ok_json(
            {"success": True, "result": {"POI_ID": "poi_a", "POI_Name": "A"}})})
    monkeypatch.setattr(main, "open_mcp_session", mcp_seam(session))
    install_fake_jev(choice=intent)
    llm = hub_llm(agent_responses=agent_responses)
    monkeypatch.setattr(main, "gemini_chat_completion", llm)
    return session, llm


def test_chat_travel_returns_additive_contract(monkeypatch):
    agent = [
        model_message(tool_calls=[
            tool_call("get_poi_details", {"poi_id": "poi_a"}, "c1")]),
        model_message(content="Here is the cafe.",
                      usage={"prompt_tokens": 7, "completion_tokens": 3,
                             "total_tokens": 10}),
    ]
    _wire_chat(monkeypatch, agent_responses=agent)

    response = _call("POST", "/chat",
                     body={"session_id": "s1", "message": "cafes in District 1"})
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "TRAVEL"
    assert body["status"] == "success"
    assert body["reply"] == "Here is the cafe."
    assert body["tool_chain"][0]["tool"] == "get_poi_details"
    assert body["usage"]["model_calls"] >= 2
    assert body["grounding_status"] == "unverified_free_text"
    assert "poi_a" in body["source_evidence_ids"]


def test_chat_invalid_supplied_token_is_401(monkeypatch):
    _wire_chat(monkeypatch, agent_responses=[model_message(content="hi")])
    monkeypatch.setenv("JWT_SECRET", SECRET)

    response = _call("POST", "/chat",
                     body={"session_id": "s1", "message": "hi"},
                     headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


def test_chat_router_malformed_never_falls_back_to_travel(monkeypatch):
    session, llm = _wire_chat(monkeypatch, agent_responses=[])
    install_fake_jev(handler=lambda request: httpx.Response(200, json={
        "model": "jev-test-1",
        "answers": {"intent": {
            "type": "choice",
            "choice": "MAYBE",
            "probabilities": {"CHITCHAT": 0.3, "TRAVEL": 0.4,
                              "UNCERTAIN": 0.3},
            "confidence": 0.4,
        }},
        "usage": {"input_tokens": 4, "output_tokens": 1},
    }))

    response = _call("POST", "/chat",
                     body={"session_id": "s1", "message": "bonjour"})
    assert response.status_code == 503
    body = response.json()
    assert body["intent"] is None
    assert body["status"] == "unavailable"
    assert body["error"]["code"] == "intent_unavailable"
    assert body["router"]["status"] == "malformed"
    assert body["router"]["fallback"] is False
    assert body["usage"]["model_calls"] == 1
    assert session.calls == []
    assert llm.state["agent_calls"] == 0


def test_chat_chitchat_bypasses_tools(monkeypatch):
    session, llm = _wire_chat(monkeypatch, intent="CHITCHAT",
                              agent_responses=[model_message(content="Hello!")])
    response = _call("POST", "/chat",
                     body={"session_id": "s1", "message": "hi there"})
    body = response.json()
    assert body["intent"] == "CHITCHAT"
    assert body["reply"] == "Hello!"
    assert body["tool_chain"] == []
    assert session.calls == []


def test_memory_disabled_sends_only_current_turn(monkeypatch):
    agent = [model_message(content="first"), model_message(content="second")]
    session, llm = _wire_chat(monkeypatch, agent_responses=agent)

    _call("POST", "/chat", body={"session_id": "s1", "message": "one",
                                 "memory_enabled": False})
    _call("POST", "/chat", body={"session_id": "s1", "message": "two",
                                 "memory_enabled": False})

    agent_payloads = llm.state["payloads"]
    assert len(agent_payloads[-1]["messages"]) == 2  # system + current user only


def test_memory_enabled_accumulates_history(monkeypatch):
    agent = [model_message(content="first"), model_message(content="second")]
    session, llm = _wire_chat(monkeypatch, agent_responses=agent)

    _call("POST", "/chat", body={"session_id": "s2", "message": "one"})
    _call("POST", "/chat", body={"session_id": "s2", "message": "two"})

    agent_payloads = llm.state["payloads"]
    assert len(agent_payloads[-1]["messages"]) > 2


# ---------------------------------------------------------------------------
# Durable profile endpoints
# ---------------------------------------------------------------------------
def _memory_env(monkeypatch, tmp_path):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "profiles.db"))


def test_profile_endpoints_require_config(monkeypatch, tmp_path):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.delenv("MEMORY_DB_PATH", raising=False)
    token = make_token("user-9", SECRET)
    response = _call("GET", "/memory/profile", headers=auth_header(token))
    assert response.status_code == 503


def test_profile_endpoints_require_valid_token(monkeypatch, tmp_path):
    _memory_env(monkeypatch, tmp_path)
    assert _call("GET", "/memory/profile").status_code == 401
    response = _call("GET", "/memory/profile",
                     headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 401


def test_profile_roundtrip_update_conflict_and_delete(monkeypatch, tmp_path):
    _memory_env(monkeypatch, tmp_path)
    token = make_token("user-9", SECRET)
    headers = auth_header(token)

    created = _call("PUT", "/memory/profile",
                    body={"profile": {"preferred_categories": {"cat_coffee": 5}},
                          "expected_version": None},
                    headers=headers)
    assert created.status_code == 200
    assert created.json()["version"] == 1

    fetched = _call("GET", "/memory/profile", headers=headers)
    assert fetched.json()["profile"]["preferred_categories"] == {"cat_coffee": 5}

    conflict = _call("PUT", "/memory/profile",
                     body={"profile": {"tags": ["x"]}, "expected_version": 99},
                     headers=headers)
    assert conflict.status_code == 409

    invalid = _call("PUT", "/memory/profile",
                    body={"dietary": "vegan"}, headers=headers)
    assert invalid.status_code == 422

    deleted = _call("DELETE", "/memory/profile", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert _call("GET", "/memory/profile", headers=headers).json()["profile"] is None


def test_two_users_get_isolated_profiles(monkeypatch, tmp_path):
    _memory_env(monkeypatch, tmp_path)
    t1 = auth_header(make_token("user-a", SECRET))
    t2 = auth_header(make_token("user-b", SECRET))

    _call("PUT", "/memory/profile",
          body={"profile": {"tags": ["alpha"]}}, headers=t1)
    _call("PUT", "/memory/profile",
          body={"profile": {"tags": ["beta"]}}, headers=t2)

    assert _call("GET", "/memory/profile", headers=t1).json()["profile"]["tags"] == ["alpha"]
    assert _call("GET", "/memory/profile", headers=t2).json()["profile"]["tags"] == ["beta"]


# ---------------------------------------------------------------------------
# /generate_itinerary identity wiring
# ---------------------------------------------------------------------------
VALID_ITIN = {
    "session_id": "sess-http",
    "current_city": "Ho Chi Minh City",
    "travel_type": "self-explore",
    "num_travelers": 2,
    "start_date": "2026-01-01",
    "target_district": "District 1",
    "duration_days": 1,
    "budget_range": "500000-1500000 VND",
    "user_description": "quiet cafes",
}


def test_itinerary_http_uid_is_verified_subject_or_null(monkeypatch, tmp_path):
    captured = {}

    async def fake_run(request, tool_chain, *, uid, uid_source, profile_block):
        captured["uid"] = uid
        captured["uid_source"] = uid_source
        return {"status": "success", "reply": {"uid": uid}, "grounding": {},
                "tool_chain": []}

    monkeypatch.setattr(main, "_run_itinerary", fake_run)
    monkeypatch.setenv("JWT_SECRET", SECRET)

    _call("POST", "/generate_itinerary", body=dict(VALID_ITIN))
    assert captured["uid"] is None
    assert captured["uid_source"] == "anonymous"

    token = make_token("user-9", SECRET)
    _call("POST", "/generate_itinerary", body=dict(VALID_ITIN),
          headers=auth_header(token))
    assert captured["uid"] == "user-9"
    assert captured["uid_source"] == "verified_jwt_sub"


def test_itinerary_http_invalid_token_is_401(monkeypatch, tmp_path):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    response = _call("POST", "/generate_itinerary", body=dict(VALID_ITIN),
                     headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Repair regressions: malformed supplied authorization must fail closed
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path,body", [
    ("/chat", {"session_id": "s", "message": "hi"}),
    ("/generate_itinerary", VALID_ITIN),
    ("/memory/short/clear", {"session_id": "s"}),
])
def test_malformed_authorization_is_401_without_side_effects(
        monkeypatch, path, body):
    def boom(*args, **kwargs):
        raise AssertionError("must not be called for a malformed token")

    monkeypatch.setattr(main, "gemini_chat_completion", boom)
    monkeypatch.setattr(main, "open_mcp_session", boom)
    monkeypatch.setattr(main, "get_profile_store", boom)
    monkeypatch.setenv("JWT_SECRET", SECRET)

    for header in ("Basic invalid", "", "Bearer", "Bearer "):
        response = _call("POST", path, body=dict(body),
                         headers={"Authorization": header})
        assert response.status_code == 401


def test_invalid_supplied_token_never_downgraded_to_anonymous(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    called = {"model": 0}

    async def model(payload):
        called["model"] += 1
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(main, "gemini_chat_completion", model)
    response = _call("POST", "/chat",
                     body={"session_id": "s", "message": "hi"},
                     headers={"Authorization": "Token abc"})
    assert response.status_code == 401
    assert called["model"] == 0


# ---------------------------------------------------------------------------
# Repair regressions: profile store integrity
# ---------------------------------------------------------------------------
def test_put_profile_rejects_malformed_expected_version(monkeypatch, tmp_path):
    _memory_env(monkeypatch, tmp_path)
    headers = auth_header(make_token("u", SECRET))
    for bad in (True, -1, "1", 1.5):
        response = _call("PUT", "/memory/profile",
                         body={"profile": {"tags": ["x"]},
                               "expected_version": bad},
                         headers=headers)
        assert response.status_code == 422, bad


def test_store_error_is_sanitized(monkeypatch, tmp_path):
    _memory_env(monkeypatch, tmp_path)
    headers = auth_header(make_token("u", SECRET))

    class BoomStore:
        def get(self, subject):
            raise RuntimeError("secret db detail")

        def put(self, *args, **kwargs):
            raise RuntimeError("secret db detail")

        def delete(self, subject):
            raise RuntimeError("secret db detail")

    monkeypatch.setattr(main, "_memory_store_or_503", lambda: BoomStore())

    for method, body in (("GET", None),
                         ("PUT", {"profile": {"tags": ["x"]}}),
                         ("DELETE", None)):
        response = _call(method, "/memory/profile", body=body, headers=headers)
        assert response.status_code == 500
        assert "secret db detail" not in response.text


# ---------------------------------------------------------------------------
# Repair regressions: namespace isolation and bounded memory-disabled path
# ---------------------------------------------------------------------------
def test_two_subjects_same_session_are_isolated(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.delenv("MEMORY_DB_PATH", raising=False)
    session, llm = _wire_chat(monkeypatch, agent_responses=[
        model_message(content="A"), model_message(content="B")])

    _call("POST", "/chat", body={"session_id": "shared", "message": "one"},
          headers=auth_header(make_token("user-a", SECRET)))
    _call("POST", "/chat", body={"session_id": "shared", "message": "two"},
          headers=auth_header(make_token("user-b", SECRET)))

    agent_payloads = llm.state["payloads"]
    # user-b must not see user-a's turn (separate verified-subject namespaces).
    assert len(agent_payloads[-1]["messages"]) == 2


def test_memory_disabled_creates_no_sessions(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.delenv("MEMORY_DB_PATH", raising=False)
    session, llm = _wire_chat(monkeypatch, agent_responses=[
        model_message(content=str(i)) for i in range(20)])

    before = len(main.WORKING_MEMORY._entries)
    for i in range(20):
        _call("POST", "/chat",
              body={"session_id": f"unique-{i}", "message": "hi",
                    "memory_enabled": False})
    assert len(main.WORKING_MEMORY._entries) == before


def test_request_length_is_bounded(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    _wire_chat(monkeypatch, agent_responses=[model_message(content="hi")])
    too_long = _call("POST", "/chat",
                     body={"session_id": "s", "message": "x" * 9000})
    assert too_long.status_code == 422
    bad_session = _call("POST", "/chat",
                        body={"session_id": "y" * 300, "message": "hi"})
    assert bad_session.status_code == 422


# ---------------------------------------------------------------------------
# Repair regression: itinerary must not touch the global chat_history
# ---------------------------------------------------------------------------
def _load_grounding_helpers():
    grounding_dir = Path(__file__).resolve().parents[1] / "ai_grounding"
    if str(grounding_dir) not in sys.path:
        sys.path.insert(0, str(grounding_dir))
    import helpers_ai_grounding
    return helpers_ai_grounding


def test_itinerary_success_does_not_write_global_chat_history(monkeypatch):
    g = _load_grounding_helpers()
    before = len(payloads.chat_history)

    session = g.ScriptedMCPSession(g.default_handlers())
    monkeypatch.setattr(main, "open_mcp_session", g.session_seam(session))
    good = g.plan([("poi_a", "2026-01-01", "2026-01-01T09:00:00+07:00",
                    "2026-01-01T11:00:00+07:00", 1000.0)])
    monkeypatch.setattr(main, "gemini_chat_completion",
                        g.FakeLLM(g.llm_text(json.dumps(good))))

    result = asyncio.run(main.generate_itinerary_endpoint(g.make_request()))

    assert result["status"] == "success"
    assert result["reply"]["uid"] is None
    assert len(payloads.chat_history) == before
