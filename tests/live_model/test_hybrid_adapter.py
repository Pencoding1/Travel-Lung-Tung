"""Adapter / production-scheduler integration tests (fake inputs, no model call)."""

from __future__ import annotations

import json
from dataclasses import replace

from live_model import hybrid_adapter, plans
from live_model.runner import DEFAULT_SCENARIOS, load_scenario_inputs
from live_model.schema import parse_hybrid

from domains.planning import parse_scenario, schedule, validate

SCENARIOS = load_scenario_inputs(DEFAULT_SCENARIOS)


def _order(*poi_ids, day_assignment=None):
    payload = {"ordered_poi_ids": list(poi_ids)}
    if day_assignment is not None:
        payload["day_assignment"] = day_assignment
    return parse_hybrid(json.dumps(payload))


def test_no_collector_local_scheduler_remains():
    assert not hasattr(plans, "schedule_from_order")
    assert not hasattr(plans, "build_hybrid_plan")


def test_adapter_replaces_only_preferences():
    raw = SCENARIOS["S01"]
    base = parse_scenario(raw)
    adapted, mapping = hybrid_adapter.adapt(raw, _order("p_cafe", "p_food"))
    for attr in ("required_categories", "days", "pois", "route_index", "budget",
                 "party_size", "start_depot_id", "end_depot_id", "minimum_stops",
                 "max_iterations", "currency"):
        assert getattr(adapted, attr) == getattr(base, attr)
    assert mapping["algorithm"] == "domains.planning.schedule"
    assert mapping["day_assignment_honored"] is False


def test_adapter_matches_direct_production_scheduler():
    for scenario_id in ("S01", "S03", "S05", "S07"):
        raw = SCENARIOS[scenario_id]
        base = parse_scenario(raw)
        candidates = [p.poi_id for p in base.pois
                      if p.poi_id not in (base.start_depot_id, base.end_depot_id)]
        order = _order(*reversed(candidates))

        adapted, plan, mapping = hybrid_adapter.schedule_hybrid(raw, order)

        model_weights, _ = hybrid_adapter.model_category_weights(base, order)
        expected_weights = dict(base.preferences)
        for category_id, weight in model_weights.items():
            expected_weights[category_id] = expected_weights.get(category_id, 0) + weight
        expected = replace(base, preferences=expected_weights)

        assert adapted == expected
        # The adapter output is the production scheduler applied to the equivalent
        # weight-mapped scenario -- not a reimplementation.
        assert plan == schedule(expected)
        assert plan == schedule(adapted)


def test_model_contribution_changes_ranking():
    raw = {
        "scenario_id": "T_order", "seed": 0, "currency": "VND", "party_size": 1,
        "days": [{"day_id": "d1", "date": "2026-11-01",
                  "window": {"start": "2026-11-01T08:00:00+07:00",
                             "end": "2026-11-01T20:00:00+07:00"}}],
        "pois": [
            {"poi_id": "p_a", "category_ids": ["cat_a"], "visit_minutes": 30},
            {"poi_id": "p_b", "category_ids": ["cat_b"], "visit_minutes": 30},
        ],
        "route_edges": [
            {"from_poi_id": "p_a", "to_poi_id": "p_b", "duration_minutes": 10,
             "distance_km": "1.0", "transport_mode": "car", "provenance": "synthetic"},
            {"from_poi_id": "p_b", "to_poi_id": "p_a", "duration_minutes": 10,
             "distance_km": "1.0", "transport_mode": "car", "provenance": "synthetic"},
        ],
    }
    _, plan_ab, _ = hybrid_adapter.schedule_hybrid(raw, _order("p_a", "p_b"))
    _, plan_ba, _ = hybrid_adapter.schedule_hybrid(raw, _order("p_b", "p_a"))
    assert plan_ab.sequence == ("p_a", "p_b")
    assert plan_ba.sequence == ("p_b", "p_a")


