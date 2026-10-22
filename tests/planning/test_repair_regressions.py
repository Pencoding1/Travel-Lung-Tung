"""Regression tests for the OC-010 bounded corrective QA.

Covers the independently confirmed validator defects and the source-review gaps:
zero ``max_stops``, omitted meal day, duplicate/out-of-order days, empty plan and
false refusal, missing-route overlap, known-cost-overbudget with an unknown cost,
two-day impossible transfer, empty final day with required return, wrong
scenario id, and validator independence from the scheduler.
"""

import inspect
import re
from dataclasses import replace

from domains.planning import parse_scenario, schedule, validate
from domains.planning import validator as validator_module
from domains.planning.contracts import Plan, PlannedDay, PlannedStop
from helpers_planning import D1, D2, cost, edge, iso, make_day, make_scenario, poi, window

DAY1 = window("d1", iso(D1, "08:00"), iso(D1, "18:00"))
DAY2 = window("d2", iso(D2, "08:00"), iso(D2, "18:00"))


def _codes(violations):
    return {v.code for v in violations}


# --- 1. structure --------------------------------------------------------
def test_zero_max_stops_cannot_be_feasible():
    scenario = parse_scenario(make_scenario(
        [poi("p1", ["cat_a"], 30, cost(0), [DAY1])], [make_day(max_stops=0)]))
    plan = schedule(scenario)
    report = validate(scenario, plan)
    assert plan.status == "no_plan"
    assert report.status == "no_plan"
    assert report.stop_count == 0


def test_validator_enforces_max_stops_on_plan():
    pois = [poi("p1", ["cat_a"], 30, cost(0), [DAY1]),
            poi("p2", ["cat_a"], 30, cost(0), [DAY1])]
    edges = [edge("p1", "p2", 5)]
    loose = parse_scenario(make_scenario(pois, [make_day()], edges))
    plan = schedule(loose)
    assert len(plan.days[0].stops) == 2
    strict = parse_scenario(make_scenario(pois, [make_day(max_stops=0)], edges))
    report = validate(strict, plan)
    assert "max_stops_exceeded" in _codes(report.known_violations)
    assert report.status == "partial"


def test_duplicate_day_id_in_plan_is_flagged():
    scenario = parse_scenario(make_scenario(
        [poi("p1", ["cat_a"], 30, cost(0), [DAY1])], [make_day()]))
    plan = schedule(scenario)
    forged = replace(plan, days=(plan.days[0], plan.days[0]))
    report = validate(scenario, forged)
    assert "duplicate_day" in _codes(report.known_violations)


def test_out_of_order_days_are_flagged():
    pois = [poi("p1", ["cat_a"], 30, cost(0), [DAY1, DAY2]),
            poi("p2", ["cat_b"], 30, cost(0), [DAY1, DAY2])]
    edges = [edge("p1", "p2", 5), edge("p2", "p1", 5)]
    scenario = parse_scenario(make_scenario(
        pois, [make_day("d1", D1), make_day("d2", D2)], edges))
    plan = schedule(scenario)
    forged = replace(plan, days=tuple(reversed(plan.days)))
    report = validate(scenario, forged)
    assert "day_order" in _codes(report.known_violations)


def test_wrong_scenario_id_is_flagged():
    scenario = parse_scenario(make_scenario(
        [poi("p1", ["cat_a"], 30, cost(0), [DAY1])], [make_day()]))
    plan = schedule(scenario)
    forged = replace(plan, scenario_id="OTHER")
    report = validate(scenario, forged)
    assert "scenario_id_mismatch" in _codes(report.known_violations)


def test_empty_plan_is_not_feasible():
    empty = Plan(
        scenario_id="T", status="feasible", no_plan_reason=None,
        days=tuple(), sequence=tuple(), total_cost_party=None,
        total_cost_currency=None, total_travel_minutes=0,
        total_distance_km=None, excluded=tuple(), unsatisfied_required=tuple(),
        unknown_reasons=tuple(), iterations=0, notes=tuple())
    scenario = parse_scenario(make_scenario(
        [poi("p1", ["cat_a"], 30, cost(0), [DAY1])], [make_day()]))
    report = validate(scenario, empty)
    assert report.status == "no_plan"
    assert report.no_plan_reason == "missing_delivery"
    assert report.stop_count == 0


def test_false_refusal_with_stops_is_checked_not_bypassed():
    scenario = parse_scenario(make_scenario(
        [poi("p1", ["cat_a"], 30, cost(0), [DAY1])], [make_day()]))
    plan = schedule(scenario)
    forged = replace(plan, status="no_plan", no_plan_reason="no_verified_plan")
    report = validate(scenario, forged)
    assert "no_plan_with_stops" in _codes(report.known_violations)
    assert report.stop_count == 1
    assert report.status != "no_plan"


def test_omitted_meal_day_is_unsatisfied():
    meal = {"category_id": "cat_food", "start": iso(D2, "11:00"), "end": iso(D2, "13:00")}
    scenario = parse_scenario(make_scenario(
        [poi("p1", ["cat_a"], 30, cost(0), [DAY1])],
        [make_day("d1", D1), make_day("d2", D2, meal_windows=[meal])]))
    plan = schedule(scenario)
    report = validate(scenario, plan)
    assert any(req == "meal_window:d2:cat_food" for req in report.unsatisfied_required)
    assert report.status == "partial"


