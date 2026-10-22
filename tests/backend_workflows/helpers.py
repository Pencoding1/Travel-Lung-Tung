"""Shared fakes and utilities for the OC-027 backend workflow tests.

Everything is in-process and synthetic: an in-memory repository, a fake Firestore
client and HMAC-signed tokens. No network, live database or Firebase call.
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import jwt
from httpx import ASGITransport, AsyncClient

from app.core.repositories.itinerary_draft import (
    DuplicateDraftId,
    ItineraryDraftRecord,
    ItineraryDraftRepository,
    utc_now_iso,
)

SECRET = "synthetic-backend-secret-0123456789abcdef"


def make_token(sub: str = "user-1", *, secret: str = SECRET,
               exp_delta: int = 3600, algorithm: str = "HS256",
               include_sub: bool = True, **claims: Any) -> str:
    payload: Dict[str, Any] = {"exp": int(time.time()) + exp_delta}
    if include_sub:
        payload["sub"] = sub
    payload.update(claims)
    if algorithm == "none":
        return jwt.encode(payload, None, algorithm="none")
    return jwt.encode(payload, secret, algorithm=algorithm)


def run_http(app, method: str, url: str, *, token: Optional[str] = None,
             json_body: Optional[Dict[str, Any]] = None,
             raw_content: Optional[bytes] = None,
             headers: Optional[Dict[str, str]] = None):
    """Drive the ASGI app in-process; return the httpx response."""
    async def _call():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            merged = dict(headers or {})
            if token is not None:
                merged["Authorization"] = f"Bearer {token}"
            return await client.request(method, url, json=json_body,
                                        content=raw_content, headers=merged)

    return asyncio.run(_call())


def sample_payload(*, uid: str = "user-1", budget: Optional[float] = None,
                   start: str = "poi_a", end: str = "poi_b",
                   validator_status: str = "unverifiable") -> Dict[str, Any]:
    """A minimal document matching the real ``/generate_itinerary`` response."""
    return {
        "status": "success",
        "reply": {
            "id": "itin_deadbeef",
            "id_source": "server",
            "uid": uid,
            "uid_source": "verified_jwt_sub",
            "start_poi_id": start,
            "end_poi_id": end,
            "total_estimated_budget": budget,
            "budget_is_estimate": True,
            "stops": [
                {
                    "date": "2026-01-01",
                    "visit_time": "2026-01-01T09:00:00+07:00",
                    "end_time": "2026-01-01T10:00:00+07:00",
                    "description": "walk and coffee",
                    "description_grounded": False,
                    "budget": budget,
                    "budget_is_estimate": True,
                    "poi": {"id": start, "name": "Synthetic POI A"},
                }
            ],
        },
        "planning": {"validator_status": validator_status,
                     "cost": {"status": "unknown"}},
        "grounding": {"scope_verification": "verified"},
    }


class InMemoryDraftRepository(ItineraryDraftRepository):
    """Owner-scoped in-memory store with the same semantics as SQLite."""

    backend = "memory"

    def __init__(self):
        self._rows: Dict[str, ItineraryDraftRecord] = {}
        self._lock = threading.Lock()
        self._closed = False

    def create(self, owner, payload, *, start_poi_id, end_poi_id, stop_count):
        with self._lock:
            draft_id = f"draft_{uuid.uuid4().hex}"
            record = ItineraryDraftRecord(
                id=draft_id, owner=owner, created_at=utc_now_iso(),
                start_poi_id=start_poi_id, end_poi_id=end_poi_id,
                stop_count=stop_count, payload=payload)
            self._rows[draft_id] = record
            return record

    def get(self, owner, draft_id):
        with self._lock:
            record = self._rows.get(draft_id)
            if record is None or record.owner != owner:
                return None
            return record

    def list(self, owner, *, limit, offset):
        with self._lock:
            owned = [r for r in self._rows.values() if r.owner == owner]
            owned.sort(key=lambda r: (r.created_at, r.id), reverse=True)
            return owned[offset:offset + limit], len(owned)

    def delete(self, owner, draft_id):
        with self._lock:
            record = self._rows.get(draft_id)
            if record is None or record.owner != owner:
                return False
            del self._rows[draft_id]
            return True

    def close(self):
        self._closed = True

    def health(self):
        return {"available": not self._closed, "backend": self.backend, "detail": None}


# ---------------------------------------------------------------------------
# Minimal fake Firestore for the optional adapter.
# ---------------------------------------------------------------------------
class _FakeSnapshot:
    def __init__(self, reference, data):
        self.reference = reference
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocumentRef:
    def __init__(self, store, doc_id):
        self._store = store
        self._id = doc_id

    def set(self, data):
        self._store[self._id] = dict(data)

    def get(self):
        return _FakeSnapshot(self, self._store.get(self._id))

    def delete(self):
        self._store.pop(self._id, None)


class _FakeAggregationResult:
    def __init__(self, value):
        self.value = value


class _FakeAggregationQuery:
    def __init__(self, value):
        self._value = value

    def get(self):
        return [_FakeAggregationResult(self._value)]


class _FakeQuery:
    """Query object that honours filter/order/offset/limit and count aggregation.

    ``stream`` logs each execution into the shared ``log`` so tests can prove the
    adapter pushed pagination to the storage query instead of materializing every
    document.
    """

    def __init__(self, docs, log, predicate=None, order=None, offset=0, limit=None):
        self._docs = docs
        self._log = log
        self._predicate = predicate
        self._order = order
        self._offset = offset
        self._limit = limit

    def _clone(self, **changes):
        state = {"predicate": self._predicate, "order": self._order,
                 "offset": self._offset, "limit": self._limit}
        state.update(changes)
        return _FakeQuery(self._docs, self._log, **state)

    def where(self, field, op, value):
        return self._clone(predicate=lambda data: data.get(field) == value)

    def order_by(self, field, direction=None):
        return self._clone(order=(field, direction))

    def offset(self, value):
        return self._clone(offset=value)

    def limit(self, value):
        return self._clone(limit=value)

    def _matching(self):
        rows = [(doc_id, data) for doc_id, data in self._docs.items()
                if self._predicate is None or self._predicate(data)]
        if self._order is not None:
            field, direction = self._order
            rows.sort(key=lambda pair: pair[1].get(field, ""),
                      reverse=(direction == "DESCENDING"))
        return rows

    def count(self):
        return _FakeAggregationQuery(len(self._matching()))

    def stream(self):
        self._log.append({"offset": self._offset, "limit": self._limit,
                          "ordered": self._order is not None,
                          "filtered": self._predicate is not None})
        rows = self._matching()
        end = None if self._limit is None else self._offset + self._limit
        for doc_id, data in rows[self._offset:end]:
            yield _FakeSnapshot(_FakeDocumentRef(self._docs, doc_id), data)


class FakeFirestoreClient:
    def __init__(self):
        self._collections: Dict[str, Dict[str, Any]] = {}
        self.query_log: List[Dict[str, Any]] = []

    def collection(self, name):
        return _FakeCollection(self._collections.setdefault(name, {}),
                               self.query_log)


class _FakeCollection:
    def __init__(self, docs, log):
        self._docs = docs
        self._log = log

    def document(self, doc_id):
        return _FakeDocumentRef(self._docs, doc_id)

    def where(self, field, op, value):
        return _FakeQuery(self._docs, self._log).where(field, op, value)

    def order_by(self, field, direction=None):
        return _FakeQuery(self._docs, self._log).order_by(field, direction)

    def offset(self, value):
        return _FakeQuery(self._docs, self._log).offset(value)

    def limit(self, value):
        return _FakeQuery(self._docs, self._log).limit(value)

    def count(self):
        return _FakeQuery(self._docs, self._log).count()

    def stream(self):
        return _FakeQuery(self._docs, self._log).stream()


LEAK_MARKER = "provider-secret:/srv/firebase/serviceAccountKey.json"


class FailingFirestoreClient:
    """Every storage operation raises, echoing a secret/path for sanitization tests."""

    def __init__(self, message: str = LEAK_MARKER):
        self._message = message

    def collection(self, name):
        return _FailingCollection(self._message)


class _FailingCollection:
    def __init__(self, message):
        self._message = message

    def document(self, doc_id):
        return _FailingDocument(self._message)

    def where(self, field, op, value):
        raise RuntimeError(self._message)

    def order_by(self, field, direction=None):
        raise RuntimeError(self._message)

    def offset(self, value):
        raise RuntimeError(self._message)

    def limit(self, value):
        raise RuntimeError(self._message)

    def count(self):
        raise RuntimeError(self._message)

    def stream(self):
        raise RuntimeError(self._message)


class _FailingDocument:
    def __init__(self, message):
        self._message = message

    def set(self, data):
        raise RuntimeError(self._message)

    def get(self):
        raise RuntimeError(self._message)

    def delete(self):
        raise RuntimeError(self._message)
