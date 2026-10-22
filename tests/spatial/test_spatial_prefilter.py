"""Focused tests for the OC-003 conservative spatial prefilter.

Scope: only the pure ``app.core.utils.spatial`` module is imported. No database
connector, no graph server and no network call is used. The graph query string
is only *constructed and inspected*; it is never executed here, so nothing in
this file is a database-integration claim.
"""

import itertools
import math
import random
from pathlib import Path

import pytest

from app.core.utils.spatial import (
    EARTH_RADIUS_KM_LOWER_BOUND,
    EARTH_RADIUS_KM_MEAN,
    MAX_ANGLE_DEG,
    canonical_endpoints,
    conservative_prefilter_cypher,
    haversine_km,
    latitude_delta_bound_degrees,
    longitude_delta_bound_degrees,
    pair_passes_prefilter,
    select_canonical_pairs,
    validate_radius_km,
    wrapped_longitude_delta_degrees,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MEMGRAPH_REPO = (
    REPO_ROOT
    / "POI_service"
    / "app"
    / "core"
    / "infrastructure"
    / "db"
    / "repositories"
    / "memgraph.py"
)


# ---------------------------------------------------------------------------
# Radius validation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bad_radius,label",
    [
        (0.0, "zero"),
        (-1.0, "negative"),
        (-0.0001, "tiny_negative"),
        (float("nan"), "nan"),
        (float("inf"), "pos_inf"),
        (float("-inf"), "neg_inf"),
    ],
)
def test_reject_nonfinite_and_nonpositive_radius(bad_radius, label):
    with pytest.raises(ValueError):
        validate_radius_km(bad_radius)
    with pytest.raises(ValueError):
        latitude_delta_bound_degrees(bad_radius)
    with pytest.raises(ValueError):
        longitude_delta_bound_degrees(10.0, bad_radius)
    with pytest.raises(ValueError):
        pair_passes_prefilter(0.0, 0.0, 0.0, 0.001, bad_radius)


def test_positive_radius_is_returned_unchanged():
    assert validate_radius_km(3) == 3.0
    assert validate_radius_km(1.0) == 1.0


# ---------------------------------------------------------------------------
# Reference Haversine
# ---------------------------------------------------------------------------
def test_reference_haversine_known_values():
    assert haversine_km(0.0, 0.0, 0.0, 0.0) == 0.0
    # One degree of latitude at the equator.
    assert haversine_km(0.0, 0.0, 1.0, 0.0) == pytest.approx(
        math.radians(1.0) * EARTH_RADIUS_KM_MEAN, rel=1e-12
    )
    # A quarter and half of the great circle.
    assert haversine_km(0.0, 0.0, 0.0, 90.0) == pytest.approx(
        math.pi / 2.0 * EARTH_RADIUS_KM_MEAN, rel=1e-12
    )
    assert haversine_km(0.0, 0.0, 0.0, 180.0) == pytest.approx(
        math.pi * EARTH_RADIUS_KM_MEAN, rel=1e-12
    )


def test_reference_haversine_is_symmetric():
    for _ in range(200):
        lat1 = random.uniform(-89.0, 89.0)
        lon1 = random.uniform(-180.0, 180.0)
        lat2 = random.uniform(-89.0, 89.0)
        lon2 = random.uniform(-180.0, 180.0)
        assert haversine_km(lat1, lon1, lat2, lon2) == pytest.approx(
            haversine_km(lat2, lon2, lat1, lon1), rel=1e-12, abs=1e-9
        )


# ---------------------------------------------------------------------------
# Angular bounds
# ---------------------------------------------------------------------------
def test_latitude_bound_matches_degrees_of_lower_bound_radius():
    assert latitude_delta_bound_degrees(1.0) == pytest.approx(
        math.degrees(1.0 / EARTH_RADIUS_KM_LOWER_BOUND), rel=1e-12
    )
    assert latitude_delta_bound_degrees(3.0) == pytest.approx(
        math.degrees(3.0 / EARTH_RADIUS_KM_LOWER_BOUND), rel=1e-12
    )
    assert latitude_delta_bound_degrees(5.0) == pytest.approx(
        math.degrees(5.0 / EARTH_RADIUS_KM_LOWER_BOUND), rel=1e-12
    )


