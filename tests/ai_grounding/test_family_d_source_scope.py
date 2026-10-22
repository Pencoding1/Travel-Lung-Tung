"""T049/AI-059 source-snapshot retention through the itinerary pipeline.

The real ``main`` and ``domains.grounding`` code is exercised, but MCP and the
model are in-process scripted fakes. This is fixture/contract evidence, not a
real graph, real model or full-import acceptance.
"""

import asyncio
import json
from dataclasses import replace

import pytest
from httpx import ASGITransport, AsyncClient

import main
from domains import grounding
from domains.payloads import ItineraryRequest

from helpers_ai_grounding import (
    FakeLLM,
    ScriptedMCPSession,
    default_handlers,
    evidence as admin_evidence,
    llm_text,
    make_request,
    ok_json,
    plan,
    session_seam,
)

NAMESPACE = "hcm_primary_geojson"
SNAPSHOT = "a" * 64
AREA_ID = "source_area_v1:" + "b" * 64
SELECTION = {
    "dataset_namespace": NAMESPACE,
    "input_sha256": SNAPSHOT,
    "source_area_id": AREA_ID,
}
LABEL = "Go Vap, HCMC"
UNCERTAINTY = (
    "Source-snapshot area labels are not a verified mapping to current "
    "administrative boundaries; current city/district status is unverified."
)


def source_context(selection=None, **overrides):
    selection = selection or SELECTION
    value = {
        "dataset_namespace": selection["dataset_namespace"],
        "input_sha256": selection["input_sha256"],
        "source_area_id": selection["source_area_id"],
        "raw_city": "HCMC",
        "raw_area": "Go Vap",
        "source_area_label": LABEL,
        "area_assignment": "qualified",
        "current_admin_status": "unverified_source_area",
        "current_boundary_uncertainty": UNCERTAINTY,
        "lineage_reference": "graph:POI.source_metadata_json#" + "c" * 64,
        "qualification": "exact_source_snapshot_tuple",
    }
    value.update(overrides)
    return value


def source_evidence(poi_id, selection=None, context=None, **overrides):
    payload = {
        "POI_ID": poi_id,
        "POI_Name": f"Source Cafe {poi_id}",
        "POI_Address": "12 Le Loi, Go Vap, HCMC",
        "POI_Category": "Cafe",
        "latitude": 10.82,
        "longitude": 106.68,
        "POI_Description": {"insight": "quiet", "seo_article": ""},
        "POI_Contact_Info": {"website": "", "fanpage": "", "phonenumber": ""},
        "Offers": [],
        "POI_Categories": [{"id": "cat_coffee", "name": "Cafe"}],
        "administrative_context": None,
        "administrative_context_status": "unverified_source_area",
        "administrative_scope": "source_snapshot_area_only",
        "source_context": source_context(selection) if context is None else context,
    }
    payload.update(overrides)
    return payload


def source_request(**overrides):
    values = {
        "session_id": "sess-source",
        "current_city": "Ho Chi Minh City",
        "travel_type": "self-explore",
        "num_travelers": 2,
        "start_date": "2026-01-01",
        "target_district": None,
        "duration_days": 1,
        "budget_range": "500000-1500000 VND",
        "user_description": "quiet cafes",
        "source_scope": SELECTION,
    }
    values.update(overrides)
    return ItineraryRequest(**values)


def _route(args):
    ids = args.get("ordered_poi_ids") or []
    return ok_json({
        "success": True,
        "distance_km": 1.0,
        "time_minutes": 10.0,
        "stops_mapped": len(ids),
        "stops": [{"id": pid, "latitude": 10.82, "longitude": 106.68}
                  for pid in ids],
        "turn_by_turn": [],
    })


