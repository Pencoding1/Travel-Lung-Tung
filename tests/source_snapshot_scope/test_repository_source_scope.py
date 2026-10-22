"""Write-derivation and fail-closed retrieval against the real repository code.

A recording/sequence transaction captures or replays data; no Memgraph server is
contacted. This proves emitted query/parameter contracts and the Python
qualification path, not live engine execution.
"""

import copy
import hashlib

import pytest

pytest.importorskip("neo4j")

from app.core.domain.graph_entities import (
    POI,
    SourceMetadata,
    canonical_source_metadata_json,
)
from app.core.domain.source_scope import (
    SourceSnapshotSelection,
    derive_source_area,
    derive_source_area_id,
)
from app.core.infrastructure.db.repositories.memgraph import MemgraphPOIRepository
from scope_fixtures import (
    INPUT_SHA,
    NAMESPACE,
    POI_ID,
    graph_record,
    lineage_row,
    metadata_dict,
    poi_payload,
    typed_metadata,
)

OTHER_POI_ID = "hcm_primary_geojson_internal:other000000000000000000000000000000"


class FakeRecord:
    def __init__(self, data):
        self._data = dict(data)

    def data(self):
        return dict(self._data)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getitem__(self, key):
        return self._data[key]


class RecordingTransaction:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])

    def run(self, query, parameters=None):
        self.calls.append({"query": query, "parameters": dict(parameters or {})})
        batch = self.responses.pop(0) if self.responses else []
        return [FakeRecord(row) for row in batch]


def _selection(city="HCMC", area="Go Vap"):
    return SourceSnapshotSelection(
        dataset_namespace=NAMESPACE,
        input_sha256=INPUT_SHA,
        source_area_id=derive_source_area_id(NAMESPACE, INPUT_SHA, city, area),
    )


def _validated(raw):
    return POI.model_validate(raw).model_dump(mode="json")


def test_all_three_writes_derive_scalar_selector_from_validated_metadata():
    metadata = typed_metadata()
    expected = derive_source_area(metadata)
    payload = _validated(poi_payload(source_metadata=metadata_dict()))
    snapshot = copy.deepcopy(payload)

    tx = RecordingTransaction()
    repo = MemgraphPOIRepository(tx)
    repo.batch_create([payload])
    repo.create(POI.model_validate(payload))
    repo.update(POI_ID, POI.model_validate(payload))

    assert payload == snapshot
    assert len(tx.calls) == 3
    for call in tx.calls:
        query = call["query"]
        assert "source_area_id: poi.source_area_id" in query
        assert "source_dataset_namespace: poi.source_dataset_namespace" in query
        assert "source_snapshot_sha256: poi.source_snapshot_sha256" in query

    batch_record = tx.calls[0]["parameters"]["batch"][0]
    single = tx.calls[1]["parameters"]["poi"]
    updated = tx.calls[2]["parameters"]["poi"]
    for record in (batch_record, single, updated):
        assert record["source_area_id"] == expected.source_area_id
        assert record["source_dataset_namespace"] == NAMESPACE
        assert record["source_snapshot_sha256"] == INPUT_SHA
        metadata_obj = SourceMetadata.model_validate_json(
            record["source_metadata_json"]
        )
        canonical = canonical_source_metadata_json(metadata_obj)
        assert record["source_metadata_sha256"] == hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()


def test_missing_metadata_clears_all_stale_selector_properties():
    payload = _validated(poi_payload(source_metadata=None))
    tx = RecordingTransaction()
    repo = MemgraphPOIRepository(tx)
    repo.create(POI.model_validate(payload))
    repo.update(POI_ID, POI.model_validate(payload))
    repo.batch_create([payload])

    for call in tx.calls:
        assert "source_area_id: poi.source_area_id" in call["query"]
    for parameters in (
        tx.calls[0]["parameters"]["poi"],
        tx.calls[1]["parameters"]["poi"],
        tx.calls[2]["parameters"]["batch"][0],
    ):
        assert parameters.get("source_area_id") is None
        assert parameters.get("source_dataset_namespace") is None
        assert parameters.get("source_snapshot_sha256") is None
        assert parameters.get("source_metadata_json") is None
        assert parameters.get("administrative_scope") is None


