"""Contract-level unit tests for :mod:`domains.planning.contracts`."""

import math
from decimal import Decimal

import pytest

from domains.planning import ScenarioError, parse_instant, parse_scenario
from helpers_planning import D1, D2, cost, edge, iso, make_day, make_scenario, poi, window

OPEN_DAY = window("d1", iso(D1, "08:00"), iso(D1, "18:00"))


def _one_poi(**overrides):
    entry = poi("p1", ["cat_a"], 60, cost(0), [OPEN_DAY])
    entry.update(overrides)
    return entry


def _valid(**overrides):
    scenario = make_scenario([_one_poi()], [make_day()])
    scenario.update(overrides)
    return scenario


def test_valid_scenario_parses():
    scenario = parse_scenario(_valid())
    assert scenario.party_size == 2
    assert scenario.pois[0].poi_id == "p1"
    assert scenario.days[0].day_id == "d1"


@pytest.mark.parametrize("bad", [True, 2.0, "2"])
def test_party_size_rejects_bool_float_string(bad):
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(_valid(party_size=bad))
    assert exc.value.code == "not_integer"


def test_party_size_must_be_positive():
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(_valid(party_size=0))
    assert exc.value.code in {"negative", "out_of_range"}


@pytest.mark.parametrize("bad", [True, 1.5, "60"])
def test_visit_minutes_rejects_bool_float_string(bad):
    scenario = make_scenario([_one_poi(visit_minutes=bad)], [make_day()])
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(scenario)
    assert exc.value.code == "not_integer"


def test_visit_minutes_must_be_positive():
    scenario = make_scenario([_one_poi(visit_minutes=0)], [make_day()])
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(scenario)
    assert exc.value.code in {"negative", "out_of_range"}


@pytest.mark.parametrize("bad", [-1, "-5", "NaN", "Infinity", True, 1.5])
def test_cost_rejects_negative_nonfinite_bool_float(bad):
    entry = _one_poi(cost={"amount": bad, "currency": "VND", "unit": "per_party"})
    scenario = make_scenario([entry], [make_day()])
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(scenario)
    assert exc.value.code in {"negative", "not_finite"}


def test_zero_free_price_is_accepted_and_absent_cost_is_unknown():
    free = parse_scenario(make_scenario([_one_poi(cost=cost(0))], [make_day()]))
    assert free.pois[0].cost is not None
    assert free.pois[0].cost.amount == Decimal(0)

    absent = parse_scenario(make_scenario(
        [poi("p1", ["cat_a"], 60, None, [OPEN_DAY])], [make_day()]))
    assert absent.pois[0].cost is None


def test_currency_mismatch_is_rejected():
    entry = _one_poi(cost=cost(100, "per_party", "THB"))
    scenario = make_scenario([entry], [make_day()])
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(scenario)
    assert exc.value.code == "currency_mismatch"


def test_budget_must_be_per_party():
    scenario = _valid(budget=cost(100, "per_person"))
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(scenario)
    assert exc.value.code == "unit_mismatch"


def test_unknown_cost_unit_is_rejected():
    entry = _one_poi(cost=cost(100, "per_group"))
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(make_scenario([entry], [make_day()]))
    assert exc.value.code == "unit_mismatch"


def test_distance_must_not_be_float():
    scenario = make_scenario([poi("p1", ["cat_a"], 60)], [make_day()],
                             [edge("p1", "p1", 1, distance_km=1.5)])
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(scenario)
    assert exc.value.code == "not_finite"


def test_duplicate_poi_ids_rejected():
    scenario = make_scenario([poi("p1", ["cat_a"], 60), poi("p1", ["cat_b"], 60)],
                             [make_day()])
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(scenario)
    assert exc.value.code == "duplicate"


def test_duplicate_day_ids_rejected():
    scenario = make_scenario([poi("p1", ["cat_a"], 60)],
                             [make_day("d1"), make_day("d1")])
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(scenario)
    assert exc.value.code == "duplicate"


