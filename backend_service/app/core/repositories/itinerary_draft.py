"""Repository abstraction for durable itinerary drafts (OC-027).

The abstraction is deliberately small and storage-agnostic. Concrete adapters
(local SQLite, optional Firestore) implement the same five operations; the API
layer depends only on this interface, so the app factory can inject a fake in
tests with no network or database.

Ownership is part of every read/write signature: a draft is only ever returned,
listed or deleted for the subject that created it. Adapters must apply the
``owner`` filter in the storage query (parameterized), not post-filter in memory,
so an unauthorized subject cannot discover another record — including by reusing
its id.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def utc_now_iso() -> str:
    """Current UTC instant as a timezone-aware ISO-8601 string (second resolution)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class RepositoryError(Exception):
    """Base class for storage-layer failures."""


class RepositoryUnavailable(RepositoryError):
    """No durable store is configured; the workflow cannot run."""


class DuplicateDraftId(RepositoryError):
    """A generated draft id collided with an existing row."""


class RepositoryClosed(RepositoryError):
    """The repository was used after ``close()``."""


@dataclass(frozen=True)
class ItineraryDraftRecord:
    id: str
    owner: str
    created_at: str
    start_poi_id: Optional[str]
    end_poi_id: Optional[str]
    stop_count: int
    payload: Dict[str, Any]


class ItineraryDraftRepository(ABC):
    """Storage contract for the authenticated itinerary-draft workflow."""

    backend: str = "abstract"

    @abstractmethod
    def create(self, owner: str, payload: Dict[str, Any], *,
               start_poi_id: Optional[str], end_poi_id: Optional[str],
               stop_count: int) -> ItineraryDraftRecord:
        """Persist a new draft owned by ``owner`` with a server-generated id."""

    @abstractmethod
    def get(self, owner: str, draft_id: str) -> Optional[ItineraryDraftRecord]:
        """Return the draft only if it exists *and* belongs to ``owner``."""

    @abstractmethod
    def list(self, owner: str, *, limit: int, offset: int
             ) -> Tuple[List[ItineraryDraftRecord], int]:
        """Return ``(page, total_for_owner)`` ordered newest-first."""

    @abstractmethod
    def delete(self, owner: str, draft_id: str) -> bool:
        """Delete the draft only if it belongs to ``owner``; else report False."""

    @abstractmethod
    def close(self) -> None:
        """Release owned resources. Idempotent."""

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """Report availability honestly (``available``/``backend``/``detail``)."""

    @property
    def available(self) -> bool:
        return bool(self.health().get("available"))


class NullItineraryDraftRepository(ItineraryDraftRepository):
    """Explicit no-storage backend.

    Used when the deployment has not opted into a durable store. Reads return
    empty and writes fail closed with :class:`RepositoryUnavailable`, so the
    service never silently accepts a draft it cannot durably keep.
    """

    backend = "none"

    def create(self, owner: str, payload: Dict[str, Any], *,
               start_poi_id: Optional[str], end_poi_id: Optional[str],
               stop_count: int) -> ItineraryDraftRecord:
        raise RepositoryUnavailable(
            "no itinerary-draft storage is configured; set ITINERARY_STORAGE")

    def get(self, owner: str, draft_id: str) -> Optional[ItineraryDraftRecord]:
        return None

    def list(self, owner: str, *, limit: int, offset: int
             ) -> Tuple[List[ItineraryDraftRecord], int]:
        return [], 0

    def delete(self, owner: str, draft_id: str) -> bool:
        return False

    def close(self) -> None:
        return None

    def health(self) -> Dict[str, Any]:
        return {"available": False, "backend": self.backend,
                "detail": "no storage configured"}
