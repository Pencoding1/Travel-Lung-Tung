"""Durable SQLite adapter tests: restart, atomicity, cleanup (OC-027)."""

from __future__ import annotations

import helpers
import pytest
from httpx import ASGITransport, AsyncClient  # noqa: F401 - documents the ASGI path

import app.core.repositories.sqlite_itinerary_draft as sqlite_mod
from app.core.repositories.itinerary_draft import (
    DuplicateDraftId,
    RepositoryClosed,
    RepositoryError,
)
from app.core.repositories.sqlite_itinerary_draft import (
    SqliteItineraryDraftRepository,
)


def _create(repo, owner="user-1", summary=None):
    summary = summary or {"start_poi_id": "poi_a", "end_poi_id": "poi_b",
                          "stop_count": 1}
    return repo.create(owner, {"reply": {"stops": []}}, **summary)


def test_restart_durability(tmp_path):
    path = str(tmp_path / "drafts.sqlite3")
    repo = SqliteItineraryDraftRepository(path)
    record = _create(repo)
    repo.close()

    reopened = SqliteItineraryDraftRepository(path)
    try:
        found = reopened.get("user-1", record.id)
        assert found is not None
        assert found.id == record.id
        assert found.payload == {"reply": {"stops": []}}
        assert reopened.get("user-2", record.id) is None
    finally:
        reopened.close()


def test_duplicate_id_is_atomic_constraint(tmp_path, monkeypatch):
    repo = SqliteItineraryDraftRepository(str(tmp_path / "drafts.sqlite3"))
    try:
        fixed = type("Fixed", (), {"hex": "0" * 32})()
        monkeypatch.setattr(sqlite_mod.uuid, "uuid4", lambda: fixed)
        first = _create(repo)
        with pytest.raises(DuplicateDraftId):
            _create(repo)
        # The failed insert did not corrupt the store.
        assert repo.get("user-1", first.id) is not None
        assert len(repo.list("user-1", limit=10, offset=0)[0]) == 1
    finally:
        repo.close()


def test_unserializable_payload_rolls_back_cleanly(tmp_path):
    repo = SqliteItineraryDraftRepository(str(tmp_path / "drafts.sqlite3"))
    try:
        with pytest.raises(RepositoryError):
            repo.create("user-1", {"bad": {1, 2, 3}},
                        start_poi_id=None, end_poi_id=None, stop_count=0)
        # The connection was released; the repository is still usable.
        record = _create(repo)
        assert repo.get("user-1", record.id) is not None
    finally:
        repo.close()


def test_closed_repository_fails_closed(tmp_path):
    repo = SqliteItineraryDraftRepository(str(tmp_path / "drafts.sqlite3"))
    repo.close()
    with pytest.raises(RepositoryClosed):
        _create(repo)
    with pytest.raises(RepositoryClosed):
        repo.get("user-1", "draft_" + "0" * 32)
    assert repo.health()["available"] is False


def test_sqlite_repository_via_asgi_endpoint(tmp_path, monkeypatch):
    """The real SQLite store backs the real HTTP surface end-to-end."""
    monkeypatch.setenv("JWT_SECRET", helpers.SECRET)
    from app.main import create_app

    repo = SqliteItineraryDraftRepository(str(tmp_path / "drafts.sqlite3"))
    app = create_app(repository=repo)
    token = helpers.make_token(sub="user-1")

    created = helpers.run_http(app, "POST", "/api/v1/itineraries", token=token,
                               json_body={"payload": helpers.sample_payload()})
    assert created.status_code == 201
    draft_id = created.json()["id"]

    fetched = helpers.run_http(app, "GET", f"/api/v1/itineraries/{draft_id}",
                               token=token)
    assert fetched.status_code == 200
