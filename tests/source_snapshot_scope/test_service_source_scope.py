"""Service-level discovery, conflict and detail evidence for source scope."""

import pytest

from app.core.domain.source_scope import (
    CURRENT_BOUNDARY_UNCERTAINTY,
    derive_source_area_id,
)
from app.core.services.management import POIManagementService, InvalidRequestError
from scope_fixtures import (
    INPUT_SHA,
    NAMESPACE,
    POI_ID,
    graph_record,
    lineage_row,
    typed_metadata,
)

OTHER_SHA = "b" * 64
OTHER_POI_ID = "hcm_primary_geojson_internal:other000000000000000000000000000000"


class FakeRepo:
    def __init__(self, *, rows=None, graph_payload=None, source_results=None):
        self.rows = list(rows or [])
        self.graph_payload = graph_payload
        self.source_results = source_results or ([], {})
        self.source_calls = []

    def iter_source_scope_records(self, after_id=None, limit=500):
        start = 0
        if after_id is not None:
            for index, row in enumerate(self.rows):
                if row.get("id") == after_id:
                    start = index + 1
                    break
        return self.rows[start : start + limit]

    def get_poi_graph_payload(self, id, radius_km=3.0, limit=5):
        return self.graph_payload

    def get_compound_explore_source(self, selection, **kwargs):
        self.source_calls.append((selection, kwargs))
        return self.source_results


class FakeUoW:
    def __init__(self, repo):
        self.pois = repo
        self.entered = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc_val, traceback):
        return False


class StubDocRepo:
    def get_poi_documents(self, poi_id):
        return {"insight": "", "seo_article": "", "review": {"rating": None}}


def _stored(row):
    return graph_record(row["id"], row=row)


def test_source_scope_conflict_is_rejected_before_entering_the_repository():
    repo = FakeRepo()
    uow = FakeUoW(repo)
    service = POIManagementService(uow)
    selection = {
        "dataset_namespace": NAMESPACE,
        "input_sha256": INPUT_SHA,
        "source_area_id": derive_source_area_id(
            NAMESPACE, INPUT_SHA, "HCMC", "Go Vap"
        ),
    }
    with pytest.raises(InvalidRequestError):
        service.explore_compound(source_scope=selection, district_id="d1")
    assert uow.entered is False
    assert repo.source_calls == []


def test_discovery_lists_distinct_snapshots_and_excludes_corrupt_rows():
    second_row = lineage_row(
        poi_id=OTHER_POI_ID,
        input_sha=OTHER_SHA,
        raw_city="Hanoi",
        raw_district="Go Vap",
        internal_record_id="r999999",
    )
    corrupt = graph_record(override_sha="0" * 64, cached=False)
    repo = FakeRepo(rows=[_stored(lineage_row()), _stored(second_row), corrupt])
    service = POIManagementService(FakeUoW(repo))

    payload = service.list_source_snapshots()
    assert payload["scan"]["scanned_record_count"] == 3
    assert payload["scan"]["excluded_corrupt_count"] == 1
    assert payload["scan"]["truncated"] is False
    assert [item["input_sha256"] for item in payload["snapshots"]] == [
        INPUT_SHA,
        OTHER_SHA,
    ]
    assert [item["valid_record_count"] for item in payload["snapshots"]] == [1, 1]
    for item in payload["snapshots"]:
        assert item["current_boundary_uncertainty"] == CURRENT_BOUNDARY_UNCERTAINTY


def test_equal_area_labels_across_cities_and_snapshots_have_distinct_selectors():
    same_label_other_city = lineage_row(
        poi_id=OTHER_POI_ID,
        raw_city="Hanoi",
        raw_district="Go Vap",
        internal_record_id="r999999",
    )
    repo = FakeRepo(rows=[_stored(lineage_row()), _stored(same_label_other_city)])
    service = POIManagementService(FakeUoW(repo))

    payload = service.list_source_areas(
        {"dataset_namespace": NAMESPACE, "input_sha256": INPUT_SHA}
    )
    assert [area["raw_city"] for area in payload["source_areas"]] == ["HCMC", "Hanoi"]
    ids = {area["source_area_id"] for area in payload["source_areas"]}
    assert len(ids) == 2
    assert ids == {
        derive_source_area_id(NAMESPACE, INPUT_SHA, "HCMC", "Go Vap"),
        derive_source_area_id(NAMESPACE, INPUT_SHA, "Hanoi", "Go Vap"),
    }
    for area in payload["source_areas"]:
        assert area["valid_record_count"] == 1
        assert area["current_boundary_uncertainty"] == CURRENT_BOUNDARY_UNCERTAINTY


