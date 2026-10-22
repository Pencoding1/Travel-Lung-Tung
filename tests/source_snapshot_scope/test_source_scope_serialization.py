"""T061 regression: source-scope results must survive JSON serialization.

``SourceEvidenceSummary.provided_at`` is a ``datetime.date``. When the service
returned ``poi.model_dump()`` (python mode) the ``date`` object survived into
the dict, and ``json.dumps`` inside the MCP tool raised
``TypeError: Object of type date is not JSON serializable``. That error was then
swallowed by the catch-all handler, so an MCP client only ever saw
``exploration_failed`` / "Exploration failed.".

These tests drive the real service and the real FastMCP tool with an
item shaped exactly like ``MemgraphPOIRepository`` builds it (a
``SourceEvidenceSummary`` populated from typed metadata), so the regression is
covered at the same place the canary blew up.
"""

import asyncio
import json
import re
from datetime import date, datetime

import pytest

pytest.importorskip("mcp")

import app.api.mcp.tools as tools
from app.api.mcp.tools import mcp
from app.core.domain.get_payload import POICompoundLite, SourceEvidenceSummary
from app.core.domain.source_scope import build_source_context, derive_source_area
from app.core.services.management import POIManagementService
from scope_fixtures import INPUT_SHA, NAMESPACE, POI_ID, typed_metadata

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SCAN_REPORT = {
    "scanned_record_count": 10,
    "matched_record_count": 1,
    "excluded_corrupt_count": 0,
    "excluded_scope_mismatch_count": 9,
    "scan_complete": True,
    "truncated": False,
}


class FakeRepo:
    def __init__(self, source_results=None):
        self.source_results = source_results or ([], dict(SCAN_REPORT))
        self.source_calls = []

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


class UnserializableItem:
    """A result item whose python-mode dump keeps a non-JSON object."""

    def __init__(self, poison):
        self._poison = poison

    def model_dump(self, mode="python"):
        return {"id": "poisoned", "provided_at": self._poison}


def _reset():
    tools.reset_uow_factory()
    tools.reset_http_client_factory()


def _metadata():
    return typed_metadata()


def _selection_payload():
    identity = derive_source_area(_metadata())
    return {
        "dataset_namespace": NAMESPACE,
        "input_sha256": INPUT_SHA,
        "source_area_id": identity.source_area_id,
    }


def _source_poi():
    """Mirror ``MemgraphPOIRepository._build_source_scope_compound``."""
    metadata = _metadata()
    identity = derive_source_area(metadata)
    return POICompoundLite(
        id=POI_ID,
        name="the gioi sua",
        full_address="681 Đường Lê Đức Thọ, Go Vap, HCMC",
        categories=[],
        offers=[],
        administrative_context=None,
        administrative_context_status="unverified_source_area",
        source_metadata=SourceEvidenceSummary.from_metadata(metadata),
        source_metadata_status="valid",
        source_context=build_source_context(identity, metadata),
        administrative_scope=metadata.administrative_scope,
    )


def _walk(node, path="root"):
    """Yield ``(path, value)`` for every leaf/container in a nested payload."""
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")


def _assert_no_date_objects(payload):
    offenders = [
        path
        for path, value in _walk(payload)
        if isinstance(value, (date, datetime))
    ]
    assert offenders == [], f"non-JSON temporal objects survived at {offenders}"


def test_service_source_scope_payload_is_json_serializable():
    _reset()
    service = POIManagementService(FakeUoW(FakeRepo(([_source_poi()], dict(SCAN_REPORT)))))
    payload = service.explore_source_scope_compound(source_scope=_selection_payload())

    encoded = json.dumps(payload)
    decoded = json.loads(encoded)

    assert decoded["results"][0]["id"] == POI_ID
    _assert_no_date_objects(payload)
    _assert_no_date_objects(decoded)


def test_service_source_scope_provided_at_is_iso_date_string():
    _reset()
    service = POIManagementService(FakeUoW(FakeRepo(([_source_poi()], dict(SCAN_REPORT)))))
    payload = service.explore_source_scope_compound(source_scope=_selection_payload())

    provided_at = payload["results"][0]["source_metadata"]["provided_at"]
    assert isinstance(provided_at, str)
    assert ISO_DATE_RE.fullmatch(provided_at)
    assert provided_at == "2026-10-16"


def test_mcp_source_scope_tool_result_is_json_serializable():
    _reset()
    tools.set_uow_factory(lambda: FakeUoW(FakeRepo(([_source_poi()], dict(SCAN_REPORT)))))
    try:
        content, _structured = asyncio.run(
            mcp.call_tool("explore_pois", {"source_scope": _selection_payload()})
        )
    finally:
        _reset()

    payload = json.loads(content[0].text)
    assert payload["success"] is True
    assert payload["count"] == 1
    result = payload["results"][0]
    assert result["source_metadata"]["provided_at"] == "2026-10-16"
    assert result["source_context"]["source_area_id"] == _selection_payload()[
        "source_area_id"
    ]
    _assert_no_date_objects(payload)


def test_unserializable_source_payload_uses_dedicated_code():
    """Negative test: a poison object must not masquerade as exploration failure."""
    _reset()
    poison = object()
    tools.set_uow_factory(
        lambda: FakeUoW(FakeRepo(([UnserializableItem(poison)], dict(SCAN_REPORT))))
    )
    try:
        content, _structured = asyncio.run(
            mcp.call_tool("explore_pois", {"source_scope": _selection_payload()})
        )
    finally:
        _reset()

    payload = json.loads(content[0].text)
    assert payload["success"] is False
    assert payload["code"] == "serialization_failed"
    assert payload["code"] != "exploration_failed"
    # The failure must stay sanitized: no object repr, no raw payload values.
    assert "0x" not in payload["detail"]
    assert "object at" not in payload["detail"]
    assert repr(poison) not in payload["detail"]
