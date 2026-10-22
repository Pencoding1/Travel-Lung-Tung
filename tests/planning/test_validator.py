"""Independent validator tests for :mod:`domains.planning.validator`."""

from dataclasses import replace
from decimal import Decimal

from domains.planning import parse_scenario, schedule, validate
from helpers_planning import D1, cost, edge, iso, make_day, make_scenario, poi, window

DAY_OPEN = window("d1", iso(D1, "08:00"), iso(D1, "18:00"))


def _two_stop_scenario(pois=None, route_edges=None, **overrides):
    if pois is None:
        pois = [
            poi("p1", ["cat_a"], 30, cost(0), [DAY_OPEN]),
            poi("p2", ["cat_a"], 30, cost(0), [DAY_OPEN]),
        ]
    if route_edges is None:
        route_edges = [edge("p1", "p2", 10), edge("p2", "p1", 10)]
    return make_scenario(pois, [make_day()], route_edges, **overrides)


def _replace_stop(plan, day_index, stop_index, **changes):
    days = list(plan.days)
    stops = list(days[day_index].stops)
    stops[stop_index] = replace(stops[stop_index], **changes)
    days[day_index] = replace(days[day_index], stops=tuple(stops))
    return replace(plan, days=tuple(days))


def test_scheduler_valid_plan_validates_feasible():
    scenario = parse_scenario(_two_stop_scenario())
    plan = schedule(scenario)
    report = validate(scenario, plan)
    assert plan.status == "feasible"
    assert report.status == "feasible"
    assert report.known_violations == ()


def test_forged_early_arrival_is_a_violation_despite_valid_baseline():
    scenario = parse_scenario(_two_stop_scenario())
    plan = schedule(scenario)
    assert plan.sequence == ("p1", "p2")
    forged = _replace_stop(plan, 0, 1, arrival=plan.days[0].stops[0].departure)
    report = validate(scenario, forged)
    assert report.status == "partial"
    assert any(v.code == "travel_infeasible" for v in report.known_violations)


def test_forged_total_cost_is_ignored_and_recomputed():
    scenario = parse_scenario(_two_stop_scenario(
        route_edges=[],
        party_size=3,
        pois=[
            poi("p1", ["cat_a"], 30, cost(100000, "per_person"), [DAY_OPEN]),
        ]))
    plan = schedule(scenario)
    forged = replace(plan, total_cost_party=Decimal("999999999"))
    report = validate(scenario, forged)
    assert report.recomputed_total_cost_party == Decimal("300000")
    assert report.status == "feasible"


def test_party_multiplication_per_party_is_not_multiplied():
    scenario = parse_scenario(make_scenario(
        [poi("p1", ["cat_a"], 30, cost(100000, "per_party"), [DAY_OPEN])],
        [make_day()], (), party_size=4))
    report = validate(scenario, schedule(scenario))
    assert report.recomputed_total_cost_party == Decimal("100000")


def test_unknown_poi_id_is_a_violation():
    scenario = parse_scenario(_two_stop_scenario())
    plan = schedule(scenario)
    forged = _replace_stop(plan, 0, 1, poi_id="ghost")
    report = validate(scenario, forged)
    assert any(v.code == "unknown_poi" for v in report.known_violations)
    assert report.status == "partial"


def test_unknown_route_in_plan_is_reported_as_unknown():
    pois = [
        poi("p1", ["cat_a"], 30, cost(0), [DAY_OPEN]),
        poi("p2", ["cat_a"], 30, cost(0), [DAY_OPEN]),
    ]
    edges = [edge("p2", "p1", 10)]  # p1->p2 missing
    scenario = parse_scenario(make_scenario(pois, [make_day()], edges))
    plan = schedule(scenario)
    assert plan.sequence == ("p1",)
    # Force p2 into the plan; its inbound route is unknown, not zero.
    forged = _replace_stop(plan, 0, 0, poi_id="p1")
    days = list(forged.days)
    stops = list(days[0].stops)
    p2_stop = replace(stops[0], poi_id="p2", arrival=stops[0].departure + 1,
                      departure=stops[0].departure + 31)
    stops.append(p2_stop)
    forged = replace(forged, days=(replace(days[0], stops=tuple(stops)),),
                     sequence=("p1", "p2"))
    report = validate(scenario, forged)
    assert any("route_unknown:p1->p2" == reason for reason in report.unknown_reasons)
    assert report.status == "unverifiable"


