"""Pure invariant tests for the OC-044 Memgraph-compatible prefilter.

The module under test is pure string construction plus Python reference math;
these tests do not connect to a database. The companion live test executes the
generated Cypher on the explicitly enabled owned Memgraph instance.
"""

from __future__ import annotations

from app.core.utils.spatial import (
    EARTH_RADIUS_KM_LOWER_BOUND,
    MAX_ANGLE_DEG,
    conservative_prefilter_cypher,
    haversine_km,
    latitude_delta_bound_degrees,
    longitude_delta_bound_degrees,
    pair_passes_prefilter,
)

from cases import RADII_KM, SEED, build_cases


def test_generated_cypher_avoids_unsupported_memgraph_functions():
    fragment = conservative_prefilter_cypher()
    assert "degrees(" not in fragment
    assert "radians(" not in fragment
    assert "pi()" in fragment
    assert "cos(" in fragment
    assert "abs(" in fragment
    assert "111" not in fragment


def test_generated_cypher_uses_exact_arithmetic_equivalents():
    fragment = conservative_prefilter_cypher()
    assert "($radius_km / $earth_radius_lower_bound_km) * 180.0 / pi()" in fragment
    assert "* pi() / 180.0" in fragment
    assert ">= 90.0" in fragment
    assert "> 180.0" in fragment
    assert "360.0 - abs(" in fragment


def test_python_reference_arithmetic_is_the_documented_conversion():
    for radius in RADII_KM:
        expected_lat = min(
            MAX_ANGLE_DEG,
            (radius / EARTH_RADIUS_KM_LOWER_BOUND) * 180.0 / 3.141592653589793,
        )
        assert latitude_delta_bound_degrees(radius) == expected_lat


def test_case_suite_covers_every_radius_and_all_regions():
    cases = build_cases()
    assert {case[5] for case in cases} == set(RADII_KM)
    ids = {case[0] for case in cases}
    for token in (
        "hcm_ordinary",
        "high_latitude",
        "north_pole",
        "south_pole",
        "dateline",
        "antipodal",
        "inside",
        "just_outside",
        "far",
        "random_",
    ):
        assert any(token in case_id for case_id in ids)
    assert len(cases) >= 1000


def test_case_suite_has_zero_false_negatives_against_haversine():
    cases = build_cases()
    checked_within = 0
    for case_id, lat1, lon1, lat2, lon2, radius in cases:
        distance_km = haversine_km(lat1, lon1, lat2, lon2)
        if distance_km <= radius:
            checked_within += 1
            assert pair_passes_prefilter(lat1, lon1, lat2, lon2, radius) is True, case_id
    assert checked_within > 0


def test_case_suite_exercises_rejections_and_conservative_accepts():
    cases = build_cases()
    kept = 0
    rejected = 0
    conservative_accepts = 0
    for _case_id, lat1, lon1, lat2, lon2, radius in cases:
        distance_km = haversine_km(lat1, lon1, lat2, lon2)
        passes = pair_passes_prefilter(lat1, lon1, lat2, lon2, radius)
        kept += int(passes)
        rejected += int(not passes)
        conservative_accepts += int(passes and distance_km > radius)
    assert kept > 0
    assert rejected > 0
    assert conservative_accepts > 0


def test_known_geometry_invariants():
    assert pair_passes_prefilter(10.7769, 106.7009, 10.7772, 106.7011, 3.0) is True
    assert pair_passes_prefilter(0.0, 179.99, 0.0, -179.99, 3.0) is True
    assert pair_passes_prefilter(0.0, 0.0, 0.0, 180.0, 5.0) is False
    assert pair_passes_prefilter(0.0, 0.0, 0.0, 1.0, 1.0) is False
    assert pair_passes_prefilter(-89.999, 0.0, -89.999, 120.0, 5.0) is True
    assert longitude_delta_bound_degrees(89.99, 3.0) == MAX_ANGLE_DEG


def test_seed_and_case_count_are_stable():
    first = build_cases()
    second = build_cases()
    assert first == second
    assert SEED == 20261017