def source_handlers(selection=None, categories=None, floor=None,
                    by_category=None, enrichments=None, explore_fail=False):
    selection = selection or SELECTION
    if categories is None:
        categories = [{"id": "cat_coffee", "name": "Cafe"}]
    if floor is None:
        floor = ["poi_a"]
    if by_category is None:
        by_category = {"cat_coffee": ["poi_a"]}
    if enrichments is None:
        enrichments = {"poi_a": source_evidence("poi_a")}

    def resolve(_args):
        raise AssertionError("source mode must not call resolve_geographic_id")

    def get_categories(_args):
        return ok_json({"success": True, "categories": categories})

    def explore(args):
        assert args.get("source_scope") == selection
        assert "city_id" not in args and "district_id" not in args
        assert "street_id" not in args
        if explore_fail:
            return ok_json({"success": False, "detail": "serialization_failed",
                            "results": []})
        category_id = args.get("category_id")
        ids = floor if category_id is None else by_category.get(category_id, [])
        return ok_json({"success": True, "count": len(ids),
                        "results": [{"id": pid} for pid in ids]})

    def details(args):
        pid = args.get("poi_id")
        item = enrichments.get(pid)
        if item is None:
            return ok_json({"success": False, "result": None, "detail": "not found"})
        return ok_json({"success": True, "result": item})

    return {
        "resolve_geographic_id": resolve,
        "get_available_categories": get_categories,
        "explore_pois": explore,
        "get_poi_details": details,
        "get_itinerary_route": _route,
    }


def _run(monkeypatch, handlers, llm, request=None):
    session = ScriptedMCPSession(handlers)
    monkeypatch.setattr(main, "open_mcp_session", session_seam(session))
    monkeypatch.setattr(main, "gemini_chat_completion", llm)
    result = asyncio.run(main.generate_itinerary_endpoint(
        request or source_request()))
    return result, session, llm


def _single_stop(pid="poi_a"):
    return plan([(pid, "2026-01-01", "2026-01-01T09:00:00+07:00",
                  "2026-01-01T11:00:00+07:00", 1000.0)])


def _good_llm(plan_obj):
    return FakeLLM(llm_text(json.dumps(plan_obj)))


# ---------------------------------------------------------------------------
# Request entry / no resolver / explore contract
# ---------------------------------------------------------------------------
def test_source_mode_accepts_request_without_target_district(monkeypatch):
    result, _session, _llm = _run(
        monkeypatch, source_handlers(), _good_llm(_single_stop()))
    assert result["status"] == "success"


def test_source_mode_skips_geographic_resolution(monkeypatch):
    result, session, _llm = _run(
        monkeypatch, source_handlers(), _good_llm(_single_stop()))
    assert result["status"] == "success"
    assert all(call["tool"] != "resolve_geographic_id"
               for call in session.calls)


def test_source_mode_explore_args_carry_exact_selector_and_no_current_ids(monkeypatch):
    result, session, _llm = _run(
        monkeypatch, source_handlers(), _good_llm(_single_stop()))
    assert result["status"] == "success"
    explores = [call for call in session.calls if call["tool"] == "explore_pois"]
    assert explores
    for call in explores:
        assert call["args"]["source_scope"] == SELECTION
        assert "city_id" not in call["args"]
        assert "district_id" not in call["args"]
        assert "street_id" not in call["args"]


def test_source_mode_adds_one_unfiltered_floor_query(monkeypatch):
    result, session, _llm = _run(
        monkeypatch, source_handlers(), _good_llm(_single_stop()))
    assert result["status"] == "success"
    explores = [call for call in session.calls if call["tool"] == "explore_pois"]
    floor = [call for call in explores if "category_id" not in call["args"]]
    assert len(floor) == 1
    assert floor[0]["args"]["limit"] == grounding.MAX_CANDIDATES


def test_source_mode_continues_when_category_catalog_is_empty(monkeypatch):
    handlers = source_handlers(categories=[], floor=["poi_a"],
                               by_category={})
    result, session, _llm = _run(
        monkeypatch, handlers, _good_llm(_single_stop()))
    assert result["status"] == "success"
    tools = [call["tool"] for call in session.calls]
    assert "get_available_categories" in tools
    assert "explore_pois" in tools
    assert any("category_id" not in call["args"]
               for call in session.calls if call["tool"] == "explore_pois")


def test_source_mode_merges_floor_and_category_ids_deterministically(monkeypatch):
    floor = [f"poi_{i:02d}" for i in range(25)] + ["poi_00"]
    handlers = source_handlers(
        floor=floor,
        by_category={"cat_coffee": ["poi_00", "poi_05"]},
        enrichments={"poi_00": source_evidence("poi_00")},
    )
    result, session, _llm = _run(
        monkeypatch, handlers, _good_llm(_single_stop("poi_00")))
    assert result["status"] == "success"
    detail_ids = [call["args"]["poi_id"] for call in session.calls
                  if call["tool"] == "get_poi_details"]
    expected = sorted(set(floor) | {"poi_00", "poi_05"})[:grounding.MAX_CANDIDATES]
    assert detail_ids == expected
    assert len(detail_ids) == len(set(detail_ids)) == grounding.MAX_CANDIDATES


