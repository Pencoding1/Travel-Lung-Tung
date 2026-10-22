"""Focused OC-002 tests for the stable POI identity and name contract.

These complement (and do not modify) the OC-001 audit baseline in
``tests/audit/test_poi_identity_and_coordinates.py``. They pin the parts of the
acceptance criteria not already covered there: byte-identical preservation of a
supplied identifier including surrounding whitespace, rejection of a missing
identifier, safe name trimming, and the absence of any rewrite/rename path.
"""

import pytest
from pydantic import ValidationError

from app.core.domain.graph_entities import POI


def make_payload(**overrides):
    payload = {
        "id": "legacy_source_key_0001",
        "name": "The Hidden Gem Cafe",
        "longitude": 106.7009,
        "latitude": 10.7769,
        "poi_categories": [
            {"id": "cat_cafe", "name": "Cafe", "context": "Coffee and pastries."}
        ],
    }
    payload.update(overrides)
    return payload


def test_supplied_identifier_is_byte_identical_including_surrounding_whitespace():
    supplied = "  legacy_source_key_0001  "
    poi = POI(**make_payload(id=supplied))
    assert poi.id == supplied


def test_missing_identifier_is_rejected():
    payload = make_payload()
    del payload["id"]
    with pytest.raises(ValidationError):
        POI(**payload)


def test_identifier_is_not_rewritten_when_category_and_address_absent():
    supplied = "opaque_external_key"
    poi = POI(id=supplied, name="Nameless Square", longitude=0.0, latitude=0.0)
    assert poi.id == supplied


def test_name_is_trimmed_safely():
    poi = POI(**make_payload(name="  The Hidden Gem Cafe  "))
    assert poi.name == "The Hidden Gem Cafe"


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_blank_name_is_rejected(blank):
    with pytest.raises(ValidationError):
        POI(**make_payload(name=blank))


def test_model_dump_does_not_rename_identifier():
    supplied = "legacy_source_key_0001"
    poi = POI(**make_payload(id=supplied))
    assert poi.model_dump()["id"] == supplied
