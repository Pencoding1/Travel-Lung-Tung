"""Repository contract tests for conjunctive exact-id exploration.

Two kinds of evidence are produced here:

* **Static query inspection** -- the Cypher string is asserted to contain the
  required structure (exact ids applied conjunctively, deterministic order,
  bound parameters). The query is never executed.
* **Fake transaction mapping** -- ``FakeTransaction`` replays queued records so
  the Python mapper is exercised. This is *not* a database integration test.
"""

import pytest

from app.core.infrastructure.db.repositories.memgraph import MemgraphPOIRepository
from mcp_fakes import FakeTransaction  # noqa: E402


def _build(records=None):
    tx = FakeTransaction(records)
    return MemgraphPOIRepository(tx), tx


# ---------------------------------------------------------------------------
# Static query contract
# ---------------------------------------------------------------------------
def test_compound_query_applies_every_id_conjunctively_before_limit():
    repo, tx = _build([])
    repo.get_compound_explore_lite(city_id="c1", district_id="d1")
    query = tx.calls[0]["query"]

    # Exact-id EXISTS clauses for every administrative level and category.
    assert "MATCH (p)-[:LOCATE_AT]->(:District)-[:IN_CITY]->(:City {id: $city_id})" in query
    assert "MATCH (p)-[:LOCATE_AT]->(:Street)-[:IN_DISTRICT]->(:District)-[:IN_CITY]->(:City {id: $city_id})" in query
    assert "MATCH (p)-[:LOCATE_AT]->(:District {id: $district_id})" in query
    assert "MATCH (p)-[:LOCATE_AT]->(:Street {id: $street_id})" in query
    assert "MATCH (p)-[:HAS_CATEGORY]->(:Category {id: $category_id})" in query

    # The city and district clauses are joined with AND (conjunction).
    city_idx = query.index("$city_id")
    district_clause = "AND ($district_id IS NULL OR"
    assert district_clause in query
    assert city_idx < query.index(district_clause)

    # Deterministic, duplicate-free page before the limit.
    assert "WITH DISTINCT p" in query
    assert "ORDER BY p.id" in query
    assert "SKIP $offset LIMIT $limit" in query

    # Product keyword is a bound parameter only (never interpolated).
    assert "toLower($product_keyword)" in query

    # No arbitrary over-fetch and no category-id rewriting.
    assert "FETCH" not in query
    assert "200" not in query
    assert "replace(" not in query


def test_compound_query_projects_structured_ids_and_admin_context():
    repo, tx = _build([])
    repo.get_compound_explore_lite(category_id="cat_a")
    query = tx.calls[0]["query"]
    assert "cat { .id, .name, .context }" in query
    assert "administrative_context_chains" in query
    assert "p.id AS id" in query


def test_compound_binds_exact_ids_without_transformation():
    repo, tx = _build([])
    repo.get_compound_explore_lite(
        city_id="city_hn", district_id="district_hn_1",
        street_id="st_1", category_id="cat_a", product_keyword="latte",
        limit=25, offset=5,
    )
    params = tx.calls[0]["parameters"]
    assert params == {
        "city_id": "city_hn",
        "district_id": "district_hn_1",
        "street_id": "st_1",
        "category_id": "cat_a",
        "product_keyword": "latte",
        "limit": 25,
        "offset": 5,
    }


# ---------------------------------------------------------------------------
# Fake-transaction mapper
# ---------------------------------------------------------------------------
def test_compound_maps_records_with_category_ids_and_context():
    records = [
        {
            "id": "p1",
            "name": "Cafe A",
            "operation_time": "8-5",
            "full_address": "1 Le Loi",
            "categories": [{"id": "cat_a", "name": "Coffee", "context": "warm"}],
            "offers": [{"name": "Latte", "price": 2.5}, {"name": None, "price": None}],
            "administrative_context_chains": [
                {"city_id": "c1", "district_id": "d1",
                 "city_name": "Hanoi", "district_name": "Quan 1"}
            ],
        }
    ]
    repo, _ = _build(records)
    results = repo.get_compound_explore_lite(city_id="c1", district_id="d1")

    assert len(results) == 1
    poi = results[0]
    assert poi.id == "p1"
    assert [c.id for c in poi.categories] == ["cat_a"]
    assert len(poi.offers) == 1  # the all-null offer is dropped, not invented
    assert poi.offers[0].name == "Latte" and poi.offers[0].price == 2.5
    assert poi.administrative_context.city_id == "c1"
    assert poi.administrative_context_status == "resolved"


def test_compound_ambiguous_context_yields_null_and_status():
    records = [
        {
            "id": "p1",
            "name": "Cafe A",
            "categories": [],
            "offers": [],
            "administrative_context_chains": [
                {"city_id": "c1", "district_id": "d1",
                 "city_name": "Hanoi", "district_name": "Quan 1"},
                {"city_id": "c2", "district_id": "d2",
                 "city_name": "Hanoi", "district_name": "Quan 2"},
            ],
        }
    ]
    repo, _ = _build(records)
    poi = repo.get_compound_explore_lite(district_id="d1")[0]
    assert poi.administrative_context is None
    assert poi.administrative_context_status == "ambiguous"


def test_compound_skips_records_without_id():
    records = [{"id": None, "name": "ghost"}, {"id": "p2", "name": "real"}]
    repo, _ = _build(records)
    results = repo.get_compound_explore_lite(city_id="c1")
    assert [r.id for r in results] == ["p2"]
