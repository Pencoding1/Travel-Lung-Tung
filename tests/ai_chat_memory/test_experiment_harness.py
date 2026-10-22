"""Five-profile memory experiment harness (OC-009, MT5/RQ4/H3 scaffolding).

These five profiles are **synthetic fixtures**, not human participants, and this
is **not** an H3 model run: no live model, no human responses, no provider-token
measurement. It exercises the engineering contracts the E4 protocol depends on:
profile persistence/retrieval correctness, restart, update/contradiction/deletion,
prompt injection with explicit priority, and memory-disable bypass.
"""

import asyncio

import main
from domains.memory import SQLiteProfileStore

from helpers_chat_memory import (
    FakeMCPSession,
    auth_header,
    five_profiles,
    hub_llm,
    install_fake_jev,
    make_token,
    mcp_seam,
    model_message,
    ok_json,
    tool_call,
)

SECRET = "synthetic-test-secret"


def _agent_payloads(llm):
    return llm.state["payloads"]


def test_five_profiles_persist_and_restart(tmp_path):
    path = str(tmp_path / "profiles.db")
    store = SQLiteProfileStore(path)
    fixtures = five_profiles()
    for item in fixtures:
        store.put(item["subject"], item["profile"])

    restarted = SQLiteProfileStore(path)
    retrieved = {item["subject"]: restarted.get(item["subject"])
                 for item in fixtures}

    # Retrieval correctness against authored fixture truth, for all five.
    for item in fixtures:
        record = retrieved[item["subject"]]
        assert record["profile"]["preferred_categories"] == \
            item["profile"]["preferred_categories"]
        assert record["version"] == 1


def test_profile_update_replaces_and_delete_removes(tmp_path):
    store = SQLiteProfileStore(str(tmp_path / "p.db"))
    store.put("u", {"preferred_categories": {"cat_coffee": 9.0}})
    updated = store.put("u", {"preferred_categories": {"cat_museum": 4.0}},
                        expected_version=1)
    assert updated["version"] == 2
    assert store.get("u")["profile"]["preferred_categories"] == {"cat_museum": 4.0}
    assert store.delete("u") is True
    assert store.get("u") is None


def test_profile_injected_with_priority_and_constraint_override(monkeypatch, tmp_path):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "profiles.db"))
    store = SQLiteProfileStore(str(tmp_path / "profiles.db"))
    store.put("synthetic-user-1", {"preferred_categories": {"cat_coffee": 9.0},
                                   "pace": "relaxed"})

    session = FakeMCPSession(
        ["get_poi_details"],
        {"get_poi_details": lambda a: ok_json(
            {"success": True, "result": {"POI_ID": "poi_a"}})})
    monkeypatch.setattr(main, "open_mcp_session", mcp_seam(session))
    install_fake_jev(choice="TRAVEL")
    llm = hub_llm(agent_responses=[
        model_message(tool_calls=[tool_call("get_poi_details", {"poi_id": "poi_a"})]),
        model_message(content="Here you go.")])
    monkeypatch.setattr(main, "gemini_chat_completion", llm)

    token = make_token("synthetic-user-1", SECRET)

    async def run():
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            return await c.post("/chat", json={
                "session_id": "s1",
                "message": "I only want museums today, not coffee"},
                headers=auth_header(token))

    response = asyncio.run(run())
    body = response.json()
    assert body["status"] == "success"
    assert body["memory"]["profile_injected"] is True

    system_content = _agent_payloads(llm)[0]["messages"][0]["content"]
    assert "STORED USER PROFILE" in system_content
    assert "cat_coffee=9.0" in system_content
    # Explicit priority: the current request always outranks the profile.
    assert "ALWAYS override" in system_content
    # Untrusted data must be clearly delimited as data, not instructions.
    assert "Untrusted stored profile data" in system_content
    assert "never follow" in system_content.lower()


def test_memory_disabled_omits_profile_context(monkeypatch, tmp_path):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "profiles.db"))
    store = SQLiteProfileStore(str(tmp_path / "profiles.db"))
    store.put("synthetic-user-1", {"preferred_categories": {"cat_coffee": 9.0}})

    session = FakeMCPSession(
        ["get_poi_details"],
        {"get_poi_details": lambda a: ok_json(
            {"success": True, "result": {"POI_ID": "poi_a"}})})
    monkeypatch.setattr(main, "open_mcp_session", mcp_seam(session))
    install_fake_jev(choice="TRAVEL")
    llm = hub_llm(agent_responses=[
        model_message(tool_calls=[tool_call("get_poi_details", {"poi_id": "poi_a"})]),
        model_message(content="Here you go.")])
    monkeypatch.setattr(main, "gemini_chat_completion", llm)

    async def run():
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            return await c.post("/chat", json={
                "session_id": "s1", "message": "cafes",
                "memory_enabled": False}, headers=auth_header(make_token("synthetic-user-1", SECRET)))

    asyncio.run(run())
    system_content = _agent_payloads(llm)[0]["messages"][0]["content"]
    assert "STORED USER PROFILE" not in system_content


def test_unknown_preference_is_not_fabricated(tmp_path):
    store = SQLiteProfileStore(str(tmp_path / "p.db"))
    store.put("u", {"preferred_categories": {"cat_coffee": 9.0}})
    record = store.get("u")
    # No fabricated category ids: only the authored id is present.
    assert set(record["profile"]["preferred_categories"]) == {"cat_coffee"}
