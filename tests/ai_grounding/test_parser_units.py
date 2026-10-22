"""Unit tests for the pure grounding parsers (no I/O)."""

from domains import grounding

from helpers_ai_grounding import ToolResult, ok_json


def test_none_result_is_protocol_error():
    outcome = grounding.parse_mcp_tool_result(None)
    assert not outcome.ok
    assert outcome.code == grounding.TOOL_PROTOCOL_ERROR


def test_empty_content_is_protocol_error():
    outcome = grounding.parse_mcp_tool_result(ToolResult(content=[]))
    assert not outcome.ok
    assert outcome.code == grounding.TOOL_PROTOCOL_ERROR


def test_non_text_content_is_protocol_error():
    outcome = grounding.parse_mcp_tool_result(ToolResult(content=["plain-string"]))
    assert not outcome.ok
    assert outcome.code == grounding.TOOL_PROTOCOL_ERROR


def test_iserror_is_protocol_error():
    outcome = grounding.parse_mcp_tool_result(ToolResult('{"success": true}', is_error=True))
    assert not outcome.ok
    assert outcome.code == grounding.TOOL_PROTOCOL_ERROR


def test_malformed_json_is_protocol_error():
    outcome = grounding.parse_mcp_tool_result(ToolResult("{not json"))
    assert not outcome.ok
    assert outcome.code == grounding.TOOL_PROTOCOL_ERROR


def test_non_dict_json_is_protocol_error():
    outcome = grounding.parse_mcp_tool_result(ToolResult("[1, 2, 3]"))
    assert not outcome.ok
    assert outcome.code == grounding.TOOL_PROTOCOL_ERROR


def test_success_false_is_failure():
    outcome = grounding.parse_mcp_tool_result(ok_json({"success": False, "detail": "nope"}))
    assert not outcome.ok
    assert outcome.code == "success_false"


def test_valid_payload_is_ok():
    outcome = grounding.parse_mcp_tool_result(ok_json({"success": True, "matches": []}))
    assert outcome.ok
    assert outcome.data["matches"] == []


def test_normalize_area_token_district_one_vs_ten():
    assert grounding.normalize_area_token("District 1") == "quan 1"
    assert grounding.normalize_area_token("Quan 1") == "quan 1"
    assert grounding.normalize_area_token("Quận 1") == "quan 1"
    assert grounding.normalize_area_token("District 10") == "quan 10"
    assert grounding.normalize_area_token("District 1") != grounding.normalize_area_token("District 10")


def test_select_unique_area_partial_match_is_not_resolved():
    matches = [{"type": "District", "id": "quan_10", "name": "District 10"}]
    outcome = grounding.select_unique_area(matches, "District 1", "District")
    assert not outcome.ok
    assert outcome.code == grounding.LOCATION_NOT_RESOLVED


def test_select_unique_area_ambiguous():
    matches = [
        {"type": "District", "id": "a", "name": "District 1"},
        {"type": "District", "id": "b", "name": "Quan 1"},
    ]
    outcome = grounding.select_unique_area(matches, "District 1", "District")
    assert not outcome.ok
    assert outcome.code == grounding.LOCATION_AMBIGUOUS


def test_select_unique_area_type_mismatch():
    matches = [{"type": "Street", "id": "s1", "name": "District 1"}]
    outcome = grounding.select_unique_area(matches, "District 1", "District")
    assert not outcome.ok
    assert outcome.code == grounding.LOCATION_TYPE_MISMATCH


def test_collect_candidate_ids_is_deterministic_and_capped():
    groups = [
        [{"id": "a"}, {"id": "b"}],
        [{"id": "b"}, {"id": "c"}],
    ]
    ids = grounding.collect_candidate_ids(groups, cap=3)
    assert ids == ["a", "b", "c"]  # sorted, de-duplicated
    dense = [[{"id": str(i)} for i in range(50)]]
    expected = sorted(str(i) for i in range(50))[:18]
    assert grounding.collect_candidate_ids(dense, cap=18) == expected
    # invalid ids are ignored, not stringified
    assert grounding.collect_candidate_ids([[{"id": None}, {"id": "z"}]]) == ["z"]


DISTRICT = {"id": "quan_1", "name": "District 1"}
CITY = {"id": "hcmc", "name": "Ho Chi Minh City"}


def _admin(**overrides):
    base = {"city_id": "hcmc", "district_id": "quan_1",
            "city_name": "Ho Chi Minh City", "district_name": "District 1"}
    base.update(overrides)
    return {"administrative_context": base}


def test_poi_scope_status_uses_structured_context_only():
    assert grounding.poi_scope_status(_admin(), DISTRICT, CITY) == "verified"
    # Free-text address is never consulted.
    assert grounding.poi_scope_status(
        {"POI_Address": "1 Le Loi, Quan 1, Ho Chi Minh City"}, DISTRICT, CITY) == "unknown"
    # Different district id/name -> conflict (address irrelevant).
    assert grounding.poi_scope_status(
        _admin(district_id="quan_5", district_name="District 5"), DISTRICT, CITY) == "conflict"
    # District name "Quan 10" must not verify against District 1.
    assert grounding.poi_scope_status(
        _admin(district_id="quan_1", district_name="Quan 10"), DISTRICT, CITY) == "conflict"
    # Conflicting parent city -> conflict.
    assert grounding.poi_scope_status(
        _admin(city_id="hanoi"), DISTRICT, CITY) == "conflict"
    # Invalid/missing context -> unknown.
    assert grounding.poi_scope_status({}, DISTRICT, CITY) == "unknown"
    assert grounding.poi_scope_status(
        {"administrative_context": {"city_id": "hcmc", "district_id": None,
                                    "city_name": "Ho Chi Minh City",
                                    "district_name": "District 1"}}, DISTRICT, CITY) == "unknown"


def test_validate_request_codes():
    class Req:
        session_id = "s"
        current_city = "Ho Chi Minh City"
        target_district = "District 1"
        travel_type = "relax"
        budget_range = "1000"
        start_date = "2026-01-01"
        duration_days = 3
        num_travelers = 2

    assert grounding.validate_request(Req()) == []

    bad = Req()
    bad.duration_days = 0
    bad.num_travelers = -1
    bad.start_date = "not-a-date"
    bad.current_city = " "
    errors = grounding.validate_request(bad)
    fields = {e["field"] for e in errors}
    assert {"duration_days", "num_travelers", "start_date", "current_city"} <= fields
