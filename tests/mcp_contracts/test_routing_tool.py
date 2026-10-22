"""Routing tool contract tests using an injected ``httpx.MockTransport``.

No network call is made. The transport handler records the exact request so the
parameter encoding, profile and absence-of-HTTP-on-abort can be asserted.
"""

import json

import httpx
import pytest

import app.api.mcp.tools as tools
from mcp_fakes import FakePOIRepository, FakeUnitOfWork, poi_stub


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    tools.reset_uow_factory()
    tools.reset_http_client_factory()
    monkeypatch.delenv("GRAPHHOPPER_URL", raising=False)
    monkeypatch.delenv("GRAPHHOPPER_PROFILES", raising=False)
    yield
    tools.reset_uow_factory()
    tools.reset_http_client_factory()


def _parse(raw):
    return json.loads(raw)


def _set_pois(pois_by_id):
    tools.set_uow_factory(lambda: FakeUnitOfWork(FakePOIRepository(pois_by_id=pois_by_id)))


def _set_transport(handler):
    transport = httpx.MockTransport(handler)
    tools.set_http_client_factory(lambda: httpx.Client(transport=transport))


def _ok_route(distance=1234.5, time_ms=90000.0, instructions=None):
    paths = [{
        "distance": distance,
        "time": time_ms,
        "instructions": instructions if instructions is not None else [{"text": "Go"}],
    }]
    return lambda request: httpx.Response(200, json={"paths": paths})


def test_fewer_than_two_stops_is_invalid():
    _set_pois({})
    payload = _parse(tools.get_itinerary_route(["p1"]))
    assert payload["success"] is False
    assert payload["code"] == "invalid_request"


def test_wrong_profile_is_invalid_and_no_http_call():
    _set_pois({"p1": poi_stub(), "p2": poi_stub(11.0, 107.0)})

    def explode(request):  # pragma: no cover - must never run
        raise AssertionError("HTTP must not be called for a rejected profile")

    _set_transport(explode)
    payload = _parse(tools.get_itinerary_route(["p1", "p2"], vehicle="foot"))
    assert payload["success"] is False
    assert payload["code"] == "invalid_request"


def test_explicitly_configured_profile_is_accepted(monkeypatch):
    monkeypatch.setenv("GRAPHHOPPER_PROFILES", "car,foot")
    _set_pois({"p1": poi_stub(), "p2": poi_stub(11.0, 107.0)})
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"paths": [{"distance": 100.0, "time": 1000.0}]})

    _set_transport(handler)
    payload = _parse(tools.get_itinerary_route(["p1", "p2"], vehicle="foot"))
    assert payload["success"] is True
    assert seen[0].url.params.get("profile") == "foot"


def test_missing_middle_stop_aborts_with_no_http_call():
    _set_pois({"p1": poi_stub(), "p3": poi_stub(11.0, 107.0)})

    def explode(request):  # pragma: no cover - must never run
        raise AssertionError("HTTP must not be called when a stop is unresolved")

    _set_transport(explode)
    payload = _parse(tools.get_itinerary_route(["p1", "p2", "p3"]))
    assert payload["success"] is False
    assert payload["code"] == "stops_unresolved"
    assert payload["failing_stops"] == [{"id": "p2", "reason": "not_found"}]


def test_missing_coordinates_aborts_with_no_http_call():
    _set_pois({"p1": poi_stub(), "p2": poi_stub(latitude=None, longitude=None)})

    def explode(request):  # pragma: no cover
        raise AssertionError("HTTP must not be called when coordinates are missing")

    _set_transport(explode)
    payload = _parse(tools.get_itinerary_route(["p1", "p2"]))
    assert payload["success"] is False
    assert payload["code"] == "stops_unresolved"
    assert payload["failing_stops"][0]["reason"] == "missing_coordinates"