def test_latitude_bound_is_capped_at_180():
    assert latitude_delta_bound_degrees(EARTH_RADIUS_KM_LOWER_BOUND * math.pi) == (
        MAX_ANGLE_DEG
    )
    assert latitude_delta_bound_degrees(1.0e9) == MAX_ANGLE_DEG


def test_longitude_bound_equator_equals_latitude_bound():
    delta_lat = latitude_delta_bound_degrees(3.0)
    # At the equator cos(lat + delta_lat) is marginally below 1, so the
    # longitude bound is a hair larger than delta_lat (expected, conservative).
    assert longitude_delta_bound_degrees(0.0, 3.0) == pytest.approx(delta_lat, rel=1e-6)


def test_longitude_bound_grows_toward_higher_latitude():
    equator = longitude_delta_bound_degrees(0.0, 3.0)
    mid = longitude_delta_bound_degrees(60.0, 3.0)
    high = longitude_delta_bound_degrees(80.0, 3.0)
    assert equator < mid < high
    expected_60 = latitude_delta_bound_degrees(3.0) / math.cos(math.radians(60.0272813))
    assert mid == pytest.approx(expected_60, rel=1e-3)


def test_longitude_bound_is_full_when_band_includes_pole():
    assert longitude_delta_bound_degrees(89.99, 3.0) == MAX_ANGLE_DEG
    assert longitude_delta_bound_degrees(90.0, 3.0) == MAX_ANGLE_DEG
    assert longitude_delta_bound_degrees(-89.995, 5.0) == MAX_ANGLE_DEG


# ---------------------------------------------------------------------------
# Dateline handling
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "lon_a,lon_b,expected",
    [
        (179.9, -179.9, 0.2),
        (-179.9, 179.9, 0.2),
        (180.0, -180.0, 0.0),
        (10.0, -10.0, 20.0),
        (0.0, 0.0, 0.0),
    ],
)
def test_wrapped_longitude_delta_handles_dateline(lon_a, lon_b, expected):
    assert wrapped_longitude_delta_degrees(lon_a, lon_b) == pytest.approx(expected)


def test_prefilter_accepts_pair_across_dateline():
    # Two points either side of the dateline, ~2 km apart at the equator.
    assert pair_passes_prefilter(0.0, 179.99, 0.0, -179.99, 3.0) is True
    assert haversine_km(0.0, 179.99, 0.0, -179.99) < 3.0


# ---------------------------------------------------------------------------
# Symmetry and conservative boundaries
# ---------------------------------------------------------------------------
def test_prefilter_is_symmetric_on_random_pairs():
    rng = random.Random(20261015)
    for _ in range(500):
        a = (rng.uniform(-89.0, 89.0), rng.uniform(-180.0, 180.0))
        b = (rng.uniform(-89.0, 89.0), rng.uniform(-180.0, 180.0))
        for radius in (1.0, 3.0, 5.0):
            assert pair_passes_prefilter(*a, *b, radius) == pair_passes_prefilter(
                *b, *a, radius
            )


def test_prefilter_keeps_just_inside_and_is_conservative_just_outside():
    # At latitude 60 one degree of longitude is ~cos(60) * 111.195 km.
    inside_lon = 0.0539
    outside_lon = 0.0541
    inside_km = haversine_km(60.0, 0.0, 60.0, inside_lon)
    outside_km = haversine_km(60.0, 0.0, 60.0, outside_lon)

    assert inside_km <= 3.0 < outside_km
    # The prefilter must never reject a true neighbour.
    assert pair_passes_prefilter(60.0, 0.0, 60.0, inside_lon, 3.0) is True
    # It is conservative, so it may keep the just-outside point; that is fine,
    # the authoritative distance test rejects it.
    assert pair_passes_prefilter(60.0, 0.0, 60.0, outside_lon, 3.0) is True


