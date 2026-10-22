"""Fail-closed graph-ready adapter for the reviewed primary POI snapshot.

The adapter is deliberately offline. It reads the frozen primary artifacts,
verifies the exact reviewed byte bindings and every cross-artifact invariant,
then builds ``prepared_pois.jsonl`` payloads that the existing
``POI_service`` ingestion contract can consume unchanged.

It is not a general importer: the real mode accepts only the reviewed primary
snapshot hashes. A non-real plan may be used by isolated fixtures, but it can
never emit the real manifest or write the real destination.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from app.core.domain.graph_entities import POI, canonical_json


TASK_ID = "OC-043"
ADAPTER_VERSION = "oc-043.1"
MANIFEST_VERSION = 2
MANIFEST_SCHEMA = "primary_graph_ready_snapshot/2"

PREPARED_FILENAME = "prepared_pois.jsonl"
MANIFEST_FILENAME = "manifest.json"
CHECKSUMS_FILENAME = "checksums.sha256"
OUTPUT_FILENAMES = (PREPARED_FILENAME, MANIFEST_FILENAME, CHECKSUMS_FILENAME)

REPO_ROOT = Path(__file__).resolve().parents[4]
REAL_OUTPUT_DIR = REPO_ROOT / "data" / "primary_20261016" / "graph_ready_v2"

DATASET_NAMESPACE = "hcm_primary_geojson"
INTERNAL_SOURCE_TYPE = "hcm_primary_geojson_internal"
PROVIDED_AT = "2026-10-16"
CATALOG_VERSION = "1e39b6e91122c6ee"
SOURCE_AREA_SCOPE = "source_snapshot_area_only"

INPUT_FEATURES = 6368
PREPARED_RECORDS = 6367
CATEGORY_COUNT = 14
DUPLICATE_LEDGER_RECORDS = 1
PREPARED_REVIEW_REQUIRED = 411

UNKNOWN = "UNKNOWN"
UNKNOWN_FIELDS = ("collection_time", "source_url", "license", "freshness")

RAW_PROPERTY_KEYS = frozenset(
    {
        "addr_city",
        "addr_district",
        "addr_full",
        "addr_house",
        "addr_stree",
        "addr_ward",
        "cluster",
        "lat",
        "lon",
        "name",
        "opening_ho",
        "poi_category",
        "processed_name",
    }
)
PREPARED_KEYS = frozenset(
    {
        "address",
        "contact_info",
        "id",
        "latitude",
        "longitude",
        "menu",
        "name",
        "operation_time",
        "poi_categories",
        "rating",
        "tag",
    }
)
LINEAGE_KEYS = frozenset(
    {
        "address",
        "catalog_version",
        "category_source_label",
        "id",
        "identity",
        "internal_record_id",
        "operation_time",
        "price",
        "provenance",
        "review_flags",
        "sequence",
        "source",
    }
)
ADDRESS_EVIDENCE_KEYS = frozenset(
    {
        "current_admin_claim",
        "payload_city",
        "payload_district",
        "raw_city",
        "raw_district",
        "raw_full",
        "raw_house",
        "raw_stree",
        "raw_ward",
        "scope",
    }
)
IDENTITY_KEYS = frozenset(
    {
        "address_anchor",
        "coordinates_token",
        "cross_export_matching",
        "derivation",
        "identity_key",
        "identity_scope",
        "name_key",
        "name_source",
        "namespace",
        "processed_name",
        "raw_name",
    }
)
SOURCE_KEYS = frozenset(
    {
        "canonical_source_index",
        "cluster",
        "exact_feature_hash",
        "geometry",
        "input_path",
        "input_sha256",
        "raw_properties",
    }
)
PROVENANCE_KEYS = frozenset(
    {"collection_time", "freshness", "license", "provided_at", "source_url"}
)
PRICE_KEYS = frozenset({"note", "status"})
CATEGORY_PAYLOAD_KEYS = frozenset({"context", "id", "name"})
CATEGORY_CATALOG_KEYS = frozenset({"context", "id", "name", "source_label"})
ADDRESS_PAYLOAD_KEYS = frozenset({"city", "district", "nation", "street_name", "ward"})
REGISTRY_RECORD_KEYS = frozenset({"identity", "identity_key", "record_id", "sequence"})
REGISTRY_IDENTITY_KEYS = frozenset(
    {"address_anchor", "coordinates", "name_key", "processed_name", "raw_name"}
)
LEDGER_KEYS = frozenset(
    {
        "canonical_source_index",
        "duplicate_source_index",
        "exact_feature_hash",
        "note",
        "reason",
    }
)
ALLOWED_REVIEW_FLAGS = frozenset({"legacy_admin_qualification_unresolved"})


class SnapshotError(Exception):
    """A truthful, fail-closed rejection with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class InputBinding:
    relative: str
    sha256: str
    size: Optional[int] = None


@dataclass(frozen=True)
class SnapshotExpectations:
    real: bool
    dataset_class: str
    namespace: str
    source_type: str
    provided_at: str
    catalog_version: str
    input_features: int
    prepared_records: int
    category_count: int
    duplicate_ledger_records: int
    files: Mapping[str, InputBinding]
    provenance_manifest: Optional[InputBinding] = None
    snapshot_manifest: Optional[InputBinding] = None


@dataclass(frozen=True)
class SnapshotPlan:
    real: bool
    expectations: SnapshotExpectations
    records: Tuple[Dict[str, Any], ...]
    prepared_bytes: bytes
    manifest: Dict[str, Any]
    manifest_bytes: bytes
    checksums_bytes: bytes
    input_files: Dict[str, Dict[str, Any]]


REAL_EXPECTATIONS = SnapshotExpectations(
    real=True,
    dataset_class="real_supplied_primary_snapshot",
    namespace=DATASET_NAMESPACE,
    source_type=INTERNAL_SOURCE_TYPE,
    provided_at=PROVIDED_AT,
    catalog_version=CATALOG_VERSION,
    input_features=INPUT_FEATURES,
    prepared_records=PREPARED_RECORDS,
    category_count=CATEGORY_COUNT,
    duplicate_ledger_records=DUPLICATE_LEDGER_RECORDS,
    files={
        "geojson": InputBinding(
            "data/primary_20261016/hcm_pois_final.geojson",
            "713b07a62cf89bd2cad9093abaad2a4c5f01e23853321764b3d66bf9f7eee43c",
            2712731,
        ),
        "prepared": InputBinding(
            "data/primary_20261016/prepared/prepared_pois.jsonl",
            "3944987f9e1d01f38c82b4e53b387a893d42811495a74ed461ea2f39d11485ad",
            3253885,
        ),
        "lineage": InputBinding(
            "data/primary_20261016/prepared/lineage.jsonl",
            "70247a350da90ed11599a492cc1b8a453e560c5fe42540ec2a51e6b0cbdbabe4",
            12399103,
        ),
        "registry": InputBinding(
            "data/primary_20261016/prepared/identity_registry.json",
            "de5594af7fc9dbf9039269b6ee5bd0989b291ea4bebdbaab37b5218730a03b65",
            3777966,
        ),
        "catalog": InputBinding(
            "data/primary_20261016/prepared/category_catalog.json",
            "80491fcc75c6bda724d10973124dab77189d86bc8ea629bc1c4c1bddeae7d6cc",
            3025,
        ),
        "ledger": InputBinding(
            "data/primary_20261016/prepared/duplicate_ledger.jsonl",
            "c00e8774c8203a75497f34ff2894ea26673d1ac919476e7b19f87f83823bbac2",
            387,
        ),
        "summary": InputBinding(
            "data/primary_20261016/prepared/summary.json",
            "1b69c250842794e0bcd6942453a42af1f580eeecd5d42b84ed4a1d5f9d4d15be",
            4755,
        ),
    },
    provenance_manifest=InputBinding(
        "data/primary_20261016/source_provenance_manifest.json",
        "6aff7d923b94642efbcdca48e517d19b64eb1374f8e8b3bd0a7bd4bf73e49c94",
        2282,
    ),
    snapshot_manifest=InputBinding(
        "data/primary_20261016/SNAPSHOT_MANIFEST.json",
        "b69f882b41296669ee6d01c5f36c2a260685a5127d9bcb10973da62318d60402",
        2198,
    ),
)


_DATASET_CLASSES = frozenset(
    {"real_supplied_primary_snapshot", "synthetic_fixture"}
)


