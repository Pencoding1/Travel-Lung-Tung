"""End-to-end draft workflow and owner-isolation tests (OC-027)."""

from __future__ import annotations

import helpers
from app.main import create_app
from app.core.repositories.itinerary_draft import NullItineraryDraftRepository

BASE = "/api/v1/itineraries"


def _app():
    return create_app(repository=helpers.InMemoryDraftRepository())


def test_create_get_list_delete_roundtrip(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", helpers.SECRET)
    app = _app()
    token = helpers.make_token(sub="user-1")

    created = helpers.run_http(app, "POST", BASE, token=token,
                               json_body={"payload": helpers.sample_payload()})
    assert created.status_code == 201
    body = created.json()
    assert body["id"].startswith("draft_")
    assert body["created_at"]
    assert body["start_poi_id"] == "poi_a"
    assert body["stop_count"] == 1
    # Unknown cost stays null and the planning verdict is preserved verbatim.
    assert body["payload"]["reply"]["total_estimated_budget"] is None
    assert body["payload"]["planning"]["validator_status"] == "unverifiable"
    assert body["payload"]["planning"]["cost"]["status"] == "unknown"

    draft_id = body["id"]
    fetched = helpers.run_http(app, "GET", f"{BASE}/{draft_id}", token=token)
    assert fetched.status_code == 200
    assert fetched.json() == body

    listed = helpers.run_http(app, "GET", BASE, token=token)
    assert listed.status_code == 200
    listing = listed.json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == draft_id

    deleted = helpers.run_http(app, "DELETE", f"{BASE}/{draft_id}", token=token)
    assert deleted.status_code == 204
    assert helpers.run_http(app, "GET", f"{BASE}/{draft_id}", token=token).status_code == 404


def test_cross_subject_isolation_same_id(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", helpers.SECRET)
    app = _app()
    token_1 = helpers.make_token(sub="user-1")
    token_2 = helpers.make_token(sub="user-2")

    created = helpers.run_http(app, "POST", BASE, token=token_1,
                               json_body={"payload": helpers.sample_payload()})
    draft_id = created.json()["id"]

    # Owner cannot discover another subject's record by reusing its id.
    assert helpers.run_http(app, "GET", f"{BASE}/{draft_id}",
                            token=token_2).status_code == 404
    assert helpers.run_http(app, "DELETE", f"{BASE}/{draft_id}",
                            token=token_2).status_code == 404
    other_list = helpers.run_http(app, "GET", BASE, token=token_2).json()
    assert other_list["items"] == [] and other_list["total"] == 0

    # The real owner is unaffected.
    assert helpers.run_http(app, "GET", f"{BASE}/{draft_id}",
                            token=token_1).status_code == 200


def test_client_supplied_owner_is_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", helpers.SECRET)
    app = _app()
    token = helpers.make_token(sub="user-1")
    response = helpers.run_http(
        app, "POST", BASE, token=token,
        json_body={"payload": helpers.sample_payload(), "owner": "attacker"})
    assert response.status_code == 422


def test_pagination_bounds(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", helpers.SECRET)
    app = _app()
    token = helpers.make_token(sub="user-1")
    assert helpers.run_http(app, "GET", f"{BASE}?limit=0", token=token).status_code == 422
    assert helpers.run_http(app, "GET", f"{BASE}?limit=101", token=token).status_code == 422
    assert helpers.run_http(app, "GET", f"{BASE}?offset=-1", token=token).status_code == 422


def test_missing_record_is_404(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", helpers.SECRET)
    app = _app()
    token = helpers.make_token()
    assert helpers.run_http(app, "GET", f"{BASE}/draft_{'0' * 32}",
                            token=token).status_code == 404
    assert helpers.run_http(app, "GET", f"{BASE}/not-a-draft",
                            token=token).status_code == 404


def test_readiness_reflects_repository_availability(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", helpers.SECRET)

    ready_app = _app()
    assert helpers.run_http(ready_app, "GET", "/health").status_code == 200
    assert helpers.run_http(ready_app, "GET", "/ready").status_code == 200

    unavailable_app = create_app(repository=NullItineraryDraftRepository())
    health = helpers.run_http(unavailable_app, "GET", "/health").json()
    assert health["repository"]["available"] is False
    assert helpers.run_http(unavailable_app, "GET", "/ready").status_code == 503

    token = helpers.make_token(sub="user-1")
    blocked = helpers.run_http(unavailable_app, "POST", BASE, token=token,
                               json_body={"payload": helpers.sample_payload()})
    assert blocked.status_code == 503
    assert blocked.json()["detail"]["code"] == "storage_unavailable"
