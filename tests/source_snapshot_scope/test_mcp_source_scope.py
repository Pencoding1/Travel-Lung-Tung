"""Actual FastMCP schema and in-process calls for explicit source selection."""

import asyncio
import json

import pytest

pytest.importorskip("mcp")

import app.api.mcp.tools as tools
from app.api.mcp.tools import mcp
from app.core.domain.get_payload import POICompoundLite
from app.core.domain.source_scope import build_source_context, derive_source_area
from scope_fixtures import INPUT_SHA, NAMESPACE, POI_ID, graph_record, typed_metadata


class FakeRepo:
    def __init__(self, *, rows=None, source_results=None):
        self.rows = list(rows or [])
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

    def get_compound_explore_source(self, selection, **kwargs):
        self.source_calls.append((selection, kwargs))
        return self.source_results


class FakeUoW:
    def __init__(self, repo):
        self.pois = repo

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, traceback):
        return False


def _reset():
    tools.reset_uow_factory()
    tools.reset_http_client_factory()


def test_explore_schema_exposes_source_discovery_and_typed_selection():
    _reset()
    tool = next(
        t for t in asyncio.run(mcp.list_tools()) if t.name == "explore_pois"
    )
    properties = tool.inputSchema["properties"]
    assert {"source_scope", "source_snapshot", "source_discovery"} <= set(properties)
    assert "source_context" in tool.description
    _reset()


def test_registered_tool_set_is_unchanged():
    _reset()
    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert names == {
        "get_poi_details",
        "get_itinerary_route",
        "explore_pois",
        "get_available_categories",
        "resolve_geographic_id",
    }
    _reset()


def test_mcp_snapshot_discovery_call_uses_existing_tool():
    _reset()
    record = graph_record()
    tools.set_uow_factory(lambda: FakeUoW(FakeRepo(rows=[record])))
    content, _structured = asyncio.run(
        mcp.call_tool("explore_pois", {"source_discovery": "snapshots"})
    )
    payload = json.loads(content[0].text)
    assert payload["success"] is True
    assert payload["mode"] == "snapshots"
    assert payload["snapshots"][0]["dataset_namespace"] == NAMESPACE
    assert payload["snapshots"][0]["input_sha256"] == INPUT_SHA
    assert payload["snapshots"][0]["valid_record_count"] == 1
    _reset()


def test_mcp_source_scope_call_returns_typed_compact_context():
    _reset()
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
                "scanned_record_count": 10,
                "matched_record_count": 1,
                "excluded_corrupt_count": 0,
                "excluded_scope_mismatch_count": 9,
                "scan_complete": True,
                "truncated": False,
            },
        )
    )
    tools.set_uow_factory(lambda: FakeUoW(repo))
    content, _structured = asyncio.run(
        mcp.call_tool(
            "explore_pois",
            {
                "source_scope": {
                    "dataset_namespace": NAMESPACE,
                    "input_sha256": INPUT_SHA,
                    "source_area_id": identity.source_area_id,
                }
            },
        )
    )
    payload = json.loads(content[0].text)
    assert payload["success"] is True
    assert payload["count"] == 1
    assert payload["source_scan"]["matched_record_count"] == 1
    result = payload["results"][0]
    assert result["source_context"]["source_area_id"] == identity.source_area_id
    assert result["source_context"]["raw_city"] == "HCMC"
    assert "raw_lineage_json" not in json.dumps(result)
    assert repo.source_calls[0][0].source_area_id == identity.source_area_id
    _reset()


def test_mcp_rejects_current_ids_with_source_scope_before_query():
    _reset()
    repo = FakeRepo()
    tools.set_uow_factory(lambda: FakeUoW(repo))
    content, _structured = asyncio.run(
        mcp.call_tool(
            "explore_pois",
            {
                "district_id": "district_1",
                "source_scope": {
                    "dataset_namespace": NAMESPACE,
                    "input_sha256": INPUT_SHA,
                    "source_area_id": "district_1",
                },
            },
        )
    )
    payload = json.loads(content[0].text)
    assert payload["success"] is False
    assert payload["code"] == "invalid_request"
    assert repo.source_calls == []
    _reset()
