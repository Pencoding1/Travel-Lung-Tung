"""Cross-contract test: the repaired MCP payload must satisfy the AI grounding.

``ai_service/domains/grounding.py`` is owned by another task and is imported
read-only here. The test proves that a real ``get_poi_details`` JSON payload
produced through the service/fake-collaborator path satisfies
``grounding.parse_enrichment`` and ``grounding.poi_scope_status`` -- i.e. that
the upstream ``administrative_context`` contract the AI needs is actually
exposed. No model/graph/network call is made.
"""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.services.management import POIManagementService
from mcp_fakes import FakePOIRepository, FakeUnitOfWork, NotImplementedDocumentRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
GROUNDING_PATH = REPO_ROOT / "ai_service" / "domains" / "grounding.py"


def _load_grounding():
    if not GROUNDING_PATH.is_file():  # pragma: no cover - defensive
        pytest.skip("grounding module not present")
    spec = importlib.util.spec_from_file_location("oc007_grounding", GROUNDING_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GROUNDING = _load_grounding()


def _tool_result(payload_json: str):
    return SimpleNamespace(
        content=[SimpleNamespace(text=payload_json)],
        isError=False,
    )


def _details_json(chains):
    graph_payload = {
        "POI_ID": "p1",
        "POI_Name": "Cafe",
        "POI_Address": "1 Le Loi",
        "POI_Category": "Coffee",
        "POI_Categories": [{"id": "cat_a", "name": "Coffee", "context": "warm"}],
        "operation_time": "8am-5pm",
        "latitude": 10.0,
        "longitude": 106.0,
        "POI_Contact_Info": {"phonenumber": None, "fanpage": None, "website": None},
        "Offers": [{"name": "Latte", "price": 2.5}],
        "NEAR_BY": [],
        "administrative_context_chains": chains,
    }
    service = POIManagementService(
        FakeUnitOfWork(FakePOIRepository(graph_payload=graph_payload))
    )
    response = service.get_agentic_poi_details("p1", NotImplementedDocumentRepository())
    return response.model_dump_json()


def test_grounding_accepts_real_details_payload_and_verifies_scope():
    chains = [
        {"city_id": "c1", "district_id": "d1",
         "city_name": "Hanoi", "district_name": "Quan 1"}
    ]
    outcome = GROUNDING.parse_mcp_tool_result(_tool_result(_details_json(chains)))
    assert outcome.ok is True

    enrichment = GROUNDING.parse_enrichment(outcome, "p1")
    assert enrichment.ok is True
    admin = enrichment.data["administrative_context"]
    assert admin == {
        "city_id": "c1",
        "district_id": "d1",
        "city_name": "Hanoi",
        "district_name": "Quan 1",
    }

    district = {"id": "d1", "name": "Quan 1"}
    city = {"id": "c1", "name": "Hanoi"}
    assert GROUNDING.poi_scope_status(enrichment.data, district, city) == "verified"


def test_grounding_reports_conflict_for_mismatched_scope():
    chains = [
        {"city_id": "c9", "district_id": "d9",
         "city_name": "Hanoi", "district_name": "Quan 9"}
    ]
    outcome = GROUNDING.parse_mcp_tool_result(_tool_result(_details_json(chains)))
    enrichment = GROUNDING.parse_enrichment(outcome, "p1")
    district = {"id": "d1", "name": "Quan 1"}
    city = {"id": "c1", "name": "Hanoi"}
    assert GROUNDING.poi_scope_status(enrichment.data, district, city) == "conflict"


def test_grounding_reports_unknown_for_ambiguity():
    chains = [
        {"city_id": "c1", "district_id": "d1",
         "city_name": "Hanoi", "district_name": "Quan 1"},
        {"city_id": "c2", "district_id": "d2",
         "city_name": "Hanoi", "district_name": "Quan 2"},
    ]
    outcome = GROUNDING.parse_mcp_tool_result(_tool_result(_details_json(chains)))
    enrichment = GROUNDING.parse_enrichment(outcome, "p1")
    assert enrichment.data["administrative_context"] is None
    district = {"id": "d1", "name": "Quan 1"}
    city = {"id": "c1", "name": "Hanoi"}
    assert GROUNDING.poi_scope_status(enrichment.data, district, city) == "unknown"
