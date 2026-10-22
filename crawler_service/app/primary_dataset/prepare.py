"""Deterministic, offline preparation of the primary GeoJSON into candidates.

Pipeline (all validation happens before the first byte is written):

1. read and hash the immutable input; validate it is a GeoJSON FeatureCollection;
2. collapse only byte-equivalent canonical feature duplicates (both source
   indices and the reason are recorded in a duplicate ledger);
3. resolve a persistent *internal* identity for every distinct feature via the
   local registry (collisions and silent reidentification fail closed);
4. build POI payloads in the closed source-category catalog and validate them
   with the *actual* POI domain model;
5. write prepared payloads, lineage, quarantine, the duplicate ledger, the
   category catalog and a summary -- atomically, with no live ingestion.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from crawler_service.app.acquisition.resolution import ConfigError
from crawler_service.app.acquisition.storage import atomic_write_bytes

from . import (
    DEFAULT_INPUT,
    DEFAULT_OUT_DIR,
    INTERNAL_SOURCE_TYPE,
    PREP_VERSION,
    PRIMARY_NAMESPACE,
)
from .catalog import CATALOG, CATALOG_VERSION, catalog_payload
from .identity import (
    address_anchor,
    canonical_name,
    coord_token,
    exact_feature_hash,
    identity_components,
    identity_key,
    name_key_for,
)
from .registry import IdentityRegistry
from .validation import load_poi_model

LEGACY_ADMIN_LABELS = {"Di An", "Thuan An", "Thu Dau Mot"}
LEGACY_ADMIN_FLAG = "legacy_admin_qualification_unresolved"


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value == value
        and value not in (float("inf"), float("-inf"))
    )


def _finite_in_range(value: Any, low: float, high: float) -> bool:
    return _is_finite_number(value) and low <= float(value) <= high


def _nonblank(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _combine_street(properties: Mapping[str, Any]) -> Optional[str]:
    house = _nonblank(properties.get("addr_house"))
    street = _nonblank(properties.get("addr_stree"))
    combined = " ".join(part for part in (house, street) if part).strip()
    return combined or None


def resolve_coordinates(feature: Mapping[str, Any], properties: Mapping[str, Any]) -> Tuple[Any, Any, List[str]]:
    """Resolve lat/lon from the property fields, cross-checked with the geometry."""

    reasons: List[str] = []
    geometry = feature.get("geometry")
    if geometry is None:
        return None, None, ["missing_geometry"]
    if not isinstance(geometry, dict):
        return None, None, ["invalid_geometry"]
    if geometry.get("type") != "Point":
        reasons.append("unsupported_geometry_kind")
    coordinates = geometry.get("coordinates")
    if not (isinstance(coordinates, list) and len(coordinates) == 2):
        reasons.append("invalid_geometry_coordinates")
    lat = properties.get("lat")
    lon = properties.get("lon")
    if not (_finite_in_range(lat, -90.0, 90.0) and _finite_in_range(lon, -180.0, 180.0)):
        reasons.append("missing_or_invalid_coordinates")
        return None, None, reasons
    return float(lat), float(lon), reasons


def _build_address(properties: Mapping[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    raw_city = properties.get("addr_city")
    raw_district = properties.get("addr_district")
    city = _nonblank(raw_city)
    district = _nonblank(raw_district)
    reasons: List[str] = []
    if not city:
        reasons.append("missing_source_city")
    if not district:
        reasons.append("missing_source_district")
    if not city or not district:
        return None, reasons
    address: Dict[str, Any] = {
        "city": city,
        "district": district,
        "nation": "Vietnam",
    }
    street = _combine_street(properties)
    if street:
        address["street_name"] = street
    ward = _nonblank(properties.get("addr_ward"))
    if ward:
        address["ward"] = ward
    return address, reasons


@dataclass
class PrepareResult:
    summary: Dict[str, Any]
    outputs: Dict[str, Path] = field(default_factory=dict)
    registry_path: Path = Path()
    assigned_in_this_run: int = 0
    registry_changed: bool = False
    revision_accepted: bool = False


def _load_input(input_path: Path) -> Tuple[bytes, Dict[str, Any], List[Any]]:
    if not input_path.is_file():
        raise ConfigError(f"input dataset does not exist: {input_path}")
    raw_bytes = input_path.read_bytes()
    try:
        document = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"input {input_path} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        raise ConfigError(f"input {input_path} is not a GeoJSON FeatureCollection")
    features = document.get("features")
    if not isinstance(features, list):
        raise ConfigError(f"input {input_path} has no 'features' list")
    return raw_bytes, document, features


def _json_line(row: Mapping[str, Any]) -> bytes:
    return (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _jsonl_bytes(rows: List[Mapping[str, Any]]) -> bytes:
    return b"".join(_json_line(row) for row in rows)


def prepare_primary_dataset(
    input_path: Path = Path(DEFAULT_INPUT),
    out_dir: Path = Path(DEFAULT_OUT_DIR),
    registry_path: Optional[Path] = None,
    *,
    provided_at: str = "2026-10-16",
    accept_input_revision: bool = False,
) -> PrepareResult:
    """Prepare the dataset into honest, schema-validated import candidates."""

    input_path = Path(input_path)
    out_dir = Path(out_dir)
    registry_path = Path(registry_path) if registry_path is not None else out_dir / "identity_registry.json"
    if out_dir.exists() and not out_dir.is_dir():
        raise ConfigError(f"output path is not a directory: {out_dir}")

    raw_bytes, _document, features = _load_input(input_path)
    input_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    poi_model = load_poi_model()
    registry = IdentityRegistry.load(registry_path)

    prepared_rows: List[Dict[str, Any]] = []
    lineage_rows: List[Dict[str, Any]] = []
    quarantine_rows: List[Dict[str, Any]] = []
    duplicate_rows: List[Dict[str, Any]] = []
    identities: Dict[str, Dict[str, Any]] = {}
    identity_by_index: Dict[int, str] = {}
    prepared_indices: set = set()

    seen_feature_hash: Dict[str, int] = {}
    duplicate_extra = 0

    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            quarantine_rows.append(
                {
                    "source_index": index,
                    "reason_codes": ["feature_not_object"],
                }
            )
            continue

        feature_hash = exact_feature_hash(feature)
        if feature_hash in seen_feature_hash:
            duplicate_extra += 1
            duplicate_rows.append(
                {
                    "canonical_source_index": seen_feature_hash[feature_hash],
                    "duplicate_source_index": index,
                    "exact_feature_hash": feature_hash,
                    "reason": "byte_equivalent_canonical_feature",
                    "note": (
                        "The two features are byte-equivalent after canonical JSON "
                        "serialization; one prepared record is retained and both "
                        "source indices are preserved. No other duplicate is merged."
                    ),
                }
            )
            continue
        seen_feature_hash[feature_hash] = index

        properties = feature.get("properties")
        if not isinstance(properties, dict):
            properties = {}

        reasons: List[str] = []
        display_name, raw_name, name_source = canonical_name(properties)
        if not display_name:
            reasons.append("missing_name")

        lat, lon, coord_reasons = resolve_coordinates(feature, properties)
        reasons.extend(coord_reasons)

        category_label = properties.get("poi_category")
        category = catalog_payload(category_label)
        if category is None:
            reasons.append("unknown_source_category")

        address, address_reasons = _build_address(properties)
        reasons.extend(address_reasons)

        if reasons:
            quarantine_rows.append(
                {
                    "source_index": index,
                    "exact_feature_hash": feature_hash,
                    "reason_codes": sorted(set(reasons)),
                    "raw_name": raw_name,
                    "poi_category": category_label,
                    "raw_properties": properties,
                    "note": "Preserved in quarantine; no field was invented to force acceptance.",
                }
            )
            continue

        key = identity_key(
            name_key_for(properties), coord_token(lat, lon), address_anchor(properties)
        )
        components = identity_components(properties)
        existing = identities.get(key)
        if existing is not None and existing != components:
            raise ConfigError(
                f"identity collision for key {key!r} at source index {index}; two "
                "distinct features claim the same identity (fail closed)"
            )
        if existing is not None:
            raise ConfigError(
                f"two distinct features share identity key {key!r} (source index "
                f"{index} and {identity_by_index.get(key)}); require explicit review"
            )
        identities[key] = components
        identity_by_index[key] = index
        prepared_indices.add(index)

    known_before = set(registry.identity_index)
    assigned_in_this_run = sum(1 for key in identities if key not in known_before)
    plan = registry.plan(
        identities, input_sha256=input_sha256, accept_input_revision=accept_input_revision
    )

    review_flags_counter: Dict[str, int] = {}
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            continue
        if index not in prepared_indices:
            continue
        feature_hash = exact_feature_hash(feature)
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            properties = {}

        lat, lon, _coord_reasons = resolve_coordinates(feature, properties)
        if lat is None:
            continue
        display_name, raw_name, name_source = canonical_name(properties)
        if not display_name:
            continue
        category = catalog_payload(properties.get("poi_category"))
        if category is None:
            continue
        address, _address_reasons = _build_address(properties)
        if address is None:
            continue

        key = identity_key(
            name_key_for(properties), coord_token(lat, lon), address_anchor(properties)
        )
        stable_id = plan.ids_by_identity_key.get(key)
        if stable_id is None:
            raise ConfigError(
                f"internal identity plan has no id for key {key!r} (fail closed)"
            )
        record = registry.records[stable_id]

        hours = _nonblank(properties.get("opening_ho"))
        payload: Dict[str, Any] = {
            "id": stable_id,
            "name": display_name,
            "latitude": lat,
            "longitude": lon,
            "poi_categories": [dict(category)],
            "address": dict(address),
            "operation_time": hours,
            "menu": [],
            "rating": None,
            "contact_info": None,
            "tag": None,
        }
        try:
            poi_model.model_validate(payload)
        except Exception as exc:
            quarantine_rows.append(
                {
                    "source_index": index,
                    "exact_feature_hash": feature_hash,
                    "reason_codes": ["poi_model_validation_failed"],
                    "validation_error": str(exc),
                    "raw_properties": properties,
                }
            )
            continue

        district = _nonblank(properties.get("addr_district")) or ""
        review_flags: List[str] = []
        if district in LEGACY_ADMIN_LABELS:
            review_flags.append(LEGACY_ADMIN_FLAG)
            review_flags_counter[LEGACY_ADMIN_FLAG] = (
                review_flags_counter.get(LEGACY_ADMIN_FLAG, 0) + 1
            )

        prepared_rows.append(payload)
        lineage_rows.append(
            {
                "id": stable_id,
                "internal_record_id": record["record_id"],
                "sequence": record["sequence"],
                "identity": {
                    "namespace": PRIMARY_NAMESPACE,
                    "identity_scope": "internal_local_only",
                    "cross_export_matching": "not_guaranteed",
                    "identity_key": key,
                    "derivation": "normalized_name + exact_coordinates + source_address_anchor",
                    "name_key": name_key_for(properties),
                    "coordinates_token": coord_token(lat, lon),
                    "address_anchor": address_anchor(properties),
                    "name_source": name_source,
                    "raw_name": raw_name,
                    "processed_name": properties.get("processed_name"),
                },
                "source": {
                    "input_path": input_path.as_posix(),
                    "input_sha256": input_sha256,
                    "canonical_source_index": index,
                    "exact_feature_hash": feature_hash,
                    "geometry": feature.get("geometry"),
                    "raw_properties": properties,
                    "cluster": properties.get("cluster"),
                },
                "catalog_version": CATALOG_VERSION,
                "category_source_label": properties.get("poi_category"),
                "address": {
                    "scope": "source_snapshot_area_only",
                    "raw_city": properties.get("addr_city"),
                    "raw_district": properties.get("addr_district"),
                    "raw_ward": properties.get("addr_ward"),
                    "raw_house": properties.get("addr_house"),
                    "raw_stree": properties.get("addr_stree"),
                    "raw_full": properties.get("addr_full"),
                    "payload_city": address.get("city"),
                    "payload_district": address.get("district"),
                    "current_admin_claim": "none",
                },
                "operation_time": (
                    {"raw": hours, "parse_status": "unparsed_source_text"}
                    if hours
                    else None
                ),
                "price": {"status": "unknown", "note": "no price field exists in the source"},
                "provenance": {
                    "provided_at": provided_at,
                    "collection_time": "UNKNOWN",
                    "source_url": "UNKNOWN",
                    "license": "UNKNOWN",
                    "freshness": "UNKNOWN",
                },
                "review_flags": review_flags,
            }
        )

    prepared_rows.sort(key=lambda row: row["id"])
    lineage_rows.sort(key=lambda row: row["id"])
    quarantine_rows.sort(key=lambda row: row.get("source_index", -1))
    duplicate_rows.sort(key=lambda row: row["duplicate_source_index"])

    candidate_features = len(features) - duplicate_extra
    quarantine_counts: Dict[str, int] = {}
    for row in quarantine_rows:
        for reason in row["reason_codes"]:
            quarantine_counts[reason] = quarantine_counts.get(reason, 0) + 1

    counts = {
        "input_features": len(features),
        "exact_duplicate_extra": duplicate_extra,
        "candidate_features": candidate_features,
        "prepared": len(prepared_rows),
        "quarantine": len(quarantine_rows),
        "prepared_review_required": sum(1 for row in lineage_rows if row["review_flags"]),
    }
    summary: Dict[str, Any] = {
        "prep_version": PREP_VERSION,
        "task_id": "OC-034",
        "status": "prepared/schema-validated candidates",
        "namespace": PRIMARY_NAMESPACE,
        "internal_source_type": INTERNAL_SOURCE_TYPE,
        "dataset": {
            "input_path": input_path.as_posix(),
            "input_sha256": input_sha256,
            "input_bytes": len(raw_bytes),
            "input_features": len(features),
            "declared_provided_at": provided_at,
        },
        "catalog": {
            "catalog_version": CATALOG_VERSION,
            "size": len(CATALOG),
            "categories": [
                {"id": row["id"], "name": row["name"], "source_label": row["source_label"]}
                for row in CATALOG
            ],
        },
        "identity": {
            "scope": "internal_local_only",
            "cross_export_matching": "not_guaranteed",
            "registry_path": registry_path.as_posix(),
            "registry_records": len(registry.records),
            "next_sequence": registry.next_sequence,
        },
        "counts": counts,
        "sumcheck": {
            "prepared_plus_quarantine_equals_candidates": (
                counts["prepared"] + counts["quarantine"] == counts["candidate_features"]
            ),
            "candidates_plus_duplicate_extra_equals_input": (
                counts["candidate_features"] + counts["exact_duplicate_extra"]
                == counts["input_features"]
            ),
        },
        "quarantine_reasons": dict(sorted(quarantine_counts.items())),
        "prepared_review_flags": dict(sorted(review_flags_counter.items())),
        "provenance": {
            "provided_at": provided_at,
            "collection_time": "UNKNOWN",
            "source_url": "UNKNOWN",
            "license": "UNKNOWN",
            "freshness": "UNKNOWN",
            "sidecar_only": True,
            "note": (
                "Lineage is a sidecar artifact only; it is NOT claimed to be persisted "
                "in any graph. A later storage/ingestion extension is required to carry "
                "this provenance into the graph."
            ),
        },
        "not_claimed": [
            "accepted graph nodes",
            "verified venues",
            "fresh data",
            "genuine upstream/source identifiers",
        ],
        "semantic_gap": {
            "admin": (
                "The existing POI Address schema only carries free-text city/district/"
                "ward. It cannot express a qualified legacy area that may fall under a "
                "different present-day jurisdiction. Legacy source labels (Di An / "
                "Thuan An / Thu Dau Mot) are preserved verbatim and flagged for review; "
                "no current ward boundary or legislative containment is claimed from the "
                "coordinate bounding box."
            ),
            "categories": (
                "The 14 source labels have no reviewed mapping onto live graph Category "
                "nodes; the prepared payload carries source-derived category ids only."
            ),
        },
        "next_integration_step": (
            "Supply an authorised, dated administrative mapping (or a graph-side "
            "qualified-admin field) and a reviewed mapping of the 14 source category ids "
            "onto live graph Category ids; then add a storage/ingestion extension that "
            "carries this sidecar lineage into the graph."
        ),
    }

    outputs: Dict[str, Path] = {
        "prepared_pois": out_dir / "prepared_pois.jsonl",
        "lineage": out_dir / "lineage.jsonl",
        "quarantine": out_dir / "quarantine.jsonl",
        "duplicate_ledger": out_dir / "duplicate_ledger.jsonl",
        "category_catalog": out_dir / "category_catalog.json",
        "summary": out_dir / "summary.json",
    }
    rendered: Dict[Path, bytes] = {
        outputs["prepared_pois"]: _jsonl_bytes(prepared_rows),
        outputs["lineage"]: _jsonl_bytes(lineage_rows),
        outputs["quarantine"]: _jsonl_bytes(quarantine_rows),
        outputs["duplicate_ledger"]: _jsonl_bytes(duplicate_rows),
        outputs["category_catalog"]: (
            json.dumps(CATALOG, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
        outputs["summary"]: (
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
        registry_path: registry.render(),
    }

    # Fail before mutating: validate the prospective registry, its required revision
    # flag and backup collision, then every existing output. These are pre-write
    # consistency checks, not a claim of filesystem crash transactionality.
    registry.preflight(
        rendered[registry_path], accept_input_revision=accept_input_revision
    )
    for path, payload in rendered.items():
        if path.exists():
            existing = path.read_bytes()
            if existing != payload and not accept_input_revision:
                raise ConfigError(
                    f"refusing to overwrite existing output {path} with different "
                    "bytes; a changed input revision must be explicitly accepted"
                )

    out_dir.mkdir(parents=True, exist_ok=True)
    registry_changed = registry.save(
        rendered[registry_path], accept_input_revision=accept_input_revision
    )
    for name, path in outputs.items():
        atomic_write_bytes(path, rendered[path], overwrite=True)

    return PrepareResult(
        summary=summary,
        outputs=outputs,
        registry_path=registry_path,
        assigned_in_this_run=assigned_in_this_run,
        registry_changed=registry_changed,
        revision_accepted=bool(accept_input_revision and plan.changed),
    )
