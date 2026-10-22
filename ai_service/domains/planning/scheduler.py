"""Bounded, deterministic itinerary scheduler (OC-010).

The scheduler is a pure function over the typed contracts. No I/O, no
randomness, no global state. Given the same :class:`Scenario` it always produces
the same ordered plan.

Heuristic shape (documented, deliberately bounded — it makes **no** global
optimality claim):

1. Days are processed in declared (chronological) order.
2. An **origin is carried across day boundaries**: the last scheduled stop of a
   day becomes the origin for the next day; if a day produces no stops the
   origin is unchanged. The outbound leg uses ``start_depot_poi_id`` when given.
   A missing directed transfer never becomes zero or a teleport — the candidate
   is excluded with an explicit ``route_unknown`` reason, or (for an
   origin-less day boundary) recorded as an unknown boundary.
3. At each step the reachable, unused candidate that covers an outstanding hard
   requirement is preferred; ties break by descending preference weight, then
   ascending directed travel time, then ascending POI id. Hard constraints
   dominate preferences.
4. A candidate is placed at the earliest instant at/after the arrival implied by
   directed travel, inside a known opening window when hours are known (waiting
   allowed), ending inside the day window, and - on the final declared day with
   an end depot - leaving room for the return leg.

Missing travel/hours/cost are never treated as satisfied. Every exclusion and
every unmet declared requirement is recorded. The final status is delegated to
the independent validator.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

from domains.planning import validator
from domains.planning.contracts import (
    Day,
    Exclusion,
    MealWindow,
    Plan,
    PlannedDay,
    PlannedStop,
    Poi,
    Scenario,
)

_KNOWN_BOUND_REASONS = {"opening_conflict", "day_window_conflict", "budget_exceeded"}


def _party_cost(scenario: Scenario, poi: Poi) -> Optional[Decimal]:
    if poi.cost is None:
        return None
    return poi.cost.party_total(scenario.party_size)


def _track(scenario: Scenario, origin: Optional[str], target: str
           ) -> Tuple[Optional[int], Optional[Decimal], bool]:
    """Return (minutes, distance_km, known). Same id => known zero transfer."""
    if origin is None:
        return None, None, True
    if origin == target:
        return 0, Decimal(0), True
    edge = scenario.route(origin, target)
    if edge is None:
        return None, None, False
    return edge.duration_minutes, edge.distance_km, True


def _valid_start(day: Day, poi: Poi, start: int, return_buffer: int) -> bool:
    if start < day.start:
        return False
    end = start + poi.visit_minutes
    if end + return_buffer > day.end:
        return False
    if poi.hours_known:
        return any(window.start <= start and end <= window.end
                   for window in poi.windows_for(day.day_id))
    return True


def _earliest_start(day: Day, poi: Poi, arrival_base: int, return_buffer: int,
                    meal_targets: List[MealWindow]) -> Optional[int]:
    for meal in meal_targets:
        candidate = max(arrival_base, meal.start)
        if candidate < meal.end and _valid_start(day, poi, candidate, return_buffer):
            return candidate
    if poi.hours_known:
        for window in poi.windows_for(day.day_id):
            start = max(arrival_base, window.start)
            if _valid_start(day, poi, start, return_buffer):
                return start
        return None
    if _valid_start(day, poi, arrival_base, return_buffer):
        return arrival_base
    return None


def _meal_overlaps(meal: MealWindow, stops: List[PlannedStop],
                   scenario: Scenario) -> bool:
    for stop in stops:
        poi = scenario.poi(stop.poi_id)
        if poi is None or meal.category_id not in poi.category_ids:
            continue
        if stop.arrival < meal.end and stop.departure > meal.start:
            return True
    return False


def _unsatisfied_meals(day: Day, stops: List[PlannedStop],
                       scenario: Scenario) -> List[MealWindow]:
    return [meal for meal in day.meal_windows
            if not _meal_overlaps(meal, stops, scenario)]


def _rank_key(scenario: Scenario, poi: Poi, travel_minutes: Optional[int],
              outstanding_required: Set[str],
              unsatisfied_meals: List[str]) -> Tuple[int, int, int, str]:
    categories = set(poi.category_ids)
    hard_priority = 0 if (categories & outstanding_required
                          or any(c in categories for c in unsatisfied_meals)) else 1
    preference = sum(scenario.preferences.get(c, 0) for c in poi.category_ids)
    travel = travel_minutes if travel_minutes is not None else 10 ** 9
    return (hard_priority, -preference, travel, poi.poi_id)


def _classify_no_plan(candidates: List[Poi], excluded: List[Exclusion],
                      iteration_limit_hit: bool, any_feasible_seen: bool) -> str:
    if iteration_limit_hit:
        return "search_limit"
    candidate_ids = {p.poi_id for p in candidates}
    known_bound = {ex.poi_id for ex in excluded if ex.reason in _KNOWN_BOUND_REASONS}
    if not any_feasible_seen and candidate_ids and candidate_ids <= known_bound:
        # Every candidate was excluded by a *known* single-stop bound (budget,
        # opening or day window), which is a formal proof that no non-empty plan
        # is deliverable. Anything else is heuristic uncertainty, not proof.
        return "infeasible_bounds"
    return "no_verified_plan"


def _finalize_no_plan(scenario: Scenario, reason: str, excluded: List[Exclusion],
                      unknown: List[str], notes: List[str], iterations: int) -> Plan:
    preserved = set(unknown)
    preserved |= {ex.reason for ex in excluded if ex.reason.startswith("route_unknown")}
    plan = Plan(
        scenario_id=scenario.scenario_id,
        status="no_plan",
        no_plan_reason=reason,
        days=tuple(),
        sequence=tuple(),
        total_cost_party=None,
        total_cost_currency=None,
        total_travel_minutes=0,
        total_distance_km=None,
        excluded=tuple(excluded),
        unsatisfied_required=tuple(),
        unknown_reasons=tuple(sorted(preserved)),
        iterations=iterations,
        notes=tuple(notes),
    )
    report = validator.validate(scenario, plan)
    return replace(plan, status=report.status,
                   unsatisfied_required=report.unsatisfied_required,
                   unknown_reasons=report.unknown_reasons)


def _enforce_return(scenario: Scenario, days_out: List[PlannedDay],
                    unknown: List[str], notes: List[str]) -> None:
    """Drop trailing stops until the required end-depot return fits.

    Only relevant when the final non-empty day did not reserve a return buffer
    (for example when the last declared day is empty). Missing return edges stay
    unknown; they are never treated as zero.
    """
    if scenario.end_depot_id is None:
        return
    while True:
        last_index = next((i for i in range(len(days_out) - 1, -1, -1)
                           if days_out[i].stops), None)
        if last_index is None:
            return
        stop = days_out[last_index].stops[-1]
        if stop.poi_id == scenario.end_depot_id:
            return
        edge = scenario.route(stop.poi_id, scenario.end_depot_id)
        if edge is None:
            unknown.append(f"route_unknown:{stop.poi_id}->{scenario.end_depot_id}")
            return
        day = scenario.days[last_index]
        if stop.departure + edge.duration_minutes <= day.end:
            return
        days_out[last_index] = replace(days_out[last_index],
                                       stops=days_out[last_index].stops[:-1])
        notes.append(f"return_buffer_repair:{stop.poi_id}")


def schedule(scenario: Scenario) -> Plan:
    """Run the bounded deterministic heuristic and return the finalized plan."""
    depot_ids = {d for d in (scenario.start_depot_id, scenario.end_depot_id) if d}
    candidates = [p for p in scenario.pois if p.poi_id not in depot_ids]
    excluded: List[Exclusion] = []
    unknown: List[str] = []
    notes: List[str] = []
    iterations = 0
    iteration_limit_hit = False

    if not candidates:
        return _finalize_no_plan(scenario, "no_candidates", excluded, unknown,
                                 notes, iterations)

    used: Set[str] = set()
    outstanding_required: Set[str] = set(scenario.required_categories)
    days_out: List[PlannedDay] = []
    any_feasible_seen = False
    last_day_index = len(scenario.days) - 1
    origin: Optional[str] = scenario.start_depot_id

    for day_index, day in enumerate(scenario.days):
        if iteration_limit_hit:
            break
        is_last = day_index == last_day_index
        current_time = day.start
        day_stops: List[PlannedStop] = []
        day_max = day.max_stops if day.max_stops is not None else len(candidates)
        if origin is None and day_index > 0:
            unknown.append(f"interday_origin_unknown:{day.day_id}")

        while len(day_stops) < day_max and not iteration_limit_hit:
            unsatisfied_meals = _unsatisfied_meals(day, day_stops, scenario)
            meal_categories = [meal.category_id for meal in unsatisfied_meals]
            scored: List[Tuple[Tuple[int, int, int, str], Poi,
                               Optional[int], Optional[Decimal]]] = []
            for poi in candidates:
                if not scenario.allow_duplicate_pois and poi.poi_id in used:
                    continue
                iterations += 1
                if iterations > scenario.max_iterations:
                    iteration_limit_hit = True
                    notes.append("iteration_limit_reached")
                    break
                travel_minutes, travel_distance, _known = _track(
                    scenario, origin, poi.poi_id)
                scored.append((_rank_key(scenario, poi, travel_minutes,
                                         outstanding_required, meal_categories),
                               poi, travel_minutes, travel_distance))

            if iteration_limit_hit:
                break
            scored.sort(key=lambda item: item[0])

            chosen: Optional[Tuple[Poi, Optional[int], Optional[Decimal],
                                   int, Optional[Decimal]]] = None
            for _key, poi, travel_minutes, travel_distance in scored:
                if origin is not None and origin != poi.poi_id \
                        and scenario.route(origin, poi.poi_id) is None:
                    excluded.append(Exclusion(
                        poi.poi_id, day.day_id, f"route_unknown:{origin}->{poi.poi_id}"))
                    continue

                return_buffer = 0
                if is_last and scenario.end_depot_id is not None:
                    if scenario.end_depot_id != poi.poi_id:
                        return_edge = scenario.route(poi.poi_id, scenario.end_depot_id)
                        if return_edge is None:
                            excluded.append(Exclusion(
                                poi.poi_id, day.day_id,
                                f"route_unknown:{poi.poi_id}->{scenario.end_depot_id}"))
                            continue
                        return_buffer = return_edge.duration_minutes

                arrival_base = current_time if travel_minutes is None \
                    else current_time + travel_minutes
                meal_targets = [meal for meal in unsatisfied_meals
                                if meal.category_id in poi.category_ids]
                start = _earliest_start(day, poi, arrival_base, return_buffer,
                                        meal_targets)
                if start is None:
                    reason = "opening_conflict" if poi.hours_known else "day_window_conflict"
                    excluded.append(Exclusion(poi.poi_id, day.day_id, reason))
                    continue

                party_cost = _party_cost(scenario, poi)
                if scenario.budget is not None and party_cost is not None:
                    # The budget is cumulative over the *whole* trip, so the
                    # candidate must be checked against prior days' known cost
                    # *and* the stops already placed on the current day. Omitting
                    # the in-progress day let a day silently exceed the budget
                    # (e.g. two 60-per-party stops under a 100 budget produced a
                    # 120 `partial` plan although a single valid stop exists).
                    committed = _known_cost_sum(days_out) + _known_stop_cost(day_stops)
                    if committed + party_cost > scenario.budget.amount:
                        excluded.append(Exclusion(poi.poi_id, day.day_id, "budget_exceeded"))
                        continue

                any_feasible_seen = True
                chosen = (poi, travel_minutes, travel_distance, start, party_cost)
                break

            if chosen is None:
                break

            poi, travel_minutes, travel_distance, start, party_cost = chosen
            departure = start + poi.visit_minutes
            if poi.cost is None:
                unknown.append(f"cost_unknown:{poi.poi_id}")
            if not poi.hours_known:
                unknown.append(f"hours_unknown:{poi.poi_id}")

            day_stops.append(PlannedStop(
                poi_id=poi.poi_id,
                arrival=start,
                departure=departure,
                visit_minutes=poi.visit_minutes,
                travel_from_prev_minutes=travel_minutes,
                travel_from_prev_distance_km=travel_distance,
                cost_party=party_cost,
                cost_currency=(poi.cost.currency if poi.cost else None),
            ))
            used.add(poi.poi_id)
            origin = poi.poi_id
            current_time = departure
            outstanding_required -= set(poi.category_ids)

        days_out.append(PlannedDay(day_id=day.day_id, stops=tuple(day_stops)))

    _enforce_return(scenario, days_out, unknown, notes)

    total_stops = sum(len(d.stops) for d in days_out)
    if total_stops == 0:
        reason = _classify_no_plan(candidates, excluded, iteration_limit_hit,
                                   any_feasible_seen)
        return _finalize_no_plan(scenario, reason, excluded, unknown, notes, iterations)

    sequence: List[str] = []
    total_travel = 0
    total_distance = Decimal(0)
    total_cost = Decimal(0)
    total_cost_known = True
    for day in days_out:
        for stop in day.stops:
            sequence.append(stop.poi_id)
            if stop.travel_from_prev_minutes is not None:
                total_travel += stop.travel_from_prev_minutes
            if stop.travel_from_prev_distance_km is not None:
                total_distance += stop.travel_from_prev_distance_km
            if stop.cost_party is None:
                total_cost_known = False
            else:
                total_cost += stop.cost_party

    if scenario.end_depot_id is not None and sequence:
        last = sequence[-1]
        if last != scenario.end_depot_id:
            return_edge = scenario.route(last, scenario.end_depot_id)
            if return_edge is not None:
                total_travel += return_edge.duration_minutes
                total_distance += return_edge.distance_km

    plan = Plan(
        scenario_id=scenario.scenario_id,
        status="unverifiable",
        no_plan_reason=None,
        days=tuple(days_out),
        sequence=tuple(sequence),
        total_cost_party=(total_cost if total_cost_known else None),
        total_cost_currency=(scenario.currency if total_cost_known else None),
        total_travel_minutes=total_travel,
        total_distance_km=total_distance,
        excluded=tuple(excluded),
        unsatisfied_required=tuple(),
        unknown_reasons=tuple(sorted(set(unknown))),
        iterations=iterations,
        notes=tuple(notes),
    )
    report = validator.validate(scenario, plan)
    return replace(plan, status=report.status,
                   unsatisfied_required=report.unsatisfied_required,
                   unknown_reasons=report.unknown_reasons)


def _known_stop_cost(stops) -> Decimal:
    """Exact sum of known party costs over an iterable of stops.

    Unknown costs (``cost_party is None``) are skipped, never treated as zero:
    the subtotal is a lower bound and the caller records the unknown separately.
    """
    total = Decimal(0)
    for stop in stops:
        if stop.cost_party is not None:
            total += stop.cost_party
    return total


def _known_cost_sum(days_out: List[PlannedDay]) -> Decimal:
    return sum((_known_stop_cost(day.stops) for day in days_out), Decimal(0))