def test_source_mode_serialization_failure_is_not_reported_as_scope_result(monkeypatch):
    llm = FakeLLM(llm_text("unused"))
    result, _session, _llm = _run(
        monkeypatch, source_handlers(explore_fail=True), llm)
    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.CANDIDATE_RETRIEVAL_FAILED
    assert result["error"]["code"] != grounding.SOURCE_SCOPE_UNVERIFIED
    assert llm.calls == []


# ---------------------------------------------------------------------------
# Fail-closed source selection at the evidence boundary
# ---------------------------------------------------------------------------
def test_source_mode_zero_qualified_records_fail_before_model(monkeypatch):
    wrong = source_evidence(
        "poi_a", context=source_context(
            source_area_id="source_area_v1:" + "d" * 64))
    llm = FakeLLM(llm_text("unused"))
    result, _session, _llm = _run(
        monkeypatch,
        source_handlers(enrichments={"poi_a": wrong}), llm)
    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.SCOPE_CONFLICT
    assert llm.calls == []
    assert result["grounding"]["excluded_source_conflicts"] == ["poi_a"]


def test_source_mode_all_unknown_fails_with_source_scope_unverified(monkeypatch):
    unknown = source_evidence("poi_a", source_context=None)
    llm = FakeLLM(llm_text("unused"))
    result, _session, _llm = _run(
        monkeypatch,
        source_handlers(enrichments={"poi_a": unknown}), llm)
    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.SOURCE_SCOPE_UNVERIFIED
    assert llm.calls == []
    assert result["grounding"]["excluded_source_unknown"] == ["poi_a"]


def test_source_mode_conflict_plus_unknown_reports_source_unverified(monkeypatch):
    conflict = source_evidence(
        "poi_a", context=source_context(qualification="assumed"))
    unknown = source_evidence("poi_b", source_context=None)
    llm = FakeLLM(llm_text("unused"))
    result, _session, _llm = _run(
        monkeypatch,
        source_handlers(floor=["poi_a", "poi_b"],
                        by_category={"cat_coffee": ["poi_a", "poi_b"]},
                        enrichments={"poi_a": conflict, "poi_b": unknown}),
        llm)
    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.SOURCE_SCOPE_UNVERIFIED
    assert llm.calls == []
    assert result["grounding"]["excluded_source_conflict_count"] == 1
    assert result["grounding"]["excluded_source_unknown_count"] == 1


def test_administrative_record_never_qualifies_source(monkeypatch):
    admin = admin_evidence("poi_a", "Admin Cafe", "1 Le Loi, Quan 1, HCMC")
    llm = FakeLLM(llm_text("unused"))
    result, _session, _llm = _run(
        monkeypatch, source_handlers(enrichments={"poi_a": admin}), llm)
    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.SOURCE_SCOPE_UNVERIFIED
    assert llm.calls == []


def test_source_record_never_qualifies_administrative_mode(monkeypatch):
    llm = FakeLLM(llm_text("unused"))
    handlers = default_handlers(
        candidates=["poi_a"],
        enrichments={"poi_a": source_evidence("poi_a")})
    result, _session, _llm = _run(
        monkeypatch, handlers, llm,
        request=make_request(target_district="District 1"))
    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.SCOPE_UNVERIFIED
    assert llm.calls == []


def test_mixed_source_records_exclude_foreign_with_counts(monkeypatch):
    qualified = source_evidence("poi_a")
    conflict = source_evidence(
        "poi_b", context=source_context(dataset_namespace="other_snapshot"))
    unknown = source_evidence("poi_c", source_context=None)
    result, _session, _llm = _run(
        monkeypatch,
        source_handlers(floor=["poi_a", "poi_b", "poi_c"],
                        by_category={"cat_coffee": ["poi_a", "poi_b", "poi_c"]},
                        enrichments={"poi_a": qualified, "poi_b": conflict,
                                     "poi_c": unknown}),
        _good_llm(_single_stop("poi_a")))
    assert result["status"] == "success"
    assert result["grounding"]["selected_poi_ids"] == ["poi_a"]
    assert result["grounding"]["excluded_source_conflicts"] == ["poi_b"]
    assert result["grounding"]["excluded_source_unknown"] == ["poi_c"]
    assert result["grounding"]["excluded_source_conflict_count"] == 1
    assert result["grounding"]["excluded_source_unknown_count"] == 1


