"""EXP089 — separate read-only E2 Memgraph primary-data collector.

Scope and evidence boundary
---------------------------
This module plans and (only after an explicitly reviewed frozen manifest)
executes the E2 spatial correctness/candidate-pruning measurements against the
*full primary* 6,367-record snapshot.  It never writes to the graph, never
loads application settings, never reads environment variables and never makes
a model or provider call.

Default behaviour is a dry-run plan.  A dry-run makes **zero** driver or
network calls.  ``--execute`` refuses to construct the Neo4j driver unless the
manifest is frozen, independently reviewed, and binds the exact input,
collector, production spatial source and query texts.

Evidence labels are intentionally narrow:

* baseline and optimized correctness rows are accepted unordered external-ID
  pairs;
* timing cells use fixed count-only aggregate variants of the same predicates;
  their latency is end-to-end execution of a one-row count, **not** transfer of
  every accepted pair;
* candidate counts are *logical prefilter predicate/input counts*, not
  physically instrumented engine evaluation counts;
* accepted-set equality is checked in RAM, not by count alone;
* an explicit driver authorization/permission denial is terminal; it is never
  down-graded to an optional metadata gap or followed by more engine queries;
* read-only canonical queries do not prove stored ``:NEAR_BY`` relationship
  orientation, duplicate or stale-update semantics;
* source-area labels are dataset labels, not verified current administrative
  containment.

Run the offline tests only through pytest; the real ``--execute`` path is
reserved for a later reviewed live run.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import platform
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

try:  # package import (``-m benchmarks.spatial_live.runner``)
    from . import journal as journal_module
except ImportError:  # direct script execution (``python benchmarks/.../runner.py``)
    import journal as journal_module  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# Fixed public paths and constants
# ---------------------------------------------------------------------------

TASK_ID = "EXP089"
SCHEMA_VERSION = "exp089.e2.live.v1"
MANIFEST_SCHEMA = "exp089.e2.manifest.v1"
PLAN_SCHEMA = "exp089.e2.plan.v1"

# ---------------------------------------------------------------------------
# TIM096 collection modes
# ---------------------------------------------------------------------------

#: Legacy full cohort: projection + 3 correctness radii + 36 timing cells.
COLLECTION_MODE_FULL = "full"
#: New timing-only cohort that reuses a validated external correctness proof.
COLLECTION_MODE_TIMING_ONLY = "timing_only_external_correctness"
COLLECTION_MODES = (COLLECTION_MODE_FULL, COLLECTION_MODE_TIMING_ONLY)
TIMING_ONLY_PROTOCOL = "tim096.external_correctness.v1"
EXTERNAL_CORRECTNESS_SCHEMA = "tim096.external_correctness_reference.v1"
TIMING_ONLY_RUN_TIMEOUT_SECONDS = 7200

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_PATH = (
    REPO_ROOT / "data" / "primary_20261016" / "graph_ready_v2" / "prepared_pois.jsonl"
)
SPATIAL_PATH = REPO_ROOT / "POI_service" / "app" / "core" / "utils" / "spatial.py"
COLLECTOR_PATH = Path(__file__).resolve()
JOURNAL_PATH = COLLECTOR_PATH.with_name("journal.py")
SUPERVISOR_PATH = COLLECTOR_PATH.with_name("supervisor.py")
DURABILITY_PROTOCOL = journal_module.PROTOCOL

DEFAULT_INPUT_SHA256 = (
    "37340a8021ca7e8b37efc1053718c4c87879f95fa9937d8c53e1a0218f080dd1"
)
DEFAULT_RECORD_COUNT = 6367
DEFAULT_POTENTIAL_PAIRS = 20_266_161

RADII_KM: tuple[float, ...] = (1.0, 3.0, 5.0)
BATCH_SIZE = 128
WARMUP_RUNS = 1
MEASURED_REPETITIONS = 5
TIMING_CELLS_TOTAL = len(RADII_KM) * 2 * (WARMUP_RUNS + MEASURED_REPETITIONS)
TIMING_PLANNED_LABEL = "36 cells = 3 radii x 2 arms x (1 warm-up + 5 measured)"

QUERY_TIMEOUT_SECONDS = 120
RUN_TIMEOUT_SECONDS = 3600
FIXED_BOLT_URI = "bolt://127.0.0.1:17687"

SOURCE_AREA_SCHEMA = "source_area_scope_v1"
SOURCE_AREA_ID_PREFIX = "source_area_v1:"

#: Tokens that must never occur in a collector query.  The exact allow-list is
#: applied first; this is a second, defence-in-depth check.
_FORBIDDEN_QUERY_TOKENS = re.compile(
    r"\b(CALL|CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP|LOAD|FOREACH)\b",
    re.IGNORECASE,
)

#: Public, bounded mismatch samples retained in evidence.
MAX_MISMATCH_SAMPLES = 10


# ---------------------------------------------------------------------------
# Errors and small helpers
# ---------------------------------------------------------------------------


class CollectorError(Exception):
    """A closed, sanitized collector failure.

    The exception never carries an arbitrary engine message.  ``detail`` is
    built only from public counts, IDs and closed labels.
    """

    def __init__(
        self,
        code: str,
        *,
        error_type: str | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.error_type = error_type
        self.detail = dict(detail or {})

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code}
        if self.error_type:
            payload["type"] = self.error_type
        if self.detail:
            payload["detail"] = _public_detail(self.detail)
        return payload


def _public_detail(value: Any) -> Any:
    """Keep evidence JSON to public, bounded scalar/ID material."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(k): _public_detail(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_public_detail(v) for v in value[:MAX_MISMATCH_SAMPLES]]
    return type(value).__name__


AUTH_DENIED_CODE = "engine_auth_denied"

#: Closed set of public Neo4j driver authorization status codes.  Only these
#: exact values are recognized; arbitrary message text is never inspected.
_DRIVER_AUTH_CODES = frozenset(
    {
        "Neo.ClientError.Security.Unauthorized",
        "Neo.ClientError.Security.Forbidden",
        "Neo.ClientError.Security.CredentialsExpired",
        "Neo.ClientError.Security.AuthorizationExpired",
    }
)

#: Closed set of explicit installed-driver authorization exception classes.
_DRIVER_AUTH_TYPE_NAMES = frozenset(
    {"AuthError", "AuthConfigurationError", "Forbidden"}
)


def is_engine_auth_denied(error: Any) -> bool:
    """Whether a CollectorError/error dict is the closed terminal auth denial."""
    if isinstance(error, CollectorError):
        return error.code == AUTH_DENIED_CODE
    if isinstance(error, Mapping):
        return error.get("code") == AUTH_DENIED_CODE
    return False


def classify_engine_exception(exc: BaseException) -> CollectorError:
    """Map an engine exception to a closed, sanitized collector error.

    Authorization/permission denial is recognized only from an exact public
    driver ``.code`` or an explicit driver exception class name.  Raw messages,
    raw codes and arbitrary text (including the word "unauthorized") are never
    retained or used as a diagnosis.
    """
    if isinstance(exc, CollectorError):
        if exc.code in _DRIVER_AUTH_CODES:
            return CollectorError(AUTH_DENIED_CODE, error_type=exc.error_type)
        return exc

    type_name = type(exc).__name__
    driver_code = getattr(exc, "code", None)
    if type_name in _DRIVER_AUTH_TYPE_NAMES or (
        isinstance(driver_code, str) and driver_code in _DRIVER_AUTH_CODES
    ):
        return CollectorError(AUTH_DENIED_CODE, error_type=type_name)
    code = "query_timeout" if "timeout" in type_name.lower() else "engine_error"
    return CollectorError(code, error_type=type_name)


def canonical_json(value: Any) -> str:
    """Canonical JSON used for reproducible hashes only."""
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def potential_pairs(n: int) -> int:
    """Unordered whole-universe potential pairs ``n(n-1)/2``."""
    if n < 2:
        return 0
    return n * (n - 1) // 2


def pruning_percent(potential: int | None, candidates: int | None) -> float | None:
    """Pruning percentage, explicitly undefined for a zero denominator."""
    if potential is None or candidates is None:
        return None
    if potential <= 0:
        return None
    return 100.0 * (1.0 - (float(candidates) / float(potential)))


def canonical_pair(a: str, b: str) -> tuple[str, str]:
    """Canonical unordered external-ID pair in ascending external order."""
    if not isinstance(a, str) or not isinstance(b, str) or not a or not b:
        raise CollectorError("pair_endpoint_invalid")
    if a == b:
        raise CollectorError("pair_self_rejected")
    return (a, b) if a < b else (b, a)


