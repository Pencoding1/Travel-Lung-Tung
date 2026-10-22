"""OC-004 ingestion failure-accounting and transaction-ownership tests.

All collaborators are in-memory fakes; the production service and broadcaster
modules are imported and exercised for real. No database, network or credential
is used. FireStoreConnector / neo4j must never be imported.
"""

import asyncio
import sys

import pytest

from app.core.services import ingestion as ingestion_module
from app.core.services.ingestion import POIIngestionService
from app.core.utils.broadcaster import IngestionBroadcaster

from ingestion_fakes import FakePOIRepository, UoWFactory, valid_poi


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _no_retry_sleep():
    """Skip tenacity's real exponential backoff so retry tests stay fast."""
    retrying = POIIngestionService._execute_chunk_with_retry.retry
    original = retrying.sleep
    retrying.sleep = lambda _seconds: None
    yield
    retrying.sleep = original


@pytest.fixture
def fresh_broadcaster(monkeypatch):
    b = IngestionBroadcaster()
    monkeypatch.setattr(ingestion_module, "broadcaster", b)
    return b


async def _run_and_collect(broadcaster, job_id, awaitable):
    result = await awaitable
    events = [event async for event in broadcaster.subscribe(job_id)]
    return result, events


def run_and_collect(broadcaster, job_id, awaitable):
    return asyncio.run(asyncio.wait_for(_run_and_collect(broadcaster, job_id, awaitable), 2.0))


# ---------------------------------------------------------------------------
# Validation / accounting
# ---------------------------------------------------------------------------
def test_valid_batch_all_accepted():
    repo = FakePOIRepository()
    factory = UoWFactory(repo)
    service = POIIngestionService(uow_factory=factory)

    result = service.process_ota_batch([valid_poi(0), valid_poi(1), valid_poi(2)])

    assert result["is_success"] is True
    summary = result["payload"]["summary"]
    assert summary["total_received"] == 3
    assert summary["accepted"] == 3
    assert summary["validation_failed"] == 0
    assert summary["database_failed"] == 0
    assert result["payload"]["status"] == "success"
    assert len(repo.rows) == 3


def test_all_invalid_returns_unprocessable_entity_with_indices():
    service = POIIngestionService(uow_factory=UoWFactory(FakePOIRepository()))

    payload = [
        {"id": "", "name": "", "longitude": 1.0, "latitude": 1.0},
        42,
        None,
        [1, 2],
    ]
    result = service.process_ota_batch(payload)

    assert result["is_success"] is False
    assert result["error_type"] == "unprocessable_entity"
    summary = result["payload"]["summary"]
    assert summary["accepted"] == 0
    assert summary["validation_failed"] == 4
    assert result["payload"]["failed_indices"] == [0, 1, 2, 3]


def test_mixed_invalid_none_list_and_null_address():
    repo = FakePOIRepository()
    service = POIIngestionService(uow_factory=UoWFactory(repo))

    payload = [
        valid_poi(0),
        None,
        valid_poi(1, address=None),
        [1, 2],
        {"id": "bad", "name": "bad", "longitude": 999, "latitude": 0},
    ]
    result = service.process_ota_batch(payload)

    assert result["is_success"] is True
    summary = result["payload"]["summary"]
    assert summary["accepted"] == 2
    assert summary["validation_failed"] == 3
    assert result["payload"]["status"] == "partial_failure"
    assert result["payload"]["failed_indices"] == [1, 3, 4]
    # The null-address record must have been safely stored, not skipped.
    assert {row["id"] for row in repo.rows} == {"poi_0", "poi_1"}


# ---------------------------------------------------------------------------
# Transaction ownership / retries
# ---------------------------------------------------------------------------
def test_database_fail_then_success_uses_fresh_uow_instances():
    repo = FakePOIRepository(fail_times=1)
    factory = UoWFactory(repo)
    service = POIIngestionService(uow_factory=factory)

    result = service.process_ota_batch([valid_poi(0), valid_poi(1)])

    assert result["is_success"] is True
    assert result["payload"]["summary"]["accepted"] == 2
    assert result["payload"]["summary"]["database_failed"] == 0
    # The first two UoWs are the two write attempts (first fails, retry
    # succeeds); the spatial stage then opens its own fresh UoW. No attempt
    # reuses a closed transaction.
    assert repo.calls == 2, "one fresh UoW per write attempt is expected"
    assert factory.uows[0] is not factory.uows[1]


def test_exhausted_bounded_retries_reports_database_failure():
    repo = FakePOIRepository(fail_forever=True)
    factory = UoWFactory(repo)
    service = POIIngestionService(uow_factory=factory)

    result = service.process_ota_batch([valid_poi(0)])

    assert result["is_success"] is False
    assert result["error_type"] == "database_unavailable"
    summary = result["payload"]["summary"]
    assert summary["accepted"] == 0
    assert summary["database_failed"] == 1
    assert result["payload"]["failed_indices"] == [0]
    assert len(factory.uows) == 3, "retries must be bounded to 3 attempts"
    # No raw exception text / traceback is exposed.
    assert result["payload"]["database_details"][0]["error_type"] == "RuntimeError"


def test_service_does_not_hold_a_shared_uow():
    factory = UoWFactory(FakePOIRepository())
    service = POIIngestionService(uow_factory=factory)
    assert not hasattr(service, "uow")
    assert factory.uows == [], "constructing the service must not open a transaction"


