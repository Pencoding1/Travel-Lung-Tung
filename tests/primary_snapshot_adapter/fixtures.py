"""Isolated synthetic fixtures for the OC-043 adapter.

The fixture reuses two real frozen records (read-only) and remaps them into a
three-feature miniature snapshot with one declared duplicate. Expected hashes
are computed after writing, so any later mutation is detected by the same gate
that protects the real snapshot.
"""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.utils.primary_snapshot import (
    CATALOG_VERSION,
    DATASET_NAMESPACE,
    INTERNAL_SOURCE_TYPE,
    PROVIDED_AT,
    InputBinding,
    SnapshotExpectations,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / "data" / "primary_20261016"
SCRATCH_ROOT = Path(__file__).resolve().parent / "_scratch"

FIXTURE_FILES = (
    "geojson",
    "prepared",
    "lineage",
    "registry",
    "catalog",
    "ledger",
    "summary",
)
FIXTURE_NAMES = {
    "geojson": "hcm_pois_final.geojson",
    "prepared": "prepared_pois.jsonl",
    "lineage": "lineage.jsonl",
    "registry": "identity_registry.json",
    "catalog": "category_catalog.json",
    "ledger": "duplicate_ledger.jsonl",
    "summary": "summary.json",
}


@dataclass(frozen=True)
class SnapshotFixture:
    root: Path
    expectations: SnapshotExpectations


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _feature_hash(properties: Dict[str, Any], geometry: Dict[str, Any]) -> str:
    body = {
        "type": "Feature",
        "properties": properties,
        "geometry": geometry,
    }
    material = json.dumps(body, sort_keys=True, ensure_ascii=False)
    return _sha256(material.encode("utf-8"))


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _read_first_jsonl(path: Path, count: int) -> List[Any]:
    rows: List[Any] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            rows.append(json.loads(line))
            if len(rows) == count:
                break
    return rows


def _write_json(path: Path, value: Any) -> bytes:
    data = (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    path.write_bytes(data)
    return data


def _write_jsonl(path: Path, rows: List[Any]) -> bytes:
    data = (
        "\n".join(
            json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            for row in rows
        )
        + "\n"
    ).encode("utf-8")
    path.write_bytes(data)
    return data


def new_scratch_dir(label: str) -> Path:
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    path = SCRATCH_ROOT / f"{label}-{uuid.uuid4().hex}"
    path.mkdir()
    return path


def _bindings(root: Path) -> Dict[str, InputBinding]:
    bindings: Dict[str, InputBinding] = {}
    for key, name in FIXTURE_NAMES.items():
        data = (root / name).read_bytes()
        bindings[key] = InputBinding(name, _sha256(data), len(data))
    return bindings


def build_fixture(root: Path) -> SnapshotFixture:
    root.mkdir(parents=True, exist_ok=True)
    prepared = _read_first_jsonl(
        SOURCE_ROOT / "prepared" / "prepared_pois.jsonl", 2
    )
    lineage = _read_first_jsonl(SOURCE_ROOT / "prepared" / "lineage.jsonl", 2)
    catalog = _read_json(SOURCE_ROOT / "prepared" / "category_catalog.json")
    raw_root = _read_json(SOURCE_ROOT / "hcm_pois_final.geojson")
    raw_features = raw_root["features"]

    source_indices = [
        row["source"]["canonical_source_index"] for row in lineage
    ]
    feature_a = copy.deepcopy(raw_features[source_indices[0]])
    feature_b = copy.deepcopy(raw_features[source_indices[1]])
    geojson = {
        "type": "FeatureCollection",
        "name": "oc043-synthetic-fixture",
        "crs": raw_root.get("crs"),
        "features": [feature_a, feature_b, copy.deepcopy(feature_a)],
    }
    geojson_bytes = _write_json(root / FIXTURE_NAMES["geojson"], geojson)
    geojson_sha = _sha256(geojson_bytes)

    for index, row in enumerate(lineage):
        row["source"]["canonical_source_index"] = index
        row["source"]["input_path"] = FIXTURE_NAMES["geojson"]
        row["source"]["input_sha256"] = geojson_sha
    _write_jsonl(root / FIXTURE_NAMES["lineage"], lineage)
    _write_jsonl(root / FIXTURE_NAMES["prepared"], prepared)
    _write_json(root / FIXTURE_NAMES["catalog"], catalog)

    ledger = [
        {
            "canonical_source_index": 0,
            "duplicate_source_index": 2,
            "exact_feature_hash": _feature_hash(
                feature_a["properties"], feature_a["geometry"]
            ),
            "note": "Synthetic fixture: a declared byte-equivalent duplicate.",
            "reason": "byte_equivalent_canonical_feature",
        }
    ]
    _write_jsonl(root / FIXTURE_NAMES["ledger"], ledger)

    records: Dict[str, Any] = {}
    identity_index: Dict[str, str] = {}
    for row in lineage:
        identity = row["identity"]
        records[row["id"]] = {
            "identity": {
                "address_anchor": identity["address_anchor"],
                "coordinates": identity["coordinates_token"],
                "name_key": identity["name_key"],
                "processed_name": identity["processed_name"],
                "raw_name": identity["raw_name"],
            },
            "identity_key": identity["identity_key"],
            "record_id": row["internal_record_id"],
            "sequence": row["sequence"],
        }
        identity_index[identity["identity_key"]] = row["id"]
    max_sequence = max(row["sequence"] for row in lineage)
    registry = {
        "cross_export_matching": "not_guaranteed",
        "identity_index": identity_index,
        "identity_scope": "internal_local_only",
        "input_sha256": geojson_sha,
        "namespace": DATASET_NAMESPACE,
        "next_sequence": max_sequence,
        "prior_input_sha256": [],
        "records": records,
        "registry_version": 1,
        "source_type": INTERNAL_SOURCE_TYPE,
    }
    _write_json(root / FIXTURE_NAMES["registry"], registry)

    review_required = sum(1 for row in lineage if row["review_flags"])
    summary = {
        "catalog": {
            "catalog_version": CATALOG_VERSION,
            "categories": [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "source_label": row["source_label"],
                }
                for row in catalog
            ],
            "size": len(catalog),
        },
        "counts": {
            "candidate_features": len(prepared),
            "exact_duplicate_extra": len(ledger),
            "input_features": len(geojson["features"]),
            "prepared": len(prepared),
            "prepared_review_required": review_required,
            "quarantine": 0,
        },
        "dataset": {
            "declared_provided_at": PROVIDED_AT,
            "input_bytes": len(geojson_bytes),
            "input_features": len(geojson["features"]),
            "input_path": FIXTURE_NAMES["geojson"],
            "input_sha256": geojson_sha,
        },
        "identity": {
            "cross_export_matching": "not_guaranteed",
            "next_sequence": max_sequence,
            "registry_path": FIXTURE_NAMES["registry"],
            "registry_records": len(records),
            "scope": "internal_local_only",
        },
        "internal_source_type": INTERNAL_SOURCE_TYPE,
        "namespace": DATASET_NAMESPACE,
        "not_claimed": [
            "accepted graph nodes",
            "verified venues",
            "fresh data",
            "genuine upstream/source identifiers",
        ],
        "prep_version": "oc-034.1",
        "prepared_review_flags": {
            "legacy_admin_qualification_unresolved": review_required
        },
        "provenance": {
            "collection_time": "UNKNOWN",
            "freshness": "UNKNOWN",
            "license": "UNKNOWN",
            "note": "Synthetic fixture only.",
            "provided_at": PROVIDED_AT,
            "sidecar_only": True,
            "source_url": "UNKNOWN",
        },
        "quarantine_reasons": {},
        "semantic_gap": {"admin": "fixture", "categories": "fixture"},
        "status": "prepared/schema-validated candidates",
        "sumcheck": {
            "candidates_plus_duplicate_extra_equals_input": True,
            "prepared_plus_quarantine_equals_candidates": True,
        },
        "task_id": "OC-034",
    }
    _write_json(root / FIXTURE_NAMES["summary"], summary)

    expectations = SnapshotExpectations(
        real=False,
        dataset_class="synthetic_fixture",
        namespace=DATASET_NAMESPACE,
        source_type=INTERNAL_SOURCE_TYPE,
        provided_at=PROVIDED_AT,
        catalog_version=CATALOG_VERSION,
        input_features=len(geojson["features"]),
        prepared_records=len(prepared),
        category_count=len(catalog),
        duplicate_ledger_records=len(ledger),
        files=_bindings(root),
    )
    return SnapshotFixture(root=root, expectations=expectations)


def refresh_binding(fixture: SnapshotFixture, key: str) -> SnapshotFixture:
    name = FIXTURE_NAMES[key]
    data = (fixture.root / name).read_bytes()
    files = dict(fixture.expectations.files)
    files[key] = InputBinding(name, _sha256(data), len(data))
    return SnapshotFixture(
        root=fixture.root,
        expectations=replace(fixture.expectations, files=files),
    )


def rewrite_jsonl(path: Path, rows: List[Any]) -> None:
    _write_jsonl(path, rows)


def read_json(path: Path) -> Any:
    return _read_json(path)