def canonical_pairs_digest(pairs: Iterable[tuple[str, str]]) -> str:
    """Deterministic SHA256 over sorted JSON-array pair serializations."""
    normalized = sorted(set(pairs))
    digest = hashlib.sha256()
    for a, b in normalized:
        digest.update(
            json.dumps([a, b], ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        digest.update(b"\n")
    return digest.hexdigest()


def _feed_pair(digest: Any, a: str, b: str) -> None:
    digest.update(
        json.dumps([a, b], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    digest.update(b"\n")


def batch_ids(ids: Sequence[str], size: int = BATCH_SIZE) -> list[list[str]]:
    ordered = sorted(ids)
    return [ordered[index : index + size] for index in range(0, len(ordered), size)]


# ---------------------------------------------------------------------------
# Production spatial source, imported in isolation
# ---------------------------------------------------------------------------


def _load_spatial_module(path: Path) -> Any:
    """Load only the pure production spatial module.

    ``importlib`` with an explicit file path avoids importing the application
    package, settings, database connector or repository.
    """
    spec = importlib.util.spec_from_file_location("_exp089_production_spatial", path)
    if spec is None or spec.loader is None:
        raise CollectorError("spatial_import_failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SPATIAL_MODULE = _load_spatial_module(SPATIAL_PATH)
EARTH_RADIUS_KM_LOWER_BOUND = float(SPATIAL_MODULE.EARTH_RADIUS_KM_LOWER_BOUND)
PREFILTER_EXPR = SPATIAL_MODULE.conservative_prefilter_cypher(
    lat_a="a.latitude",
    lon_a="a.longitude",
    lat_b="b.latitude",
    lon_b="b.longitude",
)

_DISTANCE_EXPR = (
    "point.distance(\n"
    "    point({latitude: a.latitude, longitude: a.longitude}),\n"
    "    point({latitude: b.latitude, longitude: b.longitude})\n"
    ")"
)

# ---------------------------------------------------------------------------
# Query texts (fixed, parameterized and manifest-bound)
# ---------------------------------------------------------------------------

PROJECTION_QUERY = """
MATCH (p:POI)
WHERE p.id IN $ids
RETURN p.id AS id,
       p.latitude AS latitude,
       p.longitude AS longitude,
       p.source_area_id AS source_area_id,
       p.source_snapshot_sha256 AS input_sha256,
       p.source_dataset_namespace AS dataset_namespace,
       p.source_metadata_sha256 AS metadata_sha256
""".strip()

OUT_OF_UNIVERSE_QUERY = """
MATCH (p:POI)
WHERE NOT (p.id IN $ids)
RETURN count(p) AS extra_poi_count
""".strip()

SCOPED_COUNTS_QUERY = """
MATCH (p:POI)
WHERE p.id IN $ids
RETURN count(p) AS poi_count,
       count(DISTINCT p.id) AS distinct_poi_ids
""".strip()

MATERIALIZATION_QUERY = """
MATCH (a:POI)-[r:NEAR_BY]->(b:POI)
WHERE a.id IN $ids AND b.id IN $ids
RETURN count(r) AS directed_edges,
       sum(CASE WHEN a.id < b.id THEN 1 ELSE 0 END) AS canonical_directed_edges,
       sum(CASE WHEN a.id >= b.id THEN 1 ELSE 0 END) AS noncanonical_or_self_directed_edges
""".strip()

INDEX_INFO_QUERY = "SHOW INDEX INFO"

BASELINE_QUERY = f"""
UNWIND $anchors AS anchor_id
MATCH (a:POI {{id: anchor_id}})
MATCH (b:POI)
WHERE b.id IN $ids AND a.id < b.id
WITH a, b, {_DISTANCE_EXPR} AS distance_m
WHERE distance_m <= $radius_km * 1000.0
RETURN a.id AS a_id, b.id AS b_id, distance_m
""".strip()

OPTIMIZED_QUERY = f"""
UNWIND $anchors AS anchor_id
MATCH (a:POI {{id: anchor_id}})
MATCH (b:POI)
WHERE b.id IN $ids AND a.id < b.id
WITH a, b
WHERE {PREFILTER_EXPR}
WITH a, b, {_DISTANCE_EXPR} AS distance_m
WHERE distance_m <= $radius_km * 1000.0
RETURN a.id AS a_id, b.id AS b_id, distance_m
""".strip()

CANDIDATE_COUNT_QUERY = f"""
UNWIND $anchors AS anchor_id
MATCH (a:POI {{id: anchor_id}})
MATCH (b:POI)
WHERE b.id IN $ids AND a.id < b.id
WITH a, b
WHERE {PREFILTER_EXPR}
RETURN count(*) AS candidate_pairs
""".strip()

#: Timed queries are the exact correctness pair queries with only the final
#: RETURN replaced by a server-side aggregate.  The correctness queries keep
#: returning pair rows so that real-set equality remains checkable.
TIMING_BASELINE_QUERY = f"""
UNWIND $anchors AS anchor_id
MATCH (a:POI {{id: anchor_id}})
MATCH (b:POI)
WHERE b.id IN $ids AND a.id < b.id
WITH a, b, {_DISTANCE_EXPR} AS distance_m
WHERE distance_m <= $radius_km * 1000.0
RETURN count(*) AS accepted_pairs
""".strip()

TIMING_OPTIMIZED_QUERY = f"""
UNWIND $anchors AS anchor_id
MATCH (a:POI {{id: anchor_id}})
MATCH (b:POI)
WHERE b.id IN $ids AND a.id < b.id
WITH a, b
WHERE {PREFILTER_EXPR}
WITH a, b, {_DISTANCE_EXPR} AS distance_m
WHERE distance_m <= $radius_km * 1000.0
RETURN count(*) AS accepted_pairs
""".strip()

QUERY_TEXTS: dict[str, str] = {
    "projection": PROJECTION_QUERY,
    "out_of_universe": OUT_OF_UNIVERSE_QUERY,
    "scoped_counts": SCOPED_COUNTS_QUERY,
    "materialization": MATERIALIZATION_QUERY,
    "index_info": INDEX_INFO_QUERY,
    "baseline": BASELINE_QUERY,
    "optimized": OPTIMIZED_QUERY,
    "candidates": CANDIDATE_COUNT_QUERY,
    "timing_baseline": TIMING_BASELINE_QUERY,
    "timing_optimized": TIMING_OPTIMIZED_QUERY,
}

_ALLOWED_QUERY_TEXTS = frozenset(QUERY_TEXTS.values())


def query_hashes() -> dict[str, str]:
    return {
        name: hashlib.sha256(text.encode("utf-8")).hexdigest()
        for name, text in QUERY_TEXTS.items()
    }


def assert_allowed_query(text: str) -> None:
    """Fail closed unless the text is one of the fixed read-only templates."""
    if not isinstance(text, str) or text not in _ALLOWED_QUERY_TEXTS:
        raise CollectorError("query_not_allowlisted")
    if _FORBIDDEN_QUERY_TOKENS.search(text):
        raise CollectorError("write_token_rejected")


# ---------------------------------------------------------------------------
# Source records and source-area bindings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PoiRecord:
    id: str
    latitude: float
    longitude: float
    source_metadata: Mapping[str, Any]
    source_area_id: str
    raw_city: str | None
    raw_area: str | None
    metadata_sha256: str


def _raw_label(address: Mapping[str, Any], key: str) -> str | None:
    if key not in address:
        return None
    value = address.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise CollectorError("source_area_binding_invalid")
    if not value.strip():
        return None
    return value


def derive_source_area_id(
    dataset_namespace: str,
    input_sha256: str,
    raw_city: str | None,
    raw_area: str | None,
) -> str:
    """Mirror of the documented production source-area material formula."""
    material = {
        "dataset_namespace": dataset_namespace,
        "input_sha256": input_sha256,
        "raw_area": raw_area,
        "raw_city": raw_city,
        "schema": SOURCE_AREA_SCHEMA,
    }
    encoded = json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return SOURCE_AREA_ID_PREFIX + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _coerce_coordinate(value: Any, *, axis: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CollectorError(f"input_coordinate_{axis}_invalid")
    number = float(value)
    if not math.isfinite(number):
        raise CollectorError(f"input_coordinate_{axis}_nonfinite")
    if axis == "latitude" and not (-90.0 <= number <= 90.0):
        raise CollectorError("input_coordinate_latitude_out_of_range")
    if axis == "longitude" and not (-180.0 <= number <= 180.0):
        raise CollectorError("input_coordinate_longitude_out_of_range")
    return number


def _record_from_object(row: Mapping[str, Any]) -> PoiRecord:
    poi_id = row.get("id")
    if not isinstance(poi_id, str) or not poi_id.strip():
        raise CollectorError("input_id_invalid")
    if "latitude" not in row or "longitude" not in row:
        raise CollectorError("input_coordinate_missing")
    latitude = _coerce_coordinate(row["latitude"], axis="latitude")
    longitude = _coerce_coordinate(row["longitude"], axis="longitude")
    metadata = row.get("source_metadata")
    if not isinstance(metadata, Mapping):
        raise CollectorError("input_source_metadata_invalid")
    namespace = metadata.get("dataset_namespace")
    input_sha = metadata.get("input_sha256")
    if not isinstance(namespace, str) or not namespace.strip():
        raise CollectorError("input_source_metadata_invalid")
    if not isinstance(input_sha, str) or not input_sha:
        raise CollectorError("input_source_metadata_invalid")
    raw_lineage = metadata.get("raw_lineage_json")
    if not isinstance(raw_lineage, str):
        raise CollectorError("input_source_metadata_invalid")
    try:
        lineage = json.loads(raw_lineage)
    except (TypeError, ValueError):
        raise CollectorError("input_source_metadata_invalid") from None
    if not isinstance(lineage, Mapping):
        raise CollectorError("input_source_metadata_invalid")
    address = lineage.get("address")
    if not isinstance(address, Mapping):
        raise CollectorError("input_source_metadata_invalid")
    raw_city = _raw_label(address, "raw_city")
    raw_area = _raw_label(address, "raw_district")
    area_id = derive_source_area_id(namespace, input_sha, raw_city, raw_area)
    metadata_hash = hashlib.sha256(canonical_json(metadata).encode("utf-8")).hexdigest()
    return PoiRecord(
        id=poi_id,
        latitude=latitude,
        longitude=longitude,
        source_metadata=metadata,
        source_area_id=area_id,
        raw_city=raw_city,
        raw_area=raw_area,
        metadata_sha256=metadata_hash,
    )


def load_records(
    path: Path | str,
    *,
    expected_sha256: str | None = None,
    expected_count: int | None = None,
) -> tuple[list[PoiRecord], str]:
    """Read every JSONL line, rejecting silent drops, duplicates and bad coords.

    IDs are canonically sorted for deterministic batches.  A legitimate file
    order therefore does not change the derived scope hash; the raw file hash
    still binds the exact bytes to the reviewed manifest.
    """
    source_path = Path(path)
    try:
        payload = source_path.read_bytes()
    except OSError:
        raise CollectorError("input_unreadable") from None
    digest = hashlib.sha256(payload).hexdigest()

    resolved = source_path.resolve()
    if expected_sha256 is None and resolved == DEFAULT_INPUT_PATH.resolve():
        expected_sha256 = DEFAULT_INPUT_SHA256
    if expected_sha256 is not None and digest != expected_sha256:
        raise CollectorError("input_hash_mismatch")

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        raise CollectorError("input_encoding_invalid") from None

    lines = text.splitlines()
    if not lines:
        raise CollectorError("input_empty")
    records: list[PoiRecord] = []
    seen: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise CollectorError("input_blank_line", detail={"line": line_number})
        try:
            row = json.loads(line)
        except (TypeError, ValueError):
            raise CollectorError("input_json_invalid", detail={"line": line_number}) from None
        if not isinstance(row, Mapping):
            raise CollectorError("input_json_invalid", detail={"line": line_number})
        record = _record_from_object(row)
        if record.id in seen:
            raise CollectorError("input_duplicate_id")
        seen.add(record.id)
        records.append(record)

    if expected_count is not None and len(records) != expected_count:
        raise CollectorError(
            "input_record_count_mismatch",
            detail={"expected": expected_count, "observed": len(records)},
        )
    if resolved == DEFAULT_INPUT_PATH.resolve() and len(records) != DEFAULT_RECORD_COUNT:
        raise CollectorError(
            "input_record_count_mismatch",
            detail={"expected": DEFAULT_RECORD_COUNT, "observed": len(records)},
        )
    records.sort(key=lambda record: record.id)
    return records, digest


def scope_hash(records: Sequence[PoiRecord]) -> str:
    material = [
        [record.id, record.latitude, record.longitude]
        for record in sorted(records, key=lambda item: item.id)
    ]
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


def source_area_summary(records: Sequence[PoiRecord]) -> dict[str, Any]:
    by_area: dict[str, int] = {}
    labels: dict[tuple[str | None, str | None], int] = {}
    for record in records:
        by_area[record.source_area_id] = by_area.get(record.source_area_id, 0) + 1
        key = (record.raw_city, record.raw_area)
        labels[key] = labels.get(key, 0) + 1
    raw_counts = [
        {"raw_city": city, "raw_area": area, "count": count}
        for (city, area), count in sorted(
            labels.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))
        )
    ]
    return {
        "source_area_id_counts": dict(sorted(by_area.items())),
        "raw_label_counts": raw_counts,
        "administrative_binding": "source_snapshot_area_only_not_current_admin",
    }


# ---------------------------------------------------------------------------
# Manifest / plan
# ---------------------------------------------------------------------------


def _relative_public_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _runtime_metadata() -> dict[str, Any]:
    """Public runtime metadata; no environment enumeration or secrets."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            neo4j_version = version("neo4j")
        except PackageNotFoundError:
            neo4j_version = None
    except Exception:
        neo4j_version = None
    return {
        "python_version": sys.version,
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count_logical": os.cpu_count(),
        "neo4j_package_version": neo4j_version,
        "collector_runtime": "stdlib + lazily imported installed neo4j",
    }


def _source_pins() -> dict[str, Any]:
    """Live source pins for the durable collector/supervisor/journal trio."""
    return {
        "protocol": DURABILITY_PROTOCOL,
        "runner": {
            "path": _relative_public_path(COLLECTOR_PATH),
            "sha256": file_sha256(COLLECTOR_PATH),
        },
        "journal": {
            "path": _relative_public_path(JOURNAL_PATH),
            "sha256": file_sha256(JOURNAL_PATH),
        },
        "supervisor": {
            "path": _relative_public_path(SUPERVISOR_PATH),
            "sha256": file_sha256(SUPERVISOR_PATH),
        },
    }


def journal_binding(
    manifest: Mapping[str, Any],
    manifest_sha256: str,
    input_sha256: str,
    *,
    collection_mode: str | None = None,
    external_reference: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Header binding to the exact frozen manifest and live source pins."""
    mode = collection_mode or resolve_collection_mode(manifest)
    binding = {
        "protocol": (
            TIMING_ONLY_PROTOCOL
            if mode == COLLECTION_MODE_TIMING_ONLY
            else DURABILITY_PROTOCOL
        ),
        "journal_schema": journal_module.JOURNAL_SCHEMA,
        "manifest_sha256": manifest_sha256,
        "manifest_schema": manifest.get("schema"),
        "input_sha256": input_sha256,
        "sources": _source_pins(),
    }
    if mode == COLLECTION_MODE_TIMING_ONLY:
        binding["collection_mode"] = COLLECTION_MODE_TIMING_ONLY
        if external_reference is not None:
            binding["external_correctness"] = _external_reference_binding(
                external_reference
            )
    return binding


def journal_planned_denominator(
    records: Sequence[PoiRecord],
    *,
    collection_mode: str = COLLECTION_MODE_FULL,
    external_reference: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Immutable planned denominator stored in the journal header."""
    planned: dict[str, Any] = {
        "records": len(records),
        "batches_total": len(batch_ids([record.id for record in records])),
        "potential_pairs": potential_pairs(len(records)),
        "batch_size": BATCH_SIZE,
        "radii_km": list(RADII_KM),
        "warmups": WARMUP_RUNS,
        "measured_repetitions": MEASURED_REPETITIONS,
        "timing_cells_total": TIMING_CELLS_TOTAL,
        "timing_cells": [
            {
                "radius_km": cell["radius_km"],
                "arm": cell["arm"],
                "repetition": cell["repetition"],
                "phase": cell["phase"],
            }
            for cell in _timing_plan()
        ],
    }
    if collection_mode == COLLECTION_MODE_TIMING_ONLY:
        planned["collection_mode"] = COLLECTION_MODE_TIMING_ONLY
        planned["correctness"] = {
            "planned_queries": 0,
            "external_reference_radii": list(RADII_KM),
            "correctness_reused_not_rerun": True,
        }
        if external_reference is not None:
            planned["external_correctness"] = _external_reference_binding(
                external_reference
            )
    return planned


def _emit(
    on_event: Callable[[str, Mapping[str, Any]], None] | None,
    kind: str,
    payload: Mapping[str, Any],
) -> None:
    """Public, sanitized callback; no-op for existing fake unit APIs."""
    if on_event is not None:
        on_event(kind, dict(payload))


def ensure_journal_absent(output_path: Path | str) -> Path:
    """Refuse a reused journal before backend construction (no truncation)."""
    journal_path = journal_module.journal_path_for(output_path)
    if journal_path.exists():
        raise CollectorError("journal_exists")
    return journal_path


def build_manifest(
    records: Sequence[PoiRecord],
    input_path: Path | str,
    *,
    input_sha256: str | None = None,
    collection_mode: str = COLLECTION_MODE_FULL,
    external_correctness: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an unfrozen candidate manifest.  Never self-approves."""
    source_path = Path(input_path)
    digest = input_sha256 or file_sha256(source_path)
    count = len(records)
    pairs = potential_pairs(count)
    if collection_mode not in COLLECTION_MODES:
        raise CollectorError("manifest_collection_mode_invalid")
    if collection_mode == COLLECTION_MODE_TIMING_ONLY:
        if not isinstance(external_correctness, Mapping):
            raise CollectorError("external_correctness_reference_required")
        run_timeout = TIMING_ONLY_RUN_TIMEOUT_SECONDS
    else:
        run_timeout = RUN_TIMEOUT_SECONDS
    is_full_primary = (
        digest == DEFAULT_INPUT_SHA256
        and count == DEFAULT_RECORD_COUNT
        and pairs == DEFAULT_POTENTIAL_PAIRS
    )
    manifest: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "task_id": TASK_ID,
        "collection_mode": collection_mode,
        "frozen": False,
        "review": {"decision": "pending", "reviewer": None},
        "dataset": {
            "path": _relative_public_path(source_path),
            "sha256": digest,
            "records": count,
            "potential_pairs": pairs,
            "is_full_primary": is_full_primary,
            "primary_label_policy": (
                "full_primary only when exact default input hash, 6367 records "
                "and 20266161 potential pairs"
            ),
        },
        "scope": {
            "id_coordinate_sha256": scope_hash(records),
            **source_area_summary(records),
            "cross_area_filtering": False,
            "identical_coordinates_distinct_ids": True,
            "canonical_pair_order": "external_id_ascending",
            "boundary_fixture_plan": {
                "mode": "offline_fake_only",
                "synthetic": True,
                "graph_fixture_nodes": False,
                "cases": [
                    "poles",
                    "dateline",
                    "identical_coordinates_distinct_ids",
                    "reversed_input_order",
                    "cross_area_labels",
                ],
                "note": (
                    "offline fake/reference fixtures only; no CREATE fixture nodes "
                    "on a populated graph"
                ),
            },
        },
        "spatial": {
            "path": _relative_public_path(SPATIAL_PATH),
            "sha256": file_sha256(SPATIAL_PATH),
            "export": "conservative_prefilter_cypher + EARTH_RADIUS_KM_LOWER_BOUND",
        },
        "collector": {
            "path": _relative_public_path(COLLECTOR_PATH),
            "sha256": file_sha256(COLLECTOR_PATH),
        },
        "sources": _source_pins(),
        "durability": {
            "protocol": DURABILITY_PROTOCOL,
            "journal": "append-only local JSONL, sequence + SHA256 chain",
            "journal_path_rule": "<output>.journal.jsonl",
            "supervisor": f"one fixed child, {run_timeout} s hard client deadline",
            "resume": False,
        },
        "queries": query_hashes(),
        "runtime": _runtime_metadata(),
        "budget": {
            "radii_km": list(RADII_KM),
            "batch_size": BATCH_SIZE,
            "warmups": WARMUP_RUNS,
            "measured_repetitions": MEASURED_REPETITIONS,
            "timing_cells_total": TIMING_CELLS_TOTAL,
            "query_timeout_seconds": QUERY_TIMEOUT_SECONDS,
            "run_timeout_seconds": run_timeout,
        },
        "execution": {
            "engine_uri": FIXED_BOLT_URI,
            "auth": "none",
            "read_only": True,
            "model_calls": 0,
            "graph_mutation": False,
        },
        "labels": {
            "candidate_counts": "logical prefilter predicate/input counts",
            "physical_engine_evaluation_counts": None,
            "timing_workload": (
                "count-only aggregate over the same predicates; end-to-end latency "
                "does not include transferring every accepted pair row"
            ),
            "stored_relationship_semantics": "not proven by read-only canonical queries",
            "source_areas": "dataset labels, not current administrative containment",
        },
    }
    if collection_mode == COLLECTION_MODE_TIMING_ONLY:
        manifest["external_correctness"] = dict(external_correctness or {})
    return manifest


def _require_mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CollectorError(code)
    return value


def resolve_collection_mode(manifest: Mapping[str, Any]) -> str:
    """Resolve the explicit collection mode; a missing field is legacy full."""
    mode = manifest.get("collection_mode", COLLECTION_MODE_FULL)
    if not isinstance(mode, str) or mode not in COLLECTION_MODES:
        raise CollectorError("manifest_collection_mode_invalid")
    return mode


def expected_run_timeout(mode: str) -> int:
    if mode == COLLECTION_MODE_TIMING_ONLY:
        return TIMING_ONLY_RUN_TIMEOUT_SECONDS
    if mode == COLLECTION_MODE_FULL:
        return RUN_TIMEOUT_SECONDS
    raise CollectorError("manifest_collection_mode_invalid")


def _finite_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CollectorError("manifest_budget_drift")
    number = float(value)
    if not math.isfinite(number):
        raise CollectorError("manifest_budget_drift")
    return number


def resolve_run_budget(manifest: Mapping[str, Any]) -> int:
    """Resolve the execution budget only from the validated mode + budget."""
    mode = resolve_collection_mode(manifest)
    budget = _require_mapping(manifest.get("budget"), "manifest_budget_invalid")
    value = budget.get("run_timeout_seconds")
    expected = expected_run_timeout(mode)
    if _finite_number(value) != float(expected):
        raise CollectorError("manifest_budget_drift")
    return expected


def _require_exact_budget(manifest: Mapping[str, Any]) -> None:
    mode = resolve_collection_mode(manifest)
    budget = _require_mapping(manifest.get("budget"), "manifest_budget_invalid")
    expected: dict[str, Any] = {
        "radii_km": list(RADII_KM),
        "batch_size": BATCH_SIZE,
        "warmups": WARMUP_RUNS,
        "measured_repetitions": MEASURED_REPETITIONS,
        "timing_cells_total": TIMING_CELLS_TOTAL,
        "query_timeout_seconds": QUERY_TIMEOUT_SECONDS,
        "run_timeout_seconds": expected_run_timeout(mode),
    }
    for key, value in expected.items():
        actual = budget.get(key)
        if key == "radii_km":
            if (
                not isinstance(actual, (list, tuple))
                or len(actual) != len(value)
                or any(
                    isinstance(item, bool)
                    or not isinstance(item, (int, float))
                    or not math.isfinite(float(item))
                    for item in actual
                )
                or [float(item) for item in actual] != [float(item) for item in value]
            ):
                raise CollectorError("manifest_budget_drift")
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            if _finite_number(actual) != float(value):
                raise CollectorError("manifest_budget_drift")
        elif actual != value:
            raise CollectorError("manifest_budget_drift")


def validate_manifest(
    manifest: Mapping[str, Any],
    records: Sequence[PoiRecord],
    input_path: Path | str,
    input_sha256: str,
    *,
    require_frozen: bool,
) -> None:
    """Reject drift by comparing frozen expectations; never recompute them in."""
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise CollectorError("manifest_schema_invalid")
    if manifest.get("task_id") != TASK_ID:
        raise CollectorError("manifest_task_invalid")
    mode = resolve_collection_mode(manifest)
    _require_exact_budget(manifest)
    if mode == COLLECTION_MODE_TIMING_ONLY:
        reference = _require_mapping(
            manifest.get("external_correctness"),
            "external_correctness_reference_required",
        )
        if reference.get("protocol") != TIMING_ONLY_PROTOCOL:
            raise CollectorError("external_reference_protocol_invalid")

    dataset = _require_mapping(manifest.get("dataset"), "manifest_dataset_invalid")
    if dataset.get("sha256") != input_sha256:
        raise CollectorError("manifest_input_hash_drift")
    if dataset.get("records") != len(records):
        raise CollectorError("manifest_record_count_drift")
    if dataset.get("potential_pairs") != potential_pairs(len(records)):
        raise CollectorError("manifest_potential_pairs_drift")
    scope = _require_mapping(manifest.get("scope"), "manifest_scope_invalid")
    if scope.get("id_coordinate_sha256") != scope_hash(records):
        raise CollectorError("manifest_scope_hash_drift")

    spatial = _require_mapping(manifest.get("spatial"), "manifest_spatial_invalid")
    if spatial.get("sha256") != file_sha256(SPATIAL_PATH):
        raise CollectorError("manifest_spatial_hash_drift")
    collector = _require_mapping(manifest.get("collector"), "manifest_collector_invalid")
    if collector.get("sha256") != file_sha256(COLLECTOR_PATH):
        raise CollectorError("manifest_collector_hash_drift")

    sources = _require_mapping(manifest.get("sources"), "manifest_source_pins_missing")
    if sources.get("protocol") != DURABILITY_PROTOCOL:
        raise CollectorError("manifest_protocol_drift")
    for name, path in (
        ("runner", COLLECTOR_PATH),
        ("journal", JOURNAL_PATH),
        ("supervisor", SUPERVISOR_PATH),
    ):
        pin = _require_mapping(
            sources.get(name), "manifest_source_pins_missing"
        )
        if pin.get("sha256") != file_sha256(path):
            raise CollectorError("manifest_source_hash_drift")
    queries = _require_mapping(manifest.get("queries"), "manifest_queries_invalid")
    actual_queries = query_hashes()
    if dict(queries) != actual_queries:
        raise CollectorError("manifest_query_hash_drift")

    execution = _require_mapping(manifest.get("execution"), "manifest_execution_invalid")
    if execution.get("engine_uri") != FIXED_BOLT_URI:
        raise CollectorError("remote_endpoint_not_allowed")
    if execution.get("auth") != "none":
        raise CollectorError("manifest_auth_override_rejected")
    if execution.get("read_only") is not True:
        raise CollectorError("manifest_read_only_required")

    computed_full = (
        input_sha256 == DEFAULT_INPUT_SHA256
        and len(records) == DEFAULT_RECORD_COUNT
        and potential_pairs(len(records)) == DEFAULT_POTENTIAL_PAIRS
    )
    if bool(dataset.get("is_full_primary")) != computed_full:
        raise CollectorError("primary_label_mismatch")

    if require_frozen:
        if manifest.get("frozen") is not True:
            raise CollectorError("manifest_not_frozen")
        review = _require_mapping(manifest.get("review"), "manifest_review_invalid")
        if review.get("decision") != "approved":
            raise CollectorError("manifest_review_required")
        reviewer = review.get("reviewer")
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise CollectorError("manifest_reviewer_required")


# ---------------------------------------------------------------------------
# Pinned external correctness reference (TIM096 timing-only mode)
# ---------------------------------------------------------------------------

#: Public subtrees allowed to hold an external proof.  Nothing else is read.
_EXTERNAL_REFERENCE_ROOTS = (
    (REPO_ROOT / "docs" / "project" / "handoffs").resolve(),
    (REPO_ROOT / "docs" / "experiments").resolve(),
)

#: Closed deny-list checked before a reference path is opened.  This is a
#: path-safety guard, not a general-purpose file loader.
_DENIED_REFERENCE_TOKENS = (
    ".env",
    "credential",
    "secret",
    "private",
    "auth",
    "config",
    "incident",
    ".git",
)

_EXTERNAL_ROLE_BASENAMES = {
    "frozen_manifest": "e2-execution.frozen.json",
    "parent_review": "parent-primary-result-review.json",
    "archived_runner": "runner.py",
    "archived_journal": "journal.py",
    "archived_supervisor": "supervisor.py",
}


def _is_sha256_hex(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_reference_parts(parts: Sequence[str], role: str) -> None:
    """Reject denied tokens and role-mismatched basenames in a path shape.

    Called for the lexical path and again for the fully resolved path so a
    symlink cannot redirect an approved-looking name (for example
    ``public/e2-execution.frozen.json``) to a denied basename or parent
    directory.
    """
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise CollectorError("external_reference_path_rejected")
    if any(
        token in part.lower()
        for part in parts
        for token in _DENIED_REFERENCE_TOKENS
    ):
        raise CollectorError("external_reference_path_rejected")

    basename = parts[-1]
    if role == "journal":
        if not basename.endswith(".journal.jsonl"):
            raise CollectorError("external_reference_role_invalid")
    else:
        expected_name = _EXTERNAL_ROLE_BASENAMES.get(role)
        if expected_name is None or basename != expected_name:
            raise CollectorError("external_reference_role_invalid")


def _external_reference_path(value: Any, role: str) -> Path:
    """Validate a public proof path before any read; reject escape/denial."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise CollectorError("external_reference_path_rejected")
    text = value.strip()
    if (
        not text
        or text.startswith(("/", "\\"))
        or "\\" in text
        or re.match(r"^[A-Za-z]:", text)
    ):
        raise CollectorError("external_reference_path_rejected")
    parts = PurePosixPath(text).parts
    _validate_reference_parts(parts, role)

    candidate = REPO_ROOT.joinpath(*parts)
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        raise CollectorError("external_reference_missing") from None

    # Re-check the *resolved* shape before opening: lexical checks alone cannot
    # see a symlink whose target basename/parent is denied.
    resolved_parts = resolved.parts
    _validate_reference_parts(resolved_parts, role)
    if not resolved.is_file():
        raise CollectorError("external_reference_missing")
    if not any(resolved.is_relative_to(root) for root in _EXTERNAL_REFERENCE_ROOTS):
        raise CollectorError("external_reference_path_rejected")
    return resolved


def _read_reference_bytes(entry: Any, role: str) -> tuple[bytes, Path, str]:
    """Read one hash-pinned public proof artifact after path validation."""
    mapping = _require_mapping(entry, "external_reference_invalid")
    declared = mapping.get("sha256")
    if not _is_sha256_hex(declared):
        raise CollectorError("external_reference_invalid")
    path = _external_reference_path(mapping.get("path"), role)
    try:
        payload = path.read_bytes()
    except OSError:
        raise CollectorError("external_reference_missing") from None
    actual = hashlib.sha256(payload).hexdigest()
    if actual != declared:
        raise CollectorError(
            "external_reference_hash_mismatch", detail={"role": role}
        )
    return payload, path, actual


def _reference_json(payload: bytes, code: str) -> Mapping[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise CollectorError(code) from None
    if not isinstance(value, Mapping):
        raise CollectorError(code)
    return value


def _reference_int(value: Any, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CollectorError(code)
    return value


def _reference_digest(value: Any, code: str) -> str:
    if not _is_sha256_hex(value):
        raise CollectorError(code)
    return value


def _reference_plan() -> list[dict[str, Any]]:
    return [
        {
            "radius_km": cell["radius_km"],
            "arm": cell["arm"],
            "repetition": cell["repetition"],
            "phase": cell["phase"],
        }
        for cell in _timing_plan()
    ]


def _external_reference_binding(reference: Mapping[str, Any]) -> dict[str, Any]:
    """Compact, bounded proof hashes for the new journal header/events."""
    return {
        "protocol": reference.get("protocol"),
        "frozen_manifest": reference.get("frozen_manifest"),
        "journal": {
            key: value
            for key, value in _require_mapping(
                reference.get("journal"), "external_reference_invalid"
            ).items()
            if key in ("path", "sha256", "last_seq", "incomplete_tail")
        },
        "parent_review": {
            key: value
            for key, value in _require_mapping(
                reference.get("parent_review"), "external_reference_invalid"
            ).items()
            if key in ("path", "sha256", "decision", "check_count")
        },
        "archived_sources": reference.get("archived_sources"),
        "accepted_counts": reference.get("accepted_counts"),
        "correctness_reused_not_rerun": True,
    }


def validate_external_correctness_reference(
    manifest: Mapping[str, Any],
    records: Sequence[PoiRecord],
    input_sha256: str,
) -> dict[str, Any]:
    """Fully validate the pinned E2-093 proof before any backend/child.

    The old journal is validated against the *old* manifest/source pins and the
    archived old sources, never against the amended current runner.  A missing,
    forged, failed or incomplete correctness chain is refused.
    """
    mode = resolve_collection_mode(manifest)
    if mode != COLLECTION_MODE_TIMING_ONLY:
        raise CollectorError("external_reference_mode_invalid")
    reference = _require_mapping(
        manifest.get("external_correctness"), "external_correctness_reference_required"
    )
    if reference.get("protocol") != TIMING_ONLY_PROTOCOL:
        raise CollectorError("external_reference_protocol_invalid")

    frozen_payload, frozen_path, frozen_sha = _read_reference_bytes(
        reference.get("frozen_manifest"), "frozen_manifest"
    )
    journal_payload, journal_path, journal_sha = _read_reference_bytes(
        reference.get("journal"), "journal"
    )
    review_payload, review_path, review_sha = _read_reference_bytes(
        reference.get("parent_review"), "parent_review"
    )
    archived = _require_mapping(
        reference.get("archived_sources"), "external_reference_invalid"
    )
    archives: dict[str, dict[str, Any]] = {}
    for name in ("runner", "journal", "supervisor"):
        payload, path, digest = _read_reference_bytes(
            archived.get(name), f"archived_{name}"
        )
        archives[name] = {
            "path": _relative_public_path(path),
            "sha256": digest,
            "bytes": payload,
        }

    old = _reference_json(frozen_payload, "external_manifest_invalid")
    if old.get("schema") != MANIFEST_SCHEMA or old.get("task_id") != TASK_ID:
        raise CollectorError("external_manifest_mismatch")
    if old.get("frozen") is not True:
        raise CollectorError("external_manifest_not_frozen")
    if resolve_collection_mode(old) != COLLECTION_MODE_FULL:
        raise CollectorError("external_manifest_mismatch")
    old_review = _require_mapping(
        old.get("review"), "external_manifest_mismatch"
    )
    if old_review.get("decision") != "approved":
        raise CollectorError("external_manifest_review_required")
    if not isinstance(old_review.get("reviewer"), str) or not old_review[
        "reviewer"
    ].strip():
        raise CollectorError("external_manifest_review_required")
    _require_exact_budget(old)

    old_dataset = _require_mapping(old.get("dataset"), "external_dataset_mismatch")
    computed_full = (
        input_sha256 == DEFAULT_INPUT_SHA256
        and len(records) == DEFAULT_RECORD_COUNT
        and potential_pairs(len(records)) == DEFAULT_POTENTIAL_PAIRS
    )
    if (
        old_dataset.get("sha256") != input_sha256
        or old_dataset.get("records") != len(records)
        or old_dataset.get("potential_pairs") != potential_pairs(len(records))
        or bool(old_dataset.get("is_full_primary")) != computed_full
    ):
        raise CollectorError("external_dataset_mismatch")
    old_scope = _require_mapping(old.get("scope"), "external_dataset_mismatch")
    if old_scope.get("id_coordinate_sha256") != scope_hash(records):
        raise CollectorError("external_dataset_mismatch")
    old_spatial = _require_mapping(old.get("spatial"), "external_spatial_mismatch")
    if old_spatial.get("sha256") != file_sha256(SPATIAL_PATH):
        raise CollectorError("external_spatial_mismatch")
    old_queries = _require_mapping(old.get("queries"), "external_query_mismatch")
    if dict(old_queries) != query_hashes():
        raise CollectorError("external_query_mismatch")
    old_execution = _require_mapping(
        old.get("execution"), "external_manifest_mismatch"
    )
    if (
        old_execution.get("engine_uri") != FIXED_BOLT_URI
        or old_execution.get("auth") != "none"
        or old_execution.get("read_only") is not True
    ):
        raise CollectorError("external_manifest_mismatch")

    descriptor_dataset = _require_mapping(
        reference.get("dataset"), "external_dataset_mismatch"
    )
    if (
        descriptor_dataset.get("sha256") != old_dataset.get("sha256")
        or descriptor_dataset.get("records") != old_dataset.get("records")
        or descriptor_dataset.get("potential_pairs")
        != old_dataset.get("potential_pairs")
        or descriptor_dataset.get("scope_sha256")
        != old_scope.get("id_coordinate_sha256")
        or descriptor_dataset.get("path") != old_dataset.get("path")
    ):
        raise CollectorError("external_dataset_mismatch")
    descriptor_spatial = _require_mapping(
        reference.get("spatial"), "external_spatial_mismatch"
    )
    if (
        descriptor_spatial.get("sha256") != old_spatial.get("sha256")
        or descriptor_spatial.get("path") != old_spatial.get("path")
    ):
        raise CollectorError("external_spatial_mismatch")
    descriptor_queries = _require_mapping(
        reference.get("queries"), "external_query_mismatch"
    )
    if dict(descriptor_queries) != dict(old_queries):
        raise CollectorError("external_query_mismatch")

    old_sources = _require_mapping(old.get("sources"), "external_manifest_mismatch")
    if old_sources.get("protocol") != DURABILITY_PROTOCOL:
        raise CollectorError("external_manifest_mismatch")
    for name in ("runner", "journal", "supervisor"):
        pin = _require_mapping(
            old_sources.get(name), "external_manifest_mismatch"
        )
        if not isinstance(pin.get("path"), str) or not pin["path"]:
            raise CollectorError("external_manifest_mismatch")
        if pin.get("sha256") != archives[name]["sha256"]:
            raise CollectorError(
                "external_source_archive_mismatch", detail={"source": name}
            )
    old_collector = _require_mapping(
        old.get("collector"), "external_manifest_mismatch"
    )
    if old_collector.get("sha256") != archives["runner"]["sha256"]:
        raise CollectorError("external_source_archive_mismatch")

    try:
        read = journal_module.read_journal(journal_path)
    except journal_module.JournalError as exc:
        raise CollectorError(
            "external_journal_invalid", detail={"journal_code": exc.code}
        ) from None
    if read.incomplete_tail:
        raise CollectorError("external_correctness_incomplete")
    if read.binding is None or read.planned is None:
        raise CollectorError("external_journal_invalid")
    binding = dict(read.binding)
    planned = dict(read.planned)
    if (
        binding.get("protocol") != DURABILITY_PROTOCOL
        or binding.get("journal_schema") != journal_module.JOURNAL_SCHEMA
        or binding.get("manifest_schema") != old.get("schema")
        or binding.get("manifest_sha256") != frozen_sha
        or binding.get("input_sha256") != old_dataset.get("sha256")
    ):
        raise CollectorError("external_journal_invalid")
    if dict(binding.get("sources") or {}) != dict(old_sources):
        raise CollectorError("external_journal_foreign_binding")
    expected_batches = batch_ids(sorted(record.id for record in records))
    universe_ids = sorted(record.id for record in records)
    universe_potential = potential_pairs(len(records))
    expected_plan = _reference_plan()
    if (
        planned.get("records") != len(records)
        or planned.get("batches_total") != len(expected_batches)
        or planned.get("potential_pairs") != universe_potential
        or planned.get("batch_size") != BATCH_SIZE
        or planned.get("radii_km") != list(RADII_KM)
        or planned.get("warmups") != WARMUP_RUNS
        or planned.get("measured_repetitions") != MEASURED_REPETITIONS
        or planned.get("timing_cells_total") != TIMING_CELLS_TOTAL
        or planned.get("timing_cells") != expected_plan
    ):
        raise CollectorError("external_journal_invalid")

    events = list(read.events)
    if not events or events[0].get("kind") != "run_start":
        raise CollectorError("external_correctness_incomplete")
    if sum(1 for event in events if event.get("kind") == "run_start") != 1:
        raise CollectorError("external_correctness_incomplete")
    timing_events = [event for event in events if event.get("kind") == "timing_cell"]
    if len(timing_events) > TIMING_CELLS_TOTAL:
        raise CollectorError("external_journal_invalid")
    for index, event in enumerate(timing_events):
        payload = _require_mapping(
            event.get("payload"), "external_journal_invalid"
        )
        expected_cell = expected_plan[index]
        if (
            payload.get("radius_km") != expected_cell["radius_km"]
            or payload.get("arm") != expected_cell["arm"]
            or payload.get("repetition") != expected_cell["repetition"]
            or payload.get("phase") != expected_cell["phase"]
        ):
            raise CollectorError("external_journal_invalid")

    batch_events = [event for event in events if event.get("kind") == "correctness_batch"]
    radius_events = [
        event for event in events if event.get("kind") == "correctness_radius"
    ]
    if len(batch_events) != len(RADII_KM) * len(expected_batches):
        raise CollectorError("external_correctness_incomplete")
    if len(radius_events) != len(RADII_KM):
        raise CollectorError("external_correctness_incomplete")

    receipts: list[dict[str, Any]] = []
    for radius in RADII_KM:
        radius_batches = [
            event
            for event in batch_events
            if isinstance(event.get("payload"), Mapping)
            and event["payload"].get("radius_km") == radius
        ]
        if len(radius_batches) != len(expected_batches):
            raise CollectorError("external_correctness_incomplete")
        baseline_total = 0
        optimized_total = 0
        candidate_total = 0
        potential_total = 0
        for index, event in enumerate(radius_batches):
            payload = _require_mapping(
                event.get("payload"), "external_correctness_invalid"
            )
            if (
                payload.get("index") != index
                or payload.get("status") != "success"
                or payload.get("anchor_count") != len(expected_batches[index])
            ):
                raise CollectorError("external_correctness_incomplete")
            potential = _reference_int(
                payload.get("potential_pairs"), "external_correctness_invalid"
            )
            if potential != _batch_potential(
                universe_ids, expected_batches[index]
            ):
                raise CollectorError("external_correctness_invalid")
            baseline = _reference_int(
                payload.get("baseline_count"), "external_correctness_invalid"
            )
            optimized = _reference_int(
                payload.get("optimized_count"), "external_correctness_invalid"
            )
            candidates = _reference_int(
                payload.get("candidate_pairs"), "external_correctness_invalid"
            )
            if (
                payload.get("false_negatives") != 0
                or payload.get("false_positives") != 0
                or baseline != optimized
                or candidates < optimized
                or candidates > potential
            ):
                raise CollectorError("external_correctness_invalid")
            baseline_digest = _reference_digest(
                payload.get("baseline_digest"), "external_correctness_invalid"
            )
            optimized_digest = _reference_digest(
                payload.get("optimized_digest"), "external_correctness_invalid"
            )
            if baseline_digest != optimized_digest:
                raise CollectorError("external_correctness_invalid")
            baseline_total += baseline
            optimized_total += optimized
            candidate_total += candidates
            potential_total += potential

        receipt = _require_mapping(
            radius_events[list(RADII_KM).index(radius)].get("payload"),
            "external_correctness_invalid",
        )
        if (
            receipt.get("radius_km") != radius
            or receipt.get("status") != "passed"
            or receipt.get("passed") is not True
            or receipt.get("accepted_sets_equal") is not True
            or receipt.get("false_negatives") != 0
            or receipt.get("false_positives") != 0
            or receipt.get("missing_batches") != []
            or receipt.get("error") is not None
            or receipt.get("batches_completed") != len(expected_batches)
            or receipt.get("potential_pairs_observed") != potential_total
            or receipt.get("baseline_accepted_pairs") != baseline_total
            or receipt.get("optimized_accepted_pairs") != optimized_total
            or receipt.get("candidate_pairs") != candidate_total
        ):
            raise CollectorError("external_correctness_invalid")
        if potential_total != universe_potential:
            raise CollectorError("external_correctness_invalid")
        if (
            candidate_total < optimized_total
            or candidate_total > potential_total
            or baseline_total != optimized_total
        ):
            raise CollectorError("external_correctness_invalid")
        baseline_digest = _reference_digest(
            receipt.get("baseline_pair_digest"), "external_correctness_invalid"
        )
        optimized_digest = _reference_digest(
            receipt.get("optimized_pair_digest"), "external_correctness_invalid"
        )
        if baseline_digest != optimized_digest:
            raise CollectorError("external_correctness_invalid")
        receipts.append(
            {
                "radius_km": radius,
                "status": "passed",
                "batches_completed": len(expected_batches),
                "potential_pairs": potential_total,
                "candidate_pairs": candidate_total,
                "accepted_pairs": baseline_total,
                "baseline_accepted_pairs": baseline_total,
                "optimized_accepted_pairs": optimized_total,
                "false_negatives": 0,
                "false_positives": 0,
                "baseline_pair_digest": baseline_digest,
                "optimized_pair_digest": optimized_digest,
                "accepted_sets_equal": True,
            }
        )

    try:
        if file_sha256(journal_path) != journal_sha:
            raise CollectorError("external_reference_hash_mismatch")
    except OSError:
        raise CollectorError("external_reference_missing") from None

    review = _reference_json(review_payload, "external_review_invalid")
    if not isinstance(review.get("decision"), str) or not review[
        "decision"
    ].startswith("ACCEPTED"):
        raise CollectorError("external_review_invalid")
    checks = review.get("checks")
    check_count = review.get("check_count")
    if (
        not isinstance(checks, list)
        or isinstance(check_count, bool)
        or not isinstance(check_count, int)
        or check_count < 1
        or check_count != len(checks)
    ):
        raise CollectorError("external_review_invalid")
    if review.get("journal_incomplete_tail") is not False:
        raise CollectorError("external_review_invalid")
    review_events = _require_mapping(
        review.get("journal_events"), "external_review_invalid"
    )
    if (
        review_events.get("correctness_batch") != len(batch_events)
        or review_events.get("correctness_radius") != len(radius_events)
    ):
        raise CollectorError("external_review_invalid")
    if (
        review.get("correctness_radii_planned") != list(RADII_KM)
        or review.get("correctness_radii_passed") != len(RADII_KM)
    ):
        raise CollectorError("external_review_invalid")
    review_correctness = review.get("correctness")
    if not isinstance(review_correctness, list) or len(review_correctness) != len(
        RADII_KM
    ):
        raise CollectorError("external_review_invalid")
    for radius, receipt, review_item in zip(RADII_KM, receipts, review_correctness):
        item = _require_mapping(review_item, "external_review_invalid")
        if (
            item.get("radius_km") != radius
            or item.get("passed") is not True
            or item.get("status") != "passed"
            or item.get("accepted_sets_equal") is not True
            or item.get("false_negatives") != 0
            or item.get("false_positives") != 0
            or item.get("baseline_accepted_pairs")
            != receipt["baseline_accepted_pairs"]
            or item.get("optimized_accepted_pairs")
            != receipt["optimized_accepted_pairs"]
            or item.get("candidate_pairs") != receipt["candidate_pairs"]
            or item.get("potential_pairs_observed") != receipt["potential_pairs"]
            or item.get("baseline_pair_digest") != receipt["baseline_pair_digest"]
            or item.get("optimized_pair_digest")
            != receipt["optimized_pair_digest"]
        ):
            raise CollectorError("external_review_invalid")
    evidence_hashes = _require_mapping(
        review.get("evidence_hashes"), "external_review_invalid"
    )
    frozen_relative = _relative_public_path(frozen_path)
    journal_relative = _relative_public_path(journal_path)
    if (
        evidence_hashes.get(frozen_relative) != frozen_sha
        or evidence_hashes.get(journal_relative) != journal_sha
    ):
        raise CollectorError("external_review_invalid")

    accepted_counts = {
        str(radius): {
            "baseline": receipts[index]["baseline_accepted_pairs"],
            "optimized": receipts[index]["optimized_accepted_pairs"],
        }
        for index, radius in enumerate(RADII_KM)
    }
    return {
        "schema": EXTERNAL_CORRECTNESS_SCHEMA,
        "protocol": TIMING_ONLY_PROTOCOL,
        "status": "validated",
        "correctness_reused_not_rerun": True,
        "correctness_rerun_in_new_cohort": False,
        "planned_correctness_queries": 0,
        "reference_radii": list(RADII_KM),
        "accepted_counts": accepted_counts,
        "radii": receipts,
        "frozen_manifest": {
            "path": _relative_public_path(frozen_path),
            "sha256": frozen_sha,
        },
        "journal": {
            "path": _relative_public_path(journal_path),
            "sha256": journal_sha,
            "last_seq": read.last_seq,
            "incomplete_tail": False,
            "correctness_batch_receipts": len(batch_events),
            "correctness_radius_receipts": len(radius_events),
            "timing_cell_receipts": len(timing_events),
        },
        "parent_review": {
            "path": _relative_public_path(review_path),
            "sha256": review_sha,
            "decision": review.get("decision"),
            "check_count": check_count,
        },
        "archived_sources": {
            name: {
                "path": archives[name]["path"],
                "sha256": archives[name]["sha256"],
            }
            for name in ("runner", "journal", "supervisor")
        },
        "dataset": dict(descriptor_dataset),
        "spatial": dict(descriptor_spatial),
        "queries": dict(descriptor_queries),
        "old_source_pins": dict(old_sources),
        "old_collector_sha256": old_collector.get("sha256"),
        "metric": "engine_defined_point_distance",
        "python_haversine_reference_substitution": False,
        "note": (
            "E2-093 correctness is reused as pinned external evidence; the new "
            "cohort runs a fresh projection and only the 36 timing cells."
        ),
    }



def build_dry_run_plan(
    records: Sequence[PoiRecord],
    input_path: Path | str,
    input_sha256: str,
    manifest: Mapping[str, Any] | None,
    *,
    now: datetime,
) -> dict[str, Any]:
    count = len(records)
    records_by_batch = batch_ids([record.id for record in records])
    candidate_mode = (
        resolve_collection_mode(manifest)
        if manifest is not None
        else COLLECTION_MODE_FULL
    )
    candidate_reference: Mapping[str, Any] | None = None
    if candidate_mode == COLLECTION_MODE_TIMING_ONLY and isinstance(
        manifest, Mapping
    ):
        candidate_reference = _require_mapping(
            manifest.get("external_correctness"),
            "external_correctness_reference_required",
        )
    candidate_manifest = build_manifest(
        records,
        input_path,
        input_sha256=input_sha256,
        collection_mode=candidate_mode,
        external_correctness=candidate_reference,
    )
    execution_ready = False
    manifest_summary: Mapping[str, Any] | None = None
    if manifest is not None:
        validate_manifest(
            manifest,
            records,
            input_path,
            input_sha256,
            require_frozen=False,
        )
        manifest_summary = {
            "schema": manifest.get("schema"),
            "frozen": manifest.get("frozen"),
            "review": manifest.get("review"),
        }
        execution_ready = (
            manifest.get("frozen") is True
            and isinstance(manifest.get("review"), Mapping)
            and manifest["review"].get("decision") == "approved"
            and isinstance(manifest["review"].get("reviewer"), str)
            and bool(manifest["review"]["reviewer"].strip())
        )
    return {
        "schema": PLAN_SCHEMA,
        "task_id": TASK_ID,
        "status": "dry_run_plan",
        "mode": "dry_run",
        "plan_only": True,
        "scientific_result": False,
        "latency_measured": False,
        "generated_at": _utc_iso(now),
        "input": {
            "path": _relative_public_path(Path(input_path)),
            "sha256": input_sha256,
            "records": count,
            "is_full_primary": input_sha256 == DEFAULT_INPUT_SHA256
            and count == DEFAULT_RECORD_COUNT,
        },
        "manifest": manifest_summary,
        "candidate_manifest": candidate_manifest,
        "execution_ready": execution_ready,
        "planned": {
            "collection_mode": candidate_mode,
            "radii_km": list(RADII_KM),
            "batch_size": BATCH_SIZE,
            "batches": len(records_by_batch),
            "potential_pairs": potential_pairs(count),
            "warmups_per_radius_arm": WARMUP_RUNS,
            "measured_repetitions_per_radius_arm": MEASURED_REPETITIONS,
            "timing_cells_total": TIMING_CELLS_TOTAL,
            "timing_plan": TIMING_PLANNED_LABEL,
            "correctness_queries": (
                0 if candidate_mode == COLLECTION_MODE_TIMING_ONLY else len(RADII_KM)
            ),
            "external_correctness_radii": (
                len(RADII_KM)
                if candidate_mode == COLLECTION_MODE_TIMING_ONLY
                else 0
            ),
            "engine_uri": FIXED_BOLT_URI,
        },
        "queries": {
            "hashes": query_hashes(),
            "allowlist": sorted(QUERY_TEXTS),
            "read_only_templates": True,
        },
        "labels": {
            "candidate_counts": "logical prefilter predicate/input counts",
            "scientific_result": False,
            "timing_workload": (
                "count-only aggregate over the same predicates; end-to-end latency "
                "does not include transferring every accepted pair row"
            ),
            "source_areas": "dataset labels, not current administrative containment",
            "dry_run": "plan only; no engine, latency or correctness result",
        },
        "limitations": _limitations(),
        "model_calls": 0,
        "graph_mutation": False,
    }


def _limitations() -> list[str]:
    return [
        "Read-only canonical queries do not prove stored NEAR_BY relationship "
        "orientation, duplicate or stale-update semantics; DATA068 is separate evidence.",
        "Source-area labels are dataset labels, not verified current administrative "
        "containment.",
        "Candidate counts are logical prefilter predicate/input counts, not physically "
        "instrumented engine evaluation counts.",
        "Timing cells run a fixed count-only aggregate; they measure end-to-end "
        "execution of a one-row count, not transfer of every accepted pair row.",
        "An explicit driver authorization/permission denial is terminal and stops "
        "all further engine queries; generic metadata errors remain explicit gaps.",
        "No latency improvement or subquadratic complexity claim is made.",
        "Offline fake-backend tests are synthetic engineering evidence, not a live "
        "Memgraph measurement.",
    ]


# ---------------------------------------------------------------------------
# Engine seam
# ---------------------------------------------------------------------------


class EngineBackend(Protocol):
    def run_query(
        self,
        name: str,
        text: str,
        params: Mapping[str, Any],
        timeout_seconds: float,
    ) -> list[dict[str, Any]]: ...

    def close(self) -> None: ...


def _load_neo4j() -> Any:
    """Lazy actual driver import; only reached by explicit live execution."""
    import neo4j  # type: ignore[import-not-found]

    return neo4j


class Neo4jBackend:
    """Fixed loopback-only Neo4j driver wrapper.

    The constructor performs no network I/O.  The driver is created lazily on
    the first query, after all manifest and projection gates have passed.
    """

    def __init__(self) -> None:
        self._driver: Any | None = None
        self._session: Any | None = None
        self._closed = False

    def _connect(self) -> None:
        if self._closed:
            raise CollectorError("engine_closed")
        if self._driver is not None:
            return
        neo4j = _load_neo4j()
        self._driver = neo4j.GraphDatabase.driver(
            FIXED_BOLT_URI,
            auth=None,
            connection_timeout=5,
            max_transaction_retry_time=0,
        )
        self._session = self._driver.session()

    def run_query(
        self,
        name: str,
        text: str,
        params: Mapping[str, Any],
        timeout_seconds: float,
    ) -> list[dict[str, Any]]:
        assert_allowed_query(text)
        self._connect()
        assert self._session is not None
        neo4j = _load_neo4j()
        result = self._session.run(
            neo4j.Query(text, timeout=timeout_seconds),
            dict(params),
        )
        return [dict(record) for record in result]

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        session, driver = self._session, self._driver
        self._session = None
        self._driver = None
        try:
            if session is not None:
                session.close()
        finally:
            if driver is not None:
                driver.close()


def _engine_query(
    backend: EngineBackend,
    name: str,
    text: str,
    params: Mapping[str, Any],
    *,
    clock: Callable[[], float],
    run_started: float,
    run_timeout_seconds: float,
    query_timeout_seconds: float = QUERY_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    assert_allowed_query(text)
    remaining = run_timeout_seconds - (clock() - run_started)
    if remaining <= 0:
        raise CollectorError("run_timeout")
    effective_timeout = min(query_timeout_seconds, remaining)
    try:
        rows = backend.run_query(name, text, params, effective_timeout)
    except Exception as exc:  # closed, sanitized classification
        classified = classify_engine_exception(exc)
        if classified is exc:
            raise
        raise classified from None
    if not isinstance(rows, list):
        raise CollectorError("engine_response_invalid")
    return rows


# ---------------------------------------------------------------------------
# Projection gate
# ---------------------------------------------------------------------------


def verify_projection(
    records: Sequence[PoiRecord],
    backend: EngineBackend,
    *,
    clock: Callable[[], float],
    run_started: float,
    run_timeout_seconds: float,
) -> dict[str, Any]:
    """Compare every source ID/coordinate/binding to the scoped graph projection."""
    records_by_id = {record.id: record for record in records}
    ids = sorted(records_by_id)
    rows: list[Mapping[str, Any]] = []
    for anchor_batch in batch_ids(ids):
        batch_rows = _engine_query(
            backend,
            "projection",
            PROJECTION_QUERY,
            {"ids": anchor_batch},
            clock=clock,
            run_started=run_started,
            run_timeout_seconds=run_timeout_seconds,
        )
        for row in batch_rows:
            if not isinstance(row, Mapping):
                raise CollectorError("projection_row_invalid")
            rows.append(row)

    seen: set[str] = set()
    duplicates: list[str] = []
    extras: list[str] = []
    coordinate_mismatches: list[str] = []
    binding_mismatches: list[str] = []
    nonfinite: list[str] = []
    for row in rows:
        poi_id = row.get("id")
        if not isinstance(poi_id, str) or not poi_id:
            raise CollectorError("projection_id_invalid")
        if poi_id in seen:
            duplicates.append(poi_id)
            continue
        seen.add(poi_id)
        record = records_by_id.get(poi_id)
        if record is None:
            extras.append(poi_id)
            continue
        latitude = row.get("latitude")
        longitude = row.get("longitude")
        if (
            isinstance(latitude, bool)
            or isinstance(longitude, bool)
            or not isinstance(latitude, (int, float))
            or not isinstance(longitude, (int, float))
        ):
            raise CollectorError("projection_coordinate_invalid", detail={"id": poi_id})
        if not math.isfinite(float(latitude)) or not math.isfinite(float(longitude)):
            nonfinite.append(poi_id)
            continue
        if float(latitude) != record.latitude or float(longitude) != record.longitude:
            coordinate_mismatches.append(poi_id)
        if (
            row.get("source_area_id") != record.source_area_id
            or row.get("input_sha256") != record.source_metadata.get("input_sha256")
            or row.get("dataset_namespace")
            != record.source_metadata.get("dataset_namespace")
            or row.get("metadata_sha256") != record.metadata_sha256
        ):
            binding_mismatches.append(poi_id)

    missing = sorted(set(records_by_id) - seen)
    extra_rows = sorted(set(extras) | set(duplicates))
    if missing or extra_rows or coordinate_mismatches or binding_mismatches or nonfinite:
        raise CollectorError(
            "graph_projection_mismatch",
            detail={
                "expected_records": len(records_by_id),
                "matched_records": len(seen),
                "missing_count": len(missing),
                "missing_sample": missing[:MAX_MISMATCH_SAMPLES],
                "extra_or_duplicate_count": len(extra_rows),
                "extra_or_duplicate_sample": extra_rows[:MAX_MISMATCH_SAMPLES],
                "coordinate_mismatch_count": len(coordinate_mismatches),
                "coordinate_mismatch_sample": coordinate_mismatches[:MAX_MISMATCH_SAMPLES],
                "binding_mismatch_count": len(binding_mismatches),
                "binding_mismatch_sample": binding_mismatches[:MAX_MISMATCH_SAMPLES],
                "nonfinite_count": len(nonfinite),
                "nonfinite_sample": nonfinite[:MAX_MISMATCH_SAMPLES],
            },
        )

    out_rows = _engine_query(
        backend,
        "out_of_universe",
        OUT_OF_UNIVERSE_QUERY,
        {"ids": ids},
        clock=clock,
        run_started=run_started,
        run_timeout_seconds=run_timeout_seconds,
    )
    extra_poi_count = _one_integer(out_rows, "extra_poi_count", "projection_extra_invalid")
    if extra_poi_count != 0:
        raise CollectorError(
            "graph_projection_extra_poi",
            detail={"extra_poi_count": extra_poi_count},
        )

    count_rows = _engine_query(
        backend,
        "scoped_counts",
        SCOPED_COUNTS_QUERY,
        {"ids": ids},
        clock=clock,
        run_started=run_started,
        run_timeout_seconds=run_timeout_seconds,
    )
    if len(count_rows) != 1:
        raise CollectorError("scoped_counts_invalid")
    scoped_counts = dict(count_rows[0])
    if scoped_counts.get("poi_count") != len(records_by_id) or scoped_counts.get(
        "distinct_poi_ids"
    ) != len(records_by_id):
        raise CollectorError(
            "scoped_counts_mismatch",
            detail={
                "poi_count": scoped_counts.get("poi_count"),
                "distinct_poi_ids": scoped_counts.get("distinct_poi_ids"),
            },
        )

    materialization_rows = _engine_query(
        backend,
        "materialization",
        MATERIALIZATION_QUERY,
        {"ids": ids},
        clock=clock,
        run_started=run_started,
        run_timeout_seconds=run_timeout_seconds,
    )
    if len(materialization_rows) != 1:
        raise CollectorError("materialization_metadata_invalid")
    materialization = dict(materialization_rows[0])

    index_info: dict[str, Any]
    try:
        index_rows = _engine_query(
            backend,
            "index_info",
            INDEX_INFO_QUERY,
            {},
            clock=clock,
            run_started=run_started,
            run_timeout_seconds=run_timeout_seconds,
        )
        index_info = {
            "status": "captured",
            "row_count": len(index_rows),
            "rows": _public_detail(index_rows),
        }
    except CollectorError as exc:
        if exc.code == "run_timeout" or is_engine_auth_denied(exc):
            raise
        index_info = {
            "status": "unsupported_or_unavailable",
            "error": exc.as_dict(),
            "note": "explicit metadata gap; no alternate command is attempted",
        }

    return {
        "status": "passed",
        "expected_records": len(records_by_id),
        "matched_records": len(seen),
        "missing_records": 0,
        "extra_or_duplicate_records": 0,
        "coordinate_mismatches": 0,
        "binding_mismatches": 0,
        "nonfinite_coordinates": 0,
        "source_binding": "id + coordinate + source-area + metadata hash matched",
        "out_of_universe_poi_count": extra_poi_count,
        "scoped_counts": scoped_counts,
        "materialization": {
            **materialization,
            "note": (
                "fixed directed NEAR_BY materialization metadata only; separate from "
                "canonical read-only query correctness and not a stale/update proof"
            ),
        },
        "index_info": index_info,
        "administrative_binding": "source_snapshot_area_only_not_current_admin",
    }


def _one_integer(rows: Sequence[Mapping[str, Any]], key: str, code: str) -> int:
    if len(rows) != 1:
        raise CollectorError(code)
    value = rows[0].get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CollectorError(code)
    return value


# ---------------------------------------------------------------------------
# Pair parsing and correctness
# ---------------------------------------------------------------------------


def parse_pair_rows(
    rows: Sequence[Mapping[str, Any]],
    universe: set[str],
    radius_km: float,
    *,
    anchors: set[str] | None = None,
) -> set[tuple[str, str]]:
    """Validate and canonicalize one batch of accepted pair rows."""
    accepted: set[tuple[str, str]] = set()
    limit_meters = radius_km * 1000.0
    for row in rows:
        if not isinstance(row, Mapping):
            raise CollectorError("pair_row_invalid")
        a_id = row.get("a_id")
        b_id = row.get("b_id")
        distance = row.get("distance_m")
        if not isinstance(a_id, str) or not isinstance(b_id, str) or not a_id or not b_id:
            raise CollectorError("pair_endpoint_invalid")
        if a_id == b_id:
            raise CollectorError("pair_self_rejected")
        if a_id > b_id:
            raise CollectorError("pair_not_canonical")
        if a_id not in universe or b_id not in universe:
            raise CollectorError("pair_out_of_universe")
        if anchors is not None and a_id not in anchors:
            raise CollectorError("pair_anchor_mismatch")
        if isinstance(distance, bool) or not isinstance(distance, (int, float)):
            raise CollectorError("pair_distance_invalid")
        distance_value = float(distance)
        if not math.isfinite(distance_value):
            raise CollectorError("pair_distance_nonfinite")
        if distance_value < 0.0 or distance_value > limit_meters + 1e-9:
            raise CollectorError("pair_distance_out_of_radius")
        pair = (a_id, b_id)
        if pair in accepted:
            raise CollectorError("duplicate_pair")
        accepted.add(pair)
    return accepted


def _batch_potential(universe: Sequence[str], anchors: Sequence[str]) -> int:
    positions = {poi_id: index for index, poi_id in enumerate(universe)}
    total = 0
    for anchor in anchors:
        total += len(universe) - 1 - positions[anchor]
    return total


def collect_correctness(
    records: Sequence[PoiRecord],
    radius_km: float,
    backend: EngineBackend,
    *,
    clock: Callable[[], float],
    run_started: float,
    run_timeout_seconds: float,
    on_utc: Callable[[], datetime],
    on_event: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """One correctness pass for one radius, comparing actual accepted sets in RAM."""
    universe_list = sorted(record.id for record in records)
    universe = set(universe_list)
    anchors_batches = batch_ids(universe_list)
    parameters_base = {
        "ids": universe_list,
        "radius_km": radius_km,
        "earth_radius_lower_bound_km": EARTH_RADIUS_KM_LOWER_BOUND,
    }

    batch_records: list[dict[str, Any]] = []
    baseline_digest = hashlib.sha256()
    optimized_digest = hashlib.sha256()
    potential_total = 0
    candidate_total = 0
    baseline_total = 0
    optimized_total = 0
    false_negatives_total = 0
    false_positives_total = 0
    mismatch_samples: list[dict[str, Any]] = []
    missing_batches: list[int] = []
    complete = True
    failure: CollectorError | None = None

    for index, anchor_batch in enumerate(anchors_batches):
        batch_potential = _batch_potential(universe_list, anchor_batch)
        potential_total += batch_potential
        if failure is not None:
            missing_batches.append(index)
            batch_records.append(_missing_batch(index, anchor_batch, batch_potential))
            continue
        params = dict(parameters_base)
        params["anchors"] = anchor_batch
        try:
            baseline_rows = _engine_query(
                backend,
                "baseline",
                BASELINE_QUERY,
                params,
                clock=clock,
                run_started=run_started,
                run_timeout_seconds=run_timeout_seconds,
            )
            optimized_rows = _engine_query(
                backend,
                "optimized",
                OPTIMIZED_QUERY,
                params,
                clock=clock,
                run_started=run_started,
                run_timeout_seconds=run_timeout_seconds,
            )
            candidate_rows = _engine_query(
                backend,
                "candidates",
                CANDIDATE_COUNT_QUERY,
                params,
                clock=clock,
                run_started=run_started,
                run_timeout_seconds=run_timeout_seconds,
            )
            baseline_set = parse_pair_rows(
                baseline_rows, universe, radius_km, anchors=set(anchor_batch)
            )
            optimized_set = parse_pair_rows(
                optimized_rows, universe, radius_km, anchors=set(anchor_batch)
            )
            candidates = _one_integer(
                candidate_rows, "candidate_pairs", "candidate_count_invalid"
            )
            if candidates < len(optimized_set):
                raise CollectorError("candidate_less_than_accepted")
            if candidates > batch_potential:
                raise CollectorError("candidate_exceeds_potential")

            fn_set = baseline_set - optimized_set
            fp_set = optimized_set - baseline_set
            false_negatives_total += len(fn_set)
            false_positives_total += len(fp_set)
            baseline_total += len(baseline_set)
            optimized_total += len(optimized_set)
            candidate_total += candidates
            for pair in sorted(baseline_set):
                _feed_pair(baseline_digest, pair[0], pair[1])
            for pair in sorted(optimized_set):
                _feed_pair(optimized_digest, pair[0], pair[1])
            for pair in sorted(fn_set):
                _add_mismatch(mismatch_samples, "false_negative", pair)
            for pair in sorted(fp_set):
                _add_mismatch(mismatch_samples, "false_positive", pair)
            batch_record = {
                "index": index,
                "anchor_count": len(anchor_batch),
                "potential_pairs": batch_potential,
                "status": "success",
                "baseline_count": len(baseline_set),
                "optimized_count": len(optimized_set),
                "candidate_pairs": candidates,
                "false_negatives": len(fn_set),
                "false_positives": len(fp_set),
                "baseline_digest": canonical_pairs_digest(baseline_set),
                "optimized_digest": canonical_pairs_digest(optimized_set),
            }
            batch_records.append(batch_record)
            _emit(
                on_event,
                "correctness_batch",
                {"radius_km": radius_km, **batch_record},
            )
        except CollectorError as exc:
            complete = False
            failure = exc
            missing_batches.append(index)
            batch_record = {
                **_missing_batch(index, anchor_batch, batch_potential),
                "status": "error",
                "error": exc.as_dict(),
            }
            batch_records.append(batch_record)
            _emit(
                on_event,
                "correctness_batch",
                {"radius_km": radius_km, **batch_record},
            )

    if complete:
        baseline_digest_value: str | None = baseline_digest.hexdigest()
        optimized_digest_value: str | None = optimized_digest.hexdigest()
        candidate_value: int | None = candidate_total
        baseline_value: int | None = baseline_total
        optimized_value: int | None = optimized_total
        fn_value: int | None = false_negatives_total
        fp_value: int | None = false_positives_total
    else:
        baseline_digest_value = None
        optimized_digest_value = None
        candidate_value = None
        baseline_value = None
        optimized_value = None
        fn_value = None
        fp_value = None

    accepted_equal = (
        complete
        and baseline_value == optimized_value
        and fn_value == 0
        and fp_value == 0
        and baseline_digest_value == optimized_digest_value
    )
    passed = bool(
        accepted_equal
        and complete
        and candidate_value is not None
        and candidate_value <= potential_total
    )
    result = {
        "radius_km": radius_km,
        "status": "passed" if passed else ("failed_correctness" if complete else "incomplete"),
        "potential_pairs": potential_pairs(len(universe_list)),
        "potential_pairs_observed": potential_total,
        "logical_distance_inputs_reference": potential_pairs(len(universe_list)),
        "logical_distance_inputs_optimized": candidate_value,
        "logical_distance_inputs_optimized_observed": candidate_total if not complete else None,
        "physical_engine_evaluation_counts": None,
        "count_labels": {
            "reference": "logical inputs = full unordered potential pairs",
            "optimized": "logical inputs = prefilter candidate pair count",
            "not_physical": "not physically instrumented engine evaluation counts",
        },
        "candidate_pairs": candidate_value,
        "candidate_pairs_observed": candidate_total,
        "baseline_accepted_pairs": baseline_value,
        "baseline_accepted_pairs_observed": baseline_total,
        "optimized_accepted_pairs": optimized_value,
        "optimized_accepted_pairs_observed": optimized_total,
        "false_negatives": fn_value,
        "false_positives": fp_value,
        "baseline_pair_digest": baseline_digest_value,
        "optimized_pair_digest": optimized_digest_value,
        "accepted_sets_equal": accepted_equal,
        "pruning_percent": pruning_percent(potential_total, candidate_value),
        "mismatch_samples": mismatch_samples,
        "batches": batch_records,
        "missing_batches": missing_batches,
        "passed": passed,
        "utc_started": _utc_iso(on_utc()),
    }
    if failure is not None:
        result["error"] = failure.as_dict()
    _emit(
        on_event,
        "correctness_radius",
        {
            "radius_km": radius_km,
            "status": result["status"],
            "passed": passed,
            "potential_pairs_observed": potential_total,
            "candidate_pairs": candidate_value,
            "baseline_accepted_pairs": baseline_value,
            "optimized_accepted_pairs": optimized_value,
            "false_negatives": fn_value,
            "false_positives": fp_value,
            "baseline_pair_digest": baseline_digest_value,
            "optimized_pair_digest": optimized_digest_value,
            "accepted_sets_equal": accepted_equal,
            "batches_completed": sum(
                1 for batch in batch_records if batch["status"] == "success"
            ),
            "missing_batches": list(missing_batches),
            "error": failure.as_dict() if failure is not None else None,
            "utc": result["utc_started"],
        },
    )
    return result


def _add_mismatch(
    samples: list[dict[str, Any]], kind: str, pair: tuple[str, str]
) -> None:
    if len(samples) >= MAX_MISMATCH_SAMPLES:
        return
    samples.append({"type": kind, "a_id": pair[0], "b_id": pair[1]})


def _missing_batch(index: int, anchors: Sequence[str], potential: int) -> dict[str, Any]:
    return {
        "index": index,
        "anchor_count": len(anchors),
        "potential_pairs": potential,
        "status": "missing",
        "baseline_count": None,
        "optimized_count": None,
        "candidate_pairs": None,
        "false_negatives": None,
        "false_positives": None,
        "baseline_digest": None,
        "optimized_digest": None,
    }


def _missing_correctness(
    records: Sequence[PoiRecord],
    radius_km: float,
    *,
    reason: str,
    now: datetime,
    error: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Explicit denominator-bearing record for a radius never attempted."""
    universe_list = sorted(record.id for record in records)
    batches = batch_ids(universe_list)
    batch_records: list[dict[str, Any]] = []
    potential_total = 0
    for index, anchor_batch in enumerate(batches):
        batch_potential = _batch_potential(universe_list, anchor_batch)
        potential_total += batch_potential
        batch_records.append(_missing_batch(index, anchor_batch, batch_potential))
    result: dict[str, Any] = {
        "radius_km": radius_km,
        "status": "incomplete",
        "potential_pairs": potential_pairs(len(universe_list)),
        "potential_pairs_observed": potential_total,
        "logical_distance_inputs_reference": potential_pairs(len(universe_list)),
        "logical_distance_inputs_optimized": None,
        "logical_distance_inputs_optimized_observed": None,
        "physical_engine_evaluation_counts": None,
        "count_labels": {
            "reference": "logical inputs = full unordered potential pairs",
            "optimized": "logical inputs = prefilter candidate pair count",
            "not_physical": "not physically instrumented engine evaluation counts",
        },
        "candidate_pairs": None,
        "candidate_pairs_observed": None,
        "baseline_accepted_pairs": None,
        "baseline_accepted_pairs_observed": None,
        "optimized_accepted_pairs": None,
        "optimized_accepted_pairs_observed": None,
        "false_negatives": None,
        "false_positives": None,
        "baseline_pair_digest": None,
        "optimized_pair_digest": None,
        "accepted_sets_equal": False,
        "pruning_percent": None,
        "mismatch_samples": [],
        "batches": batch_records,
        "missing_batches": list(range(len(batch_records))),
        "passed": False,
        "reason": reason,
        "utc_started": _utc_iso(now),
    }
    if error is not None:
        result["error"] = dict(error)
    return result


# ---------------------------------------------------------------------------
# Timings
# ---------------------------------------------------------------------------


def _timing_plan() -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for radius in RADII_KM:
        for repetition in range(WARMUP_RUNS + MEASURED_REPETITIONS):
            order = (
                ("baseline", "optimized")
                if repetition % 2 == 0
                else ("optimized", "baseline")
            )
            for arm in order:
                plan.append(
                    {
                        "radius_km": radius,
                        "arm": arm,
                        "repetition": repetition,
                        "phase": "warmup" if repetition == 0 else "measured",
                        "arm_order": list(order),
                    }
                )
    return plan


_TIMING_QUERY_NAMES = {
    "baseline": "timing_baseline",
    "optimized": "timing_optimized",
}


def _timing_accepted_count(
    rows: Sequence[Mapping[str, Any]], batch_potential: int
) -> int:
    """Validate one fully-consumed count-only timing result.

    The returned value is the server aggregate, never ``len(rows)``.  A
    missing, multi-row, boolean, negative or over-potential value is a failed
    cell, not a fabricated zero.
    """
    if len(rows) != 1:
        raise CollectorError("timing_count_row_count_invalid")
    row = rows[0]
    if not isinstance(row, Mapping):
        raise CollectorError("timing_count_invalid")
    value = row.get("accepted_pairs")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CollectorError("timing_count_invalid")
    if value > batch_potential:
        raise CollectorError(
            "timing_count_exceeds_potential",
            detail={"accepted_pairs": value, "batch_potential": batch_potential},
        )
    return value


def _run_timing_cell(
    records: Sequence[PoiRecord],
    cell: Mapping[str, Any],
    backend: EngineBackend,
    *,
    clock: Callable[[], float],
    run_started: float,
    run_timeout_seconds: float,
    on_utc: Callable[[], datetime],
    expected_accepted: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    universe_list = sorted(record.id for record in records)
    radius = float(cell["radius_km"])
    arm = str(cell["arm"])
    query_name = _TIMING_QUERY_NAMES[arm]
    query_text = QUERY_TEXTS[query_name]
    start = clock()
    start_utc = on_utc()
    batch_trace: list[dict[str, Any]] = []
    total = 0
    failure: CollectorError | None = None
    for index, anchor_batch in enumerate(batch_ids(universe_list)):
        batch_potential = _batch_potential(universe_list, anchor_batch)
        if failure is not None:
            batch_trace.append(
                {
                    "index": index,
                    "potential_pairs": batch_potential,
                    "status": "missing",
                    "accepted_pairs": None,
                    "returned_count": None,
                }
            )
            continue
        try:
            rows = _engine_query(
                backend,
                query_name,
                query_text,
                {
                    "anchors": anchor_batch,
                    "ids": universe_list,
                    "radius_km": radius,
                    "earth_radius_lower_bound_km": EARTH_RADIUS_KM_LOWER_BOUND,
                },
                clock=clock,
                run_started=run_started,
                run_timeout_seconds=run_timeout_seconds,
            )
            accepted = _timing_accepted_count(rows, batch_potential)
            total += accepted
            batch_trace.append(
                {
                    "index": index,
                    "potential_pairs": batch_potential,
                    "status": "success",
                    "accepted_pairs": accepted,
                    "returned_count": accepted,
                }
            )
        except CollectorError as exc:
            failure = exc
            batch_trace.append(
                {
                    "index": index,
                    "potential_pairs": batch_potential,
                    "status": "error",
                    "accepted_pairs": None,
                    "returned_count": None,
                    "error": exc.as_dict(),
                }
            )
    end = clock()
    end_utc = on_utc()
    reference_expected: int | None = None
    if expected_accepted is not None:
        try:
            arm_counts = _require_mapping(
                expected_accepted.get(str(radius)), "external_reference_incomplete"
            )
            reference_expected = _reference_int(
                arm_counts.get(arm), "external_reference_incomplete"
            )
        except CollectorError as exc:
            if failure is None:
                failure = exc
        if failure is None and total != reference_expected:
            failure = CollectorError(
                "timing_reference_count_mismatch",
                detail={"expected": reference_expected, "observed": total},
            )
    result: dict[str, Any] = {
        "radius_km": radius,
        "arm": arm,
        "repetition": int(cell["repetition"]),
        "phase": cell["phase"],
        "arm_order": list(cell["arm_order"]),
        "planned": True,
        "query": query_name,
        "count_only": True,
        "status": "success" if failure is None else "error",
        "monotonic_start": start,
        "monotonic_end": end,
        "duration_seconds": end - start,
        "utc_start": _utc_iso(start_utc),
        "utc_end": _utc_iso(end_utc),
        "accepted_pairs": total if failure is None else None,
        "accepted_pairs_observed": total,
        "returned_count": total if failure is None else None,
        "returned_count_observed": total,
        "reference_accepted_pairs": reference_expected,
        "batches": batch_trace,
    }
    if failure is not None:
        result["error"] = failure.as_dict()
    return result


def _missing_timing_cell(cell: Mapping[str, Any], reason: str) -> dict[str, Any]:
    arm = str(cell["arm"])
    return {
        "radius_km": float(cell["radius_km"]),
        "arm": arm,
        "repetition": int(cell["repetition"]),
        "phase": cell["phase"],
        "arm_order": list(cell["arm_order"]),
        "planned": True,
        "query": _TIMING_QUERY_NAMES[arm],
        "count_only": True,
        "status": "missing",
        "reason": reason,
        "monotonic_start": None,
        "monotonic_end": None,
        "duration_seconds": None,
        "utc_start": None,
        "utc_end": None,
        "accepted_pairs": None,
        "accepted_pairs_observed": None,
        "returned_count": None,
        "batches": [],
    }


def collect_timings(
    records: Sequence[PoiRecord],
    backend: EngineBackend,
    *,
    clock: Callable[[], float],
    run_started: float,
    run_timeout_seconds: float,
    on_utc: Callable[[], datetime],
    on_event: Callable[[str, Mapping[str, Any]], None] | None = None,
    expected_accepted: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    halted = False
    halt_reason = "earlier_failure_no_retry"
    for planned in _timing_plan():
        if halted:
            cells.append(_missing_timing_cell(planned, halt_reason))
            continue
        cell = _run_timing_cell(
            records,
            planned,
            backend,
            clock=clock,
            run_started=run_started,
            run_timeout_seconds=run_timeout_seconds,
            on_utc=on_utc,
            expected_accepted=expected_accepted,
        )
        cells.append(cell)
        # Journal only after the cell's end clock: writer latency is never
        # inside a measured cell's duration.
        _emit(
            on_event,
            "timing_cell",
            {
                "radius_km": cell["radius_km"],
                "arm": cell["arm"],
                "repetition": cell["repetition"],
                "phase": cell["phase"],
                "status": cell["status"],
                "accepted_pairs": cell["accepted_pairs"],
                "accepted_pairs_observed": cell["accepted_pairs_observed"],
                "duration_seconds": cell["duration_seconds"],
                "utc_start": cell["utc_start"],
                "utc_end": cell["utc_end"],
                "error": cell.get("error"),
            },
        )
        if cell["status"] != "success":
            halted = True
            if is_engine_auth_denied(cell.get("error")):
                halt_reason = "engine_auth_denied_no_continuation"
    return cells


def summarize_timings(cells: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Median/range over measured repetitions only; warm-ups are excluded."""
    summaries: list[dict[str, Any]] = []
    for radius in RADII_KM:
        for arm in ("baseline", "optimized"):
            warmups = [
                cell
                for cell in cells
                if cell["radius_km"] == radius
                and cell["arm"] == arm
                and cell["phase"] == "warmup"
                and cell["status"] == "success"
            ]
            measured = [
                cell
                for cell in cells
                if cell["radius_km"] == radius
                and cell["arm"] == arm
                and cell["phase"] == "measured"
                and cell["status"] == "success"
            ]
            durations = [float(cell["duration_seconds"]) for cell in measured]
            summaries.append(
                {
                    "radius_km": radius,
                    "arm": arm,
                    "planned_measured_repetitions": MEASURED_REPETITIONS,
                    "measured_success_count": len(measured),
                    "measured_missing_count": MEASURED_REPETITIONS - len(measured),
                    "warmup_count": len(warmups),
                    "warmup_duration_seconds": (
                        float(warmups[0]["duration_seconds"]) if warmups else None
                    ),
                    "measured_durations_seconds": durations,
                    "median_seconds": statistics.median(durations) if durations else None,
                    "range_seconds": [min(durations), max(durations)] if durations else None,
                    "returned_counts": [cell.get("returned_count") for cell in measured],
                    "warmup_excluded_from_median_and_range": True,
                }
            )
    return summaries


# ---------------------------------------------------------------------------
# Output ownership
# ---------------------------------------------------------------------------


class OutputLock:
    """One-writer lock tied to the exact output path."""

    def __init__(self, output_path: Path | str) -> None:
        self.output_path = Path(output_path)
        self.lock_path = self.output_path.with_name(self.output_path.name + ".lock")
        self.acquired = False

    def acquire(self) -> None:
        if self.output_path.exists() and self.output_path.stat().st_size > 0:
            raise CollectorError("output_not_empty")
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(
                str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY
            )
        except FileExistsError:
            raise CollectorError("output_locked") from None
        except OSError:
            raise CollectorError("output_lock_failed") from None
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("EXP089 collector output lock\n")
        self.acquired = True

    def release(self) -> None:
        if self.acquired:
            try:
                self.lock_path.unlink()
            except OSError:
                pass
            self.acquired = False

    def write_json(self, payload: Mapping[str, Any]) -> None:
        if not self.acquired:
            raise CollectorError("output_lock_not_held")
        encoded = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False)
        _atomic_write_text(self.output_path, encoded + "\n")


def _atomic_write_text(path: Path, text: str) -> None:
    """Same-directory temp + flush/fsync + os.replace, never truncating first."""
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}.{time.monotonic_ns()}")
    descriptor: int | None = None
    try:
        descriptor = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except OSError:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            tmp.unlink()
        except OSError:
            pass
        raise CollectorError("output_write_failed") from None


# ---------------------------------------------------------------------------
# Collection orchestration
# ---------------------------------------------------------------------------


def _base_result(
    records: Sequence[PoiRecord],
    input_path: Path | str,
    input_sha256: str,
    manifest: Mapping[str, Any],
    *,
    now: datetime,
    collection_mode: str | None = None,
    external_reference: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    count = len(records)
    mode = collection_mode or resolve_collection_mode(manifest)
    result: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "status": "running",
        "mode": "execute",
        "collection_mode": mode,
        "generated_at": _utc_iso(now),
        "input": {
            "path": _relative_public_path(Path(input_path)),
            "sha256": input_sha256,
            "records": count,
            "potential_pairs": potential_pairs(count),
            "is_full_primary": input_sha256 == DEFAULT_INPUT_SHA256
            and count == DEFAULT_RECORD_COUNT,
        },
        "manifest_binding": {
            "schema": manifest.get("schema"),
            "frozen": manifest.get("frozen"),
            "review": manifest.get("review"),
            "spatial_sha256": manifest.get("spatial", {}).get("sha256")
            if isinstance(manifest.get("spatial"), Mapping)
            else None,
            "collector_sha256": manifest.get("collector", {}).get("sha256")
            if isinstance(manifest.get("collector"), Mapping)
            else None,
            "query_hashes": manifest.get("queries"),
        },
        "planned": {
            "radii_km": list(RADII_KM),
            "batch_size": BATCH_SIZE,
            "batches": len(batch_ids([record.id for record in records])),
            "potential_pairs": potential_pairs(count),
            "timing_cells_total": TIMING_CELLS_TOTAL,
        },
        "projection": None,
        "correctness": [],
        "timings": [],
        "timing_summary": [],
        "timing_cells": {
            "planned": TIMING_CELLS_TOTAL,
            "success": 0,
            "error": 0,
            "missing": 0,
            "warmups_success": 0,
            "measured_success": 0,
        },
        "labels": {
            "candidate_counts": "logical prefilter predicate/input counts",
            "physical_engine_evaluation_counts": None,
            "timing_workload": (
                "count-only aggregate over the same predicates; end-to-end latency "
                "does not include transferring every accepted pair row"
            ),
            "latency_improvement_claimed": False,
            "subquadratic_complexity_claimed": False,
            "source_areas": "dataset labels, not current administrative containment",
            "stored_relationship_semantics": "not proven by read-only canonical queries",
            "synthetic_offline_tests_are_not_live_engine_evidence": True,
        },
        "model_calls": 0,
        "graph_mutation": False,
        "assertions": {
            "no_model_calls": True,
            "no_graph_mutation": True,
            "read_only_queries_only": True,
        },
        "runtime": _runtime_metadata(),
        "limitations": _limitations(),
    }
    if mode == COLLECTION_MODE_TIMING_ONLY:
        result["external_correctness"] = (
            dict(external_reference) if isinstance(external_reference, Mapping) else None
        )
        result["planned"]["correctness_queries"] = 0
        result["planned"]["external_correctness_radii"] = len(RADII_KM)
    return result


def run_collection(
    records: Sequence[PoiRecord],
    input_path: Path | str,
    input_sha256: str,
    manifest: Mapping[str, Any],
    backend: EngineBackend,
    *,
    clock: Callable[[], float] = time.monotonic,
    on_utc: Callable[[], datetime] = utc_now,
    run_timeout_seconds: float | None = None,
    on_event: Callable[[str, Mapping[str, Any]], None] | None = None,
    external_reference: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run projection, then either full correctness or reused-proof timings."""
    mode = resolve_collection_mode(manifest)
    resolved_budget = float(resolve_run_budget(manifest))
    if run_timeout_seconds is None:
        run_timeout_seconds = resolved_budget
    else:
        if (
            mode == COLLECTION_MODE_TIMING_ONLY
            and _finite_number(run_timeout_seconds) != resolved_budget
        ):
            raise CollectorError("run_budget_override_rejected")
        run_timeout_seconds = _finite_number(run_timeout_seconds)
    if mode == COLLECTION_MODE_TIMING_ONLY:
        if (
            not isinstance(external_reference, Mapping)
            or external_reference.get("status") != "validated"
            or external_reference.get("correctness_reused_not_rerun") is not True
        ):
            raise CollectorError("external_reference_not_validated")
    result = _base_result(
        records,
        input_path,
        input_sha256,
        manifest,
        now=on_utc(),
        collection_mode=mode,
        external_reference=external_reference,
    )
    result["execution_budget_seconds"] = run_timeout_seconds
    run_started = clock()
    result["run_started_monotonic"] = run_started
    result["run_started_utc"] = _utc_iso(on_utc())

    try:
        result["stage"] = "graph_projection"
        try:
            result["projection"] = verify_projection(
                records,
                backend,
                clock=clock,
                run_started=run_started,
                run_timeout_seconds=run_timeout_seconds,
            )
        except CollectorError as exc:
            result["status"] = "blocked"
            result["error"] = exc.as_dict()
            _emit(
                on_event,
                "projection",
                {"status": "error", "error": exc.as_dict()},
            )
            result["run_elapsed_seconds"] = clock() - run_started
            return result
        projection = result["projection"]
        _emit(
            on_event,
            "projection",
            {
                "status": projection.get("status"),
                "expected_records": projection.get("expected_records"),
                "matched_records": projection.get("matched_records"),
                "out_of_universe_poi_count": projection.get(
                    "out_of_universe_poi_count"
                ),
                "index_info_status": (
                    projection.get("index_info", {}).get("status")
                    if isinstance(projection.get("index_info"), Mapping)
                    else None
                ),
            },
        )

        terminal_error: Mapping[str, Any] | None = None
        all_correctness_passed = True
        expected_accepted: Mapping[str, Any] | None = None
        if mode == COLLECTION_MODE_TIMING_ONLY:
            expected_accepted = _require_mapping(
                external_reference.get("accepted_counts"),
                "external_reference_invalid",
            )
            timings_ready = True
        else:
            result["stage"] = "correctness"
            for radius in RADII_KM:
                if terminal_error is not None:
                    result["correctness"].append(
                        _missing_correctness(
                            records,
                            radius,
                            reason="engine_auth_denied_no_continuation",
                            now=on_utc(),
                            error=terminal_error,
                        )
                    )
                    continue
                correctness = collect_correctness(
                    records,
                    radius,
                    backend,
                    clock=clock,
                    run_started=run_started,
                    run_timeout_seconds=run_timeout_seconds,
                    on_utc=on_utc,
                    on_event=on_event,
                )
                result["correctness"].append(correctness)
                if not correctness["passed"]:
                    all_correctness_passed = False
                error = correctness.get("error")
                if is_engine_auth_denied(error):
                    terminal_error = dict(error) if isinstance(error, Mapping) else {
                        "code": AUTH_DENIED_CODE
                    }
            timings_ready = all_correctness_passed

        result["stage"] = "timings"
        if terminal_error is not None:
            cells = [
                _missing_timing_cell(cell, "engine_auth_denied_no_continuation")
                for cell in _timing_plan()
            ]
        elif timings_ready:
            cells = collect_timings(
                records,
                backend,
                clock=clock,
                run_started=run_started,
                run_timeout_seconds=run_timeout_seconds,
                on_utc=on_utc,
                on_event=on_event,
                expected_accepted=expected_accepted,
            )
        else:
            cells = [
                _missing_timing_cell(cell, "correctness_not_passed")
                for cell in _timing_plan()
            ]
        if terminal_error is None:
            for cell in cells:
                error = cell.get("error")
                if is_engine_auth_denied(error):
                    terminal_error = dict(error) if isinstance(error, Mapping) else {
                        "code": AUTH_DENIED_CODE
                    }
                    break
        result["timings"] = cells
        result["timing_summary"] = summarize_timings(cells)
        result["timing_cells"] = {
            "planned": len(cells),
            "success": sum(1 for cell in cells if cell["status"] == "success"),
            "error": sum(1 for cell in cells if cell["status"] == "error"),
            "missing": sum(1 for cell in cells if cell["status"] == "missing"),
            "warmups_success": sum(
                1
                for cell in cells
                if cell["status"] == "success" and cell["phase"] == "warmup"
            ),
            "measured_success": sum(
                1
                for cell in cells
                if cell["status"] == "success" and cell["phase"] == "measured"
            ),
        }
        full_timing = bool(
            result["timing_cells"]["planned"] == TIMING_CELLS_TOTAL
            and result["timing_cells"]["success"] == TIMING_CELLS_TOTAL
            and result["timing_cells"]["warmups_success"]
            == len(RADII_KM) * 2 * WARMUP_RUNS
            and result["timing_cells"]["measured_success"]
            == len(RADII_KM) * 2 * MEASURED_REPETITIONS
        )
        if mode == COLLECTION_MODE_TIMING_ONLY:
            if full_timing and external_reference.get("status") == "validated":
                result["status"] = "completed"
            elif (
                result["timing_cells"]["success"]
                or result["timing_cells"]["error"]
            ):
                result["status"] = "partial"
            else:
                result["status"] = "failed"
        elif all_correctness_passed and full_timing:
            result["status"] = "completed"
        elif result["timing_cells"]["success"] or result["correctness"]:
            result["status"] = "partial"
        else:
            result["status"] = "failed"
        if terminal_error is not None:
            result["terminal_error"] = dict(terminal_error)
            result["error"] = dict(terminal_error)
        result["run_elapsed_seconds"] = clock() - run_started
        return result
    except CollectorError as exc:
        result["status"] = "failed"
        result["error"] = exc.as_dict()
    except journal_module.JournalError as exc:
        result["status"] = "failed"
        result["error"] = exc.as_dict()
    except Exception as exc:  # sanitized type only; keep earlier completed units
        result["status"] = "failed"
        result["error"] = {"code": "engine_error", "type": type(exc).__name__}
    result["run_elapsed_seconds"] = clock() - run_started
    return result


# ---------------------------------------------------------------------------
# Execute CLI
# ---------------------------------------------------------------------------


def load_manifest(path: Path | str) -> tuple[dict[str, Any], str]:
    manifest_path = Path(path)
    try:
        payload = manifest_path.read_bytes()
    except OSError:
        raise CollectorError("manifest_unreadable") from None
    try:
        manifest = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise CollectorError("manifest_invalid") from None
    if not isinstance(manifest, dict):
        raise CollectorError("manifest_invalid")
    return manifest, hashlib.sha256(payload).hexdigest()


def _final_event(result: Mapping[str, Any]) -> dict[str, Any]:
    """Bounded final journal summary; completed-unit evidence stays per event."""
    correctness = []
    for item in result.get("correctness", []) or []:
        if not isinstance(item, Mapping):
            continue
        correctness.append(
            {
                "radius_km": item.get("radius_km"),
                "status": item.get("status"),
                "passed": item.get("passed"),
                "candidate_pairs": item.get("candidate_pairs"),
                "baseline_accepted_pairs": item.get("baseline_accepted_pairs"),
                "optimized_accepted_pairs": item.get("optimized_accepted_pairs"),
                "false_negatives": item.get("false_negatives"),
                "false_positives": item.get("false_positives"),
                "baseline_pair_digest": item.get("baseline_pair_digest"),
                "optimized_pair_digest": item.get("optimized_pair_digest"),
                "batches_completed": sum(
                    1
                    for batch in item.get("batches", [])
                    if isinstance(batch, Mapping) and batch.get("status") == "success"
                ),
                "missing_batches": item.get("missing_batches"),
            }
        )
    timings = result.get("timings", []) or []
    external = result.get("external_correctness")
    external_summary = None
    if isinstance(external, Mapping):
        external_summary = {
            "protocol": external.get("protocol"),
            "status": external.get("status"),
            "correctness_reused_not_rerun": external.get(
                "correctness_reused_not_rerun"
            ),
            "accepted_counts": external.get("accepted_counts"),
            "frozen_manifest": external.get("frozen_manifest"),
            "journal": external.get("journal"),
            "parent_review": external.get("parent_review"),
            "archived_sources": external.get("archived_sources"),
        }
    return {
        "status": result.get("status"),
        "stage": result.get("stage"),
        "collection_mode": result.get("collection_mode"),
        "correctness": correctness,
        "external_correctness": external_summary,
        "timing_cells": result.get("timing_cells"),
        "timing_success_units": [
            {
                "radius_km": cell.get("radius_km"),
                "arm": cell.get("arm"),
                "repetition": cell.get("repetition"),
                "phase": cell.get("phase"),
                "duration_seconds": cell.get("duration_seconds"),
            }
            for cell in timings
            if isinstance(cell, Mapping) and cell.get("status") == "success"
        ],
        "run_elapsed_seconds": result.get("run_elapsed_seconds"),
        "error": result.get("error"),
        "cleanup": result.get("cleanup"),
    }


def execute_collection(
    input_path: Path | str,
    manifest_path: Path | str,
    output_path: Path | str,
    *,
    backend_factory: Callable[[], EngineBackend] | None = None,
    clock: Callable[[], float] = time.monotonic,
    on_utc: Callable[[], datetime] = utc_now,
    run_timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Full execute path.  Every gate runs before driver construction."""
    records, input_sha256 = load_records(input_path)
    manifest, manifest_sha256 = load_manifest(manifest_path)
    validate_manifest(
        manifest,
        records,
        input_path,
        input_sha256,
        require_frozen=True,
    )
    mode = resolve_collection_mode(manifest)
    resolved_budget = float(resolve_run_budget(manifest))
    if run_timeout_seconds is None:
        run_timeout_seconds = resolved_budget
    else:
        if (
            mode == COLLECTION_MODE_TIMING_ONLY
            and _finite_number(run_timeout_seconds) != resolved_budget
        ):
            raise CollectorError("run_budget_override_rejected")
        run_timeout_seconds = _finite_number(run_timeout_seconds)
    external_reference: Mapping[str, Any] | None = None
    if mode == COLLECTION_MODE_TIMING_ONLY:
        # The full proof is validated before the output lock, journal or backend.
        external_reference = validate_external_correctness_reference(
            manifest, records, input_sha256
        )

    lock = OutputLock(output_path)
    lock.acquire()
    journal_path = journal_module.journal_path_for(output_path)
    sink: journal_module.DurableJournal | None = None
    backend: EngineBackend | None = None
    result: dict[str, Any] | None = None
    try:
        journal_path = ensure_journal_absent(output_path)
        sink = journal_module.DurableJournal.open_new(
            journal_path,
            binding=journal_binding(
                manifest,
                manifest_sha256,
                input_sha256,
                collection_mode=mode,
                external_reference=external_reference,
            ),
            planned=journal_planned_denominator(
                records,
                collection_mode=mode,
                external_reference=external_reference,
            ),
            created_utc=on_utc(),
        )
        # Run-start is durable before backend construction.
        sink.append(
            "run_start",
            {
                "mode": "execute",
                "collection_mode": mode,
                "input_sha256": input_sha256,
                "manifest_sha256": manifest_sha256,
                "records": len(records),
                "potential_pairs": potential_pairs(len(records)),
                "timing_cells_total": TIMING_CELLS_TOTAL,
                "engine_uri": FIXED_BOLT_URI,
                "auth": "none",
                "read_only": True,
                "execution_budget_seconds": run_timeout_seconds,
            },
        )
        if mode == COLLECTION_MODE_TIMING_ONLY and external_reference is not None:
            sink.append(
                "correctness_reference_validated",
                {
                    **_external_reference_binding(external_reference),
                    "correctness_reused_not_rerun": True,
                    "planned_correctness_queries": 0,
                    "reference_radii": external_reference.get("reference_radii"),
                    "radii": external_reference.get("radii"),
                },
            )
        try:
            backend = backend_factory() if backend_factory is not None else Neo4jBackend()
        except CollectorError as exc:
            result = _base_result(
                records,
                input_path,
                input_sha256,
                manifest,
                now=on_utc(),
                collection_mode=mode,
                external_reference=external_reference,
            )
            result["status"] = "failed"
            result["stage"] = "backend_start"
            result["error"] = exc.as_dict()
            sink.append(
                "backend_start", {"status": "error", "error": exc.as_dict()}
            )
        except Exception as exc:  # sanitized type only
            result = _base_result(
                records,
                input_path,
                input_sha256,
                manifest,
                now=on_utc(),
                collection_mode=mode,
                external_reference=external_reference,
            )
            result["status"] = "failed"
            result["stage"] = "backend_start"
            result["error"] = {"code": "engine_error", "type": type(exc).__name__}
            sink.append(
                "backend_start",
                {"status": "error", "error": result["error"]},
            )
        else:
            sink.append("backend_start", {"status": "created"})
            result = run_collection(
                records,
                input_path,
                input_sha256,
                manifest,
                backend,
                clock=clock,
                on_utc=on_utc,
                run_timeout_seconds=run_timeout_seconds,
                on_event=sink.append,
                external_reference=external_reference,
            )

        # Backend close is cleanup, never a reason to drop completed units.
        if backend is not None:
            try:
                backend.close()
            except Exception as exc:  # sanitized type only; no retry
                cleanup_entry = {
                    "stage": "backend_close",
                    "code": "cleanup_error",
                    "type": type(exc).__name__,
                }
                result.setdefault("cleanup", []).append(cleanup_entry)
                sink.append("cleanup", cleanup_entry)
            finally:
                backend = None

        result["manifest_binding"]["sha256"] = manifest_sha256
        result["output_path"] = _relative_public_path(Path(output_path))
        result["journal_path"] = _relative_public_path(journal_path)
        sink.append("final_result", _final_event(result))
        try:
            lock.write_json(result)
        except CollectorError as exc:
            sink.append("output_write", {"status": "error", "error": exc.as_dict()})
            raise
        return result
    finally:
        if backend is not None:
            try:
                backend.close()
            except Exception:
                pass
        if sink is not None:
            sink.close()
        lock.release()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "EXP089 read-only E2 collector. Default is a zero-engine dry-run plan. "
            "--execute requires a reviewed frozen manifest."
        )
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT_PATH))
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    backend_factory: Callable[[], EngineBackend] | None = None,
    clock: Callable[[], float] = time.monotonic,
    on_utc: Callable[[], datetime] = utc_now,
) -> int:
    args = _parser().parse_args(argv)
    input_path = Path(args.input)
    try:
        if args.execute:
            if not args.manifest:
                raise CollectorError("manifest_required_for_execute")
            if not args.output:
                raise CollectorError("output_required_for_execute")
            result = execute_collection(
                input_path,
                args.manifest,
                args.output,
                backend_factory=backend_factory,
                clock=clock,
                on_utc=on_utc,
            )
            print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
            return 0 if result.get("status") == "completed" else 1

        records, input_sha256 = load_records(input_path)
        manifest = None
        if args.manifest:
            manifest, _ = load_manifest(args.manifest)
        plan = build_dry_run_plan(
            records,
            input_path,
            input_sha256,
            manifest,
            now=on_utc(),
        )
        if args.output:
            lock = OutputLock(args.output)
            lock.acquire()
            try:
                lock.write_json(plan)
            finally:
                lock.release()
        print(json.dumps(plan, indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    except CollectorError as exc:
        error = {
            "schema": SCHEMA_VERSION,
            "task_id": TASK_ID,
            "status": "blocked",
            "mode": "execute" if args.execute else "dry_run",
            "plan_only": not args.execute,
            "scientific_result": False,
            "latency_measured": False,
            "error": exc.as_dict(),
        }
        print(json.dumps(error, indent=2, ensure_ascii=False, allow_nan=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
