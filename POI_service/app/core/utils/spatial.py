"""Conservative spherical prefilter and reference spatial math for NEAR_BY.

This module is deliberately free of database, network and I/O dependencies so
that it is the single, unit-testable source of truth for the conservative
radius prefilter used by ``MemgraphPOIRepository``.

The prefilter is only a *necessary* condition for "within radius". Every value
here is derived from a lower-bound Earth radius (:data:`EARTH_RADIUS_KM_LOWER_BOUND`
= 6300 km), which makes all angular bounds strictly looser than the exact
spherical geometry. The authoritative test remains the graph engine's
``point.distance`` (great-circle, mean radius ~6371 km) applied after the
prefilter. No asymptotic performance claim is made: the prefilter is still
``O(n^2)`` unless the coordinates are actually indexed.
"""

from __future__ import annotations

import math

#: Mean Earth radius used by the exact reference Haversine (matches the sphere
#: used by ``point.distance``). Kept for reference/benchmark comparisons only.
EARTH_RADIUS_KM_MEAN = 6371.0

#: Lower-bound spherical radius. The brief fixes this at 6300 km so that the
#: derived angular bounds can never exclude a true neighbour.
EARTH_RADIUS_KM_LOWER_BOUND = 6300.0

#: Shared global radius for every NEAR_BY rebuild in a rebuild scope. A spatial
#: rebuild replaces the incident edges of the districts it is given, so the
#: *same* radius must be used for all affected districts. Rebuilding one district
#: at a different radius while leaving a neighbour at this one would silently
#: flip the shared cross-district edges; that is a scope-consistency
#: requirement documented in ``docs/decisions/010-graph-lifecycle.md``.
NEARBY_RADIUS_KM_DEFAULT = 3.0

#: Angular values are capped at 180 degrees (full sphere).
MAX_ANGLE_DEG = 180.0


def validate_radius_km(radius_km: float) -> float:
    """Return ``radius_km`` as a finite, strictly positive float.

    Rejects non-numeric, non-finite (``NaN``/``+-inf``) and non-positive
    radii with :class:`ValueError` so that no downstream spherical math is
    attempted with an invalid radius.
    """

    try:
        value = float(radius_km)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise ValueError(
            f"radius_km must be a finite number > 0, got {radius_km!r}"
        ) from exc
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"radius_km must be finite and > 0, got {radius_km!r}")
    return value


def latitude_delta_bound_degrees(radius_km: float) -> float:
    """Conservative half-width of the latitude band, in degrees.

    ``delta_lat = degrees(radius / 6300)`` capped at 180. This is an upper
    bound on ``|lat_a - lat_b|`` for any true pair within ``radius_km`` because
    the meridional arc is never longer than the great-circle distance and the
    lower-bound radius makes the conversion larger than reality.
    """

    radius_km = validate_radius_km(radius_km)
    return min(MAX_ANGLE_DEG, math.degrees(radius_km / EARTH_RADIUS_KM_LOWER_BOUND))


def longitude_delta_bound_degrees(lat_deg: float, radius_km: float) -> float:
    """Conservative longitude half-width for an anchor latitude, in degrees.

    Uses ``cos(max_abs_lat along the latitude band)``. The band reaches
    ``abs(lat) + delta_lat``; if that reaches a pole (>= 90 deg) the bound is
    widened to the full 180 deg. Otherwise the bound is
    ``min(180, delta_lat / cos(radians(abs(lat) + delta_lat)))``.
    """

    radius_km = validate_radius_km(radius_km)
    delta_lat = latitude_delta_bound_degrees(radius_km)
    band_max_abs_lat = abs(lat_deg) + delta_lat
    if band_max_abs_lat >= 90.0:
        return MAX_ANGLE_DEG
    cosine = math.cos(math.radians(band_max_abs_lat))
    if cosine <= 0.0:  # pragma: no cover - guarded by the >= 90 branch
        return MAX_ANGLE_DEG
    return min(MAX_ANGLE_DEG, delta_lat / cosine)


def wrapped_longitude_delta_degrees(lon_a: float, lon_b: float) -> float:
    """Shortest longitude separation in degrees, handling the dateline."""

    raw = abs(lon_a - lon_b)
    if raw > 180.0:
        return 360.0 - raw
    return raw


def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    radius_km: float = EARTH_RADIUS_KM_MEAN,
) -> float:
    """Exact reference great-circle distance, in kilometres.

    This is the *reference* used by the tests and benchmark, computed on a
    sphere of ``radius_km`` (default 6371 km). It is not executed against the
    graph database.
    """

    radius_km = float(radius_km)
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return radius_km * c


