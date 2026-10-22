"""Pure reference model of the district rebuild replacement.

The repository replaces the edges incident to a district's anchors, so these
tests compute the expected pair set directly from coordinates and compare
scenarios (moved POI, removed POI, radius shrink, cross-district higher anchor).
This is reference/model evidence, not graph execution.
"""

from app.core.utils.spatial import (
    canonical_endpoints,
    haversine_km,
    select_canonical_pairs,
)


def replacement_pairs(anchors, coords, radius_km):
    """Pairs the rebuild would materialise for ``anchors`` at ``radius_km``."""
    pairs = set()
    for a in anchors:
        if a not in coords:
            continue
        for b, b_coord in coords.items():
            if b == a:
                continue
            if haversine_km(*coords[a], *b_coord) <= radius_km:
                pairs.add(canonical_endpoints(a, b))
    return pairs


BASE_COORDS = {
    1: (10.0, 106.0),
    2: (10.0, 106.02),
    3: (10.0, 106.04),
}


def test_moved_poi_drops_old_pairs_and_keeps_untouched_pairs():
    old = replacement_pairs({1, 2, 3}, BASE_COORDS, 3.0)
    assert (1, 2) in old and (2, 3) in old
    assert (1, 3) not in old  # ~4.38 km away

    moved = dict(BASE_COORDS)
    moved[1] = (10.0, 107.0)  # moved far away
    new = replacement_pairs({1, 2, 3}, moved, 3.0)

    assert (1, 2) not in new
    assert (1, 3) not in new
    assert (2, 3) in new  # unrelated pair preserved


def test_removed_poi_contributes_no_pairs():
    coords = {k: v for k, v in BASE_COORDS.items() if k != 2}
    pairs = replacement_pairs({1, 3}, coords, 3.0)

    assert all(2 not in pair for pair in pairs)
    assert pairs == set()  # 1 and 3 are ~4.38 km apart


def test_radius_shrink_reduces_pairs():
    wide = replacement_pairs({1, 2, 3}, BASE_COORDS, 3.0)
    narrow = replacement_pairs({1, 2, 3}, BASE_COORDS, 1.0)

    assert narrow <= wide
    assert narrow == set()  # every pair is > 1 km apart
    assert (1, 2) in wide


def test_cross_district_higher_id_anchor_is_still_selected():
    # Districts A = {10, 20}, B = {30, 40}; rebuild only B whose ids are higher.
    selected = select_canonical_pairs([30, 40], [10, 20, 30, 40])

    assert canonical_endpoints(20, 30) in selected
    assert canonical_endpoints(10, 40) in selected
