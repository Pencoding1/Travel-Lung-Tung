"""OC-017 single-POI incident-edge rebuild integration.

Evidence type: **real** ``POIManagementService`` + **real**
``MemgraphPOIRepository``/``MemgraphUnitOfWork`` driven by a *captured*
``RecordingTransaction`` (fake neo4j driver). The Cypher is recorded and
inspected, never executed against a live graph. The transaction outcome
(commit/rollback counts) is observed on the fake transaction, which is exactly
the boundary that proves the source mutation is rolled back when the spatial
rebuild fails.
"""

import pytest

from app.core.infrastructure.db.uow import MemgraphUnitOfWork
from app.core.services.management import POIManagementService
from app.core.utils.spatial import NEARBY_RADIUS_KM_DEFAULT
from graph_fakes import FakeConnector, RecordingDriver, RecordingSession, RecordingTransaction


EXISTING_POI = {
    "id": "poi_1",
    "name": "Old Name",
    "longitude": 106.0,
    "latitude": 10.0,
    "operation_time": None,
    "rating": None,
    "menu": [],
    "poi_categories": [],
    "tag": None,
    "contact_info": {"phone_number": None, "fanpage": None, "website": None},
}

CREATE_PAYLOAD = {
    "id": "poi_1",
    "name": "New POI",
    "longitude": 106.7001,
    "latitude": 10.7001,
    "address": {"district": "quan 1", "city": "ho chi minh"},
}

UPDATE_PAYLOAD = {
    "name": "Moved POI",
    "longitude": 107.5001,   # different district / city
    "latitude": 10.9001,
    "address": {"district": "quan 3", "city": "ho chi minh"},
}


def _real_uow(responses=None, **tx_kwargs):
    tx = RecordingTransaction(responses, **tx_kwargs)
    session = RecordingSession(tx)
    driver = RecordingDriver(session)
    return MemgraphUnitOfWork(FakeConnector(driver)), tx, session, driver


def _queries(tx):
    return [call["query"] for call in tx.calls]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------
def test_create_rebuilds_incident_edges_in_the_same_transaction():
    # 0 get_by_id (no existing), 1 CREATE, 2 radius read, 3 delete, 4 rebuild.
    uow, tx, _session, _driver = _real_uow([
        [],
        [],
        [],
        [{"deleted_edges": 0}],
        [{"created_edges": 4}],
    ])
    service = POIManagementService(uow)

    outcome = service.create(dict(CREATE_PAYLOAD))

    assert outcome["is_success"] is True
    assert tx.commit_calls == 1
    assert tx.rollback_calls == 0
    queries = _queries(tx)
    assert "MERGE (p:POI {id: poi.id})" in queries[1]
    # Exactly one incident-edge delete and one rebuild (no double rebuild).
    assert sum("DELETE rel" in q for q in queries) == 1
    assert sum("MERGE (a)-[r:NEAR_BY]-(b)" in q for q in queries) == 1
    # Application path uses the single fixed service radius.
    assert tx.calls[4]["parameters"]["radius_km"] == NEARBY_RADIUS_KM_DEFAULT


# ---------------------------------------------------------------------------
# Move across district
# ---------------------------------------------------------------------------
def test_move_out_of_previous_district_replaces_all_incident_edges():
    uow, tx, _session, _driver = _real_uow([
        [{"poi_data": dict(EXISTING_POI)}],  # 0 get_by_id (exists)
        [],                                   # 1 update source properties
        [],                                   # 2 radius read (consistent)
        [{"deleted_edges": 3}],              # 3 delete old incident edges
        [{"created_edges": 2}],              # 4 rebuild new incident edges
    ])
    service = POIManagementService(uow)

    outcome = service.update("poi_1", dict(UPDATE_PAYLOAD))

    assert outcome["is_success"] is True
    assert tx.commit_calls == 1

    delete_query = tx.calls[3]["query"]
    # The delete is anchored on the POI id ONLY -- district-independent -- so the
    # edges the POI left in its OLD district are removed too.
    assert "MATCH (anchor:POI {id: $poi_id})" in delete_query
    assert "MATCH (anchor)-[r:NEAR_BY]-(:POI)" in delete_query
    assert "District" not in delete_query
    assert tx.calls[3]["parameters"] == {"poi_id": "poi_1"}

    rebuild_query = tx.calls[4]["query"]
    # The rebuild matches neighbours graph-wide, so NEW-district neighbours are
    # linked, and it uses the undirected canonical pair.
    assert "MATCH (p1:POI {id: $poi_id})" in rebuild_query
    assert "MATCH (p2:POI)" in rebuild_query
    assert "MERGE (a)-[r:NEAR_BY]-(b)" in rebuild_query
    assert tx.calls[4]["parameters"]["radius_km"] == NEARBY_RADIUS_KM_DEFAULT


def test_mixed_stored_radii_abort_mutation_honestly():
    # A mixed stored-radius configuration makes the repository raise inside the
    # transaction; the source update must NOT commit.
    uow, tx, _session, _driver = _real_uow([
        [{"poi_data": dict(EXISTING_POI)}],        # 0 get_by_id
        [],                                         # 1 update source properties
        [{"radius_km": 3.0}, {"radius_km": 5.0}],   # 2 mixed radii -> raise
    ])
    service = POIManagementService(uow)

    outcome = service.update("poi_1", dict(UPDATE_PAYLOAD))

    assert outcome["is_success"] is False
    assert outcome["error_type"] == "internal_error"
    assert tx.commit_calls == 0
    assert tx.rollback_calls == 1
    # No delete / rebuild query ran after the rejected radius read.
    assert all("DELETE rel" not in q for q in _queries(tx))
    assert all("MERGE (a)-[r:NEAR_BY]-(b)" not in q for q in _queries(tx))