# ---------------------------------------------------------------------------
# Meta / prompt / plan retention
# ---------------------------------------------------------------------------
def test_source_mode_grounding_and_planning_meta_keep_selection(monkeypatch):
    result, _session, _llm = _run(
        monkeypatch, source_handlers(), _good_llm(_single_stop()))
    assert result["status"] == "success"
    grounding_meta = result["grounding"]
    assert grounding_meta["scope_mode"] == "source_snapshot_area"
    assert grounding_meta["scope_contract"] == "source_snapshot_area"
    assert grounding_meta["scope_verification"] == "qualified_source_snapshot_area"
    assert grounding_meta["source_scope"] == SELECTION
    assert grounding_meta["source_area_label"] == LABEL
    assert grounding_meta["current_boundary_uncertainty"] == UNCERTAINTY
    assert grounding_meta["unused_request_fields"] == ["current_city"]

    planning = result["planning"]
    assert planning["scope_mode"] == "source_snapshot_area"
    assert planning["source_scope"] == SELECTION
    assert planning["request_constraints"]["source_scope"] == SELECTION
    assert planning["request_constraints"]["scope_mode"] == "source_snapshot_area"


def test_legacy_target_label_is_recorded_unused_not_sent(monkeypatch):
    result, session, _llm = _run(
        monkeypatch, source_handlers(), _good_llm(_single_stop()),
        request=source_request(target_district="District 1"))
    assert result["status"] == "success"
    assert result["grounding"]["unused_request_fields"] == [
        "current_city", "target_district"]
    for call in session.calls:
        assert call["args"].get("district_id") is None
        assert call["args"].get("city_id") is None
        assert call["args"].get("target_district") is None


def test_source_prompt_has_label_and_uncertainty_but_no_provenance(monkeypatch):
    llm = _good_llm(_single_stop())
    result, _session, _llm = _run(
        monkeypatch, source_handlers(), llm)
    assert result["status"] == "success"
    prompt = llm.calls[0]["messages"][0]["content"]
    assert LABEL in prompt
    assert "UNVERIFIED" in prompt
    assert "not a verified mapping" in prompt
    for forbidden in ("lineage_reference", "raw_lineage", "source_metadata",
                      "administrative_context", NAMESPACE, SNAPSHOT, AREA_ID,
                      "Target Area:"):
        assert forbidden not in prompt


def test_source_plan_stop_retains_compact_claim_and_null_current_admin(monkeypatch):
    result, _session, _llm = _run(
        monkeypatch, source_handlers(), _good_llm(_single_stop()))
    assert result["status"] == "success"
    stop = result["reply"]["stops"][0]["poi"]
    assert stop["address"]["district"] is None
    assert stop["address"]["city"] is None
    assert stop["current_admin_status"] == "unverified_source_area"
    claim = stop["source_snapshot_area"]
    assert claim["source_area_id"] == AREA_ID
    assert claim["source_area_label"] == LABEL
    assert claim["current_boundary_uncertainty"] == UNCERTAINTY
    assert claim["qualification"] == "exact_source_snapshot_tuple"
    assert "lineage_reference" not in claim
    assert result["grounding"]["scope_verifications"] == [
        "qualified_source_snapshot_area"]


def test_model_cannot_change_selector_or_inject_admin_facts(monkeypatch):
    proposal = _single_stop()
    proposal["stops"][0]["poi"] = {
        "id": "poi_a",
        "name": "Fabricated Name",
        "address": {"city": "Hanoi", "district": "Fabricated District"},
        "source_scope": {
            "dataset_namespace": "model_chosen",
            "input_sha256": "d" * 64,
            "source_area_id": "source_area_v1:" + "d" * 64,
        },
        "administrative_context": {
            "city_id": "hanoi", "district_id": "fake",
            "city_name": "Hanoi", "district_name": "Fabricated District",
        },
    }
    proposal["stops"][0]["description"] = "fabricated description"
    result, _session, _llm = _run(
        monkeypatch, source_handlers(), _good_llm(proposal))
    assert result["status"] == "success"
    poi = result["reply"]["stops"][0]["poi"]
    assert poi["name"] == "Source Cafe poi_a"
    assert poi["address"]["district"] is None
    assert poi["address"]["city"] is None
    assert "source_scope" not in poi
    assert "administrative_context" not in poi
    assert poi["source_snapshot_area"]["source_area_id"] == AREA_ID
    assert result["grounding"]["source_scope"] == SELECTION


