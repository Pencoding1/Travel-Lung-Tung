"""Fixtures built from one real frozen primary-snapshot record.

The POI id, input SHA and raw HCMC/Go Vap labels are the actual values from
``data/primary_20261016/prepared/lineage.jsonl``. No frozen file is modified or
regenerated. Additional rows only change the qualified tuple to prove that equal
labels do not collide.
"""

import hashlib
import json
from typing import Optional

from app.core.domain.graph_entities import (
    SourceMetadata,
    canonical_json,
    canonical_source_metadata_json,
)

INPUT_SHA = "713b07a62cf89bd2cad9093abaad2a4c5f01e23853321764b3d66bf9f7eee43c"
NAMESPACE = "hcm_primary_geojson"
POI_ID = "hcm_primary_geojson_internal:00017f7e17050fd16ce73d2e60599715"
INTERNAL_RECORD_ID = "r005494"

GEOMETRY = {"coordinates": [106.6677248, 10.8482306], "type": "Point"}


def raw_properties():
    return {
        "addr_city": "HCMC",
        "addr_district": "Go Vap",
        "addr_full": None,
        "addr_house": "681",
        "addr_stree": "Đường Lê Đức Thọ",
        "addr_ward": None,
        "cluster": 0,
        "lat": 10.8482306,
        "lon": 106.6677248,
        "name": "Thế Giới Sữa",
        "opening_ho": None,
        "poi_category": "retail_center",
        "processed_name": "the gioi sua",
    }