# --- 2. missing route does not disable the overlap check -----------------
def test_missing_route_overlap_reports_both_violation_and_unknown():
    pois = [poi("p1", ["cat_a"], 30, cost(0), [DAY1]),
            poi("p2", ["cat_a"], 30, cost(0), [DAY1])]
    scenario = parse_scenario(make_scenario(pois, [make_day()], [edge("p2", "p1", 10)]))
    plan = schedule(scenario)
    assert plan.sequence == ("p1",)
    p1 = plan.days[0].stops[0]
    forged_p2 = PlannedStop(
        poi_id="p2", arrival=p1.arrival, departure=p1.arrival + 30,
        visit_minutes=30, travel_from_prev_minutes=None,
        travel_from_prev_distance_km=None, cost_party=None, cost_currency=None)
    forged = replace(plan, days=(replace(plan.days[0], stops=(p1, forged_p2)),))
    report = validate(scenario, forged)
    assert "travel_infeasible" in _codes(report.known_violations)
    assert any(reason == "route_unknown:p1->p2" for reason in report.unknown_reasons)


def test_known_cost_overbudget_even_with_unknown_cost():
    raw = make_scenario(
        [poi("p_known", ["cat_a"], 30, cost(1000), [DAY1]),
         poi("p_unknown", ["cat_a"], 30, None, [DAY1])],
        [make_day()],
        [edge("p_known", "p_unknown", 5), edge("p_unknown", "p_known", 5)])
    plan = schedule(parse_scenario(raw))
    budgeted = parse_scenario({**raw, "budget": cost(10, "per_party")})
    report = validate(budgeted, plan)
    assert "budget_exceeded" in _codes(report.known_violations)
    assert any(reason.startswith("cost_unknown:") for reason in report.unknown_reasons)
    assert report.recomputed_total_cost_party is None


# --- 3. multi-day transfer semantics -------------------------------------
def test_two_day_impossible_transfer_is_unknown_not_zero():
    pois = [poi("p1", ["cat_a"], 30, cost(0), [DAY1, DAY2]),
            poi("p2", ["cat_b"], 30, cost(0), [DAY1, DAY2])]
    edges = [edge("p2", "p1", 5)]  # p1->p2 missing (interday transfer impossible)
    scenario = parse_scenario(make_scenario(
        pois, [make_day("d1", D1), make_day("d2", D2)], edges))
    plan = schedule(scenario)
    assert plan.sequence == ("p1",)
    day2_start = scenario.days[1].start
    forged_p2 = PlannedStop("p2", day2_start, day2_start + 30, 30,
                            None, None, None, None)
    days = (plan.days[0], replace(plan.days[1], stops=(forged_p2,)))
    report = validate(scenario, replace(plan, days=days, sequence=("p1", "p2")))
    assert any(reason == "route_unknown:p1->p2" for reason in report.unknown_reasons)
    assert report.status == "unverifiable"


def test_interday_carry_includes_transfer_in_totals():
    pois = [poi("p1", ["cat_a"], 30, cost(0), [DAY1, DAY2]),
            poi("p2", ["cat_b"], 30, cost(0), [DAY1, DAY2])]
    edges = [edge("p1", "p2", 25), edge("p2", "p1", 25)]
    scenario = parse_scenario(make_scenario(
        pois, [make_day("d1", D1), make_day("d2", D2)], edges))
    plan = schedule(scenario)
    report = validate(scenario, plan)
    assert report.status == "feasible"
    assert plan.sequence == ("p1", "p2")
    # p1 -> p2 is the interday transfer and must be counted once.
    assert report.recomputed_total_travel_minutes == 25
    assert report.recomputed_total_distance_km is not None


def test_empty_final_day_with_required_return_is_dropped_if_infeasible():
    short_day = make_day("d2", D2, start=iso(D2, "08:00"), end=iso(D2, "08:01"))
    pois = [poi("depot", ["cat_depot"], 1, cost(0)),
            poi("p1", ["cat_a"], 60, cost(0), [window("d1", iso(D1, "08:00"), iso(D1, "10:00"))])]
    edges = [edge("depot", "p1", 5), edge("p1", "depot", 90)]
    scenario = parse_scenario(make_scenario(
        pois, [make_day("d1", D1, start=iso(D1, "08:00"), end=iso(D1, "10:00")), short_day],
        edges, start_depot_poi_id="depot", end_depot_poi_id="depot"))
    plan = schedule(scenario)
    report = validate(scenario, plan)
    assert plan.status == "no_plan"
    assert any(note.startswith("return_buffer_repair") for note in plan.notes)
    assert report.status == "no_plan"


def test_empty_final_day_with_feasible_return_keeps_plan():
    short_day = make_day("d2", D2, start=iso(D2, "08:00"), end=iso(D2, "08:01"))
    pois = [poi("depot", ["cat_depot"], 1, cost(0)),
            poi("p1", ["cat_a"], 60, cost(0), [window("d1", iso(D1, "08:00"), iso(D1, "10:00"))])]
    edges = [edge("depot", "p1", 5), edge("p1", "depot", 30)]
    scenario = parse_scenario(make_scenario(
        pois, [make_day("d1", D1, start=iso(D1, "08:00"), end=iso(D1, "10:00")), short_day],
        edges, start_depot_poi_id="depot", end_depot_poi_id="depot"))
    plan = schedule(scenario)
    report = validate(scenario, plan)
    assert plan.sequence == ("p1",)
    assert report.status == "feasible"
    assert report.recomputed_total_travel_minutes == 35  # 5 out + 30 return


# --- validator independence ----------------------------------------------
def test_validator_source_does_not_reference_scheduler():
    source = inspect.getsource(validator_module)
    assert not re.search(r"^\s*(from|import)\s+.*scheduler", source, re.M)
    assert not hasattr(validator_module, "schedule")
