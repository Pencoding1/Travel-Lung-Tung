"""ScopeGate unit contract: arguments sent and evidence shown.

These are pure-function tests around ``domains.source_gate.ScopeGate``; they
prove the server rebuilds tool arguments and re-qualifies tool results before
the model, trace or memory can observe them.
"""

import json

from domains import grounding, source_gate
from helpers_core_flow import (
    SELECTION_A,
    SELECTION_B,
    source_detail,
    source_explore_record,
)


def _gate(**overrides):
    values = {"source_selection": dict(SELECTION_A), "transport_mode": "car"}
    values.update(overrides)
    return source_gate.ScopeGate(**values)


def _payload(result):
    return json.loads(result.content[0].text)


def test_explore_injects_the_exact_selection():
    gate = _gate()
    decision = gate.prepare("explore_pois", {"limit": 5})
    assert decision.ok
    assert decision.args["source_scope"] == SELECTION_A
    assert decision.args["limit"] == 5


def test_explore_refuses_a_different_model_selector():
    gate = _gate()
    decision = gate.prepare("explore_pois", {"source_scope": dict(SELECTION_B)})
    assert not decision.ok
    assert decision.code == source_gate.SOURCE_SELECTION_MISMATCH


def test_explore_refuses_discovery_and_admin_filters():
    gate = _gate()
    assert not gate.prepare(
        "explore_pois",
        {"source_discovery": "snapshots"}).ok
    for args in ({"city_id": "hcmc"}, {"district_id": "quan_1"},
                 {"street_id": "le_loi"}):
        decision = gate.prepare("explore_pois", args)
        assert not decision.ok
        assert decision.code == source_gate.SOURCE_SCOPE_VIOLATION


def test_legacy_mode_refuses_source_arguments():
    gate = _gate(source_selection=None)
    decision = gate.prepare("explore_pois", {"source_scope": dict(SELECTION_A)})
    assert not decision.ok
    assert decision.code == source_gate.SOURCE_DISCOVERY_BLOCKED


def test_resolver_is_blocked_in_source_mode_only():
    assert not _gate().prepare("resolve_geographic_id", {"keyword": "Quận 1"}).ok
    legacy = _gate(source_selection=None)
    assert legacy.prepare("resolve_geographic_id", {"keyword": "Quận 1"}).ok


def test_details_require_a_discovered_id_in_source_mode():
    gate = _gate()
    decision = gate.prepare("get_poi_details", {"poi_id": "poi_unknown"})
    assert not decision.ok
    assert decision.code == source_gate.UNVERIFIED_POI_ID

    explore = gate.filter_result(
        "explore_pois", {"source_scope": dict(SELECTION_A)},
        _tool((
            {"success": True, "source_scope": dict(SELECTION_A),
             "results": [source_explore_record("poi_a", "A", SELECTION_A)]}
        )))
    assert _payload(explore)["results"][0]["id"] == "poi_a"
    assert gate.prepare("get_poi_details", {"poi_id": "poi_a"}).ok


def test_details_filter_drops_out_of_scope_nearby_entries():
    gate = _gate()
    gate.filter_result(
        "explore_pois", {"source_scope": dict(SELECTION_A)},
        _tool({"success": True, "source_scope": dict(SELECTION_A),
               "results": [source_explore_record("poi_a", "A", SELECTION_A)]}))
    detail = source_detail(
        "poi_a", "A", SELECTION_A,
        nearby=[{"poi": {"id": "poi_a"}, "distance": 12.0},
                {"poi": {"id": "foreign_poi"}, "distance": 9.0}])
    result = gate.filter_result("get_poi_details", {"poi_id": "poi_a"},
                                _tool({"success": True, "result": detail}))
    payload = _payload(result)
    nearby_ids = [entry["poi"]["id"] for entry in payload["result"]["NEAR_BY"]]
    assert nearby_ids == ["poi_a"]
    assert payload["result"]["nearby_filtered_out_of_scope"] == 1
    assert "foreign_poi" not in result.content[0].text


def test_details_filter_rejects_a_mixed_source_context():
    gate = _gate()
    gate.filter_result(
        "explore_pois", {"source_scope": dict(SELECTION_A)},
        _tool({"success": True, "source_scope": dict(SELECTION_A),
               "results": [source_explore_record("poi_a", "A", SELECTION_A)]}))
    detail = source_detail("poi_a", "A", SELECTION_B)
    result = gate.filter_result("get_poi_details", {"poi_id": "poi_a"},
                                _tool({"success": True, "result": detail}))
    payload = _payload(result)
    assert payload["success"] is False
    assert payload["code"] == source_gate.SOURCE_SCOPE_VIOLATION
    assert gate.verified_ids == set()


def test_explore_filter_drops_unqualified_records():
    gate = _gate()
    unqualified = source_explore_record("poi_x", "X", SELECTION_B)
    result = gate.filter_result(
        "explore_pois", {"source_scope": dict(SELECTION_A)},
        _tool({"success": True, "source_scope": dict(SELECTION_A),
               "results": [source_explore_record("poi_a", "A", SELECTION_A),
                           unqualified]}))
    payload = _payload(result)
    assert [item["id"] for item in payload["results"]] == ["poi_a"]
    assert payload["filtered_out_of_scope"] == 1
    assert gate.discovered_ids == {"poi_a"}


