"""OC-038 repository contract tests against the real production queries.

A recording transaction captures the emitted Cypher and parameters. This is
explicitly NOT a live Memgraph execution proof; it establishes the scalar
persistence fields, the null-address/source-only guards and stale-link removal
that the driver would execute.
"""

import copy
import hashlib

import pytest

pytest.importorskip("neo4j")

from app.core.domain.graph_entities import (
    POI,
    canonical_source_metadata_json,
    decode_source_metadata,
)
from app.core.infrastructure.db.repositories.memgraph import (
    MemgraphPOIRepository,
    MemgraphUserBehaviorRepository,
)
from provenance_fixtures import metadata_dict, poi_payload


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
        if self.responses:
            batch = self.responses.pop(0)
        else:
            batch = []
        return [FakeRecord(row) for row in batch]


def _validated(raw):
    return POI.model_validate(raw).model_dump(mode="json")


def _guarded_hierarchy(query):
    start = query.index(
        "FOREACH (ignoreMe IN CASE WHEN build_current_hierarchy THEN [1] ELSE [] END |"
    )
    end = query.index(
        "FOREACH (ignoreMe IN CASE WHEN NOT build_current_hierarchy THEN [1] ELSE [] END |",
        start,
    )
    return query[start:end]


def _assert_hierarchy_is_guarded(query):
    block = _guarded_hierarchy(query)
    for merge in (
        "MERGE (n:Nation",
        "MERGE (c:City",
        "MERGE (d:District",
        "MERGE (s:Street",
        "MERGE (p)-[:LOCATE_AT]->",
    ):
        assert merge in block
    # The source-only / null-address guard is part of the same condition.
    assert "coalesce(poi.administrative_scope, '') <> 'source_snapshot_area_only'" in query
    assert "poi.address IS NOT NULL" in query


def test_batch_persists_canonical_scalar_provenance_without_mutation():
    raw = poi_payload(source_metadata=metadata_dict())
    snapshot = copy.deepcopy(raw)
    payload = [_validated(raw)]
    tx = RecordingTransaction()

    MemgraphPOIRepository(tx).batch_create(payload)

    assert raw == snapshot  # caller payload untouched
    emitted = tx.calls[0]["parameters"]["batch"][0]
    assert isinstance(emitted["source_metadata_json"], str)
    assert "source_metadata_json" in tx.calls[0]["query"]
    metadata, status = decode_source_metadata(
        emitted["source_metadata_json"], emitted["source_metadata_sha256"]
    )
    assert status == "valid"
    assert metadata.raw_lineage_json == metadata_dict()["raw_lineage_json"]
    assert emitted["administrative_scope"] == "source_snapshot_area_only"

    assert emitted["source_metadata_sha256"] == hashlib.sha256(
        emitted["source_metadata_json"].encode("utf-8")
    ).hexdigest()


def test_single_create_and_update_persist_the_same_scalar_contract():
    entity = POI.model_validate(poi_payload(source_metadata=metadata_dict()))
    for method in ("create", "update"):
        tx = RecordingTransaction()
        repo = MemgraphPOIRepository(tx)
        if method == "create":
            repo.create(entity)
        else:
            repo.update(entity.id, entity)
        query = tx.calls[0]["query"]
        poi = tx.calls[0]["parameters"]["poi"]
        assert "source_metadata_json: poi.source_metadata_json" in query
        assert "source_metadata_sha256: poi.source_metadata_sha256" in query
        assert "administrative_scope: poi.administrative_scope" in query
        assert decode_source_metadata(
            poi["source_metadata_json"], poi["source_metadata_sha256"]
        )[1] == "valid"


def test_null_address_and_contact_are_safe_on_all_three_writes():
    raw = poi_payload(address=None, contact_info=None)
    entity = POI.model_validate(raw)
    dumped = _validated(raw)

    tx = RecordingTransaction()
    MemgraphPOIRepository(tx).batch_create([dumped])
    _assert_hierarchy_is_guarded(tx.calls[0]["query"])

    for method in ("create", "update"):
        tx = RecordingTransaction()
        repo = MemgraphPOIRepository(tx)
        if method == "create":
            repo.create(entity)
        else:
            repo.update(entity.id, entity)
        query = tx.calls[0]["query"]
        _assert_hierarchy_is_guarded(query)
        # No unconditional hierarchy outside the guard.
        guarded = _guarded_hierarchy(query)
        assert query.count("MERGE (n:Nation") == guarded.count("MERGE (n:Nation")
        assert query.count("MERGE (c:City") == guarded.count("MERGE (c:City")
        assert query.count("MERGE (d:District") == guarded.count("MERGE (d:District")