def test_default_compound_query_excludes_every_provenance_bearing_record():
    tx = RecordingTransaction()
    repo = MemgraphPOIRepository(tx)
    repo.get_compound_explore_lite(city_id="c1")
    query = tx.calls[0]["query"]
    assert "p.source_metadata_json IS NULL" in query
    assert "p.source_area_id IS NULL" in query
    assert "coalesce(p.administrative_scope, '') <> 'source_snapshot_area_only'" in query
    assert "p.source_metadata_json IS NULL" in query.split("SKIP $offset")[0]


def test_source_mode_matches_valid_uncached_and_rejects_corrupt_evidence():
    matching_uncached = graph_record(cached=False)
    matching_cached = graph_record()
    mismatch = graph_record(
        OTHER_POI_ID,
        row=lineage_row(poi_id=OTHER_POI_ID, raw_district="District 1"),
        cached=False,
    )
    corrupt_sha = graph_record(override_sha="0" * 64)
    copied = graph_record(cached=False)
    copied["id"] = "another_poi_id"
    cache_mismatch = graph_record(
        cache_area_id=derive_source_area_id(
            NAMESPACE, INPUT_SHA, "Hanoi", "Go Vap"
        )
    )

    tx = RecordingTransaction(
        responses=[
            [
                matching_uncached,
                matching_cached,
                mismatch,
                corrupt_sha,
                copied,
                cache_mismatch,
            ]
        ]
    )
    repo = MemgraphPOIRepository(tx)
    results, report = repo.get_compound_explore_source(
        _selection(), limit=15, offset=0
    )

    assert [poi.id for poi in results] == [
        matching_uncached["id"],
        matching_cached["id"],
    ]
    assert results[0].source_context.raw_city == "HCMC"
    assert results[0].source_context.raw_area == "Go Vap"
    assert results[0].source_context.source_area_id == _selection().source_area_id
    assert "raw_lineage_json" not in results[0].model_dump()
    assert results[0].administrative_context is None
    assert results[0].administrative_context_status == "unverified_source_area"
    assert report["scanned_record_count"] == 6
    assert report["matched_record_count"] == 2
    assert report["excluded_corrupt_count"] == 3
    assert report["excluded_scope_mismatch_count"] == 1
    assert report["truncated"] is False

    query = tx.calls[0]["query"]
    assert "p.source_area_id = $source_area_id" in query
    assert "p.source_dataset_namespace = $dataset_namespace" in query
    assert "p.source_snapshot_sha256 = $input_sha256" in query
    assert "OR p.source_area_id IS NULL" in query
    assert "LIMIT $page_size" in query


def test_source_mode_applies_offset_and_limit_after_qualification():
    records = [
        graph_record(cached=False),
        graph_record(cached=False),
        graph_record(cached=False),
    ]
    tx = RecordingTransaction(responses=[records])
    repo = MemgraphPOIRepository(tx)
    results, report = repo.get_compound_explore_source(
        _selection(), limit=1, offset=1
    )
    assert len(results) == 1
    assert report["matched_record_count"] == 3
    assert report["scan_complete"] is True


def test_iter_source_scope_records_is_keyset_bounded_and_metadata_based():
    tx = RecordingTransaction()
    repo = MemgraphPOIRepository(tx)
    repo.iter_source_scope_records(after_id="p1", limit=50)
    query = tx.calls[0]["query"]
    assert "p.source_metadata_json IS NOT NULL" in query
    assert "$after_id IS NULL OR p.id > $after_id" in query
    assert "ORDER BY p.id" in query
    assert "LIMIT $limit" in query
    assert tx.calls[0]["parameters"] == {"after_id": "p1", "limit": 50}
