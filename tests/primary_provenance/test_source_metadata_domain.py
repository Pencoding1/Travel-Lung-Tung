"""OC-038 typed source-provenance domain contract.

These use the actual ``POI``/``SourceMetadata`` models and no graph call. The
metadata is rejected at the trusted boundary, before any repository is reached.
"""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.domain.graph_entities import (
    POI,
    SourceMetadata,
    decode_source_metadata,
    canonical_json,
)
from provenance_fixtures import (
    FEATURE_SHA,
    INPUT_SHA,
    POI_ID,
    feature_hash,
    lineage_row,
    metadata_dict,
    poi_payload,
    raw_properties,
)


def test_valid_metadata_round_trips_every_required_source_field():
    metadata = metadata_dict()
    poi = POI.model_validate(poi_payload(source_metadata=metadata))

    assert poi.id == POI_ID
    assert isinstance(poi.source_metadata, SourceMetadata)
    dumped = poi.model_dump(mode="json")
    assert dumped["source_metadata"] == metadata

    # Full raw lineage, Vietnamese source text and geometry survive verbatim.
    row = poi.source_metadata.parsed_lineage()
    assert row["source"]["raw_properties"]["name"] == "Thế Giới Sữa"
    assert row["source"]["geometry"] == {
        "coordinates": [106.6677248, 10.8482306],
        "type": "Point",
    }
    assert row["source"]["canonical_source_index"] == 157
    assert poi.source_metadata.input_sha256 == INPUT_SHA
    assert poi.source_metadata.feature_sha256 == FEATURE_SHA
    assert poi.source_metadata.internal_record_id == "r005494"
    assert poi.source_metadata.provided_at.isoformat() == "2026-10-16"
    # Unknowns stay unknown/null; they are never invented.
    assert poi.source_metadata.collection_time is None
    assert poi.source_metadata.source_url is None
    assert poi.source_metadata.license is None
    assert poi.source_metadata.freshness is None
    assert poi.source_metadata.identity_scope == "internal_local_only"
    assert poi.source_metadata.cross_export_matching == "not_guaranteed"
    assert poi.source_metadata.administrative_scope == "source_snapshot_area_only"

    # A second production validation/serialization pass is stable.
    assert POI.model_validate(dumped).model_dump(mode="json") == dumped


def test_absent_metadata_remains_legacy_unspecified_and_backward_compatible():
    poi = POI.model_validate(poi_payload(source_metadata=None))
    assert poi.source_metadata is None
    assert decode_source_metadata(None) == (None, "missing")
    assert decode_source_metadata("   ") == (None, "missing")


def test_metadata_does_not_mutate_the_caller_payload():
    raw = poi_payload(source_metadata=metadata_dict())
    snapshot = copy.deepcopy(raw)
    POI.model_validate(raw)
    assert raw == snapshot


@pytest.mark.parametrize(
    "overrides",
    [
        {"input_sha256": "NOT-A-HASH"},
        {"feature_sha256": FEATURE_SHA.upper()},
        {"raw_lineage_sha256": "0" * 63},
        {"canonical_source_index": -1},
        {"canonical_source_index": True},
        {"duplicate_source_indices": [157]},
        {"duplicate_source_indices": [1, 1]},
        {"duplicate_source_indices": [-2]},
        {"duplicate_source_indices": [False]},
        {"identity_scope": "global"},
        {"cross_export_matching": "guaranteed"},
        {"administrative_scope": "current_admin"},
        {"feature_sha": "nope"},  # misspelled metadata field must not be ignored
    ],
)
def test_malformed_or_ambiguous_metadata_is_rejected(overrides):
    with pytest.raises(ValidationError):
        POI.model_validate(poi_payload(source_metadata=metadata_dict(**overrides)))


def test_wrong_identity_binding_is_rejected():
    other = lineage_row(poi_id="hcm_primary_geojson_internal:someone_else")
    with pytest.raises(ValidationError):
        POI.model_validate(poi_payload(source_metadata=metadata_dict(other)))

    row = lineage_row()
    row["identity"]["namespace"] = "another_dataset"
    with pytest.raises(ValidationError):
        POI.model_validate(
            poi_payload(
                source_metadata=metadata_dict(row, dataset_namespace="hcm_primary_geojson")
            )
        )

    row = lineage_row()
    row["source"]["exact_feature_hash"] = "a" * 64
    with pytest.raises(ValidationError):
        POI.model_validate(
            poi_payload(source_metadata=metadata_dict(row, feature_sha256=FEATURE_SHA))
        )

    row = lineage_row()
    row["internal_record_id"] = "r999999"
    with pytest.raises(ValidationError):
        POI.model_validate(
            poi_payload(source_metadata=metadata_dict(row, internal_record_id="r005494"))
        )


def test_noncanonical_or_tampered_raw_lineage_is_rejected():
    metadata = metadata_dict()
    tampered = dict(metadata)
    row = lineage_row()
    row["source"]["raw_properties"]["name"] = "Tampered"
    tampered["raw_lineage_json"] = canonical_json(row)  # hash no longer matches
    with pytest.raises(ValidationError):
        POI.model_validate(poi_payload(source_metadata=tampered))

    metadata = metadata_dict()
    metadata["raw_lineage_json"] = metadata["raw_lineage_json"] + "\n"
    with pytest.raises(ValidationError):
        POI.model_validate(poi_payload(source_metadata=metadata))


def test_misspelled_top_level_metadata_is_not_silently_ignored():
    raw = poi_payload()
    raw["source_metdata"] = metadata_dict()
    with pytest.raises(ValidationError):
        POI.model_validate(raw)


