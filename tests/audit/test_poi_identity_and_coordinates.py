"""Baseline regression tests for POI identity and coordinate validation.

These tests assert required behavior and are expected to FAIL against the
current application source. They exist to demonstrate the current defects in
a reproducible way; they do NOT bless the current behavior.

Scope: only the safe domain module ``app.core.domain.graph_entities`` is
imported. No database connectors, no ingestion scripts, no network calls.
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.core.domain.graph_entities import POI
from app.core.utils.helper import normalize_for_id


def make_payload(**overrides):
    """A structurally valid POI payload used as the base for each test."""
    payload = {
        "id": "poi_imported_legacy_0001",
        "name": "The Hidden Gem Cafe",
        "longitude": 106.7009,
        "latitude": 10.7769,
        "poi_categories": [
            {
                "id": "cat_cafe",
                "name": "Cafe",
                "context": "A place serving coffee and light pastries.",
            }
        ],
        "address": {
            "street_name": "Le Loi",
            "district": "District 1",
            "city": "Ho Chi Minh City",
            "nation": "Vietnam",
        },
    }
    payload.update(overrides)
    return payload


def expected_id_prefix(category_name, address):
    """Mirror the production ID scheme to build an already-conforming ID.

    Used by the round-trip test so the supplied identifier is a legal,
    existing identifier rather than a malformed one.
    """
    province = normalize_for_id(address["city"], entity_type="city")
    district = normalize_for_id(
        address["district"], entity_type="district", context_city=province
    )
    parts = [normalize_for_id(category_name), province, district]
    if address.get("street_name"):
        parts.append(normalize_for_id(address["street_name"]))
    parts.append(datetime.now().strftime("%Y%m%d"))
    return "_".join(str(part) for part in parts if part)


# --- Test case 1: supplied POI id must remain byte-identical -----------------
def test_supplied_poi_id_is_byte_identical_across_validation():
    supplied = "poi_imported_legacy_0001"
    poi = POI(**make_payload(id=supplied))
    assert poi.id == supplied, (
        "A supplied POI identifier must be preserved byte-for-byte, "
        f"but validation rewrote it to {poi.id!r}."
    )


def test_supplied_poi_id_survives_category_and_address_changes():
    supplied = "poi_imported_legacy_0001"
    changed = make_payload(
        id=supplied,
        poi_categories=[
            {"id": "cat_food", "name": "Local Food", "context": "Street food."}
        ],
        address={
            "street_name": "Ham Nghi",
            "district": "District 3",
            "city": "Ha Noi",
            "nation": "Vietnam",
        },
    )
    poi = POI(**changed)
    assert poi.id == supplied, (
        "Changing category/address must not mutate an explicit POI "
        f"identifier, but it was rewritten to {poi.id!r}."
    )


# --- Test case 2: reject nonfinite and out-of-range coordinates --------------
@pytest.mark.parametrize(
    "latitude,longitude,label",
    [
        (float("nan"), 106.7009, "nan_latitude"),
        (10.7769, float("nan"), "nan_longitude"),
        (float("inf"), 106.7009, "inf_latitude"),
        (10.7769, float("inf"), "inf_longitude"),
        (float("-inf"), 106.7009, "neg_inf_latitude"),
        (10.7769, float("-inf"), "neg_inf_longitude"),
        (-90.0001, 106.7009, "latitude_below_min"),
        (90.0001, 106.7009, "latitude_above_max"),
        (10.7769, -180.0001, "longitude_below_min"),
        (10.7769, 180.0001, "longitude_above_max"),
    ],
)
def test_reject_nonfinite_and_out_of_range_coordinates(latitude, longitude, label):
    with pytest.raises(ValidationError):
        POI(**make_payload(latitude=latitude, longitude=longitude))


# --- Test case 3: legal boundary coordinates accepted ------------------------
@pytest.mark.parametrize(
    "latitude,longitude",
    [
        (-90.0, -180.0),
        (90.0, 180.0),
        (90.0, -180.0),
        (-90.0, 180.0),
        (0.0, 0.0),
    ],
)
def test_accept_legal_boundary_coordinates(latitude, longitude):
    poi = POI(**make_payload(latitude=latitude, longitude=longitude))
    assert poi.latitude == latitude
    assert poi.longitude == longitude


# --- Test case 4: reject blank POI name and blank explicit identifier --------
@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_reject_blank_poi_name(blank):
    with pytest.raises(ValidationError):
        POI(**make_payload(name=blank))


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_reject_blank_explicit_identifier(blank):
    with pytest.raises(ValidationError):
        POI(**make_payload(id=blank))


# --- Test case 5: valid POI round-trips without ID changes -------------------
def test_existing_valid_poi_round_trips_without_id_change():
    address = {
        "street_name": "Le Loi",
        "district": "District 1",
        "city": "Ho Chi Minh City",
        "nation": "Vietnam",
    }
    poi_id = f"{expected_id_prefix('Cafe', address)}_abc123"
    original = POI(**make_payload(id=poi_id))
    assert original.id == poi_id

    dumped = original.model_dump()
    round_tripped = POI(**dumped)

    assert round_tripped.id == poi_id
    assert round_tripped.model_dump() == dumped