def pair_passes_prefilter(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    radius_km: float,
) -> bool:
    """Conservative, symmetric prefilter for one unordered pair.

    The latitude test uses :func:`latitude_delta_bound_degrees`. The longitude
    test uses the *union* of both per-anchor bands, which is equivalent to
    evaluating :func:`longitude_delta_bound_degrees` at both anchors and
    keeping the pair if either accepts it (the bound is monotonic in
    ``abs(lat)``, so the union collapses to the larger ``abs(lat)``). A pair
    that passes here may still be rejected by the authoritative distance test;
    a pair that fails here is guaranteed to be farther than ``radius_km``.
    """

    radius_km = validate_radius_km(radius_km)
    delta_lat = latitude_delta_bound_degrees(radius_km)
    if abs(lat1 - lat2) > delta_lat:
        return False

    max_abs_lat = max(abs(lat1), abs(lat2))
    band_max_abs_lat = max_abs_lat + delta_lat
    if band_max_abs_lat >= 90.0:
        delta_lon = MAX_ANGLE_DEG
    else:
        cosine = math.cos(math.radians(band_max_abs_lat))
        delta_lon = (
            MAX_ANGLE_DEG if cosine <= 0.0 else min(MAX_ANGLE_DEG, delta_lat / cosine)
        )
    return wrapped_longitude_delta_degrees(lon1, lon2) <= delta_lon


def conservative_prefilter_cypher(
    lat_a: str = "p1.latitude",
    lon_a: str = "p1.longitude",
    lat_b: str = "p2.latitude",
    lon_b: str = "p2.longitude",
    *,
    radius_param: str = "$radius_km",
    earth_radius_lower_bound_param: str = "$earth_radius_lower_bound_km",
) -> str:
    """Return a Cypher boolean expression that mirrors the Python prefilter.

    The returned fragment is a *conservative* necessary condition only. It
    replicates :func:`latitude_delta_bound_degrees` /
    :func:`longitude_delta_bound_degrees` / :func:`wrapped_longitude_delta_degrees`
    using ``cos``, ``abs``, ``pi()`` and the same 90/180 degree caps. It
    deliberately does **not** use an arbitrary ``111`` km/degree constant.

    Memgraph 3.13.2 (the verified engine) does not provide the ``degrees`` or
    ``radians`` functions. The exact arithmetic equivalents are emitted instead:
    ``degrees(x) == x * 180.0 / pi()`` and
    ``radians(x) == x * pi() / 180.0``. The Python reference functions keep
    using :func:`math.degrees` / :func:`math.radians`; only the generated
    Cypher is rewritten.

    This is pure string construction; the resulting expression is executed
    against a real engine by the dedicated runtime tests.
    """

    delta_lat_ratio = f"({radius_param} / {earth_radius_lower_bound_param})"
    delta_lat = (
        f"CASE WHEN {delta_lat_ratio} * 180.0 / pi() > 180.0 THEN 180.0 "
        f"ELSE {delta_lat_ratio} * 180.0 / pi() END"
    )
    max_abs_lat = (
        f"CASE WHEN abs({lat_a}) >= abs({lat_b}) "
        f"THEN abs({lat_a}) ELSE abs({lat_b}) END"
    )
    band_max_abs_lat = f"({max_abs_lat} + ({delta_lat}))"
    cosine = f"cos({band_max_abs_lat} * pi() / 180.0)"
    delta_lon = (
        f"CASE WHEN {band_max_abs_lat} >= 90.0 THEN 180.0 "
        f"WHEN ({delta_lat}) / {cosine} > 180.0 THEN 180.0 "
        f"ELSE ({delta_lat}) / {cosine} END"
    )
    wrapped_delta_lon = (
        f"CASE WHEN abs({lon_a} - {lon_b}) > 180.0 "
        f"THEN 360.0 - abs({lon_a} - {lon_b}) ELSE abs({lon_a} - {lon_b}) END"
    )
    return (
        f"(abs({lat_a} - {lat_b}) <= ({delta_lat}) "
        f"AND ({wrapped_delta_lon}) <= ({delta_lon}))"
    )


def canonical_endpoints(id_a: int, id_b: int) -> tuple[int, int]:
    """Order a pair's endpoints by internal id into a deterministic orientation.

    ``canonical_endpoints(x, y) == canonical_endpoints(y, x)`` so that a pair
    has exactly one canonical representation regardless of which endpoint was
    the anchor.
    """

    if id_a == id_b:
        raise ValueError("a pair must join two distinct nodes")
    return (id_a, id_b) if id_a < id_b else (id_b, id_a)


def select_canonical_pairs(
    anchor_ids: "set[int] | list[int]", all_ids: "set[int] | list[int]"
) -> set[tuple[int, int]]:
    """Pure model of the repository's anchored candidate-selection step.

    For every *anchor* node (a POI in the district being rebuilt), match every
    other node in the graph **in both orientations**, order each pair by
    internal id, and deduplicate. Anchoring is independent of which endpoint has
    the smaller internal id, so a pair that straddles two districts is selected
    by whichever district is being built, even when the sole anchor has a
    higher internal id.

    This deliberately mirrors the Cypher, which normalises endpoints with a
    ``CASE`` after matching both orientations and then applies
    ``WITH DISTINCT``.
    """

    anchors = set(anchor_ids)
    universe = set(all_ids)
    pairs: set[tuple[int, int]] = set()
    for anchor in anchors:
        for other in universe:
            if other == anchor:
                continue
            pairs.add(canonical_endpoints(anchor, other))
    return pairs