# ---------------------------------------------------------------------------
# Explicit regression: latitude 60, longitude delta 0.04 deg
# ---------------------------------------------------------------------------
def test_regression_latitude_60_longitude_delta_004_deg_is_kept():
    """A <3 km neighbour that the old invalid 111 km/degree filter excluded.

    ``abs(lon1 - lon2) <= radius / 111`` gives ``<= 0.0270`` degrees for 3 km,
    so the 0.04 degree pair was dropped even though it is only ~2.22 km away.
    The conservative prefilter must keep it.
    """

    delta_lon = 0.04
    distance_km = haversine_km(60.0, 0.0, 60.0, delta_lon)
    assert distance_km <= 3.0

    old_invalid_bound_deg = 3.0 / 111.0
    assert delta_lon > old_invalid_bound_deg  # documents the old defect

    assert pair_passes_prefilter(60.0, 0.0, 60.0, delta_lon, 3.0) is True


# ---------------------------------------------------------------------------
# Exhaustive comparison: zero false negatives
# ---------------------------------------------------------------------------
def _assert_no_false_negatives(points, radius_km):
    checked_true_pairs = 0
    for (lat1, lon1), (lat2, lon2) in itertools.combinations(points, 2):
        true_distance = haversine_km(lat1, lon1, lat2, lon2)
        if true_distance <= radius_km:
            checked_true_pairs += 1
            assert pair_passes_prefilter(lat1, lon1, lat2, lon2, radius_km) is True
    return checked_true_pairs


def test_randomized_global_pairs_have_zero_false_negatives():
    rng = random.Random(20261015)
    points = [
        (rng.uniform(-89.999, 89.999), rng.uniform(-180.0, 180.0))
        for _ in range(150)
    ]
    for radius in (1.0, 3.0, 5.0):
        _assert_no_false_negatives(points, radius)


def test_clustered_pairs_have_zero_false_negatives_and_real_neighbours():
    rng = random.Random(20261015)
    centers = [
        (10.7769, 106.7009),  # Ho Chi Minh City
        (60.0, 10.0),         # high latitude
        (0.0, 0.0),           # equator
        (0.0, 179.9),         # near dateline
        (80.0, 20.0),         # near pole
        (10.0, 106.8),
    ]
    points = []
    for _ in range(200):
        center_lat, center_lon = rng.choice(centers)
        lat = center_lat + rng.gauss(0.0, 0.05)
        lon = center_lon + rng.gauss(0.0, 0.05)
        if lon > 180.0:
            lon -= 360.0
        if lon < -180.0:
            lon += 360.0
        points.append((max(-89.999, min(89.999, lat)), lon))

    for radius in (1.0, 3.0, 5.0):
        true_pairs = _assert_no_false_negatives(points, radius)
        # The clustered fixture must actually contain true neighbours, otherwise
        # the zero-false-negative assertion above would be vacuous.
        assert true_pairs > 0


def test_extreme_latitudes_and_dateline_grid():
    points = []
    for lat in (89.999, 89.99, 89.9, -89.999, -89.99, -89.9, 0.0):
        for lon in (179.999, 179.99, -179.999, -179.99, 0.0):
            points.append((lat, lon))
    for radius in (1.0, 3.0, 5.0):
        _assert_no_false_negatives(points, radius)


# ---------------------------------------------------------------------------
# Cypher construction (construction only, never executed)
# ---------------------------------------------------------------------------
def test_cypher_prefilter_replicates_python_rule_structurally():
    fragment = conservative_prefilter_cypher()
    # Memgraph 3.13.2 has no ``degrees``/``radians``; use exact arithmetic.
    assert (
        "($radius_km / $earth_radius_lower_bound_km) * 180.0 / pi()" in fragment
    )
    assert "cos((" in fragment
    assert "* pi() / 180.0)" in fragment
    assert "degrees(" not in fragment
    assert "radians(" not in fragment
    assert ">= 90.0" in fragment
    assert "> 180.0" in fragment
    assert "360.0 - abs(" in fragment
    assert "abs(p1.latitude - p2.latitude)" in fragment
    # No arbitrary 111 km/degree constant and no performance shortcut.
    assert "111" not in fragment


def test_cypher_prefilter_accepts_custom_expressions_and_params():
    fragment = conservative_prefilter_cypher(
        lat_a="a.lat",
        lon_a="a.lon",
        lat_b="b.lat",
        lon_b="b.lon",
        radius_param="$r",
        earth_radius_lower_bound_param="$r0",
    )
    assert "a.lat" in fragment and "b.lon" in fragment
    assert "$r / $r0" in fragment


