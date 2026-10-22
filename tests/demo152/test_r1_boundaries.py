"""DEMO-152 R1 focused regressions (synthetic, no engine/model/network).

Covers only the three reviewed corrections:

1. Nested Pydantic serialisation omits the unused source selector through both
   public request models and a tiny POI-side wrapper, in Python and JSON, and
   the emitted payload revalidates.
2. The chat/model-facing ``get_itinerary_route`` payload no longer carries the
   provider polyline, in legacy and source modes, while every other route
   field and the typed planner record keep it.
3. The plan-busy chat notice describes a sent message and a sequential
   same-session lease, not parallel model processing.
"""

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.core.domain.source_scope import SourceSnapshotSelection
from domains import planning_adapter, source_gate
from domains.payloads import ChatRequest, ItineraryRequest, SourceScopeSelection

UI_PATH = Path(__file__).resolve().parents[2] / "ai_service" / "static" / "travel.html"

NS = "qa_demo152"
HASH = "a" * 64
AREA_A = "source_area_v1:" + "b" * 64
AREA_B = "source_area_v1:" + "c" * 64

GEOMETRY = {
    "type": "LineString",
    "coordinates": [[106.70, 10.70], [106.71, 10.71]],
}
STOPS = [
    {"id": "p1", "latitude": 10.70, "longitude": 106.70},
    {"id": "p2", "latitude": 10.71, "longitude": 106.71},
]


def single(area=AREA_A):
    return {"dataset_namespace": NS, "input_sha256": HASH,
            "source_area_id": area}


def multi(ids=None):
    return {"dataset_namespace": NS, "input_sha256": HASH,
            "source_area_ids": list(ids if ids is not None else [AREA_B, AREA_A])}


class POISelectionWrapper(BaseModel):
    """Minimal POI-side nested model, mirroring a request wrapper."""

    scope: SourceSnapshotSelection


def _chat(scope):
    return ChatRequest(session_id="qa-r1", message="fixture", source_scope=scope)


def _itinerary(scope):
    return ItineraryRequest(
        session_id="qa-r1",
        travel_type="self-explore",
        num_travelers=1,
        start_date="2026-10-20",
        duration_days=1,
        budget_range="chưa nêu",
        user_description="fixture",
        source_scope=scope,
    )


@pytest.mark.parametrize("builder", [_chat, _itinerary])
def test_nested_single_selector_roundtrips_python_and_json(builder):
    request = builder(single())
    nested = request.model_dump()["source_scope"]
    nested_json = json.loads(request.model_dump_json())["source_scope"]

    assert nested == single()
    assert nested_json == single()
    assert "source_area_ids" not in nested
    assert "source_area_ids" not in nested_json

    revalidated = type(request).model_validate(request.model_dump())
    assert revalidated.source_scope.area_ids == (AREA_A,)


@pytest.mark.parametrize("builder", [_chat, _itinerary])
def test_nested_multi_selector_roundtrips_python_and_json(builder):
    expected = multi([AREA_A, AREA_B])
    request = builder(multi([AREA_B, AREA_A]))
    nested = request.model_dump()["source_scope"]
    nested_json = json.loads(request.model_dump_json())["source_scope"]

    assert nested == expected
    assert nested_json == expected
    assert "source_area_id" not in nested
    assert "source_area_id" not in nested_json

    revalidated = type(request).model_validate(request.model_dump())
    assert revalidated.source_scope.area_ids == (AREA_A, AREA_B)


def test_poi_selection_nested_in_wrapper_omits_unused_selector():
    for body, forbidden in ((single(), "source_area_ids"),
                            (multi([AREA_A, AREA_B]), "source_area_id")):
        wrapped = POISelectionWrapper(scope=body)
        dumped = wrapped.model_dump()["scope"]
        dumped_json = json.loads(wrapped.model_dump_json())["scope"]
        assert dumped == body
        assert dumped_json == body
        assert forbidden not in dumped
        assert forbidden not in dumped_json
        assert POISelectionWrapper.model_validate(wrapped.model_dump()).scope \
            == wrapped.scope


def test_direct_serialisation_and_strict_rejections_stay_unchanged():
    for model in (SourceScopeSelection, SourceSnapshotSelection):
        direct = model.model_validate(single())
        assert direct.model_dump() == single()
        assert json.loads(direct.model_dump_json()) == single()
        # include/exclude semantics remain the caller's.
        assert set(direct.model_dump(include={"dataset_namespace",
                                              "source_area_id"})) == {
            "dataset_namespace", "source_area_id"}
        assert "input_sha256" not in direct.model_dump(
            exclude={"input_sha256"})

        assert model.model_validate(multi([AREA_B, AREA_A])).model_dump() == \
            multi([AREA_A, AREA_B])

        bad = [
            {**single(), "source_area_ids": [AREA_B]},  # both selectors
            {"dataset_namespace": NS, "input_sha256": HASH},  # none
            {**single(), "source_area_id": None},  # explicit null
            multi([AREA_A, AREA_A]),  # duplicates
            multi(["*"]),  # global sentinel
            {**single(), "source_area_id": "quan_1"},  # admin id
        ]
        for value in bad:
            with pytest.raises(ValueError):
                model.model_validate(value)


