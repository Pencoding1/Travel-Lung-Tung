"""Isolated spatial filtering benchmark for the OC-003 conservative prefilter.

This benchmark is fully deterministic and uses only *synthetic* coordinates. It
does not read any graph, does not connect to Memgraph and does not use the
original thesis POIs. Nothing here is a runtime database measurement.

For each (n, radius) it compares:

- the exhaustive baseline: compute the exact Haversine distance for every
  unordered pair and accept those within the radius; and
- the optimized path: apply the conservative prefilter first, then compute the
  exact Haversine distance only on the surviving candidate pairs.

The two accepted sets must be identical (zero false negatives).

Run:

    .venv-validation\\Scripts\\python.exe benchmarks/spatial/benchmark.py
"""

from __future__ import annotations

import itertools
import json
import math
import os
import platform
import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SYS_PATH_ROOT = REPO_ROOT / "POI_service"
if str(SYS_PATH_ROOT) not in sys.path:
    sys.path.insert(0, str(SYS_PATH_ROOT))

from app.core.utils.spatial import (  # noqa: E402  (path bootstrap above)
    EARTH_RADIUS_KM_LOWER_BOUND,
    EARTH_RADIUS_KM_MEAN,
    haversine_km,
    pair_passes_prefilter,
)

SEED = 20261015
SIZES = (200, 1000)
RADII_KM = (1.0, 3.0, 5.0)
OUTPUT_JSON = Path(__file__).resolve().parent / "benchmark_results.json"

# Cluster centres only shape the *synthetic* fixture (a few latitudes and a
# dateline cluster so the prefilter is exercised). No real POI data is used.
CLUSTER_CENTERS = (
    (10.7769, 106.7009),
    (60.0, 10.0),
    (0.0, 0.0),
    (0.0, 179.9),
    (80.0, 20.0),
    (10.0, 106.8),
)


def make_synthetic_points(n: int, rng: random.Random) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for _ in range(n):
        center_lat, center_lon = rng.choice(CLUSTER_CENTERS)
        lat = center_lat + rng.gauss(0.0, 0.05)
        lon = center_lon + rng.gauss(0.0, 0.05)
        if lon > 180.0:
            lon -= 360.0
        if lon < -180.0:
            lon += 360.0
        points.append((max(-89.999, min(89.999, lat)), lon))
    return points


def exhaustive(points, radius_km):
    started = time.perf_counter()
    accepted = 0
    for (lat1, lon1), (lat2, lon2) in itertools.combinations(points, 2):
        if haversine_km(lat1, lon1, lat2, lon2) <= radius_km:
            accepted += 1
    elapsed = time.perf_counter() - started
    return accepted, elapsed


def optimized(points, radius_km):
    started = time.perf_counter()
    candidates = 0
    distance_computations = 0
    accepted = 0
    for (lat1, lon1), (lat2, lon2) in itertools.combinations(points, 2):
        if not pair_passes_prefilter(lat1, lon1, lat2, lon2, radius_km):
            continue
        candidates += 1
        distance_computations += 1
        if haversine_km(lat1, lon1, lat2, lon2) <= radius_km:
            accepted += 1
    elapsed = time.perf_counter() - started
    return {
        "candidate_pairs": candidates,
        "exact_distance_computations": distance_computations,
        "accepted_edges": accepted,
    }, elapsed


def machine_metadata() -> dict:
    try:
        load_avg = list(os.getloadavg())
    except (AttributeError, OSError):
        load_avg = None
    return {
        "python_version": sys.version,
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "node": platform.node(),
        "cpu_count_logical": os.cpu_count(),
        "load_average": load_avg,
        "earth_radius_km_mean": EARTH_RADIUS_KM_MEAN,
        "earth_radius_km_lower_bound": EARTH_RADIUS_KM_LOWER_BOUND,
    }


def run() -> dict:
    results = {
        "task": "OC-003",
        "data_source": "synthetic",
        "warning": (
            "All coordinates are synthetic (seed 20261015) and are NOT the "
            "original thesis POIs. Timings are single-run process measurements, "
            "not database runtime and not asymptotic claims. The candidate "
            "prefilter is still O(n^2) unless coordinates are indexed."
        ),
        "seed": SEED,
        "sizes": list(SIZES),
        "radii_km": list(RADII_KM),
        "cluster_centers": [list(c) for c in CLUSTER_CENTERS],
        "metadata": machine_metadata(),
        "measurements": [],
    }

    for n in SIZES:
        rng = random.Random(SEED)
        points = make_synthetic_points(n, rng)
        total_pairs = n * (n - 1) // 2
        for radius in RADII_KM:
            exhaustive_accepted, exhaustive_elapsed = exhaustive(points, radius)
            optimized_result, optimized_elapsed = optimized(points, radius)
            false_negatives = exhaustive_accepted - optimized_result["accepted_edges"]
            record = {
                "n": n,
                "radius_km": radius,
                "unordered_total_pairs": total_pairs,
                "candidate_pairs": optimized_result["candidate_pairs"],
                "exact_distance_computations": optimized_result[
                    "exact_distance_computations"
                ],
                "accepted_edges": optimized_result["accepted_edges"],
                "exhaustive_accepted_edges": exhaustive_accepted,
                "false_negatives": false_negatives,
                "candidate_ratio": (
                    optimized_result["candidate_pairs"] / total_pairs
                    if total_pairs
                    else 0.0
                ),
                "candidate_reduction_percent": (
                    100.0 * (1.0 - optimized_result["candidate_pairs"] / total_pairs)
                    if total_pairs
                    else 0.0
                ),
                "elapsed_optimized_seconds": optimized_elapsed,
                "elapsed_exhaustive_seconds": exhaustive_elapsed,
            }
            results["measurements"].append(record)
            if false_negatives != 0:
                raise AssertionError(
                    f"False negatives detected: n={n} radius={radius} "
                    f"exhaustive={exhaustive_accepted} "
                    f"optimized={optimized_result['accepted_edges']}"
                )

    return results


def main() -> int:
    results = run()
    OUTPUT_JSON.write_text(
        json.dumps(results, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )

    print(f"seed={results['seed']} data_source={results['data_source']}")
    header = (
        f"{'n':>5} {'radius_km':>9} {'total_pairs':>11} {'candidates':>10} "
        f"{'dist_calcs':>10} {'accepted':>8} {'false_neg':>9} "
        f"{'optimized_s':>11} {'exhaustive_s':>12}"
    )
    print(header)
    for record in results["measurements"]:
        print(
            f"{record['n']:>5} {record['radius_km']:>9.1f} "
            f"{record['unordered_total_pairs']:>11} "
            f"{record['candidate_pairs']:>10} "
            f"{record['exact_distance_computations']:>10} "
            f"{record['accepted_edges']:>8} "
            f"{record['false_negatives']:>9} "
            f"{record['elapsed_optimized_seconds']:>11.4f} "
            f"{record['elapsed_exhaustive_seconds']:>12.4f}"
        )
    print(f"raw results: {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
