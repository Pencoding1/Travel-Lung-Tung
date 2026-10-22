"""Tool-envelope contract tests.

The tool functions are exercised in process with an injected fake UnitOfWork.
This is not a transport test; real MCP registration/transport is covered in
``test_mcp_registration.py``.
"""

import json

import pytest

import app.api.mcp.tools as tools
from app.core.domain.get_payload import POICompoundLite
from mcp_fakes import FakePOIRepository, FakeUnitOfWork


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    tools.reset_uow_factory()
    tools.reset_http_client_factory()
    monkeypatch.delenv("GRAPHHOPPER_URL", raising=False)
    monkeypatch.delenv("GRAPHHOPPER_PROFILES", raising=False)
    yield
    tools.reset_uow_factory()
    tools.reset_http_client_factory()


def _use(repo):
    uow = FakeUnitOfWork(repo)
    tools.set_uow_factory(lambda: uow)
    return uow


def _parse(raw):
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Empty results are lists with success=true
# ---------------------------------------------------------------------------
def test_empty_categories_is_success_with_empty_list():
    _use(FakePOIRepository(categories=[]))
    payload = _parse(tools.get_available_categories())
    assert payload["success"] is True
    assert payload["categories"] == []
    assert payload["total"] == 0


def test_empty_location_matches_is_success_with_empty_list():
    _use(FakePOIRepository(location_matches=[]))
    payload = _parse(tools.resolve_geographic_id("Nowhere"))
    assert payload["success"] is True
    assert payload["matches"] == []


def test_empty_explore_is_success_with_empty_list():
    _use(FakePOIRepository(compound_results=[]))
    payload = _parse(tools.explore_pois(city_id="c1"))
    assert payload["success"] is True
    assert payload["results"] == []
    assert payload["count"] == 0


def test_explore_returns_structured_lite_results():
    poi = POICompoundLite(id="p1", name="Cafe")
    _use(FakePOIRepository(compound_results=[poi]))
    payload = _parse(tools.explore_pois(city_id="c1", category_id="cat_a"))
    assert payload["success"] is True
    assert payload["count"] == 1
    assert payload["results"][0]["id"] == "p1"


# ---------------------------------------------------------------------------
# Invalid input -> stable invalid_request code
# ---------------------------------------------------------------------------
def test_explore_without_criteria_is_invalid_request():
    _use(FakePOIRepository())
    payload = _parse(tools.explore_pois())
    assert payload["success"] is False
    assert payload["code"] == "invalid_request"
    assert payload["results"] == []


@pytest.mark.parametrize("bad_limit", [0, 101, -5])
def test_explore_bad_limit_is_invalid_request(bad_limit):
    _use(FakePOIRepository())
    payload = _parse(tools.explore_pois(city_id="c1", limit=bad_limit))
    assert payload["success"] is False
    assert payload["code"] == "invalid_request"
    assert payload["results"] == []


def test_resolve_blank_keyword_is_invalid_request():
    _use(FakePOIRepository())
    payload = _parse(tools.resolve_geographic_id("   "))
    assert payload["success"] is False
    assert payload["code"] == "invalid_request"
    assert payload["matches"] == []


# ---------------------------------------------------------------------------
# Errors are sanitized (no tracebacks / provider raw messages)
# ---------------------------------------------------------------------------
class _ExplodingRepo(FakePOIRepository):
    def get_compound_explore_lite(self, **kwargs):
        raise RuntimeError("SECRET provider token abc123")


def test_explore_error_is_sanitized():
    _use(_ExplodingRepo())
    raw = tools.explore_pois(city_id="c1")
    payload = _parse(raw)
    assert payload["success"] is False
    assert payload["code"] == "exploration_failed"
    assert "SECRET" not in raw
    assert "Traceback" not in raw


class _ExplodingDetailsRepo(FakePOIRepository):
    def get_poi_graph_payload(self, id, radius_km=3.0, limit=5):
        raise ValueError("raw driver text")


def test_get_poi_details_error_is_sanitized():
    _use(_ExplodingDetailsRepo())
    raw = tools.get_poi_details("p1")
    payload = _parse(raw)
    assert payload["success"] is False
    assert payload["code"] == "internal_error"
    assert payload["result"] is None
    assert "raw driver text" not in raw
    assert "Traceback" not in raw


def test_get_poi_details_missing_is_not_found():
    _use(FakePOIRepository(graph_payload=None))
    payload = _parse(tools.get_poi_details("p1"))
    assert payload["success"] is False
    assert payload["code"] == "not_found"
    assert payload["result"] is None


def test_get_poi_details_blank_id_is_invalid_request():
    _use(FakePOIRepository())
    payload = _parse(tools.get_poi_details("  "))
    assert payload["success"] is False
    assert payload["code"] == "invalid_request"


def test_categories_error_is_sanitized():
    class _CatExplode(FakePOIRepository):
        def get_all_categories(self):
            raise RuntimeError("db down token=xyz")

    _use(_CatExplode())
    raw = tools.get_available_categories()
    payload = _parse(raw)
    assert payload["success"] is False
    assert payload["code"] == "category_fetch_failed"
    assert payload["categories"] == []
    assert "xyz" not in raw
