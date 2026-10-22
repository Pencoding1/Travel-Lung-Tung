"""Scheduler behavior tests for :mod:`domains.planning.scheduler`."""

from domains.planning import parse_instant, parse_scenario, schedule, validate
from helpers_planning import D1, D2, cost, edge, iso, make_day, make_scenario, poi, window

DAY_OPEN = window("d1", iso(D1, "08:00"), iso(D1, "18:00"))


def _run(scenario):
    parsed = parse_scenario(scenario)
    plan = schedule(parsed)
    return parsed, plan, validate(parsed, plan)


def test_single_feasible_stop_is_feasible():
    _, plan, report = _run(make_scenario(
        [poi("p1", ["cat_a"], 60, cost(0), [DAY_OPEN])], [make_day()]))
    assert plan.status == "feasible"
    assert plan.sequence == ("p1",)
    assert report.status == "feasible"
    assert plan.days[0].stops[0].arrival == parse_instant(iso(D1, "08:00"), "x")


def test_preference_then_travel_then_id_deterministic_tie():
    # Three equivalent POIs (same category/window) so only id breaks the tie.
    pois = [poi(name, ["cat_a"], 30, cost(0), [DAY_OPEN])
            for name in ("p_b", "p_a", "p_c")]
    edges = [edge(a, b, 5) for a in ("p_a", "p_b", "p_c")
             for b in ("p_a", "p_b", "p_c") if a != b]
    _, plan, _ = _run(make_scenario(pois, [make_day()], edges))
    assert plan.sequence == ("p_a", "p_b", "p_c")


def test_preference_weight_orders_candidates():
    pois = [
        poi("p_low", ["cat_a"], 30, cost(0), [DAY_OPEN]),
        poi("p_high", ["cat_b"], 30, cost(0), [DAY_OPEN]),
    ]
    edges = [edge("p_high", "p_low", 5), edge("p_low", "p_high", 5)]
    _, plan, _ = _run(make_scenario(
        pois, [make_day()], edges,
        preferences={"category_weights": {"cat_a": 1, "cat_b": 9}}))
    assert plan.sequence[0] == "p_high"


def test_waiting_before_opening_is_allowed():
    late = window("d1", iso(D1, "12:00"), iso(D1, "17:00"))
    _, plan, report = _run(make_scenario(
        [poi("p1", ["cat_a"], 60, cost(0), [late])], [make_day()]))
    assert plan.days[0].stops[0].arrival == parse_instant(iso(D1, "12:00"), "x")
    assert report.status == "feasible"


def test_exact_closing_and_day_end_boundary():
    tight = window("d1", iso(D1, "09:00"), iso(D1, "10:00"))
    _, plan, report = _run(make_scenario(
        [poi("p1", ["cat_a"], 60, cost(0), [tight])],
        [make_day(start=iso(D1, "08:00"), end=iso(D1, "10:00"))]))
    assert plan.days[0].stops[0].departure == parse_instant(iso(D1, "10:00"), "x")
    assert report.status == "feasible"


def test_budget_excludes_expensive_candidate():
    pois = [
        poi("p_cheap", ["cat_a"], 30, cost(1000), [DAY_OPEN]),
        poi("p_pricey", ["cat_a"], 30, cost(1000000), [DAY_OPEN]),
    ]
    edges = [edge("p_cheap", "p_pricey", 5), edge("p_pricey", "p_cheap", 5)]
    _, plan, _ = _run(make_scenario(
        pois, [make_day()], edges,
        budget=cost(5000, "per_party")))
    assert plan.sequence == ("p_cheap",)
    assert any(ex.reason == "budget_exceeded" for ex in plan.excluded)


def test_meal_window_is_satisfied():
    meal = {"category_id": "cat_food", "start": iso(D1, "11:00"),
            "end": iso(D1, "13:00")}
    _, plan, report = _run(make_scenario(
        [poi("p_food", ["cat_food"], 60, cost(0), [DAY_OPEN])],
        [make_day(meal_windows=[meal])]))
    assert plan.days[0].stops[0].arrival == parse_instant(iso(D1, "11:00"), "x")
    assert report.status == "feasible"
    assert report.unsatisfied_required == ()


def test_duplicate_poi_not_reused_across_days():
    windows = [window("d1", iso(D1, "08:00"), iso(D1, "18:00")),
               window("d2", iso(D2, "08:00"), iso(D2, "18:00"))]
    _, plan, _ = _run(make_scenario(
        [poi("p1", ["cat_a"], 30, cost(0), windows)],
        [make_day("d1", D1), make_day("d2", D2)]))
    assert plan.sequence == ("p1",)


def test_duplicates_allowed_when_explicitly_flagged():
    windows = [window("d1", iso(D1, "08:00"), iso(D1, "18:00")),
               window("d2", iso(D2, "08:00"), iso(D2, "18:00"))]
    _, plan, report = _run(make_scenario(
        [poi("p1", ["cat_a"], 30, cost(0), windows)],
        [make_day("d1", D1), make_day("d2", D2)], (), allow_duplicate_pois=True))
    assert plan.sequence == ("p1", "p1")
    assert report.known_violations == ()


