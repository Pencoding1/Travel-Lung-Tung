"""Service tests for the repaired deep-retrieval contract.

Uses a real ``POIManagementService`` with a fake UnitOfWork/repository; the
graph database is never contacted.
"""

import pytest

from app.core.services.management import EntityNotFoundError, POIManagementService
from mcp_fakes import (
    FakePOIRepository,
    FakeUnitOfWork,
    NotImplementedDocumentRepository,
    ThrowingDocumentRepository,
)


def _payload(
    poi_id="p1",
    *,
    address="1 Le Loi, Quan 1",
    category="Coffee",
    categories=None,
    operation_time="8am-5pm",
    latitude=10.0,
    longitude=106.0,
    contact=None,
    offers=None,
    nearby=None,
    chains=None,
):
    return {
        "POI_ID": poi_id,
        "POI_Name": "Cafe",
        "POI_Address": address,
        "POI_Category": category,
        "POI_Categories": categories if categories is not None else [
            {"id": "cat_a", "name": "Coffee", "context": "warm"}
        ],
        "operation_time": operation_time,
        "latitude": latitude,
        "longitude": longitude,
        "POI_Contact_Info": contact if contact is not None else {
            "phonenumber": "+84900000000", "fanpage": None, "website": None
        },
        "Offers": offers if offers is not None else [],
        "NEAR_BY": nearby if nearby is not None else [],
        "administrative_context_chains": chains if chains is not None else [
            {"city_id": "c1", "district_id": "d1",
             "city_name": "Hanoi", "district_name": "Quan 1"}
        ],
    }


def _service(payload):
    return POIManagementService(
        FakeUnitOfWork(FakePOIRepository(graph_payload=payload))
    )


def test_missing_poi_raises_not_found():
    with pytest.raises(EntityNotFoundError):
        _service(None).get_agentic_poi_details("p1", NotImplementedDocumentRepository())


def test_mismatched_returned_id_is_not_found():
    service = _service(_payload(poi_id="other"))
    with pytest.raises(EntityNotFoundError):
        service.get_agentic_poi_details("p1", NotImplementedDocumentRepository())


def test_unimplemented_document_rag_is_unavailable_with_null_rating():
    response = _service(_payload()).get_agentic_poi_details(
        "p1", NotImplementedDocumentRepository()
    )
    result = response.result
    assert result.POI_Description.status == "unavailable"
    assert result.POI_Description.review.rating is None
    assert "rating" in result.missing_data
    assert "description" in result.missing_data


def test_failing_document_rag_is_unavailable_without_leaking_message():
    response = _service(_payload()).get_agentic_poi_details(
        "p1", ThrowingDocumentRepository()
    )
    assert response.result.POI_Description.status == "unavailable"
    assert response.result.POI_Description.review.rating is None


def test_exact_requested_id_is_returned():
    response = _service(_payload(poi_id="p1")).get_agentic_poi_details(
        "p1", NotImplementedDocumentRepository()
    )
    assert response.result.POI_ID == "p1"


def test_offers_never_invent_name_or_price():
    offers = [
        {"name": None, "price": 2.5},
        {"name": "Latte", "price": None},
        {"name": None, "price": None},
        {"name": "Bad", "price": -3.0},
        {"name": "NaN", "price": float("nan")},
    ]
    result = _service(_payload(offers=offers)).get_agentic_poi_details(
        "p1", NotImplementedDocumentRepository()
    ).result

    dumped = result.Offers
    assert dumped[0].name is None and dumped[0].price == 2.5
    assert dumped[1].name == "Latte" and dumped[1].price is None
    # The nil/nil offer is dropped, not turned into "Unnamed Product".
    assert all(o.name != "Unnamed Product" for o in dumped)
    assert dumped[2].name == "Bad" and dumped[2].price is None
    assert dumped[3].price is None


def test_missing_distance_is_null_not_zero():
    nearby = [
        {"POI_ID": "n1", "POI_Name": "Near", "POI_Address": "x", "distance": None},
        {"POI_ID": "n2", "POI_Name": "Near2", "POI_Address": "y", "distance": -4.0},
    ]
    result = _service(_payload(nearby=nearby)).get_agentic_poi_details(
        "p1", NotImplementedDocumentRepository()
    ).result
    assert result.NEAR_BY[0].distance is None
    assert result.NEAR_BY[1].distance is None


def test_admin_context_resolved_and_preserved():
    result = _service(_payload()).get_agentic_poi_details(
        "p1", NotImplementedDocumentRepository()
    ).result
    assert result.administrative_context_status == "resolved"
    assert result.administrative_context.city_id == "c1"
    assert result.administrative_context.district_name == "Quan 1"


def test_admin_context_ambiguous_is_null():
    chains = [
        {"city_id": "c1", "district_id": "d1", "city_name": "Hanoi", "district_name": "Quan 1"},
        {"city_id": "c2", "district_id": "d2", "city_name": "Hanoi", "district_name": "Quan 2"},
    ]
    result = _service(_payload(chains=chains)).get_agentic_poi_details(
        "p1", NotImplementedDocumentRepository()
    ).result
    assert result.administrative_context is None
    assert result.administrative_context_status == "ambiguous"


def test_category_ids_and_operation_time_preserved():
    result = _service(_payload()).get_agentic_poi_details(
        "p1", NotImplementedDocumentRepository()
    ).result
    assert [c.id for c in result.POI_Categories] == ["cat_a"]
    assert result.operation_time == "8am-5pm"
    assert result.POI_Address == "1 Le Loi, Quan 1"


def test_missing_operation_time_and_address_are_listed():
    result = _service(
        _payload(address=None, operation_time=None)
    ).get_agentic_poi_details("p1", NotImplementedDocumentRepository()).result
    assert result.operation_time is None
    assert result.POI_Address is None
    assert "operation_time" in result.missing_data
    assert "address" in result.missing_data
