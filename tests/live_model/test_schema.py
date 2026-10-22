from __future__ import annotations

import json

import pytest

from live_model.schema import OutputError, parse_hybrid, parse_llm_only


PLAN = json.dumps({
    "status": "plan", "no_plan_reason": None,
    "days": [{"day_id": "d1", "stops": [
        {"poi_id": "p_food", "arrival": "2026-11-01T09:00:00+07:00",
         "departure": "2026-11-01T10:00:00+07:00"}]}],
})


def test_parse_valid_plan():
    parsed = parse_llm_only(PLAN)
    assert parsed.status == "plan"
    assert parsed.days[0].stops[0].poi_id == "p_food"


def test_parse_no_plan():
    parsed = parse_llm_only(json.dumps({"status": "no_plan", "no_plan_reason": "x", "days": []}))
    assert parsed.status == "no_plan" and parsed.no_plan_reason == "x"


@pytest.mark.parametrize("text", [
    "```json\n" + PLAN + "\n```",
    "Here is the plan:\n" + PLAN,
    PLAN[:-3],
    "",
])
def test_malformed_outputs_rejected(text):
    with pytest.raises(OutputError):
        parse_llm_only(text)


def test_no_plan_requires_reason_and_no_stops():
    with pytest.raises(OutputError):
        parse_llm_only(json.dumps({"status": "no_plan", "days": []}))
    with pytest.raises(OutputError):
        parse_llm_only(json.dumps({
            "status": "no_plan", "no_plan_reason": "x",
            "days": [{"day_id": "d1", "stops": [
                {"poi_id": "p", "arrival": "a", "departure": "b"}]}]}))


def test_hybrid_parse_and_duplicates():
    parsed = parse_hybrid(json.dumps({"ordered_poi_ids": ["p_food", "p_cafe"],
                                      "day_assignment": {"p_food": "d1"}}))
    assert parsed.ordered_poi_ids == ("p_food", "p_cafe")
    assert parsed.day_assignment == {"p_food": "d1"}
    with pytest.raises(OutputError):
        parse_hybrid(json.dumps({"ordered_poi_ids": ["p_food", "p_food"]}))
    with pytest.raises(OutputError):
        parse_hybrid(json.dumps({"ordered_poi_ids": ["p_food"],
                                 "day_assignment": {"p_ghost": "d1"}}))
