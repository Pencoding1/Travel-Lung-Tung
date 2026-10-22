"""OC-005 corrective-QA regressions.

Covers the fixes from the repair brief: structured scope contract, id
validation, rating provenance, coordinate bounds, offer/opening-hours
provenance, trip-window/budget validation, server identity, deterministic caps,
trace status propagation and sanitized model-shape failures.
"""

import asyncio
import json
from pathlib import Path

import main
import pytest
from domains import grounding

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


def _run(monkeypatch, handlers, llm, request=None):
    session = ScriptedMCPSession(handlers)
    monkeypatch.setattr(main, "open_mcp_session", session_seam(session))
    monkeypatch.setattr(main, "gemini_chat_completion", llm)
    result = asyncio.run(main.generate_itinerary_endpoint(request or make_request()))
    return result, session


def _single_stop(pid="poi_a", day="2026-01-01",
                 visit="2026-01-01T09:00:00+07:00",
                 end="2026-01-01T11:00:00+07:00", budget=1000.0):
    return plan([(pid, day, visit, end, budget)])


def _good_llm(plan_obj):
    return FakeLLM(llm_text(json.dumps(plan_obj)))


# ---------------------------------------------------------------------------
# 1. Structured scope contract
# ---------------------------------------------------------------------------
def test_district_10_context_is_not_verified_as_district_1(monkeypatch):
    enrichments = {
        "poi_a": evidence(
            "poi_a", "A", "12 Le Loi, Quan 1, Ho Chi Minh City",
            admin={"city_id": "hcmc", "district_id": "quan_10",
                   "city_name": "Ho Chi Minh City", "district_name": "Quận 10"}),
    }
    handlers = default_handlers(candidates=["poi_a"], enrichments=enrichments)
    llm = FakeLLM(llm_text("unused"))

    result, _session = _run(monkeypatch, handlers, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.SCOPE_CONFLICT
    assert llm.calls == []
    assert result["grounding"]["excluded_scope_conflicts"] == ["poi_a"]


def test_free_text_address_never_verifies_scope(monkeypatch):
    enrichments = {"poi_a": evidence("poi_a", "A",
                                     "12 Le Loi, Quan 1, Ho Chi Minh City",
                                     admin=None)}
    handlers = default_handlers(candidates=["poi_a"], enrichments=enrichments)
    llm = FakeLLM(llm_text("unused"))

    result, _session = _run(monkeypatch, handlers, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.SCOPE_UNVERIFIED
    assert llm.calls == []


def test_district_parent_city_conflict_is_rejected(monkeypatch):
    handlers = default_handlers(district_matches=[{
        "type": "District", "id": "quan_1", "name": "District 1",
        "city_id": "hanoi", "city_name": "Hanoi",
    }])
    llm = FakeLLM(llm_text("unused"))

    result, _session = _run(monkeypatch, handlers, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.SCOPE_CONFLICT
    assert llm.calls == []


def test_district_parent_city_match_is_preserved(monkeypatch):
    handlers = default_handlers(district_matches=[{
        "type": "District", "id": "quan_1", "name": "District 1",
        "city_id": "hcmc", "city_name": "Ho Chi Minh City",
    }])
    result, _session = _run(monkeypatch, handlers, _good_llm(_single_stop()))

    assert result["status"] == "success"
    assert result["grounding"]["scope_evidence"]["district"]["parent_city_id"] == "hcmc"


def test_only_verified_subset_is_synthesized(monkeypatch):
    enrichments = {
        "poi_a": evidence("poi_a", "Verified", "1 Le Loi, Quan 1, Ho Chi Minh City"),
        "poi_b": evidence("poi_b", "Unknown", "2 Le Loi, Quan 1, Ho Chi Minh City",
                          admin=None),
        "poi_c": evidence("poi_c", "Conflict", "3 Le Loi, Quan 5, Ho Chi Minh City",
                          admin={"city_id": "hcmc", "district_id": "quan_5",
                                 "city_name": "Ho Chi Minh City",
                                 "district_name": "District 5"}),
    }
    handlers = default_handlers(candidates=["poi_a", "poi_b", "poi_c"],
                                enrichments=enrichments)
    result, _session = _run(monkeypatch, handlers, _good_llm(_single_stop()))

    assert result["status"] == "success"
    assert result["grounding"]["selected_poi_ids"] == ["poi_a"]
    assert result["grounding"]["excluded_scope_unknown"] == ["poi_b"]
    assert result["grounding"]["excluded_scope_conflicts"] == ["poi_c"]


def test_invalid_admin_context_types_are_unknown(monkeypatch):
    enrichments = {
        "poi_a": evidence("poi_a", "A", "12 Le Loi, Quan 1, Ho Chi Minh City",
                          admin={"city_id": 1, "district_id": None,
                                 "city_name": ["x"], "district_name": True}),
    }
    handlers = default_handlers(candidates=["poi_a"], enrichments=enrichments)
    llm = FakeLLM(llm_text("unused"))

    result, _session = _run(monkeypatch, handlers, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.SCOPE_UNVERIFIED


# ---------------------------------------------------------------------------
# 2. ID validation
# ---------------------------------------------------------------------------
def test_enrichment_id_mismatch_marks_trace_failed_and_excludes(monkeypatch):
    handlers = default_handlers(candidates=["poi_a"])
    handlers["get_poi_details"] = lambda args: ok_json({
        "success": True,
        "result": evidence("poi_b", "B", "1 X, Quan 1, Ho Chi Minh City"),
    })
    llm = FakeLLM(llm_text("unused"))

    result, _session = _run(monkeypatch, handlers, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.INSUFFICIENT_DATA
    detail_steps = [s for s in result["tool_chain"] if s["tool"] == "get_poi_details"]
    assert detail_steps[0]["status"] == "failed"
    assert detail_steps[0]["summary"] == grounding.ENRICHMENT_MISMATCH
    assert llm.calls == []


def test_select_unique_area_skips_invalid_id_record():
    matches = [
        {"type": "District", "id": None, "name": "District 1"},
        {"type": "District", "id": True, "name": "District 1"},
        {"type": "District", "id": ["quan_1"], "name": "District 1"},
        {"type": "District", "id": "quan_1", "name": "District 1"},
    ]
    outcome = grounding.select_unique_area(matches, "District 1", "District")
    assert outcome.ok
    assert outcome.data["id"] == "quan_1"


def test_parse_explore_rejects_non_string_ids():
    outcome = grounding.parse_explore(grounding.ToolOutcome(True, {
        "results": [{"id": None}, {"id": [1]}, {"id": True}, {"id": ""},
                    {"id": "ok"}],
    }))
    assert outcome.ok
    assert [c["id"] for c in outcome.data] == ["ok"]


def test_nonblank_str_rejects_str_none_like_values():
    assert grounding.nonblank_str("x") == "x"
    assert grounding.nonblank_str("  ") is None
    assert grounding.nonblank_str(None) is None
    assert grounding.nonblank_str(True) is None
    assert grounding.nonblank_str(5) is None
    assert grounding.nonblank_str(["a"]) is None


# ---------------------------------------------------------------------------
# 3. Rating / coordinates / offers / opening hours provenance
# ---------------------------------------------------------------------------
def test_generic_rating_is_not_promoted_to_a_provider(monkeypatch):
    enrichments = {"poi_a": evidence("poi_a", "A",
                                     "1 Le Loi, Quan 1, Ho Chi Minh City",
                                     rating=4.9)}
    handlers = default_handlers(candidates=["poi_a"], enrichments=enrichments)
    result, _session = _run(monkeypatch, handlers, _good_llm(_single_stop()))

    assert result["status"] == "success"
    assert result["reply"]["stops"][0]["poi"]["rating"] is None
    assert any("rating" in item for item in result["grounding"]["missing_data"])


def test_explicit_rating_providers_are_respected(monkeypatch):
    enrichments = {
        "poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, Ho Chi Minh City",
                          rating=4.9,
                          rating_sources={"google_maps": 4.5,
                                          "unsupported_provider": 4.9,
                                          "tripadvisor": 0}),
    }
    handlers = default_handlers(candidates=["poi_a"], enrichments=enrichments)
    result, _session = _run(monkeypatch, handlers, _good_llm(_single_stop()))

    assert result["status"] == "success"
    assert result["reply"]["stops"][0]["poi"]["rating"] == {"google_maps": 4.5}


def test_out_of_range_coordinates_reject_enrichment(monkeypatch):
    enrichments = {"poi_a": evidence("poi_a", "A",
                                     "1 Le Loi, Quan 1, Ho Chi Minh City",
                                     latitude=999.0)}
    handlers = default_handlers(candidates=["poi_a"], enrichments=enrichments)
    llm = FakeLLM(llm_text("unused"))

    result, _session = _run(monkeypatch, handlers, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.INSUFFICIENT_DATA
    detail_steps = [s for s in result["tool_chain"] if s["tool"] == "get_poi_details"]
    assert detail_steps[0]["status"] == "failed"


def test_nan_coordinate_rejects_enrichment(monkeypatch):
    enrichments = {"poi_a": evidence("poi_a", "A",
                                     "1 Le Loi, Quan 1, Ho Chi Minh City",
                                     longitude=float("nan"))}
    handlers = default_handlers(candidates=["poi_a"], enrichments=enrichments)
    result, _session = _run(monkeypatch, handlers, FakeLLM(llm_text("unused")))

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.INSUFFICIENT_DATA


def test_fallback_zero_offer_price_is_null_and_unverified(monkeypatch):
    enrichments = {
        "poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, Ho Chi Minh City",
                          offers=[{"name": "Coffee", "price": 0}]),
    }
    handlers = default_handlers(candidates=["poi_a"], enrichments=enrichments)
    result, _session = _run(monkeypatch, handlers, _good_llm(_single_stop()))

    assert result["status"] == "success"
    menu = result["reply"]["stops"][0]["poi"]["menu"]
    assert menu[0]["price"] is None
    assert menu[0]["price_verified"] is False


def test_explicit_operation_time_is_included_but_feasibility_unverified(monkeypatch):
    enrichments = {
        "poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, Ho Chi Minh City",
                          operation_time="08:00-22:00"),
    }
    handlers = default_handlers(candidates=["poi_a"], enrichments=enrichments)
    result, _session = _run(monkeypatch, handlers, _good_llm(_single_stop()))

    assert result["status"] == "success"
    poi = result["reply"]["stops"][0]["poi"]
    assert poi["operation_time"] == "08:00-22:00"
    assert poi["operation_time_feasibility"] == "unverified"


def test_absent_operation_time_is_missing_data(monkeypatch):
    handlers = default_handlers()
    result, _session = _run(monkeypatch, handlers, _good_llm(_single_stop()))

    assert result["status"] == "success"
    assert result["reply"]["stops"][0]["poi"]["operation_time"] is None
    assert any("operation_time" in item for item in result["grounding"]["missing_data"])


# ---------------------------------------------------------------------------
# 4. Trip window / budgets / identity
# ---------------------------------------------------------------------------
def test_stop_outside_trip_window_fails(monkeypatch):
    bad = _single_stop(day="2026-01-05", visit="2026-01-05T09:00:00+07:00",
                       end="2026-01-05T11:00:00+07:00")
    handlers = default_handlers()
    result, _session = _run(monkeypatch, handlers, _good_llm(bad))

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.TIME_ORDER_INVALID


def test_end_time_beyond_trip_fails(monkeypatch):
    bad = _single_stop(visit="2026-01-01T22:00:00+07:00",
                       end="2026-01-02T02:00:00+07:00")
    handlers = default_handlers()
    result, _session = _run(monkeypatch, handlers, _good_llm(bad))

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.TIME_ORDER_INVALID


def test_negative_budget_fails(monkeypatch):
    bad = _single_stop(budget=-5.0)
    handlers = default_handlers()
    result, _session = _run(monkeypatch, handlers, _good_llm(bad))

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.BUDGET_INVALID


def test_nonfinite_budget_fails(monkeypatch):
    bad = _single_stop(budget=float("inf"))
    handlers = default_handlers()
    result, _session = _run(monkeypatch, handlers, _good_llm(bad))

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.BUDGET_INVALID


def test_total_budget_mismatch_fails(monkeypatch):
    bad = plan([("poi_a", "2026-01-01", "2026-01-01T09:00:00+07:00",
                 "2026-01-01T11:00:00+07:00", 1000.0)], total=999999.0)
    handlers = default_handlers()
    result, _session = _run(monkeypatch, handlers, _good_llm(bad))

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.BUDGET_INVALID


def test_total_budget_reconciled_to_stop_sum(monkeypatch):
    enrichments = {
        "poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, Ho Chi Minh City"),
        "poi_b": evidence("poi_b", "B", "2 Le Loi, Quan 1, Ho Chi Minh City"),
    }
    handlers = default_handlers(candidates=["poi_a", "poi_b"], enrichments=enrichments)
    good = plan([
        ("poi_a", "2026-01-01", "2026-01-01T09:00:00+07:00",
         "2026-01-01T11:00:00+07:00", 1000.0),
        ("poi_b", "2026-01-01", "2026-01-01T11:00:00+07:00",
         "2026-01-01T13:00:00+07:00", 2000.0),
    ], total=3000.0)
    result, _session = _run(monkeypatch, handlers, _good_llm(good))

    assert result["status"] == "success"
    assert result["reply"]["total_estimated_budget"] == 3000.0


def test_server_generates_identity_and_ignores_model_id_uid(monkeypatch):
    good = _single_stop()
    good["id"] = "model-id"
    good["uid"] = "model-uid"
    handlers = default_handlers()
    result, _session = _run(monkeypatch, handlers, _good_llm(good))

    assert result["status"] == "success"
    assert result["reply"]["id"].startswith("itin_")
    assert result["reply"]["id"] != "model-id"
    # OC-009 repair: reply.uid is never derived from session_id. Ownership must
    # come from a verified JWT subject or be null, so the in-process entry point
    # is anonymous by default. The model id/uid must still never be adopted.
    assert result["reply"]["uid"] is None
    assert result["reply"]["uid"] != "model-uid"
    assert result["grounding"]["id_source"] == "server"


# ---------------------------------------------------------------------------
# 5. Deterministic caps / trace status / model shapes
# ---------------------------------------------------------------------------
def test_category_cap_is_permutation_invariant():
    cats = [{"id": f"c{i}", "name": f"C{i}"} for i in range(10)]

    def parsed(order):
        out = grounding.parse_categories(grounding.ToolOutcome(
            True, {"categories": order}))
        return [c["id"] for c in out.data]

    expected = sorted(c["id"] for c in cats)[:grounding.MAX_CATEGORIES]
    assert parsed(cats) == expected
    assert parsed(list(reversed(cats))) == expected
    assert parsed(cats[4:] + cats[:4]) == expected


def test_candidate_cap_is_permutation_invariant():
    ids = [f"p{i}" for i in range(25)]
    expected = sorted(ids)[:grounding.MAX_CANDIDATES]

    assert grounding.collect_candidate_ids([[{"id": i} for i in ids]]) == expected
    assert grounding.collect_candidate_ids(
        [[{"id": i} for i in list(reversed(ids))]]) == expected


def test_invalid_explore_result_marks_trace_failed(monkeypatch):
    handlers = default_handlers()
    handlers["explore_pois"] = lambda args: ok_json(
        {"success": True, "results": {"bad": "shape"}})
    llm = FakeLLM(llm_text("unused"))

    result, _session = _run(monkeypatch, handlers, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.INSUFFICIENT_DATA
    explore_steps = [s for s in result["tool_chain"] if s["tool"].startswith("explore_pois")]
    assert explore_steps[0]["status"] == "failed"
    assert llm.calls == []


@pytest.mark.parametrize("response", [
    {},
    {"choices": []},
    {"choices": "nope"},
    {"choices": [{"message": {"content": None}}]},
    {"choices": [{"message": {"content": ["x"]}}]},
    {"choices": [{"message": {"content": "   "}}]},
])
def test_invalid_model_shapes_fail_sanitized(monkeypatch, response):
    handlers = default_handlers()
    llm = FakeLLM(response)

    result, _session = _run(monkeypatch, handlers, llm)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.LLM_ERROR
    synthesis = result["tool_chain"][-1]
    assert synthesis["tool"] == "Gemini Synthesis"
    assert synthesis["status"] == "failed"


def test_endpoint_does_not_log_repr_of_exceptions():
    src = Path(main.__file__).read_text(encoding="utf-8")
    assert "repr(e)" not in src
