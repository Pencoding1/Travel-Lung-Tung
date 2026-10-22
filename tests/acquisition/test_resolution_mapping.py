"""Per-entity resolution and mapping-manifest validation tests (SYNTHETIC)."""

import json

import pytest

from crawler_service.app.acquisition.contracts import POICandidate, ReasonCode
from crawler_service.app.acquisition.jsonptr import resolve_pointer
from crawler_service.app.acquisition.resolution import (
    ConfigError,
    load_mapping_manifest,
    resolve_candidate,
)

from acquisition_helpers import (
    default_categories,
    entities_for,
    entity_review,
    reviewed_source,
    write_mapping,
)


def make_candidate(
    entity_id="node/1",
    geometry="point",
    name="Demo",
    coords=(10.0, 106.0),
    tags=("amenity=cafe",),
    hints=None,
    opening_hours=None,
):
    return POICandidate(
        source_type="osm",
        source_entity_id=entity_id,
        geometry_kind=geometry,
        name=name,
        aliases=[],
        coordinates=coords,
        address_hints=dict(hints or {}),
        category_tags=list(tags),
        opening_hours_raw=opening_hours,
        raw_content_reference="raw/osm.json",
        raw_sha256="a" * 64,
        source_url="file://synthetic",
        license="ODbL-1.0",
        retrieved_at="2026-10-15T00:00:00Z",
        field_paths={
            "identity": "/elements/0/id",
            "name": "/elements/0/tags/name",
            "opening_hours": "/elements/0/tags/opening_hours",
        },
    )


def load(tmp_path, sources):
    path = write_mapping(tmp_path / "mapping.json", default_categories(), sources)
    return path, load_mapping_manifest(path)


def test_exact_resolution_accepts_reviewed_entity(tmp_path):
    path, manifest = load(tmp_path, {"osm-test": reviewed_source(entities=entities_for("osm/node/1"))})
    resolution = resolve_candidate(make_candidate(opening_hours="Mo-Su 07:00-22:00"), manifest.sources["osm-test"], manifest)
    resolved = resolution.resolved
    assert resolved is not None and resolution.resolution_status == "exact"
    assert resolved.category_ids == ["cafe"]
    assert resolved.categories == [
        {"id": "cafe", "name": "Cafe", "context": "Coffee shops and cafes"}
    ]
    assert resolved.operation_time == "Mo-Su 07:00-22:00"

    provenance = resolved.provenance
    assert provenance["mapping"]["manifest_sha256"] == manifest.sha256
    assert len(manifest.sha256) == 64
    assert provenance["operation_time"]["parse_status"] == "unparsed_source_text"

    document = json.loads(path.read_text(encoding="utf-8"))
    admin = resolve_pointer(document, provenance["mapping"]["admin"]["pointer"])
    assert admin["district"] == "District 1"
    category_map_pointer = provenance["mapping"]["categories"][0]["map_pointer"]
    assert resolve_pointer(document, category_map_pointer) == "cafe"
    assert resolve_pointer(document, provenance["mapping"]["categories"][0]["catalog_pointer"])["id"] == "cafe"


def test_file_level_review_alone_is_not_sufficient(tmp_path):
    _, manifest = load(tmp_path, {"osm-test": reviewed_source()})  # no entities
    resolution = resolve_candidate(make_candidate(), manifest.sources["osm-test"], manifest)
    assert resolution.resolved is None
    assert ReasonCode.ENTITY_UNREVIEWED in resolution.reasons


def test_mixed_city_export_cannot_be_accepted_wholesale(tmp_path):
    _, manifest = load(
        tmp_path,
        {
            "osm-test": reviewed_source(
                entities={
                    "osm/node/1": entity_review(district="District 1"),
                    "osm/node/2": entity_review(city="Ha Noi", district="Ba Dinh"),
                }
            )
        },
    )
    first = resolve_candidate(make_candidate(entity_id="node/1"), manifest.sources["osm-test"], manifest)
    second = resolve_candidate(make_candidate(entity_id="node/2"), manifest.sources["osm-test"], manifest)
    assert first.resolved is not None
    assert second.resolved is not None
    assert first.resolved.city == "Ho Chi Minh City"
    assert second.resolved.city == "Ha Noi"


def test_unlisted_entity_in_mixed_export_routes_to_review(tmp_path):
    _, manifest = load(tmp_path, {"osm-test": reviewed_source(entities=entities_for("osm/node/1"))})
    resolution = resolve_candidate(make_candidate(entity_id="node/9"), manifest.sources["osm-test"], manifest)
    assert resolution.resolved is None
    assert ReasonCode.ENTITY_UNREVIEWED in resolution.reasons


