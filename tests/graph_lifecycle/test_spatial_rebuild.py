"""Spatial rebuild replacement semantics.

Evidence produced here is explicitly labelled:

* **Query-contract (unexecuted Cypher):** the real repository runs against a
  ``RecordingTransaction``; the captured Cypher is inspected. It is never sent
  to a database.
* **Fake transactional model:** ``TransactionalNearbyGraph`` shows that a delete
  followed by a failing rebuild is rolled back as one unit.
"""

import pytest

from app.core.infrastructure.db.repositories.memgraph import (
    IncompatibleStoredRadiusError,
    MemgraphPOIRepository,
    UnknownStoredRadiusError,
)
from graph_fakes import RecordingTransaction, TransactionalNearbyGraph


def _repo(responses):
    tx = RecordingTransaction(responses)
    return MemgraphPOIRepository(tx), tx


def test_district_rebuild_deletes_then_rebuilds_in_one_transaction():
    repo, tx = _repo([
        [],                              # 0: incident radii (consistent)
        [{"deleted_edges": 2}],          # 1: delete stale incident edges
        [{"created_edges": 5}],          # 2: rebuild canonical pairs
    ])

    created = repo.build_nearby_edges_for_district("d1", 3.0)

    assert created == 5
    assert len(tx.calls) == 3
    delete_query = tx.calls[1]["query"]
    rebuild_query = tx.calls[2]["query"]

    # Delete: anchored on the district, only incident edges, invalid anchors kept.
    assert "<-[:LOCATE_AT]-(anchor:POI)" in delete_query
    assert "MATCH (anchor)-[r:NEAR_BY]-(:POI)" in delete_query
    assert "DELETE rel" in delete_query
    assert "latitude IS NOT NULL" not in delete_query  # invalid anchors cleaned too

    # Rebuild: conservative prefilter, canonical both orientations, full precision.
    assert "MATCH (p2:POI)" in rebuild_query
    assert "CASE WHEN id(p1) < id(p2) THEN p1 ELSE p2 END AS a" in rebuild_query
    assert "CASE WHEN id(p1) < id(p2) THEN p2 ELSE p1 END AS b" in rebuild_query
    assert "WITH DISTINCT a, b" in rebuild_query
    assert "MERGE (a)-[r:NEAR_BY]-(b)" in rebuild_query
    assert "dist_meters / 1000.0" in rebuild_query
    assert "round(" not in rebuild_query
    assert "AND id(p1) < id(p2)" not in rebuild_query  # not gated on anchor id
    # Memgraph 3.13.2 has no ``degrees``/``radians``; the emitted Cypher uses
    # the exact arithmetic equivalents backed by ``pi()``.
    assert (
        "($radius_km / $earth_radius_lower_bound_km) * 180.0 / pi()"
        in rebuild_query
    )
    assert "* pi() / 180.0" in rebuild_query
    assert "degrees(" not in rebuild_query
    assert "radians(" not in rebuild_query


def test_delete_precedes_rebuild_and_never_touches_non_incident_edges():
    repo, tx = _repo([[], [{"deleted_edges": 1}], [{"created_edges": 1}]])
    repo.build_nearby_edges_for_district("d1", 3.0)

    assert "DELETE rel" in tx.calls[1]["query"]
    assert "MERGE (a)-[r:NEAR_BY]-(b)" in tx.calls[2]["query"]

    delete_query = tx.calls[1]["query"]
    # The delete is scoped to anchor-incident edges only: it never deletes an
    # edge whose endpoints are both outside the district.
    assert "MATCH (anchor)-[r:NEAR_BY]-(:POI)" in delete_query


def test_duplicate_old_edges_are_deduplicated_on_delete_and_merge():
    repo, tx = _repo([[], [{"deleted_edges": 2}], [{"created_edges": 1}]])
    repo.build_nearby_edges_for_district("d1", 3.0)

    # Delete collapses repeated incident relationships; rebuild MERGEs the
    # canonical undirected pair so a duplicate old edge cannot survive.
    assert "WITH DISTINCT r" in tx.calls[1]["query"]
    assert "MERGE (a)-[r:NEAR_BY]-(b)" in tx.calls[2]["query"]


