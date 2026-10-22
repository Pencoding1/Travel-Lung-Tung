"""Fake collaborators for the OC-007 MCP contract tests.

These are functional fake transaction / repository / UnitOfWork objects. The
Cypher strings produced by the real repository classes are *captured and
inspected* (or mapped through fake records); no database server, driver or
network connection is ever created. Any test that exercises a query therefore
documents "fake transaction" evidence, not graph integration.
"""

from types import SimpleNamespace
from typing import Any, Dict, List, Optional


class FakeRecord:
    """Mimics a neo4j record: exposes ``.data()`` and supports ``[]`` access."""

    def __init__(self, data: Dict[str, Any]):
        self._data = dict(data)

    def data(self) -> Dict[str, Any]:
        return dict(self._data)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)


class FakeTransaction:
    """Captures every query/parameter pair and replays queued records."""

    def __init__(self, records: Optional[List[Dict[str, Any]]] = None):
        self.records = list(records or [])
        self.calls: List[Dict[str, Any]] = []

    def run(self, query, parameters=None):
        self.calls.append({"query": query, "parameters": dict(parameters or {})})
        result = []
        for record in self.records:
            result.append(record if hasattr(record, "data") else FakeRecord(record))
        return result

    def closed(self) -> bool:  # pragma: no cover - parity with neo4j transaction
        return False


class FakePOIRepository:
    def __init__(
        self,
        *,
        graph_payload: Optional[Dict[str, Any]] = None,
        compound_results=None,
        location_matches=None,
        categories=None,
        pois_by_id=None,
    ):
        self.graph_payload = graph_payload
        self.compound_results = list(compound_results or [])
        self.location_matches = list(location_matches or [])
        self.categories = list(categories or [])
        self.pois_by_id = dict(pois_by_id or {})
        self.compound_calls: List[Dict[str, Any]] = []

    def get_poi_graph_payload(self, id, radius_km=3.0, limit=5):
        return self.graph_payload

    def get_compound_explore_lite(self, **kwargs):
        self.compound_calls.append(dict(kwargs))
        return list(self.compound_results)

    def search_location_id(self, keyword, limit=15):
        return list(self.location_matches)

    def get_all_categories(self):
        return list(self.categories)

    def get_by_id(self, id):
        return self.pois_by_id.get(id)


class FakeCategoryRepository:
    def __init__(self, existing=None):
        self.existing = existing
        self.created = []
        self.updated = []

    def get_by_id(self, id):
        return self.existing

    def create(self, entity):
        self.created.append(entity)
        return entity

    def update(self, id, entity):
        self.updated.append((id, entity))
        return entity


class FakeUnitOfWork:
    """Minimal UnitOfWork with repositories and entered/exited bookkeeping."""

    def __init__(self, poi_repo: Optional[FakePOIRepository] = None,
                 cat_repo: Optional[FakeCategoryRepository] = None):
        self.pois = poi_repo or FakePOIRepository()
        self.cats = cat_repo or FakeCategoryRepository()
        self.enter_count = 0
        self.exit_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    def __enter__(self):
        self.enter_count += 1
        return self

    def __exit__(self, exc_type, exc_val, traceback):
        self.exit_count += 1
        if exc_type:
            self.rollback_count += 1
        else:
            self.commit_count += 1
        return False

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


class ThrowingDocumentRepository:
    """A document repository whose retrieval always fails."""

    def get_poi_documents(self, poi_id: str) -> dict:
        raise RuntimeError("provider exploded with secret-ish raw message")


class NotImplementedDocumentRepository:
    def get_poi_documents(self, poi_id: str) -> dict:
        from travel_shared.exceptions import IntentedNotImplementedException

        raise IntentedNotImplementedException("Document RAG not implemented")


def poi_stub(latitude=10.0, longitude=106.0):
    return SimpleNamespace(latitude=latitude, longitude=longitude)
