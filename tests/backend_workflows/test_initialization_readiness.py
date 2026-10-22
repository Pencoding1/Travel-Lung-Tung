"""OC-028: deliberate SQLite initialization vs. observational readiness.

These tests pin the invariant that ``health``/``/ready`` and ordinary CRUD are
non-mutating: a dropped table, a malformed schema, a removed database file or a
removed parent directory must be reported unavailable (sanitized ``503``) and
must **not** be recreated by any read, probe or operation. Storage is restored
only by an explicit ``initialize()`` or by restoring the original database.

Everything is a real local SQLite file and a real ASGI app; no network, Firebase
or model call is involved.
"""

from __future__ import annotations

import asyncio
import shutil
import sqlite3
from pathlib import Path

import helpers
import pytest

from app.core.repositories.itinerary_draft import RepositoryError
from app.core.repositories.sqlite_itinerary_draft import (
    SqliteItineraryDraftRepository,
)
from app.main import create_app

BASE = "/api/v1/itineraries"
SECRET = helpers.SECRET

_LEAK_MARKERS = ("sqlite", "OperationalError", "unable to open", ".sqlite3",
                 "file is not a database")


def _create(repo, owner="user-1"):
    return repo.create(owner, {"reply": {"stops": []}},
                       start_poi_id="poi_a", end_poi_id="poi_b", stop_count=1)


def _sqlite_master(path):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall()
    finally:
        conn.close()


def _journal_mode(path):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()


def _table_present(path):
    return any(row[1] == "itinerary_drafts" for row in _sqlite_master(path))


def _assert_sanitized_503(response, *forbidden):
    assert response.status_code == 503, response.text
    text = response.text
    for marker in _LEAK_MARKERS + forbidden:
        assert marker not in text, f"{marker!r} leaked in {text!r}"


def _remove_database(path):
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            candidate.unlink()


