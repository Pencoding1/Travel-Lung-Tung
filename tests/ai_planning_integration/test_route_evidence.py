"""Adapter-level route-evidence collection contract (OC-016).

Exercises the real ``planning_adapter.collect_route_edges`` against scripted
``get_itinerary_route`` payloads: success parsing with ceil-minute/raw-second and
meter provenance, exact ordered-id validation, provider errors, transport
errors, and the explicit bounded pair cap. No network call is made.
"""

import asyncio
from decimal import Decimal

from domains import planning_adapter
from domains.planning.contracts import ceil_minutes_from_seconds
from helpers_planning_integration import ok_json, route_handler


def _collect(handler, poi_ids, **kwargs):
    calls = []

    async def call_tool(name, args):
        calls.append((name, dict(args)))
        return handler(args)

    edges, evidence = asyncio.run(
        planning_adapter.collect_route_edges(call_tool, poi_ids, **kwargs))
    return edges, evidence, calls


def test_success_parses_distance_time_and_reconciles_provenance():
    edges, evidence, calls = _collect(
        route_handler(duration_minutes=1.5, distance_km=1.234), ["p1", "p2"])

    # Two nodes produce both directed pairs.
    assert len(edges) == 2
    edge = next(e for e in edges if e["from_poi_id"] == "p1")
    assert edge["to_poi_id"] == "p2"
    assert edge["raw_duration_seconds"] == 90
    assert edge["duration_minutes"] == 2 == ceil_minutes_from_seconds(90)
    assert edge["raw_distance_meters"] == 1234
    assert Decimal(edge["distance_km"]) == Decimal("1.234")
    assert edge["transport_mode"] == "car"
    assert edge["provenance"] == planning_adapter.ROUTE_PROVENANCE

    assert evidence.coverage == "complete"
    assert set(evidence.attempted_pairs) == {("p1", "p2"), ("p2", "p1")}
    assert calls[0][0] == "get_itinerary_route"
    assert calls[0][1]["vehicle"] == "car"
    assert set(calls[0][1]["ordered_poi_ids"]) == {"p1", "p2"}


def test_provider_error_is_recorded_not_substituted():
    edges, evidence, _ = _collect(
        route_handler(provider_error=True), ["p1", "p2"])

    assert edges == []
    assert evidence.coverage == "partial"
    record = evidence.records[0]
    assert record.status == "failed"
    assert record.duration_minutes is None
    assert record.distance_km is None


def test_ordered_ids_mismatch_is_rejected():
    edges, evidence, _ = _collect(
        route_handler(ordered_override=["ghost_a", "ghost_b"]), ["p1", "p2"])

    assert edges == []
    assert all(r.status == "failed" for r in evidence.records)
    assert all(r.code == "ordered_ids_mismatch" for r in evidence.records)


def test_stops_mapped_mismatch_is_rejected():
    def handler(args):
        return ok_json({"success": True, "distance_km": 1.0, "time_minutes": 5.0,
                        "stops_mapped": 99, "stops": [{"id": p} for p in args["ordered_poi_ids"]]})

    edges, evidence, _ = _collect(handler, ["p1", "p2"])
    assert edges == []
    assert evidence.records[0].code == "stops_mapped_mismatch"


def test_missing_distance_or_time_is_rejected():
    def handler(args):
        return ok_json({"success": True, "distance_km": None, "time_minutes": 5.0})

    edges, evidence, _ = _collect(handler, ["p1", "p2"])
    assert edges == []
    assert evidence.records[0].code == "malformed_route"


def test_transport_exception_is_recorded_and_never_raised():
    async def call_tool(name, args):
        raise RuntimeError("boom")

    edges, evidence = asyncio.run(
        planning_adapter.collect_route_edges(call_tool, ["p1", "p2"]))
    assert edges == []
    assert evidence.records[0].status == "failed"
    assert evidence.records[0].code == "route_transport_error"
    assert evidence.records[0].detail == "RuntimeError"


def test_pair_cap_is_explicit_and_not_silent():
    ids = ["p1", "p2", "p3", "p4"]
    # 4 nodes -> 12 directed pairs; cap at 5.
    edges, evidence, calls = _collect(route_handler(), ids, max_pairs=5)
    assert evidence.cap_reason == planning_adapter.ROUTE_CAP_REASON
    assert len(evidence.selected_pairs) == 5
    assert len(evidence.skipped_pairs) == 7
    assert evidence.attempted_pairs == evidence.selected_pairs
    assert len(calls) == 5
    assert evidence.coverage == "partial"


def test_single_candidate_needs_no_route_calls():
    edges, evidence, calls = _collect(route_handler(), ["p1"])
    assert edges == [] and calls == []
    assert evidence.coverage == "empty"


def _collect_one(handler):
    edges, evidence, _ = _collect(handler, ["p1", "p2"])
    return edges, evidence


def test_present_empty_stops_is_a_malformed_binding():
    def handler(args):
        return ok_json({"success": True, "distance_km": 1.0, "time_minutes": 5.0,
                        "stops_mapped": 2, "stops": []})

    edges, evidence = _collect_one(handler)
    assert edges == []
    assert evidence.records[0].code == "malformed_stops"


def test_present_non_list_stops_is_a_malformed_binding():
    def handler(args):
        return ok_json({"success": True, "distance_km": 1.0, "time_minutes": 5.0,
                        "stops_mapped": 2, "stops": {"id": "p1"}})

    edges, evidence = _collect_one(handler)
    assert edges == []
    assert evidence.records[0].code == "malformed_stops"


def test_present_stop_entry_missing_id_is_a_malformed_binding():
    def handler(args):
        return ok_json({"success": True, "distance_km": 1.0, "time_minutes": 5.0,
                        "stops_mapped": 2, "stops": [{"id": "p1"}, {"latitude": 1.0}]})

    edges, evidence = _collect_one(handler)
    assert edges == []
    assert evidence.records[0].code == "malformed_stops"


def test_absent_stops_is_accepted_for_upstream_compatibility():
    def handler(args):
        return ok_json({"success": True, "distance_km": 1.0, "time_minutes": 5.0})

    edges, evidence = _collect_one(handler)
    assert len(edges) == 2
    assert all(r.status == "success" for r in evidence.records)
    assert all(r.stops_mapped is None for r in evidence.records)
