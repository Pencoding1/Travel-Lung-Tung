"""OC-015 — namespace collision regression + multi-turn tool metadata chaining.

Two independent defects are covered here:

1. The working-memory namespace key was ``f"{owner}:{session_id}"``, which
   aliases distinct ``(scope, subject, session)`` tuples: ``("a:b", "c")`` and
   ``("a", "b:c")`` both derive ``"a:b:c"``, and the anonymous scope (no bearer)
   aliases any verified subject whose literal value is ``"anonymous"``. These
   tests drive the **real** ``/chat`` and ``/memory/short/clear`` routes with
   synthetic signed JWTs, use **distinct messages**, and inspect the **fake model
   contexts** (not merely key strings) to prove users cannot read or clear each
   other's working memory.

2. The ReAct loop must preserve the *actual-shaped* tool metadata in the next
   model call and must not treat metadata (resolver matches / category lists) as
   POI evidence. A metadata-only final answer stays ``insufficient_data``.

All tokens use a synthetic secret of at least 32 bytes. No live model, MCP,
database or network call is made; this is in-process mocked contract evidence.
"""

import asyncio
import json

import main
import pytest
from domains import chat_agent, memory_auth
from domains.memory_auth import AuthError
from httpx import ASGITransport, AsyncClient

from helpers_chat_memory import (
    FakeMCPSession,
    ScriptedTools,
    auth_header,
    hub_llm,
    install_fake_jev,
    make_token,
    mcp_seam,
    model_message,
    ok_json,
    tool_call,
)

# >= 32 bytes so HS256 never emits an insecure-key warning.
SECRET = "oc015-namespace-synthetic-secret-0123456789"


def _call(method, path, body=None, headers=None):
    async def _run():
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, json=body, headers=headers)

    return asyncio.run(_run())


def _wire_chat(monkeypatch, agent_responses):
    session = FakeMCPSession(
        ("get_poi_details",),
        {"get_poi_details": lambda a: ok_json(
            {"success": True, "result": {"POI_ID": "poi_a", "POI_Name": "A"}})})
    monkeypatch.setattr(main, "open_mcp_session", mcp_seam(session))
    install_fake_jev(choice="TRAVEL")
    llm = hub_llm(agent_responses=agent_responses)
    monkeypatch.setattr(main, "gemini_chat_completion", llm)
    return session, llm


def _agent_messages(llm):
    """Return the generation-model messages (Jev is never on this seam)."""
    return [p["messages"] for p in llm.state["payloads"]]


def _joined(messages):
    return "\n".join(str(m.get("content") or "") for m in messages)


# ---------------------------------------------------------------------------
# Key-derivation contract (documents the counterexample; the integration tests
# below are the real proof).
# ---------------------------------------------------------------------------
def test_memory_key_encodes_unambiguous_structured_tuple():
    # Colon reassociation must not collide.
    assert main._memory_key("a:b", "c") != main._memory_key("a", "b:c")
    # The anonymous scope must differ from a verified subject "anonymous".
    assert main._memory_key(None, "session") != main._memory_key("anonymous", "session")
    # Deterministic for the same tuple.
    assert main._memory_key("u", "s") == main._memory_key("u", "s")
    # Bounded regardless of identifier length (never hits WorkingMemory's bound).
    key = main._memory_key("x" * memory_auth.MAX_SUBJECT_CHARS, "y" * 200)
    assert len(key) <= 200


