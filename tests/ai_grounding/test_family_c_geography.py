"""Adversarial family C: out-of-scope / ambiguous geography.

Requested city and district must resolve to a unique normalized exact match of
the expected entity type *before* any synthesis. Partial keyword matches,
ambiguous matches, type mismatches, unknown areas and cross-district POIs must
fail (or be excluded) rather than be misrepresented as the requested location.
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


def _run(monkeypatch, handlers, llm, request=None):
    session = ScriptedMCPSession(handlers)
    monkeypatch.setattr(main, "open_mcp_session", session_seam(session))
    monkeypatch.setattr(main, "gemini_chat_completion", llm)
    return asyncio.run(main.generate_itinerary_endpoint(request or make_request()))


def test_no_matching_district_fails_before_synthesis(monkeypatch):
    handlers = default_handlers(district_matches=[])
    llm = FakeLLM(llm_text("unused"))

    result = _run(monkeypatch, handlers, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.LOCATION_NOT_RESOLVED
    assert llm.calls == []


def test_ambiguous_district_fails_before_synthesis(monkeypatch):
    handlers = default_handlers(district_matches=[
        {"type": "District", "id": "quan_1_a", "name": "District 1"},
        {"type": "District", "id": "quan_1_b", "name": "Quan 1"},
    ])
    llm = FakeLLM(llm_text("unused"))

    result = _run(monkeypatch, handlers, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.LOCATION_AMBIGUOUS
    assert llm.calls == []


def test_wrong_entity_type_is_rejected(monkeypatch):
    handlers = default_handlers(district_matches=[
        {"type": "City", "id": "city_1", "name": "District 1"},
    ])
    llm = FakeLLM(llm_text("unused"))

    result = _run(monkeypatch, handlers, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.LOCATION_TYPE_MISMATCH
    assert llm.calls == []


def test_partial_keyword_match_is_rejected(monkeypatch):
    # Request "District 1" but the database only has "District 10".
    handlers = default_handlers(district_matches=[
        {"type": "District", "id": "quan_10", "name": "District 10"},
    ])
    llm = FakeLLM(llm_text("unused"))

    result = _run(monkeypatch, handlers, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.LOCATION_NOT_RESOLVED
    assert llm.calls == []


def test_district_10_is_not_accepted_for_district_1(monkeypatch):
    handlers = default_handlers(district_matches=[
        {"type": "District", "id": "quan_1", "name": "District 1"},
        {"type": "District", "id": "quan_10", "name": "District 10"},
    ])
    good = plan([("poi_a", "2026-01-01", "2026-01-01T09:00:00+07:00",
                  "2026-01-01T11:00:00+07:00", 1000.0)])
    llm = FakeLLM(llm_text(json.dumps(good)))

    result = _run(monkeypatch, handlers, llm)

    # A unique exact match for "District 1" exists; "District 10" is ignored.
    assert result["status"] == "success"
    assert result["grounding"]["scope_evidence"]["district"]["id"] == "quan_1"


def test_accent_and_alias_normalization_accepts_quan_1(monkeypatch):
    handlers = default_handlers(district_matches=[
        {"type": "District", "id": "quan_1", "name": "Quận 1"},
    ])
    good = plan([("poi_a", "2026-01-01", "2026-01-01T09:00:00+07:00",
                  "2026-01-01T11:00:00+07:00", 1000.0)])
    llm = FakeLLM(llm_text(json.dumps(good)))

    result = _run(monkeypatch, handlers, llm,
                  request=make_request(target_district="District 1"))

    assert result["status"] == "success"
    assert result["grounding"]["scope_evidence"]["district"]["id"] == "quan_1"


def test_wrong_city_fails_before_synthesis(monkeypatch):
    handlers = default_handlers(city_matches=[])
    llm = FakeLLM(llm_text("unused"))

    result = _run(monkeypatch, handlers, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.LOCATION_NOT_RESOLVED
    assert llm.calls == []


def test_cross_district_poi_is_excluded(monkeypatch):
    enrichments = {
        "poi_a": evidence("poi_a", "In Scope", "1 Le Loi, Quan 1, Ho Chi Minh City"),
        "poi_b": evidence("poi_b", "Out Of Scope", "9 Nguyen Trai, Quan 5, Ho Chi Minh City",
                          admin={"city_id": "hcmc", "district_id": "quan_5",
                                 "city_name": "Ho Chi Minh City",
                                 "district_name": "District 5"}),
    }
    handlers = default_handlers(candidates=["poi_a", "poi_b"], enrichments=enrichments)
    good = plan([("poi_a", "2026-01-01", "2026-01-01T09:00:00+07:00",
                  "2026-01-01T11:00:00+07:00", 1000.0)])
    llm = FakeLLM(llm_text(json.dumps(good)))

    result = _run(monkeypatch, handlers, llm)

    assert result["status"] == "success"
    assert result["grounding"]["excluded_scope_conflicts"] == ["poi_b"]
    assert result["grounding"]["selected_poi_ids"] == ["poi_a"]


def test_all_cross_district_pois_fail_closed(monkeypatch):
    enrichments = {
        "poi_b": evidence("poi_b", "Out", "9 Nguyen Trai, Quan 5, Ho Chi Minh City",
                          admin={"city_id": "hcmc", "district_id": "quan_5",
                                 "city_name": "Ho Chi Minh City",
                                 "district_name": "District 5"}),
    }
    handlers = default_handlers(candidates=["poi_b"], enrichments=enrichments)
    llm = FakeLLM(llm_text("unused"))

    result = _run(monkeypatch, handlers, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.SCOPE_CONFLICT
    assert llm.calls == []


def test_missing_parent_context_fails_closed_with_scope_unverified(monkeypatch):
    # No structured administrative_context -> cannot verify scope -> fail before
    # the model. The free-text address is deliberately plausible; it must not be
    # trusted for scope.
    enrichments = {
        "poi_a": evidence("poi_a", "Looks In Scope",
                          "12 Le Loi, Quan 1, Ho Chi Minh City", admin=None),
    }
    handlers = default_handlers(candidates=["poi_a"], enrichments=enrichments)
    llm = FakeLLM(llm_text("unused"))

    result = _run(monkeypatch, handlers, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.SCOPE_UNVERIFIED
    assert llm.calls == []
    assert result["grounding"]["excluded_scope_unknown"] == ["poi_a"]
