"""Independent temporal/budget validator for the OC-010 planner.

Separate implementation from the scheduler: it never imports or calls a scheduler
feasibility helper. It recomputes every structural, timing, travel, cost and
constraint check directly from the raw scenario evidence plus the ordered stops.

Guarantees:

* The plan's ``status`` and ``sequence`` are **not trusted**. The validator
  recomputes the canonical stop count/sequence from the day stops. A declared
  ``no_plan`` that still contains stops is fully checked (never bypassed) and a
  false refusal is reported.
* An **empty itinerary is never feasible**, even with no explicit minimum.
* The structural contract is enforced: matching ``scenario_id``, unique day ids
  in declared chronological order, no undeclared day, per-day ``max_stops`` and
  required days (meals, depots) considered by iterating *scenario* days.
* Directed travel is always enforced: ``arrival >= departure + travel`` when the
  edge is known; even when the edge is unknown the ordinary ``arrival >=
  previous departure`` overlap check still applies, and the missing edge is
  reported separately as unknown. A same-id transfer is a known zero only when
  the ids actually match.
* If the sum of the *known* costs alone already exceeds the budget, that is a
  known violation even if another cost is missing.
* Forged cost/time fields cannot change the verdict; totals are recomputed.

Statuses: ``feasible``, ``partial`` (known violation or unmet requirement),
``unverifiable`` (no known violation, but unknown source facts), ``no_plan``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

from domains.planning.contracts import (
    ALLOWED_COST_UNITS,
    Day,
    MealWindow,
    Plan,
    PlannedDay,
    Scenario,
    ValidationReport,
    Violation,
)


def _unsatisfied_requirements(scenario: Scenario, plan: Plan,
                              used_categories: Set[str]) -> List[str]:
    unmet: List[str] = []
    for category_id in scenario.required_categories:
        if category_id not in used_categories:
            unmet.append(f"required_category:{category_id}")

    if scenario.minimum_stops is not None:
        stop_count = sum(
            1 for day in plan.days for stop in day.stops
            if stop.poi_id not in (scenario.start_depot_id, scenario.end_depot_id)
        )
        if stop_count < scenario.minimum_stops:
            unmet.append(f"minimum_stops:{scenario.minimum_stops}>={stop_count}")

    lookup = {}
    for day in plan.days:
        lookup.setdefault(day.day_id, day)
    for source_day in scenario.days:
        if not source_day.meal_windows:
            continue
        planned = lookup.get(source_day.day_id)
        stops = planned.stops if planned is not None else ()
        for meal in source_day.meal_windows:
            if not _meal_covered(meal, stops, scenario):
                unmet.append(f"meal_window:{source_day.day_id}:{meal.category_id}")
    return unmet


def _meal_covered(meal: MealWindow, stops, scenario: Scenario) -> bool:
    for stop in stops:
        poi = scenario.poi(stop.poi_id)
        if poi is None or meal.category_id not in poi.category_ids:
            continue
        if stop.arrival < meal.end and stop.departure > meal.start:
            return True
    return False


def _empty_report(scenario: Scenario, plan: Plan,
                  unknown: Set[str], checks: Dict[str, int]) -> ValidationReport:
    unsatisfied = _unsatisfied_requirements(scenario, plan, set())
    checks["unsatisfied"] = len(unsatisfied)
    return ValidationReport(
        scenario_id=scenario.scenario_id,
        status="no_plan",
        no_plan_reason=plan.no_plan_reason or "missing_delivery",
        known_violations=tuple(),
        unknown_reasons=tuple(sorted(unknown)),
        unsatisfied_required=tuple(unsatisfied),
        recomputed_total_cost_party=None,
        recomputed_total_travel_minutes=0,
        recomputed_total_distance_km=None,
        stop_count=0,
        checks=checks,
    )


def validate(scenario: Scenario, plan: Plan) -> ValidationReport:
    """Recompute and return the independent validation report."""
    checks: Dict[str, int] = {
        "stops": 0, "known_violations": 0, "unknown": 0, "unsatisfied": 0}

    violations: List[Violation] = []
    unknown: Set[str] = set()
    used_categories: Set[str] = set()
    scenario_day_index = {day.day_id: i for i, day in enumerate(scenario.days)}
    plan_day_lookup: Dict[str, PlannedDay] = {}

    def add_violation(code: str, day_id: Optional[str], poi_id: Optional[str],
                      detail: str) -> None:
        violations.append(Violation(code=code, day_id=day_id, poi_id=poi_id,
                                    detail=detail))

    # --- structural: scenario id, day ids, order, duplicates -------------
    if plan.scenario_id != scenario.scenario_id:
        add_violation("scenario_id_mismatch", None, None,
                      "plan scenario_id does not match the scenario")
    seen_days: Set[str] = set()
    order: List[int] = []
    for day in plan.days:
        if day.day_id in seen_days:
            add_violation("duplicate_day", day.day_id, None, "day_id appears more than once")
            continue
        seen_days.add(day.day_id)
        plan_day_lookup[day.day_id] = day
        idx = scenario_day_index.get(day.day_id)
        if idx is None:
            add_violation("unknown_day", day.day_id, None, "day_id is not declared")
        else:
            order.append(idx)
    if order != sorted(order):
        add_violation("day_order", None, None, "plan days are not in declared order")

    canonical_sequence: List[str] = []
    for day in plan.days:
        for stop in day.stops:
            canonical_sequence.append(stop.poi_id)
    total_stops = len(canonical_sequence)

    if plan.sequence and tuple(plan.sequence) != tuple(canonical_sequence):
        add_violation("sequence_mismatch", None, None,
                      "plan.sequence does not match the canonical stop order")

    # --- empty itinerary is never feasible -------------------------------
    if total_stops == 0:
        unknown |= set(plan.unknown_reasons)
        # A no_plan refusal is preserved as-is; an empty non-refusal is
        # reported as missing delivery rather than a 0-violation success.
        return _empty_report(scenario, plan, unknown, checks)

    if plan.status == "no_plan":
        # A refusal that actually contains stops must not bypass checking.
        add_violation("no_plan_with_stops", None, None,
                      "plan is declared no_plan but contains stops")

    used: Set[str] = set()
    total_cost_known = Decimal(0)
    has_unknown_cost = False
    total_travel = 0
    total_distance = Decimal(0)
    origin: Optional[str] = scenario.start_depot_id
    prev_poi: Optional[str] = None
    prev_departure: Optional[int] = None

    for day_index, source_day in enumerate(scenario.days):
        planned = plan_day_lookup.get(source_day.day_id)
        stops = planned.stops if planned is not None else ()
        if source_day.max_stops is not None and len(stops) > source_day.max_stops:
            add_violation("max_stops_exceeded", source_day.day_id, None,
                          f"day has {len(stops)} stops > max_stops {source_day.max_stops}")
        for stop_index, stop in enumerate(stops):
            checks["stops"] += 1
            poi = scenario.poi(stop.poi_id)
            if poi is None:
                add_violation("unknown_poi", source_day.day_id, stop.poi_id,
                              f"poi_id '{stop.poi_id}' is not in the scenario")
                origin = None
                prev_poi = None
                prev_departure = stop.departure
                continue

            if stop.poi_id in used and not scenario.allow_duplicate_pois:
                add_violation("duplicate_poi", source_day.day_id, stop.poi_id,
                              "poi scheduled more than once")
            used.add(stop.poi_id)

            arrival = stop.arrival
            departure = stop.departure

            # Directed travel from the previous location. The overlap check is
            # always applied; the missing-edge case is reported separately.
            if stop_index == 0:
                if origin is not None:
                    if origin != stop.poi_id:
                        edge = scenario.route(origin, stop.poi_id)
                        if edge is None:
                            unknown.add(f"route_unknown:{origin}->{stop.poi_id}")
                            if arrival < source_day.start:
                                add_violation("travel_infeasible", source_day.day_id,
                                              stop.poi_id, "arrival before day start")
                        else:
                            total_travel += edge.duration_minutes
                            total_distance += edge.distance_km
                            if arrival < source_day.start + edge.duration_minutes:
                                add_violation("travel_infeasible", source_day.day_id,
                                              stop.poi_id,
                                              "arrival precedes directed inbound travel")
            else:
                if prev_poi != stop.poi_id:
                    edge = scenario.route(prev_poi, stop.poi_id)
                    if edge is None:
                        unknown.add(f"route_unknown:{prev_poi}->{stop.poi_id}")
                        if arrival < prev_departure:
                            add_violation("travel_infeasible", source_day.day_id,
                                          stop.poi_id,
                                          "arrival precedes previous departure")
                    else:
                        total_travel += edge.duration_minutes
                        total_distance += edge.distance_km
                        if arrival < prev_departure + edge.duration_minutes:
                            add_violation("travel_infeasible", source_day.day_id,
                                          stop.poi_id,
                                          "arrival precedes previous departure + travel")

            if departure <= arrival:
                add_violation("nonpositive_visit", source_day.day_id, stop.poi_id,
                              "visit interval is not positive")
            elif departure - arrival < poi.visit_minutes:
                add_violation("visit_too_short", source_day.day_id, stop.poi_id,
                              f"visit shorter than required {poi.visit_minutes} minutes")

            if arrival < source_day.start or departure > source_day.end:
                add_violation("day_bounds", source_day.day_id, stop.poi_id,
                              "stop falls outside the day window")

            if poi.hours_known:
                if not any(window.start <= arrival and departure <= window.end
                           for window in poi.windows_for(source_day.day_id)):
                    add_violation("opening_violation", source_day.day_id, stop.poi_id,
                                  "visit is not contained in a known opening window")
            else:
                unknown.add(f"hours_unknown:{stop.poi_id}")

            if poi.cost is None:
                has_unknown_cost = True
                unknown.add(f"cost_unknown:{stop.poi_id}")
            else:
                if poi.cost.currency != scenario.currency:
                    add_violation("currency_mismatch", source_day.day_id, stop.poi_id,
                                  "cost currency differs from the scenario currency")
                if poi.cost.unit not in ALLOWED_COST_UNITS:
                    add_violation("unit_mismatch", source_day.day_id, stop.poi_id,
                                  "cost unit is not per_person/per_party")
                total_cost_known += poi.cost.party_total(scenario.party_size)

            used_categories |= set(poi.category_ids)
            origin = stop.poi_id
            prev_poi = stop.poi_id
            prev_departure = departure

    # --- required end-depot return leg ------------------------------------
    if scenario.end_depot_id is not None:
        last_index = next((i for i in range(len(plan.days) - 1, -1, -1)
                           if plan.days[i].stops), None)
        if last_index is not None:
            stop = plan.days[last_index].stops[-1]
            source_day = scenario.days[scenario_day_index.get(plan.days[last_index].day_id, 0)]
            if scenario.poi(stop.poi_id) is not None and stop.poi_id != scenario.end_depot_id:
                edge = scenario.route(stop.poi_id, scenario.end_depot_id)
                if edge is None:
                    unknown.add(f"route_unknown:{stop.poi_id}->{scenario.end_depot_id}")
                else:
                    total_travel += edge.duration_minutes
                    total_distance += edge.distance_km
                    if stop.departure + edge.duration_minutes > source_day.end:
                        add_violation("return_depot_infeasible", source_day.day_id,
                                      stop.poi_id, "return to end depot exceeds the day window")

    # --- budget from recomputed known cost --------------------------------
    if scenario.budget is not None:
        if scenario.budget.currency != scenario.currency:
            add_violation("currency_mismatch", None, None,
                          "budget currency differs from the scenario currency")
        if total_cost_known > scenario.budget.amount:
            add_violation("budget_exceeded", None, None,
                          "recomputed known party cost exceeds the declared budget")

    unsatisfied = _unsatisfied_requirements(scenario, plan, used_categories)

    if violations:
        status = "partial"
    elif unsatisfied:
        status = "partial"
    elif unknown:
        status = "unverifiable"
    else:
        status = "feasible"

    checks["known_violations"] = len(violations)
    checks["unknown"] = len(unknown)
    checks["unsatisfied"] = len(unsatisfied)

    return ValidationReport(
        scenario_id=scenario.scenario_id,
        status=status,
        no_plan_reason=None,
        known_violations=tuple(violations),
        unknown_reasons=tuple(sorted(unknown)),
        unsatisfied_required=tuple(unsatisfied),
        recomputed_total_cost_party=(total_cost_known if not has_unknown_cost else None),
        recomputed_total_travel_minutes=total_travel,
        recomputed_total_distance_km=total_distance,
        stop_count=total_stops,
        checks=checks,
    )
