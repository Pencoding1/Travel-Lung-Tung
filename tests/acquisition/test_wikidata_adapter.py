"""Wikidata entity JSON adapter tests (SYNTHETIC)."""

import pytest

from crawler_service.app.acquisition.adapters.base import SourceFormatError
from crawler_service.app.acquisition.adapters.wikidata import WikidataAdapter
from crawler_service.app.acquisition.contracts import InfoCode, ReasonCode
from crawler_service.app.acquisition.jsonptr import resolve_pointer

from acquisition_helpers import coord_claim, wikidata_entity


def parse(payload):
    return WikidataAdapter().parse(
        payload,
        source_id="wikidata-test",
        source_url="file://synthetic",
        license="CC0-1.0",
        retrieved_at="2026-10-15T00:00:00Z",
        raw_content_reference="raw/wikidata.json",
        raw_sha256="b" * 64,
    )


def entities(*items):
    return {"entities": {e["id"]: e for e in items}}


def test_labels_prefer_vietnamese_then_english():
    vi = parse(entities(wikidata_entity("Q1", labels={"vi": "Tiếng Việt", "en": "English"})))[0]
    en = parse(entities(wikidata_entity("Q2", labels={"en": "English only"})))[0]
    missing = parse(entities(wikidata_entity("Q3", labels={})))[0]
    assert vi.name == "Tiếng Việt"
    assert vi.field_paths["name"] == "/entities/Q1/labels/vi/value"
    assert en.name == "English only"
    assert missing.name is None


def test_preferred_rank_wins_over_normal():
    candidate = parse(
        entities(
            wikidata_entity(
                "Q1", labels={"en": "P"}, p31=["Q33506"],
                coordinates=[coord_claim(10.0, 106.0, rank="normal"), coord_claim(10.5, 106.5, rank="preferred")],
            )
        )
    )[0]
    assert candidate.coordinates == (10.5, 106.5)


def test_deprecated_is_informational_when_valid_live_exists():
    candidate = parse(
        entities(
            wikidata_entity(
                "Q1", labels={"en": "D"}, p31=["Q33506"],
                coordinates=[coord_claim(10.0, 106.0, rank="deprecated"), coord_claim(10.5, 106.5)],
            )
        )
    )[0]
    assert candidate.coordinates == (10.5, 106.5)
    assert InfoCode.DEPRECATED_COORDINATE_IGNORED in candidate.info_codes
    assert candidate.uncertainty_codes == []


def test_non_earth_is_informational_when_valid_live_exists():
    candidate = parse(
        entities(
            wikidata_entity(
                "Q1", labels={"en": "G"}, p31=["Q33506"],
                coordinates=[coord_claim(0.0, 0.0, globe="Q405"), coord_claim(10.5, 106.5)],
            )
        )
    )[0]
    assert candidate.coordinates == (10.5, 106.5)
    assert InfoCode.NON_EARTH_GLOBE_IGNORED in candidate.info_codes


def test_only_deprecated_requires_review():
    candidate = parse(
        entities(wikidata_entity("Q1", labels={"en": "D"}, p31=["Q33506"], coordinates=[coord_claim(9.0, 105.0, rank="deprecated")]))
    )[0]
    assert candidate.coordinates is None
    assert ReasonCode.NO_LIVE_COORDINATES in candidate.uncertainty_codes
    assert InfoCode.DEPRECATED_COORDINATE_IGNORED in candidate.info_codes


def test_only_non_earth_requires_review():
    candidate = parse(
        entities(wikidata_entity("Q1", labels={"en": "M"}, p31=["Q33506"], coordinates=[coord_claim(0.0, 0.0, globe="Q405")]))
    )[0]
    assert candidate.coordinates is None
    assert ReasonCode.NO_LIVE_COORDINATES in candidate.uncertainty_codes


def test_multiple_nonidentical_live_coordinates_are_ambiguous():
    candidate = parse(
        entities(wikidata_entity("Q1", labels={"en": "A"}, p31=["Q33506"], coordinates=[coord_claim(10.0, 106.0), coord_claim(10.1, 106.1)]))
    )[0]
    assert candidate.coordinates is None
    assert ReasonCode.AMBIGUOUS_COORDINATES in candidate.uncertainty_codes


def test_malformed_coordinate_list_does_not_crash():
    candidate = parse(
        entities(wikidata_entity("Q1", labels={"en": "B"}, p31=["Q33506"], coordinates=[coord_claim([10.0], {"x": 1})]))
    )[0]
    assert candidate.coordinates is None
    assert ReasonCode.INVALID_COORDINATES in candidate.uncertainty_codes


@pytest.mark.parametrize(
    "entity_id,expected",
    [("Q1", True), ("Q10", True), ("Q0", False), ("Qabc", False), ("1", False), (None, False)],
)
def test_identity_validation(entity_id, expected):
    entity = {"id": entity_id, "claims": {}}
    candidate = parse({"entities": [entity]})[0]
    if expected:
        assert candidate.source_entity_id == entity_id
        assert ReasonCode.INVALID_SOURCE_IDENTITY not in candidate.uncertainty_codes
        assert ReasonCode.MISSING_SOURCE_IDENTITY not in candidate.uncertainty_codes
    else:
        assert candidate.source_entity_id == ""
        assert (
            ReasonCode.INVALID_SOURCE_IDENTITY in candidate.uncertainty_codes
            or ReasonCode.MISSING_SOURCE_IDENTITY in candidate.uncertainty_codes
        )


def test_json_pointers_include_entities_qid_prefix_and_resolve():
    payload = entities(
        wikidata_entity("Q100", labels={"en": "Museum"}, p31=["Q33506"], coordinates=[coord_claim(10.77, 106.70)])
    )
    candidate = parse(payload)[0]
    assert resolve_pointer(payload, candidate.field_paths["identity"]) == "Q100"
    assert resolve_pointer(payload, candidate.field_paths["name"]) == "Museum"
    assert resolve_pointer(payload, candidate.field_paths["latitude"]) == 10.77
    assert resolve_pointer(payload, candidate.field_paths["longitude"]) == 106.70
    assert resolve_pointer(payload, candidate.field_paths["category"])["rank"] == "normal"


def test_error_payload_raises():
    with pytest.raises(SourceFormatError):
        parse({"error": {"code": "timeout"}})
