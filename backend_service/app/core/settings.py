"""Backend storage configuration and repository construction (OC-027).

Storage is an explicit opt-in read from the process environment. The default is
``none``: the service starts, is import-safe (no ``firebase_admin``), and reports
its repository as unavailable rather than silently accepting drafts it cannot
keep. No backend ever falls back to another backend on failure.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from app.core.repositories.itinerary_draft import (
    ItineraryDraftRepository,
    NullItineraryDraftRepository,
)
from app.core.repositories.sqlite_itinerary_draft import SqliteItineraryDraftRepository

STORAGE_NONE = "none"
STORAGE_SQLITE = "sqlite"
STORAGE_FIREBASE = "firebase"
_VALID_STORAGE = (STORAGE_NONE, STORAGE_SQLITE, STORAGE_FIREBASE)


@dataclass(frozen=True)
class BackendSettings:
    storage: str = STORAGE_NONE
    sqlite_path: Optional[str] = None
    firebase_key_path: Optional[str] = None
    firebase_project_id: Optional[str] = None


def load_settings() -> BackendSettings:
    """Read backend settings from the environment, failing loudly on bad config."""
    raw = os.getenv("ITINERARY_STORAGE", STORAGE_NONE)
    storage = (raw or STORAGE_NONE).strip().lower()
    if storage not in _VALID_STORAGE:
        raise ValueError(
            f"ITINERARY_STORAGE must be one of {_VALID_STORAGE}, got {raw!r}")

    sqlite_path = os.getenv("ITINERARY_SQLITE_PATH") or None
    if storage == STORAGE_SQLITE and not sqlite_path:
        raise ValueError(
            "ITINERARY_STORAGE=sqlite requires ITINERARY_SQLITE_PATH")

    return BackendSettings(
        storage=storage,
        sqlite_path=sqlite_path,
        firebase_key_path=os.getenv("FIREBASE_KEY_PATH") or None,
        firebase_project_id=os.getenv("FIREBASE_PROJECT_ID") or None,
    )


def build_repository(settings: BackendSettings) -> ItineraryDraftRepository:
    """Construct the configured repository. Never falls back on failure."""
    if settings.storage == STORAGE_SQLITE:
        return SqliteItineraryDraftRepository(settings.sqlite_path or "")
    if settings.storage == STORAGE_FIREBASE:
        from app.core.repositories.firestore_itinerary_draft import (
            build_firestore_repository,
        )
        return build_firestore_repository(
            key_path=settings.firebase_key_path,
            project_id=settings.firebase_project_id)
    return NullItineraryDraftRepository()
