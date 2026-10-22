"""Shared fakes/utilities for the OC-016 planner-integration tests.

Reuses the OC-005 grounding fakes (scripted MCP session, fake Gemini) via
``helpers_ai_grounding`` and adds a configurable ``get_itinerary_route`` fake.
All evidence is in-process and synthetic; no live collaborator is contacted.
"""

import asyncio
import json

import main
from helpers_ai_grounding import (
    FakeLLM,
    ScriptedMCPSession,
    ToolResult,
    default_handlers,
    evidence,
    llm_text,
    make_request,
    ok_json,
    plan,
    session_seam,
)

DEFAULT_BODY = {
    "session_id": "sess-plan",
    "current_city": "Ho Chi Minh City",
    "travel_type": "self-explore",
    "num_travelers": 2,
    "start_date": "2026-01-01",
    "target_district": "District 1",
    "duration_days": 1,
    "budget_range": "500000-1500000 VND",
    "user_description": "quiet cafes",
}


def route_handler(duration_minutes=10.0, distance_km=1.0, fail_pairs=(),
                  provider_error=False, ordered_override=None, echo_ids=True):
    """Build a ``get_itinerary_route`` handler.

    ``fail_pairs`` is a set of directed ``(a, b)`` tuples to fail with
    ``success=false``. ``provider_error=True`` fails every call as a provider
    error. ``ordered_override`` forces a wrong ordered-id echo to exercise the
    exact-id validation.
    """
    fail_pairs = {tuple(pair) for pair in fail_pairs}

    def handler(args):
        ids = args.get("ordered_poi_ids") or []
        if provider_error:
            return ok_json({"success": False, "code": "route_failed",
                            "detail": "provider down"})
        if tuple(ids) in fail_pairs:
            return ok_json({"success": False, "code": "no_route",
                            "detail": "no route between stops"})
        returned = ordered_override if ordered_override is not None else ids
        return ok_json({
            "success": True,
            "distance_km": distance_km,
            "time_minutes": duration_minutes,
            "stops_mapped": len(ids),
            "stops": ([{"id": pid} for pid in returned] if echo_ids else []),
            "turn_by_turn": [],
        })

    return handler


def run_endpoint(monkeypatch, handlers, llm, request=None):
    session = ScriptedMCPSession(handlers)
    monkeypatch.setattr(main, "open_mcp_session", session_seam(session))
    monkeypatch.setattr(main, "gemini_chat_completion", llm)
    result = asyncio.run(main.generate_itinerary_endpoint(request or make_request()))
    return result, session


def run_http(monkeypatch, handlers, llm, body, headers=None):
    session = ScriptedMCPSession(handlers)
    monkeypatch.setattr(main, "open_mcp_session", session_seam(session))
    monkeypatch.setattr(main, "gemini_chat_completion", llm)

    async def _call():
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/generate_itinerary", json=body, headers=headers)

    return asyncio.run(_call())


def good_llm(plan_obj):
    return FakeLLM(llm_text(json.dumps(plan_obj)))


def stop_plan(pois, day="2026-01-01", start_hour=9, visit_hours=1):
    """Build a model plan with sequential hourly stops (synthetic)."""
    stops = []
    hour = start_hour
    for pid, budget in pois:
        visit = f"{day}T{hour:02d}:00:00+07:00"
        end = f"{day}T{hour + visit_hours:02d}:00:00+07:00"
        stops.append((pid, day, visit, end, budget))
        hour += visit_hours
    return plan(stops)
