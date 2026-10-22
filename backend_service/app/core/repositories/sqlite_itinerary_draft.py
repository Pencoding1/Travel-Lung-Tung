"""Local durable SQLite adapter for itinerary drafts (OC-027, revised OC-028).

Opt-in, file-backed and durable across process restarts. A fresh connection is
opened per operation (``check_same_thread=False`` is therefore unnecessary) so
the adapter is safe under FastAPI's sync threadpool; every write is a single
atomic statement inside an implicit transaction. All SQL is parameterized and
ownership is enforced in the ``WHERE`` clause, so cross-subject access cannot
leak even for a colliding id.

Initialization vs. readiness (OC-028)
-------------------------------------
Deliberate, mutating initialization is **separated** from observational
readiness:

* :meth:`initialize` is the *only* code path that creates the parent directory,
  opens the database for creation (``mode=rwc``), selects the journal mode and
  runs ``CREATE TABLE/INDEX``. It is invoked deliberately — at repository
  construction (``initialize=True``, the default) and again from the application
  lifespan startup boundary.
* Every ordinary operation (``create/get/list/delete``) and :meth:`health` open
  the database with ``mode=rw`` (open-only, never create). If the file, parent
  directory or required table/columns have disappeared after initialization,
  they are reported unavailable and the operation fails closed with a sanitized
  :class:`RepositoryError` — no DDL, no journal-mode change, no file/tree
  recreation, and no automated schema or data-loss recovery.
* :meth:`health` is a bounded, purely observational probe (``SELECT <required
  columns> ... LIMIT 0``). It issues no canary write and no DDL; it recovers to
  ``available`` only when the *actually initialized* database and schema are
  present again.

Windows-safe paths use SQLite URI filenames (``file:///...?mode=...``) so spaces
and backslashes are handled correctly and the open mode is explicit.

Error boundary (OC-027-R1, retained): every connection, PRAGMA, query, commit and
payload decode failure in **every** operation is normalized into a sanitized
:class:`RepositoryError`. Raw ``sqlite3`` messages, file paths and SQL text never
escape the adapter, so the HTTP layer can return a structured ``503`` without
leaking internals.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from app.core.repositories.itinerary_draft import (
    DuplicateDraftId,
    ItineraryDraftRecord,
    ItineraryDraftRepository,
    RepositoryClosed,
    RepositoryError,
    utc_now_iso,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS itinerary_drafts (
    id           TEXT PRIMARY KEY,
    owner        TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    start_poi_id TEXT,
    end_poi_id   TEXT,
    stop_count   INTEGER NOT NULL,
    payload      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_itinerary_drafts_owner
    ON itinerary_drafts (owner, created_at);
"""

# Required columns and index, verified observationally by ``health``.
_REQUIRED_COLUMNS = ("id", "owner", "created_at", "start_poi_id", "end_poi_id",
                     "stop_count", "payload")
_HEALTH_PROBE = (
    "SELECT id, owner, created_at, start_poi_id, end_poi_id, stop_count, payload "
    "FROM itinerary_drafts LIMIT 0"
)


def _database_uri(path: str, mode: str) -> str:
    """Build a Windows-safe SQLite URI filename with an explicit open mode.

    ``mode='rw'`` opens an existing database and fails if it is absent (never
    creates); ``mode='rwc'`` creates the file. ``Path.as_uri`` percent-encodes
    spaces and normalizes separators, so database paths that contain spaces work
    on Windows.
    """
    absolute = os.path.abspath(path)
    return Path(absolute).as_uri() + f"?mode={mode}"


