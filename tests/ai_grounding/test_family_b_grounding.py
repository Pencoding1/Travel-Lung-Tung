"""Adversarial family B: unsupported POI details and invalid plan structures.

The model may only choose POI ids that came back from ``get_poi_details``; every
factual field of a stop is reconstructed from that evidence. Unknown ids,
duplicated stops, start/end mismatches, malformed JSON and invalid timestamps
must fail explicitly rather than reach the caller.
"""

import asyncio
import json

import main
from domains import grounding

from helpers_ai_grounding import (
    FakeLLM,
    ScriptedMCPSession,
    default_handlers,
    evidence,
    llm_text,
    make_request,
    plan,
    session_seam,
)


def _run(monkeypatch, session, llm, request=None):
    monkeypatch.setattr(main, "open_mcp_session", session_seam(session))
    monkeypatch.setattr(main, "gemini_chat_completion", llm)
    return asyncio.run(main.generate_itinerary_endpoint(request or make_request()))


def _session_with_plan(plan_obj, **handler_kwargs):
    handlers = default_handlers(**handler_kwargs)
    return ScriptedMCPSession(handlers), handlers


def test_unknown_poi_id_is_rejected(monkeypatch):
    session, _ = _session_with_plan(None)
    bad = plan([("poi_ghost", "2026-01-01", "2026-01-01T09:00:00+07:00",
                 "2026-01-01T11:00:00+07:00", 100.0)])
    llm = FakeLLM(llm_text(json.dumps(bad)))

    result = _run(monkeypatch, session, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.UNKNOWN_POI
    assert len(llm.calls) == 1


def test_invented_factual_fields_are_reconstructed_from_evidence(monkeypatch):
    good = plan([("poi_a", "2026-01-01", "2026-01-01T09:00:00+07:00",
                  "2026-01-01T11:00:00+07:00", 55000.0)])
    # Inject hallucinated / unsupported attributes into the model plan.
    good["stops"][0]["poi"].update({
        "name": "HALLUCINATED NAME",
        "latitude": 0.0,
        "longitude": 0.0,
        "operation_time": "Open 24/7",
        "address": {"street_name": "Fake St"},
        "rating": {"google_maps": 5.0, "tripadvisor": 5.0},
    })
    good["stops"][0]["description"] = "Award-winning world's best coffee."

    session, handlers = _session_with_plan(None)
    llm = FakeLLM(llm_text(json.dumps(good)))

    result = _run(monkeypatch, session, llm)

    assert result["status"] == "success"
    stop = result["reply"]["stops"][0]
    poi = stop["poi"]
    verified = handlers  # readability
    assert poi["id"] == "poi_a"
    assert poi["name"] == "Verified Cafe A"
    assert poi["latitude"] == 10.77
    assert poi["longitude"] == 106.7
    assert poi["operation_time"] is None
    assert poi["rating"] is None
    assert poi["address"]["street_name"] == "12 Le Loi, Quan 1, Ho Chi Minh City"
    assert stop["description"] == grounding.NEUTRAL_DESCRIPTION
    assert stop["description_grounded"] is False
    assert stop["budget_is_estimate"] is True


def test_fallback_rating_zero_is_not_promoted_to_verified(monkeypatch):
    good = plan([("poi_a", "2026-01-01", "2026-01-01T09:00:00+07:00",
                  "2026-01-01T11:00:00+07:00", 1000.0)])
    session, _ = _session_with_plan(None)  # evidence rating defaults to 0.0
    llm = FakeLLM(llm_text(json.dumps(good)))

    result = _run(monkeypatch, session, llm)

    assert result["status"] == "success"
    assert result["reply"]["stops"][0]["poi"]["rating"] is None
    assert any("rating" in item for item in result["grounding"]["missing_data"])


def test_malformed_model_json_fails(monkeypatch):
    session, _ = _session_with_plan(None)
    llm = FakeLLM(llm_text("this is not json at all"))

    result = _run(monkeypatch, session, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.LLM_ERROR
    assert result["tool_chain"][-1]["status"] == "failed"


def test_naive_timestamp_fails(monkeypatch):
    bad = plan([("poi_a", "2026-01-01", "2026-01-01T09:00:00",
                 "2026-01-01T11:00:00", 1000.0)])
    session, _ = _session_with_plan(None)
    llm = FakeLLM(llm_text(json.dumps(bad)))

    result = _run(monkeypatch, session, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.TIME_ORDER_INVALID


def test_timestamp_overlap_fails(monkeypatch):
    enrichments = {
        "poi_a": evidence("poi_a", "A", "1 X, Quan 1, Ho Chi Minh City"),
        "poi_b": evidence("poi_b", "B", "2 Y, Quan 1, Ho Chi Minh City"),
    }
    session, _ = _session_with_plan(
        None, candidates=["poi_a", "poi_b"], enrichments=enrichments)
    overlapping = plan([
        ("poi_a", "2026-01-01", "2026-01-01T09:00:00+07:00",
         "2026-01-01T12:00:00+07:00", 1000.0),
        ("poi_b", "2026-01-01", "2026-01-01T11:00:00+07:00",
         "2026-01-01T13:00:00+07:00", 1000.0),
    ])
    llm = FakeLLM(llm_text(json.dumps(overlapping)))

    result = _run(monkeypatch, session, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.TIME_ORDER_INVALID


def test_start_end_mismatch_fails(monkeypatch):
    bad = plan([("poi_a", "2026-01-01", "2026-01-01T09:00:00+07:00",
                 "2026-01-01T11:00:00+07:00", 1000.0)],
               start_poi_id="poi_a", end_poi_id="poi_other")
    session, _ = _session_with_plan(None)
    llm = FakeLLM(llm_text(json.dumps(bad)))

    result = _run(monkeypatch, session, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.START_END_MISMATCH


def test_duplicate_stops_fail(monkeypatch):
    dup = plan([
        ("poi_a", "2026-01-01", "2026-01-01T09:00:00+07:00",
         "2026-01-01T11:00:00+07:00", 1000.0),
        ("poi_a", "2026-01-01", "2026-01-01T11:00:00+07:00",
         "2026-01-01T13:00:00+07:00", 1000.0),
    ])
    session, _ = _session_with_plan(None)
    llm = FakeLLM(llm_text(json.dumps(dup)))

    result = _run(monkeypatch, session, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.DUPLICATE_STOPS


def test_empty_stops_fails(monkeypatch):
    empty = plan([])
    session, _ = _session_with_plan(None)
    llm = FakeLLM(llm_text(json.dumps(empty)))

    result = _run(monkeypatch, session, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.PLAN_INVALID


def test_valid_plan_is_grounded_and_trace_records_statuses(monkeypatch):
    good = plan([("poi_a", "2026-01-01", "2026-01-01T09:00:00+07:00",
                  "2026-01-01T11:00:00+07:00", 55000.0)])
    session, _ = _session_with_plan(None)
    llm = FakeLLM(llm_text(json.dumps(good)))

    result = _run(monkeypatch, session, llm)

    assert result["status"] == "success"
    assert result["grounding"]["status"] == "grounded"
    assert result["grounding"]["scope_verification"] == "verified"
    # OC-016(-R1) contract: route/hours feasibility is classified per dimension
    # by the independent validator. A single stop needs no inter-stop route, so
    # route feasibility is explicitly `not_applicable` (never a vacuous
    # `verified`); unknown source hours keep hours `unverifiable`. The separate
    # `planning` block qualifies the delivery.
    assert result["grounding"]["route_feasibility"] == "not_applicable"
    assert result["grounding"]["opening_hours_feasibility"] == "unverifiable"
    assert result["planning"]["validator_status"] == "unverifiable"
    assert result["planning"]["verified"] is False
    assert result["reply"]["start_poi_id"] == "poi_a"
    assert result["reply"]["end_poi_id"] == "poi_a"
    assert result["reply"]["budget_is_estimate"] is True
    assert all(step.get("status") in ("success", "failed", "processing")
               for step in result["tool_chain"])
    assert result["tool_chain"][-1]["tool"] == "Gemini Synthesis"
    assert result["tool_chain"][-1]["status"] == "success"