def test_explore_filter_rejects_a_different_echoed_selection():
    gate = _gate()
    result = gate.filter_result(
        "explore_pois", {"source_scope": dict(SELECTION_A)},
        _tool({"success": True, "source_scope": dict(SELECTION_B),
               "results": [source_explore_record("poi_a", "A", SELECTION_A)]}))
    payload = _payload(result)
    assert payload["success"] is False
    assert payload["code"] == source_gate.SOURCE_SELECTION_MISMATCH
    assert gate.discovered_ids == set()


def test_route_requires_explicit_mode_and_verified_ids():
    gate = _gate(transport_mode="foot")
    decision = gate.prepare("get_itinerary_route",
                            {"ordered_poi_ids": ["poi_a", "poi_b"],
                             "vehicle": "car"})
    assert not decision.ok
    assert decision.code == source_gate.TRANSPORT_MODE_MISMATCH

    decision = gate.prepare("get_itinerary_route",
                            {"ordered_poi_ids": ["poi_a", "poi_b"]})
    assert not decision.ok
    assert decision.code == source_gate.ROUTE_IDS_UNVERIFIED

    gate.discovered_ids.update({"poi_a", "poi_b"})
    gate.verified_ids.update({"poi_a", "poi_b"})
    decision = gate.prepare("get_itinerary_route",
                            {"ordered_poi_ids": ["poi_a", "poi_b"],
                             "vehicle": "foot"})
    assert decision.ok
    assert decision.args["vehicle"] == "foot"
    assert gate.route_calls[-1]["vehicle"] == "foot"


def _verified_route_gate(vehicle="foot"):
    gate = _gate(transport_mode=vehicle)
    gate.discovered_ids.update({"poi_a", "poi_b"})
    gate.verified_ids.update({"poi_a", "poi_b"})
    decision = gate.prepare("get_itinerary_route", {
        "ordered_poi_ids": ["poi_a", "poi_b"], "vehicle": vehicle})
    assert decision.ok
    return gate


def test_route_evidence_requires_a_valid_actual_payload():
    gate = _verified_route_gate()
    result = gate.filter_result("get_itinerary_route", {
        "ordered_poi_ids": ["poi_a", "poi_b"], "vehicle": "foot"}, _tool({
            "success": True,
            "distance_km": 1.25,
            "time_minutes": 18.0,
            "stops_mapped": 2,
            "stops": [
                {"id": "poi_a", "latitude": 10.77, "longitude": 106.70},
                {"id": "poi_b", "latitude": 10.78, "longitude": 106.71},
            ],
        }))
    assert _payload(result)["success"] is True
    evidence = gate.as_meta()["route_evidence"]
    assert evidence["success"] is True
    assert evidence["distance_km"] == 1.25
    assert evidence["time_minutes"] == 18.0
    assert evidence["stops_mapped"] == 2
    assert evidence["ordered_poi_ids"] == ["poi_a", "poi_b"]
    assert evidence["vehicle"] == "foot"
    assert evidence["source_scope"] == SELECTION_A
    assert gate.route_calls[-1]["success"] is True


def test_route_evidence_requires_actual_success():
    gate = _verified_route_gate()
    gate.filter_result("get_itinerary_route", {
        "ordered_poi_ids": ["poi_a", "poi_b"], "vehicle": "foot"},
        _tool({"success": False, "detail": "synthetic failure"}))
    assert gate.as_meta()["route_evidence"] is None
    assert gate.route_calls[-1]["success"] is False
    assert gate.route_calls[-1]["error_code"] == "route_not_success"


def test_route_evidence_is_never_successful_on_bad_numeric_or_ids():
    specs = [
        ("route_invalid_numeric", {"distance_km": -1, "time_minutes": 1}),
        ("route_invalid_numeric", {"distance_km": 1, "time_minutes": "fast"}),
        ("route_stops_mismatch", {"distance_km": 1, "time_minutes": 1,
                                  "stops_mapped": 1,
                                  "stops": [{"id": "poi_a", "latitude": 10.0,
                                             "longitude": 106.0}]}),
        ("route_stops_mismatch", {"distance_km": 1, "time_minutes": 1,
                                  "stops_mapped": 2,
                                  "stops": [{"id": "poi_a", "latitude": 10.0,
                                             "longitude": 106.0},
                                            {"id": "poi_foreign",
                                             "latitude": 10.1,
                                             "longitude": 106.1}]}),
    ]
    for expected_code, extra in specs:
        gate = _verified_route_gate()
        payload = {"success": True, **extra}
        gate.filter_result("get_itinerary_route", {
            "ordered_poi_ids": ["poi_a", "poi_b"], "vehicle": "foot"},
            _tool(payload))
        meta = gate.as_meta()
        assert meta["route_evidence"] is None
        assert gate.route_calls[-1]["success"] is False
        assert gate.route_calls[-1]["error_code"] == expected_code


def test_meta_is_bounded_for_a_hostile_model():
    gate = _gate(source_selection=None)
    for _ in range(100):
        gate.prepare("explore_pois", {"source_discovery": "snapshots"})
    meta = gate.as_meta()
    assert len(meta["rejections"]) <= source_gate.MAX_RECORDED_REJECTIONS
    assert meta["mode"] == grounding.SCOPE_MODE_CURRENT
    assert "api_key" not in json.dumps(meta).lower()


class _Text:
    def __init__(self, text):
        self.text = text


class _Result:
    def __init__(self, text):
        self.content = [_Text(text)]
        self.isError = False


def _tool(payload):
    return _Result(json.dumps(payload))
