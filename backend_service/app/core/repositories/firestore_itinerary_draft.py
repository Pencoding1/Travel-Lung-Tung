"""Optional Firestore adapter for itinerary drafts (OC-027).

This adapter is **import-safe**: it imports no ``firebase_admin`` at module load
and instead operates on an injected Firestore ``client``. The app can therefore
start with no Firebase package, credential or network access, and the adapter can
be exercised against a fake client. Enabling it is a deliberate opt-in (see
``build_firestore_repository``), and there is no automatic fallback from a failed
Firebase store to SQLite.

Error boundary (OC-027-R1): every operation (create/get/list/delete/health)
normalizes failures into a sanitized :class:`RepositoryError`; no raw provider
message, credential or path is surfaced. ``list`` is **bounded at the storage
query level**: it issues a count aggregation for the owner total and a
``order_by + offset + limit`` page query, so it never materializes every owner
document. This requires the ``owner`` equality filter to be combined with an
``created_at`` order (a composite index in production) and an aggregation-capable
client; if the client cannot serve those, the operation fails closed rather than
downloading the whole collection.

The legacy Firebase repositories in ``app.core.infrastructure.repository`` are
left untouched; this is a separate, additive adapter for the draft workflow.
Live Firebase/Aggregation integration is **not** verified here — only a fake
client is exercised in tests.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.core.repositories.itinerary_draft import (
    ItineraryDraftRecord,
    ItineraryDraftRepository,
    RepositoryError,
    utc_now_iso,
)

COLLECTION_NAME = "itinerary_drafts"
_DESCENDING = "DESCENDING"


class FirestoreItineraryDraftRepository(ItineraryDraftRepository):
    backend = "firebase"

    def __init__(self, client: Any, collection: str = COLLECTION_NAME):
        self._client = client
        self._collection = client.collection(collection)
        self._collection_name = collection

    @staticmethod
    def _to_record(data: Dict[str, Any]) -> ItineraryDraftRecord:
        return ItineraryDraftRecord(
            id=data["id"], owner=data["owner"], created_at=data["created_at"],
            start_poi_id=data.get("start_poi_id"),
            end_poi_id=data.get("end_poi_id"),
            stop_count=int(data.get("stop_count", 0)),
            payload=data.get("payload") or {},
        )

    @staticmethod
    def _count(owner_query: Any) -> int:
        """Owner-scoped total via a count aggregation (no document download)."""
        try:
            result = owner_query.count().get()
            return int(result[0].value)
        except Exception as exc:  # noqa: BLE001 - sanitized
            raise RepositoryError(
                f"firestore count failed: {type(exc).__name__}") from None

    def create(self, owner: str, payload: Dict[str, Any], *,
               start_poi_id: Optional[str], end_poi_id: Optional[str],
               stop_count: int) -> ItineraryDraftRecord:
        draft_id = f"draft_{uuid.uuid4().hex}"
        created_at = utc_now_iso()
        data = {
            "id": draft_id, "owner": owner, "created_at": created_at,
            "start_poi_id": start_poi_id, "end_poi_id": end_poi_id,
            "stop_count": int(stop_count), "payload": payload,
        }
        try:
            self._collection.document(draft_id).set(data)
        except Exception as exc:  # noqa: BLE001 - sanitized store failure
            raise RepositoryError(
                f"firestore create failed: {type(exc).__name__}") from None
        return ItineraryDraftRecord(
            id=draft_id, owner=owner, created_at=created_at,
            start_poi_id=start_poi_id, end_poi_id=end_poi_id,
            stop_count=int(stop_count), payload=payload)

    def get(self, owner: str, draft_id: str) -> Optional[ItineraryDraftRecord]:
        try:
            snapshot = self._collection.document(draft_id).get()
        except Exception as exc:  # noqa: BLE001 - sanitized store failure
            raise RepositoryError(
                f"firestore get failed: {type(exc).__name__}") from None
        if not getattr(snapshot, "exists", False):
            return None
        data = snapshot.to_dict() or {}
        if data.get("owner") != owner:
            return None
        return self._to_record(data)

    def list(self, owner: str, *, limit: int, offset: int
             ) -> Tuple[List[ItineraryDraftRecord], int]:
        try:
            owner_query = self._collection.where("owner", "==", owner)
            total = self._count(owner_query)
            page = (owner_query
                    .order_by("created_at", direction=_DESCENDING)
                    .offset(offset)
                    .limit(limit))
            docs = list(page.stream())
        except RepositoryError:
            raise
        except Exception as exc:  # noqa: BLE001 - sanitized store failure
            raise RepositoryError(
                f"firestore list failed: {type(exc).__name__}") from None
        return [self._to_record(doc.to_dict() or {}) for doc in docs], total

    def delete(self, owner: str, draft_id: str) -> bool:
        try:
            snapshot = self._collection.document(draft_id).get()
            if not getattr(snapshot, "exists", False):
                return False
            data = snapshot.to_dict() or {}
            if data.get("owner") != owner:
                return False
            snapshot.reference.delete()
            return True
        except Exception as exc:  # noqa: BLE001 - sanitized store failure
            raise RepositoryError(
                f"firestore delete failed: {type(exc).__name__}") from None

    def close(self) -> None:
        return None

    def health(self) -> Dict[str, Any]:
        """Bounded liveness probe (at most one document streamed), sanitized."""
        try:
            for _ in self._collection.limit(1).stream():
                break
        except Exception:  # noqa: BLE001 - never leak provider detail
            return {"available": False, "backend": self.backend,
                    "detail": "storage unavailable"}
        return {"available": True, "backend": self.backend, "detail": None}


def build_firestore_repository(*, key_path: Optional[str] = None,
                               project_id: Optional[str] = None
                               ) -> FirestoreItineraryDraftRepository:
    """Lazily construct a Firestore-backed repository (opt-in only).

    ``firebase_admin`` is imported here, never at module load. A missing package
    or credential fails loudly; there is no fallback to another backend.
    """
    import firebase_admin  # noqa: WPS433 - intentionally lazy
    from firebase_admin import credentials, firestore

    app = None
    if key_path:
        if firebase_admin._apps:
            app = firebase_admin.get_app()
        else:
            cred = credentials.Certificate(key_path)
            app = firebase_admin.initialize_app(cred)
    client = firestore.client(app) if app is not None else firestore.client()
    return FirestoreItineraryDraftRepository(client)