def test_unassigned_source_area_is_explicit_and_never_invents_a_name():
    row = lineage_row(raw_city="HCMC", raw_district=None)
    repo = FakeRepo(rows=[_stored(row)])
    service = POIManagementService(FakeUoW(repo))

    payload = service.list_source_areas(
        {"dataset_namespace": NAMESPACE, "input_sha256": INPUT_SHA}
    )
    area = payload["source_areas"][0]
    assert area["raw_city"] == "HCMC"
    assert area["raw_area"] is None
    assert area["area_assignment"] == "unassigned"
    assert area["source_area_label"] == "HCMC"


def test_source_explore_returns_scan_report_with_current_boundary_uncertainty():
    from app.core.domain.get_payload import POICompoundLite
    from app.core.domain.source_scope import (
        build_source_context,
        derive_source_area,
    )

    metadata = typed_metadata()
    identity = derive_source_area(metadata)
    item = POICompoundLite(
        id=POI_ID,
        name="the gioi sua",
        administrative_context_status="unverified_source_area",
        source_context=build_source_context(identity, metadata),
        administrative_scope="source_snapshot_area_only",
    )
    repo = FakeRepo(
        source_results=(
            [item],
            {
                "scanned_record_count": 7,
                "matched_record_count": 1,
                "excluded_corrupt_count": 2,
                "excluded_scope_mismatch_count": 4,
                "scan_complete": True,
                "truncated": False,
            },
        )
    )
    service = POIManagementService(FakeUoW(repo))
    selection = {
        "dataset_namespace": NAMESPACE,
        "input_sha256": INPUT_SHA,
        "source_area_id": identity.source_area_id,
    }
    payload = service.explore_compound(source_scope=selection, limit=15)
    assert payload["source_scan"]["scanned_record_count"] == 7
    assert payload["source_scan"]["truncated"] is False
    assert payload["source_scan"]["current_boundary_uncertainty"] == (
        CURRENT_BOUNDARY_UNCERTAINTY
    )
    result = payload["results"][0]
    assert result["source_context"]["raw_city"] == "HCMC"
    assert result["source_context"]["raw_area"] == "Go Vap"
    assert "raw_lineage_json" not in result
    assert result["administrative_context"] is None


def test_details_expose_compact_source_context_and_no_raw_lineage():
    record = graph_record()
    graph_payload = {
        "POI_ID": POI_ID,
        "POI_Name": "the gioi sua",
        "POI_Address": "681, Go Vap, HCMC",
        "POI_Category": "Retail Center",
        "POI_Categories": [],
        "operation_time": None,
        "latitude": 10.8482306,
        "longitude": 106.6677248,
        "source_metadata_json": record["source_metadata_json"],
        "source_metadata_sha256": record["source_metadata_sha256"],
        "administrative_scope": record["administrative_scope"],
        "POI_Contact_Info": {},
        "Offers": [],
        "NEAR_BY": [],
        "administrative_context_chains": [],
    }
    service = POIManagementService(FakeUoW(FakeRepo(graph_payload=graph_payload)))
    response = service.get_agentic_poi_details(POI_ID, StubDocRepo())
    result = response.result
    assert result.administrative_context is None
    assert result.administrative_context_status == "unverified_source_area"
    assert result.source_context is not None
    assert result.source_context.raw_city == "HCMC"
    assert result.source_context.raw_area == "Go Vap"
    dumped = result.model_dump_json()
    assert "raw_lineage_json" not in dumped
    assert '"district_id"' not in dumped