def test_source_only_payload_never_reaches_an_unguarded_current_hierarchy():
    payload = [_validated(poi_payload(source_metadata=metadata_dict()))]
    tx = RecordingTransaction()
    MemgraphPOIRepository(tx).batch_create(payload)

    query = tx.calls[0]["query"]
    _assert_hierarchy_is_guarded(query)
    guarded = _guarded_hierarchy(query)
    assert query.count("MERGE (n:Nation") == guarded.count("MERGE (n:Nation")
    assert query.count("MERGE (d:District") == guarded.count("MERGE (d:District")
    # City/district shortcuts are never written for source-only records.
    assert "SET p.addr_city = null" in query


def test_repeated_upsert_and_update_remove_stale_locate_at():
    for method in ("batch", "create", "update"):
        tx = RecordingTransaction()
        repo = MemgraphPOIRepository(tx)
        entity = POI.model_validate(poi_payload())
        if method == "batch":
            repo.batch_create([entity.model_dump(mode="json")])
        elif method == "create":
            repo.create(entity)
        else:
            repo.update(entity.id, entity)
        query = tx.calls[0]["query"]
        assert "OPTIONAL MATCH (p)-[old_loc:LOCATE_AT]->()" in query
        assert "DELETE old_loc" in query
        assert query.index("DELETE old_loc") < query.index(
            "FOREACH (ignoreMe IN CASE WHEN build_current_hierarchy THEN [1] ELSE [] END |"
        )


def test_empty_categories_do_not_drop_the_outer_poi_row():
    raw = poi_payload(source_metadata=None, poi_categories=[], tag=None)
    entity = POI.model_validate(raw)
    for method in ("batch", "create", "update"):
        tx = RecordingTransaction()
        repo = MemgraphPOIRepository(tx)
        if method == "batch":
            repo.batch_create([entity.model_dump(mode="json")])
        elif method == "create":
            repo.create(entity)
        else:
            repo.update(entity.id, entity)
        query = tx.calls[0]["query"]
        assert "UNWIND poi.poi_categories" not in query
        assert "FOREACH (cat IN CASE WHEN poi.poi_categories IS NOT NULL" in query


def test_explicit_category_and_tag_ids_are_still_the_merge_identity():
    payload = [
        _validated(
            poi_payload(
                source_metadata=None,
                poi_categories=[
                    {
                        "id": "hcm_primary_geojson:source-category:coffee",
                        "name": "Coffee",
                        "context": "source label",
                    }
                ],
                tag={"id": "tag_coffee", "name": "Coffee"},
            )
        )
    ]
    tx = RecordingTransaction()
    MemgraphPOIRepository(tx).batch_create(payload)
    query = tx.calls[0]["query"]
    assert "MERGE (t:Tag {id: poi.tag.id})" in query
    assert "MERGE (catNode:Category {id: cat.id})" in query
    assert "MERGE (t:Tag {name: poi.tag.name})" not in query
    assert "MERGE (catNode:Category {name: cat.name})" not in query


def test_compound_read_exposes_source_scope_and_never_resolves_it_as_current():
    metadata = metadata_dict()
    entity = POI.model_validate(poi_payload(source_metadata=metadata))
    canonical = canonical_source_metadata_json(entity.source_metadata)

    record = {
        "id": entity.id,
        "name": "the gioi sua",
        "operation_time": None,
        "full_address": "681 Đường Lê Đức Thọ, Go Vap, HCMC, Vietnam",
        "source_metadata_json": canonical,
        "source_metadata_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "administrative_scope": "source_snapshot_area_only",
        "categories": [],
        "offers": [],
        "administrative_context_chains": [
            {
                "city_id": "hcmc_vietnam",
                "district_id": "go vap_hcmc",
                "city_name": "HCMC",
                "district_name": "Go Vap",
            }
        ],
    }
    tx = RecordingTransaction(responses=[[record]])
    results = MemgraphPOIRepository(tx).get_compound_explore_lite(city_id="hcmc_vietnam")

    assert len(results) == 1
    result = results[0]
    assert result.administrative_scope == "source_snapshot_area_only"
    assert result.source_metadata_status == "valid"
    assert result.source_metadata is not None
    assert result.administrative_context is None
    assert result.administrative_context_status == "unverified_source_area"
    # The query may still traverse genuine chains, but it never uses the flat
    # source address shortcuts for city/district scoping.
    assert "p.addr_city" not in tx.calls[0]["query"]
    assert "p.addr_district" not in tx.calls[0]["query"]


