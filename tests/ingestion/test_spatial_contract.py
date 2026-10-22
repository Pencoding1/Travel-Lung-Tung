"""OC-017 bulk-ingestion spatial stage contract.

The production ingestion service runs for real; the repository/UoW are the
in-memory fakes whose ``build_nearby_edges_for_poi`` implements the spatial
contract. This asserts the *separation* of concerns: POI-write accounting
(accepted / validation_failed / database_failed) is never rewritten by a
spatial failure, which is reported through a separate structured field.
"""

import asyncio
import json

import pytest

from app.core.services import ingestion as ingestion_module
from app.core.services.ingestion import POIIngestionService
from app.core.utils.broadcaster import IngestionBroadcaster
from app.core.utils.updater import SpatialUpdater

from ingestion_fakes import FakePOIRepository, UoWFactory, valid_poi


@pytest.fixture(autouse=True)
def _no_retry_sleep():
    """Skip tenacity backoff for both the write and the spatial stage."""
    write_retry = POIIngestionService._execute_chunk_with_retry.retry
    spatial_retry = SpatialUpdater._build_pois_with_retry.retry
    orig_write, orig_spatial = write_retry.sleep, spatial_retry.sleep
    write_retry.sleep = lambda _seconds: None
    spatial_retry.sleep = lambda _seconds: None
    yield
    write_retry.sleep = orig_write
    spatial_retry.sleep = orig_spatial


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
# Coverage: accepted changed ids (not only new districts)
# ---------------------------------------------------------------------------
def test_accepted_changed_ids_are_spatially_rebuilt(fresh_broadcaster):
    repo = FakePOIRepository()
    service = POIIngestionService(uow_factory=UoWFactory(repo))

    counts, events = run_and_collect(
        fresh_broadcaster,
        "job-spatial",
        service.process_background_remainder([valid_poi(i) for i in range(4)], "job-spatial"),
    )

    assert counts["accepted"] == 4
    assert counts["database_failed"] == 0
    rebuilt = [poi_id for poi_id, _ in repo.spatial_calls]
    assert set(rebuilt) == {"poi_0", "poi_1", "poi_2", "poi_3"}
    # Application path uses the single fixed 3 km service radius.
    assert all(radius == 3.0 for _, radius in repo.spatial_calls)

    terminal = events[-1]
    assert terminal["status"] == "success"
    assert terminal["spatial"]["status"] == "success"
    assert terminal["spatial"]["requested"] == 4
    assert terminal["spatial"]["succeeded"] == 4


def test_canary_and_background_spatial_reports_are_merged(fresh_broadcaster):
    repo = FakePOIRepository()
    service = POIIngestionService(uow_factory=UoWFactory(repo))

    records = [valid_poi(i) for i in range(12)]
    canary_result, remainder = service.process_canary_and_split(records, limit=10)

    counts, events = run_and_collect(
        fresh_broadcaster,
        "job-merge-spatial",
        service.process_background_remainder(
            remainder, "job-merge-spatial", canary_result, 10
        ),
    )

    assert counts["accepted"] == 12
    terminal = events[-1]
    assert terminal["spatial"]["requested"] == 12
    assert terminal["spatial"]["succeeded"] == 12
    assert terminal["spatial"]["status"] == "success"


# ---------------------------------------------------------------------------
# Duplicate ids + failed chunks
# ---------------------------------------------------------------------------
def test_duplicate_accepted_ids_are_rebuilt_once():
    repo = FakePOIRepository()
    service = POIIngestionService(uow_factory=UoWFactory(repo))

    result = service.process_ota_batch([valid_poi(0), valid_poi(0)])

    # Both records were accepted (no dedup of the write), but the spatial stage
    # de-duplicates so the same POI is rebuilt exactly once.
    assert result["payload"]["summary"]["accepted"] == 2
    assert repo.spatial_calls == [("poi_0", 3.0)]
    assert result["payload"]["spatial"]["requested"] == 1


def test_failed_chunk_ids_are_not_spatially_scheduled():
    repo = FakePOIRepository(fail_ids={"poi_1"})
    service = POIIngestionService(uow_factory=UoWFactory(repo))
    service.chunk_size = 1

    result = service.process_ota_batch([valid_poi(0), valid_poi(1), valid_poi(2)])

    rebuilt = {poi_id for poi_id, _ in repo.spatial_calls}
    assert rebuilt == {"poi_0", "poi_2"}
    assert "poi_1" not in rebuilt
    assert result["payload"]["summary"]["database_failed"] == 1
    assert result["payload"]["spatial"]["requested"] == 2


