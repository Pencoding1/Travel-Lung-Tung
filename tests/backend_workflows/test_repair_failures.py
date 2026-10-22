"""OC-027-R1 corrective tests: sanitized storage failures, readiness recovery,
bounded Firestore listing and safe deep-nesting rejection.

All collaborators are fakes or a real local SQLite file; no network, live
database, Firebase or model call is made.
"""

from __future__ import annotations

import sqlite3

import helpers
from app.main import create_app
from app.core.repositories.itinerary_draft import RepositoryError
from app.core.repositories.firestore_itinerary_draft import (
    FirestoreItineraryDraftRepository,
)
from app.core.repositories.sqlite_itinerary_draft import (
    SqliteItineraryDraftRepository,
)

BASE = "/api/v1/itineraries"
SECRET = helpers.SECRET


def _summary():
    return {"start_poi_id": "poi_a", "end_poi_id": "poi_b", "stop_count": 1}


def _broken_path(tmp_path):
    return str(tmp_path / "does_not_exist_dir" / "drafts.sqlite3")


def _invoke(repo, op):
    if op == "create":
        return repo.create("user-1", {"reply": {"stops": []}}, **_summary())
    if op == "get":
        return repo.get("user-1", "draft_" + "0" * 32)
    if op == "list":
        return repo.list("user-1", limit=5, offset=0)
    return repo.delete("user-1", "draft_" + "0" * 32)


# ---------------------------------------------------------------------------
# SQLite error boundary
# ---------------------------------------------------------------------------
def test_all_sqlite_ops_normalize_connection_failure(tmp_path):
    repo = SqliteItineraryDraftRepository(str(tmp_path / "drafts.sqlite3"))
    repo._path = _broken_path(tmp_path)  # parent directory absent -> connect fails
    for op in ("create", "get", "list", "delete"):
        try:
            _invoke(repo, op)
        except RepositoryError:
            pass
        except sqlite3.Error as exc:  # pragma: no cover - regression guard
            raise AssertionError(f"{op} leaked raw {type(exc).__name__}") from None
        else:
            raise AssertionError(f"{op} did not raise")
    health = repo.health()
    assert health["available"] is False
    assert "does_not_exist_dir" not in str(health)


