"""In-process HTTP contract tests over the FastAPI ASGI app (no network).

The MCP session and Gemini call are still faked through the module seams; only
the HTTP request/response layer (routing, pydantic parsing, JSON body) is real.
"""

import asyncio
import json

import main
from domains import grounding
from httpx import ASGITransport, AsyncClient

from helpers_ai_grounding import (
    FakeLLM,
    ScriptedMCPSession,
    default_handlers,
    evidence,
    llm_text,
    plan,
    session_seam,
)

VALID_BODY = {
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


def _post(monkeypatch, handlers, llm, body):
    session = ScriptedMCPSession(handlers)
    monkeypatch.setattr(main, "open_mcp_session", session_seam(session))
    monkeypatch.setattr(main, "gemini_chat_completion", llm)

    async def _call():
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/generate_itinerary", json=body)

    return asyncio.run(_call())


def test_http_valid_grounded_plan(monkeypatch):
    good = plan([("poi_a", "2026-01-01", "2026-01-01T09:00:00+07:00",
                  "2026-01-01T11:00:00+07:00", 55000.0)])
    response = _post(monkeypatch, default_handlers(),
                     FakeLLM(llm_text(json.dumps(good))), VALID_BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["reply"]["id"].startswith("itin_")
    assert body["reply"]["stops"][0]["poi"]["name"] == "Verified Cafe A"
    assert body["grounding"]["scope_verification"] == "verified"


def test_http_invalid_duration_is_rejected(monkeypatch):
    body = dict(VALID_BODY, duration_days=0)
    response = _post(monkeypatch, default_handlers(),
                     FakeLLM(llm_text("unused")), body)

    assert response.status_code == 422


def test_http_empty_candidates_fail_closed(monkeypatch):
    body = dict(VALID_BODY)
    response = _post(monkeypatch, default_handlers(candidates=[]),
                     FakeLLM(llm_text("unused")), body)

    assert response.status_code == 200
    assert response.json()["error"]["code"] == grounding.INSUFFICIENT_DATA


def test_http_scope_unverified_fails_closed(monkeypatch):
    enrichments = {"poi_a": evidence("poi_a", "A",
                                     "1 Le Loi, Quan 1, Ho Chi Minh City",
                                     admin=None)}
    response = _post(monkeypatch,
                     default_handlers(candidates=["poi_a"], enrichments=enrichments),
                     FakeLLM(llm_text("unused")), body=dict(VALID_BODY))

    assert response.status_code == 200
    assert response.json()["error"]["code"] == grounding.SCOPE_UNVERIFIED