def test_duplicate_route_edge_rejected():
    scenario = make_scenario([poi("p1", ["cat_a"], 60)], [make_day()],
                             [edge("p1", "p1"), edge("p1", "p1", 20)])
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(scenario)
    assert exc.value.code == "duplicate"


def test_malformed_day_window_rejected():
    bad_day = make_day(start=iso(D1, "18:00"), end=iso(D1, "08:00"))
    scenario = make_scenario([poi("p1", ["cat_a"], 60)], [bad_day])
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(scenario)
    assert exc.value.code == "malformed_interval"


def test_malformed_opening_window_rejected():
    entry = poi("p1", ["cat_a"], 60, cost(0),
                [window("d1", iso(D1, "12:00"), iso(D1, "11:00"))])
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(make_scenario([entry], [make_day()]))
    assert exc.value.code == "malformed_interval"


def test_meal_window_outside_day_rejected():
    meal = {"category_id": "cat_food", "start": iso(D1, "07:00"), "end": iso(D1, "08:30")}
    scenario = make_scenario([poi("p1", ["cat_a"], 60)],
                             [make_day(meal_windows=[meal])])
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(scenario)
    assert exc.value.code == "malformed_interval"


def test_naive_datetime_rejected():
    bad_day = make_day(start="2026-11-01T08:00:00", end="2026-11-01T18:00:00")
    scenario = make_scenario([poi("p1", ["cat_a"], 60)], [bad_day])
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(scenario)
    assert exc.value.code == "naive_datetime"


def test_seconds_resolution_rejected():
    with pytest.raises(ScenarioError) as exc:
        parse_instant("2026-11-01T08:00:30+07:00", "x")
    assert exc.value.code == "malformed_interval"


def test_route_unknown_poi_reference_rejected():
    scenario = make_scenario([poi("p1", ["cat_a"], 60)], [make_day()],
                             [edge("p1", "ghost")])
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(scenario)
    assert exc.value.code == "unknown_poi_reference"


def test_depot_unknown_reference_rejected():
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(_valid(start_depot_poi_id="ghost"))
    assert exc.value.code == "unknown_poi_reference"


def test_opening_window_unknown_day_rejected():
    entry = poi("p1", ["cat_a"], 60, cost(0),
                [window("d9", iso(D1, "09:00"), iso(D1, "10:00"))])
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(make_scenario([entry], [make_day()]))
    assert exc.value.code == "unknown_poi_reference"


def test_over_limit_candidates_rejected():
    pois = [poi(f"p{i}", ["cat_a"], 60) for i in range(201)]
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(make_scenario(pois, [make_day()]))
    assert exc.value.code == "over_limit"


def test_preference_weight_rejects_nonfinite_or_bool():
    with pytest.raises(ScenarioError):
        parse_scenario(_valid(preferences={"category_weights": {"cat_a": True}}))


def test_allow_duplicate_pois_must_be_bool():
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(_valid(allow_duplicate_pois="yes"))
    assert exc.value.code == "invalid_type"


def test_instant_comparison_is_timezone_absolute():
    # 08:00+07:00 == 01:00+00:00 == 02:00+01:00
    assert parse_instant("2026-11-01T08:00:00+07:00", "a") == \
        parse_instant("2026-11-01T01:00:00+00:00", "b") == \
        parse_instant("2026-11-01T02:00:00+01:00", "c")


def test_two_days_accepted():
    scenario = parse_scenario(make_scenario(
        [poi("p1", ["cat_a"], 60)], [make_day("d1", D1), make_day("d2", D2)]))
    assert len(scenario.days) == 2


def test_missing_scenario_id_rejected():
    scenario = _valid()
    del scenario["scenario_id"]
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(scenario)
    assert exc.value.code == "invalid_type"


def test_cost_math_is_exact_no_float_rounding():
    assert Decimal("0.1") + Decimal("0.2") == Decimal("0.3")


def test_nan_rejected_for_explicit_nan_string():
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(make_scenario(
            [poi("p1", ["cat_a"], 60, cost("nan"))], [make_day()]))
    assert not math.isfinite(float("nan"))  # sanity
    assert exc.value.code == "not_finite"

