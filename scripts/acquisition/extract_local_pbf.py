"""Bounded, read-only extraction of real OSM NODE samples from a local PBF.

This is a research sampling tool, not a coverage claim. It streams an existing
``.osm.pbf`` (never modifying it), selects a small deterministic subset of
named point features inside an explicit bounding box, and writes:

* ``osm_local_sample.json`` — an Overpass-shaped JSON export (``elements``)
  consumable by ``crawler_service.app.acquisition.adapters.osm``. The parent PBF
  SHA-256 and derivation semantics are embedded explicitly; no download URL or
  acquisition time is invented.
* ``osm_local_provenance.json`` — header/derivation evidence for the export.
* ``osm_local_commands.log`` — the exact command line and key run facts.

Only ``osmium`` (pyosmium) is used beyond the standard library. Extraction is
read-only and deterministic (ascending numeric OSM id).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_PBF = "graphhopper/data/hcmc-latest.osm.pbf"
DEFAULT_OUT_DIR = "data/expansion_20261015/osm_local"
DEFAULT_BBOX = "10.77,106.68,10.79,106.70"
DEFAULT_MAX_FEATURES = 30

# Named point-feature selectors for this bounded sample. Only NODES are read;
# ways/relations are ignored so that way/relation "centers" (unconfirmed venue
# entrances) are never approximated as points.
TOURISM_VALUES = {"museum", "attraction"}
AMENITY_VALUES = {"cafe", "restaurant"}


def parse_bbox(text: str) -> Dict[str, float]:
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox must be 'minlat,minlon,maxlat,maxlon'")
    try:
        minlat, minlon, maxlat, maxlon = (float(p) for p in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"bbox values must be numbers: {exc}") from exc
    if minlat > maxlat or minlon > maxlon:
        raise argparse.ArgumentTypeError("bbox minimums must not exceed maximums")
    return {"minlat": minlat, "minlon": minlon, "maxlat": maxlat, "maxlon": maxlon}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp_to_iso(value: Any) -> Any:
    if not value:
        return None
    try:
        seconds = value.seconds
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    except Exception:  # pragma: no cover - defensive
        text = str(value).strip()
        return text or None


def _match(tags: Any) -> bool:
    tourism = tags.get("tourism")
    amenity = tags.get("amenity")
    if tourism in TOURISM_VALUES:
        return True
    if amenity in AMENITY_VALUES:
        return True
    return False


def extract(pbf: Path, bbox: Dict[str, float], max_features: int) -> Dict[str, Any]:
    try:
        import osmium
    except ImportError as exc:  # pragma: no cover - reported as blocked
        raise SystemExit(
            "osmium (pyosmium) is required; install it with "
            "'.venv-acquisition-validation/Scripts/python.exe -m pip install osmium'"
        ) from exc

    reader = osmium.io.Reader(str(pbf))
    header = reader.header()
    header_evidence = {
        key: (header.get(key) or None)
        for key in (
            "generator",
            "writingprogram",
            "source",
            "osmosis_replication_timestamp",
            "osmosis_replication_sequence_number",
            "osmosis_replication_base_url",
        )
    }
    header_evidence["pbf_dense_nodes"] = header.get("pbf_dense_nodes") or None
    header_evidence["sorting"] = header.get("sorting") or None
    header_evidence["has_multiple_object_versions"] = bool(
        header.has_multiple_object_versions
    )

    state = {"total_matched": 0, "nodes": []}

    class Handler(osmium.SimpleHandler):
        def node(self, n: Any) -> None:
            if not (bbox["minlat"] <= n.location.lat <= bbox["maxlat"]):
                return
            if not (bbox["minlon"] <= n.location.lon <= bbox["maxlon"]):
                return
            tags = dict(n.tags)
            if not tags.get("name"):
                return
            if not _match(tags):
                return
            state["total_matched"] += 1
            state["nodes"].append(
                {
                    "type": "node",
                    "id": int(n.id),
                    "lat": n.location.lat,
                    "lon": n.location.lon,
                    "version": int(n.version) if n.version else None,
                    "timestamp": _timestamp_to_iso(n.timestamp),
                    "changeset": int(n.changeset) if n.changeset else None,
                    "uid": int(n.uid) if n.uid else None,
                    "user": n.user or None,
                    "tags": tags,
                }
            )

    Handler().apply_file(str(pbf), locations=False)

    state["nodes"].sort(key=lambda node: node["id"])
    exported = state["nodes"][:max_features]
    return {
        "elements": exported,
        "total_matched": state["total_matched"],
        "exported": len(exported),
        "truncated": state["total_matched"] > len(exported),
        "header_evidence": header_evidence,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="extract_local_pbf.py",
        description=(
            "Read-only bounded extraction of real named OSM NODE point features "
            "from a local .osm.pbf into an Overpass-shaped JSON sample. Research "
            "sample only; not a coverage claim."
        ),
    )
    parser.add_argument("--pbf", default=DEFAULT_PBF, help="Path to a local .osm.pbf (read-only).")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="Output directory.")
    parser.add_argument(
        "--bbox",
        default=DEFAULT_BBOX,
        type=parse_bbox,
        help="Bounding box 'minlat,minlon,maxlat,maxlon'.",
    )
    parser.add_argument(
        "--max-features",
        type=int,
        default=DEFAULT_MAX_FEATURES,
        help="Maximum number of NODE features to export (research sample cap).",
    )
    parser.add_argument(
        "--derived-at",
        default=None,
        help="Explicit UTC ISO-8601 timestamp for the derivation event; default now.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow overwriting existing outputs with different bytes.",
    )
    args = parser.parse_args(argv)

    pbf = Path(args.pbf)
    if not pbf.is_file():
        sys.stderr.write(f"error: PBF not found: {pbf}\n")
        return 2
    out_dir = Path(args.out_dir)

    pbf_sha256 = sha256_file(pbf)
    pbf_bytes = pbf.stat().st_size
    derived_at = args.derived_at or to_utc_iso(datetime.now(timezone.utc))

    result = extract(pbf, args.bbox, args.max_features)
    header_evidence = result["header_evidence"]

    export = {
        "_comment": (
            "Real OSM NODE point features derived from a local PBF. Research "
            "sample only; not a coverage claim. District is NOT inferred from "
            "the bounding box. Only node geometry is used; ways/relations are "
            "excluded to avoid centroid approximation."
        ),
        "version": 0.6,
        "derived": {
            "derivation": "bounded_readonly_local_pbf_node_extraction",
            "parent_pbf_path": str(pbf),
            "parent_pbf_sha256": pbf_sha256,
            "parent_pbf_bytes": pbf_bytes,
            "derived_export_time_utc": derived_at,
            "bbox": args.bbox,
            "selectors": {
                "tourism": sorted(TOURISM_VALUES),
                "amenity": sorted(AMENITY_VALUES),
                "geometry": "node",
                "named_only": True,
                "max_features": args.max_features,
            },
            "total_matched_before_limit": result["total_matched"],
            "exported": result["exported"],
            "truncated": result["truncated"],
            "download_url": "UNKNOWN",
            "download_time": "UNKNOWN",
        },
        "elements": result["elements"],
    }

    provenance = {
        "dataset": "expansion_20261015",
        "export_file": "osm_local_sample.json",
        "parent_pbf_path": str(pbf),
        "parent_pbf_sha256": pbf_sha256,
        "parent_pbf_bytes": pbf_bytes,
        "derived_export_time_utc": derived_at,
        "derived_export_time_semantics": (
            "Timestamp of this derived extraction event. It is NOT the PBF "
            "download/acquisition time and is NOT the OSM data timestamp."
        ),
        "bbox": args.bbox,
        "selectors": {
            "tourism": sorted(TOURISM_VALUES),
            "amenity": sorted(AMENITY_VALUES),
            "geometry": "node",
            "named_only": True,
            "max_features": args.max_features,
        },
        "exported_count": result["exported"],
        "total_matched_before_limit": result["total_matched"],
        "truncated": result["truncated"],
        "license": "ODbL-1.0",
        "attribution": "OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright)",
        "origin": {
            "status": "header_evidence_only",
            "generator_header": header_evidence.get("generator"),
            "osmosis_replication_timestamp": header_evidence.get(
                "osmosis_replication_timestamp"
            ),
            "source_header": header_evidence.get("source"),
            "interpretation": (
                "Header generator/source keys are the only origin evidence in the "
                "file. Download URL and acquisition time remain UNKNOWN; the "
                "filesystem mtime is not acquisition evidence."
            ),
        },
        "limitations": [
            "Research sample only; exported counts are a bounded slice, not coverage.",
            "District/administrative area is not inferred from the bounding box.",
            "Only NODE geometry is used; way/relation centers are excluded.",
            "OSM tags are source evidence, not independent ground truth.",
        ],
        "header_evidence": header_evidence,
        "osmium_version": __import__("osmium").__version__
        if hasattr(__import__("osmium"), "__version__")
        else "unknown",
        "python_version": sys.version.split()[0],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    export_path = out_dir / "osm_local_sample.json"
    provenance_path = out_dir / "osm_local_provenance.json"
    log_path = out_dir / "osm_local_commands.log"

    _write_json(export_path, export, args.force)
    _write_json(provenance_path, provenance, args.force)
    log_lines = [
        "command: " + " ".join([Path(sys.argv[0]).name, *sys.argv[1:]]),
        f"pbf: {pbf}",
        f"pbf_sha256: {pbf_sha256}",
        f"derived_export_time_utc: {derived_at}",
        f"bbox: {args.bbox}",
        f"exported: {result['exported']} (matched before cap: {result['total_matched']})",
    ]
    _write_text(log_path, "\n".join(log_lines) + "\n", args.force)

    sys.stdout.write(
        json.dumps(
            {
                "status": "ok",
                "export": str(export_path),
                "provenance": str(provenance_path),
                "exported": result["exported"],
                "total_matched_before_limit": result["total_matched"],
                "truncated": result["truncated"],
                "parent_pbf_sha256": pbf_sha256,
            },
            sort_keys=True,
        )
        + "\n"
    )
    return 0


def _write_bytes(path: Path, payload: bytes, force: bool) -> None:
    if path.exists():
        if path.read_bytes() == payload:
            return
        if not force:
            raise SystemExit(
                f"refusing to overwrite existing file with different bytes: {path}"
            )
    path.write_bytes(payload)


def _write_json(path: Path, value: Any, force: bool) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _write_bytes(path, text.encode("utf-8"), force)


def _write_text(path: Path, text: str, force: bool) -> None:
    _write_bytes(path, text.encode("utf-8"), force)


if __name__ == "__main__":
    raise SystemExit(main())
