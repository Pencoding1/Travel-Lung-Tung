"""Shared fixtures for the OC-038 source-provenance contract tests.

The lineage shape mirrors the frozen primary dataset rows read-only; no actual
prepared file is regenerated or modified by these tests.
"""

import hashlib
import json

from app.core.domain.graph_entities import canonical_json

INPUT_SHA = "713b07a62cf89bd2cad9093abaad2a4c5f01e23853321764b3d66bf9f7eee43c"
NAMESPACE = "hcm_primary_geojson"
RECORD_ID = "r005494"
POI_ID = "hcm_primary_geojson_internal:00017f7e17050fd16ce73d2e60599715"

GEOMETRY = {
    "coordinates": [106.6677248, 10.8482306],
    "type": "Point",
}


def raw_properties(raw_name="Thế Giới Sữa"):
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
        "name": raw_name,
        "opening_ho": None,
        "poi_category": "retail_center",
        "processed_name": "the gioi sua",
    }


def feature_hash(properties, geometry=GEOMETRY):
    """The source feature-body recipe (default JSON separators, spaced).

    This is intentionally distinct from ``canonical_json`` used for the raw
    lineage envelope. It mirrors the frozen preparation hash without importing
    crawler code into the POI service.
    """
    feature = {"type": "Feature", "properties": properties, "geometry": geometry}
    material = json.dumps(feature, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


FEATURE_SHA = feature_hash(raw_properties())


def lineage_row(
    poi_id=POI_ID,
    *,
    canonical_source_index=157,
    internal_record_id=RECORD_ID,
    feature_sha=None,
    raw_name="Thế Giới Sữa",
):
    """A full lineage object equivalent to one frozen `lineage.jsonl` row."""
    properties = raw_properties(raw_name)
    if feature_sha is None:
        feature_sha = feature_hash(properties)
    return {
        "id": poi_id,
        "internal_record_id": internal_record_id,
        "sequence": 5494,
        "identity": {
            "namespace": NAMESPACE,
            "identity_scope": "internal_local_only",
            "cross_export_matching": "not_guaranteed",
            "identity_key": "hcm_primary_geojson|thegioisua|106.6677248,10.8482306|681|uongleuctho",
            "derivation": "normalized_name + exact_coordinates + source_address_anchor",
            "name_key": "thegioisua",
            "coordinates_token": "106.6677248,10.8482306",
            "address_anchor": "681|uongleuctho",
            "name_source": "processed_name",
            "raw_name": raw_name,
            "processed_name": "the gioi sua",
        },
        "source": {
            "input_path": "data/primary_20261016/hcm_pois_final.geojson",
            "input_sha256": INPUT_SHA,
            "canonical_source_index": canonical_source_index,
            "exact_feature_hash": feature_sha,
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
            "raw_city": "HCMC",
            "raw_district": "Go Vap",
            "raw_ward": None,
            "raw_house": "681",
            "raw_stree": "Đường Lê Đức Thọ",
            "raw_full": None,
            "payload_city": "HCMC",
            "payload_district": "Go Vap",
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


def poi_payload(poi_id=POI_ID, *, source_metadata=None, address="source", **overrides):
    if address == "source":
        address = {
            "street_name": "681 Đường Lê Đức Thọ",
            "district": "Go Vap",
            "city": "HCMC",
            "nation": "Vietnam",
        }
    payload = {
        "id": poi_id,
        "name": "the gioi sua",
        "longitude": 106.6677248,
        "latitude": 10.8482306,
        "address": address,
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
