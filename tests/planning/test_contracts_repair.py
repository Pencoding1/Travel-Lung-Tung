"""Contract regressions from the OC-010 corrective QA (parse-time rules)."""

from decimal import Decimal

import pytest

from domains.planning import ScenarioError, ceil_minutes_from_seconds, parse_scenario
from helpers_planning import D1, D2, cost, edge, iso, make_day, make_scenario, poi, window

OPEN_DAY = window("d1", iso(D1, "08:00"), iso(D1, "18:00"))


def test_nonchronological_day_windows_rejected():
    days = [make_day("d1", D2), make_day("d2", D1)]
    scenario = make_scenario([poi("p1", ["cat_a"], 60)], days)
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(scenario)
    assert exc.value.code == "malformed_interval"


def test_overlapping_day_windows_rejected():
    days = [make_day("d1", D1, start=iso(D1, "08:00"), end=iso(D1, "12:00")),
            make_day("d2", D1, start=iso(D1, "11:00"), end=iso(D1, "18:00"))]
    scenario = make_scenario([poi("p1", ["cat_a"], 60)], days)
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(scenario)
    assert exc.value.code == "malformed_interval"


def test_date_window_mismatch_rejected():
    bad_day = {"day_id": "d1", "date": D1,
               "window": {"start": iso(D2, "08:00"), "end": iso(D2, "18:00")}}
    scenario = make_scenario([poi("p1", ["cat_a"], 60)], [bad_day])
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(scenario)
    assert exc.value.code == "date_window_mismatch"


def test_transport_mode_mismatch_rejected():
    scenario = make_scenario([poi("p1", ["cat_a"], 60), poi("p2", ["cat_b"], 60)],
                             [make_day()], [edge("p1", "p2", 5, mode="foot")],
                             transport_mode="car")
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(scenario)
    assert exc.value.code == "transport_mode_mismatch"


def test_per_leg_transport_modes_allowed_without_scenario_mode():
    scenario = parse_scenario(make_scenario(
        [poi("p1", ["cat_a"], 60), poi("p2", ["cat_b"], 60)],
        [make_day()],
        [edge("p1", "p2", 5, mode="car"), edge("p2", "p1", 8, mode="foot")]))
    assert scenario.route("p1", "p2").transport_mode == "car"
    assert scenario.route("p2", "p1").transport_mode == "foot"


def test_ceil_minutes_from_seconds():
    assert ceil_minutes_from_seconds(0) == 0
    assert ceil_minutes_from_seconds(60) == 1
    assert ceil_minutes_from_seconds(61) == 2
    assert ceil_minutes_from_seconds(90) == 2
    assert ceil_minutes_from_seconds(3599) == 60


def test_raw_duration_seconds_derives_ceiling_minutes():
    scenario = parse_scenario(make_scenario(
        [poi("p1", ["cat_a"], 60), poi("p2", ["cat_b"], 60)],
        [make_day()],
        [{"from_poi_id": "p1", "to_poi_id": "p2", "raw_duration_seconds": 90,
          "distance_km": "1.0", "transport_mode": "car", "provenance": "syn"}]))
    edge_obj = scenario.route("p1", "p2")
    assert edge_obj.duration_minutes == 2
    assert edge_obj.raw_duration_seconds == 90


def test_raw_duration_seconds_inconsistent_minutes_rejected():
    scenario = make_scenario(
        [poi("p1", ["cat_a"], 60), poi("p2", ["cat_b"], 60)], [make_day()],
        [{"from_poi_id": "p1", "to_poi_id": "p2", "raw_duration_seconds": 90,
          "duration_minutes": 1, "distance_km": "1.0",
          "transport_mode": "car", "provenance": "syn"}])
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(scenario)
    assert exc.value.code == "duration_rounding_mismatch"


def test_raw_distance_meters_consistency():
    good = parse_scenario(make_scenario(
        [poi("p1", ["cat_a"], 60), poi("p2", ["cat_b"], 60)], [make_day()],
        [{"from_poi_id": "p1", "to_poi_id": "p2", "duration_minutes": 5,
          "distance_km": "1.5", "raw_distance_meters": 1500,
          "transport_mode": "car", "provenance": "syn"}]))
    assert good.route("p1", "p2").raw_distance_meters == 1500

    bad = make_scenario(
        [poi("p1", ["cat_a"], 60), poi("p2", ["cat_b"], 60)], [make_day()],
        [{"from_poi_id": "p1", "to_poi_id": "p2", "duration_minutes": 5,
          "distance_km": "1.5", "raw_distance_meters": 1400,
          "transport_mode": "car", "provenance": "syn"}])
    with pytest.raises(ScenarioError) as exc:
        parse_scenario(bad)
    assert exc.value.code == "distance_mismatch"