# ---------------------------------------------------------------------------
# Spatial failure must not rewrite write accounting
# ---------------------------------------------------------------------------
def test_spatial_failure_keeps_accepted_counts_and_reports_partial(fresh_broadcaster):
    repo = FakePOIRepository(spatial_fail_forever=True)
    service = POIIngestionService(uow_factory=UoWFactory(repo))

    counts, events = run_and_collect(
        fresh_broadcaster,
        "job-spatial-fail",
        service.process_background_remainder(
            [valid_poi(0), valid_poi(1), valid_poi(2)], "job-spatial-fail"
        ),
    )

    # The writes committed: accounting stays exact.
    assert counts["accepted"] == 3
    assert counts["database_failed"] == 0
    assert counts["validation_failed"] == 0

    terminal = events[-1]
    assert terminal["counts"] == counts
    assert terminal["spatial"]["status"] == "failed"
    assert terminal["spatial"]["failed"] == 3
    assert terminal["spatial"]["succeeded"] == 0
    # The spatial failure is surfaced, not hidden behind a blanket success.
    assert terminal["status"] == "partial_failure"
    # Sanitized: no raw provider text in the report.
    assert "simulated spatial outage" not in json.dumps(terminal["spatial"])


def test_spatial_failure_does_not_change_process_ota_batch_status_when_writes_ok():
    repo = FakePOIRepository(spatial_fail_forever=True)
    service = POIIngestionService(uow_factory=UoWFactory(repo))

    result = service.process_ota_batch([valid_poi(0)])

    assert result["is_success"] is True  # POI write contract still satisfied
    assert result["payload"]["summary"]["accepted"] == 1
    assert result["payload"]["status"] == "partial_failure"
    assert result["payload"]["spatial"]["status"] == "failed"


def test_bulk_incompatible_stored_radius_preserves_insert_count(fresh_broadcaster):
    # The repository's fixed-radius gate rejects a uniform 5 km stored policy.
    # The bulk writes have already committed, so accepted counts must be retained
    # while the spatial stage reports an explicit failure.
    repo = FakePOIRepository(
        spatial_error=ValueError("stored NEAR_BY radius 5.0 incompatible with 3.0")
    )
    service = POIIngestionService(uow_factory=UoWFactory(repo))

    counts, events = run_and_collect(
        fresh_broadcaster,
        "job-radius-gate",
        service.process_background_remainder(
            [valid_poi(0), valid_poi(1)], "job-radius-gate"
        ),
    )

    assert counts["accepted"] == 2
    assert counts["database_failed"] == 0

    terminal = events[-1]
    assert terminal["spatial"]["status"] == "failed"
    assert terminal["spatial"]["errors"]["poi_0"] == "ValueError"
    assert terminal["status"] == "partial_failure"
    assert "5.0 incompatible" not in json.dumps(terminal["spatial"])


# ---------------------------------------------------------------------------
# Updater-level bounding / dedup / sanitization
# ---------------------------------------------------------------------------
def test_rebuild_pois_dedups_and_bounds_coverage():
    repo = FakePOIRepository()
    updater = SpatialUpdater()

    report = updater.rebuild_pois(["a", "a", " b ", "c"], UoWFactory(repo), max_pois=2)

    assert report["requested"] == 3      # a, b, c (deduped, trimmed)
    assert report["attempted"] == 2      # bounded to max_pois
    assert report["truncated"] is True
    assert report["deferred"] == 1
    assert report["succeeded"] == 2
    assert report["status"] == "partial_failure"
    assert report["is_success"] is False


def test_rebuild_pois_sanitizes_provider_error():
    repo = FakePOIRepository(spatial_fail_forever=True)
    updater = SpatialUpdater()

    report = updater.rebuild_pois(["poi_x"], UoWFactory(repo))

    assert report["status"] == "failed"
    assert report["errors"] == {"poi_x": "RuntimeError"}
    assert "simulated spatial outage" not in json.dumps(report)


def test_rebuild_pois_empty_is_skipped_not_failed():
    updater = SpatialUpdater()
    report = updater.rebuild_pois([], UoWFactory(FakePOIRepository()))

    assert report["status"] == "skipped"
    assert report["is_success"] is True
    assert report["requested"] == 0
