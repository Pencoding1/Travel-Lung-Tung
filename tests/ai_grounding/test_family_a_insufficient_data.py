"""Adversarial family A: empty / insufficient candidate data.

The endpoint must not call the language model and must return an explicit
``insufficient_data`` structured error instead of inventing places.
"""

import asyncio

import main
from domains import grounding

from helpers_ai_grounding import (
    FakeLLM,
    ScriptedMCPSession,
    default_handlers,
    llm_text,
    make_request,
    ok_json,
    session_seam,
)


def _run(monkeypatch, session, llm):
    monkeypatch.setattr(main, "open_mcp_session", session_seam(session))
    monkeypatch.setattr(main, "gemini_chat_completion", llm)
    return asyncio.run(main.generate_itinerary_endpoint(make_request()))


def test_empty_candidate_list_skips_llm_and_reports_insufficient_data(monkeypatch):
    handlers = default_handlers(candidates=[])
    session = ScriptedMCPSession(handlers)
    llm = FakeLLM(llm_text("should never be used"))

    result = _run(monkeypatch, session, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.INSUFFICIENT_DATA
    assert llm.calls == []
    assert all("status" in step for step in result["tool_chain"])
    # exploration steps are observable even when empty
    explore_steps = [s for s in result["tool_chain"] if s["tool"].startswith("explore_pois")]
    assert explore_steps and explore_steps[0]["summary"] == "found 0 candidates"


def test_all_enrichment_failures_skip_llm(monkeypatch):
    handlers = default_handlers(candidates=["poi_a", "poi_b"], enrichments={})
    session = ScriptedMCPSession(handlers)
    llm = FakeLLM(llm_text("should never be used"))

    result = _run(monkeypatch, session, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.INSUFFICIENT_DATA
    assert llm.calls == []
    detail_steps = [s for s in result["tool_chain"] if s["tool"] == "get_poi_details"]
    assert len(detail_steps) == 2
    assert all(step["status"] == "failed" for step in detail_steps)


def test_enrichment_iserror_is_surfaced_and_skips_llm(monkeypatch):
    from helpers_ai_grounding import ToolResult

    handlers = default_handlers(candidates=["poi_a"])
    handlers["get_poi_details"] = lambda args: ToolResult("boom", is_error=True)
    session = ScriptedMCPSession(handlers)
    llm = FakeLLM(llm_text("should never be used"))

    result = _run(monkeypatch, session, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.INSUFFICIENT_DATA
    assert llm.calls == []


def test_enrichment_non_dict_content_is_surfaced(monkeypatch):
    from helpers_ai_grounding import ToolResult

    handlers = default_handlers(candidates=["poi_a"])
    handlers["get_poi_details"] = lambda args: ToolResult(content=["not-a-text-item"])
    session = ScriptedMCPSession(handlers)
    llm = FakeLLM(llm_text("should never be used"))

    result = _run(monkeypatch, session, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.INSUFFICIENT_DATA
    assert llm.calls == []


def test_category_discovery_failure_skips_llm(monkeypatch):
    handlers = default_handlers(categories=[])
    handlers["get_available_categories"] = lambda args: ok_json(
        {"success": True, "message": "No categories currently exist in the database."})
    session = ScriptedMCPSession(handlers)
    llm = FakeLLM(llm_text("should never be used"))

    result = _run(monkeypatch, session, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.INSUFFICIENT_DATA
    assert llm.calls == []
