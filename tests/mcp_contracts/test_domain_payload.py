"""Domain-level contract tests for the repaired MCP payload types.

Pure unit tests (pydantic only). No database, network or connector import.
"""

import math

import pytest

from app.core.domain.get_payload import (
    AdministrativeContext,
    CategoryRef,
    NearbyPOI,
    OfferLite,
    POILite,
    POIResult,
    POIDescription,
    ReviewDetail,
    resolve_administrative_context,
)


# ---------------------------------------------------------------------------
# Resolver: exact structured evidence only
# ---------------------------------------------------------------------------
def _chain(city_id="c1", district_id="d1", city_name="Hanoi", district_name="Quan 1"):
    return {
        "city_id": city_id,
        "district_id": district_id,
        "city_name": city_name,
        "district_name": district_name,
    }


def test_resolve_single_complete_chain_is_resolved():
    context, status = resolve_administrative_context([_chain()])
    assert status == "resolved"
    assert context == {
        "city_id": "c1",
        "district_id": "d1",
        "city_name": "Hanoi",
        "district_name": "Quan 1",
    }


def test_resolve_empty_is_missing():
    assert resolve_administrative_context([]) == (None, "missing")
    assert resolve_administrative_context(None) == (None, "missing")


def test_resolve_partial_chain_is_incomplete_not_resolved():
    partial = [{"city_id": "c1", "district_id": None, "city_name": "Hanoi", "district_name": None}]
    assert resolve_administrative_context(partial) == (None, "incomplete")


def test_resolve_blank_strings_are_incomplete():
    blank = [_chain(city_name="   ", district_name="")]
    assert resolve_administrative_context(blank) == (None, "incomplete")


def test_resolve_contradictory_chains_are_ambiguous_never_first():
    a = _chain(city_id="c1", district_id="d1")
    b = _chain(city_id="c2", district_id="d2")
    assert resolve_administrative_context([a, b]) == (None, "ambiguous")


def test_resolve_duplicate_chains_still_resolved():
    chain = _chain()
    context, status = resolve_administrative_context([chain, dict(chain)])
    assert status == "resolved"
    assert context["district_id"] == "d1"


# ---------------------------------------------------------------------------
# Null-truthful field validation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), -1.0, -0.5, "abc", None, True])
def test_offer_price_invalid_values_become_none(bad):
    assert OfferLite(name="Coffee", price=bad).price is None


def test_offer_price_zero_is_retained_but_never_fabricated():
    # An explicit 0 is a valid finite nonnegative value; a *missing* price stays None.
    assert OfferLite(name="Coffee", price=0.0).price == 0.0
    assert OfferLite(name="Coffee").price is None
    assert OfferLite().name is None


def test_offer_name_may_be_absent():
    offer = OfferLite(price=2.5)
    assert offer.name is None
    assert offer.price == 2.5


@pytest.mark.parametrize("bad", [float("nan"), -2.0, "x", None])
def test_distance_bad_values_become_none(bad):
    assert NearbyPOI(poi=POILite(id="p", name="P"), distance=bad).distance is None


def test_distance_zero_is_valid():
    assert NearbyPOI(poi=POILite(id="p", name="P"), distance=0.0).distance == 0.0


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0, "nope"])
def test_rating_bad_values_become_none(bad):
    assert ReviewDetail(rating=bad).rating is None


def test_rating_none_is_preserved():
    assert ReviewDetail(rating=None).rating is None


# ---------------------------------------------------------------------------
# POIResult carries structured context and explicit categories
# ---------------------------------------------------------------------------
def test_poi_result_default_context_and_optional_fields():
    result = POIResult(
        POI_ID="p1",
        POI_Name="Place",
        POI_Description=POIDescription(),
        POI_Contact_Info={},
    )
    assert result.administrative_context is None
    assert result.administrative_context_status == "missing"
    assert result.POI_Categories == []
    assert result.operation_time is None
    assert result.missing_data == []


def test_poi_result_exposes_admin_context_and_category_ids():
    result = POIResult(
        POI_ID="p1",
        POI_Name="Place",
        POI_Description=POIDescription(),
        POI_Contact_Info={},
        administrative_context=AdministrativeContext(
            city_id="c1", district_id="d1", city_name="Hanoi", district_name="Quan 1"
        ),
        administrative_context_status="resolved",
        POI_Categories=[CategoryRef(id="cat_a", name="Coffee", context="ctx")],
        operation_time="8am-5pm",
        missing_data=["rating"],
    )
    dumped = result.model_dump()
    assert dumped["administrative_context"]["city_id"] == "c1"
    assert dumped["POI_Categories"][0]["id"] == "cat_a"
    assert dumped["operation_time"] == "8am-5pm"
