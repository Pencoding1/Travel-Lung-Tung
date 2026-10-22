"""RT-064 transport-mode propagation contract.

Runs the real ASGI app and the real planner adapter with controlled fake MCP
and fake LLM collaborators. No network, live model, graph or database call is
made; this is contract evidence only.

Covered:
* HTTP omitted/explicit car/explicit foot reaches every directed route call,
  the typed scenario and the response provenance;
* invalid modes fail at the request boundary (HTTP 422) before any model/MCP
  call, and direct adapter callers fail closed without a scenario;
* optional upstream ``vehicle``/``profile`` echoes are validated exactly, with
  no silent car fallback and no invented provider confirmation when absent;
* car/foot durations change delivered travel totals while raw seconds,
  rounding and meters stay exact;
* a failed foot leg stays unknown/partial;
* source-scope foot flow keeps the selection and source provenance.
"""

import asyncio
import json
from decimal import Decimal

import pytest

import main
from domains import planning_adapter
from domains.payloads import ItineraryRequest
from helpers_ai_grounding import (
    ScriptedMCPSession,
    default_handlers,
    evidence,
    ok_json,
    session_seam,
)
from helpers_planning_integration import DEFAULT_BODY, good_llm, stop_plan

TWO_POIS = ["poi_a", "poi_b"]
INVALID_MODES = [None, True, 1, 1.5, {}, [], "", " foot", "FOOT", "bike"]

ABSENT = object()
MATCH = object()


def _enrich():
    return {
        "poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC"),
        "poi_b": evidence("poi_b", "B", "2 Le Loi, Quan 1, HCMC"),
    }


def _route_handler(*, durations=None, fail_pairs=(), vehicle=MATCH,
                   profile=ABSENT):
    """Fake ``get_itinerary_route`` with explicit echo controls.

    ``MATCH`` echoes the requested vehicle/mode; ``ABSENT`` omits the field; any
    other value is sent verbatim (e.g. a mismatched/no-null/malformed echo).
    """
    fail_pairs = {tuple(pair) for pair in fail_pairs}

    def handler(args):
        ids = args.get("ordered_poi_ids") or []
        mode = args.get("vehicle")
        if tuple(ids) in fail_pairs:
            return ok_json({"success": False, "code": "no_route",
                            "detail": "no route between stops"})
        payload = {
            "success": True,
            "distance_km": 1.0,
            "time_minutes": (durations or {}).get(mode, 10.0),
            "stops_mapped": len(ids),
            "stops": [{"id": pid} for pid in ids],
            "turn_by_turn": [],
        }
        if vehicle is not ABSENT:
            payload["vehicle"] = mode if vehicle is MATCH else vehicle
        if profile is not ABSENT:
            payload["profile"] = mode if profile is MATCH else profile
        return ok_json(payload)

    return handler


def _run_http(monkeypatch, handlers, llm, body, headers=None):
    session = ScriptedMCPSession(handlers)
    monkeypatch.setattr(main, "open_mcp_session", session_seam(session))
    monkeypatch.setattr(main, "gemini_chat_completion", llm)

    async def _call():
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/generate_itinerary", json=body, headers=headers)

    return asyncio.run(_call()), session


def _two_stop_plan():
    return stop_plan([("poi_a", 1000.0), ("poi_b", 2000.0)])


def _collect(handler, poi_ids, **kwargs):
    calls = []

    async def call_tool(name, args):
        calls.append((name, dict(args)))
        return handler(args)

    edges, route_evidence = asyncio.run(
        planning_adapter.collect_route_edges(call_tool, poi_ids, **kwargs))
    return edges, route_evidence, calls


# ---------------------------------------------------------------------------
# 1. Valid mode propagation through the actual ASGI endpoint
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "body_mode,expected,source",
    [(None, "car", "default"), ("car", "car", "explicit"),
     ("foot", "foot", "explicit")])