def test_repaired_schedule_revalidates_selection(monkeypatch):
    real = grounding.poi_source_scope_status
    state = {"calls": 0}

    def flaky(evidence, selection):
        state["calls"] += 1
        if state["calls"] >= 3:  # filter -> initial plan -> repaired loop
            return "conflict"
        return real(evidence, selection)

    monkeypatch.setattr(main.grounding, "poi_source_scope_status", flaky)
    result, _session, _llm = _run(
        monkeypatch, source_handlers(), _good_llm(_single_stop()))
    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.SCOPE_CONFLICT
    assert result["error"].get("details", {}).get("poi_id") == "poi_a"


# ---------------------------------------------------------------------------
# Final-schedule metadata integrity (AI-059 R1)
# ---------------------------------------------------------------------------
def _two_candidates(monkeypatch, enrichments, llm, request):
    handlers = source_handlers(
        floor=["poi_a", "poi_b"],
        by_category={"cat_coffee": ["poi_a", "poi_b"]},
        enrichments=enrichments)
    return _run(monkeypatch, handlers, llm, request=request)


def test_final_metadata_covers_scheduler_added_source_stop(monkeypatch):
    """Model proposes 1 stop; the real scheduler (minimum_stops=2) delivers 2."""
    result, _session, _llm = _two_candidates(
        monkeypatch,
        {"poi_a": source_evidence("poi_a"), "poi_b": source_evidence("poi_b")},
        _good_llm(_single_stop("poi_a")),
        source_request(minimum_stops=2))

    assert result["status"] == "success"
    delivered = result["reply"]["stops"]
    assert len(delivered) == 2
    delivered_ids = [stop["poi"]["id"] for stop in delivered]
    assert sorted(delivered_ids) == ["poi_a", "poi_b"]

    # Every delivered stop carries its own exact compact source claim.
    for stop in delivered:
        claim = stop["poi"]["source_snapshot_area"]
        assert claim["source_area_id"] == AREA_ID
        assert claim["qualification"] == "exact_source_snapshot_tuple"
        assert stop["poi"]["address"]["city"] is None
        assert stop["poi"]["address"]["district"] is None

    # Final metadata follows final stop indices, including the added stop.
    assert result["grounding"]["scope_verifications"] == [
        "qualified_source_snapshot_area", "qualified_source_snapshot_area"]
    missing = result["grounding"]["missing_data"]
    for index in range(len(delivered)):
        assert f"stops[{index}].address.city" in missing
        assert f"stops[{index}].address.district" in missing
    assert not any(path.startswith(f"stops[{len(delivered)}]")
                   for path in missing)

    # The one-stop initial proposal evidence remains separately identifiable.
    initial = result["planning"]["initial_proposal"]
    assert initial["scope_verifications"] == ["qualified_source_snapshot_area"]
    assert len(initial["sequence"]) == 1
    initial_missing = initial["missing_data"]
    assert any(path.startswith("stops[0].") for path in initial_missing)
    assert not any(path.startswith("stops[1].") for path in initial_missing)


