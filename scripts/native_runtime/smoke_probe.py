"""OC-041 read-only smoke probe for the isolated native Memgraph runtime.

Exit code 0 only if the real engine answers identity/RETURN 1, point.distance
with plausible WGS84 metre units, and reports zero nodes on the fresh owner.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

from neo4j import GraphDatabase

BOLT_URI = "bolt://127.0.0.1:17687"
WARSAW = (52.2297, 21.0122)
KRAKOW = (50.0647, 19.9450)
EXPECTED_MIN_M = 235_000.0
EXPECTED_MAX_M = 270_000.0


def _point(lat: float, lon: float) -> str:
    return f"point({{latitude: {lat}, longitude: {lon}}})"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", default=BOLT_URI)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    evidence: dict = {
        "run_id": "OC-041",
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "uri": args.uri,
        "checks": {},
        "server": {},
        "limits": [
            "Real-engine smoke only; not application Cypher, persistence, import, benchmark, MAGE, Docker or deployment acceptance.",
            "Read-only probes; no database writes or migrations.",
        ],
    }
    failures: list[str] = []

    driver = GraphDatabase.driver(args.uri, auth=None)
    try:
        info = driver.get_server_info()
        evidence["server"] = {
            "agent": getattr(info, "agent", None),
            "address": str(getattr(info, "address", "")),
            "protocol_version": getattr(info, "protocol_version", None),
        }
        with driver.session() as session:
            record = session.run("RETURN 1 AS one").single()
            value = record["one"] if record else None
            ok = value == 1
            evidence["checks"]["return_1"] = {"value": value, "ok": ok}
            if not ok:
                failures.append(f"RETURN 1 returned {value!r}")

            try:
                storage = session.run("SHOW STORAGE INFO").data()
                evidence["server"]["storage_info"] = storage
            except Exception as exc:  # noqa: BLE001 - diagnostic evidence only
                evidence["server"]["storage_info_error"] = f"{type(exc).__name__}: {exc}"

            distance_query = (
                f"RETURN point.distance({_point(*WARSAW)}, {_point(*KRAKOW)}) AS distance_m"
            )
            record = session.run(distance_query).single()
            distance_m = float(record["distance_m"]) if record else None
            within = (
                distance_m is not None
                and EXPECTED_MIN_M <= distance_m <= EXPECTED_MAX_M
            )
            evidence["checks"]["point_distance"] = {
                "from": {"latitude": WARSAW[0], "longitude": WARSAW[1]},
                "to": {"latitude": KRAKOW[0], "longitude": KRAKOW[1]},
                "distance_m": distance_m,
                "expected_range_m": [EXPECTED_MIN_M, EXPECTED_MAX_M],
                "units_assumed": "metres (WGS84 2D point.distance)",
                "ok": within,
            }
            if not within:
                failures.append(f"point.distance outside expected metres range: {distance_m!r}")

            record = session.run("MATCH (n) RETURN count(n) AS total_nodes").single()
            total_nodes = int(record["total_nodes"]) if record else None
            empty_ok = total_nodes == 0
            evidence["checks"]["fresh_owner_empty"] = {
                "total_nodes": total_nodes,
                "ok": empty_ok,
            }
            if not empty_ok:
                failures.append(f"expected total_nodes=0 on fresh owner, got {total_nodes!r}")
    finally:
        driver.close()

    evidence["ok"] = not failures
    evidence["failures"] = failures
    payload = json.dumps(evidence, indent=2)
    print(payload)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