def test_http_mode_reaches_route_tool_scenario_and_response(
        monkeypatch, body_mode, expected, source):
    handlers = default_handlers(candidates=TWO_POIS, enrichments=_enrich())
    handlers["get_itinerary_route"] = _route_handler()
    body = dict(DEFAULT_BODY)
    body.pop("transport_mode", None)
    if body_mode is not None:
        body["transport_mode"] = body_mode

    captured = {}
    real_build = planning_adapter.build_scenario

    def capture_build(*args, **kwargs):
        inputs = real_build(*args, **kwargs)
        captured["inputs"] = inputs
        return inputs

    monkeypatch.setattr(planning_adapter, "build_scenario", capture_build)

    response, session = _run_http(
        monkeypatch, handlers, good_llm(_two_stop_plan()), body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"

    route_calls = [c for c in session.calls if c["tool"] == "get_itinerary_route"]
    assert len(route_calls) == 2  # every directed pair
    assert all(c["args"]["vehicle"] == expected for c in route_calls)

    route_evidence = payload["planning"]["route_evidence"]
    assert route_evidence["transport_mode"] == expected
    assert route_evidence["transport_mode_source"] == "request"
    assert route_evidence["failed"] == []
    assert len(route_evidence["records"]) == 2
    assert all(r["transport_mode"] == expected for r in route_evidence["records"])
    assert all(r["provenance"] == f"get_itinerary_route:mcp:{expected}"
               for r in route_evidence["records"])

    constraints = payload["planning"]["request_constraints"]
    assert constraints["transport_mode"] == expected
    assert constraints["transport_mode_source"] == source

    scenario = captured["inputs"].scenario
    assert scenario is not None
    assert scenario.route("poi_a", "poi_b").transport_mode == expected
    assert scenario.route("poi_b", "poi_a").transport_mode == expected
    assert {edge.transport_mode for edge in scenario.route_index.values()} == {expected}


# ---------------------------------------------------------------------------
# 2. Invalid requests fail closed before model/MCP and adapter calls
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("invalid", INVALID_MODES)
def test_http_invalid_mode_is_422_before_model_and_mcp(monkeypatch, invalid):
    handlers = default_handlers(candidates=TWO_POIS, enrichments=_enrich())
    handlers["get_itinerary_route"] = _route_handler()
    llm = good_llm(_two_stop_plan())

    response, session = _run_http(
        monkeypatch, handlers, llm, dict(DEFAULT_BODY, transport_mode=invalid))

    assert response.status_code == 422
    assert llm.calls == []
    assert session.calls == []


@pytest.mark.parametrize("invalid", INVALID_MODES)
def test_direct_collector_invalid_mode_raises_constant_before_tool(invalid):
    calls = []

    async def call_tool(name, args):  # pragma: no cover - must not be reached
        calls.append((name, args))
        return ok_json({"success": True})

    with pytest.raises(ValueError) as exc:
        asyncio.run(planning_adapter.collect_route_edges(
            call_tool, ["p1", "p2"], transport_mode=invalid))

    assert str(exc.value) == planning_adapter.INVALID_TRANSPORT_MODE
    assert calls == []


BASE_DICT_REQUEST = {
    "session_id": "sess-mode-direct",
    "travel_type": "self-explore",
    "num_travelers": 2,
    "start_date": "2026-01-01",
    "target_district": "District 1",
    "duration_days": 1,
    "budget_range": "unknown",
    "user_description": "synthetic",
}
EVIDENCE_MAP = _enrich()
CATEGORY_IDS = {"poi_a": ["cat_coffee"], "poi_b": ["cat_coffee"]}


def test_direct_validate_and_build_reject_invalid_mode_without_scenario():
    request = dict(BASE_DICT_REQUEST, transport_mode="bike")
    assert planning_adapter.validate_constraints(
        request, EVIDENCE_MAP, CATEGORY_IDS) == (
            "invalid_request", planning_adapter.INVALID_TRANSPORT_MODE)
    inputs = planning_adapter.build_scenario(
        request, EVIDENCE_MAP, CATEGORY_IDS, [], None)
    assert inputs.scenario is None
    assert inputs.build_error == (
        "invalid_request", planning_adapter.INVALID_TRANSPORT_MODE)


def test_direct_missing_mode_defaults_car_and_explicit_mode_is_recorded():
    default_inputs = planning_adapter.build_scenario(
        dict(BASE_DICT_REQUEST), EVIDENCE_MAP, CATEGORY_IDS, [], None)
    assert default_inputs.build_error is None
    assert default_inputs.request_constraints["transport_mode"] == "car"
    assert default_inputs.request_constraints["transport_mode_source"] == "default"

    foot_request = ItineraryRequest(**BASE_DICT_REQUEST, transport_mode="foot")
    foot_inputs = planning_adapter.build_scenario(
        foot_request, EVIDENCE_MAP, CATEGORY_IDS, [], None)
    assert foot_inputs.build_error is None
    assert foot_inputs.request_constraints["transport_mode"] == "foot"
    assert foot_inputs.request_constraints["transport_mode_source"] == "explicit"


def test_build_scenario_rejects_edge_mode_mismatch_via_contract():
    car_edge = {
        "from_poi_id": "poi_a", "to_poi_id": "poi_b",
        "raw_duration_seconds": 600, "duration_minutes": 10,
        "distance_km": "1.0", "raw_distance_meters": 1000,
        "transport_mode": "car", "provenance": "get_itinerary_route:mcp:car",
    }
    request = ItineraryRequest(**BASE_DICT_REQUEST, transport_mode="foot")
    inputs = planning_adapter.build_scenario(
        request, EVIDENCE_MAP, CATEGORY_IDS, [car_edge], None)
    assert inputs.scenario is None
    assert inputs.build_error is not None
    assert inputs.build_error[0] == "transport_mode_mismatch"


# ---------------------------------------------------------------------------
# 3. Optional profile/vehicle echo: exact, or fail closed
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("vehicle,profile", [
    ("car", ABSENT),          # vehicle disagrees
    (ABSENT, "car"),          # profile disagrees
    (None, ABSENT),           # null
    (ABSENT, None),           # null
    ({"mode": "foot"}, ABSENT),  # object
    ("bike", ABSENT),         # unsupported
    (MATCH, "car"),           # contradictory vehicle/profile
])
def test_foot_wrong_or_malformed_echo_refuses_edges(vehicle, profile):
    edges, route_evidence, calls = _collect(
        _route_handler(vehicle=vehicle, profile=profile), ["p1", "p2"],
        transport_mode="foot")

    assert edges == []
    assert len(calls) == 2
    # No silent fallback: every tool call still requested foot.
    assert all(args["vehicle"] == "foot" for _, args in calls)
    assert route_evidence.transport_mode == "foot"
    assert route_evidence.coverage == "partial"
    assert len(route_evidence.records) == 2
    assert all(r.status == "failed" for r in route_evidence.records)
    assert all(r.code == planning_adapter.ROUTE_PROFILE_MISMATCH
               for r in route_evidence.records)
    assert all(r.profile_echo == "mismatch" for r in route_evidence.records)
    assert all(r.transport_mode == "foot" for r in route_evidence.records)
    assert all(r.duration_minutes is None and r.distance_km is None
               for r in route_evidence.records)


def test_profile_mismatch_detail_is_sanitized_constant():
    marker = "SYNTHETIC_PROVIDER_MARKER_RT064_R1"
    edges, route_evidence, calls = _collect(
        _route_handler(vehicle={"untrusted": marker}), ["p1", "p2"],
        transport_mode="foot")

    assert edges == []
    assert len(calls) == 2
    assert all(args["vehicle"] == "foot" for _, args in calls)
    assert all(r.code == planning_adapter.ROUTE_PROFILE_MISMATCH
               for r in route_evidence.records)
    assert all(r.detail == planning_adapter.ROUTE_PROFILE_MISMATCH_DETAIL
               for r in route_evidence.records)
    assert marker not in json.dumps(route_evidence.as_dict(), sort_keys=True)


@pytest.mark.parametrize("vehicle,profile,expected_echo", [
    (MATCH, ABSENT, "matched"),
    (ABSENT, MATCH, "matched"),
    (MATCH, MATCH, "matched"),
    (ABSENT, ABSENT, "absent"),
])
def test_matching_or_absent_echo_accepts_requested_mode(
        vehicle, profile, expected_echo):
    edges, route_evidence, calls = _collect(
        _route_handler(vehicle=vehicle, profile=profile), ["p1", "p2"],
        transport_mode="foot")

    assert len(edges) == 2
    assert all(edge["transport_mode"] == "foot" for edge in edges)
    # Provenance says requested mode, never provider-confirmed when absent.
    assert all(edge["transport_mode_source"] == "request" for edge in edges)
    assert all(edge["profile_echo"] == expected_echo for edge in edges)
    assert all(edge["provenance"] == "get_itinerary_route:mcp:foot"
               for edge in edges)
    assert all(r.profile_echo == expected_echo for r in route_evidence.records)
    assert all(r.transport_mode == "foot" for r in route_evidence.records)
    assert all(args["vehicle"] == "foot" for _, args in calls)


def test_foot_raw_seconds_rounding_and_meters_are_unchanged():
    edges, _, _ = _collect(
        _route_handler(durations={"foot": 1.5}), ["p1", "p2"],
        transport_mode="foot")

    assert len(edges) == 2
    for edge in edges:
        assert edge["raw_duration_seconds"] == 90
        assert edge["duration_minutes"] == 2
        assert edge["raw_distance_meters"] == 1000
        assert Decimal(edge["distance_km"]) == Decimal("1.0")
        assert edge["transport_mode"] == "foot"


def test_http_foot_wrong_echo_yields_no_edges_and_failed_code(monkeypatch):
    handlers = default_handlers(candidates=TWO_POIS, enrichments=_enrich())
    handlers["get_itinerary_route"] = _route_handler(vehicle="car")
    body = dict(DEFAULT_BODY, transport_mode="foot")

    response, session = _run_http(
        monkeypatch, handlers, good_llm(_two_stop_plan()), body)

    assert response.status_code == 200
    payload = response.json()
    assert "planning" in payload  # mode is visible even on the no-route branch
    route_evidence = payload["planning"]["route_evidence"]
    assert route_evidence["transport_mode"] == "foot"
    assert route_evidence["succeeded"] == []
    assert route_evidence["attempted"] == 2
    assert len(route_evidence["failed"]) == 2
    assert all(f["code"] == planning_adapter.ROUTE_PROFILE_MISMATCH
               for f in route_evidence["failed"])
    assert all(r["status"] == "failed"
               for r in route_evidence["records"])
    assert payload["planning"]["request_constraints"]["transport_mode"] == "foot"
    route_calls = [c for c in session.calls if c["tool"] == "get_itinerary_route"]
    assert len(route_calls) == 2
    assert all(c["args"]["vehicle"] == "foot" for c in route_calls)


# ---------------------------------------------------------------------------
# 4. Delivered travel totals follow car vs foot evidence
# ---------------------------------------------------------------------------
def _run_mode(monkeypatch, mode):
    handlers = default_handlers(candidates=TWO_POIS, enrichments=_enrich())
    handlers["get_itinerary_route"] = _route_handler(
        durations={"car": 30.0, "foot": 120.0})
    body = dict(DEFAULT_BODY, transport_mode=mode)
    response, _ = _run_http(
        monkeypatch, handlers, good_llm(_two_stop_plan()), body)
    assert response.status_code == 200
    return response.json()


def test_car_and_foot_delivered_travel_totals_differ(monkeypatch):
    car = _run_mode(monkeypatch, "car")
    foot = _run_mode(monkeypatch, "foot")

    assert car["status"] == "success" and foot["status"] == "success"
    assert car["planning"]["totals"]["travel_minutes"] == 30
    assert foot["planning"]["totals"]["travel_minutes"] == 120

    car_records = car["planning"]["route_evidence"]["records"]
    foot_records = foot["planning"]["route_evidence"]["records"]
    assert all(r["raw_duration_seconds"] == 1800 for r in car_records)
    assert all(r["raw_duration_seconds"] == 7200 for r in foot_records)
    # Distance provenance is unchanged by mode.
    assert all(r["raw_distance_meters"] == 1000
               for r in car_records + foot_records)
    assert all(r["transport_mode"] == "car" for r in car_records)
    assert all(r["transport_mode"] == "foot" for r in foot_records)


def test_failed_foot_leg_stays_unknown_partial_without_car_substitute(monkeypatch):
    handlers = default_handlers(candidates=TWO_POIS, enrichments=_enrich())
    handlers["get_itinerary_route"] = _route_handler(
        fail_pairs={("poi_a", "poi_b")})
    body = dict(DEFAULT_BODY, transport_mode="foot")

    response, session = _run_http(
        monkeypatch, handlers, good_llm(_two_stop_plan()), body)

    assert response.status_code == 200
    payload = response.json()
    route_evidence = payload["planning"]["route_evidence"]
    assert route_evidence["transport_mode"] == "foot"
    assert route_evidence["coverage"] == "partial"
    failed_pair = [f for f in route_evidence["failed"]
                   if f["pair"] == ["poi_a", "poi_b"]]
    assert failed_pair and failed_pair[0]["code"] == "success_false"
    failed_record = next(r for r in route_evidence["records"]
                         if (r["from_poi_id"], r["to_poi_id"]) == ("poi_a", "poi_b"))
    assert failed_record["status"] == "failed"
    assert failed_record["duration_minutes"] is None
    assert failed_record["distance_km"] is None
    assert failed_record["transport_mode"] == "foot"
    assert not any(r["transport_mode"] == "car"
                   for r in route_evidence["records"])
    assert all(c["args"]["vehicle"] == "foot"
               for c in session.calls if c["tool"] == "get_itinerary_route")


# ---------------------------------------------------------------------------
# 5. Source-scope foot flow keeps selection/source provenance
# ---------------------------------------------------------------------------
SOURCE_SELECTION = {
    "dataset_namespace": "hcm_primary_geojson",
    "input_sha256": "a" * 64,
    "source_area_id": "source_area_v1:" + "b" * 64,
}
SOURCE_AREA_LABEL = "Go Vap, HCMC"


def _source_context():
    return {
        "dataset_namespace": SOURCE_SELECTION["dataset_namespace"],
        "input_sha256": SOURCE_SELECTION["input_sha256"],
        "source_area_id": SOURCE_SELECTION["source_area_id"],
        "raw_city": "HCMC",
        "raw_area": "Go Vap",
        "source_area_label": SOURCE_AREA_LABEL,
        "area_assignment": "qualified",
        "current_admin_status": "unverified_source_area",
        "current_boundary_uncertainty": "Source label is not a current boundary.",
        "lineage_reference": "graph:POI.source_metadata_json#" + "c" * 64,
        "qualification": "exact_source_snapshot_tuple",
    }


def _source_evidence(poi_id):
    return {
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
        "source_context": _source_context(),
    }


def _source_handlers(route):
    enrichments = {pid: _source_evidence(pid) for pid in TWO_POIS}

    def resolve(_args):
        raise AssertionError("source mode must not resolve current geography")

    def get_categories(_args):
        return ok_json({"success": True,
                        "categories": [{"id": "cat_coffee", "name": "Cafe"}]})

    def explore(args):
        assert args.get("source_scope") == SOURCE_SELECTION
        assert "city_id" not in args and "district_id" not in args
        ids = TWO_POIS if args.get("category_id") is None else TWO_POIS
        return ok_json({"success": True, "count": len(ids),
                        "results": [{"id": pid} for pid in ids]})

    def details(args):
        item = enrichments.get(args.get("poi_id"))
        if item is None:
            return ok_json({"success": False, "result": None,
                            "detail": "not found"})
        return ok_json({"success": True, "result": item})

    return {
        "resolve_geographic_id": resolve,
        "get_available_categories": get_categories,
        "explore_pois": explore,
        "get_poi_details": details,
        "get_itinerary_route": route,
    }


def test_source_scope_foot_flow_keeps_selection_and_source_provenance(monkeypatch):
    handlers = _source_handlers(_route_handler(profile=MATCH))
    body = dict(DEFAULT_BODY)
    body.pop("target_district", None)
    body["source_scope"] = SOURCE_SELECTION
    body["transport_mode"] = "foot"

    response, session = _run_http(
        monkeypatch, handlers, good_llm(_two_stop_plan()), body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["grounding"]["scope_mode"] == "source_snapshot_area"
    assert payload["grounding"]["source_scope"] == SOURCE_SELECTION

    planning = payload["planning"]
    assert planning["source_scope"] == SOURCE_SELECTION
    assert planning["request_constraints"]["source_scope"] == SOURCE_SELECTION
    assert planning["request_constraints"]["scope_mode"] == "source_snapshot_area"
    assert planning["request_constraints"]["transport_mode"] == "foot"
    assert planning["route_evidence"]["transport_mode"] == "foot"
    assert all(r["transport_mode"] == "foot"
               for r in planning["route_evidence"]["records"])
    assert all(c["args"]["vehicle"] == "foot"
               for c in session.calls if c["tool"] == "get_itinerary_route")
    assert not any(c["tool"] == "resolve_geographic_id" for c in session.calls)

    delivered_poi = payload["reply"]["stops"][0]["poi"]
    assert delivered_poi["source_snapshot_area"]["source_area_id"] == \
        SOURCE_SELECTION["source_area_id"]
    assert delivered_poi["address"]["city"] is None
