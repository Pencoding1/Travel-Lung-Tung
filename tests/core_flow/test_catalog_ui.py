"""Catalog proxy and static UI contract.

The MCP discovery call is faked; the AI HTTP layer, sanitizers and static file
serving are real. Static checks are not a browser/render proof.
"""

import json
from pathlib import Path

import pytest
from helpers_core_flow import (
    INPUT_SHA256,
    SELECTION_A,
    FakeMCPSession,
    http_call,
    mcp_seam,
)

import main

REPO_ROOT = Path(__file__).resolve().parents[2]
UI_PATH = REPO_ROOT / "ai_service" / "static" / "travel.html"

AREA_ID = SELECTION_A["source_area_id"]


def _wire(monkeypatch, response):
    session = FakeMCPSession(("explore_pois",), {
        "explore_pois": lambda _args: _tool(response)})
    monkeypatch.setattr(main, "open_mcp_session", mcp_seam(session))
    return session


class _Text:
    def __init__(self, text):
        self.text = text


class _Result:
    def __init__(self, payload):
        self.content = [_Text(json.dumps(payload))]
        self.isError = False


def _tool(payload):
    return _Result(payload)


def test_snapshot_catalog_sanitizes_fields_and_never_calls_the_model(monkeypatch):
    session = _wire(monkeypatch, {
        "success": True,
        "scan": {"scanned_record_count": 5, "excluded_corrupt_count": 1,
                 "scan_complete": True, "truncated": False,
                 "raw": "must not leak"},
        "snapshots": [{
            "dataset_namespace": "hcm_primary_geojson",
            "input_sha256": INPUT_SHA256,
            "valid_record_count": 6367,
            "source_area_count": 12,
            "absolute_path": "C:/secret/path",
            "results": [{"id": "poi_secret"}],
        }],
    })

    async def _model(_payload):
        raise AssertionError("catalog must not call the model")

    monkeypatch.setattr(main, "gemini_chat_completion", _model)

    response = http_call("GET", "/catalog/snapshots")
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["snapshots"] == [{
        "dataset_namespace": "hcm_primary_geojson",
        "input_sha256": INPUT_SHA256,
        "valid_record_count": 6367,
        "source_area_count": 12,
    }]
    assert "C:/secret/path" not in response.text
    assert "poi_secret" not in response.text
    assert "not present-day administrative boundaries" in body["notice"]
    assert session.calls[0]["args"] == {"source_discovery": "snapshots"}


def test_area_catalog_returns_the_canonical_tuple(monkeypatch):
    session = _wire(monkeypatch, {
        "success": True,
        "dataset_namespace": "hcm_primary_geojson",
        "input_sha256": INPUT_SHA256,
        "source_areas": [{
            "source_area_id": AREA_ID,
            "source_area_label": "Vùng dữ liệu Quận 1",
            "raw_city": "Hồ Chí Minh",
            "raw_area": "Quận 1",
            "area_assignment": "qualified",
            "valid_record_count": 100,
            "owner_token": "must-not-leak",
        }],
        "scan": {"scanned_record_count": 100, "excluded_corrupt_count": 0,
                 "scan_complete": True, "truncated": False},
    })

    response = http_call(
        "GET", f"/catalog/source_areas?dataset_namespace=hcm_primary_geojson"
               f"&input_sha256={INPUT_SHA256}")
    body = response.json()

    assert response.status_code == 200
    area = body["source_areas"][0]
    assert area["selection"] == SELECTION_A
    assert area["source_area_label"] == "Vùng dữ liệu Quận 1"
    assert "owner_token" not in response.text
    assert "must-not-leak" not in response.text
    assert session.calls[0]["args"] == {
        "source_discovery": "source_areas",
        "source_snapshot": {
            "dataset_namespace": "hcm_primary_geojson",
            "input_sha256": INPUT_SHA256,
        },
    }


@pytest.mark.parametrize("query", [
    f"?dataset_namespace=hcm_primary_geojson&input_sha256={'A' * 64}",
    f"?dataset_namespace=hcm_primary_geojson&input_sha256={'a' * 63}",
    f"?dataset_namespace=%20hcm_primary_geojson&input_sha256={INPUT_SHA256}",
    f"?dataset_namespace=&input_sha256={INPUT_SHA256}",
])
def test_invalid_snapshot_is_422_without_mcp(monkeypatch, query):
    session = _wire(monkeypatch, {"success": True})
    response = http_call("GET", "/catalog/source_areas" + query)
    assert response.status_code == 422
    assert session.calls == []


def test_snapshot_echo_mismatch_is_refused(monkeypatch):
    _wire(monkeypatch, {
        "success": True,
        "dataset_namespace": "hcm_primary_geojson",
        "input_sha256": "d" * 64,
        "source_areas": [],
    })
    response = http_call(
        "GET", f"/catalog/source_areas?dataset_namespace=hcm_primary_geojson"
               f"&input_sha256={INPUT_SHA256}")
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "catalog_contract_mismatch"


def test_catalog_unavailable_is_structured(monkeypatch):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _broken():
        raise RuntimeError("transport down")
        yield  # pragma: no cover - keeps this an async generator

    monkeypatch.setattr(main, "open_mcp_session", _broken)
    response = http_call("GET", "/catalog/snapshots")
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "catalog_unavailable"


def test_ui_is_served_same_origin():
    response = http_call("GET", "/travel")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Travel Lung Tung" in response.text
    assert "<select id=\"snapshot\">" in response.text


def test_static_ui_uses_safe_dom_rendering_only():
    source = UI_PATH.read_text(encoding="utf-8")
    lower = source.lower()
    assert "innerhtml" not in lower
    assert "insertadjacenthtml" not in lower
    assert "sethtml" not in lower
    assert "localstorage" not in lower
    assert "sessionstorage" not in lower
    assert "authorization" not in lower
    assert "bearer" not in lower
    assert "<script src" not in lower
    assert "document.createelement" in lower
    assert "textcontent" in lower
    assert "setdomcontent" in lower

    # UI127 pins exactly these browser-runtime dependencies. Everything else
    # in the page must stay same-origin and free of arbitrary external URLs.
    allowed = [
        '<link rel="stylesheet" '
        'href="https://unpkg.com/maplibre-gl@6.15.0/dist/maplibre-gl.css">',
        "https://unpkg.com/maplibre-gl@6.15.0/dist/maplibre-gl.mjs",
        "https://tiles.openfreemap.org/styles/bright",
        "https://tiles.openfreemap.org/planet",
    ]
    for url in allowed:
        assert source.count(url) == 1, url
    assert lower.count("<link") == 1
    stripped = source
    for url in allowed:
        stripped = stripped.replace(url, "")
    assert "https://" not in stripped
    assert "http://" not in stripped


def test_static_ui_sends_the_exact_context_and_shows_unknowns():
    source = UI_PATH.read_text(encoding="utf-8")
    for needle in ("source_scope", "transport_mode", "source_area_id",
                   "input_sha256", "dataset_namespace",
                   "/catalog/snapshots", "/catalog/source_areas",
                   "/chat", "/generate_itinerary",
                   "chưa rõ", "Giờ mở cửa", "Giá", "travel_from_prev_minutes",
                   "travel_from_prev_distance_km"):
        assert needle in source, needle
    assert "value=\"car\"" in source
    assert "value=\"foot\"" in source