def test_uniform_incompatible_radius_rolls_application_update_back():
    # A *uniform* 5 km stored configuration contradicts the fixed 3 km
    # application policy; the update must roll back rather than silently rebuild
    # the shared policy at 3 km.
    uow, tx, _session, _driver = _real_uow([
        [{"poi_data": dict(EXISTING_POI)}],  # 0 get_by_id
        [],                                   # 1 update source properties
        [{"radius_km": 5.0}],                # 2 uniform incompatible -> raise
    ])
    service = POIManagementService(uow)

    outcome = service.update("poi_1", dict(UPDATE_PAYLOAD))

    assert outcome["is_success"] is False
    assert outcome["error_type"] == "internal_error"
    assert tx.commit_calls == 0
    assert tx.rollback_calls == 1
    assert all("DELETE rel" not in q for q in _queries(tx))
    assert all("MERGE (a)-[r:NEAR_BY]-(b)" not in q for q in _queries(tx))


def test_uniform_three_km_application_update_succeeds():
    uow, tx, _session, _driver = _real_uow([
        [{"poi_data": dict(EXISTING_POI)}],  # 0 get_by_id
        [],                                   # 1 update source properties
        [{"radius_km": 3.0}],                # 2 gate: matches fixed 3 km
        [{"deleted_edges": 1}],              # 3 delete old incident edges
        [{"created_edges": 2}],              # 4 rebuild at 3 km
    ])
    service = POIManagementService(uow)

    outcome = service.update("poi_1", dict(UPDATE_PAYLOAD))

    assert outcome["is_success"] is True
    assert tx.commit_calls == 1
    assert tx.calls[4]["parameters"]["radius_km"] == NEARBY_RADIUS_KM_DEFAULT


def test_legacy_missing_radius_gates_application_update():
    # Legacy edges without a stored radius are an explicit unknown gate: the
    # application must not pretend they are validated.
    uow, tx, _session, _driver = _real_uow([
        [{"poi_data": dict(EXISTING_POI)}],  # 0 get_by_id
        [],                                   # 1 update source properties
        [{"radius_km": None}],               # 2 unknown/legacy -> raise
    ])
    service = POIManagementService(uow)

    outcome = service.update("poi_1", dict(UPDATE_PAYLOAD))

    assert outcome["is_success"] is False
    assert outcome["error_type"] == "internal_error"
    assert tx.commit_calls == 0
    assert tx.rollback_calls == 1
    assert all("DELETE rel" not in q for q in _queries(tx))


# ---------------------------------------------------------------------------
# Forced spatial failure rolls the source mutation back
# ---------------------------------------------------------------------------
def test_forced_rebuild_failure_rolls_source_update_back():
    # Fail on the rebuild run (call index 4) after the source update was issued
    # on the same transaction.
    uow, tx, _session, _driver = _real_uow(
        [
            [{"poi_data": dict(EXISTING_POI)}],
            [],
            [],
            [{"deleted_edges": 3}],
            [{"created_edges": 2}],
        ],
        fail_on_run=4,
    )
    service = POIManagementService(uow)

    outcome = service.update("poi_1", dict(UPDATE_PAYLOAD))

    assert outcome["is_success"] is False
    assert outcome["error_type"] == "internal_error"
    # The source update was written inside the transaction, then the rebuild
    # failed -> the whole transaction (including the source mutation) rolled back.
    assert "MATCH (p:POI {id: $id})" in tx.calls[1]["query"]
    assert tx.commit_calls == 0
    assert tx.rollback_calls == 1


def test_forced_rebuild_failure_on_create_rolls_back_and_is_sanitized():
    uow, tx, _session, _driver = _real_uow(
        [[], [], [], [{"deleted_edges": 0}], [{"created_edges": 0}]],
        fail_on_run=4,
        run_error=RuntimeError("raw provider secret text"),
    )
    service = POIManagementService(uow)

    outcome = service.create(dict(CREATE_PAYLOAD))

    assert outcome["is_success"] is False
    assert "raw provider secret text" not in str(outcome)
    assert tx.commit_calls == 0
    assert tx.rollback_calls == 1


# ---------------------------------------------------------------------------
# Invalid coordinate
# ---------------------------------------------------------------------------
def test_invalid_coordinate_is_rejected_before_any_transaction():
    uow, tx, _session, driver = _real_uow([])
    service = POIManagementService(uow)

    outcome = service.create({
        "id": "poi_bad",
        "name": "Bad",
        "longitude": 106.0,
        "latitude": 999.0,  # out of [-90, 90]
    })

    assert outcome["is_success"] is False
    assert outcome["error_type"] == "unprocessable_entity"
    assert driver.session_calls == 0
    assert tx.calls == []


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------
def test_delete_removes_poi_and_its_incident_edges_only():
    uow, tx, _session, _driver = _real_uow([
        [{"poi_data": dict(EXISTING_POI)}],  # 0 get_by_id
        [{"deleted_count": 1}],              # 1 DETACH DELETE
    ])
    service = POIManagementService(uow)

    outcome = service.delete("poi_1")

    assert outcome["is_success"] is True
    assert tx.commit_calls == 1
    delete_query = tx.calls[1]["query"]
    # DETACH DELETE removes the node and every incident edge (NEAR_BY included)
    # while unrelated nodes/edges are never matched.
    assert "MATCH (p:POI {id: $id})" in delete_query
    assert "DETACH DELETE p" in delete_query
    assert tx.calls[1]["parameters"] == {"id": "poi_1"}