def test_depot_travel_is_included_and_reconciled():
    pois = [poi("depot", ["cat_depot"], 1, cost(0)),
            poi("p1", ["cat_a"], 60, cost(0), [DAY_OPEN])]
    edges = [edge("depot", "p1", 10), edge("p1", "depot", 8)]
    parsed, plan, report = _run(make_scenario(
        pois, [make_day()], edges,
        start_depot_poi_id="depot", end_depot_poi_id="depot"))
    assert plan.sequence == ("p1",)
    assert plan.days[0].stops[0].travel_from_prev_minutes == 10
    assert plan.total_travel_minutes == 18
    assert report.recomputed_total_travel_minutes == 18


def test_unknown_middle_route_excludes_candidate():
    pois = [poi("depot", ["cat_depot"], 1, cost(0)),
            poi("p1", ["cat_a"], 30, cost(0), [DAY_OPEN]),
            poi("p2", ["cat_a"], 30, cost(0), [DAY_OPEN])]
    edges = [edge("depot", "p1", 10), edge("p1", "depot", 8), edge("p2", "depot", 8)]
    parsed, plan, _ = _run(make_scenario(
        pois, [make_day()], edges,
        start_depot_poi_id="depot", end_depot_poi_id="depot"))
    assert plan.sequence == ("p1",)
    assert any(ex.reason.startswith("route_unknown") for ex in plan.excluded)


def test_unknown_return_route_yields_no_plan():
    pois = [poi("depot", ["cat_depot"], 1, cost(0)),
            poi("p1", ["cat_a"], 30, cost(0), [DAY_OPEN])]
    edges = [edge("depot", "p1", 10)]  # return edge missing
    _, plan, report = _run(make_scenario(
        pois, [make_day()], edges,
        start_depot_poi_id="depot", end_depot_poi_id="depot"))
    assert plan.status == "no_plan"
    assert plan.no_plan_reason == "no_verified_plan"
    assert any(ex.reason.startswith("route_unknown") for ex in plan.excluded)
    assert report.status == "no_plan"


def test_empty_candidates_yields_no_plan_no_candidates():
    _, plan, report = _run(make_scenario([], [make_day()]))
    assert plan.status == "no_plan"
    assert plan.no_plan_reason == "no_candidates"
    assert report.status == "no_plan"


def test_impossible_day_yields_known_bound_no_plan():
    night = window("d1", iso(D1, "18:00"), iso(D1, "22:00"))
    _, plan, _ = _run(make_scenario(
        [poi("p_night", ["cat_a"], 60, cost(0), [night])],
        [make_day(start=iso(D1, "08:00"), end=iso(D1, "10:00"))]))
    assert plan.status == "no_plan"
    assert plan.no_plan_reason == "infeasible_bounds"
    assert any(ex.reason == "opening_conflict" for ex in plan.excluded)


def test_preference_cannot_override_closing():
    closed = window("d1", iso(D1, "14:00"), iso(D1, "18:00"))
    openw = window("d1", iso(D1, "08:00"), iso(D1, "10:00"))
    pois = [
        poi("p_high", ["cat_b"], 30, cost(0), [closed]),
        poi("p_low", ["cat_a"], 30, cost(0), [openw]),
    ]
    _, plan, _ = _run(make_scenario(
        pois, [make_day(start=iso(D1, "08:00"), end=iso(D1, "10:00"))],
        (), preferences={"category_weights": {"cat_a": 1, "cat_b": 99}}))
    assert plan.sequence == ("p_low",)
    assert any(ex.poi_id == "p_high" and ex.reason == "opening_conflict"
               for ex in plan.excluded)


def test_minimum_stops_unmet_is_partial():
    _, plan, report = _run(make_scenario(
        [poi("p1", ["cat_a"], 30, cost(0), [DAY_OPEN])],
        [make_day()], (), minimum_stops=2))
    assert plan.status == "partial"
    assert any(req.startswith("minimum_stops") for req in report.unsatisfied_required)


def test_midnight_crossing_day_window():
    start = iso(D1, "20:00")
    end = iso(D2, "02:00")
    day = make_day(start=start, end=end)
    _, plan, report = _run(make_scenario(
        [poi("p1", ["cat_a"], 60, cost(0), [window("d1", start, end)])], [day]))
    assert plan.days[0].stops[0].arrival == parse_instant(start, "x")
    assert not any(v.code == "day_bounds" for v in report.known_violations)


def test_scheduling_is_deterministic():
    pois = [poi(name, ["cat_a"], 30, cost(0), [DAY_OPEN])
            for name in ("p_a", "p_b", "p_c")]
    edges = [edge(a, b, 5) for a in ("p_a", "p_b", "p_c")
             for b in ("p_a", "p_b", "p_c") if a != b]
    scenario = make_scenario(pois, [make_day()], edges)
    first = schedule(parse_scenario(scenario))
    second = schedule(parse_scenario(scenario))
    assert first.sequence == second.sequence
    assert first.total_travel_minutes == second.total_travel_minutes
