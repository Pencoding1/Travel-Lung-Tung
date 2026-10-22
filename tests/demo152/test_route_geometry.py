"""DEMO-152 actual road geometry and selected-leg exposure (synthetic)."""

import json

from domains import planning_adapter
from domains.planning_adapter import RouteEvidence, RouteRecord


def _line(coords):
    return {"type": "LineString", "coordinates": coords}


def test_tool_geometry_validator_rejects_absent_malformed_nan_and_oversize():
    from app.api.mcp.tools import MAX_ROUTE_GEOMETRY_POINTS, _validated_route_geometry

    assert _validated_route_geometry(None) == (None, "missing")
    assert _validated_route_geometry({"type": "Point", "coordinates": [1, 2]}) == \
        (None, "malformed")
    assert _validated_route_geometry({"type": "LineString", "coordinates": [[1, 2]]}) == \
        (None, "malformed")
    nan = _validated_route_geometry(
        {"type": "LineString", "coordinates": [[1.0, 2.0], [float("nan"), 3.0]]})
    assert nan == (None, "malformed")
    too_many = {"type": "LineString", "coordinates": [[1.0, 2.0]] * (
        MAX_ROUTE_GEOMETRY_POINTS + 1)}
    assert _validated_route_geometry(too_many) == (None, "malformed")
    valid, status = _validated_route_geometry(
        {"type": "LineString", "coordinates": [[106.7, 10.7], [106.71, 10.71]]})
    assert status == "available"
    assert valid["coordinates"][0] == [106.7, 10.7]


def test_route_records_keep_geometry_private_from_candidate_evidence():
    geometry = _line([[106.7, 10.7], [106.8, 10.8]])
    record = RouteRecord("a", "b", "success", duration_minutes=5,
                         distance_km="1.2", transport_mode="car",
                         geometry=geometry, instructions=["Turn right"])
    evidence = RouteEvidence(records=[record], transport_mode="car")
    dumped = evidence.as_dict()
    assert dumped["records"][0]["status"] == "success"
    assert "geometry" not in json.dumps(dumped)
    assert "Turn right" not in json.dumps(dumped)


def test_geometry_is_only_for_selected_directed_day_legs():
    a_geo = _line([[106.70, 10.70], [106.71, 10.71]])
    b_geo = _line([[106.71, 10.71], [106.72, 10.72]])
    cross_geo = _line([[106.72, 10.72], [106.73, 10.73]])
    records = [
        RouteRecord("a", "b", "success", transport_mode="car",
                    geometry=a_geo, instructions=["Straight"]),
        RouteRecord("b", "c", "success", transport_mode="car", geometry=b_geo),
        # reverse direction must not be reused for a->b
        RouteRecord("b", "a", "success", transport_mode="car", geometry=cross_geo),
        # selected pair but another mode
        RouteRecord("c", "d", "success", transport_mode="foot", geometry=cross_geo),
        RouteRecord("a", "c", "success", transport_mode="car"),  # geometry missing
    ]
    evidence = RouteEvidence(records=records, transport_mode="car")
    days = [
        {"day_id": "d1", "poi_ids": ["a", "b"]},
        {"day_id": "d2", "poi_ids": ["c", "d"]},
    ]

    payload = planning_adapter.selected_plan_day_route_geometry(
        days, evidence, transport_mode="car")

    assert payload["type"] == "FeatureCollection"
    props = [feature["properties"] for feature in payload["features"]]
    assert [(p["day_id"], p["from_poi_id"], p["to_poi_id"]) for p in props] == [
        ("d1", "a", "b")]
    assert props[0]["transport_mode"] == "car"
    assert props[0]["provenance"] == "graphhopper"
    assert payload["missing_geometry_count"] == 1
    assert payload["missing_legs"][0]["day_id"] == "d2"
    assert payload["instructions"][0]["steps"] == ["Straight"]
    assert payload["straight_line_fallback"] is False


def test_no_geometry_yields_empty_features_not_a_straight_line():
    evidence = RouteEvidence(
        records=[RouteRecord("a", "b", "success", transport_mode="car")],
        transport_mode="car")
    payload = planning_adapter.selected_plan_day_route_geometry(
        [{"day_id": "d1", "poi_ids": ["a", "b"]}], evidence,
        transport_mode="car")
    assert payload["features"] == []
    assert payload["missing_geometry_count"] == 1