def test_compound_read_reports_corrupt_provenance_without_trusting_chains():
    record = {
        "id": "p1",
        "name": "Cafe",
        "operation_time": None,
        "full_address": "x",
        "source_metadata_json": "{not-json",
        "source_metadata_sha256": "0" * 64,
        "administrative_scope": "source_snapshot_area_only",
        "categories": [],
        "offers": [],
        "administrative_context_chains": [
            {
                "city_id": "c1",
                "district_id": "d1",
                "city_name": "HCMC",
                "district_name": "Go Vap",
            }
        ],
    }
    tx = RecordingTransaction(responses=[[record]])
    result = MemgraphPOIRepository(tx).get_compound_explore_lite(city_id="c1")[0]
    assert result.source_metadata is None
    assert result.source_metadata_status == "corrupt"
    assert result.administrative_context is None
    assert result.administrative_context_status == "provenance_corrupt"


def test_compound_read_binds_valid_metadata_to_the_returned_poi_id():
    metadata = metadata_dict()
    entity = POI.model_validate(poi_payload(source_metadata=metadata))
    canonical = canonical_source_metadata_json(entity.source_metadata)
    record = {
        "id": "WRONG_INDEPENDENT_TEST_ID",
        "name": "the gioi sua",
        "operation_time": None,
        "full_address": "x",
        "source_metadata_json": canonical,
        "source_metadata_sha256": hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest(),
        "administrative_scope": "source_snapshot_area_only",
        "categories": [],
        "offers": [],
        "administrative_context_chains": [
            {
                "city_id": "hcmc_vietnam",
                "district_id": "go vap_hcmc",
                "city_name": "HCMC",
                "district_name": "Go Vap",
            }
        ],
    }
    tx = RecordingTransaction(responses=[[record]])
    result = MemgraphPOIRepository(tx).get_compound_explore_lite(city_id="c1")[0]

    assert result.id == "WRONG_INDEPENDENT_TEST_ID"
    assert result.source_metadata is None
    assert result.source_metadata_status == "corrupt"
    assert result.administrative_context is None
    assert result.administrative_context_status == "provenance_corrupt"


def test_full_crud_read_retains_the_full_raw_lineage():
    metadata = metadata_dict()
    entity = POI.model_validate(poi_payload(source_metadata=metadata))
    canonical = canonical_source_metadata_json(entity.source_metadata)
    poi_data = {
        "id": entity.id,
        "name": entity.name,
        "longitude": entity.longitude,
        "latitude": entity.latitude,
        "operation_time": None,
        "rating": None,
        "menu": [],
        "full_address": "source full address",
        "source_metadata": canonical,
        "contact_info": {"phone_number": None, "fanpage": None, "website": None},
        "poi_categories": [],
        "tag": None,
    }
    tx = RecordingTransaction(responses=[[{"poi_data": poi_data}]])
    poi = MemgraphPOIRepository(tx).get_by_id(entity.id)

    assert poi is not None
    assert poi.source_metadata.raw_lineage_json == metadata["raw_lineage_json"]
    assert poi.source_metadata.raw_lineage_sha256 == metadata["raw_lineage_sha256"]
    assert "raw_lineage_json" in poi.model_dump_json()


def test_current_jurisdiction_selection_excludes_source_provenance_and_keeps_projection():
    metadata = metadata_dict()
    entity = POI.model_validate(poi_payload(source_metadata=metadata))
    canonical = canonical_source_metadata_json(entity.source_metadata)
    poi_data = {
        "id": entity.id,
        "name": entity.name,
        "longitude": entity.longitude,
        "latitude": entity.latitude,
        "operation_time": None,
        "rating": None,
        "menu": [],
        "address": {
            "street_name": "681 Duong Le Duc Tho",
            "ward": None,
            "district": "Go Vap",
            "city": "HCMC",
            "nation": "Vietnam",
        },
        "source_metadata": canonical,
        "contact_info": {"phone_number": None, "fanpage": None, "website": None},
        "poi_categories": [],
        "tag": None,
    }
    tx = RecordingTransaction(responses=[[{"poi_data": poi_data}]])
    results = MemgraphUserBehaviorRepository(tx).get_preferred_pois(
        "u1", "HCMC", "Go Vap"
    )
    query = tx.calls[0]["query"]

    assert "p.source_metadata_json IS NULL" in query
    assert "p.administrative_scope IS NULL" in query
    assert "source_metadata: p.source_metadata_json" in query
    assert results[0].source_metadata is not None
    assert results[0].source_metadata.raw_lineage_json == metadata["raw_lineage_json"]

    tx_delegate = RecordingTransaction()
    MemgraphUserBehaviorRepository(tx_delegate).get_routing_candidates(
        "u1", "HCMC", "Go Vap"
    )
    delegate_query = tx_delegate.calls[0]["query"]
    assert "p.source_metadata_json IS NULL" in delegate_query
    assert "p.administrative_scope IS NULL" in delegate_query