def test_mixed_stored_radius_is_rejected_before_any_write():
    repo, tx = _repo([[{"radius_km": 3.0}, {"radius_km": 5.0}]])

    with pytest.raises(IncompatibleStoredRadiusError):
        repo.build_nearby_edges_for_district("d1", 3.0)

    # Only the consistency read ran; nothing was deleted or rebuilt.
    assert len(tx.calls) == 1


def test_application_uniform_incompatible_radius_is_rejected_before_delete():
    # A uniform 5 km configuration is NOT compatible with the fixed 3 km
    # application policy: the application must not silently flip it.
    repo, tx = _repo([[{"radius_km": 5.0}]])

    with pytest.raises(IncompatibleStoredRadiusError):
        repo.build_nearby_edges_for_district("d1", 3.0)

    assert len(tx.calls) == 1
    assert "MATCH (anchor)-[r:NEAR_BY]-(:POI)" in tx.calls[0]["query"]


def test_application_uniform_matching_radius_succeeds():
    repo, tx = _repo([
        [{"radius_km": 3.0}],
        [{"deleted_edges": 2}],
        [{"created_edges": 1}],
    ])

    created = repo.build_nearby_edges_for_district("d1", 3.0)

    assert created == 1
    assert tx.calls[2]["parameters"]["radius_km"] == 3.0


def test_application_legacy_missing_radius_is_an_unknown_gate():
    repo, tx = _repo([[{"radius_km": None}]])

    with pytest.raises(UnknownStoredRadiusError):
        repo.build_nearby_edges_for_poi("poi_x", 3.0)

    # The unknown gate runs before any deletion.
    assert len(tx.calls) == 1


def test_explicit_migration_allows_uniform_different_radius():
    # The offline/migration policy is a distinctly separate, explicit opt-out:
    # a uniform different radius is a legitimate wholesale rebuild.
    repo, tx = _repo([
        [{"radius_km": 5.0}],
        [{"deleted_edges": 3}],
        [{"created_edges": 1}],
    ])

    created = repo.migrate_nearby_edges_for_district("d1", 1.0)

    assert created == 1
    assert tx.calls[2]["parameters"]["radius_km"] == 1.0


def test_poi_rebuild_targets_a_single_poi_contract():
    repo, tx = _repo([
        [],
        [{"deleted_edges": 1}],
        [{"created_edges": 2}],
    ])

    created = repo.build_nearby_edges_for_poi("poi_x", 3.0)

    assert created == 2
    assert "MATCH (anchor:POI {id: $poi_id})" in tx.calls[1]["query"]
    assert "MATCH (p1:POI {id: $poi_id})" in tx.calls[2]["query"]
    assert tx.calls[1]["parameters"] == {"poi_id": "poi_x"}


def test_rollback_between_delete_and_rebuild_retains_old_edges():
    """Fake transactional model: a failed rebuild undoes the delete."""

    old_edges = {("p1", "p2"), ("p2", "p3")}
    graph = TransactionalNearbyGraph(edges=old_edges)

    class Repo:
        def build_nearby_edges_for_district(self, district_id, radius_km):
            graph.delete_incident({"p2"})  # all edges incident to p2
            raise RuntimeError("rebuild boom")

    class Uow:
        def __init__(self):
            self.pois = Repo()

        def __enter__(self):
            graph.begin()
            return self

        def __exit__(self, exc_type, exc_val, tb):
            if exc_type:
                graph.rollback()
            else:
                graph.commit()
            return False

        def commit(self):
            graph.commit()

        def rollback(self):
            graph.rollback()

    with pytest.raises(RuntimeError):
        with Uow() as uow:
            uow.pois.build_nearby_edges_for_district("d1", 3.0)

    # Both incident edges were pending-deleted; commit would have emptied the
    # graph, so retaining the originals proves the rollback undid the delete.
    assert graph.edges == old_edges
