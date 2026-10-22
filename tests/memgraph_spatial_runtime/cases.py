"""Deterministic spatial-prefilter cases shared by pure and live tests.

Each case is ``(case_id, lat_a, lon_a, lat_b, lon_b, radius_km)``. The suite
covers ordinary Ho Chi Minh City pairs, high latitudes, both poles, the
dateline, antipodal points, near-threshold distances and a bounded seeded
random adversarial sample. Radii are always 1, 3 and 5 km.
"""

from __future__ import annotations

import math
import random

EARTH_RADIUS_KM_MEAN = 6371.0
SEED = 20261017
RADII_KM = (1.0, 3.0, 5.0)


def _destination(
    lat: float,
    lon: float,
    bearing_deg: float,
    distance_km: float,
) -> tuple[float, float]:
    angular = distance_km / EARTH_RADIUS_KM_MEAN
    phi1 = math.radians(lat)
    lambda1 = math.radians(lon)
    theta = math.radians(bearing_deg)

    sin_phi2 = math.sin(phi1) * math.cos(angular) + math.cos(phi1) * math.sin(
        angular
    ) * math.cos(theta)
    sin_phi2 = max(-1.0, min(1.0, sin_phi2))
    phi2 = math.asin(sin_phi2)
    lambda2 = lambda1 + math.atan2(
        math.sin(theta) * math.sin(angular) * math.cos(phi1),
        math.cos(angular) - math.sin(phi1) * sin_phi2,
    )

    lat2 = math.degrees(phi2)
    lon2 = (math.degrees(lambda2) + 180.0) % 360.0 - 180.0
    return lat2, lon2


def _wrap_lon(lon: float) -> float:
    return (lon + 180.0) % 360.0 - 180.0


def _clamp_lat(lat: float) -> float:
    return max(-89.999, min(89.999, lat))


def build_cases(radii_km: tuple[float, ...] = RADII_KM) -> list[tuple]:
    cases: list[tuple] = []
    bearings = (0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0)
    anchors = (
        ("hcm", 10.7769, 106.7009),
        ("high_lat", 60.0, 10.0),
        ("near_pole", 80.0, 20.0),
        ("south_pole", -80.0, -20.0),
        ("dateline", 0.0, 179.999),
    )

    for radius in radii_km:
        tag = f"r{radius:g}"

        cases.extend(
            [
                (f"hcm_ordinary_1_{tag}", 10.7769, 106.7009, 10.7772, 106.7011, radius),
                (f"hcm_ordinary_2_{tag}", 10.7769, 106.7009, 10.7760, 106.7001, radius),
                (f"hcm_dateline_like_{tag}", 10.7769, 106.7009, 10.7769, 106.7060, radius),
                (f"high_latitude_{tag}", 60.0, 10.0, 60.0005, 10.0009, radius),
                (f"north_pole_{tag}", 89.999, 0.0, 89.999, 120.0, radius),
                (f"south_pole_{tag}", -89.999, 0.0, -89.999, -120.0, radius),
                (f"dateline_{tag}", 0.0, 179.999, 0.0, -179.999, radius),
                (f"dateline_high_lat_{tag}", 60.0, 179.999, 60.0, -179.999, radius),
                (f"antipodal_{tag}", 0.0, 0.0, 0.0, 180.0, radius),
                (f"antipodal_high_lat_{tag}", 45.0, 10.0, -45.0, -170.0, radius),
                (f"same_point_{tag}", 10.7769, 106.7009, 10.7769, 106.7009, radius),
            ]
        )

        for anchor_tag, anchor_lat, anchor_lon in anchors:
            for bearing in bearings:
                inside = _destination(anchor_lat, anchor_lon, bearing, radius * 0.95)
                cases.append(
                    (
                        f"{anchor_tag}_inside_{int(bearing)}_{tag}",
                        anchor_lat,
                        anchor_lon,
                        _clamp_lat(inside[0]),
                        _wrap_lon(inside[1]),
                        radius,
                    )
                )
                outside = _destination(anchor_lat, anchor_lon, bearing, radius * 1.02)
                cases.append(
                    (
                        f"{anchor_tag}_just_outside_{int(bearing)}_{tag}",
                        anchor_lat,
                        anchor_lon,
                        _clamp_lat(outside[0]),
                        _wrap_lon(outside[1]),
                        radius,
                    )
                )
                far = _destination(anchor_lat, anchor_lon, bearing, radius * 3.0)
                cases.append(
                    (
                        f"{anchor_tag}_far_{int(bearing)}_{tag}",
                        anchor_lat,
                        anchor_lon,
                        _clamp_lat(far[0]),
                        _wrap_lon(far[1]),
                        radius,
                    )
                )

        rng = random.Random(SEED + int(round(radius * 1000.0)))
        centers = (
            (10.7769, 106.7009),
            (10.8, 106.75),
            (60.0, 10.0),
            (80.0, 20.0),
            (-80.0, -20.0),
            (0.0, 179.99),
            (0.0, -179.99),
        )
        sigma_deg = radius / 111.0
        for index in range(240):
            center_lat, center_lon = rng.choice(centers)
            lat1 = _clamp_lat(center_lat + rng.gauss(0.0, sigma_deg))
            lon1 = _wrap_lon(center_lon + rng.gauss(0.0, sigma_deg))
            scale = 1.0 if index % 4 else 8.0
            lat2 = _clamp_lat(lat1 + rng.gauss(0.0, sigma_deg * scale))
            lon2 = _wrap_lon(lon1 + rng.gauss(0.0, sigma_deg * scale))
            cases.append((f"random_{index}_{tag}", lat1, lon1, lat2, lon2, radius))

    return cases