def test_conflicting_address_hint_routes_to_review(tmp_path):
    _, manifest = load(tmp_path, {"osm-test": reviewed_source(entities=entities_for("osm/node/1"))})
    conflict = resolve_candidate(
        make_candidate(hints={"addr:district": "Quan 3"}), manifest.sources["osm-test"], manifest
    )
    assert conflict.resolved is None
    assert ReasonCode.ADMIN_CONFLICT in conflict.reasons


def test_matching_address_hint_is_accepted(tmp_path):
    _, manifest = load(tmp_path, {"osm-test": reviewed_source(entities=entities_for("osm/node/1"))})
    ok = resolve_candidate(
        make_candidate(hints={"addr:district": "Quan 1"}), manifest.sources["osm-test"], manifest
    )
    assert ok.resolved is not None


def test_unknown_category_requires_review(tmp_path):
    _, manifest = load(tmp_path, {"osm-test": reviewed_source(entities=entities_for("osm/node/1"))})
    resolution = resolve_candidate(make_candidate(tags=("amenity=nightclub",)), manifest.sources["osm-test"], manifest)
    assert resolution.resolved is None
    assert ReasonCode.UNKNOWN_CATEGORY in resolution.reasons


@pytest.mark.parametrize("coords", [(float("nan"), 106.0), (10.0, float("inf")), (91.0, 106.0), (10.0, 181.0), (True, 106.0)])
def test_invalid_coordinates_are_rejected(tmp_path, coords):
    _, manifest = load(tmp_path, {"osm-test": reviewed_source(entities=entities_for("osm/node/1"))})
    resolution = resolve_candidate(make_candidate(coords=coords), manifest.sources["osm-test"], manifest)
    assert resolution.resolved is None
    assert resolution.resolution_status == "unresolved"
    assert ReasonCode.INVALID_COORDINATES in resolution.reasons


@pytest.mark.parametrize("geometry,expected", [("area", ReasonCode.AREA_GEOMETRY_REVIEW), ("center", ReasonCode.CENTER_COORDINATE_REVIEW)])
def test_area_and_center_require_review(tmp_path, geometry, expected):
    _, manifest = load(tmp_path, {"osm-test": reviewed_source(entities=entities_for("osm/node/1"))})
    resolution = resolve_candidate(make_candidate(geometry=geometry), manifest.sources["osm-test"], manifest)
    assert resolution.resolved is None and expected in resolution.reasons


def test_two_similarly_named_sources_remain_separate(tmp_path):
    _, manifest = load(
        tmp_path,
        {"osm-test": reviewed_source(entities=entities_for("osm/node/1", "osm/node/2"))},
    )
    first = resolve_candidate(make_candidate(entity_id="node/1", name="Cafe Demo"), manifest.sources["osm-test"], manifest)
    second = resolve_candidate(make_candidate(entity_id="node/2", name="Cafe Demo"), manifest.sources["osm-test"], manifest)
    assert first.resolved.stable_id != second.resolved.stable_id


def test_reviewer_evidence_city_must_be_nonblank_strings(tmp_path):
    for bad in ({"reviewer": {"nested": "obj"}}, {"reviewer": ""}, {"evidence_reference": 123}, {"city": None}, {"district": []}):
        entry = entity_review()
        entry.update(bad)
        path = write_mapping(
            tmp_path / "m.json", default_categories(), {"osm-test": reviewed_source(entities={"osm/node/1": entry})}
        )
        with pytest.raises(ConfigError):
            load_mapping_manifest(path)


def test_conflicting_category_definition_is_invalid(tmp_path):
    categories = [
        {"id": "cafe", "name": "Cafe", "context": "one"},
        {"id": "cafe", "name": "Different", "context": "two"},
    ]
    path = write_mapping(tmp_path / "m.json", categories, {"s": reviewed_source(entities=entities_for("osm/node/1"))})
    with pytest.raises(ConfigError):
        load_mapping_manifest(path)


def test_category_map_referencing_unknown_category_is_invalid(tmp_path):
    source = reviewed_source(category_map={"amenity=cafe": "ghost"}, entities=entities_for("osm/node/1"))
    path = write_mapping(tmp_path / "m.json", default_categories(), {"s": source})
    with pytest.raises(ConfigError):
        load_mapping_manifest(path)


def test_equivalence_configuration_is_rejected(tmp_path):
    document = {
        "mapping_version": 1,
        "categories": default_categories(),
        "sources": {"s": reviewed_source(entities=entities_for("osm/node/1"))},
        "equivalences": [{"a": "osm:1", "b": "wikidata:Q1"}],
    }
    path = tmp_path / "m.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_mapping_manifest(path)


def test_synthetic_flag_must_be_boolean(tmp_path):
    source = reviewed_source(entities=entities_for("osm/node/1"))
    source["synthetic"] = "yes"
    path = write_mapping(tmp_path / "m.json", default_categories(), {"s": source})
    with pytest.raises(ConfigError):
        load_mapping_manifest(path)
