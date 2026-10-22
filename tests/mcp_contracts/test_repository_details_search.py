"""Repository tests for deep retrieval admin-context and location resolution.

Static query inspection plus fake-transaction mapping. No database is contacted.
"""

from app.core.infrastructure.db.repositories.memgraph import MemgraphPOIRepository
from mcp_fakes import FakeTransaction


def _build(records=None):
    tx = FakeTransaction(records)
    return MemgraphPOIRepository(tx), tx


# ---------------------------------------------------------------------------
# get_poi_graph_payload
# ---------------------------------------------------------------------------
def test_graph_payload_query_supports_both_parent_chain_shapes():
    repo, tx = _build([])
    repo.get_poi_graph_payload("p1")
    query = tx.calls[0]["query"]

    # Direct district shape.
    assert "MATCH (p)-[:LOCATE_AT]->(d1:District)-[:IN_CITY]->(city1:City)" in query
    # Street-mediated shape.
    assert "MATCH (p)-[:LOCATE_AT]->(:Street)-[:IN_DISTRICT]->(d2:District)-[:IN_CITY]->(city2:City)" in query
    # Raw chains are returned for contradiction detection in the resolver.
    assert "administrative_context_chains" in query
    # Explicit category ids are preserved.
    assert "POI_Categories: categories" in query
    assert "cat { .id, .name, .context }" in query


def test_graph_payload_returns_mapped_payload():
    payload = {
        "POI_ID": "p1",
        "POI_Name": "Cafe",
        "POI_Address": None,
        "POI_Category": "Coffee",
        "POI_Categories": [{"id": "cat_a", "name": "Coffee", "context": "c"}],
        "operation_time": "8-5",
        "latitude": 10.0,
        "longitude": 106.0,
        "POI_Contact_Info": {"phonenumber": None, "fanpage": None, "website": None},
        "Offers": [],
        "NEAR_BY": [],
        "administrative_context_chains": [
            {"city_id": "c1", "district_id": "d1",
             "city_name": "Hanoi", "district_name": "Quan 1"}
        ],
    }
    repo, _ = _build([{"graph_result": payload}])
    result = repo.get_poi_graph_payload("p1")
    assert result["POI_ID"] == "p1"
    assert result["administrative_context_chains"][0]["district_id"] == "d1"


def test_graph_payload_missing_returns_none():
    repo, _ = _build([])
    assert repo.get_poi_graph_payload("missing") is None


# ---------------------------------------------------------------------------
# search_location_id
# ---------------------------------------------------------------------------
def test_search_query_projects_parent_city_and_district():
    repo, tx = _build([])
    repo.search_location_id("District 1")
    query = tx.calls[0]["query"]
    assert "OPTIONAL MATCH (n)-[:IN_CITY]->(direct_city:City)" in query
    assert "OPTIONAL MATCH (n)-[:IN_DISTRICT]->(mid_district:District)-[:IN_CITY]->(via_city:City)" in query
    assert "COALESCE(via_city.id, direct_city.id) AS city_id" in query
    assert "mid_district.id AS district_id" in query
    assert "ORDER BY type ASC, name ASC, id ASC" in query
    assert "LIMIT $limit" in query


def test_search_mapping_district_has_parent_city():
    records = [
        {"type": "District", "id": "d1", "name": "Quan 1",
         "district_id": None, "district_name": None,
         "city_id": "c1", "city_name": "Hanoi"},
    ]
    repo, _ = _build(records)
    matches = repo.search_location_id("Quan 1")
    assert matches[0]["id"] == "d1"
    assert matches[0]["city_id"] == "c1"
    assert matches[0]["city_name"] == "Hanoi"


def test_search_mapping_street_has_district_and_city():
    records = [
        {"type": "Street", "id": "s1", "name": "Le Loi",
         "district_id": "d1", "district_name": "Quan 1",
         "city_id": "c1", "city_name": "Hanoi"},
    ]
    repo, _ = _build(records)
    matches = repo.search_location_id("Le Loi")
    assert matches[0]["district_id"] == "d1"
    assert matches[0]["city_id"] == "c1"


def test_search_skips_records_without_id():
    records = [{"type": "City", "id": None, "name": "ghost"}]
    repo, _ = _build(records)
    assert repo.search_location_id("ghost") == []
