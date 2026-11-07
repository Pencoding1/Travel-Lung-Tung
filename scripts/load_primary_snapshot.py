"""Load the frozen graph-ready primary POI snapshot into Memgraph.

Verifies the SHA-256 checksum and record count of
``data/primary_20261016/graph_ready_v2/prepared_pois.jsonl`` against its
companion ``manifest.json``, validates all records against the domain ``POI``
schema, and ingests them in bounded transactions via ``MemgraphUnitOfWork``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
POI_SERVICE_ROOT = REPO_ROOT / "POI_service"
SHARED_LIB_ROOT = REPO_ROOT / "shared_lib"

for path_entry in reversed(
    (str(POI_SERVICE_ROOT), str(SHARED_LIB_ROOT), str(REPO_ROOT))
):
    if path_entry in sys.path:
        sys.path.remove(path_entry)
    sys.path.insert(0, path_entry)

_HAD_USER = "MEMGRAPH_USER" in os.environ
_HAD_PASS = "MEMGRAPH_PASSWORD" in os.environ
os.environ.setdefault("POI_DB_SETTINGS_SOURCE", "process_only")
os.environ.setdefault("MEMGRAPH_HOST", "127.0.0.1")
os.environ.setdefault("MEMGRAPH_PORT", "7687")
os.environ.setdefault("MEMGRAPH_USER", "")
os.environ.setdefault("MEMGRAPH_PASSWORD", "")

from app.core.config.settings import MemgraphDB  # noqa: E402
from app.core.domain.graph_entities import POI  # noqa: E402
from app.core.infrastructure.db.database.connector import MemgraphConnector  # noqa: E402
from app.core.infrastructure.db.uow import MemgraphUnitOfWork  # noqa: E402
from app.core.services.management import POIManagementService  # noqa: E402
from app.core.utils.spatial import NEARBY_RADIUS_KM_DEFAULT  # noqa: E402
from app.core.utils.updater import SpatialUpdater  # noqa: E402

if not _HAD_USER:
    os.environ.pop("MEMGRAPH_USER", None)
if not _HAD_PASS:
    os.environ.pop("MEMGRAPH_PASSWORD", None)

DEFAULT_SNAPSHOT_DIR = REPO_ROOT / "data" / "primary_20261016" / "graph_ready_v2"


def _build_memgraph_settings(host: str, port: int) -> MemgraphDB:
    """Build Memgraph settings from process env or root .env without exposing secrets."""
    root_env = REPO_ROOT / ".env"
    if root_env.is_file() and not (_HAD_USER and _HAD_PASS):
        return MemgraphDB(
            _env_file=str(root_env),
            MEMGRAPH_HOST=host,
            MEMGRAPH_PORT=port,
        )
    return MemgraphDB(
        _env_file=None,
        MEMGRAPH_HOST=host,
        MEMGRAPH_PORT=port,
        MEMGRAPH_USER=os.environ.get("MEMGRAPH_USER", ""),
        MEMGRAPH_PASSWORD=os.environ.get("MEMGRAPH_PASSWORD", ""),
    )


def load_and_verify_snapshot(snapshot_dir: Path) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Verify manifest integrity and validate all JSONL POI records."""
    manifest_path = snapshot_dir / "manifest.json"
    prepared_path = snapshot_dir / "prepared_pois.jsonl"

    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    if not prepared_path.is_file():
        raise FileNotFoundError(f"Prepared JSONL not found: {prepared_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_bytes = prepared_path.read_bytes()
    actual_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    expected_output = manifest.get("outputs", {}).get("prepared_pois.jsonl", {})
    expected_sha256 = expected_output.get("sha256")
    expected_records = expected_output.get("records")

    if expected_sha256 and actual_sha256 != expected_sha256:
        raise ValueError(
            f"SHA-256 mismatch for prepared_pois.jsonl: expected {expected_sha256}, got {actual_sha256}"
        )

    lines = [line for line in raw_bytes.decode("utf-8").splitlines() if line.strip()]
    if expected_records is not None and len(lines) != expected_records:
        raise ValueError(
            f"Record count mismatch: expected {expected_records}, got {len(lines)}"
        )

    validated_records: List[Dict[str, Any]] = []
    for idx, line in enumerate(lines):
        raw_obj = json.loads(line)
        poi = POI.model_validate(raw_obj)
        validated_records.append(poi.model_dump(mode="json"))

    return manifest, validated_records


async def ingest_snapshot(
    snapshot_dir: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 7687,
    chunk_size: int = 500,
    build_spatial: bool = True,
    spatial_batch_size: int = 200,
) -> Dict[str, Any]:
    """Load validated records into Memgraph and optionally rebuild NEAR_BY edges."""
    start_time = time.monotonic()
    manifest, records = load_and_verify_snapshot(snapshot_dir)

    settings = _build_memgraph_settings(host, port)
    connector = MemgraphConnector(settings)
    await connector.connect()

    uow_factory = lambda: MemgraphUnitOfWork(connector)
    accepted = 0

    try:
        for offset in range(0, len(records), chunk_size):
            chunk = records[offset : offset + chunk_size]
            with uow_factory() as uow:
                accepted += uow.pois.batch_create(chunk)

        spatial_summary: Dict[str, Any] = {"status": "skipped", "rebuilt_pois": 0}
        if build_spatial:
            all_ids = [r["id"] for r in records if isinstance(r.get("id"), str)]
            rebuilt = 0
            total_edges = 0
            for offset in range(0, len(all_ids), spatial_batch_size):
                batch_ids = all_ids[offset : offset + spatial_batch_size]
                with uow_factory() as uow:
                    edges = uow.pois._rebuild_nearby_edges(
                        "UNWIND $batch_ids AS pid MATCH (p1:POI {id: pid})",
                        {"batch_ids": batch_ids},
                        NEARBY_RADIUS_KM_DEFAULT,
                    )
                rebuilt += len(batch_ids)
                total_edges += int(edges or 0)
            spatial_summary = {
                "status": "success",
                "rebuilt_pois": rebuilt,
                "failed_pois": 0,
                "touched_edges": total_edges,
                "radius_km": NEARBY_RADIUS_KM_DEFAULT,
            }

        # Verify graph counts and catalog snapshots inside Memgraph
        mgmt_snapshots = POIManagementService(uow_factory()).list_source_snapshots()
        snapshots = mgmt_snapshots.get("snapshots", [])
        namespace = manifest.get("namespace", "hcm_primary_geojson")
        input_sha256 = (
            manifest.get("inputs", {}).get("geojson", {}).get("sha256", "")
        )
        areas: List[Dict[str, Any]] = []
        if input_sha256:
            mgmt_areas = POIManagementService(uow_factory()).list_source_areas(
                {"dataset_namespace": namespace, "input_sha256": input_sha256}
            )
            areas = mgmt_areas.get("source_areas", [])
    finally:
        connector.close()

    elapsed = round(time.monotonic() - start_time, 2)
    return {
        "status": "ok",
        "namespace": manifest.get("namespace"),
        "total_records": len(records),
        "accepted_records": accepted,
        "spatial": spatial_summary,
        "snapshots_in_graph": len(snapshots),
        "source_areas_in_graph": len(areas),
        "elapsed_seconds": elapsed,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Load data/primary_20261016/graph_ready_v2/prepared_pois.jsonl into Memgraph."
    )
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=DEFAULT_SNAPSHOT_DIR,
        help="Path to graph_ready_v2 directory.",
    )
    parser.add_argument("--host", default=os.environ.get("MEMGRAPH_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("MEMGRAPH_PORT", "7687"))
    )
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument(
        "--skip-spatial",
        action="store_true",
        help="Skip NEAR_BY spatial edge rebuild after node upsert.",
    )
    args = parser.parse_args(argv)

    summary = asyncio.run(
        ingest_snapshot(
            args.snapshot_dir,
            host=args.host,
            port=args.port,
            chunk_size=args.chunk_size,
            build_spatial=not args.skip_spatial,
        )
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary.get("accepted_records") == summary.get("total_records") else 1


if __name__ == "__main__":
    raise SystemExit(main())
