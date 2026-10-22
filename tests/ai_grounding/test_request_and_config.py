"""Request validation, configured-model and prompt-path contract tests."""

import asyncio
import json
from pathlib import Path

import main
from domains import grounding

from helpers_ai_grounding import (
    FakeLLM,
    ScriptedMCPSession,
    default_handlers,
    llm_text,
    make_request,
    plan,
    session_seam,
)


def _run(monkeypatch, request, handlers=None, llm=None):
    session = ScriptedMCPSession(handlers or {})
    llm = llm or FakeLLM(llm_text("unused"))
    monkeypatch.setattr(main, "open_mcp_session", session_seam(session))
    monkeypatch.setattr(main, "gemini_chat_completion", llm)
    result = asyncio.run(main.generate_itinerary_endpoint(request))
    return result, session, llm


def _invalid(monkeypatch, field, value):
    request = make_request()
    setattr(request, field, value)
    result, session, llm = _run(monkeypatch, request)
    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.INVALID_REQUEST
    assert any(d["field"] == field for d in result["error"]["details"])
    assert session.calls == []
    assert llm.calls == []


def test_duration_days_below_range(monkeypatch):
    _invalid(monkeypatch, "duration_days", 0)


def test_duration_days_above_range(monkeypatch):
    _invalid(monkeypatch, "duration_days", 15)


def test_travelers_non_positive(monkeypatch):
    _invalid(monkeypatch, "num_travelers", 0)


def test_travelers_above_bound(monkeypatch):
    _invalid(monkeypatch, "num_travelers", 51)


def test_invalid_iso_start_date(monkeypatch):
    _invalid(monkeypatch, "start_date", "2026-13-40")


def test_blank_city_rejected(monkeypatch):
    _invalid(monkeypatch, "current_city", "   ")


def test_blank_district_rejected(monkeypatch):
    _invalid(monkeypatch, "target_district", "")


def test_duration_bounds_are_inclusive(monkeypatch):
    for days in (1, 14):
        request = make_request(duration_days=days)
        good = plan([("poi_a", "2026-01-01", "2026-01-01T09:00:00+07:00",
                      "2026-01-01T11:00:00+07:00", 1000.0)])
        result, _session, _llm = _run(
            monkeypatch, request, default_handlers(),
            FakeLLM(llm_text(json.dumps(good))))
        assert result["status"] == "success"


def test_prompt_path_is_relative_to_module_file():
    assert main.PROMPT_PATH.is_absolute()
    assert main.PROMPT_PATH == Path(main.__file__).resolve().parent / "prompt.json"
    assert main.PROMPT_PATH.exists()
    assert "Travel Lung Tung" in main.SYSTEM_PROMPT


def test_synthesis_uses_configured_model(monkeypatch):
    good = plan([("poi_a", "2026-01-01", "2026-01-01T09:00:00+07:00",
                  "2026-01-01T11:00:00+07:00", 1000.0)])
    llm = FakeLLM(llm_text(json.dumps(good)))
    request = make_request()

    result, _session, llm = _run(monkeypatch, request, default_handlers(), llm)

    assert result["status"] == "success"
    assert llm.calls[0]["model"] == main.GEMINI_MODEL
    synthesis_step = result["tool_chain"][-1]
    assert synthesis_step["tool"] == "Gemini Synthesis"
    assert synthesis_step["args"]["model"] == main.GEMINI_MODEL