# ---------------------------------------------------------------------------
# Static inspection of the repository integration (no import, no execution)
# ---------------------------------------------------------------------------
def test_repository_integration_is_static_inspection_only():
    """Read the repository source and assert the shared prefilter is wired in.

    This is a static source inspection, not an executed database test.
    """

    source = MEMGRAPH_REPO.read_text(encoding="utf-8")
    assert "conservative_prefilter_cypher(" in source
    assert "validate_radius_km(radius_km)" in source
    assert "MERGE (a)-[r:NEAR_BY]-(b)" in source  # undirected storage
    assert "(p)-[nb:NEAR_BY]-(nearby:POI)" in source  # undirected retrieval
    assert "dist_meters / 1000.0" in source  # full precision stored
    assert "round((dist_meters" not in source  # rounded value not used
    # p2 is matched graph-wide, not restricted to the anchor district.
    assert "MATCH (p2:POI)" in source


def test_repository_query_normalises_endpoints_and_does_not_gate_on_anchor_id():
    """Source/query contract: both orientations matched, then normalised.

    Static inspection only; the Cypher is never executed here.
    """

    source = MEMGRAPH_REPO.read_text(encoding="utf-8")
    # The defective predicate must NOT gate matching.
    assert "AND id(p1) < id(p2)" not in source
    # Endpoints are normalised by internal id after matching both orientations.
    assert (
        "CASE WHEN id(p1) < id(p2) THEN p1 ELSE p2 END AS a" in source
    )
    assert (
        "CASE WHEN id(p1) < id(p2) THEN p2 ELSE p1 END AS b" in source
    )
    # Canonical pairs are deduplicated before distance/merge.
    assert "WITH DISTINCT a, b" in source
    # Undirected retrieval is preserved.
    assert "(p)-[nb:NEAR_BY]-(nearby:POI)" in source


# ---------------------------------------------------------------------------
# Functional anchored pair-selection regression (two districts, either ordering)
# ---------------------------------------------------------------------------
def test_canonical_endpoints_is_order_independent():
    assert canonical_endpoints(2, 5) == (2, 5)
    assert canonical_endpoints(5, 2) == (2, 5)
    assert canonical_endpoints(5, 2) == canonical_endpoints(2, 5)
    with pytest.raises(ValueError):
        canonical_endpoints(1, 1)


def test_building_district_with_only_higher_id_anchor_still_selects_cross_pair():
    """The sole anchor having a higher internal id must not drop the pair.

    Districts A = {10, 20} and B = {30, 40}. When only district B is rebuilt,
    anchors 30 and 40 have higher ids than their cross-district neighbours 20
    and 10. The old ``id(p1) < id(p2)`` gate dropped these; normalising after
    matching both orientations keeps them.
    """

    all_ids = [10, 20, 30, 40]
    district_b = [30, 40]

    selected = select_canonical_pairs(district_b, all_ids)

    assert canonical_endpoints(20, 30) in selected  # anchor 30 > neighbour 20
    assert canonical_endpoints(10, 40) in selected  # anchor 40 > neighbour 10

    # Document the old, defective predicate.
    def old_predicate(anchor, other):
        return anchor < other

    assert not old_predicate(30, 20)
    assert not old_predicate(40, 10)


def test_select_canonical_pairs_deduplicates_across_anchors():
    all_ids = [10, 20, 30, 40]
    district_a = [10, 20]
    district_b = [30, 40]

    selected_a = select_canonical_pairs(district_a, all_ids)
    expected_a = {
        canonical_endpoints(10, 20),
        canonical_endpoints(10, 30),
        canonical_endpoints(10, 40),
        canonical_endpoints(20, 30),
        canonical_endpoints(20, 40),
    }
    assert selected_a == expected_a
    assert all(low < high for low, high in selected_a)

    selected_b = select_canonical_pairs(district_b, all_ids)
    every_pair = {
        canonical_endpoints(a, b)
        for index, a in enumerate(all_ids)
        for b in all_ids[index + 1:]
    }
    # Union of both districts' builds covers every unordered pair exactly once.
    assert selected_a | selected_b == every_pair
    assert len(selected_a) == 5 and len(selected_b) == 5 and len(every_pair) == 6