class SqliteItineraryDraftRepository(ItineraryDraftRepository):
    backend = "sqlite"

    def __init__(self, path: str, *, initialize: bool = True):
        if not isinstance(path, str) or not path.strip():
            raise RepositoryError("a nonblank SQLite path is required")
        self._path = path
        self._lock = threading.Lock()
        self._closed = False
        # Construction is the deliberate startup boundary by default; callers may
        # opt out and invoke :meth:`initialize` explicitly instead.
        if initialize:
            self.initialize()

    # -- connection handling ------------------------------------------------
    def _open(self, *, mode: str) -> sqlite3.Connection:
        """Open and configure a connection, sanitizing every failure.

        Only connection-local PRAGMAs are set here (``busy_timeout``,
        ``foreign_keys``); the journal mode is never changed on an ordinary
        connection, so a probe/read cannot mutate the database.
        """
        try:
            conn = sqlite3.connect(_database_uri(self._path, mode),
                                   uri=True, timeout=5.0)
        except (sqlite3.Error, ValueError):
            raise RepositoryError("sqlite connection failed") from None
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("PRAGMA foreign_keys = ON")
        except sqlite3.Error:
            conn.close()
            raise RepositoryError("sqlite connection setup failed") from None
        return conn

    @contextmanager
    def _connect(self, *, mode: str = "rw") -> Iterator[sqlite3.Connection]:
        if self._closed:
            raise RepositoryClosed("the SQLite repository is closed")
        conn = self._open(mode=mode)
        try:
            yield conn
        finally:
            try:
                conn.close()
            except sqlite3.Error:  # pragma: no cover - defensive
                pass

    def initialize(self) -> None:
        """Deliberately create/ensure the storage directory, database and schema.

        This is the *only* mutating setup path. It is safe to call repeatedly
        (``CREATE ... IF NOT EXISTS``); calling it after the file was deleted
        recreates an empty database, so it must be an explicit lifecycle action,
        never a side effect of a read or a health probe. A pre-existing invalid
        (non-database) file fails loudly here rather than being silently
        replaced.
        """
        if self._closed:
            raise RepositoryClosed("the SQLite repository is closed")
        absolute = os.path.abspath(self._path)
        parent = os.path.dirname(absolute)
        if parent:
            try:
                os.makedirs(parent, exist_ok=True)
            except OSError:
                raise RepositoryError(
                    "sqlite storage directory could not be created") from None
        with self._connect(mode="rwc") as conn:
            try:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.executescript(_SCHEMA)
                conn.commit()
            except sqlite3.Error:
                try:
                    conn.rollback()
                except sqlite3.Error:  # pragma: no cover - defensive
                    pass
                raise RepositoryError(
                    "sqlite schema initialization failed") from None

    # -- record mapping -----------------------------------------------------
    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ItineraryDraftRecord:
        try:
            payload = json.loads(row["payload"])
        except (ValueError, TypeError):
            raise RepositoryError("stored draft payload is unreadable") from None
        return ItineraryDraftRecord(
            id=row["id"],
            owner=row["owner"],
            created_at=row["created_at"],
            start_poi_id=row["start_poi_id"],
            end_poi_id=row["end_poi_id"],
            stop_count=row["stop_count"],
            payload=payload,
        )

    # -- contract -----------------------------------------------------------
    def create(self, owner: str, payload: Dict[str, Any], *,
               start_poi_id: Optional[str], end_poi_id: Optional[str],
               stop_count: int) -> ItineraryDraftRecord:
        draft_id = f"draft_{uuid.uuid4().hex}"
        created_at = utc_now_iso()
        try:
            encoded = json.dumps(payload, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError):
            raise RepositoryError("payload is not JSON-serializable") from None
        with self._lock:
            with self._connect() as conn:
                try:
                    conn.execute(
                        "INSERT INTO itinerary_drafts "
                        "(id, owner, created_at, start_poi_id, end_poi_id, "
                        " stop_count, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (draft_id, owner, created_at, start_poi_id, end_poi_id,
                         int(stop_count), encoded),
                    )
                    conn.commit()
                except sqlite3.IntegrityError:
                    try:
                        conn.rollback()
                    except sqlite3.Error:  # pragma: no cover - defensive
                        pass
                    raise DuplicateDraftId("draft id already exists") from None
                except sqlite3.Error:
                    try:
                        conn.rollback()
                    except sqlite3.Error:  # pragma: no cover - defensive
                        pass
                    raise RepositoryError("sqlite create failed") from None
        return ItineraryDraftRecord(
            id=draft_id, owner=owner, created_at=created_at,
            start_poi_id=start_poi_id, end_poi_id=end_poi_id,
            stop_count=int(stop_count), payload=payload)

    def get(self, owner: str, draft_id: str) -> Optional[ItineraryDraftRecord]:
        with self._connect() as conn:
            try:
                row = conn.execute(
                    "SELECT id, owner, created_at, start_poi_id, end_poi_id, "
                    "stop_count, payload FROM itinerary_drafts "
                    "WHERE id = ? AND owner = ?",
                    (draft_id, owner),
                ).fetchone()
            except sqlite3.Error:
                raise RepositoryError("sqlite get failed") from None
        return self._row_to_record(row) if row is not None else None

    def list(self, owner: str, *, limit: int, offset: int
             ) -> Tuple[List[ItineraryDraftRecord], int]:
        with self._connect() as conn:
            try:
                total = conn.execute(
                    "SELECT COUNT(*) FROM itinerary_drafts WHERE owner = ?",
                    (owner,),
                ).fetchone()[0]
                rows = conn.execute(
                    "SELECT id, owner, created_at, start_poi_id, end_poi_id, "
                    "stop_count, payload FROM itinerary_drafts "
                    "WHERE owner = ? ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                    (owner, limit, offset),
                ).fetchall()
            except sqlite3.Error:
                raise RepositoryError("sqlite list failed") from None
        return [self._row_to_record(row) for row in rows], int(total)

    def delete(self, owner: str, draft_id: str) -> bool:
        with self._lock:
            with self._connect() as conn:
                try:
                    cursor = conn.execute(
                        "DELETE FROM itinerary_drafts WHERE id = ? AND owner = ?",
                        (draft_id, owner),
                    )
                    conn.commit()
                except sqlite3.Error:
                    try:
                        conn.rollback()
                    except sqlite3.Error:  # pragma: no cover - defensive
                        pass
                    raise RepositoryError("sqlite delete failed") from None
                return cursor.rowcount == 1

    def close(self) -> None:
        self._closed = True

    def health(self) -> Dict[str, Any]:
        """Bounded observational probe; never creates or mutates storage.

        Opens the database read/write-existing (``mode=rw``, never creates),
        verifies the required columns are queryable with a ``LIMIT 0`` statement
        and reports unavailable on any connection/schema error. It performs no
        DDL, no journal-mode change and no canary write, and recovers only when
        the actually initialized database and schema are present again.
        """
        if self._closed:
            return {"available": False, "backend": self.backend, "detail": "closed"}
        try:
            with self._connect(mode="rw") as conn:
                conn.execute(_HEALTH_PROBE).fetchone()
        except (RepositoryError, sqlite3.Error):
            return {"available": False, "backend": self.backend,
                    "detail": "storage unavailable"}
        return {"available": True, "backend": self.backend, "detail": None}
