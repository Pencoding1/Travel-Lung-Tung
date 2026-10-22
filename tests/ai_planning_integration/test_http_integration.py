"""Real in-process HTTP contract tests over the FastAPI ASGI app (OC-016).

The MCP session and Gemini seam are faked; routing, pydantic request parsing,
auth and the JSON response layer are real. No network is used.
"""

import time

import jwt
from domains import grounding
from helpers_ai_grounding import default_handlers
from helpers_planning_integration import (
    DEFAULT_BODY,
    good_llm,
    run_http,
    stop_plan,
)

SECRET = "synthetic-test-secret-0123456789abcdef"


def test_http_success_delivers_planning_block(monkeypatch):
    handlers = default_handlers()
    response = run_http(monkeypatch, handlers,
                        good_llm(stop_plan([("poi_a", 1000.0)])), DEFAULT_BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["reply"]["id"].startswith("itin_")
    assert body["grounding"]["scope_verification"] == "verified"
    planning = body["planning"]
    assert planning["validator_status"] in ("feasible", "unverifiable", "partial")
    assert "initial_proposal" in planning
    assert "repaired_schedule" in planning
    assert planning["cost"]["status"] == "unknown"
    assert planning["cost"]["menu_offers_repurposed"] is False
    assert planning["cost"]["model_budget_promoted_to_source_cost"] is False


def test_http_verified_uid_is_preserved(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    token = jwt.encode({"sub": "user-123", "exp": int(time.time()) + 3600},
                       SECRET, algorithm="HS256")
    handlers = default_handlers()
    response = run_http(monkeypatch, handlers,
                        good_llm(stop_plan([("poi_a", 1000.0)])), DEFAULT_BODY,
                        headers={"Authorization": f"Bearer {token}"})

    body = response.json()
    assert body["status"] == "success"
    assert body["reply"]["uid"] == "user-123"
    assert body["reply"]["uid_source"] == "verified_jwt_sub"


def test_http_invalid_duration_is_422(monkeypatch):
    handlers = default_handlers()
    response = run_http(monkeypatch, handlers, good_llm(stop_plan([("poi_a", 1.0)])),
                        dict(DEFAULT_BODY, duration_days=0))
    assert response.status_code == 422


def test_http_scope_conflict_fails_closed(monkeypatch):
    from helpers_ai_grounding import evidence
    enrich = {"poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC", admin=None)}
    handlers = default_handlers(candidates=["poi_a"], enrichments=enrich)
    response = run_http(monkeypatch, handlers, good_llm(stop_plan([("poi_a", 1.0)])),
                        DEFAULT_BODY)
    body = response.json()
    assert response.status_code == 200
    assert body["error"]["code"] == grounding.SCOPE_UNVERIFIED
