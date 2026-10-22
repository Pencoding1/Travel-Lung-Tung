"""T060: routing mode per profile — measured behaviour, no silent fallback.

Measured on the running engine (GraphHopper 11.1, config builds CH for ``car``
only): ``profile=foot`` without ``ch.disable=true`` answers HTTP 400
("Disable CH using ch.disable=true; available CH profiles: [car]"), while
``foot`` with ``ch.disable=true`` answers 200. The tool must therefore send
``ch.disable`` for profiles without a built CH, keep ``car`` byte-identical, and
never invent a straight-line distance when the provider fails.
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
    monkeypatch.delenv("GRAPHHOPPER_CH_PROFILES", raising=False)
    yield
    tools.reset_uow_factory()
    tools.reset_http_client_factory()


def _set_pois(pois_by_id):
    tools.set_uow_factory(
        lambda: FakeUnitOfWork(FakePOIRepository(pois_by_id=pois_by_id)))


def _capture(handler):
    seen = []

    def wrapper(request):
        seen.append(request)
        return handler(request)

    tools.set_http_client_factory(
        lambda: httpx.Client(transport=httpx.MockTransport(wrapper)))
    return seen


def _ok(request):
    return httpx.Response(
        200, json={"paths": [{"distance": 1234.5, "time": 90000.0,
                              "instructions": [{"text": "Go"}]}]})


def _parse(raw):
    return json.loads(raw)


def _query(request):
    return dict(request.url.params)


def test_car_keeps_existing_params_without_ch_disable():
    _set_pois({"p1": poi_stub(), "p2": poi_stub(11.0, 107.0)})
    seen = _capture(_ok)
    payload = _parse(tools.get_itinerary_route(["p1", "p2"], vehicle="car"))
    assert payload["success"] is True
    params = _query(seen[0])
    assert params["profile"] == "car"
    assert "ch.disable" not in params
    assert seen[0].url.params.get_list("point") == ["10.0,106.0", "11.0,107.0"]


def test_foot_without_built_ch_sends_ch_disable(monkeypatch):
    monkeypatch.setenv("GRAPHHOPPER_PROFILES", "car,foot")
    _set_pois({"p1": poi_stub(), "p2": poi_stub(11.0, 107.0)})
    seen = _capture(_ok)
    payload = _parse(tools.get_itinerary_route(["p1", "p2"], vehicle="foot"))
    assert payload["success"] is True
    assert _query(seen[0])["ch.disable"] == "true"


def test_foot_with_built_ch_does_not_send_ch_disable(monkeypatch):
    monkeypatch.setenv("GRAPHHOPPER_PROFILES", "car,foot")
    monkeypatch.setenv("GRAPHHOPPER_CH_PROFILES", "car,foot")
    _set_pois({"p1": poi_stub(), "p2": poi_stub(11.0, 107.0)})
    seen = _capture(_ok)
    tools.get_itinerary_route(["p1", "p2"], vehicle="foot")
    assert "ch.disable" not in _query(seen[0])


def test_provider_400_is_explicit_and_echoes_no_message(monkeypatch):
    monkeypatch.setenv("GRAPHHOPPER_PROFILES", "car,foot")
    _set_pois({"p1": poi_stub(), "p2": poi_stub(11.0, 107.0)})

    def fail(request):
        return httpx.Response(
            400, json={"message": "Disable CH using ch.disable=true"})

    _capture(fail)
    payload = _parse(tools.get_itinerary_route(["p1", "p2"], vehicle="foot"))
    assert payload["success"] is False
    assert payload["code"] == "route_failed"
    assert payload["upstream_status"] == 400
    assert payload["ch_disabled"] is True
    assert "Disable CH" not in json.dumps(payload)
    # No straight-line substitute: no distance/time is ever synthesised.
    assert "distance_km" not in payload
    assert "time_minutes" not in payload


def test_transport_failure_is_explicit_and_never_falls_back():
    _set_pois({"p1": poi_stub(), "p2": poi_stub(11.0, 107.0)})

    def boom(request):
        raise httpx.ConnectError("no route to engine", request=request)

    _capture(boom)
    payload = _parse(tools.get_itinerary_route(["p1", "p2"], vehicle="car"))
    assert payload["success"] is False
    assert payload["code"] == "route_failed"
    assert "distance_km" not in payload


def test_exactly_one_http_request_per_call(monkeypatch):
    monkeypatch.setenv("GRAPHHOPPER_PROFILES", "car,foot")
    _set_pois({"p1": poi_stub(), "p2": poi_stub(11.0, 107.0)})
    seen = _capture(_ok)
    tools.get_itinerary_route(["p1", "p2"], vehicle="foot")
    assert len(seen) == 1