def test_no_plan_status_is_preserved_not_reported_as_zero_violation_success():
    scenario = parse_scenario(make_scenario([], [make_day()]))
    plan = schedule(scenario)
    report = validate(scenario, plan)
    assert plan.status == "no_plan"
    assert report.status == "no_plan"
    assert report.known_violations == ()
    assert report.stop_count == 0


def test_opening_violation_is_detected():
    tight = window("d1", iso(D1, "09:00"), iso(D1, "10:00"))
    scenario = parse_scenario(make_scenario(
        [poi("p1", ["cat_a"], 30, cost(0), [tight])], [make_day()]))
    plan = schedule(scenario)
    forged = _replace_stop(plan, 0, 0, arrival=plan.days[0].stops[0].arrival + 3600,
                           departure=plan.days[0].stops[0].departure + 3600)
    report = validate(scenario, forged)
    assert any(v.code in {"opening_violation", "day_bounds"}
               for v in report.known_violations)


def test_day_bounds_violation_is_detected():
    scenario = parse_scenario(make_scenario(
        [poi("p1", ["cat_a"], 30, cost(0), [DAY_OPEN])], [make_day(end=iso(D1, "10:00"))]))
    plan = schedule(scenario)
    stop = plan.days[0].stops[0]
    forged = _replace_stop(plan, 0, 0, departure=stop.arrival + 5 * 60)
    report = validate(scenario, forged)
    assert any(v.code == "day_bounds" for v in report.known_violations)


def test_return_depot_infeasible_is_detected():
    pois = [poi("depot", ["cat_depot"], 1, cost(0)),
            poi("p1", ["cat_a"], 30, cost(0), [window("d1", iso(D1, "08:00"), iso(D1, "10:00"))])]
    edges = [edge("depot", "p1", 10), edge("p1", "depot", 10)]
    scenario = parse_scenario(make_scenario(
        pois, [make_day(start=iso(D1, "08:00"), end=iso(D1, "10:00"))], edges,
        start_depot_poi_id="depot", end_depot_poi_id="depot"))
    plan = schedule(scenario)
    stop = plan.days[0].stops[0]
    forged = _replace_stop(plan, 0, 0, departure=stop.arrival + 115)
    report = validate(scenario, forged)
    assert any(v.code == "return_depot_infeasible" for v in report.known_violations)


def test_duplicate_poi_in_plan_is_detected():
    scenario = parse_scenario(make_scenario(
        [poi("p1", ["cat_a"], 30, cost(0), [DAY_OPEN])], [make_day()]))
    plan = schedule(scenario)
    stop = plan.days[0].stops[0]
    dup = replace(stop, arrival=stop.departure + 1, departure=stop.departure + 31)
    forged = replace(plan, days=(replace(plan.days[0], stops=(stop, dup)),))
    report = validate(scenario, forged)
    assert any(v.code == "duplicate_poi" for v in report.known_violations)


def test_missing_hours_is_unknown_not_violation():
    scenario = parse_scenario(make_scenario(
        [poi("p1", ["cat_a"], 30, cost(0))], [make_day()]))
    report = validate(scenario, schedule(scenario))
    assert report.status == "unverifiable"
    assert any(reason.startswith("hours_unknown:") for reason in report.unknown_reasons)
    assert report.known_violations == ()


def test_missing_cost_is_unknown_not_violation():
    scenario = parse_scenario(make_scenario(
        [poi("p1", ["cat_a"], 30, None, [DAY_OPEN])], [make_day()],
        (), budget=cost(100000)))
    report = validate(scenario, schedule(scenario))
    assert report.status == "unverifiable"
    assert any(reason.startswith("cost_unknown:") for reason in report.unknown_reasons)


def test_budget_exceeded_is_recomputed_from_source():
    raw = make_scenario(
        [poi("p_pricey", ["cat_a"], 30, cost(1000000), [DAY_OPEN])], [make_day()])
    generous = parse_scenario(raw)
    plan = schedule(generous)  # feasible without a budget
    strict_raw = dict(raw)
    strict_raw["budget"] = cost(10, "per_party")
    strict = parse_scenario(strict_raw)
    report = validate(strict, plan)
    assert any(v.code == "budget_exceeded" for v in report.known_violations)
    assert report.status == "partial"


def test_short_visit_is_detected():
    scenario = parse_scenario(make_scenario(
        [poi("p1", ["cat_a"], 60, cost(0), [DAY_OPEN])], [make_day()]))
    plan = schedule(scenario)
    stop = plan.days[0].stops[0]
    forged = _replace_stop(plan, 0, 0, departure=stop.arrival + 10)
    report = validate(scenario, forged)
    assert any(v.code == "visit_too_short" for v in report.known_violations)
