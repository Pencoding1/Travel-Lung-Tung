"""Pure deterministic itinerary planning bounded by an independent validator.

Public surface:

* :func:`domains.planning.contracts.parse_scenario` — strict input parsing.
* :func:`domains.planning.scheduler.schedule` — bounded deterministic heuristic.
* :func:`domains.planning.validator.validate` — independent re-verification.

This package is stdlib-only and imports no provider, database, graph or network
code. It is not yet wired into ``main.py`` (see
``docs/project/handoffs/OC-010/report.md`` for the integration contract).
"""

from domains.planning.contracts import (
    MAX_DAYS,
    MAX_ITERATIONS,
    MAX_POIS,
    MAX_PARTY_SIZE,
    Cost,
    Day,
    Exclusion,
    MealWindow,
    OpeningWindow,
    Plan,
    PlannedDay,
    PlannedStop,
    Poi,
    RouteEdge,
    Scenario,
    ScenarioError,
    ValidationReport,
    Violation,
    ceil_minutes_from_seconds,
    format_instant,
    parse_instant,
    parse_scenario,
)
from domains.planning.scheduler import schedule
from domains.planning.validator import validate

__all__ = [
    "MAX_DAYS",
    "MAX_ITERATIONS",
    "MAX_POIS",
    "MAX_PARTY_SIZE",
    "Cost",
    "Day",
    "Exclusion",
    "MealWindow",
    "OpeningWindow",
    "Plan",
    "PlannedDay",
    "PlannedStop",
    "Poi",
    "RouteEdge",
    "Scenario",
    "ScenarioError",
    "ValidationReport",
    "Violation",
    "ceil_minutes_from_seconds",
    "format_instant",
    "parse_instant",
    "parse_scenario",
    "schedule",
    "validate",
]
