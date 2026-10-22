"""Explicitly gated live test for the generated prefilter on real Memgraph.

Enable only with the verified OC-041-owned instance::

    $env:OC044_LIVE_MEMGRAPH_URI = "bolt://127.0.0.1:17687"
    .\\.venv-mcp-validation\\Scripts\\python.exe -m pytest \
        tests/memgraph_spatial_runtime/test_spatial_runtime_live.py

The executed query is read-only: ``UNWIND`` over parameter pairs, a ``RETURN``
of the generated prefilter expression plus ``point.distance``. No graph
mutation clause is present.
"""

from __future__ import annotations

import os

import pytest

from app.core.utils.spatial import (
    EARTH_RADIUS_KM_LOWER_BOUND,
    conservative_prefilter_cypher,
    pair_passes_prefilter,
)

from cases import RADII_KM, build_cases

EXPECTED_URI = "bolt://127.0.0.1:17687"


def _live_uri() -> str:
    uri = os.environ.get("OC044_LIVE_MEMGRAPH_URI", "").strip()
    if not uri:
        pytest.skip(
            "set OC044_LIVE_MEMGRAPH_URI=bolt://127.0.0.1:17687 to run the "
            "read-only real-engine gate"
        )
    if uri != EXPECTED_URI:
        pytest.fail(
            f"refusing non-owned/default URI {uri!r}; only {EXPECTED_URI!r} is allowed"
        )
    return uri


def _live_query() -> str:
    prefilter = conservative_prefilter_cypher(
        lat_a="pair.lat1",
        lon_a="pair.lon1",
        lat_b="pair.lat2",
        lon_b="pair.lon2",
    )
    return f"""
    UNWIND $pairs AS pair
    WITH pair,
         {prefilter} AS kept,
         point.distance(
             point({{latitude: pair.lat1, longitude: pair.lon1}}),
             point({{latitude: pair.lat2, longitude: pair.lon2}})
         ) AS dist_meters
    RETURN pair.case_id AS case_id,
           kept AS kept,
           dist_meters AS dist_meters
    """


def _graph_state(session) -> dict:
    record = session.run(
        "MATCH (n) WITH count(n) AS nodes "
        "OPTIONAL MATCH ()-[r]->() RETURN nodes, count(r) AS relationships"
    ).single()
    return {"nodes": int(record["nodes"]), "relationships": int(record["relationships"])}


def test_generated_prefilter_matches_python_reference_on_real_memgraph():
    neo4j = pytest.importorskip("neo4j")
    uri = _live_uri()

    cases = build_cases()
    query = _live_query()

    driver = neo4j.GraphDatabase.driver(uri, auth=None)
    try:
        with driver.session() as session:
            info = driver.get_server_info()
            assert "memgraph" in (getattr(info, "agent", "") or "").lower()

            before = _graph_state(session)
            assert before["nodes"] == 0, "owned instance must be empty before the gate"
            assert before["relationships"] == 0

            results: dict[str, dict] = {}
            for radius in RADII_KM:
                radius_cases = [case for case in cases if case[5] == radius]
                pairs = [
                    {
                        "case_id": case_id,
                        "lat1": lat1,
                        "lon1": lon1,
                        "lat2": lat2,
                        "lon2": lon2,
                    }
                    for case_id, lat1, lon1, lat2, lon2, _radius in radius_cases
                ]
                records = session.run(
                    query,
                    {
                        "pairs": pairs,
                        "radius_km": radius,
                        "earth_radius_lower_bound_km": EARTH_RADIUS_KM_LOWER_BOUND,
                    },
                ).data()
                assert len(records) == len(pairs)
                for record in records:
                    results[record["case_id"]] = record

            assert len(results) == len(cases)

            for case_id, lat1, lon1, lat2, lon2, radius in cases:
                record = results[case_id]
                kept = bool(record["kept"])
                distance_km = float(record["dist_meters"]) / 1000.0
                expected = pair_passes_prefilter(lat1, lon1, lat2, lon2, radius)

                if distance_km <= radius:
                    assert kept is True, (
                        f"real within-radius pair rejected: {case_id} "
                        f"distance_km={distance_km} radius={radius}"
                    )
                assert kept == expected, (
                    f"Cypher/Python prefilter mismatch: {case_id} "
                    f"kept={kept} expected={expected}"
                )

            after = _graph_state(session)
            assert after == before, "read-only gate mutated the graph"
    finally:
        driver.close()
