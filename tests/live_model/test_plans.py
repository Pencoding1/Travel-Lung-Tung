from __future__ import annotations

import json

import pytest

from live_model import plans
from live_model.runner import DEFAULT_SCENARIOS, load_scenario_inputs
from live_model.schema import OutputError, parse_hybrid, parse_llm_only

from domains.planning import parse_scenario, validate

SCENARIOS = load_scenario_inputs(DEFAULT_SCENARIOS)


def _scenario(scenario_id):
    return parse_scenario(SCENARIOS[scenario_id])


def _llm(stops, status="plan", reason=None, day="d1"):
    return parse_llm_only(json.dumps({
        "status": status, "no_plan_reason": reason,
        "days": [] if status == "no_plan" else [
            {"day_id": day, "stops": [
                {"poi_id": pid, "arrival": a, "departure": d} for pid, a, d in stops]}],
    }))


def test_llm_only_feasible():
    plan = plans.build_llm_only_plan(_scenario("S01"), _llm([
        ("p_food", "2026-11-01T09:00:00+07:00", "2026-11-01T10:00:00+07:00")]))
    assert plan.status == "feasible"
    assert plan.sequence == ("p_food",)


def test_llm_only_fabricated_poi_flagged_by_validator():
    scenario = _scenario("S01")
    plan = plans.build_llm_only_plan(scenario, _llm([
        ("p_ghost", "2026-11-01T09:00:00+07:00", "2026-11-01T10:00:00+07:00")]))
    report = validate(scenario, plan)
    assert report.status == "partial"
    assert any(v.code == "unknown_poi" for v in report.known_violations)


def test_llm_only_known_temporal_violation():
    scenario = _scenario("S01")
    plan = plans.build_llm_only_plan(scenario, _llm([
        ("p_food", "2026-11-01T14:30:00+07:00", "2026-11-01T15:30:00+07:00")]))
    report = validate(scenario, plan)
    assert report.status == "partial"
    assert any(v.code == "opening_violation" for v in report.known_violations)


def test_llm_only_no_plan():
    plan = plans.build_llm_only_plan(_scenario("S12"), _llm([], status="no_plan", reason="empty"))
    assert plan.status == "no_plan"
    assert plan.no_plan_reason == "no_candidates"


def test_llm_only_naive_instant_rejected():
    with pytest.raises(OutputError):
        plans.build_llm_only_plan(_scenario("S01"), _llm([
            ("p_food", "2026-11-01T09:00:00", "2026-11-01T10:00:00+07:00")]))
