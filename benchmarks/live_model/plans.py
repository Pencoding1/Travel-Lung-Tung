"""Build typed plans from model output and validate them independently.

The **llm_only** path turns the model's own timed itinerary into typed
``Plan``/``PlannedDay``/``PlannedStop`` objects. Cost/visit/travel facts are taken
from the *scenario*, never from the model; only the model's chosen order and
instants are consumed. The model's claimed status is ignored.

The **hybrid** path no longer lives here: it runs the *production* scheduler via
:mod:`live_model.hybrid_adapter` (see that module for the documented mapping).
Both paths end in the existing independent validator (:func:`validate`), which
owns the verdict.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AI_ROOT = _REPO_ROOT / "ai_service"
if str(_AI_ROOT) not in sys.path:
    sys.path.insert(0, str(_AI_ROOT))

from domains.planning import parse_instant, validate  # noqa: E402
from domains.planning.contracts import (  # noqa: E402
    Exclusion,
    Plan,
    PlannedDay,
    PlannedStop,
    Scenario,
    ScenarioError,
)

from .schema import LlmOnlyPlan, OutputError  # noqa: E402

_KNOWN_BOUND_REASONS = {"opening_conflict", "day_window_conflict", "budget_exceeded"}


def _known_stop_cost(stops: Sequence[PlannedStop]) -> Decimal:
    total = Decimal(0)
    for stop in stops:
        if stop.cost_party is not None:
            total += stop.cost_party
    return total


def _totals(days_out: Sequence[PlannedDay]) -> Tuple[List[str], int, Decimal, Optional[Decimal]]:
    sequence: List[str] = []
    total_travel = 0
    total_distance = Decimal(0)
    total_cost = Decimal(0)
    cost_known = True
    for day in days_out:
        for stop in day.stops:
            sequence.append(stop.poi_id)
            if stop.travel_from_prev_minutes is not None:
                total_travel += stop.travel_from_prev_minutes
            if stop.travel_from_prev_distance_km is not None:
                total_distance += stop.travel_from_prev_distance_km
            if stop.cost_party is None:
                cost_known = False
            else:
                total_cost += stop.cost_party
    return sequence, total_travel, total_distance, (total_cost if cost_known else None)


def _finalize(scenario: Scenario, days_out: List[PlannedDay], excluded: List[Exclusion],
              unknown: List[str], notes: List[str], iterations: int) -> Plan:
    sequence, total_travel, total_distance, total_cost = _totals(days_out)
    total_stops = len(sequence)

    if total_stops == 0:
        candidate_ids = {
            poi.poi_id for poi in scenario.pois
            if poi.poi_id not in (scenario.start_depot_id, scenario.end_depot_id)
        }
        known_bound = {ex.poi_id for ex in excluded if ex.reason in _KNOWN_BOUND_REASONS}
        if candidate_ids and candidate_ids <= known_bound:
            reason = "infeasible_bounds"
        elif not candidate_ids:
            reason = "no_candidates"
        else:
            reason = "no_verified_plan"
        plan = Plan(
            scenario_id=scenario.scenario_id, status="no_plan", no_plan_reason=reason,
            days=tuple(), sequence=tuple(), total_cost_party=None, total_cost_currency=None,
            total_travel_minutes=0, total_distance_km=None, excluded=tuple(excluded),
            unsatisfied_required=tuple(), unknown_reasons=tuple(sorted(set(unknown))),
            iterations=iterations, notes=tuple(notes),
        )
        report = validate(scenario, plan)
        return replace(plan, status=report.status,
                       no_plan_reason=report.no_plan_reason or reason,
                       unknown_reasons=report.unknown_reasons,
                       unsatisfied_required=report.unsatisfied_required)

    plan = Plan(
        scenario_id=scenario.scenario_id, status="unverifiable", no_plan_reason=None,
        days=tuple(days_out), sequence=tuple(sequence),
        total_cost_party=total_cost,
        total_cost_currency=(scenario.currency if total_cost is not None else None),
        total_travel_minutes=total_travel, total_distance_km=total_distance,
        excluded=tuple(excluded), unsatisfied_required=tuple(),
        unknown_reasons=tuple(sorted(set(unknown))), iterations=iterations,
        notes=tuple(notes),
    )
    report = validate(scenario, plan)
    return replace(plan, status=report.status, no_plan_reason=None,
                   unknown_reasons=report.unknown_reasons,
                   unsatisfied_required=report.unsatisfied_required)


def build_llm_only_plan(scenario: Scenario, parsed: LlmOnlyPlan) -> Plan:
    """Turn the model's timed itinerary into a typed plan (strict times)."""
    excluded: List[Exclusion] = []
    unknown: List[str] = []
    notes: List[str] = ["llm_only_model_plan"]
    days_out: List[PlannedDay] = []
    origin: Optional[str] = scenario.start_depot_id

    for parsed_day in parsed.days:
        stops: List[PlannedStop] = []
        prev = origin
        for raw in parsed_day.stops:
            try:
                arrival = parse_instant(raw.arrival, f"{parsed_day.day_id}.{raw.poi_id}.arrival")
                departure = parse_instant(raw.departure, f"{parsed_day.day_id}.{raw.poi_id}.departure")
            except ScenarioError as exc:
                raise OutputError(f"model time is not a valid minute-resolution instant: {exc}")

            poi = scenario.poi(raw.poi_id)
            if poi is None:
                visit_minutes = max(0, departure - arrival)
                cost_party = None
                cost_currency = None
                unknown.append(f"unknown_poi:{raw.poi_id}")
            else:
                visit_minutes = poi.visit_minutes
                cost_party = poi.cost.party_total(scenario.party_size) if poi.cost else None
                cost_currency = poi.cost.currency if poi.cost else None
                if not poi.hours_known:
                    unknown.append(f"hours_unknown:{raw.poi_id}")
                if poi.cost is None:
                    unknown.append(f"cost_unknown:{raw.poi_id}")

            travel_minutes = None
            travel_distance = None
            if prev is not None and prev != raw.poi_id:
                edge = scenario.route(prev, raw.poi_id)
                if edge is None:
                    unknown.append(f"route_unknown:{prev}->{raw.poi_id}")
                else:
                    travel_minutes = edge.duration_minutes
                    travel_distance = edge.distance_km

            stops.append(PlannedStop(
                poi_id=raw.poi_id, arrival=arrival, departure=departure,
                visit_minutes=visit_minutes, travel_from_prev_minutes=travel_minutes,
                travel_from_prev_distance_km=travel_distance, cost_party=cost_party,
                cost_currency=cost_currency,
            ))
            prev = raw.poi_id
            origin = raw.poi_id
        days_out.append(PlannedDay(day_id=parsed_day.day_id, stops=tuple(stops)))

    return _finalize(scenario, days_out, excluded, unknown, notes, iterations=len(parsed.days))
