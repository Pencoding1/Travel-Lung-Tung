"""Typed input/output contracts for the OC-010 deterministic planner.

This module is **pure** and **stdlib-only**: it imports nothing from the AI
provider stack, no database driver, no graph or network client, and no POI
source. The scheduler (:mod:`domains.planning.scheduler`) and the independent
validator (:mod:`domains.planning.validator`) both depend only on the typed
objects below.

Design rules (see ``docs/decisions/008-deterministic-planning.md``):

* Times are integer **minutes since the Unix epoch (UTC)**. Input instants must
  be timezone-aware ISO-8601 strings at minute resolution; naive, second- or
  microsecond-bearing, non-finite or empty values are rejected. Integer minutes
  mean route sums are exact and never silently rounded.
* Money and distance are exact :class:`decimal.Decimal` values. They are
  accepted only as integers or decimal strings; ``float``/``bool`` inputs are
  rejected so binary floating point can never introduce a rounded route sum.
* A missing opening-hours entry is ``hours_known = False``; a missing cost is
  ``cost = None``. Both are *unknown*, never zero. A legitimate free price is an
  explicit ``"0"`` amount with a currency and unit.
* Route edges are directed and carry a transport mode and provenance. A missing
  edge is unknown; it is never substituted with zero or a Haversine estimate.
* Stable ids are required: POI ids, category ids, day ids and the scenario id
  are all nonblank strings supplied by the caller. Coordinates/names are never
  accepted, so no factual field can be synthesized here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

# ---------------------------------------------------------------------------
# Bounds. Exceeding any bound is a hard rejection (never a silent truncation).
# ---------------------------------------------------------------------------
MAX_PARTY_SIZE = 50
MAX_DAYS = 14
MAX_POIS = 200
MAX_ROUTE_EDGES = 200 * 200
MAX_ITERATIONS = 100_000
MAX_REQUIRED_CATEGORIES = 32
MAX_MEAL_WINDOWS_PER_DAY = 8
MAX_MINIMUM_STOPS = MAX_POIS

ALLOWED_COST_UNITS = ("per_person", "per_party")

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class ScenarioError(ValueError):
    """Structured rejection of a malformed scenario input.

    ``code`` is a stable machine-readable string, ``field`` points at the JSON
    path and ``detail`` explains the failure. The scheduler never sees an
    invalid scenario.
    """

    __slots__ = ("code", "field", "detail")

    def __init__(self, code: str, field: str, detail: str):
        super().__init__(f"{code}: {field}: {detail}")
        self.code = code
        self.field = field
        self.detail = detail


# ---------------------------------------------------------------------------
# Primitive coercion helpers
# ---------------------------------------------------------------------------
def _fail(code: str, field: str, detail: str) -> "ScenarioError":
    return ScenarioError(code, field, detail)


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise _fail("not_an_object", field, "expected a JSON object")
    return value


def _require_list(value: Any, field: str) -> List[Any]:
    if not isinstance(value, list):
        raise _fail("invalid_type", field, "expected a JSON array")
    return value


def _nonblank_str(value: Any, field: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str) or not value.strip():
        raise _fail("invalid_type", field, "expected a nonblank string")
    return value.strip()


def _require_int(value: Any, field: str, *, minimum: Optional[int] = None,
                 maximum: Optional[int] = None) -> int:
    """Strict integer: rejects ``bool`` and any ``float`` (even integral)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail("not_integer", field, "expected an integer (bools rejected)")
    if minimum is not None and value < minimum:
        raise _fail("negative" if minimum == 0 else "out_of_range", field,
                    f"must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise _fail("over_limit", field, f"must be <= {maximum}")
    return value


def _parse_decimal(value: Any, field: str, *, allow_zero: bool = True) -> Decimal:
    """Exact decimal from an integer or decimal string. Floats are rejected."""
    if isinstance(value, bool):
        raise _fail("not_finite", field, "bool is not a numeric amount")
    if isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise _fail("invalid_type", field, "empty decimal string")
        try:
            result = Decimal(text)
        except InvalidOperation:
            raise _fail("not_finite", field, "not a parsable decimal")
    else:
        raise _fail("not_finite", field,
                    "amounts must be integers or decimal strings, never float/bool")
    if not result.is_finite():
        raise _fail("not_finite", field, "NaN/Inf are not allowed")
    if result < 0:
        raise _fail("negative", field, "amounts must be nonnegative")
    if not allow_zero and result == 0:
        raise _fail("negative", field, "amount must be positive")
    return result


def parse_instant(value: Any, field: str) -> int:
    """Parse an ISO-8601 timezone-aware instant to epoch minutes (UTC)."""
    if isinstance(value, bool) or not isinstance(value, str) or not value.strip():
        raise _fail("invalid_type", field, "expected an ISO-8601 datetime string")
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise _fail("malformed_interval", field, "not an ISO-8601 datetime")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _fail("naive_datetime", field, "instant must include a UTC offset")
    if parsed.second != 0 or parsed.microsecond != 0:
        raise _fail("malformed_interval", field,
                    "instants must be minute-resolution (no seconds/microseconds)")
    delta: timedelta = parsed.astimezone(timezone.utc) - _EPOCH
    return int(delta.total_seconds()) // 60


def format_instant(minutes: int) -> str:
    """Render epoch minutes back to a UTC ISO-8601 string."""
    return (_EPOCH + timedelta(minutes=minutes)).isoformat()


def ceil_minutes_from_seconds(seconds: int) -> int:
    """Round a raw provider duration **up** to whole minutes.

    The planner works in integer minutes. A route provider (e.g. GraphHopper)
    returns seconds, which are almost never a whole number of minutes. Rounding
    down would under-state travel and could admit an infeasible visit, so the
    only permitted conversion is round-up. Integration code must call this and
    disclose the rounding; the raw seconds are preserved on the route edge for
    provenance.
    """
    if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds < 0:
        raise ScenarioError("invalid_type", "raw_duration_seconds",
                            "raw seconds must be a nonnegative integer")
    return (seconds + 59) // 60


def _instant_local_date(value: Any, field: str) -> str:
    """Local calendar date of a timezone-aware instant (its own offset)."""
    if isinstance(value, bool) or not isinstance(value, str) or not value.strip():
        raise _fail("invalid_type", field, "expected an ISO-8601 datetime string")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise _fail("malformed_interval", field, "not an ISO-8601 datetime")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _fail("naive_datetime", field, "instant must include a UTC offset")
    return parsed.date().isoformat()


# ---------------------------------------------------------------------------
# Typed contract objects
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Cost:
    amount: Decimal
    currency: str
    unit: str

    def party_total(self, party_size: int) -> Decimal:
        """Exact party cost. ``per_person`` multiplies, ``per_party`` does not."""
        if self.unit == "per_person":
            return self.amount * party_size
        return self.amount


@dataclass(frozen=True)
class OpeningWindow:
    day_id: str
    start: int  # epoch minutes
    end: int    # epoch minutes


@dataclass(frozen=True)
class Poi:
    poi_id: str
    category_ids: Tuple[str, ...]
    visit_minutes: int
    cost: Optional[Cost]
    opening_windows: Tuple[OpeningWindow, ...]

    @property
    def hours_known(self) -> bool:
        return len(self.opening_windows) > 0

    def windows_for(self, day_id: str) -> Tuple[OpeningWindow, ...]:
        return tuple(w for w in self.opening_windows if w.day_id == day_id)


@dataclass(frozen=True)
class MealWindow:
    category_id: str
    start: int
    end: int


@dataclass(frozen=True)
class Day:
    day_id: str
    date: str
    start: int
    end: int
    meal_windows: Tuple[MealWindow, ...]
    max_stops: Optional[int]


@dataclass(frozen=True)
class RouteEdge:
    from_poi_id: str
    to_poi_id: str
    duration_minutes: int
    distance_km: Decimal
    transport_mode: str
    provenance: str
    raw_duration_seconds: Optional[int] = None
    raw_distance_meters: Optional[int] = None


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    seed: int
    currency: str
    party_size: int
    budget: Optional[Cost]
    days: Tuple[Day, ...]
    pois: Tuple[Poi, ...]
    route_index: Mapping[Tuple[str, str], RouteEdge]
    start_depot_id: Optional[str]
    end_depot_id: Optional[str]
    minimum_stops: Optional[int]
    allow_duplicate_pois: bool
    preferences: Mapping[str, int]
    required_categories: Tuple[str, ...]
    max_iterations: int

    def poi(self, poi_id: str) -> Optional[Poi]:
        for entry in self.pois:
            if entry.poi_id == poi_id:
                return entry
        return None

    def route(self, from_poi_id: str, to_poi_id: str) -> Optional[RouteEdge]:
        return self.route_index.get((from_poi_id, to_poi_id))


# ---------------------------------------------------------------------------
# Output contract objects
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PlannedStop:
    poi_id: str
    arrival: int
    departure: int
    visit_minutes: int
    travel_from_prev_minutes: Optional[int]
    travel_from_prev_distance_km: Optional[Decimal]
    cost_party: Optional[Decimal]
    cost_currency: Optional[str]
    is_depot: bool = False


@dataclass(frozen=True)
class PlannedDay:
    day_id: str
    stops: Tuple[PlannedStop, ...]


@dataclass(frozen=True)
class Exclusion:
    poi_id: str
    day_id: Optional[str]
    reason: str


@dataclass(frozen=True)
class Plan:
    """Scheduler output.

    ``status`` is always provisional and is finalized by the independent
    validator; the scheduler copies the validator's verdict when it reports.
    """

    scenario_id: str
    status: str
    no_plan_reason: Optional[str]
    days: Tuple[PlannedDay, ...]
    sequence: Tuple[str, ...]
    total_cost_party: Optional[Decimal]
    total_cost_currency: Optional[str]
    total_travel_minutes: int
    total_distance_km: Optional[Decimal]
    excluded: Tuple[Exclusion, ...]
    unsatisfied_required: Tuple[str, ...]
    unknown_reasons: Tuple[str, ...]
    iterations: int
    notes: Tuple[str, ...]


@dataclass(frozen=True)
class Violation:
    code: str
    day_id: Optional[str]
    poi_id: Optional[str]
    detail: str


@dataclass(frozen=True)
class ValidationReport:
    scenario_id: str
    status: str
    no_plan_reason: Optional[str]
    known_violations: Tuple[Violation, ...]
    unknown_reasons: Tuple[str, ...]
    unsatisfied_required: Tuple[str, ...]
    recomputed_total_cost_party: Optional[Decimal]
    recomputed_total_travel_minutes: int
    recomputed_total_distance_km: Optional[Decimal]
    stop_count: int
    checks: Mapping[str, int]


# ---------------------------------------------------------------------------
# Scenario parsing / validation
# ---------------------------------------------------------------------------
def _parse_cost(value: Any, field: str, currency: str, *, budget: bool) -> Cost:
    data = _require_mapping(value, field)
    amount = _parse_decimal(data.get("amount"), f"{field}.amount")
    raw_currency = data.get("currency")
    cost_currency = _nonblank_str(raw_currency, f"{field}.currency")
    if cost_currency != currency:
        raise _fail("currency_mismatch", f"{field}.currency",
                    f"'{cost_currency}' does not match scenario currency '{currency}'")
    if budget:
        unit = "per_party"
        supplied = data.get("unit", unit)
        if supplied != unit:
            raise _fail("unit_mismatch", f"{field}.unit",
                        "trip budget must be declared per_party")
    else:
        unit = _nonblank_str(data.get("unit"), f"{field}.unit")
        if unit not in ALLOWED_COST_UNITS:
            raise _fail("unit_mismatch", f"{field}.unit",
                        f"unit must be one of {ALLOWED_COST_UNITS}")
    return Cost(amount=amount, currency=cost_currency, unit=unit)


def _parse_poi(raw: Any, index: int, scenario_currency: str) -> Poi:
    field = f"pois[{index}]"
    data = _require_mapping(raw, field)
    poi_id = _nonblank_str(data.get("poi_id"), f"{field}.poi_id")

    raw_categories = _require_list(data.get("category_ids"), f"{field}.category_ids")
    categories: List[str] = []
    for offset, category in enumerate(raw_categories):
        cid = _nonblank_str(category, f"{field}.category_ids[{offset}]")
        if cid not in categories:
            categories.append(cid)
    if not categories:
        raise _fail("empty", f"{field}.category_ids", "at least one category id required")

    visit_minutes = _require_int(data.get("visit_minutes"), f"{field}.visit_minutes",
                                 minimum=1, maximum=24 * 60)

    cost: Optional[Cost] = None
    if data.get("cost") is not None:
        cost = _parse_cost(data["cost"], f"{field}.cost", scenario_currency, budget=False)

    windows: List[OpeningWindow] = []
    if data.get("opening_windows") is not None:
        raw_windows = _require_list(data["opening_windows"], f"{field}.opening_windows")
        for offset, window in enumerate(raw_windows):
            wfield = f"{field}.opening_windows[{offset}]"
            wdata = _require_mapping(window, wfield)
            day_id = _nonblank_str(wdata.get("day_id"), f"{wfield}.day_id")
            start = parse_instant(wdata.get("start"), f"{wfield}.start")
            end = parse_instant(wdata.get("end"), f"{wfield}.end")
            if start >= end:
                raise _fail("malformed_interval", wfield, "window start >= end")
            windows.append(OpeningWindow(day_id=day_id, start=start, end=end))

    return Poi(poi_id=poi_id, category_ids=tuple(categories),
               visit_minutes=visit_minutes, cost=cost,
               opening_windows=tuple(windows))


def _parse_day(raw: Any, index: int, known_poi_ids: Iterable[str]) -> Day:
    field = f"days[{index}]"
    data = _require_mapping(raw, field)
    day_id = _nonblank_str(data.get("day_id"), f"{field}.day_id")
    date = _nonblank_str(data.get("date"), f"{field}.date")
    window = _require_mapping(data.get("window"), f"{field}.window")
    start = parse_instant(window.get("start"), f"{field}.window.start")
    end = parse_instant(window.get("end"), f"{field}.window.end")
    if start >= end:
        raise _fail("malformed_interval", f"{field}.window", "day start >= end")
    if _instant_local_date(window.get("start"), f"{field}.window.start") != date:
        raise _fail("date_window_mismatch", f"{field}.date",
                    "declared date does not match the day window start date")

    meals: List[MealWindow] = []
    if data.get("meal_windows") is not None:
        raw_meals = _require_list(data["meal_windows"], f"{field}.meal_windows")
        if len(raw_meals) > MAX_MEAL_WINDOWS_PER_DAY:
            raise _fail("over_limit", f"{field}.meal_windows",
                        f"at most {MAX_MEAL_WINDOWS_PER_DAY} meal windows per day")
        for offset, meal in enumerate(raw_meals):
            mfield = f"{field}.meal_windows[{offset}]"
            mdata = _require_mapping(meal, mfield)
            category_id = _nonblank_str(mdata.get("category_id"), f"{mfield}.category_id")
            m_start = parse_instant(mdata.get("start"), f"{mfield}.start")
            m_end = parse_instant(mdata.get("end"), f"{mfield}.end")
            if m_start >= m_end:
                raise _fail("malformed_interval", mfield, "meal window start >= end")
            if m_start < start or m_end > end:
                raise _fail("malformed_interval", mfield,
                            "meal window must lie inside the day window")
            meals.append(MealWindow(category_id=category_id, start=m_start, end=m_end))

    max_stops: Optional[int] = None
    if data.get("max_stops") is not None:
        max_stops = _require_int(data["max_stops"], f"{field}.max_stops", minimum=0)
    return Day(day_id=day_id, date=date, start=start, end=end,
               meal_windows=tuple(meals), max_stops=max_stops)


def _parse_route(raw: Any, index: int) -> RouteEdge:
    field = f"route_edges[{index}]"
    data = _require_mapping(raw, field)
    from_id = _nonblank_str(data.get("from_poi_id"), f"{field}.from_poi_id")
    to_id = _nonblank_str(data.get("to_poi_id"), f"{field}.to_poi_id")

    raw_seconds: Optional[int] = None
    if data.get("raw_duration_seconds") is not None:
        raw_seconds = _require_int(data["raw_duration_seconds"],
                                   f"{field}.raw_duration_seconds", minimum=0)
    derived_minutes = ceil_minutes_from_seconds(raw_seconds) if raw_seconds is not None else None
    if data.get("duration_minutes") is not None:
        duration = _require_int(data["duration_minutes"], f"{field}.duration_minutes",
                                minimum=0)
        if derived_minutes is not None and duration != derived_minutes:
            raise _fail("duration_rounding_mismatch", f"{field}.duration_minutes",
                        f"must equal ceil(raw_duration_seconds/60) = {derived_minutes}")
    elif derived_minutes is not None:
        duration = derived_minutes
    else:
        raise _fail("missing_field", f"{field}",
                    "provide duration_minutes or raw_duration_seconds")

    distance = _parse_decimal(data.get("distance_km"), f"{field}.distance_km")
    raw_meters: Optional[int] = None
    if data.get("raw_distance_meters") is not None:
        raw_meters = _require_int(data["raw_distance_meters"],
                                  f"{field}.raw_distance_meters", minimum=0)
        if distance * 1000 != raw_meters:
            raise _fail("distance_mismatch", f"{field}.raw_distance_meters",
                        "distance_km * 1000 must equal raw_distance_meters")
    mode = _nonblank_str(data.get("transport_mode"), f"{field}.transport_mode")
    provenance = _nonblank_str(data.get("provenance"), f"{field}.provenance")
    return RouteEdge(from_poi_id=from_id, to_poi_id=to_id,
                     duration_minutes=duration, distance_km=distance,
                     transport_mode=mode, provenance=provenance,
                     raw_duration_seconds=raw_seconds,
                     raw_distance_meters=raw_meters)


def parse_scenario(raw: Any) -> Scenario:
    """Validate a raw scenario mapping into a typed :class:`Scenario`.

    Raises :class:`ScenarioError` with a stable ``code`` on any malformed,
    duplicated, non-finite or over-limit input. Nothing is silently truncated.
    """
    data = _require_mapping(raw, "scenario")
    scenario_id = _nonblank_str(data.get("scenario_id"), "scenario_id")
    seed = _require_int(data.get("seed", 0), "seed", minimum=0)
    currency = _nonblank_str(data.get("currency"), "currency")
    party_size = _require_int(data.get("party_size"), "party_size",
                              minimum=1, maximum=MAX_PARTY_SIZE)

    budget: Optional[Cost] = None
    if data.get("budget") is not None:
        budget = _parse_cost(data["budget"], "budget", currency, budget=True)

    raw_pois = _require_list(data.get("pois"), "pois")
    if len(raw_pois) > MAX_POIS:
        raise _fail("over_limit", "pois", f"at most {MAX_POIS} POIs")
    pois: List[Poi] = []
    seen_pois = set()
    for index, entry in enumerate(raw_pois):
        poi = _parse_poi(entry, index, currency)
        if poi.poi_id in seen_pois:
            raise _fail("duplicate", f"pois[{index}].poi_id",
                        f"duplicate poi_id '{poi.poi_id}'")
        seen_pois.add(poi.poi_id)
        pois.append(poi)

    raw_days = _require_list(data.get("days"), "days")
    if len(raw_days) > MAX_DAYS:
        raise _fail("over_limit", "days", f"at most {MAX_DAYS} days")
    if not raw_days:
        raise _fail("empty", "days", "at least one day is required")
    days: List[Day] = []
    seen_days = set()
    for index, entry in enumerate(raw_days):
        day = _parse_day(entry, index, seen_pois)
        if day.day_id in seen_days:
            raise _fail("duplicate", f"days[{index}].day_id",
                        f"duplicate day_id '{day.day_id}'")
        seen_days.add(day.day_id)
        days.append(day)

    for index in range(1, len(days)):
        if days[index].start < days[index - 1].end:
            raise _fail("malformed_interval", f"days[{index}].window",
                        "day windows must be chronological and non-overlapping")

    known_days = {day.day_id for day in days}
    for poi in pois:
        for window in poi.opening_windows:
            if window.day_id not in known_days:
                raise _fail("unknown_poi_reference", f"pois.{poi.poi_id}.opening_windows",
                            f"unknown day_id '{window.day_id}'")

    start_depot_id = data.get("start_depot_poi_id")
    if start_depot_id is not None:
        start_depot_id = _nonblank_str(start_depot_id, "start_depot_poi_id")
        if start_depot_id not in seen_pois:
            raise _fail("unknown_poi_reference", "start_depot_poi_id",
                        f"unknown poi_id '{start_depot_id}'")
    end_depot_id = data.get("end_depot_poi_id")
    if end_depot_id is not None:
        end_depot_id = _nonblank_str(end_depot_id, "end_depot_poi_id")
        if end_depot_id not in seen_pois:
            raise _fail("unknown_poi_reference", "end_depot_poi_id",
                        f"unknown poi_id '{end_depot_id}'")

    minimum_stops: Optional[int] = None
    if data.get("minimum_stops") is not None:
        minimum_stops = _require_int(data["minimum_stops"], "minimum_stops",
                                     minimum=0, maximum=MAX_MINIMUM_STOPS)

    allow_duplicate_pois = data.get("allow_duplicate_pois", False)
    if not isinstance(allow_duplicate_pois, bool):
        raise _fail("invalid_type", "allow_duplicate_pois", "expected a boolean")

    preferences: Dict[str, int] = {}
    if data.get("preferences") is not None:
        prefs = _require_mapping(data["preferences"], "preferences")
        weights = _require_mapping(prefs.get("category_weights"), "preferences.category_weights")
        for category_id, weight in weights.items():
            cid = _nonblank_str(category_id, "preferences.category_weights.<key>")
            preferences[cid] = _require_int(
                weight, f"preferences.category_weights.{cid}", minimum=0)

    raw_required = data.get("required_categories", [])
    required = _require_list(raw_required, "required_categories")
    if len(required) > MAX_REQUIRED_CATEGORIES:
        raise _fail("over_limit", "required_categories",
                    f"at most {MAX_REQUIRED_CATEGORIES} required categories")
    required_categories: Tuple[str, ...] = tuple(
        _nonblank_str(value, f"required_categories[{i}]") for i, value in enumerate(required))

    raw_edges = _require_list(data.get("route_edges", []), "route_edges")
    if len(raw_edges) > MAX_ROUTE_EDGES:
        raise _fail("over_limit", "route_edges", f"at most {MAX_ROUTE_EDGES} edges")
    scenario_mode: Optional[str] = None
    if data.get("transport_mode") is not None:
        scenario_mode = _nonblank_str(data["transport_mode"], "transport_mode")
    route_index: Dict[Tuple[str, str], RouteEdge] = {}
    for index, entry in enumerate(raw_edges):
        edge = _parse_route(entry, index)
        if scenario_mode is not None and edge.transport_mode != scenario_mode:
            raise _fail("transport_mode_mismatch", f"route_edges[{index}].transport_mode",
                        f"scenario declares single mode '{scenario_mode}'")
        for endpoint in (edge.from_poi_id, edge.to_poi_id):
            if endpoint not in seen_pois:
                raise _fail("unknown_poi_reference", f"route_edges[{index}]",
                            f"unknown poi_id '{endpoint}'")
        key = (edge.from_poi_id, edge.to_poi_id)
        if key in route_index:
            raise _fail("duplicate", f"route_edges[{index}]",
                        f"duplicate directed edge {key}")
        route_index[key] = edge

    max_iterations = _require_int(data.get("max_iterations", MAX_ITERATIONS),
                                  "max_iterations", minimum=1,
                                  maximum=MAX_ITERATIONS)

    return Scenario(
        scenario_id=scenario_id,
        seed=seed,
        currency=currency,
        party_size=party_size,
        budget=budget,
        days=tuple(days),
        pois=tuple(pois),
        route_index=route_index,
        start_depot_id=start_depot_id,
        end_depot_id=end_depot_id,
        minimum_stops=minimum_stops,
        allow_duplicate_pois=allow_duplicate_pois,
        preferences=dict(preferences),
        required_categories=required_categories,
        max_iterations=max_iterations,
    )