class _TextContent:
    def __init__(self, text):
        self.text = text


class _ToolResult:
    def __init__(self, payload):
        text = payload if isinstance(payload, str) else json.dumps(payload)
        self.content = [_TextContent(text)]
        self.isError = False


def _route_payload():
    return {
        "success": True,
        "distance_km": 1.2,
        "time_minutes": 4.0,
        "turn_by_turn": ["Đi thẳng", "Rẽ phải"],
        "route_geometry": dict(GEOMETRY),
        "route_geometry_status": "available",
        "route_provenance": "graphhopper",
        "route_profile": "car",
        "stops_mapped": 2,
        "stops": [dict(stop) for stop in STOPS],
    }


def _assert_model_route_payload(payload):
    assert payload["success"] is True
    assert "route_geometry" not in payload
    assert payload["distance_km"] == 1.2
    assert payload["time_minutes"] == 4.0
    assert payload["turn_by_turn"] == ["Đi thẳng", "Rẽ phải"]
    assert payload["stops_mapped"] == 2
    assert payload["stops"] == STOPS
    assert payload["route_geometry_status"] == "available"
    assert payload["route_provenance"] == "graphhopper"
    assert payload["route_profile"] == "car"


def test_legacy_model_route_payload_omits_geometry_and_keeps_metadata():
    gate = source_gate.ScopeGate(transport_mode="car")
    raw = _ToolResult(_route_payload())
    filtered = gate.filter_result(
        "get_itinerary_route",
        {"ordered_poi_ids": ["p1", "p2"], "vehicle": "car"},
        raw,
    )

    assert filtered is not raw
    _assert_model_route_payload(json.loads(filtered.content[0].text))
    # Legacy turns still accumulate no source route evidence.
    assert gate.route_evidence is None
    assert gate.route_calls == []


def test_source_model_route_payload_omits_geometry_but_evidence_remains():
    gate = source_gate.ScopeGate(source_selection=single(), transport_mode="car")
    gate.verified_ids.update({"p1", "p2"})
    raw = _ToolResult(_route_payload())
    decision = gate.prepare("get_itinerary_route",
                            {"ordered_poi_ids": ["p1", "p2"], "vehicle": "car"})
    assert decision.ok
    filtered = gate.filter_result("get_itinerary_route", decision.args, raw)

    _assert_model_route_payload(json.loads(filtered.content[0].text))
    assert gate.route_calls[-1]["success"] is True
    evidence = gate.route_evidence
    assert evidence is not None
    assert evidence["ordered_poi_ids"] == ["p1", "p2"]
    assert evidence["stops_mapped"] == 2
    assert evidence["distance_km"] == 1.2
    assert evidence["time_minutes"] == 4.0
    assert [(stop["id"], stop["latitude"], stop["longitude"])
            for stop in evidence["stops"]] == [
        ("p1", 10.70, 106.70), ("p2", 10.71, 106.71)]
    assert evidence["source_scope"] == single()


@pytest.mark.parametrize("raw_text", [
    '{"success": false, "code": "no_route", "message": "none"}',
    "not-json",
])
@pytest.mark.parametrize("source_selection", [None, single()])
def test_genuine_route_errors_are_returned_raw(raw_text, source_selection):
    gate = source_gate.ScopeGate(source_selection=source_selection,
                                 transport_mode="car")
    raw = _ToolResult(raw_text)
    filtered = gate.filter_result(
        "get_itinerary_route",
        {"ordered_poi_ids": ["p1", "p2"], "vehicle": "car"},
        raw,
    )
    assert filtered is raw
    assert gate.route_evidence is None


def test_typed_route_record_still_retains_private_geometry():
    by_id = {stop["id"]: stop for stop in STOPS}

    async def call_tool(_name, args):
        first, second = args["ordered_poi_ids"]
        payload = _route_payload()
        payload["stops"] = [dict(by_id[first]), dict(by_id[second])]
        return _ToolResult(payload)

    _edges, evidence = asyncio.run(
        planning_adapter.collect_route_edges(call_tool, ["p1", "p2"]))
    records = [record for record in evidence.records
               if record.status == "success"]
    assert len(records) == 2
    for record in records:
        assert record.geometry == GEOMETRY
        assert record.instructions == ["Đi thẳng", "Rẽ phải"]


def test_ui_plan_busy_notice_describes_sequential_lease_only():
    source = UI_PATH.read_text(encoding="utf-8")
    assert "Tin đã gửi; có thể chờ tác vụ tạo lịch hoàn tất." in source
    assert "Hội thoại và tạo lịch trong cùng phiên được xử lý lần lượt." in source
    assert "state.planBusy" in source
    assert "xử lý song song" not in source