def test_final_metadata_reindexes_reordered_final_schedule(monkeypatch):
    """Model order differs from repaired order; missing paths use final indices.

    Bounded test seam: the real scheduler output is retained but its stop order
    is forced to poi_a, poi_b so the initial (poi_b, poi_a) indexing is
    observably different. No scheduler shape is fabricated.
    """
    real_schedule = main.planning_schedule

    def ordered_schedule(scenario):
        scheduled = real_schedule(scenario)
        order = ["poi_a", "poi_b"]

        def key(pid):
            return order.index(pid) if pid in order else len(order)

        days = tuple(
            replace(day, stops=tuple(sorted(day.stops,
                                            key=lambda stop: key(stop.poi_id))))
            for day in scheduled.days)
        sequence = tuple(sorted(scheduled.sequence, key=key))
        return replace(scheduled, days=days, sequence=sequence)

    monkeypatch.setattr(main, "planning_schedule", ordered_schedule)

    # poi_b has known hours, poi_a does not. Model order (b, a) would record
    # poi_a's operation_time as stops[1]; final order (a, b) must record it as
    # stops[0] and never claim the reordered initial path.
    enrichments = {
        "poi_a": source_evidence("poi_a"),
        "poi_b": source_evidence("poi_b", operation_time="08:00-22:00"),
    }
    model_plan = plan([
        ("poi_b", "2026-01-01", "2026-01-01T09:00:00+07:00",
         "2026-01-01T10:00:00+07:00", 1000.0),
        ("poi_a", "2026-01-01", "2026-01-01T10:15:00+07:00",
         "2026-01-01T11:15:00+07:00", 1000.0),
    ])
    result, _session, _llm = _two_candidates(
        monkeypatch, enrichments, _good_llm(model_plan), source_request())

    assert result["status"] == "success"
    delivered = result["reply"]["stops"]
    assert [stop["poi"]["id"] for stop in delivered] == ["poi_a", "poi_b"]
    assert result["grounding"]["scope_verifications"] == [
        "qualified_source_snapshot_area", "qualified_source_snapshot_area"]

    missing = result["grounding"]["missing_data"]
    assert "stops[0].operation_time" in missing
    assert "stops[1].operation_time" not in missing
    assert "stops[0].address.city" in missing
    assert "stops[1].address.city" in missing

    # Preserved initial proposal keeps the model-order paths.
    initial_missing = result["planning"]["initial_proposal"]["missing_data"]
    assert "stops[1].operation_time" in initial_missing
    assert "stops[0].operation_time" not in initial_missing


# ---------------------------------------------------------------------------
# Legacy administrative mode remains unchanged
# ---------------------------------------------------------------------------
def test_current_mode_without_source_scope_is_unchanged(monkeypatch):
    result, session, _llm = _run(
        monkeypatch, default_handlers(), _good_llm(_single_stop()),
        request=make_request())
    assert result["status"] == "success"
    assert result["grounding"]["scope_contract"] == "administrative_context"
    assert result["grounding"]["scope_verification"] == "verified"
    assert result["grounding"]["scope_verifications"] == ["verified"]
    assert "source_scope" not in result["grounding"]
    assert any(call["tool"] == "resolve_geographic_id" for call in session.calls)


# ---------------------------------------------------------------------------
# HTTP boundary: invalid selector is rejected before MCP/model
# ---------------------------------------------------------------------------
VALID_SOURCE_BODY = {
    "session_id": "sess-http-source",
    "current_city": "Ho Chi Minh City",
    "travel_type": "self-explore",
    "num_travelers": 2,
    "start_date": "2026-01-01",
    "duration_days": 1,
    "budget_range": "500000-1500000 VND",
    "user_description": "quiet cafes",
    "source_scope": SELECTION,
}


def _post(monkeypatch, body):
    session = ScriptedMCPSession(source_handlers())
    llm = FakeLLM(llm_text("unused"))
    monkeypatch.setattr(main, "open_mcp_session", session_seam(session))
    monkeypatch.setattr(main, "gemini_chat_completion", llm)

    async def _call():
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/generate_itinerary", json=body)

    response = asyncio.run(_call())
    return response, session, llm


@pytest.mark.parametrize("mutate", [
    lambda body: body["source_scope"].update(extra="no"),
    lambda body: body["source_scope"].update(input_sha256="A" * 64),
    lambda body: body["source_scope"].update(source_area_id="quan_1"),
    lambda body: body["source_scope"].update(dataset_namespace=" ns"),
])
def test_http_invalid_source_selector_is_422_before_mcp_or_model(monkeypatch, mutate):
    body = json.loads(json.dumps(VALID_SOURCE_BODY))
    mutate(body)
    response, session, llm = _post(monkeypatch, body)
    assert response.status_code == 422
    assert session.calls == []
    assert llm.calls == []


def test_http_missing_selector_still_requires_target_district(monkeypatch):
    body = json.loads(json.dumps(VALID_SOURCE_BODY))
    body.pop("source_scope")
    response, session, llm = _post(monkeypatch, body)
    assert response.status_code == 422
    assert session.calls == []
    assert llm.calls == []