def test_out_of_range_coordinate_aborts():
    _set_pois({"p1": poi_stub(95.0, 106.0), "p2": poi_stub(11.0, 107.0)})
    _set_transport(lambda request: httpx.Response(200, json={"paths": []}))
    payload = _parse(tools.get_itinerary_route(["p1", "p2"]))
    assert payload["success"] is False
    assert payload["code"] == "stops_unresolved"
    assert payload["failing_stops"] == [{"id": "p1", "reason": "missing_coordinates"}]


def test_zero_coordinates_are_accepted_and_encoded():
    _set_pois({"p1": poi_stub(0.0, 0.0), "p2": poi_stub(0.0, 0.0)})
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"paths": [{"distance": 0.0, "time": 0.0}]})

    _set_transport(handler)
    payload = _parse(tools.get_itinerary_route(["p1", "p2"]))
    assert payload["success"] is True
    assert payload["stops_mapped"] == 2
    assert seen[0].url.params.get_list("point") == ["0.0,0.0", "0.0,0.0"]


def test_distance_and_time_are_unrounded():
    _set_pois({"p1": poi_stub(), "p2": poi_stub(11.0, 107.0)})
    _set_transport(_ok_route(distance=1234.5, time_ms=90000.0))
    payload = _parse(tools.get_itinerary_route(["p1", "p2"]))
    assert payload["distance_km"] == pytest.approx(1.2345)
    assert payload["time_minutes"] == pytest.approx(1.5)


def test_stops_are_ordered_and_count_is_exact():
    _set_pois({
        "p1": poi_stub(10.0, 106.0),
        "p2": poi_stub(11.0, 107.0),
        "p3": poi_stub(12.0, 108.0),
    })
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"paths": [{"distance": 10.0, "time": 60000.0}]})

    _set_transport(handler)
    payload = _parse(tools.get_itinerary_route(["p3", "p1", "p2"]))
    assert payload["stops_mapped"] == 3
    assert [s["id"] for s in payload["stops"]] == ["p3", "p1", "p2"]
    assert seen[0].url.params.get_list("point") == ["12.0,108.0", "10.0,106.0", "11.0,107.0"]


def test_graphhopper_url_is_configurable():
    import os

    os.environ["GRAPHHOPPER_URL"] = "http://example.test/route"
    try:
        _set_pois({"p1": poi_stub(), "p2": poi_stub(11.0, 107.0)})
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(200, json={"paths": [{"distance": 1.0, "time": 1000.0}]})

        _set_transport(handler)
        tools.get_itinerary_route(["p1", "p2"])
        assert seen[0].url.host == "example.test"
        assert seen[0].url.path == "/route"
    finally:
        os.environ.pop("GRAPHHOPPER_URL", None)


def test_http_failure_is_explicit_error():
    _set_pois({"p1": poi_stub(), "p2": poi_stub(11.0, 107.0)})
    _set_transport(lambda request: httpx.Response(400, json={"message": "bad point"}))
    payload = _parse(tools.get_itinerary_route(["p1", "p2"]))
    assert payload["success"] is False
    assert payload["code"] == "route_failed"
    assert "bad point" not in json.dumps(payload)


def test_empty_paths_is_no_route():
    _set_pois({"p1": poi_stub(), "p2": poi_stub(11.0, 107.0)})
    _set_transport(lambda request: httpx.Response(200, json={"paths": []}))
    payload = _parse(tools.get_itinerary_route(["p1", "p2"]))
    assert payload["success"] is False
    assert payload["code"] == "no_route"


def test_negative_time_is_rejected():
    _set_pois({"p1": poi_stub(), "p2": poi_stub(11.0, 107.0)})
    _set_transport(_ok_route(distance=100.0, time_ms=-5.0))
    payload = _parse(tools.get_itinerary_route(["p1", "p2"]))
    assert payload["success"] is False
    assert payload["code"] == "route_failed"


def test_malformed_paths_payload_is_rejected():
    _set_pois({"p1": poi_stub(), "p2": poi_stub(11.0, 107.0)})
    _set_transport(lambda request: httpx.Response(200, json={"paths": ["not-a-dict"]}))
    payload = _parse(tools.get_itinerary_route(["p1", "p2"]))
    assert payload["success"] is False
    assert payload["code"] == "route_failed"
