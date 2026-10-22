"""Actual MCP registration, schema and in-process call contract.

These tests use the real ``FastMCP`` object exported by ``tools`` (no transport
socket) and a real subprocess to prove importing ``tools`` has no database or
credential side effects.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import app.api.mcp.tools as tools
from app.api.mcp.tools import mcp
from mcp_fakes import FakePOIRepository, FakeUnitOfWork

REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_TOOLS = {
    "get_poi_details",
    "get_itinerary_route",
    "explore_pois",
    "get_available_categories",
    "resolve_geographic_id",
}


def _reset():
    tools.reset_uow_factory()
    tools.reset_http_client_factory()


def test_all_tools_are_registered_with_expected_names():
    _reset()
    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert names == EXPECTED_TOOLS


def test_explore_pois_schema_exposes_exact_id_parameters():
    _reset()
    tool = next(t for t in asyncio.run(mcp.list_tools()) if t.name == "explore_pois")
    properties = set(tool.inputSchema["properties"])
    assert {
        "city_id", "district_id", "street_id",
        "category_id", "product_keyword", "limit", "offset",
    } <= properties


def test_itinerary_route_schema_exposes_ordered_ids_and_profile():
    _reset()
    tool = next(t for t in asyncio.run(mcp.list_tools()) if t.name == "get_itinerary_route")
    assert "ordered_poi_ids" in tool.inputSchema["properties"]
    assert "vehicle" in tool.inputSchema["properties"]


def test_inprocess_call_returns_empty_category_list():
    _reset()
    tools.set_uow_factory(lambda: FakeUnitOfWork(FakePOIRepository(categories=[])))
    content, _structured = asyncio.run(mcp.call_tool("get_available_categories", {}))
    payload = json.loads(content[0].text)
    assert payload["success"] is True
    assert payload["categories"] == []
    _reset()


def test_inprocess_call_explore_pois():
    _reset()
    tools.set_uow_factory(lambda: FakeUnitOfWork(FakePOIRepository(compound_results=[])))
    content, _structured = asyncio.run(mcp.call_tool("explore_pois", {"city_id": "c1"}))
    payload = json.loads(content[0].text)
    assert payload["success"] is True
    assert payload["results"] == []
    _reset()


def test_decorated_functions_remain_directly_callable():
    # ``mcp.tool`` returns the original function, so the contract can be called
    # as a plain function too.
    assert tools.get_available_categories.__name__ == "get_available_categories"
    assert callable(tools.explore_pois)


_IMPORT_ISOLATION_SCRIPT = (
    "import sys, os\n"
    "root = os.getcwd()\n"
    "sys.path.insert(0, os.path.join(root, 'POI_service'))\n"
    "sys.path.insert(0, os.path.join(root, 'shared_lib'))\n"
    "import app.api.mcp.tools\n"
    "sensitive = [m for m in sys.modules if any(k in m for k in (\n"
    "    'firebase', 'app.core.config.settings',\n"
    "    'app.core.infrastructure.db.database.connector',\n"
    "    'app.core.infrastructure.db.uow', 'neo4j'))]\n"
    "assert not sensitive, sensitive\n"
    "print('CLEAN')\n"
)


def test_importing_tools_has_no_database_or_credential_side_effects():
    result = subprocess.run(
        [sys.executable, "-c", _IMPORT_ISOLATION_SCRIPT],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "CLEAN" in result.stdout