# ---------------------------------------------------------------------------
# Colon-colliding subject/session pairs, over the real endpoints.
# ---------------------------------------------------------------------------
def test_colon_colliding_pairs_cannot_read_or_clear_each_other(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.delenv("MEMORY_DB_PATH", raising=False)
    _session, llm = _wire_chat(monkeypatch, [
        model_message(content="reply-A"),
        model_message(content="reply-B"),
        model_message(content="reply-B2"),
    ])

    token_a = auth_header(make_token("a:b", SECRET))   # subject "a:b", session "c"
    token_b = auth_header(make_token("a", SECRET))     # subject "a",   session "b:c"

    # Both tuples used to derive the single key "a:b:c".
    _call("POST", "/chat",
          body={"session_id": "c", "message": "ALPHA_FROM_A"}, headers=token_a)
    _call("POST", "/chat",
          body={"session_id": "b:c", "message": "BETA_FROM_B"}, headers=token_b)

    contexts = _agent_messages(llm)
    assert len(contexts[0]) == 2
    # B's first turn must NOT see A's history (read isolation).
    assert len(contexts[1]) == 2
    assert "ALPHA_FROM_A" not in _joined(contexts[1])

    # Clearing A's namespace must not clear B's (clear isolation).
    cleared = _call("POST", "/memory/short/clear",
                    body={"session_id": "c"}, headers=token_a)
    assert cleared.status_code == 200
    assert cleared.json() == {"cleared": True, "scope": "verified_user"}

    _call("POST", "/chat",
          body={"session_id": "b:c", "message": "BETA2"}, headers=token_b)
    b_after = _joined(_agent_messages(llm)[-1])
    assert "BETA_FROM_B" in b_after          # B's history survived A's clear
    assert "ALPHA_FROM_A" not in b_after


# ---------------------------------------------------------------------------
# Anonymous scope vs a verified subject whose literal value is "anonymous".
# ---------------------------------------------------------------------------
def test_anonymous_scope_isolated_from_literal_anonymous_subject(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.delenv("MEMORY_DB_PATH", raising=False)
    _session, llm = _wire_chat(monkeypatch, [
        model_message(content="anon-1"),
        model_message(content="user-1"),
        model_message(content="user-2"),
        model_message(content="anon-2"),
        model_message(content="anon-3"),
    ])

    session_id = "oc015-anon-vs-literal"
    token = auth_header(make_token("anonymous", SECRET))

    # 1) Anonymous (no Authorization header at all).
    _call("POST", "/chat",
          body={"session_id": session_id, "message": "ANON_ONLY"})
    # 2) Verified subject literally "anonymous" — distinct scope.
    _call("POST", "/chat",
          body={"session_id": session_id, "message": "USER_LITERAL_ANON"},
          headers=token)

    contexts = _agent_messages(llm)
    assert len(contexts[0]) == 2
    assert len(contexts[1]) == 2                        # no ANON_ONLY leaked
    assert "ANON_ONLY" not in _joined(contexts[1])

    # Clearing the anonymous namespace must not clear the verified user's.
    cleared = _call("POST", "/memory/short/clear", body={"session_id": session_id})
    assert cleared.json() == {"cleared": True, "scope": "anonymous_local_only"}

    _call("POST", "/chat",
          body={"session_id": session_id, "message": "USER2"}, headers=token)
    user_after = _joined(_agent_messages(llm)[-1])
    assert "USER_LITERAL_ANON" in user_after            # user history survived
    assert "ANON_ONLY" not in user_after

    _call("POST", "/chat",
          body={"session_id": session_id, "message": "ANON2"})
    anon_after = _joined(_agent_messages(llm)[-1])
    assert "ANON_ONLY" not in anon_after                # anon scope was cleared
    assert "USER_LITERAL_ANON" not in anon_after        # no user leakage

    # Clearing the verified user must not clear the anonymous namespace.
    user_cleared = _call("POST", "/memory/short/clear",
                         body={"session_id": session_id}, headers=token)
    assert user_cleared.json() == {"cleared": True, "scope": "verified_user"}

    _call("POST", "/chat",
          body={"session_id": session_id, "message": "ANON3"})
    anon_final = _joined(_agent_messages(llm)[-1])
    assert "ANON2" in anon_final                        # anon survived user clear
    assert "USER_LITERAL_ANON" not in anon_final


# ---------------------------------------------------------------------------
# Overlong subject -> explicit structured error, never an uncaught ValueError.
# ---------------------------------------------------------------------------
def test_overlong_subject_is_rejected_explicitly(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)

    def boom(*args, **kwargs):
        raise AssertionError("must fail closed before any model/tool work")

    monkeypatch.setattr(main, "gemini_chat_completion", boom)
    monkeypatch.setattr(main, "open_mcp_session", boom)

    token = auth_header(make_token("s" * (memory_auth.MAX_SUBJECT_CHARS + 1), SECRET))

    chat = _call("POST", "/chat",
                 body={"session_id": "s", "message": "hi"}, headers=token)
    assert chat.status_code == 401
    assert chat.json()["detail"]["code"] == "subject_too_long"

    clear = _call("POST", "/memory/short/clear",
                  body={"session_id": "s"}, headers=token)
    assert clear.status_code == 401
    assert clear.json()["detail"]["code"] == "subject_too_long"


def test_subject_length_boundary_is_enforced_at_auth_layer():
    ok_subject = "s" * memory_auth.MAX_SUBJECT_CHARS
    assert memory_auth.decode_subject(make_token(ok_subject, SECRET), SECRET) == ok_subject

    with pytest.raises(AuthError) as exc:
        memory_auth.decode_subject(
            make_token(ok_subject + "s", SECRET), SECRET)
    assert exc.value.status_code == 401
    assert exc.value.code == "subject_too_long"


# ---------------------------------------------------------------------------
# Functional ReAct chain: metadata survives to the next model call and is not
# counted as POI evidence.
# ---------------------------------------------------------------------------
RESOLVE_PAYLOAD = {"success": True, "matches": [
    {"id": "quan_1", "name": "District 1", "type": "District"}]}
CATEGORY_PAYLOAD = {"success": True, "categories": [
    {"id": "cat_coffee", "name": "Cafe"}]}
EXPLORE_PAYLOAD = {"success": True, "count": 1, "results": [
    {"id": "poi_1", "POI_ID": "poi_1", "POI_Name": "Cafe One"}]}
DETAILS_PAYLOAD = {"success": True, "result": {
    "POI_ID": "poi_1", "POI_Name": "Cafe One"}}


class _ChainedModel:
    """A model that picks each next call's args from the previous tool result.

    It reads the *actual* tool-result message text produced by the loop (the
    resolver's ``matches[0].id`` and the category's id), proving the metadata is
    preserved across turns rather than reconstructed from the test.
    """

    def __init__(self):
        self.calls = []
        self.district_id = None

    async def __call__(self, messages, tools):
        self.calls.append(list(messages))
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        if not tool_msgs:
            return model_message(tool_calls=[
                tool_call("resolve_geographic_id", {"keyword": "District 1"}, "c1")])
        last = tool_msgs[-1]
        payload = json.loads(last["content"])
        if last["name"] == "resolve_geographic_id":
            self.district_id = payload["matches"][0]["id"]
            return model_message(tool_calls=[
                tool_call("get_available_categories", {}, "c2")])
        if last["name"] == "get_available_categories":
            category_id = payload["categories"][0]["id"]
            return model_message(tool_calls=[tool_call("explore_pois", {
                "city_id": "city_1",
                "district_id": self.district_id,
                "category_id": category_id,
            }, "c3")])
        if last["name"] == "explore_pois":
            poi_id = payload["results"][0]["id"]
            return model_message(tool_calls=[
                tool_call("get_poi_details", {"poi_id": poi_id}, "c4")])
        return model_message(content="The best coffee is Cafe One.")


def test_react_chain_preserves_metadata_and_grounds_on_poi_only():
    handlers = {
        "resolve_geographic_id": lambda a: ok_json(RESOLVE_PAYLOAD),
        "get_available_categories": lambda a: ok_json(CATEGORY_PAYLOAD),
        "explore_pois": lambda a: ok_json(EXPLORE_PAYLOAD),
        "get_poi_details": lambda a: ok_json(DETAILS_PAYLOAD),
    }
    messages = [{"role": "system", "content": "sys"},
                {"role": "user", "content": "coffee in District 1"}]
    model = _ChainedModel()
    tools_obj = ScriptedTools(handlers)

    result = asyncio.run(chat_agent.run_agent_loop(
        messages=messages,
        tool_specs=[],
        known_tool_names=set(handlers),
        call_model=model,
        call_tool=tools_obj,
    ))

    assert result["status"] == chat_agent.STATUS_SUCCESS
    assert result["reply"] == "The best coffee is Cafe One."
    assert result["grounding_status"] == chat_agent.GROUNDING_UNVERIFIED_FREE_TEXT
    # Only the real POI is evidence; resolver/category metadata is not.
    assert result["source_evidence_ids"] == ["poi_1"]

    # Metadata reached the next model call (turn 3 saw the resolver's id).
    third_turn_text = _joined(model.calls[2])
    assert "quan_1" in third_turn_text
    # Chaining used actual response values, not constants.
    assert [c["tool"] for c in tools_obj.calls] == [
        "resolve_geographic_id", "get_available_categories",
        "explore_pois", "get_poi_details"]
    assert tools_obj.calls[2]["args"]["district_id"] == "quan_1"
    assert tools_obj.calls[2]["args"]["category_id"] == "cat_coffee"
    assert tools_obj.calls[3]["args"]["poi_id"] == "poi_1"

    # Metadata-only results are traced but never counted as POI evidence.
    summaries = [e["summary"] for e in result["tool_chain"]]
    assert summaries == ["no_poi_evidence", "no_poi_evidence", "ok", "ok"]
    assert "quan_1" not in result["source_evidence_ids"]
    assert "cat_coffee" not in result["source_evidence_ids"]


def test_metadata_only_final_answer_is_insufficient_data():
    class _MetadataOnlyModel:
        async def __call__(self, messages, tools):
            tool_msgs = [m for m in messages if m.get("role") == "tool"]
            if not tool_msgs:
                return model_message(tool_calls=[
                    tool_call("resolve_geographic_id", {"keyword": "District 1"}, "c1")])
            return model_message(content="District 1 has the best coffee!")

    handlers = {"resolve_geographic_id": lambda a: ok_json(RESOLVE_PAYLOAD)}
    messages = [{"role": "system", "content": "sys"},
                {"role": "user", "content": "coffee in District 1"}]
    result = asyncio.run(chat_agent.run_agent_loop(
        messages=messages,
        tool_specs=[],
        known_tool_names=set(handlers),
        call_model=_MetadataOnlyModel(),
        call_tool=ScriptedTools(handlers),
    ))

    assert result["status"] == chat_agent.STATUS_INSUFFICIENT
    assert result["reply"] == chat_agent.INSUFFICIENT_DATA_MESSAGE
    assert result["source_evidence_ids"] == []
    assert result["tool_chain"][0]["summary"] == "no_poi_evidence"