# ---------------------------------------------------------------------------
# 1. Dropped required table: unavailable, unchanged schema (defect reproduction)
# ---------------------------------------------------------------------------
def test_dropped_table_is_unavailable_and_not_recreated(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    path = str(tmp_path / "drafts.sqlite3")
    repo = SqliteItineraryDraftRepository(path)
    _create(repo)

    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE itinerary_drafts")
    conn.commit()
    conn.close()

    assert _table_present(path) is False
    master_after_drop = _sqlite_master(path)

    # Direct readiness probe: unavailable, no recreation.
    assert repo.health()["available"] is False
    assert _sqlite_master(path) == master_after_drop
    assert _table_present(path) is False

    # Real ASGI readiness: 503, still no recreation.
    app = create_app(repository=repo)
    assert helpers.run_http(app, "GET", "/ready").status_code == 503
    assert helpers.run_http(app, "GET", "/health").json()["repository"]["available"] is False
    assert _sqlite_master(path) == master_after_drop
    assert _table_present(path) is False


# ---------------------------------------------------------------------------
# 2. Malformed schema (missing required columns): unavailable and unchanged
# ---------------------------------------------------------------------------
def test_malformed_table_missing_columns_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    path = str(tmp_path / "drafts.sqlite3")
    raw = sqlite3.connect(path)
    raw.execute("CREATE TABLE itinerary_drafts (id TEXT PRIMARY KEY)")
    raw.commit()
    master_before = _sqlite_master(path)
    raw.close()

    repo = SqliteItineraryDraftRepository(path, initialize=False)
    assert repo.health()["available"] is False

    app = create_app(repository=repo)
    assert helpers.run_http(app, "GET", "/ready").status_code == 503

    # The table exists but is not the required schema; nothing was repaired.
    assert _sqlite_master(path) == master_before
    assert _table_present(path) is True


# ---------------------------------------------------------------------------
# 3. Removed database file/parent: never recreated by health or any CRUD
# ---------------------------------------------------------------------------
def test_removed_database_file_is_not_recreated_by_health_or_crud(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    base = tmp_path / "storage dir"
    path = base / "drafts.sqlite3"
    repo = SqliteItineraryDraftRepository(str(path))
    _create(repo)

    _remove_database(path)
    shutil.rmtree(base)
    assert not path.exists() and not base.exists()

    app = create_app(repository=repo)
    token = helpers.make_token(sub="user-1")
    draft_id = "draft_" + "0" * 32
    responses = [
        helpers.run_http(app, "GET", BASE, token=token),
        helpers.run_http(app, "POST", BASE, token=token,
                         json_body={"payload": helpers.sample_payload()}),
        helpers.run_http(app, "GET", f"{BASE}/{draft_id}", token=token),
        helpers.run_http(app, "DELETE", f"{BASE}/{draft_id}", token=token),
    ]
    for response in responses:
        _assert_sanitized_503(response, str(base), "does_not_exist_dir")

    assert repo.health()["available"] is False
    assert helpers.run_http(app, "GET", "/ready").status_code == 503
    assert not path.exists(), "health/CRUD recreated the database file"
    assert not base.exists(), "health/CRUD recreated the parent directory"


# ---------------------------------------------------------------------------
# 4. Restoring the original initialized DB recovers readiness and records
# ---------------------------------------------------------------------------
def test_restoring_initialized_db_recovers_ready_and_retains_records(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    path = tmp_path / "drafts.sqlite3"
    repo = SqliteItineraryDraftRepository(str(path))
    record = _create(repo)

    checkpoint = sqlite3.connect(str(path))
    checkpoint.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    checkpoint.close()
    backup = tmp_path / "backup.sqlite3"
    shutil.copy2(str(path), str(backup))

    app = create_app(repository=repo)
    assert helpers.run_http(app, "GET", "/ready").status_code == 200

    _remove_database(path)
    assert helpers.run_http(app, "GET", "/ready").status_code == 503

    shutil.copy2(str(backup), str(path))
    assert helpers.run_http(app, "GET", "/ready").status_code == 200

    token = helpers.make_token(sub="user-1")
    listed = helpers.run_http(app, "GET", BASE, token=token).json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == record.id


# ---------------------------------------------------------------------------
# 5. An ordinary health probe mutates neither schema/data nor journal mode
# ---------------------------------------------------------------------------
def test_ordinary_health_does_not_mutate_schema_or_journal_mode(tmp_path):
    path = tmp_path / "drafts.sqlite3"
    repo = SqliteItineraryDraftRepository(str(path))
    _create(repo)

    def snapshot():
        conn = sqlite3.connect(str(path))
        try:
            master = conn.execute(
                "SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall()
            rows = conn.execute(
                "SELECT id, owner, start_poi_id, end_poi_id, stop_count, payload "
                "FROM itinerary_drafts ORDER BY id").fetchall()
            journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            conn.close()
        return master, rows, journal

    before = snapshot()
    for _ in range(3):
        assert repo.health()["available"] is True
    after = snapshot()
    assert after == before
    assert after[2] == before[2] == _journal_mode(str(path))


# ---------------------------------------------------------------------------
# 6. Paths containing spaces
# ---------------------------------------------------------------------------
def test_path_with_spaces_is_supported(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    path = tmp_path / "dir with spaces" / "my drafts file.sqlite3"
    repo = SqliteItineraryDraftRepository(str(path))
    assert path.exists()
    record = _create(repo)
    assert repo.health()["available"] is True
    assert repo.get("user-1", record.id) is not None

    app = create_app(repository=repo)
    assert helpers.run_http(app, "GET", "/ready").status_code == 200


# ---------------------------------------------------------------------------
# 7. Legitimate fresh startup persists and reopens
# ---------------------------------------------------------------------------
def test_fresh_startup_persists_and_reopens(tmp_path):
    path = str(tmp_path / "drafts.sqlite3")
    first = SqliteItineraryDraftRepository(path)
    record = _create(first)
    first.close()

    reopened = SqliteItineraryDraftRepository(path)
    try:
        found = reopened.get("user-1", record.id)
        assert found is not None
        assert found.id == record.id
        assert found.payload == {"reply": {"stops": []}}
    finally:
        reopened.close()


# ---------------------------------------------------------------------------
# 8. Explicit init is required when construction opts out; it never mutates reads
# ---------------------------------------------------------------------------
def test_initialize_is_explicit_and_creates_storage_once(tmp_path):
    path = tmp_path / "drafts.sqlite3"
    repo = SqliteItineraryDraftRepository(str(path), initialize=False)
    assert not path.exists()
    assert repo.health()["available"] is False
    with pytest.raises(RepositoryError):
        _create(repo)
    assert not path.exists(), "a failed ordinary operation created the database"

    repo.initialize()
    assert path.exists()
    assert repo.health()["available"] is True


# ---------------------------------------------------------------------------
# 9. The app lifespan startup boundary performs the deliberate initialization
# ---------------------------------------------------------------------------
def test_app_lifespan_startup_initializes_storage(tmp_path):
    path = tmp_path / "drafts.sqlite3"
    repo = SqliteItineraryDraftRepository(str(path), initialize=False)
    assert not path.exists()

    app = create_app(repository=repo)

    async def _run():
        async with app.router.lifespan_context(app):
            assert path.exists()
            assert repo.health()["available"] is True

    asyncio.run(_run())
    # Shutdown closed the owned repository.
    assert repo.health()["available"] is False


# ---------------------------------------------------------------------------
# 10. A pre-existing invalid database fails loudly at initialize (sanitized)
# ---------------------------------------------------------------------------
def test_startup_on_preexisting_invalid_db_fails_sanitized(tmp_path):
    path = tmp_path / "corrupt.sqlite3"
    path.write_bytes(b"this is definitely not a sqlite database" * 8)
    with pytest.raises(RepositoryError) as excinfo:
        SqliteItineraryDraftRepository(str(path))
    message = str(excinfo.value)
    assert "corrupt.sqlite3" not in message
    assert str(tmp_path) not in message
