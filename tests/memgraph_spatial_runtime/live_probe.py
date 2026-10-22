"""Read-only evidence probe for the OC-044 spatial prefilter correction.

Runs the generated prefilter on the explicitly enabled owned native Memgraph
instance and writes a JSON record with counts, query text, code hashes and
mismatch samples. The query contains only ``UNWIND``/``RETURN`` and
``point.distance``; it never writes to the graph.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path

from neo4j import GraphDatabase

from app.core.utils.spatial import (
    EARTH_RADIUS_KM_LOWER_BOUND,
    conservative_prefilter_cypher,
    pair_passes_prefilter,
)

from cases import RADII_KM, SEED, build_cases

EXPECTED_URI = "bolt://127.0.0.1:17687"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:  # noqa: BLE001 - evidence fallback only
        return "unavailable"


def _query() -> str:
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


def _state(session) -> dict:
    record = session.run(
        "MATCH (n) WITH count(n) AS nodes "
        "OPTIONAL MATCH ()-[r]->() RETURN nodes, count(r) AS relationships"
    ).single()
    return {"nodes": int(record["nodes"]), "relationships": int(record["relationships"])}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", default=EXPECTED_URI)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.uri != EXPECTED_URI:
        raise SystemExit(f"refusing non-owned URI {args.uri!r}")

    cases = build_cases()
    query = _query()
    evidence: dict = {
        "run_id": "OC-044",
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "uri": args.uri,
        "seed": SEED,
        "radii_km": list(RADII_KM),
        "case_count": len(cases),
        "units": {
            "point.distance": "metres (WGS84 2D spherical, mean radius ~6371 km)",
            "radius_comparison": "radius_km * 1000.0 metres",
            "earth_radius_lower_bound_km": EARTH_RADIUS_KM_LOWER_BOUND,
        },
        "code": {
            "git_head": _git_head(),
            "spatial_py_sha256": _sha256(
                REPO_ROOT / "POI_service/app/core/utils/spatial.py"
            ),
            "cases_py_sha256": _sha256(Path(__file__).with_name("cases.py")),
        },
        "query": query,
    }

    within_radius = 0
    false_negatives: list[dict] = []
    false_positives = 0
    reference_mismatches: list[dict] = []
    kept_total = 0
    rejected_total = 0

    driver = GraphDatabase.driver(args.uri, auth=None)
    try:
        with driver.session() as session:
            info = driver.get_server_info()
            evidence["engine"] = {
                "agent": getattr(info, "agent", None),
                "protocol_version": getattr(info, "protocol_version", None),
            }
            evidence["graph_before"] = _state(session)

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
                if len(records) != len(pairs):
                    raise SystemExit(
                        f"expected {len(pairs)} rows for radius {radius}, got {len(records)}"
                    )
                for record in records:
                    results[record["case_id"]] = record

            for case_id, lat1, lon1, lat2, lon2, radius in cases:
                record = results[case_id]
                kept = bool(record["kept"])
                distance_km = float(record["dist_meters"]) / 1000.0
                expected = pair_passes_prefilter(lat1, lon1, lat2, lon2, radius)

                kept_total += int(kept)
                rejected_total += int(not kept)
                if distance_km <= radius:
                    within_radius += 1
                    if not kept:
                        false_negatives.append(
                            {
                                "case_id": case_id,
                                "distance_km": distance_km,
                                "radius_km": radius,
                            }
                        )
                elif kept:
                    false_positives += 1

                if kept != expected and len(reference_mismatches) < 20:
                    reference_mismatches.append(
                        {
                            "case_id": case_id,
                            "cypher": kept,
                            "python": expected,
                            "distance_km": distance_km,
                            "radius_km": radius,
                        }
                    )

            evidence["graph_after"] = _state(session)
    finally:
        driver.close()

    evidence.update(
        {
            "within_radius_cases": within_radius,
            "kept_total": kept_total,
            "rejected_total": rejected_total,
            "false_negatives": false_negatives,
            "false_negative_count": len(false_negatives),
            "false_positives": false_positives,
            "reference_mismatch_count": len(reference_mismatches),
            "reference_mismatch_samples": reference_mismatches,
            "ok": not false_negatives and not reference_mismatches,
            "limits": [
                "Read-only expression evaluation on an empty owned instance; no NEAR_BY writes, import, durability, benchmark or deployment acceptance.",
                "Conservative false positives are expected and are authoritative-rejected by point.distance in the repository query.",
            ],
        }
    )

    payload = json.dumps(evidence, indent=2)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