# ---------------------------------------------------------------------------
# Background terminal accounting
# ---------------------------------------------------------------------------
def test_partial_chunk_failure_terminal_counts(fresh_broadcaster):
    repo = FakePOIRepository(fail_ids={"poi_1"})
    service = POIIngestionService(uow_factory=UoWFactory(repo))
    service.chunk_size = 1

    payload = [
        valid_poi(0),
        valid_poi(1),
        {"id": "", "name": "", "longitude": 1.0, "latitude": 1.0},
        valid_poi(2),
    ]
    counts, events = run_and_collect(
        fresh_broadcaster,
        "job-partial",
        service.process_background_remainder(payload, "job-partial"),
    )

    assert counts["accepted"] == 2
    assert counts["validation_failed"] == 1
    assert counts["database_failed"] == 1
    assert counts["processed"] == 4

    terminal = events[-1]
    assert terminal["type"] == "complete"
    assert terminal["status"] == "partial_failure"
    assert terminal["counts"] == counts
    assert terminal["failed_indices"] == [1, 2]


def test_background_success_status(fresh_broadcaster):
    repo = FakePOIRepository()
    service = POIIngestionService(uow_factory=UoWFactory(repo))

    counts, events = run_and_collect(
        fresh_broadcaster,
        "job-ok",
        service.process_background_remainder(
            [valid_poi(0, address=None), valid_poi(1)], "job-ok"
        ),
    )

    assert counts["accepted"] == 2
    terminal = events[-1]
    assert terminal["type"] == "complete"
    assert terminal["status"] == "success"


def test_background_all_database_failure_status_failed(fresh_broadcaster):
    repo = FakePOIRepository(fail_forever=True)
    service = POIIngestionService(uow_factory=UoWFactory(repo))

    counts, events = run_and_collect(
        fresh_broadcaster,
        "job-dbfail",
        service.process_background_remainder([valid_poi(0)], "job-dbfail"),
    )

    assert counts["accepted"] == 0
    assert counts["database_failed"] == 1
    assert events[-1]["status"] == "failed"


# ---------------------------------------------------------------------------
# Whole-batch merge: canary totals + original background offset
# ---------------------------------------------------------------------------
def test_terminal_totals_merge_canary_and_background(fresh_broadcaster):
    repo = FakePOIRepository()
    service = POIIngestionService(uow_factory=UoWFactory(repo))
    service.chunk_size = 5

    records = [valid_poi(i) for i in range(12)]
    records[2] = {"id": "", "name": "", "longitude": 0.0, "latitude": 0.0}  # canary idx 2
    records[11] = None  # background idx 11

    canary_result, remainder = service.process_canary_and_split(records, limit=10)
    assert len(remainder) == 2
    assert canary_result["is_success"] is True
    assert canary_result["payload"]["failed_indices"] == [2]

    start_index = len(records) - len(remainder)
    counts, events = run_and_collect(
        fresh_broadcaster,
        "job-merge",
        service.process_background_remainder(
            remainder, "job-merge", canary_result, start_index
        ),
    )

    assert counts["total_received"] == 12
    assert counts["accepted"] == 10
    assert counts["validation_failed"] == 2
    assert counts["database_failed"] == 0

    terminal = events[-1]
    assert terminal["type"] == "complete"
    assert terminal["status"] == "partial_failure"
    assert terminal["counts"] == counts
    assert terminal["failed_indices"] == [2, 11]


def test_partial_canary_not_hidden_by_successful_remainder(fresh_broadcaster):
    repo = FakePOIRepository()
    service = POIIngestionService(uow_factory=UoWFactory(repo))

    records = [valid_poi(i) for i in range(12)]
    records[0] = None  # invalid first record -> canary is partial

    canary_result, remainder = service.process_canary_and_split(records, limit=10)
    assert canary_result["payload"]["status"] == "partial_failure"
    assert len(remainder) == 2  # remainder is fully valid

    counts, events = run_and_collect(
        fresh_broadcaster,
        "job-canary-partial",
        service.process_background_remainder(
            remainder, "job-canary-partial", canary_result, 10
        ),
    )

    # Remainder fully succeeds, yet the canary failure must remain visible.
    assert counts["accepted"] == 11
    assert counts["validation_failed"] == 1
    terminal = events[-1]
    assert terminal["status"] == "partial_failure"
    assert terminal["failed_indices"] == [0]


# ---------------------------------------------------------------------------
# Canary-only terminal event
# ---------------------------------------------------------------------------
def test_small_canary_only_job_has_terminal_event(fresh_broadcaster):
    repo = FakePOIRepository()
    service = POIIngestionService(uow_factory=UoWFactory(repo))

    payload = [valid_poi(0), valid_poi(1)]
    canary_result, remainder = service.process_canary_and_split(payload, limit=10)
    assert remainder == []
    assert canary_result["is_success"] is True

    _, events = run_and_collect(
        fresh_broadcaster,
        "job-canary",
        service.finalize_canary_job("job-canary", canary_result),
    )

    terminal = events[-1]
    assert terminal["type"] == "complete"
    assert terminal["status"] == "success"
    assert terminal["counts"]["accepted"] == 2


# ---------------------------------------------------------------------------
# Connector side-effect guard
# ---------------------------------------------------------------------------
def test_repository_import_does_not_pull_db_connectors():
    import app.core.base.repository  # noqa: F401

    assert "neo4j" not in sys.modules
    assert "firebase_admin" not in sys.modules
    assert "app.core.infrastructure.db.database.connector" not in sys.modules
