"""OC-016 bounded integration regression: cumulative trip budget.

The scheduler's budget check previously summed only the *completed* prior days,
so stops already placed on the in-progress day were invisible. Two stops of 60
per party under a 100 per-party budget were both admitted (120 total), producing
a ``partial``/``budget_exceeded`` plan even though a single valid 60-cost stop
satisfies the explicit ``minimum_stops``.

These tests pin the corrected cumulative semantics:
* current-day stops are summed before adding a candidate;
* the same counterexample is fixed within one day and across days;
* an unknown cost does not erase a known subtotal (the known sum still bounds
  further candidates), while remaining unknown \u2014 never zero.
"""

from domains.planning import parse_scenario, schedule, validate
from helpers_planning import D1, D2, cost, edge, iso, make_day, make_scenario, poi, window

DAY1_WINDOW = window("d1", iso(D1, "08:00"), iso(D1, "18:00"))


def _two_pois_60():
    return [
        poi("p1", ["cat_a"], 30, cost(60), [DAY1_WINDOW]),
        poi("p2", ["cat_a"], 30, cost(60), [DAY1_WINDOW]),
    ]


def _bidirectional_edges():
    return [edge("p1", "p2", 5), edge("p2", "p1", 5)]


def test_two_sixty_stops_budget_100_same_day_yields_one_stop():
    scenario = parse_scenario(make_scenario(
        _two_pois_60(), [make_day()], _bidirectional_edges(),
        budget=cost(100, "per_party"), minimum_stops=1))
    plan = schedule(scenario)
    report = validate(scenario, plan)

    assert len(plan.sequence) == 1
    assert plan.total_cost_party == 60
    assert report.status == "feasible"
    assert report.stop_count == 1
    assert report.recomputed_total_cost_party == 60
    assert any(ex.reason == "budget_exceeded" for ex in plan.excluded)


def test_cumulative_budget_across_days_stops_at_two_valid_days():
    # Two days, one 60-cost stop per day, 100 per-party budget: only one
    # *additional* stop may be committed in total, so the trip carries a single
    # stop even though two days are available.
    pois = [
        poi("p1", ["cat_a"], 30, cost(60), [window("d1", iso(D1, "08:00"), iso(D1, "18:00")),
                                            window("d2", iso(D2, "08:00"), iso(D2, "18:00"))]),
        poi("p2", ["cat_a"], 30, cost(60), [window("d1", iso(D1, "08:00"), iso(D1, "18:00")),
                                            window("d2", iso(D2, "08:00"), iso(D2, "18:00"))]),
    ]
    scenario = parse_scenario(make_scenario(
        pois, [make_day("d1", D1), make_day("d2", D2)],
        [edge("p1", "p2", 5), edge("p2", "p1", 5)],
        budget=cost(100, "per_party"), minimum_stops=1))
    plan = schedule(scenario)
    report = validate(scenario, plan)

    assert len(plan.sequence) == 1
    assert plan.total_cost_party == 60
    assert report.status == "feasible"
    assert report.recomputed_total_cost_party == 60


def test_current_day_stop_is_counted_not_just_prior_days():
    # p1 (60, day one) + p2 (60, day one) cannot both fit under 100; p3 (60, day
    # two) is also blocked by the cumulative subtotal. The delivered plan must not
    # exceed the budget and must remain a single stop.
    pois = [
        poi("p1", ["cat_a"], 30, cost(60), [window("d1", iso(D1, "08:00"), iso(D1, "18:00"))]),
        poi("p2", ["cat_a"], 30, cost(60), [window("d1", iso(D1, "08:00"), iso(D1, "18:00"))]),
        poi("p3", ["cat_b"], 30, cost(60), [window("d2", iso(D2, "08:00"), iso(D2, "18:00"))]),
    ]
    edges = [edge("p1", "p2", 5), edge("p2", "p1", 5), edge("p1", "p3", 5),
             edge("p3", "p1", 5)]
    scenario = parse_scenario(make_scenario(
        pois, [make_day("d1", D1), make_day("d2", D2)], edges,
        budget=cost(100, "per_party"), minimum_stops=1))
    plan = schedule(scenario)
    report = validate(scenario, plan)

    assert plan.total_cost_party is not None
    assert plan.total_cost_party <= 100
    assert report.status == "feasible"


def test_unknown_cost_does_not_erase_known_subtotal():
    # Day 1 places p_known (60, known) and p_unknown (cost unknown). The unknown
    # cost must not be treated as zero, and must not erase the known 60 subtotal:
    # a later 60-cost candidate on day 2 is still blocked by the cumulative
    # *known* subtotal (60 + 60 > 100). The unknown is surfaced explicitly.
    pois = [
        poi("p_known", ["cat_a"], 30, cost(60),
            [window("d1", iso(D1, "08:00"), iso(D1, "18:00"))]),
        poi("p_unknown", ["cat_a"], 30, None,
            [window("d1", iso(D1, "08:00"), iso(D1, "18:00"))]),
        poi("p_known2", ["cat_a"], 30, cost(60),
            [window("d2", iso(D2, "08:00"), iso(D2, "18:00"))]),
    ]
    edges = [
        edge("p_known", "p_unknown", 5), edge("p_unknown", "p_known", 5),
        edge("p_unknown", "p_known2", 5), edge("p_known2", "p_unknown", 5),
    ]
    scenario = parse_scenario(make_scenario(
        pois, [make_day("d1", D1), make_day("d2", D2)], edges,
        budget=cost(100, "per_party"), minimum_stops=1))
    plan = schedule(scenario)
    report = validate(scenario, plan)

    known_subtotal = sum((stop.cost_party for day in plan.days for stop in day.stops
                          if stop.cost_party is not None), 0)
    assert known_subtotal == 60
    assert "p_known2" not in plan.sequence
    assert any(ex.poi_id == "p_known2" and ex.reason == "budget_exceeded"
               for ex in plan.excluded)
    assert any(reason.startswith("cost_unknown:") for reason in report.unknown_reasons)


def test_no_current_day_regression_when_budget_allows_both():
    # Sanity: with a 120 budget both 60-cost stops are admitted (the fix must not
    # over-exclude).
    scenario = parse_scenario(make_scenario(
        _two_pois_60(), [make_day()], _bidirectional_edges(),
        budget=cost(120, "per_party"), minimum_stops=1))
    plan = schedule(scenario)
    report = validate(scenario, plan)

    assert len(plan.sequence) == 2
    assert plan.total_cost_party == 120
    assert report.status == "feasible"