@pytest.mark.parametrize("missing_key", ["geometry", "raw_properties"])
def test_missing_full_source_feature_body_is_rejected(missing_key):
    row = lineage_row()
    row["source"].pop(missing_key)
    with pytest.raises(ValidationError):
        POI.model_validate(poi_payload(source_metadata=metadata_dict(row)))


def test_changed_source_body_requires_recomputed_feature_hash():
    row = lineage_row()
    changed_properties = raw_properties(raw_name="Deliberately Changed Name")
    row["source"]["raw_properties"] = changed_properties

    # Self-hashed raw lineage but stale declared feature hash: rejected.
    stale = metadata_dict(row)
    with pytest.raises(ValidationError):
        POI.model_validate(poi_payload(source_metadata=stale))

    # A deliberately changed fixture is valid only when its feature hash is
    # independently recomputed with the frozen feature-body recipe.
    row["source"]["exact_feature_hash"] = feature_hash(changed_properties)
    accepted = POI.model_validate(
        poi_payload(source_metadata=metadata_dict(row))
    )
    assert accepted.source_metadata.feature_sha256 == feature_hash(changed_properties)


def test_geometry_property_coordinate_contradiction_is_rejected():
    row = lineage_row()
    row["source"]["raw_properties"]["lat"] = 11.0
    row["source"]["exact_feature_hash"] = feature_hash(
        row["source"]["raw_properties"]
    )
    with pytest.raises(ValidationError):
        POI.model_validate(poi_payload(source_metadata=metadata_dict(row)))


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Point", "coordinates": [106.7]},
        {"type": "Point", "coordinates": [106.7, float("nan")]},
        {"type": "Point", "coordinates": [200.0, 10.7]},
        {"type": "LineString", "coordinates": [106.7, 10.7]},
    ],
)
def test_invalid_source_geometry_is_rejected(geometry):
    row = lineage_row()
    row["source"]["geometry"] = geometry
    row["source"]["exact_feature_hash"] = feature_hash(
        row["source"]["raw_properties"], geometry
    )
    with pytest.raises(ValidationError):
        POI.model_validate(poi_payload(source_metadata=metadata_dict(row)))


def test_canonical_raw_lineage_json_is_not_the_feature_hash_recipe():
    row = lineage_row()
    compact_feature_hash = hashlib.sha256(
        canonical_json(
            {
                "type": "Feature",
                "properties": row["source"]["raw_properties"],
                "geometry": row["source"]["geometry"],
            }
        ).encode("utf-8")
    ).hexdigest()
    row["source"]["exact_feature_hash"] = compact_feature_hash
    with pytest.raises(ValidationError):
        POI.model_validate(poi_payload(source_metadata=metadata_dict(row)))


def test_compound_lite_omits_absent_provenance_and_exposes_present_evidence():
    from app.core.domain.get_payload import (
        POICompoundLite,
        SourceEvidenceSummary,
    )

    plain = POICompoundLite(id="p1", name="Cafe").model_dump()
    assert "source_metadata" not in plain
    assert "administrative_scope" not in plain
    assert "source_metadata_status" not in plain

    metadata = SourceMetadata.model_validate(metadata_dict())
    enriched = POICompoundLite(
        id=POI_ID,
        name="the gioi sua",
        source_metadata=SourceEvidenceSummary.from_metadata(metadata),
        source_metadata_status="valid",
        administrative_scope="source_snapshot_area_only",
    ).model_dump()
    assert enriched["administrative_scope"] == "source_snapshot_area_only"
    assert enriched["source_metadata"]["internal_record_id"] == "r005494"
    assert enriched["source_metadata"]["raw_lineage_sha256"] == metadata.raw_lineage_sha256
    assert "raw_lineage_json" not in enriched["source_metadata"]
    assert enriched["source_metadata_status"] == "valid"


def test_production_ingestion_validation_route_carries_typed_metadata():
    pytest.importorskip("tenacity")
    from app.core.services.ingestion import POIIngestionService

    service = POIIngestionService(uow_factory=lambda: None)
    valid, indices, failures = service._validate_batch(
        [
            poi_payload(source_metadata=metadata_dict()),
            poi_payload(source_metadata=metadata_dict(feature_sha256="bad")),
        ]
    )

    assert indices == [0]
    assert [failure["index"] for failure in failures] == [1]
    assert valid[0]["source_metadata"] == metadata_dict()


def test_real_frozen_lineage_row_binds_through_the_new_schema():
    """Read-only readiness check: no prepared artifact is written or regenerated."""
    root = Path(__file__).resolve().parents[2]
    lineage_path = root / "data" / "primary_20261016" / "prepared" / "lineage.jsonl"
    prepared_path = (
        root / "data" / "primary_20261016" / "prepared" / "prepared_pois.jsonl"
    )
    if not lineage_path.is_file() or not prepared_path.is_file():
        pytest.skip("frozen primary preparation artifacts are not present")

    with lineage_path.open(encoding="utf-8") as handle:
        row = json.loads(handle.readline())
    with prepared_path.open(encoding="utf-8") as handle:
        prepared = json.loads(handle.readline())

    raw_json = canonical_json(row)
    prepared["source_metadata"] = {
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
        "raw_lineage_sha256": hashlib.sha256(
            raw_json.encode("utf-8")
        ).hexdigest(),
    }

    poi = POI.model_validate(prepared)
    assert poi.id == row["id"]
    assert poi.source_metadata.canonical_source_index == row["source"][
        "canonical_source_index"
    ]
    assert poi.source_metadata.administrative_scope == "source_snapshot_area_only"
