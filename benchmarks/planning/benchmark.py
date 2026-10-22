"""Frozen 20-scenario engineering benchmark for the OC-010 planner.

This benchmark is **synthetic and deterministic**. It reads the hand-authored,
pre-frozen manifest ``scenarios.json`` (excluded from the original thesis
dataset), runs the stdlib-only scheduler and then the *independent* validator on
each scenario, and records:

* the raw scheduler output and the independent validation report,
* the author-declared expected property (authored before the run, never read by
  the scheduler) and whether the run matched it,
* elapsed wall time per scenario, the seed, module/version and file hashes.

It makes no model, network, database or graph call, and reports **no** LLM-only
condition, provider-token estimate or H2/H3 statistical claim (those are marked
unavailable — see the experiment protocol).

Run:

    .venv-validation\\Scripts\\python.exe benchmarks/planning/benchmark.py
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = REPO_ROOT / "ai_service"
if str(AI_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_ROOT))

from domains.planning import parse_scenario, schedule, validate  # noqa: E402

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "scenarios.json"
OUTPUT_JSON = HERE / "benchmark_results.json"
VERSION = "oc-010.v2"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_json(value) -> str:
    return _sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _file_hash(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _decimal_str(value):
    if value is None:
        return None
    return str(value)


def _serialise_plan(plan) -> dict:
    return {
        "status": plan.status,
        "no_plan_reason": plan.no_plan_reason,
        "sequence": list(plan.sequence),
        "days": [
            {
                "day_id": day.day_id,
                "stops": [
                    {
                        "poi_id": stop.poi_id,
                        "arrival_minute": stop.arrival,
                        "departure_minute": stop.departure,
                        "visit_minutes": stop.visit_minutes,
                        "travel_from_prev_minutes": stop.travel_from_prev_minutes,
                        "travel_from_prev_distance_km": _decimal_str(stop.travel_from_prev_distance_km),
                        "cost_party": _decimal_str(stop.cost_party),
                        "cost_currency": stop.cost_currency,
                    }
                    for stop in day.stops
                ],
            }
            for day in plan.days
        ],
        "total_cost_party": _decimal_str(plan.total_cost_party),
        "total_cost_currency": plan.total_cost_currency,
        "total_travel_minutes": plan.total_travel_minutes,
        "total_distance_km": _decimal_str(plan.total_distance_km),
        "iterations": plan.iterations,
        "excluded": [
            {"poi_id": ex.poi_id, "day_id": ex.day_id, "reason": ex.reason}
            for ex in plan.excluded
        ],
        "unknown_reasons": list(plan.unknown_reasons),
        "unsatisfied_required": list(plan.unsatisfied_required),
        "notes": list(plan.notes),
    }


def _serialise_report(report) -> dict:
    return {
        "status": report.status,
        "no_plan_reason": report.no_plan_reason,
        "known_violations": [
            {"code": v.code, "day_id": v.day_id, "poi_id": v.poi_id, "detail": v.detail}
            for v in report.known_violations
        ],
        "unknown_reasons": list(report.unknown_reasons),
        "unsatisfied_required": list(report.unsatisfied_required),
        "recomputed_total_cost_party": _decimal_str(report.recomputed_total_cost_party),
        "recomputed_total_travel_minutes": report.recomputed_total_travel_minutes,
        "recomputed_total_distance_km": _decimal_str(report.recomputed_total_distance_km),
        "stop_count": report.stop_count,
        "checks": dict(report.checks),
    }


def _source_hashes() -> dict:
    planning_dir = AI_ROOT / "domains" / "planning"
    return {
        path.name: _file_hash(path)
        for path in sorted(planning_dir.glob("*.py"))
    }


def run() -> dict:
    manifest_bytes = MANIFEST.read_bytes()
    manifest = json.loads(manifest_bytes)
    scenarios = manifest["scenarios"]
    if len(scenarios) != 20:
        raise AssertionError(f"expected exactly 20 frozen scenarios, found {len(scenarios)}")

    results = {
        "task": "OC-010",
        "version": VERSION,
        "data_source": "synthetic",
        "label": manifest.get("label"),
        "excluded_from_original_dataset": True,
        "frozen_before_benchmark": True,
        "warning": (
            "All scenarios are hand-authored synthetic fixtures. They are NOT the "
            "original thesis dataset and this is an engineering harness, not a "
            "statistical experiment. No LLM-only condition, provider-token estimate, "
            "H2 or H3 claim is produced; those are unavailable."
        ),
        "unavailable_analyses": [
            "llm_only_condition",
            "provider_token_estimate",
            "H2_significance",
            "H3_significance",
            "original_dataset_reproduction",
        ],
        "manifest_sha256": _sha256_bytes(manifest_bytes),
        "source_sha256": _source_hashes(),
        "python": {
            "version": sys.version,
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "scenarios": [],
        "summary": {},
    }

    summary = {
        "total": len(scenarios),
        "retained": 0,
        "status_counts": {},
        "no_plan_reasons": {},
        "known_violation_scenarios": 0,
        "unknown_scenarios": 0,
        "unsatisfied_scenarios": 0,
        "author_expected_match": 0,
        "author_expected_mismatch": [],
    }

    for entry in scenarios:
        scenario_id = entry["scenario_id"]
        raw_input = entry["input"]
        expected = entry.get("author_expected", {})
        input_hash = _sha256_json(raw_input)

        started = time.perf_counter()
        scenario = parse_scenario(raw_input)
        plan = schedule(scenario)
        report = validate(scenario, plan)
        elapsed = time.perf_counter() - started

        matched = (
            plan.status == expected.get("status")
            and plan.no_plan_reason == expected.get("no_plan_reason")
        )
        if matched:
            summary["author_expected_match"] += 1
        else:
            summary["author_expected_mismatch"].append({
                "scenario_id": scenario_id,
                "expected": {"status": expected.get("status"),
                             "no_plan_reason": expected.get("no_plan_reason")},
                "actual": {"status": plan.status, "no_plan_reason": plan.no_plan_reason},
            })

        results["scenarios"].append({
            "scenario_id": scenario_id,
            "seed": scenario.seed,
            "input_sha256": input_hash,
            "author_expected": expected,
            "matched_author_expected": matched,
            "elapsed_seconds": elapsed,
            "plan": _serialise_plan(plan),
            "independent_validation": _serialise_report(report),
        })

        summary["retained"] += 1
        summary["status_counts"][plan.status] = summary["status_counts"].get(plan.status, 0) + 1
        if plan.no_plan_reason:
            summary["no_plan_reasons"][plan.no_plan_reason] = \
                summary["no_plan_reasons"].get(plan.no_plan_reason, 0) + 1
        if report.known_violations:
            summary["known_violation_scenarios"] += 1
        if report.unknown_reasons:
            summary["unknown_scenarios"] += 1
        if report.unsatisfied_required:
            summary["unsatisfied_scenarios"] += 1

    results["summary"] = summary
    return results


def main() -> int:
    results = run()
    OUTPUT_JSON.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    summary = results["summary"]
    print(f"task={results['task']} version={results['version']} "
          f"data_source={results['data_source']} scenarios={summary['total']}")
    header = f"{'scenario':>9} {'status':>15} {'no_plan_reason':>22} {'match':>6} {'sec':>8}"
    print(header)
    for record in results["scenarios"]:
        plan = record["plan"]
        print(f"{record['scenario_id']:>9} {plan['status']:>15} "
              f"{str(plan['no_plan_reason']):>22} "
              f"{str(record['matched_author_expected']):>6} "
              f"{record['elapsed_seconds']:>8.5f}")
    print(f"status_counts={summary['status_counts']}")
    print(f"no_plan_reasons={summary['no_plan_reasons']}")
    print(f"author_expected_match={summary['author_expected_match']}/{summary['total']}")
    print(f"raw results: {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