def test_required_category_not_dropped_when_model_omits_it():
    raw = {
        "scenario_id": "T_required", "seed": 0, "currency": "VND", "party_size": 1,
        "required_categories": ["cat_b"],
        "days": [{"day_id": "d1", "date": "2026-11-01",
                  "window": {"start": "2026-11-01T08:00:00+07:00",
                             "end": "2026-11-01T20:00:00+07:00"}}],
        "pois": [
            {"poi_id": "p_a", "category_ids": ["cat_a"], "visit_minutes": 30},
            {"poi_id": "p_b", "category_ids": ["cat_b"], "visit_minutes": 30},
        ],
        "route_edges": [
            {"from_poi_id": "p_a", "to_poi_id": "p_b", "duration_minutes": 10,
             "distance_km": "1.0", "transport_mode": "car", "provenance": "synthetic"},
            {"from_poi_id": "p_b", "to_poi_id": "p_a", "duration_minutes": 10,
             "distance_km": "1.0", "transport_mode": "car", "provenance": "synthetic"},
        ],
    }
    adapted, plan, _ = hybrid_adapter.schedule_hybrid(raw, _order("p_a"))
    assert "p_b" in plan.sequence  # hard requirement dominates the model preference
    report = validate(adapted, plan)
    assert not report.unsatisfied_required


def test_missing_route_and_cumulative_budget_match_direct():
    raw = {
        "scenario_id": "T_budget", "seed": 0, "currency": "VND", "party_size": 1,
        "budget": {"amount": "1000", "currency": "VND", "unit": "per_party"},
        "days": [{"day_id": "d1", "date": "2026-11-01",
                  "window": {"start": "2026-11-01T08:00:00+07:00",
                             "end": "2026-11-01T20:00:00+07:00"},
                  "meal_windows": [{"category_id": "cat_a",
                                    "start": "2026-11-01T12:00:00+07:00",
                                    "end": "2026-11-01T13:00:00+07:00"}]}],
        "pois": [
            {"poi_id": "p_a", "category_ids": ["cat_a"], "visit_minutes": 30,
             "cost": {"amount": "600", "currency": "VND", "unit": "per_person"}},
            {"poi_id": "p_b", "category_ids": ["cat_b"], "visit_minutes": 30,
             "cost": {"amount": "600", "currency": "VND", "unit": "per_person"}},
            {"poi_id": "p_orphan", "category_ids": ["cat_c"], "visit_minutes": 30,
             "cost": {"amount": "1", "currency": "VND", "unit": "per_person"}},
        ],
        "route_edges": [
            {"from_poi_id": "p_a", "to_poi_id": "p_b", "duration_minutes": 10,
             "distance_km": "1.0", "transport_mode": "car", "provenance": "synthetic"},
            {"from_poi_id": "p_b", "to_poi_id": "p_a", "duration_minutes": 10,
             "distance_km": "1.0", "transport_mode": "car", "provenance": "synthetic"},
        ],
    }
    adapted, plan, mapping = hybrid_adapter.schedule_hybrid(
        raw, _order("p_a", "p_b", "p_orphan"))
    assert plan == schedule(adapted)
    total = plan.total_cost_party
    assert total is None or total <= 1000
    # p_orphan has no directed edge and must not be silently placed.
    assert "p_orphan" not in plan.sequence
    assert mapping["effective_category_weights"]["cat_a"] >= 1


def test_day_assignment_recorded_but_not_honored():
    raw = SCENARIOS["S01"]
    _, _, mapping = hybrid_adapter.schedule_hybrid(
        raw, _order("p_food", day_assignment={"p_food": "d1"}))
    assert mapping["model_day_assignment"] == {"p_food": "d1"}
    assert mapping["day_assignment_honored"] is False
    assert "plan_notes" in mapping
    assert "ranking_semantics" in mapping


def test_unknown_poi_recorded_not_fabricated():
    raw = SCENARIOS["S01"]
    _, plan, mapping = hybrid_adapter.schedule_hybrid(
        raw, _order("p_ghost", "p_food"))
    assert "p_ghost" in mapping["unknown_pois"]
    assert plan.scenario_id == raw["scenario_id"]
    assert "p_ghost" not in plan.sequence
