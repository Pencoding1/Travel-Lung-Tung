"""Optional Firestore adapter tests against a fake client (OC-027).

No ``firebase_admin`` package, credential or network call is involved: the
adapter is driven by a fake Firestore client, proving it is import-safe and
owner-scoped. Live Firebase integration remains unverified (see the handoff).
"""

from __future__ import annotations

import helpers
from app.core.repositories.firestore_itinerary_draft import (
    FirestoreItineraryDraftRepository,
)


def _summary():
    return {"start_poi_id": "poi_a", "end_poi_id": "poi_b", "stop_count": 1}


def test_firestore_adapter_roundtrip_and_isolation():
    repo = FirestoreItineraryDraftRepository(helpers.FakeFirestoreClient())
    record = repo.create("user-1", {"reply": {"stops": []}}, **_summary())

    assert repo.get("user-1", record.id) is not None
    assert repo.get("user-2", record.id) is None

    records, total = repo.list("user-1", limit=10, offset=0)
    assert total == 1 and records[0].id == record.id
    assert repo.list("user-2", limit=10, offset=0) == ([], 0)

    assert repo.delete("user-2", record.id) is False
    assert repo.get("user-1", record.id) is not None
    assert repo.delete("user-1", record.id) is True
    assert repo.get("user-1", record.id) is None


def test_firestore_adapter_is_available():
    repo = FirestoreItineraryDraftRepository(helpers.FakeFirestoreClient())
    assert repo.health()["available"] is True
    assert repo.health()["backend"] == "firebase"