def _fail(code: str, message: str) -> None:
    raise SnapshotError(code, message)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_hash(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        _fail(code, message)


def _require_keys(value: Any, expected: frozenset, location: str) -> None:
    _require(isinstance(value, dict), "invalid_shape", f"{location} must be an object.")
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        _fail(
            "invalid_shape",
            f"{location} has unexpected keys; missing={missing}, extra={extra}.",
        )


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant {value!r}")


def _pairs_no_duplicates(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _assert_finite(value: Any, location: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        _fail("non_finite_json", f"{location} contains a non-finite number.")
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_finite(item, f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_finite(item, f"{location}[{index}]")


def _decode_utf8(data: bytes, location: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        _fail("invalid_utf8", f"{location} is not strict UTF-8: {exc}.")


def _loads_json(text: str, location: str) -> Any:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
        )
    except ValueError as exc:
        _fail("invalid_json", f"{location} is not valid JSON: {exc}.")
    _assert_finite(value, location)
    return value


def _load_json(data: bytes, location: str) -> Any:
    return _loads_json(_decode_utf8(data, location), location)


def _load_jsonl(data: bytes, location: str) -> List[Any]:
    text = _decode_utf8(data, location)
    if not text:
        return []
    lines = text.splitlines()
    if any(not line.strip() for line in lines):
        _fail("invalid_jsonl", f"{location} contains a blank line.")
    return [
        _loads_json(line, f"{location}:{line_number}")
        for line_number, line in enumerate(lines, start=1)
    ]


def _read_checked(base_dir: Path, binding: InputBinding) -> Tuple[Path, bytes]:
    path = base_dir / binding.relative
    if not path.is_file():
        _fail("missing_input", f"Required input is missing: {binding.relative}.")
    data = path.read_bytes()
    if binding.size is not None and len(data) != binding.size:
        _fail(
            "input_size_mismatch",
            f"{binding.relative} has {len(data)} bytes, expected {binding.size}.",
        )
    actual = _sha256_bytes(data)
    if actual != binding.sha256:
        _fail(
            "input_hash_mismatch",
            f"{binding.relative} SHA256 is {actual}, expected {binding.sha256}.",
        )
    return path, data


def _validate_expectations(expectations: SnapshotExpectations) -> None:
    # QA-DATA-01: the "real" label is a reviewed, fixed binding, never a
    # caller-supplied claim. `prepare_snapshot` still accepts an `expectations`
    # argument for the synthetic test path, so an externally built object must
    # not be able to label arbitrary bytes as the real snapshot.
    if expectations.real and expectations != REAL_EXPECTATIONS:
        _fail(
            "real_binding_mismatch",
            "A real-labelled snapshot must bind to the reviewed "
            "REAL_EXPECTATIONS; caller-supplied expectations cannot claim "
            "real provenance.",
        )
    _require(
        expectations.dataset_class in _DATASET_CLASSES,
        "invalid_expectations",
        "dataset_class is not one of the reviewed classes.",
    )
    _require(
        bool(expectations.namespace.strip()),
        "invalid_expectations",
        "namespace cannot be blank.",
    )
    _require(
        bool(expectations.source_type.strip()),
        "invalid_expectations",
        "source_type cannot be blank.",
    )
    try:
        parsed_date = date.fromisoformat(expectations.provided_at)
    except (TypeError, ValueError):
        _fail("invalid_expectations", "provided_at is not an ISO date.")
    _require(
        parsed_date.isoformat() == expectations.provided_at,
        "invalid_expectations",
        "provided_at must be a canonical ISO date.",
    )
    for label, value in (
        ("input_features", expectations.input_features),
        ("prepared_records", expectations.prepared_records),
        ("category_count", expectations.category_count),
        ("duplicate_ledger_records", expectations.duplicate_ledger_records),
    ):
        _require(
            _is_int(value) and value >= 0,
            "invalid_expectations",
            f"{label} must be a nonnegative integer.",
        )
        _require(
            value > 0,
            "invalid_expectations",
            f"{label} must be positive for this adapter.",
        )
    _require(
        expectations.prepared_records
        + expectations.duplicate_ledger_records
        == expectations.input_features,
        "invalid_expectations",
        "prepared_records + duplicate_ledger_records must equal input_features.",
    )
    required = {"geojson", "prepared", "lineage", "registry", "catalog", "ledger", "summary"}
    _require(
        set(expectations.files) == required,
        "invalid_expectations",
        "files must bind exactly the seven required inputs.",
    )
    for name, binding in expectations.files.items():
        _require(
            isinstance(binding, InputBinding),
            "invalid_expectations",
            f"{name} is not an InputBinding.",
        )
        _require(
            bool(binding.relative.strip()),
            "invalid_expectations",
            f"{name} relative path cannot be blank.",
        )
        _require(
            _is_hash(binding.sha256),
            "invalid_expectations",
            f"{name} must be bound to a lowercase SHA256.",
        )
        if binding.size is not None:
            _require(
                _is_int(binding.size) and binding.size > 0,
                "invalid_expectations",
                f"{name} size must be a positive integer.",
            )
    if expectations.real:
        _require(
            expectations.dataset_class == "real_supplied_primary_snapshot",
            "invalid_expectations",
            "real plans require the real dataset class.",
        )
        _require(
            expectations.provenance_manifest is not None
            and expectations.snapshot_manifest is not None,
            "invalid_expectations",
            "real plans require both source manifests.",
        )
    else:
        _require(
            expectations.dataset_class == "synthetic_fixture",
            "invalid_expectations",
            "non-real plans require the synthetic fixture class.",
        )


@dataclass(frozen=True)
class _CatalogInfo:
    entries: Dict[str, Dict[str, str]]
    entries_by_id: Dict[str, Dict[str, str]]
    labels: frozenset
    ids: frozenset


@dataclass(frozen=True)
class _LedgerInfo:
    pairs: Tuple[Tuple[int, int], ...]
    duplicate_of: Dict[int, int]
    duplicates_for: Dict[int, Tuple[int, ...]]
    hashes: Dict[int, str]


def _validate_catalog(catalog: Any, expectations: SnapshotExpectations) -> _CatalogInfo:
    _require(isinstance(catalog, list), "invalid_catalog", "Catalog must be a JSON array.")
    _require(
        len(catalog) == expectations.category_count,
        "invalid_catalog",
        f"Catalog has {len(catalog)} entries, expected {expectations.category_count}.",
    )
    entries: Dict[str, Dict[str, str]] = {}
    entries_by_id: Dict[str, Dict[str, str]] = {}
    for index, row in enumerate(catalog):
        location = f"catalog[{index}]"
        _require_keys(row, CATEGORY_CATALOG_KEYS, location)
        for key in ("id", "name", "source_label", "context"):
            _require(
                isinstance(row[key], str) and row[key].strip(),
                "invalid_catalog",
                f"{location}.{key} must be a nonblank string.",
            )
        label = row["source_label"]
        expected_id = f"{expectations.namespace}:source-category:{label}"
        _require(
            row["id"] == expected_id,
            "invalid_catalog",
            f"{location}.id is not the namespaced source-category id.",
        )
        _require(
            label not in entries,
            "invalid_catalog",
            f"Duplicate catalog label {label!r}.",
        )
        _require(
            row["id"] not in entries_by_id,
            "invalid_catalog",
            f"Duplicate catalog id {row['id']!r}.",
        )
        entry = {
            "id": row["id"],
            "name": row["name"],
            "context": row["context"],
        }
        entries[label] = entry
        entries_by_id[row["id"]] = entry
    return _CatalogInfo(
        entries=entries,
        entries_by_id=entries_by_id,
        labels=frozenset(entries),
        ids=frozenset(entries_by_id),
    )


def _validate_summary(
    summary: Any,
    expectations: SnapshotExpectations,
    catalog: _CatalogInfo,
) -> Dict[str, Any]:
    _require(isinstance(summary, dict), "invalid_summary", "Summary must be an object.")
    for key in (
        "counts",
        "catalog",
        "dataset",
        "identity",
        "provenance",
        "namespace",
        "internal_source_type",
    ):
        _require(key in summary, "invalid_summary", f"Summary is missing {key!r}.")

    _require(
        summary["namespace"] == expectations.namespace,
        "invalid_summary",
        "Summary namespace contradicts the reviewed namespace.",
    )
    _require(
        summary["internal_source_type"] == expectations.source_type,
        "invalid_summary",
        "Summary source class contradicts the reviewed source type.",
    )

    dataset = summary["dataset"]
    _require(isinstance(dataset, dict), "invalid_summary", "Summary dataset must be an object.")
    geojson_binding = expectations.files["geojson"]
    _require(
        dataset.get("input_path") == geojson_binding.relative,
        "invalid_summary",
        "Summary input path contradicts the reviewed input path.",
    )
    _require(
        dataset.get("input_sha256") == geojson_binding.sha256,
        "invalid_summary",
        "Summary input SHA256 contradicts the reviewed input hash.",
    )
    _require(
        _is_int(dataset.get("input_features"))
        and dataset["input_features"] == expectations.input_features,
        "invalid_summary",
        "Summary input feature count contradicts the reviewed count.",
    )
    if geojson_binding.size is not None:
        _require(
            _is_int(dataset.get("input_bytes"))
            and dataset["input_bytes"] == geojson_binding.size,
            "invalid_summary",
            "Summary input byte count contradicts the reviewed size.",
        )

    counts = summary["counts"]
    _require(isinstance(counts, dict), "invalid_summary", "Summary counts must be an object.")
    expected_counts = {
        "input_features": expectations.input_features,
        "candidate_features": expectations.prepared_records,
        "prepared": expectations.prepared_records,
        "exact_duplicate_extra": expectations.duplicate_ledger_records,
        "quarantine": 0,
    }
    for key, expected in expected_counts.items():
        _require(
            _is_int(counts.get(key)) and counts[key] == expected,
            "invalid_summary",
            f"Summary counts.{key} must be {expected}.",
        )
    _require(
        _is_int(counts.get("prepared_review_required"))
        and counts["prepared_review_required"] >= 0,
        "invalid_summary",
        "Summary prepared_review_required must be a nonnegative integer.",
    )

    sumcheck = summary.get("sumcheck")
    _require(isinstance(sumcheck, dict), "invalid_summary", "Summary sumcheck must be an object.")
    _require(
        sumcheck.get("candidates_plus_duplicate_extra_equals_input") is True
        and sumcheck.get("prepared_plus_quarantine_equals_candidates") is True,
        "invalid_summary",
        "Summary sumchecks must be true.",
    )
    _require(
        summary.get("quarantine_reasons") == {},
        "invalid_summary",
        "Summary quarantine reasons must be empty for this snapshot.",
    )

    catalog_summary = summary["catalog"]
    _require(
        isinstance(catalog_summary, dict),
        "invalid_summary",
        "Summary catalog must be an object.",
    )
    _require(
        catalog_summary.get("catalog_version") == expectations.catalog_version,
        "invalid_summary",
        "Summary catalog version contradicts the reviewed catalog version.",
    )
    _require(
        _is_int(catalog_summary.get("size"))
        and catalog_summary["size"] == expectations.category_count,
        "invalid_summary",
        "Summary catalog size contradicts the reviewed category count.",
    )
    summary_categories = catalog_summary.get("categories")
    _require(
        isinstance(summary_categories, list),
        "invalid_summary",
        "Summary catalog categories must be an array.",
    )
    summary_pairs = set()
    for index, row in enumerate(summary_categories):
        _require_keys(
            row,
            frozenset({"id", "name", "source_label"}),
            f"summary.catalog.categories[{index}]",
        )
        summary_pairs.add((row["id"], row["name"], row["source_label"]))
    catalog_pairs = {
        (entry["id"], entry["name"], label)
        for label, entry in catalog.entries.items()
    }
    _require(
        summary_pairs == catalog_pairs,
        "invalid_summary",
        "Summary catalog categories contradict the catalog file.",
    )

    identity = summary["identity"]
    _require(isinstance(identity, dict), "invalid_summary", "Summary identity must be an object.")
    _require(
        _is_int(identity.get("registry_records"))
        and identity["registry_records"] == expectations.prepared_records,
        "invalid_summary",
        "Summary registry record count contradicts the prepared count.",
    )
    _require(
        identity.get("registry_path") == expectations.files["registry"].relative,
        "invalid_summary",
        "Summary registry path contradicts the reviewed registry path.",
    )
    _require(
        identity.get("scope") == "internal_local_only",
        "invalid_summary",
        "Summary identity scope must remain internal_local_only.",
    )
    _require(
        identity.get("cross_export_matching") == "not_guaranteed",
        "invalid_summary",
        "Summary cross-export matching must remain not_guaranteed.",
    )
    _require(
        _is_int(identity.get("next_sequence"))
        and identity["next_sequence"] >= 0,
        "invalid_summary",
        "Summary next_sequence must be a nonnegative integer.",
    )

    provenance = summary["provenance"]
    _require(
        isinstance(provenance, dict),
        "invalid_summary",
        "Summary provenance must be an object.",
    )
    _require(
        provenance.get("provided_at") == expectations.provided_at,
        "invalid_summary",
        "Summary provided_at contradicts the reviewed date.",
    )
    for field in UNKNOWN_FIELDS:
        _require(
            provenance.get(field) == UNKNOWN,
            "invalid_summary",
            f"Summary provenance.{field} must stay UNKNOWN.",
        )
    _require(
        provenance.get("sidecar_only") is True,
        "invalid_summary",
        "Summary provenance must remain sidecar-only.",
    )

    return {
        "prepared_review_required": counts["prepared_review_required"],
        "next_sequence": identity["next_sequence"],
        "registry_records": identity["registry_records"],
    }


def _validate_source_manifests(
    loaded: Mapping[str, Tuple[Path, bytes]],
    expectations: SnapshotExpectations,
) -> None:
    if expectations.provenance_manifest is not None:
        data = loaded["provenance_manifest"][1]
        manifest = _load_json(data, "source_provenance_manifest")
        _require(
            isinstance(manifest, dict),
            "invalid_provenance_manifest",
            "Source provenance manifest must be an object.",
        )
        _require(
            manifest.get("provenance_status") == "INCOMPLETE_UNKNOWN",
            "invalid_provenance_manifest",
            "Source provenance status must remain INCOMPLETE_UNKNOWN.",
        )
        geojson_binding = expectations.files["geojson"]
        _require(
            manifest.get("dataset") == geojson_binding.relative,
            "invalid_provenance_manifest",
            "Source provenance dataset must match the reviewed input path.",
        )
        known = manifest.get("known")
        _require(
            isinstance(known, dict),
            "invalid_provenance_manifest",
            "Source provenance known block is missing.",
        )
        _require(
            known.get("file_sha256") == geojson_binding.sha256,
            "invalid_provenance_manifest",
            "Source provenance hash contradicts the reviewed input hash.",
        )
        _require(
            _is_int(known.get("features"))
            and known["features"] == expectations.input_features,
            "invalid_provenance_manifest",
            "Source provenance feature count contradicts the reviewed count.",
        )
        if geojson_binding.size is not None:
            _require(
                _is_int(known.get("file_bytes"))
                and known["file_bytes"] == geojson_binding.size,
                "invalid_provenance_manifest",
                "Source provenance byte count contradicts the reviewed size.",
            )
        unknown_text = " ".join(
            item for item in manifest.get("unknown", []) if isinstance(item, str)
        ).lower()
        for concept in (
            "collection",
            "source platform or url",
            "license",
            "freshness",
        ):
            _require(
                concept in unknown_text,
                "invalid_provenance_manifest",
                f"Source provenance must keep {concept!r} unknown.",
            )
        evidence = manifest.get("evidence")
        _require(
            isinstance(evidence, dict),
            "invalid_provenance_manifest",
            "Source provenance evidence block is missing.",
        )
        _require(
            evidence.get("has_provenance_block") is False,
            "invalid_provenance_manifest",
            "The supplied source must not claim a provenance block.",
        )
        _require(
            evidence.get("per_feature_id_fields_observed") == [],
            "invalid_provenance_manifest",
            "The supplied source must not claim per-feature upstream ids.",
        )

    if expectations.snapshot_manifest is not None:
        data = loaded["snapshot_manifest"][1]
        manifest = _load_json(data, "snapshot_manifest")
        _require(
            isinstance(manifest, dict),
            "invalid_snapshot_manifest",
            "Snapshot manifest must be an object.",
        )
        _require(
            manifest.get("frozen") is True,
            "invalid_snapshot_manifest",
            "Snapshot manifest must be frozen.",
        )
        primary = manifest.get("primary_dataset")
        _require(
            isinstance(primary, dict),
            "invalid_snapshot_manifest",
            "Snapshot manifest primary_dataset is missing.",
        )
        geojson_binding = expectations.files["geojson"]
        _require(
            primary.get("path") == geojson_binding.relative,
            "invalid_snapshot_manifest",
            "Snapshot manifest path contradicts the reviewed input path.",
        )
        _require(
            primary.get("sha256") == geojson_binding.sha256,
            "invalid_snapshot_manifest",
            "Snapshot manifest hash contradicts the reviewed input hash.",
        )
        _require(
            primary.get("immutable") is True,
            "invalid_snapshot_manifest",
            "Snapshot manifest must mark the primary dataset immutable.",
        )
        _require(
            _is_int(primary.get("features"))
            and primary["features"] == expectations.input_features,
            "invalid_snapshot_manifest",
            "Snapshot manifest feature count contradicts the reviewed count.",
        )
        if geojson_binding.size is not None:
            _require(
                _is_int(primary.get("bytes"))
                and primary["bytes"] == geojson_binding.size,
                "invalid_snapshot_manifest",
                "Snapshot manifest byte count contradicts the reviewed size.",
            )
        observed = primary.get("observed")
        _require(
            isinstance(observed, dict)
            and observed.get("features") == expectations.input_features
            and observed.get("sha256_matches_parent_assertion") is True
            and observed.get("bytes_matches_parent_assertion") is True,
            "invalid_snapshot_manifest",
            "Snapshot manifest observed facts are contradictory.",
        )
        separation = manifest.get("separation_of_datasets")
        _require(
            isinstance(separation, dict),
            "invalid_snapshot_manifest",
            "Snapshot manifest separation block is missing.",
        )
        expansion = separation.get("expansion_source")
        _require(
            isinstance(expansion, dict)
            and expansion.get("accepted") == 0
            and expansion.get("disjoint_from_primary") is True,
            "invalid_snapshot_manifest",
            "Snapshot manifest must keep the expansion source disjoint and unaccepted.",
        )


def _feature_hash(properties: Mapping[str, Any], geometry: Mapping[str, Any]) -> str:
    feature = {
        "type": "Feature",
        "properties": properties,
        "geometry": geometry,
    }
    material = json.dumps(feature, sort_keys=True, ensure_ascii=False)
    return _sha256_text(material)


def _validate_raw_geojson(
    geojson: Any,
    expectations: SnapshotExpectations,
    catalog: _CatalogInfo,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    _require(
        isinstance(geojson, dict),
        "invalid_geojson",
        "GeoJSON root must be an object.",
    )
    _require(
        geojson.get("type") == "FeatureCollection",
        "invalid_geojson",
        "GeoJSON root must be a FeatureCollection.",
    )
    features = geojson.get("features")
    _require(
        isinstance(features, list),
        "invalid_geojson",
        "GeoJSON features must be an array.",
    )
    _require(
        len(features) == expectations.input_features,
        "invalid_geojson",
        f"GeoJSON has {len(features)} features, expected {expectations.input_features}.",
    )
    hashes: List[str] = []
    for index, feature in enumerate(features):
        location = f"features[{index}]"
        _require_keys(feature, frozenset({"geometry", "properties", "type"}), location)
        _require(
            feature["type"] == "Feature",
            "invalid_geojson",
            f"{location}.type must be 'Feature'.",
        )
        properties = feature["properties"]
        _require_keys(properties, RAW_PROPERTY_KEYS, f"{location}.properties")
        geometry = feature["geometry"]
        _require_keys(geometry, frozenset({"coordinates", "type"}), f"{location}.geometry")
        _require(
            geometry["type"] == "Point",
            "invalid_geojson",
            f"{location}.geometry.type must be 'Point'.",
        )
        coordinates = geometry["coordinates"]
        _require(
            isinstance(coordinates, list) and len(coordinates) == 2,
            "invalid_geojson",
            f"{location}.geometry.coordinates must be [lon, lat].",
        )
        longitude, latitude = coordinates
        _require(
            _is_number(longitude) and -180.0 <= longitude <= 180.0,
            "invalid_geojson",
            f"{location} longitude must be finite and in range.",
        )
        _require(
            _is_number(latitude) and -90.0 <= latitude <= 90.0,
            "invalid_geojson",
            f"{location} latitude must be finite and in range.",
        )
        for key, expected in (("lon", longitude), ("lat", latitude)):
            value = properties[key]
            _require(
                _is_number(value),
                "invalid_geojson",
                f"{location}.properties.{key} must be finite.",
            )
            _require(
                math.isclose(float(value), float(expected), rel_tol=0.0, abs_tol=1e-9),
                "invalid_geojson",
                f"{location}.properties.{key} contradicts the geometry coordinate.",
            )
        _require(
            isinstance(properties["name"], str) and properties["name"].strip(),
            "invalid_geojson",
            f"{location}.properties.name must be nonblank.",
        )
        _require(
            properties["processed_name"] is None
            or isinstance(properties["processed_name"], str),
            "invalid_geojson",
            f"{location}.properties.processed_name must be null or text.",
        )
        _require(
            properties["opening_ho"] is None
            or isinstance(properties["opening_ho"], str),
            "invalid_geojson",
            f"{location}.properties.opening_ho must be null or text.",
        )
        for key in ("addr_city", "addr_district", "addr_full", "addr_house", "addr_stree", "addr_ward"):
            _require(
                properties[key] is None or isinstance(properties[key], str),
                "invalid_geojson",
                f"{location}.properties.{key} must be null or text.",
            )
        _require(
            _is_int(properties["cluster"]),
            "invalid_geojson",
            f"{location}.properties.cluster must be an integer.",
        )
        _require(
            properties["poi_category"] in catalog.labels,
            "invalid_geojson",
            f"{location}.properties.poi_category is not in the catalog.",
        )
        hashes.append(_feature_hash(properties, geometry))
    return features, hashes


def _validate_ledger(
    rows: List[Any],
    raw_hashes: Sequence[str],
    expectations: SnapshotExpectations,
) -> _LedgerInfo:
    _require(
        len(rows) == expectations.duplicate_ledger_records,
        "invalid_ledger",
        f"Duplicate ledger has {len(rows)} rows, expected "
        f"{expectations.duplicate_ledger_records}.",
    )
    pairs: List[Tuple[int, int]] = []
    duplicate_of: Dict[int, int] = {}
    duplicates_for: Dict[int, List[int]] = {}
    hashes: Dict[int, str] = {}
    for index, row in enumerate(rows):
        location = f"ledger[{index}]"
        _require_keys(row, LEDGER_KEYS, location)
        canonical = row["canonical_source_index"]
        duplicate = row["duplicate_source_index"]
        _require(
            _is_int(canonical) and 0 <= canonical < expectations.input_features,
            "invalid_ledger",
            f"{location}.canonical_source_index is out of range.",
        )
        _require(
            _is_int(duplicate) and 0 <= duplicate < expectations.input_features,
            "invalid_ledger",
            f"{location}.duplicate_source_index is out of range.",
        )
        _require(
            canonical != duplicate,
            "invalid_ledger",
            f"{location} cannot duplicate itself.",
        )
        _require(
            _is_hash(row["exact_feature_hash"]),
            "invalid_ledger",
            f"{location}.exact_feature_hash is malformed.",
        )
        _require(
            raw_hashes[canonical] == raw_hashes[duplicate] == row["exact_feature_hash"],
            "invalid_ledger",
            f"{location} hash contradicts the referenced source features.",
        )
        _require(
            canonical not in duplicates_for
            and duplicate not in duplicate_of
            and duplicate not in duplicates_for,
            "invalid_ledger",
            f"{location} overlaps another ledger pair.",
        )
        _require(
            isinstance(row["reason"], str) and row["reason"].strip(),
            "invalid_ledger",
            f"{location}.reason must be nonblank.",
        )
        _require(
            isinstance(row["note"], str) and row["note"].strip(),
            "invalid_ledger",
            f"{location}.note must be nonblank.",
        )
        pairs.append((canonical, duplicate))
        duplicate_of[duplicate] = canonical
        duplicates_for.setdefault(canonical, []).append(duplicate)
        hashes[duplicate] = row["exact_feature_hash"]

    groups: Dict[str, List[int]] = {}
    for index, digest in enumerate(raw_hashes):
        groups.setdefault(digest, []).append(index)
    expected_pairs = set(pairs)
    for digest, indices in groups.items():
        if len(indices) <= 1:
            continue
        _require(
            len(indices) == 2 and tuple(indices) in expected_pairs,
            "invalid_ledger",
            "An undeclared duplicate source feature body was found.",
        )

    return _LedgerInfo(
        pairs=tuple(pairs),
        duplicate_of=duplicate_of,
        duplicates_for={
            canonical: tuple(sorted(duplicates))
            for canonical, duplicates in duplicates_for.items()
        },
        hashes=hashes,
    )


def _validate_prepared(
    rows: List[Any],
    catalog: _CatalogInfo,
    expectations: SnapshotExpectations,
) -> Dict[str, Dict[str, Any]]:
    _require(
        len(rows) == expectations.prepared_records,
        "invalid_prepared",
        f"Prepared file has {len(rows)} rows, expected {expectations.prepared_records}.",
    )
    by_id: Dict[str, Dict[str, Any]] = {}
    for index, row in enumerate(rows):
        location = f"prepared[{index}]"
        _require_keys(row, PREPARED_KEYS, location)
        poi_id = row["id"]
        _require(
            isinstance(poi_id, str) and poi_id.strip(),
            "invalid_prepared",
            f"{location}.id must be nonblank.",
        )
        _require(
            poi_id not in by_id,
            "invalid_prepared",
            f"Duplicate prepared id {poi_id!r}.",
        )
        _require(
            isinstance(row["name"], str) and row["name"].strip(),
            "invalid_prepared",
            f"{location}.name must be nonblank.",
        )
        _require(
            _is_number(row["latitude"]) and -90.0 <= row["latitude"] <= 90.0,
            "invalid_prepared",
            f"{location}.latitude must be finite and in range.",
        )
        _require(
            _is_number(row["longitude"]) and -180.0 <= row["longitude"] <= 180.0,
            "invalid_prepared",
            f"{location}.longitude must be finite and in range.",
        )
        _require(
            row["contact_info"] is None,
            "invalid_prepared",
            f"{location}.contact_info must stay null (source has none).",
        )
        _require(
            row["menu"] == [],
            "invalid_prepared",
            f"{location}.menu must stay empty (source has none).",
        )
        _require(
            row["rating"] is None,
            "invalid_prepared",
            f"{location}.rating must stay null (source has none).",
        )
        _require(
            row["tag"] is None,
            "invalid_prepared",
            f"{location}.tag must stay null (source has none).",
        )
        _require(
            row["operation_time"] is None
            or isinstance(row["operation_time"], str),
            "invalid_prepared",
            f"{location}.operation_time must be null or text.",
        )

        categories = row["poi_categories"]
        _require(
            isinstance(categories, list) and len(categories) == 1,
            "invalid_prepared",
            f"{location}.poi_categories must contain exactly one source category.",
        )
        category = categories[0]
        _require_keys(category, CATEGORY_PAYLOAD_KEYS, f"{location}.poi_categories[0]")
        _require(
            category["id"] in catalog.entries_by_id,
            "invalid_prepared",
            f"{location} uses a category outside the catalog.",
        )
        expected_category = catalog.entries_by_id[category["id"]]
        _require(
            category == expected_category,
            "invalid_prepared",
            f"{location} category values contradict the catalog.",
        )

        address = row["address"]
        _require(
            isinstance(address, dict),
            "invalid_prepared",
            f"{location}.address must be an object for this snapshot.",
        )
        _require(
            set(address) <= ADDRESS_PAYLOAD_KEYS,
            "invalid_prepared",
            f"{location}.address has unexpected keys.",
        )
        for key in ("city", "district", "nation"):
            _require(
                isinstance(address.get(key), str) and address[key].strip(),
                "invalid_prepared",
                f"{location}.address.{key} must be nonblank.",
            )
        for key in ("street_name", "ward"):
            _require(
                address.get(key) is None or isinstance(address[key], str),
                "invalid_prepared",
                f"{location}.address.{key} must be null or text.",
            )
        by_id[poi_id] = row
    return by_id


def _validate_lineage(
    rows: List[Any],
    prepared: Mapping[str, Dict[str, Any]],
    raw_features: Sequence[Dict[str, Any]],
    raw_hashes: Sequence[str],
    ledger: _LedgerInfo,
    catalog: _CatalogInfo,
    expectations: SnapshotExpectations,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[int, int]]:
    _require(
        len(rows) == expectations.prepared_records,
        "invalid_lineage",
        f"Lineage file has {len(rows)} rows, expected {expectations.prepared_records}.",
    )
    by_id: Dict[str, Dict[str, Any]] = {}
    index_to_id: Dict[int, str] = {}
    identity_keys = set()
    sequences = set()
    review_required = 0
    for position, row in enumerate(rows):
        location = f"lineage[{position}]"
        _require_keys(row, LINEAGE_KEYS, location)
        poi_id = row["id"]
        _require(
            isinstance(poi_id, str) and poi_id in prepared,
            "invalid_lineage",
            f"{location}.id does not match a prepared record.",
        )
        _require(
            poi_id not in by_id,
            "invalid_lineage",
            f"Duplicate lineage id {poi_id!r}.",
        )
        prepared_row = prepared[poi_id]

        sequence = row["sequence"]
        _require(
            _is_int(sequence) and sequence >= 1,
            "invalid_lineage",
            f"{location}.sequence must be a positive integer.",
        )
        _require(
            sequence not in sequences,
            "invalid_lineage",
            f"{location}.sequence is duplicated.",
        )
        sequences.add(sequence)
        record_id = row["internal_record_id"]
        _require(
            isinstance(record_id, str)
            and record_id == f"r{sequence:06d}",
            "invalid_lineage",
            f"{location}.internal_record_id contradicts its sequence.",
        )

        _require(
            row["catalog_version"] == expectations.catalog_version,
            "invalid_lineage",
            f"{location}.catalog_version contradicts the reviewed catalog.",
        )
        label = row["category_source_label"]
        _require(
            label in catalog.labels,
            "invalid_lineage",
            f"{location}.category_source_label is outside the catalog.",
        )
        expected_category = {
            "id": f"{expectations.namespace}:source-category:{label}",
            "name": catalog.entries[label]["name"],
            "context": catalog.entries[label]["context"],
        }
        _require(
            prepared_row["poi_categories"] == [expected_category],
            "invalid_lineage",
            f"{location} category contradicts the prepared payload.",
        )

        flags = row["review_flags"]
        _require(
            isinstance(flags, list)
            and all(isinstance(flag, str) for flag in flags),
            "invalid_lineage",
            f"{location}.review_flags must be a string array.",
        )
        _require(
            set(flags) <= ALLOWED_REVIEW_FLAGS,
            "invalid_lineage",
            f"{location}.review_flags contains an unknown flag.",
        )
        _require(
            len(flags) == len(set(flags)),
            "invalid_lineage",
            f"{location}.review_flags contains a duplicate flag.",
        )
        if flags:
            review_required += 1

        price = row["price"]
        _require_keys(price, PRICE_KEYS, f"{location}.price")
        _require(
            price["status"] == "unknown",
            "invalid_lineage",
            f"{location}.price.status must stay unknown.",
        )

        operation = row["operation_time"]
        if operation is None:
            _require(
                prepared_row["operation_time"] is None,
                "invalid_lineage",
                f"{location}.operation_time contradicts the prepared payload.",
            )
        else:
            _require(
                isinstance(operation, dict)
                and set(operation) == {"parse_status", "raw"}
                and operation["parse_status"] == "unparsed_source_text"
                and (operation["raw"] is None or isinstance(operation["raw"], str)),
                "invalid_lineage",
                f"{location}.operation_time has an unexpected shape.",
            )
            _require(
                operation["raw"] == prepared_row["operation_time"],
                "invalid_lineage",
                f"{location}.operation_time contradicts the prepared payload.",
            )

        source = row["source"]
        _require_keys(source, SOURCE_KEYS, f"{location}.source")
        canonical_index = source["canonical_source_index"]
        _require(
            _is_int(canonical_index)
            and 0 <= canonical_index < expectations.input_features,
            "invalid_lineage",
            f"{location}.source.canonical_source_index is out of range.",
        )
        _require(
            canonical_index not in index_to_id,
            "invalid_lineage",
            f"Source index {canonical_index} is covered more than once.",
        )
        _require(
            canonical_index not in ledger.duplicate_of,
            "invalid_lineage",
            f"{location} uses a duplicate-only source index.",
        )
        index_to_id[canonical_index] = poi_id

        _require(
            source["input_path"] == expectations.files["geojson"].relative,
            "invalid_lineage",
            f"{location}.source.input_path contradicts the reviewed input path.",
        )
        _require(
            source["input_sha256"] == expectations.files["geojson"].sha256,
            "invalid_lineage",
            f"{location}.source.input_sha256 contradicts the reviewed input hash.",
        )
        _require(
            _is_hash(source["exact_feature_hash"]),
            "invalid_lineage",
            f"{location}.source.exact_feature_hash is malformed.",
        )
        _require(
            _is_int(source["cluster"]),
            "invalid_lineage",
            f"{location}.source.cluster must be an integer.",
        )

        raw_feature = raw_features[canonical_index]
        _require(
            source["geometry"] == raw_feature["geometry"],
            "invalid_lineage",
            f"{location} geometry contradicts the source feature.",
        )
        _require(
            source["raw_properties"] == raw_feature["properties"],
            "invalid_lineage",
            f"{location} raw properties contradict the source feature.",
        )
        _require(
            source["cluster"] == raw_feature["properties"]["cluster"],
            "invalid_lineage",
            f"{location}.source.cluster contradicts the raw properties.",
        )
        _require(
            source["exact_feature_hash"] == raw_hashes[canonical_index],
            "invalid_lineage",
            f"{location} feature hash contradicts the source body.",
        )

        properties = source["raw_properties"]
        _require(
            prepared_row["latitude"] == properties["lat"]
            and prepared_row["longitude"] == properties["lon"],
            "invalid_lineage",
            f"{location} coordinates contradict the prepared payload.",
        )
        _require(
            prepared_row["operation_time"] == properties["opening_ho"],
            "invalid_lineage",
            f"{location} hours contradict the raw source.",
        )

        identity = row["identity"]
        _require_keys(identity, IDENTITY_KEYS, f"{location}.identity")
        _require(
            identity["namespace"] == expectations.namespace,
            "invalid_lineage",
            f"{location}.identity.namespace contradicts the reviewed namespace.",
        )
        _require(
            identity["identity_scope"] == "internal_local_only",
            "invalid_lineage",
            f"{location}.identity.identity_scope must stay internal_local_only.",
        )
        _require(
            identity["cross_export_matching"] == "not_guaranteed",
            "invalid_lineage",
            f"{location}.identity.cross_export_matching must stay not_guaranteed.",
        )
        _require(
            identity["raw_name"] == properties["name"],
            "invalid_lineage",
            f"{location}.identity.raw_name contradicts the raw source.",
        )
        _require(
            identity["processed_name"] == properties["processed_name"],
            "invalid_lineage",
            f"{location}.identity.processed_name contradicts the raw source.",
        )
        processed_name = identity["processed_name"]
        expected_name = (
            processed_name
            if isinstance(processed_name, str) and processed_name.strip()
            else identity["raw_name"]
        )
        _require(
            prepared_row["name"] == expected_name,
            "invalid_lineage",
            f"{location} name contradicts the prepared payload.",
        )
        expected_name_source = (
            "processed_name"
            if isinstance(processed_name, str) and processed_name.strip()
            else "raw_name_fallback"
        )
        _require(
            identity["name_source"] == expected_name_source,
            "invalid_lineage",
            f"{location}.identity.name_source contradicts the name used.",
        )
        _require(
            isinstance(identity["derivation"], str) and identity["derivation"].strip(),
            "invalid_lineage",
            f"{location}.identity.derivation must be nonblank.",
        )
        _require(
            isinstance(identity["name_key"], str),
            "invalid_lineage",
            f"{location}.identity.name_key must be text.",
        )
        _require(
            isinstance(identity["address_anchor"], str),
            "invalid_lineage",
            f"{location}.identity.address_anchor must be text.",
        )
        coordinates_token = identity["coordinates_token"]
        _require(
            isinstance(coordinates_token, str),
            "invalid_lineage",
            f"{location}.identity.coordinates_token must be text.",
        )
        token_parts = coordinates_token.split(",")
        _require(
            len(token_parts) == 2,
            "invalid_lineage",
            f"{location}.identity.coordinates_token must contain lon,lat.",
        )
        try:
            token_lon = float(token_parts[0])
            token_lat = float(token_parts[1])
        except ValueError:
            _fail(
                "invalid_lineage",
                f"{location}.identity.coordinates_token is not numeric.",
            )
        _require(
            math.isclose(token_lon, properties["lon"], rel_tol=0.0, abs_tol=1e-9)
            and math.isclose(token_lat, properties["lat"], rel_tol=0.0, abs_tol=1e-9),
            "invalid_lineage",
            f"{location}.identity.coordinates_token contradicts the geometry.",
        )
        expected_identity_key = "|".join(
            (
                identity["namespace"],
                identity["name_key"],
                coordinates_token,
                identity["address_anchor"],
            )
        )
        _require(
            identity["identity_key"] == expected_identity_key,
            "invalid_lineage",
            f"{location}.identity.identity_key contradicts its components.",
        )
        _require(
            identity["identity_key"] not in identity_keys,
            "invalid_lineage",
            f"{location}.identity.identity_key is duplicated.",
        )
        identity_keys.add(identity["identity_key"])

        address = row["address"]
        _require_keys(address, ADDRESS_EVIDENCE_KEYS, f"{location}.address")
        _require(
            address["scope"] == SOURCE_AREA_SCOPE,
            "invalid_lineage",
            f"{location}.address.scope must stay source_snapshot_area_only.",
        )
        _require(
            address["current_admin_claim"] == "none",
            "invalid_lineage",
            f"{location}.address.current_admin_claim must stay none.",
        )
        prepared_address = prepared_row["address"]
        _require(
            address["payload_city"] == prepared_address["city"]
            and address["payload_district"] == prepared_address["district"],
            "invalid_lineage",
            f"{location} payload address contradicts the prepared payload.",
        )
        for raw_key, property_key in (
            ("raw_city", "addr_city"),
            ("raw_district", "addr_district"),
            ("raw_full", "addr_full"),
            ("raw_house", "addr_house"),
            ("raw_stree", "addr_stree"),
            ("raw_ward", "addr_ward"),
        ):
            _require(
                address[raw_key] == properties[property_key],
                "invalid_lineage",
                f"{location}.address.{raw_key} contradicts the raw source.",
            )
        expected_street = " ".join(
            part for part in (address["raw_house"], address["raw_stree"]) if part
        )
        _require(
            (prepared_address.get("street_name") or "") == expected_street,
            "invalid_lineage",
            f"{location} street_name contradicts the source address.",
        )
        _require(
            (prepared_address.get("ward") or None) == (address["raw_ward"] or None),
            "invalid_lineage",
            f"{location} ward contradicts the source address.",
        )

        provenance = row["provenance"]
        _require_keys(provenance, PROVENANCE_KEYS, f"{location}.provenance")
        _require(
            provenance["provided_at"] == expectations.provided_at,
            "invalid_lineage",
            f"{location}.provenance.provided_at contradicts the reviewed date.",
        )
        for field in UNKNOWN_FIELDS:
            _require(
                provenance[field] == UNKNOWN,
                "invalid_lineage",
                f"{location}.provenance.{field} must stay UNKNOWN.",
            )

        by_id[poi_id] = row

    _require(
        set(by_id) == set(prepared),
        "invalid_lineage",
        "Lineage and prepared ids are not the same exact set.",
    )

    canonical_indices = set(index_to_id)
    duplicate_indices = set(ledger.duplicate_of)
    _require(
        not (canonical_indices & duplicate_indices),
        "invalid_lineage",
        "A source index is both canonical and duplicate.",
    )
    covered = canonical_indices | duplicate_indices
    expected_indices = set(range(expectations.input_features))
    _require(
        covered == expected_indices,
        "invalid_lineage",
        "Source indices are not exactly conserved across canonical and duplicate rows.",
    )
    _require(
        len(canonical_indices) == expectations.prepared_records,
        "invalid_lineage",
        "Canonical source-index count contradicts the prepared count.",
    )
    _require(
        len(covered) == len(canonical_indices) + len(duplicate_indices),
        "invalid_lineage",
        "A source index is covered more than once.",
    )
    return by_id, index_to_id


def _validate_registry(
    registry: Any,
    prepared: Mapping[str, Dict[str, Any]],
    lineage: Mapping[str, Dict[str, Any]],
    expectations: SnapshotExpectations,
    summary_facts: Mapping[str, Any],
) -> Dict[str, Any]:
    _require(
        isinstance(registry, dict),
        "invalid_registry",
        "Identity registry must be an object.",
    )
    required = {
        "cross_export_matching",
        "identity_index",
        "identity_scope",
        "input_sha256",
        "namespace",
        "next_sequence",
        "prior_input_sha256",
        "records",
        "registry_version",
        "source_type",
    }
    _require(
        set(registry) == required,
        "invalid_registry",
        "Identity registry has unexpected top-level keys.",
    )
    _require(
        registry["namespace"] == expectations.namespace,
        "invalid_registry",
        "Registry namespace contradicts the reviewed namespace.",
    )
    _require(
        registry["source_type"] == expectations.source_type,
        "invalid_registry",
        "Registry source type contradicts the reviewed source type.",
    )
    _require(
        registry["identity_scope"] == "internal_local_only",
        "invalid_registry",
        "Registry identity scope must stay internal_local_only.",
    )
    _require(
        registry["cross_export_matching"] == "not_guaranteed",
        "invalid_registry",
        "Registry cross-export matching must stay not_guaranteed.",
    )
    _require(
        registry["input_sha256"] == expectations.files["geojson"].sha256,
        "invalid_registry",
        "Registry input hash contradicts the reviewed input hash.",
    )
    _require(
        _is_int(registry["registry_version"]) and registry["registry_version"] >= 1,
        "invalid_registry",
        "Registry version must be a positive integer.",
    )
    _require(
        _is_int(registry["next_sequence"]) and registry["next_sequence"] >= 0,
        "invalid_registry",
        "Registry next_sequence must be a nonnegative integer.",
    )
    _require(
        registry["next_sequence"] == summary_facts["next_sequence"],
        "invalid_registry",
        "Registry next_sequence contradicts the summary.",
    )
    prior = registry["prior_input_sha256"]
    _require(
        isinstance(prior, list) and all(_is_hash(item) for item in prior),
        "invalid_registry",
        "Registry prior_input_sha256 must be a list of SHA256 values.",
    )

    records = registry["records"]
    index = registry["identity_index"]
    _require(
        isinstance(records, dict) and isinstance(index, dict),
        "invalid_registry",
        "Registry records and identity_index must be objects.",
    )
    _require(
        set(records) == set(prepared),
        "invalid_registry",
        "Registry ids are not the exact prepared id set.",
    )
    _require(
        len(index) == expectations.prepared_records,
        "invalid_registry",
        "Registry identity_index size contradicts the prepared count.",
    )

    expected_index: Dict[str, str] = {}
    record_ids = set()
    sequences = set()
    for poi_id in sorted(records):
        record = records[poi_id]
        _require_keys(record, REGISTRY_RECORD_KEYS, f"registry.records[{poi_id}]")
        lineage_row = lineage[poi_id]
        _require(
            record["record_id"] == lineage_row["internal_record_id"],
            "invalid_registry",
            f"Registry record id contradicts lineage for {poi_id!r}.",
        )
        _require(
            record["sequence"] == lineage_row["sequence"],
            "invalid_registry",
            f"Registry sequence contradicts lineage for {poi_id!r}.",
        )
        _require(
            record["identity_key"] == lineage_row["identity"]["identity_key"],
            "invalid_registry",
            f"Registry identity key contradicts lineage for {poi_id!r}.",
        )
        _require(
            record["record_id"] not in record_ids,
            "invalid_registry",
            f"Registry record id {record['record_id']!r} is duplicated.",
        )
        record_ids.add(record["record_id"])
        _require(
            record["sequence"] not in sequences,
            "invalid_registry",
            f"Registry sequence {record['sequence']!r} is duplicated.",
        )
        sequences.add(record["sequence"])

        identity = record["identity"]
        _require_keys(identity, REGISTRY_IDENTITY_KEYS, f"registry.records[{poi_id}].identity")
        source_identity = lineage_row["identity"]
        _require(
            identity["address_anchor"] == source_identity["address_anchor"]
            and identity["coordinates"] == source_identity["coordinates_token"]
            and identity["name_key"] == source_identity["name_key"]
            and identity["processed_name"] == source_identity["processed_name"]
            and identity["raw_name"] == source_identity["raw_name"],
            "invalid_registry",
            f"Registry identity values contradict lineage for {poi_id!r}.",
        )

        expected_id = (
            f"{expectations.source_type}:"
            f"{_sha256_text(expectations.source_type + chr(0x1F) + record['record_id'])[:32]}"
        )
        _require(
            poi_id == expected_id,
            "invalid_registry",
            f"Registry id {poi_id!r} does not match its record-id derivation.",
        )
        expected_index[record["identity_key"]] = poi_id

    _require(
        index == expected_index,
        "invalid_registry",
        "Registry identity_index contradicts its records.",
    )
    _require(
        len(set(index.values())) == len(index),
        "invalid_registry",
        "Registry identity_index maps multiple keys to one id.",
    )
    _require(
        registry["next_sequence"] >= max(sequences),
        "invalid_registry",
        "Registry next_sequence is behind an assigned sequence.",
    )
    return {
        "records": len(records),
        "identity_index": len(index),
        "next_sequence": registry["next_sequence"],
    }


def _build_metadata(
    lineage_row: Mapping[str, Any],
    ledger: _LedgerInfo,
    expectations: SnapshotExpectations,
) -> Dict[str, Any]:
    raw_lineage_json = canonical_json(lineage_row)
    canonical_index = lineage_row["source"]["canonical_source_index"]
    identity = lineage_row["identity"]
    address = lineage_row["address"]
    source = lineage_row["source"]
    provenance = lineage_row["provenance"]
    return {
        "dataset_namespace": identity["namespace"],
        "identity_scope": identity["identity_scope"],
        "cross_export_matching": identity["cross_export_matching"],
        "administrative_scope": address["scope"],
        "input_sha256": source["input_sha256"],
        "feature_sha256": source["exact_feature_hash"],
        "canonical_source_index": canonical_index,
        "duplicate_source_indices": list(
            ledger.duplicates_for.get(canonical_index, ())
        ),
        "internal_record_id": lineage_row["internal_record_id"],
        "provided_at": expectations.provided_at,
        "collection_time": None,
        "source_url": None,
        "license": None,
        "freshness": None,
        "raw_lineage_json": raw_lineage_json,
        "raw_lineage_sha256": _sha256_text(raw_lineage_json),
    }


def _build_manifest(
    expectations: SnapshotExpectations,
    input_files: Mapping[str, Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
    prepared_bytes: bytes,
    category_ids: Sequence[str],
    ledger: _LedgerInfo,
    summary_facts: Mapping[str, Any],
    registry_facts: Mapping[str, Any],
) -> Dict[str, Any]:
    duplicate_indices = sorted(ledger.duplicate_of)
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "manifest_schema": MANIFEST_SCHEMA,
        "adapter_version": ADAPTER_VERSION,
        "task_id": TASK_ID,
        "dataset_class": expectations.dataset_class,
        "real_supplied_primary_dataset": expectations.real,
        "synthetic_fixture": not expectations.real,
        "source_snapshot_area_only": True,
        "administrative_labels_are_current_jurisdiction": False,
        "admin_current_unverified": True,
        "internal_local_only": True,
        "cross_export_matching_guaranteed": False,
        "reviewed_exact_snapshot_binding": True,
        "arbitrary_hash_acceptance": False,
        "general_dataset_class_enforcement": False,
        "future_real_synthetic_expansion_write_boundary": "T050",
        "namespace": expectations.namespace,
        "source_type": expectations.source_type,
        "provided_at": expectations.provided_at,
        "provided_at_is_snapshot_freshness": False,
        "catalog_version": expectations.catalog_version,
        "unknowns": {
            "collection_time": UNKNOWN,
            "source_url": UNKNOWN,
            "license": UNKNOWN,
            "freshness": UNKNOWN,
        },
        "scope_limits": [
            "source_snapshot_area_only: administrative labels are source claims, not present-day containment",
            "internal_local_only: ids are internal and are not upstream/source identifiers",
            "cross_export_matching is not guaranteed",
            "collection time, source URL, license and freshness are UNKNOWN",
            "coordinate/name/category values are preserved, not repaired or enriched",
            "no graph, network, model, Docker or API call is performed by this adapter",
        ],
        "inputs": input_files,
        "counts": {
            "input_features": expectations.input_features,
            "prepared_records": len(records),
            "duplicate_ledger_records": len(ledger.pairs),
            "source_indices_accounted": expectations.input_features,
            "category_count": len(category_ids),
            "prepared_review_required": summary_facts[
                "prepared_review_required"
            ],
            "input_quarantine": 0,
            "model_validated_records": len(records),
            "registry_records": registry_facts["records"],
            "identity_index_records": registry_facts["identity_index"],
            "summary_prepared_review_required": summary_facts[
                "prepared_review_required"
            ],
        },
        "index_accounting": {
            "canonical_source_indices": len(records),
            "duplicate_source_indices": duplicate_indices,
            "covered_source_indices": len(records) + len(duplicate_indices),
            "expected_source_indices": expectations.input_features,
            "each_source_index_exactly_once": True,
            "ledger_pairs": [
                {
                    "canonical_source_index": canonical,
                    "duplicate_source_index": duplicate,
                    "exact_feature_hash": ledger.hashes[duplicate],
                }
                for canonical, duplicate in ledger.pairs
            ],
        },
        "category_ids": sorted(category_ids),
        "outputs": {
            PREPARED_FILENAME: {
                "records": len(records),
                "bytes": len(prepared_bytes),
                "sha256": _sha256_bytes(prepared_bytes),
            }
        },
        "not_claimed": [
            "accepted graph nodes",
            "verified venues",
            "fresh data",
            "genuine upstream/source identifiers",
            "present-day administrative containment",
            "routes",
            "primary H2/H3 completion",
            "full goal completion",
        ],
    }
    return manifest


def _build_checksums(
    prepared_bytes: bytes,
    manifest_bytes: bytes,
) -> bytes:
    lines = sorted(
        [
            f"{_sha256_bytes(manifest_bytes)}  {MANIFEST_FILENAME}",
            f"{_sha256_bytes(prepared_bytes)}  {PREPARED_FILENAME}",
        ]
    )
    return ("\n".join(lines) + "\n").encode("utf-8")


def prepare_snapshot(
    base_dir: Path | str,
    expectations: SnapshotExpectations = REAL_EXPECTATIONS,
) -> SnapshotPlan:
    """Verify every input and build an in-memory graph-ready candidate plan."""
    base = Path(base_dir)
    _validate_expectations(expectations)

    loaded: Dict[str, Tuple[Path, bytes]] = {}
    for name in ("geojson", "prepared", "lineage", "registry", "catalog", "ledger", "summary"):
        loaded[name] = _read_checked(base, expectations.files[name])
    if expectations.provenance_manifest is not None:
        loaded["provenance_manifest"] = _read_checked(
            base, expectations.provenance_manifest
        )
    if expectations.snapshot_manifest is not None:
        loaded["snapshot_manifest"] = _read_checked(
            base, expectations.snapshot_manifest
        )
    _require(
        (expectations.provenance_manifest is None)
        == (expectations.snapshot_manifest is None),
        "invalid_expectations",
        "Both source manifests must be supplied together or omitted together.",
    )

    catalog = _validate_catalog(_load_json(loaded["catalog"][1], "catalog"), expectations)
    summary_facts = _validate_summary(
        _load_json(loaded["summary"][1], "summary"), expectations, catalog
    )
    _validate_source_manifests(loaded, expectations)

    raw_features, raw_hashes = _validate_raw_geojson(
        _load_json(loaded["geojson"][1], "geojson"), expectations, catalog
    )
    ledger = _validate_ledger(
        _load_jsonl(loaded["ledger"][1], "ledger"), raw_hashes, expectations
    )
    prepared = _validate_prepared(
        _load_jsonl(loaded["prepared"][1], "prepared"), catalog, expectations
    )
    lineage, _ = _validate_lineage(
        _load_jsonl(loaded["lineage"][1], "lineage"),
        prepared,
        raw_features,
        raw_hashes,
        ledger,
        catalog,
        expectations,
    )
    registry_facts = _validate_registry(
        _load_json(loaded["registry"][1], "registry"),
        prepared,
        lineage,
        expectations,
        summary_facts,
    )

    actual_review_required = sum(
        1 for row in lineage.values() if row["review_flags"]
    )
    _require(
        actual_review_required == summary_facts["prepared_review_required"],
        "invalid_summary",
        "Summary review-required count contradicts lineage flags.",
    )
    _require(
        registry_facts["records"] == expectations.prepared_records,
        "invalid_registry",
        "Registry record count contradicts the prepared count.",
    )

    records: List[Dict[str, Any]] = []
    for poi_id in sorted(lineage):
        payload = dict(prepared[poi_id])
        payload["source_metadata"] = _build_metadata(
            lineage[poi_id], ledger, expectations
        )
        try:
            POI.model_validate(payload)
        except Exception as exc:
            _fail(
                "model_validation_failed",
                f"Prepared id {poi_id!r} failed POI model validation: {exc}",
            )
        records.append(payload)

    prepared_bytes = (
        "\n".join(canonical_json(record) for record in records) + "\n"
    ).encode("utf-8")

    input_files: Dict[str, Dict[str, Any]] = {}
    for name in sorted(loaded):
        binding = (
            expectations.files.get(name)
            or (
                expectations.provenance_manifest
                if name == "provenance_manifest"
                else expectations.snapshot_manifest
            )
        )
        _require(
            binding is not None,
            "invalid_expectations",
            f"No reviewed binding for loaded input {name!r}.",
        )
        path, data = loaded[name]
        input_files[name] = {
            "path": binding.relative,
            "bytes": len(data),
            "sha256": _sha256_bytes(data),
        }

    manifest = _build_manifest(
        expectations=expectations,
        input_files=input_files,
        records=records,
        prepared_bytes=prepared_bytes,
        category_ids=sorted(catalog.labels),
        ledger=ledger,
        summary_facts=summary_facts,
        registry_facts=registry_facts,
    )
    manifest_bytes = (
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    checksums_bytes = _build_checksums(prepared_bytes, manifest_bytes)

    return SnapshotPlan(
        real=expectations.real,
        expectations=expectations,
        records=tuple(records),
        prepared_bytes=prepared_bytes,
        manifest=manifest,
        manifest_bytes=manifest_bytes,
        checksums_bytes=checksums_bytes,
        input_files=input_files,
    )


def write_plan(plan: SnapshotPlan, output_dir: Path | str) -> Path:
    """Write a fully validated plan without overwriting any existing path."""
    destination = Path(output_dir)
    resolved = destination.resolve()
    real_destination = REAL_OUTPUT_DIR.resolve()

    if plan.real:
        _require(
            resolved == real_destination,
            "output_not_allowed",
            "Real snapshot output is restricted to data/primary_20261016/graph_ready_v2.",
        )
    else:
        _require(
            resolved != real_destination,
            "output_not_allowed",
            "A synthetic fixture can never write the real graph-ready destination.",
        )
    _require(
        not destination.exists(),
        "output_exists",
        f"Refusing to overwrite existing destination {destination}.",
    )
    _require(
        destination.parent.is_dir(),
        "output_parent_missing",
        f"Output parent does not exist: {destination.parent}.",
    )
    try:
        destination.mkdir()
    except FileExistsError:
        _fail("output_exists", f"Refusing to overwrite existing destination {destination}.")

    payloads = (
        (PREPARED_FILENAME, plan.prepared_bytes),
        (MANIFEST_FILENAME, plan.manifest_bytes),
        (CHECKSUMS_FILENAME, plan.checksums_bytes),
    )
    for name, data in payloads:
        target = destination / name
        with open(target, "xb") as handle:
            handle.write(data)
    return destination


def _summary_payload(plan: SnapshotPlan) -> Dict[str, Any]:
    return {
        "status": "validated",
        "real": plan.real,
        "dataset_class": plan.expectations.dataset_class,
        "records": len(plan.records),
        "manifest": plan.manifest,
        "prepared_sha256": _sha256_bytes(plan.prepared_bytes),
        "prepared_bytes": len(plan.prepared_bytes),
        "manifest_sha256": _sha256_bytes(plan.manifest_bytes),
        "checksums_sha256": _sha256_bytes(plan.checksums_bytes),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fail-closed graph-ready adapter for the exact reviewed primary "
            "POI snapshot (offline; no graph/model/network call)."
        )
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--check",
        action="store_true",
        help="Verify all inputs and build the plan in memory without writing.",
    )
    action.add_argument(
        "--write",
        action="store_true",
        help="Write the validated plan to the reviewed graph_ready_v2 destination.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help=(
            "Output directory (defaults to the reviewed graph_ready_v2 path; "
            "real plans can only write there)."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable summary.",
    )
    args = parser.parse_args(argv)

    try:
        plan = prepare_snapshot(REPO_ROOT, REAL_EXPECTATIONS)
        if args.check:
            summary = _summary_payload(plan)
        else:
            destination = write_plan(
                plan, REAL_OUTPUT_DIR if args.out is None else args.out
            )
            summary = _summary_payload(plan)
            summary["written_to"] = str(destination)
    except SnapshotError as exc:
        if args.json:
            print(json.dumps({"status": "rejected", "code": exc.code, "error": exc.message}))
        else:
            print(f"REJECTED [{exc.code}]: {exc.message}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(summary, sort_keys=True, ensure_ascii=False))
    else:
        print(
            f"{summary['status']}: {summary['records']} records, "
            f"prepared_sha256={summary['prepared_sha256']}, "
            f"manifest_sha256={summary['manifest_sha256']}"
        )
        if "written_to" in summary:
            print(f"written_to={summary['written_to']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
