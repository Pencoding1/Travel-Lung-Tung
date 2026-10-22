"""Functional fakes for the OC-014 graph-lifecycle tests.

Nothing here connects to a database. Three kinds of collaborator are provided:

* ``RecordingTransaction`` / ``RecordingSession`` / ``RecordingDriver`` /
  ``FakeConnector`` -- enough of the neo4j surface for the *real*
  ``MemgraphUnitOfWork`` to run against a captured transaction. This is how the
  category wiring and error paths are proven through the real UnitOfWork rather
  than through a fake ``.cats`` that could mask a wiring bug.
* ``ServiceFakeUnitOfWork`` -- a transactional UnitOfWork that only records
  whether it committed or rolled back, for the management-service failure paths.
* ``TransactionalNearbyGraph`` -- a small transactional edge model used to show
  that deleting stale edges and rebuilding them share one transaction, so a
  failed rebuild rolls the deletion back.
"""

from typing import Any, Dict, List, Optional


class FakeRecord:
    """Mimics a neo4j record: ``.data()`` plus ``[]`` / ``.get`` access."""

    def __init__(self, data: Dict[str, Any]):
        self._data = dict(data)

    def data(self) -> Dict[str, Any]:
        return dict(self._data)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)


class RecordingTransaction:
    """Records every ``run`` call and replays queued record batches.

    ``responses`` is a list of *per-call* record lists so a multi-query flow
    (for example an existence check followed by a create) can return different
    results. Once the queue is exhausted an empty batch is returned.
    """

    def __init__(
        self,
        responses: Optional[List[List[Dict[str, Any]]]] = None,
        *,
        fail_on_run: Optional[int] = None,
        run_error: Optional[Exception] = None,
        commit_error: Optional[Exception] = None,
        rollback_error: Optional[Exception] = None,
    ):
        self.responses = list(responses or [])
        self.calls: List[Dict[str, Any]] = []
        self.commit_calls = 0
        self.rollback_calls = 0
        self.close_calls = 0
        self._index = 0
        self._closed = False
        self._fail_on_run = fail_on_run
        self._run_error = run_error or RuntimeError("scripted run failure")
        self._commit_error = commit_error
        self._rollback_error = rollback_error

    def run(self, query, parameters=None):
        call_index = len(self.calls)
        self.calls.append({"query": query, "parameters": dict(parameters or {})})
        if self._fail_on_run is not None and call_index == self._fail_on_run:
            raise self._run_error
        if self._index < len(self.responses):
            batch = self.responses[self._index]
            self._index += 1
        else:
            batch = []
        return [FakeRecord(record) for record in batch]

    def commit(self):
        self.commit_calls += 1
        if self._commit_error is not None:
            raise self._commit_error

    def rollback(self):
        self.rollback_calls += 1
        if self._rollback_error is not None:
            raise self._rollback_error

    def closed(self) -> bool:
        return self._closed

    def close(self):
        self.close_calls += 1
        self._closed = True


class RecordingSession:
    def __init__(self, transaction):
        self._transaction = transaction
        self.begin_calls = 0
        self.close_calls = 0

    def begin_transaction(self):
        self.begin_calls += 1
        if isinstance(self._transaction, Exception):
            raise self._transaction
        return self._transaction

    def close(self):
        self.close_calls += 1


class RecordingDriver:
    def __init__(self, session):
        self._session = session
        self.session_calls = 0

    def session(self):
        self.session_calls += 1
        if isinstance(self._session, Exception):
            raise self._session
        return self._session


class FakeConnector:
    """Minimal connector: ``MemgraphUnitOfWork`` only reads ``.driver``."""

    def __init__(self, driver=None):
        self.driver = driver


class ServiceFakeRepository:
    """Category/POI-style repository with a controllable failure point."""

    def __init__(self, *, existing=None, fail_on: Optional[str] = None):
        self.existing = existing
        self.fail_on = fail_on
        self.created: List[Any] = []
        self.updated: List[Any] = []
        self.deleted: List[str] = []

    def get_by_id(self, id):
        return self.existing

    def create(self, entity):
        if self.fail_on == "create":
            raise RuntimeError("raw provider failure text")
        self.created.append(entity)
        return entity

    def update(self, id, entity):
        if self.fail_on == "update":
            raise RuntimeError("raw provider failure text")
        self.updated.append((id, entity))
        return entity

    def delete(self, id):
        if self.fail_on == "delete":
            raise RuntimeError("raw provider failure text")
        self.deleted.append(id)
        return True


class ServiceFakeUnitOfWork:
    """Transactional UnitOfWork that only records commit/rollback decisions."""

    def __init__(self, repo=None, *, fail_on_enter: bool = False):
        self.pois = repo or ServiceFakeRepository()
        self.cats = repo or ServiceFakeRepository()
        self.categories = self.cats
        self.enter_count = 0
        self.exit_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self._fail_on_enter = fail_on_enter
        self._active = False

    def __enter__(self):
        self.enter_count += 1
        if self._fail_on_enter:
            raise RuntimeError("begin failed")
        self._active = True
        return self

    def __exit__(self, exc_type, exc_val, traceback):
        self.exit_count += 1
        self._active = False
        if exc_type:
            self.rollback_count += 1
        else:
            self.commit_count += 1
        return False

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


class TransactionalNearbyGraph:
    """Tiny transactional model of ``:NEAR_BY`` edges.

    ``begin`` snapshots the current edges into a pending set; mutating methods
    change only the pending set; ``commit`` promotes it and ``rollback``
    discards it. Canonical (sorted-tuple) undirected edges mirror the real
    repository's undirected storage.
    """

    def __init__(self, edges=None):
        self.edges = {self._canonical(a, b) for a, b in (edges or set())}
        self._pending: Optional[set] = None

    @staticmethod
    def _canonical(a, b):
        return (a, b) if a <= b else (b, a)

    def begin(self):
        self._pending = set(self.edges)

    def delete_incident(self, anchors):
        anchors = set(anchors)
        self._pending = {e for e in self._pending if not (e[0] in anchors or e[1] in anchors)}

    def add(self, a, b):
        self._pending.add(self._canonical(a, b))

    def commit(self):
        self.edges = set(self._pending)
        self._pending = None

    def rollback(self):
        self._pending = None
