"""OSM JSON adapter tests (SYNTHETIC)."""

import pytest

from crawler_service.app.acquisition.adapters.base import SourceFormatError
from crawler_service.app.acquisition.adapters.osm import OSMAdapter
from crawler_service.app.acquisition.contracts import GeometryKind, ReasonCode
from crawler_service.app.acquisition.jsonptr import resolve_pointer

from acquisition_helpers import osm_node, osm_relation, osm_way


def parse(payload):
    return OSMAdapter().parse(
        payload,
        source_id="osm-test",
        source_url="file://synthetic",
        license="ODbL-1.0",
        retrieved_at="2026-10-15T00:00:00Z",
        raw_content_reference="raw/osm.json",
        raw_sha256="a" * 64,
    )


def elements(elements_list):
    return {"version": 0.6, "elements": elements_list}


def test_element_identity_includes_primitive():
    candidates = parse(elements([osm_node(1, 10.0, 106.0, name="N")]))
    assert candidates[0].source_entity_id == "node/1"
    assert candidates[0].source_identity == "osm/node/1"


def test_node_coordinates_are_point_venues():
    candidate = parse(elements([osm_node(1, 10.0, 106.0, name="N")]))[0]
    assert candidate.geometry_kind == GeometryKind.POINT.value
    assert candidate.coordinates == (10.0, 106.0)


def test_way_center_and_relation_are_review_geometry():
    way = parse(elements([osm_way(10, center=(10.0, 106.0), name="W")]))[0]
    relation = parse(elements([osm_relation(20, name="R")]))[0]
    assert way.geometry_kind == GeometryKind.CENTER.value
    assert relation.geometry_kind == GeometryKind.AREA.value
    assert (way.source_entity_id, relation.source_entity_id) == ("way/10", "relation/20")


def test_amenity_tourism_shop_tags_extracted():
    candidate = parse(elements([osm_node(1, 10.0, 106.0, name="N", amenity="cafe", shop="bakery")]))[0]
    assert "amenity=cafe" in candidate.category_tags
    assert "shop=bakery" in candidate.category_tags


def test_opening_hours_is_retained_as_original_text():
    candidate = parse(elements([osm_node(1, 10.0, 106.0, name="N", opening_hours="Mo-Su 07:00-22:00")]))[0]
    assert candidate.opening_hours_raw == "Mo-Su 07:00-22:00"
    assert not hasattr(candidate, "parsed_hours")


@pytest.mark.parametrize(
    "primitive,raw_id,expected",
    [
        ("node", "1", ReasonCode.INVALID_SOURCE_IDENTITY),
        ("node", True, ReasonCode.INVALID_SOURCE_IDENTITY),
        ("node", -1, ReasonCode.INVALID_SOURCE_IDENTITY),
        ("node", 1.5, ReasonCode.INVALID_SOURCE_IDENTITY),
        ("building", 1, ReasonCode.INVALID_SOURCE_IDENTITY),
        (None, None, ReasonCode.MISSING_SOURCE_IDENTITY),
    ],
)
def test_malformed_identities_are_rejected(primitive, raw_id, expected):
    element = {"type": primitive, "id": raw_id, "tags": {"name": "x"}}
    candidate = parse(elements([element]))[0]
    assert candidate.source_entity_id == ""
    assert expected in candidate.uncertainty_codes


def test_non_object_entries_do_not_shift_indices():
    payload = elements([osm_node(7, 10.0, 106.0, name="Real"), "not-an-object", osm_node(8, 11.0, 107.0, name="Second")])
    candidates = parse(payload)
    assert candidates[1].source_entity_id == ""
    # The third element keeps original index 2.
    assert candidates[2].field_paths["identity"] == "/elements/2/id"


def test_json_pointers_resolve_against_raw_document():
    payload = elements([osm_node(1, 10.55, 106.66, name="Cafe X", amenity="cafe", opening_hours="Mo-Fr 08:00-18:00")])
    candidate = parse(payload)[0]
    assert resolve_pointer(payload, candidate.field_paths["identity"]) == 1
    assert resolve_pointer(payload, candidate.field_paths["name"]) == "Cafe X"
    assert resolve_pointer(payload, candidate.field_paths["coordinates"]) == 10.55
    assert resolve_pointer(payload, candidate.field_paths["longitude"]) == 106.66
    assert resolve_pointer(payload, candidate.field_paths["category"]) == "cafe"
    assert resolve_pointer(payload, candidate.field_paths["opening_hours"]) == "Mo-Fr 08:00-18:00"


def test_way_pointer_resolves_center():
    payload = elements([osm_way(10, center=(10.0, 106.0), name="W", tourism="attraction")])
    candidate = parse(payload)[0]
    assert resolve_pointer(payload, candidate.field_paths["latitude"]) == 10.0
    assert resolve_pointer(payload, candidate.field_paths["longitude"]) == 106.0


def test_error_payload_and_bad_shape_raise():
    with pytest.raises(SourceFormatError):
        parse({"error": "timeout"})
    with pytest.raises(SourceFormatError):
        parse("not a document")
