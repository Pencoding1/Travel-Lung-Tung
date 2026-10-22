"""Frozen-manifest tests: all 20 synthetic scenarios are retained and labelled."""

import json
from pathlib import Path

import pytest

from domains.planning import parse_scenario, schedule, validate

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "benchmarks" / "planning" / "scenarios.json"


@pytest.fixture(scope="module")
def manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_is_frozen_and_synthetic(manifest):
    assert manifest["frozen"] is True
    assert manifest["excluded_from_original_dataset"] is True
    assert manifest["generated_before_benchmark"] is True
    assert manifest["label"] == "synthetic-engineering-fixtures"
    assert len(manifest["scenarios"]) == 20


def test_scenario_ids_are_unique(manifest):
    ids = [entry["scenario_id"] for entry in manifest["scenarios"]]
    assert len(ids) == len(set(ids)) == 20


def test_every_scenario_has_authored_expected_properties(manifest):
    for entry in manifest["scenarios"]:
        expected = entry["author_expected"]
        assert expected["status"] in {"feasible", "partial", "unverifiable", "no_plan"}
        assert expected["properties"]


@pytest.mark.parametrize("index", range(20))
def test_scenario_matches_author_expected(manifest, index):
    entry = manifest["scenarios"][index]
    scenario = parse_scenario(entry["input"])
    plan = schedule(scenario)
    report = validate(scenario, plan)
    expected = entry["author_expected"]
    assert plan.status == expected["status"], entry["scenario_id"]
    assert plan.no_plan_reason == expected["no_plan_reason"], entry["scenario_id"]
    assert report.status == plan.status
    if plan.status == "no_plan":
        assert report.status == "no_plan"
        assert report.stop_count == 0


def test_all_twenty_retained_and_statuses_present(manifest):
    statuses = {}
    for entry in manifest["scenarios"]:
        scenario = parse_scenario(entry["input"])
        plan = schedule(scenario)
        statuses[plan.status] = statuses.get(plan.status, 0) + 1
        assert plan.scenario_id == entry["scenario_id"]
    assert sum(statuses.values()) == 20
    assert statuses.get("no_plan", 0) >= 1
    assert statuses.get("feasible", 0) >= 1
    assert statuses.get("unverifiable", 0) >= 1
    assert statuses.get("partial", 0) >= 1


def test_refusals_are_not_reported_as_zero_violation_success(manifest):
    refusals = 0
    for entry in manifest["scenarios"]:
        scenario = parse_scenario(entry["input"])
        plan = schedule(scenario)
        if plan.status != "no_plan":
            continue
        refusals += 1
        report = validate(scenario, plan)
        assert report.status == "no_plan"
        assert report.no_plan_reason == plan.no_plan_reason
    assert refusals >= 1
