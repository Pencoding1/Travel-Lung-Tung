"""Service validation tests for conjunctive exploration."""

import pytest

from app.core.domain.get_payload import POICompoundLite
from app.core.services.management import InvalidRequestError, POIManagementService
from mcp_fakes import FakePOIRepository, FakeUnitOfWork


def _service(results=None):
    repo = FakePOIRepository(compound_results=results or [])
    return POIManagementService(FakeUnitOfWork(repo)), repo


def test_no_criteria_is_invalid():
    service, _ = _service()
    with pytest.raises(InvalidRequestError):
        service.explore_compound()


def test_blank_strings_count_as_no_criteria():
    service, _ = _service()
    with pytest.raises(InvalidRequestError):
        service.explore_compound(city_id="   ", category_id="")


@pytest.mark.parametrize("bad_limit", [0, 101, -1, "15", 1.5, True, None])
def test_invalid_limit_is_rejected(bad_limit):
    service, _ = _service()
    with pytest.raises(InvalidRequestError):
        service.explore_compound(city_id="c1", limit=bad_limit)


@pytest.mark.parametrize("bad_offset", [-1, "0", 1.5, True, None])
def test_invalid_offset_is_rejected(bad_offset):
    service, _ = _service()
    with pytest.raises(InvalidRequestError):
        service.explore_compound(city_id="c1", offset=bad_offset)


def test_non_string_identifier_is_rejected():
    service, _ = _service()
    with pytest.raises(InvalidRequestError):
        service.explore_compound(city_id=123)


def test_valid_request_forwards_exact_ids_verbatim():
    poi = POICompoundLite(id="p1", name="Cafe")
    service, repo = _service([poi])
    out = service.explore_compound(
        city_id="c1", district_id="d1", category_id="cat_a",
        product_keyword="latte", limit=20, offset=3,
    )
    assert out == [poi.model_dump()]
    called = repo.compound_calls[0]
    assert called == {
        "city_id": "c1",
        "district_id": "d1",
        "street_id": None,
        "category_id": "cat_a",
        "product_keyword": "latte",
        "limit": 20,
        "offset": 3,
    }


def test_category_id_is_not_transformed_to_display_name():
    service, repo = _service([])
    service.explore_compound(category_id="cat_coffee")
    assert repo.compound_calls[0]["category_id"] == "cat_coffee"


def test_inconsistent_city_district_yields_empty_from_repository():
    # The repository returns nothing when the district is not under the city;
    # the service passes that through as an empty list (no fallback inference).
    service, repo = _service([])
    out = service.explore_compound(city_id="c1", district_id="d_other")
    assert out == []
    assert repo.compound_calls[0]["district_id"] == "d_other"
