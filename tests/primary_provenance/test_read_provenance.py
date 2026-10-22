"""OC-038 production read-projection tests (no graph/network call).

These drive the real ``POIManagementService`` with the actual Pydantic read
models and a fake repository payload. They prove that source-only records are
never reported as resolved current jurisdiction and that provenance-free read
shape stays unchanged.
"""

import hashlib

from app.core.domain.graph_entities import (
    POI,
    canonical_source_metadata_json,
)
from app.core.services.management import POIManagementService
from provenance_fixtures import POI_ID, metadata_dict, poi_payload


class FakePOIRepository:
    def __init__(self, payload):
        self.payload = payload

    def get_poi_graph_payload(self, id, radius_km=3.0, limit=5):
        return self.payload


class FakeUnitOfWork:
    def __init__(self, repo):
        self.pois = repo

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, traceback):
        return False


class FakeDocumentRepository:
    def get_poi_documents(self, poi_id):
        return {"insight": "", "seo_article": "", "review": None}


def _graph_payload(
    *, poi_id=POI_ID, metadata=None, chains=None, address="source full address"
):
    payload = {
        "POI_ID": poi_id,
        "POI_Name": "the gioi sua",
        "POI_Address": address,
        "POI_Category": "Retail Center",
        "POI_Categories": [
            {"id": "cat", "name": "Retail Center", "context": "source label"}
        ],
        "operation_time": "8am-5pm",
        "latitude": 10.8482306,
        "longitude": 106.6677248,
        "POI_Contact_Info": {"phonenumber": None, "fanpage": None, "website": None},
        "Offers": [],
        "NEAR_BY": [],
        "administrative_context_chains": chains or [],
        "source_metadata_json": None,
        "source_metadata_sha256": None,
        "administrative_scope": None,
    }
    if metadata is not None:
        entity = POI.model_validate(poi_payload(source_metadata=metadata))
        canonical = canonical_source_metadata_json(entity.source_metadata)
        payload["source_metadata_json"] = canonical
        payload["source_metadata_sha256"] = hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()
        payload["administrative_scope"] = metadata["administrative_scope"]
    return payload


def _details(payload, poi_id=POI_ID):
    service = POIManagementService(FakeUnitOfWork(FakePOIRepository(payload)))
    return service.get_agentic_poi_details(
        poi_id, FakeDocumentRepository()
    ).result


def test_source_only_details_are_never_resolved_as_current_context():
    resolved_chain = {
        "city_id": "hcmc_vietnam",
        "district_id": "go vap_hcmc",
        "city_name": "HCMC",
        "district_name": "Go Vap",
    }
    result = _details(
        _graph_payload(metadata=metadata_dict(), chains=[resolved_chain])
    )

    assert result.administrative_context is None
    assert result.administrative_context_status == "unverified_source_area"
    assert result.administrative_scope == "source_snapshot_area_only"
    assert result.source_metadata_status == "valid"
    assert result.source_metadata is not None
    assert result.source_metadata.internal_record_id == "r005494"
    assert result.source_metadata.raw_lineage_sha256 == metadata_dict()[
        "raw_lineage_sha256"
    ]
    assert result.source_metadata.raw_lineage_reference.startswith(
        "graph:POI.source_metadata_json#"
    )
    # The AI-facing projection must never repeat the full raw lineage blob.
    assert "raw_lineage_json" not in result.model_dump_json()
    # Full address is preserved as the source display claim.
    assert result.POI_Address == "source full address"
    assert "current_administrative_context" in result.missing_data


def test_source_metadata_with_self_consistent_hashes_but_wrong_poi_binding_is_corrupt():
    wrong_id = "WRONG_INDEPENDENT_TEST_ID"
    payload = _graph_payload(
        poi_id=wrong_id,
        metadata=metadata_dict(),
        chains=[
            {
                "city_id": "hcmc_vietnam",
                "district_id": "go vap_hcmc",
                "city_name": "HCMC",
                "district_name": "Go Vap",
            }
        ],
    )

    result = _details(payload, poi_id=wrong_id)

    assert result.POI_ID == wrong_id
    assert result.source_metadata is None
    assert result.source_metadata_status == "corrupt"
    assert result.administrative_context is None
    assert result.administrative_context_status == "provenance_corrupt"


def test_corrupt_stored_provenance_is_explicit_and_not_trusted():
    payload = _graph_payload(
        chains=[
            {
                "city_id": "c1",
                "district_id": "d1",
                "city_name": "HCMC",
                "district_name": "Go Vap",
            }
        ]
    )
    payload["source_metadata_json"] = "{not json"
    payload["source_metadata_sha256"] = "0" * 64
    payload["administrative_scope"] = "source_snapshot_area_only"

    result = _details(payload)

    assert result.source_metadata is None
    assert result.source_metadata_status == "corrupt"
    assert result.administrative_context is None
    assert result.administrative_context_status == "provenance_corrupt"
    assert "source_metadata" in result.missing_data


def test_provenance_free_read_shape_is_unchanged():
    result = _details(_graph_payload())
    dumped = result.model_dump()
    assert "source_metadata" not in dumped
    assert "source_metadata_status" not in dumped
    assert "administrative_scope" not in dumped
    # Ordinary verified/legacy chains still resolve exactly as before.
    result_with_chain = _details(
        _graph_payload(
            chains=[
                {
                    "city_id": "c1",
                    "district_id": "d1",
                    "city_name": "HCMC",
                    "district_name": "Go Vap",
                }
            ]
        )
    )
    assert result_with_chain.administrative_context_status == "resolved"
    assert result_with_chain.administrative_context.district_name == "Go Vap"