def feature_hash(properties, geometry=GEOMETRY):
    feature = {"type": "Feature", "properties": properties, "geometry": geometry}
    material = json.dumps(feature, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def lineage_row(
    poi_id=POI_ID,
    *,
    namespace=NAMESPACE,
    input_sha=INPUT_SHA,
    raw_city: Optional[str] = "HCMC",
    raw_district: Optional[str] = "Go Vap",
    internal_record_id=INTERNAL_RECORD_ID,
    canonical_source_index=157,
):
    properties = raw_properties()
    return {
        "id": poi_id,
        "internal_record_id": internal_record_id,
        "sequence": 5494,
        "identity": {
            "namespace": namespace,
            "identity_scope": "internal_local_only",
            "cross_export_matching": "not_guaranteed",
            "identity_key": "hcm_primary_geojson|thegioisua|106.6677248,10.8482306|681|uongleuctho",
            "derivation": "normalized_name + exact_coordinates + source_address_anchor",
            "name_key": "thegioisua",
            "coordinates_token": "106.6677248,10.8482306",
            "address_anchor": "681|uongleuctho",
            "name_source": "processed_name",
            "raw_name": properties["name"],
            "processed_name": "the gioi sua",
        },
        "source": {
            "input_path": "data/primary_20261016/hcm_pois_final.geojson",
            "input_sha256": input_sha,
            "canonical_source_index": canonical_source_index,
            "exact_feature_hash": feature_hash(properties),
            "geometry": {
                "type": GEOMETRY["type"],
                "coordinates": list(GEOMETRY["coordinates"]),
            },
            "raw_properties": properties,
        },
        "catalog_version": "1e39b6e91122c6ee",
        "category_source_label": "retail_center",
        "address": {
            "scope": "source_snapshot_area_only",
            "raw_city": raw_city,
            "raw_district": raw_district,
            "raw_ward": None,
            "raw_house": "681",
            "raw_stree": "Đường Lê Đức Thọ",
            "raw_full": None,
            "payload_city": raw_city,
            "payload_district": raw_district,
            "current_admin_claim": "none",
        },
        "operation_time": None,
        "price": {"status": "unknown", "note": "no price field exists in the source"},
        "provenance": {
            "provided_at": "2026-10-16",
            "collection_time": "UNKNOWN",
            "source_url": "UNKNOWN",
            "license": "UNKNOWN",
            "freshness": "UNKNOWN",
        },
        "review_flags": [],
    }


def metadata_dict(row=None, **overrides):
    row = row if row is not None else lineage_row()
    raw_json = canonical_json(row)
    metadata = {
        "dataset_namespace": row["identity"]["namespace"],
        "identity_scope": row["identity"]["identity_scope"],
        "cross_export_matching": row["identity"]["cross_export_matching"],
        "administrative_scope": row["address"]["scope"],
        "input_sha256": row["source"]["input_sha256"],
        "feature_sha256": row["source"]["exact_feature_hash"],
        "canonical_source_index": row["source"]["canonical_source_index"],
        "duplicate_source_indices": [],
        "internal_record_id": row["internal_record_id"],
        "provided_at": row["provenance"]["provided_at"],
        "collection_time": None,
        "source_url": None,
        "license": None,
        "freshness": None,
        "raw_lineage_json": raw_json,
        "raw_lineage_sha256": hashlib.sha256(raw_json.encode("utf-8")).hexdigest(),
    }
    metadata.update(overrides)
    return metadata


def typed_metadata(row=None, **overrides):
    return SourceMetadata.model_validate(metadata_dict(row, **overrides))


def poi_payload(poi_id=POI_ID, *, source_metadata=None, **overrides):
    payload = {
        "id": poi_id,
        "name": "the gioi sua",
        "longitude": 106.6677248,
        "latitude": 10.8482306,
        "address": {
            "street_name": "681 Đường Lê Đức Thọ",
            "district": "Go Vap",
            "city": "HCMC",
            "nation": "Vietnam",
        },
        "contact_info": None,
        "poi_categories": [
            {
                "id": "hcm_primary_geojson:source-category:retail_center",
                "name": "Retail Center",
                "context": "Shopping centres and retail complexes as labelled by the source.",
            }
        ],
        "tag": None,
        "menu": [],
        "rating": None,
        "operation_time": None,
        "source_metadata": source_metadata,
    }
    payload.update(overrides)
    return payload


def metadata_storage(source_metadata):
    metadata = (
        source_metadata
        if isinstance(source_metadata, SourceMetadata)
        else SourceMetadata.model_validate(source_metadata)
    )
    canonical = canonical_source_metadata_json(metadata)
    return {
        "source_metadata_json": canonical,
        "source_metadata_sha256": hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest(),
        "administrative_scope": metadata.administrative_scope,
    }


def graph_record(
    poi_id=POI_ID,
    *,
    row=None,
    metadata=None,
    cached=True,
    cache_area_id=None,
    cache_namespace=None,
    cache_snapshot=None,
    override_sha=None,
    categories=None,
    offers=None,
):
    row = row if row is not None else lineage_row(poi_id=poi_id)
    metadata = metadata if metadata is not None else metadata_dict(row)
    storage = metadata_storage(metadata)
    if override_sha is not None:
        storage["source_metadata_sha256"] = override_sha

    from app.core.domain.source_scope import derive_source_area

    identity = derive_source_area(SourceMetadata.model_validate(metadata))
    record = {
        "id": poi_id,
        "name": "the gioi sua",
        "operation_time": None,
        "full_address": "681 Đường Lê Đức Thọ, Go Vap, HCMC",
        "source_metadata_json": storage["source_metadata_json"],
        "source_metadata_sha256": storage["source_metadata_sha256"],
        "administrative_scope": storage["administrative_scope"],
        "source_area_id": identity.source_area_id if cached else None,
        "source_dataset_namespace": identity.dataset_namespace if cached else None,
        "source_snapshot_sha256": identity.input_sha256 if cached else None,
        "categories": (
            categories
            if categories is not None
            else [
                {
                    "id": "hcm_primary_geojson:source-category:retail_center",
                    "name": "Retail Center",
                    "context": "source category",
                }
            ]
        ),
        "offers": offers if offers is not None else [],
    }
    if cache_area_id is not None:
        record["source_area_id"] = cache_area_id
    if cache_namespace is not None:
        record["source_dataset_namespace"] = cache_namespace
    if cache_snapshot is not None:
        record["source_snapshot_sha256"] = cache_snapshot
    return record