def test_query_failure_is_normalized_without_unsafe_recovery(tmp_path):
    """OC-028: a dropped table must fail closed, not be silently recreated."""
    path = str(tmp_path / "drafts.sqlite3")
    repo = SqliteItineraryDraftRepository(path)
    _invoke(repo, "create")

    raw = sqlite3.connect(path)
    raw.execute("DROP TABLE itinerary_drafts")
    raw.commit()
    rows_after_drop = raw.execute(
        "SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall()
    raw.close()

    for op in ("get", "list"):
        try:
            _invoke(repo, op)
        except RepositoryError:
            pass
        except sqlite3.Error as exc:  # pragma: no cover - regression guard
            raise AssertionError(f"{op} leaked raw {type(exc).__name__}") from None
        else:
            raise AssertionError(f"{op} did not raise")

    # readiness reports the real state and does not recreate the schema.
    assert repo.health()["available"] is False

    raw = sqlite3.connect(path)
    rows_after_health = raw.execute(
        "SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall()
    raw.close()
    assert rows_after_health == rows_after_drop, "health mutated the schema"

    # Only an explicit, deliberate re-initialization restores service.
    repo.initialize()
    assert repo.health()["available"] is True
    assert _invoke(repo, "list") == ([], 0)


def test_sqlite_connection_failure_over_asgi_is_503_without_leak(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    repo = SqliteItineraryDraftRepository(str(tmp_path / "drafts.sqlite3"))
    repo._path = _broken_path(tmp_path)
    app = create_app(repository=repo)
    token = helpers.make_token(sub="user-1")

    responses = [
        helpers.run_http(app, "GET", BASE, token=token),
        helpers.run_http(app, "POST", BASE, token=token,
                         json_body={"payload": helpers.sample_payload()}),
        helpers.run_http(app, "GET", f"{BASE}/{'draft_' + '0' * 32}", token=token),
        helpers.run_http(app, "DELETE", f"{BASE}/{'draft_' + '0' * 32}", token=token),
    ]
    for response in responses:
        assert response.status_code == 503, response.text
        text = response.text
        for forbidden in ("does_not_exist_dir", "sqlite", "OperationalError",
                          "unable to open", ".sqlite3", SECRET):
            assert forbidden not in text, f"{forbidden!r} leaked in {text!r}"


def test_readiness_reflects_actual_storage_and_recovers(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    good = str(tmp_path / "drafts.sqlite3")
    repo = SqliteItineraryDraftRepository(good)
    app = create_app(repository=repo)

    assert helpers.run_http(app, "GET", "/ready").status_code == 200
    assert helpers.run_http(app, "GET", "/health").json()["repository"]["available"] is True

    repo._path = _broken_path(tmp_path)
    assert helpers.run_http(app, "GET", "/ready").status_code == 503
    assert helpers.run_http(app, "GET", "/health").json()["repository"]["available"] is False

    repo._path = good  # storage comes back
    assert helpers.run_http(app, "GET", "/ready").status_code == 200


# ---------------------------------------------------------------------------
# Deep-nesting parser guard
# ---------------------------------------------------------------------------
def test_deeply_nested_body_is_structured_422(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    app = create_app(repository=helpers.InMemoryDraftRepository())
    raw = b'{"payload":' + b'{"a":' * 3000 + b'1' + b'}' * 3000 + b'}'
    response = helpers.run_http(app, "POST", BASE, token=helpers.make_token(),
                                raw_content=raw,
                                headers={"content-type": "application/json"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "payload_too_deep"


# ---------------------------------------------------------------------------
# Firestore sanitization + bounded listing (fake client)
# ---------------------------------------------------------------------------
def test_firestore_all_ops_normalize_failures():
    repo = FirestoreItineraryDraftRepository(helpers.FailingFirestoreClient())
    for op in ("create", "get", "list", "delete"):
        try:
            _invoke(repo, op)
        except RepositoryError:
            pass
        else:
            raise AssertionError(f"{op} did not raise")
    health = repo.health()
    assert health["available"] is False
    assert helpers.LEAK_MARKER not in str(health)


def test_firestore_failure_over_asgi_is_503_without_leak(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    repo = FirestoreItineraryDraftRepository(helpers.FailingFirestoreClient())
    app = create_app(repository=repo)
    token = helpers.make_token(sub="user-1")

    responses = [
        helpers.run_http(app, "GET", BASE, token=token),
        helpers.run_http(app, "POST", BASE, token=token,
                         json_body={"payload": helpers.sample_payload()}),
        helpers.run_http(app, "GET", f"{BASE}/{'draft_' + '0' * 32}", token=token),
        helpers.run_http(app, "DELETE", f"{BASE}/{'draft_' + '0' * 32}", token=token),
    ]
    for response in responses:
        assert response.status_code == 503, response.text
        assert helpers.LEAK_MARKER not in response.text
        assert "serviceAccountKey" not in response.text


def test_firestore_listing_is_bounded_at_query_level():
    client = helpers.FakeFirestoreClient()
    repo = FirestoreItineraryDraftRepository(client)
    for _ in range(5):
        _invoke(repo, "create")
    repo.create("user-2", {"reply": {"stops": []}}, **_summary())

    page, total = repo.list("user-1", limit=2, offset=0)
    assert total == 5 and len(page) == 2
    # The page query (not a full scan) was pushed to storage with limit+offset.
    stream_calls = [entry for entry in client.query_log
                    if entry["limit"] is not None or entry["offset"]]
    assert stream_calls, "no bounded query was issued"
    assert all(entry["ordered"] and entry["filtered"] for entry in stream_calls)
    assert any(entry["limit"] == 2 and entry["offset"] == 0 for entry in stream_calls)

    second, _ = repo.list("user-1", limit=2, offset=2)
    assert len(second) == 2
    assert repo.list("user-2", limit=10, offset=0)[1] == 1
