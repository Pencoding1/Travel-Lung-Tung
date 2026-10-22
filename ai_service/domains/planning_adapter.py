"""Integration adapter between verified grounding evidence and the OC-010 planner.

This module is the *only* place that turns live (MCP) evidence plus explicit
request constraints into a typed :class:`domains.planning.contracts.Scenario`,
collects directed route evidence from the real ``get_itinerary_route`` tool, and
maps the planner's verdict back into a JSON-safe summary for the
``/generate_itinerary`` reply.

Design rules (ADR 011, superset of ADR 008 §5):

* **No invented facts.** A route edge is built only from an actual
  ``get_itinerary_route`` response for that exact directed pair. A missing or
  failed pair stays *unknown*: it is never replaced by ``0`` or a Haversine
  estimate and never defaulted.
* **No repurposed prices.** A ``get_poi_details`` menu/offer price is *not* an
  admission/visit cost. This adapter never promotes an offer price or the
  model's stop ``budget`` into a source cost. The current tool exposes no
  explicit planning cost, so POI cost stays ``None`` (unknown) until such a
  field exists (documented in ADR 011).
* **Narrow, disclosed parsing.** Opening hours are parsed only for an explicit
  ``24/7`` token or a single daily ``HH:MM-HH:MM`` range. Any complex,
  weekday-dependent, holiday or ambiguous string is *unsupported* and the POI's
  hours stay unknown (\u2260 "always open"). Original text and parser status are
  retained. Dates are interpreted in Vietnam time (UTC+07:00).
* **Explicit constraints, disclosed assumptions.** Request constraints are typed
  and validated. When a day window or visit duration is not supplied by the
  source or the user, the adapter records an explicit *planning assumption*
  separate from any POI fact.
* **Bounded route collection.** The directed pair pool is explicit and capped;
  every attempted pair/status/provenance is recorded and incomplete coverage is
  disclosed. No unbounded retry.

The module performs no network, database, graph or model call itself; it calls
an injected async ``call_tool`` (the existing MCP session) for route evidence.
"""

from __future__ import annotations

import asyncio
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple

from domains import grounding
from domains.planning.contracts import (
    Scenario,
    ScenarioError,
    ceil_minutes_from_seconds,
    parse_instant,
    parse_scenario,
)

VN_TZ = timezone(timedelta(hours=7))

# --- Disclosed planning assumptions (never presented as POI facts) ---------
DEFAULT_VISIT_MINUTES = 60
DEFAULT_VISIT_POLICY = (
    "assumed_uniform_visit_minutes; get_poi_details exposes no visit duration")
DEFAULT_DAY_WINDOW = ("09:00", "18:00")
DEFAULT_DAY_WINDOW_POLICY = (
    "assumed_default_day_window; no explicit user day window supplied")
DEFAULT_CURRENCY = "VND"

# --- Bounded route collection ----------------------------------------------
MAX_ROUTE_PAIRS = 60
MAX_ROUTE_CONCURRENCY = 4
ROUTE_CALL_TIMEOUT_SECONDS = 15.0
ROUTE_PROVENANCE = "get_itinerary_route:mcp:car"
ROUTE_CAP_REASON = "route_pair_cap:max_route_pairs_exceeded"

# Route coverage is reported for two *different* questions. The candidate pool
# question ("did we attempt the whole capped pool?") never proves that the
# delivered schedule is routable; the selected-plan question ("is every actual
# scheduled leg backed by an actual successful edge?") does. CORE-071 keeps them
# separate so a known selected leg is never called unverifiable only because
# unrelated candidate pairs were never attempted.
CANDIDATE_POOL_COVERAGE_SCOPE = "candidate_pool"
SELECTED_PLAN_COVERAGE_SCOPE = "selected_plan"

# --- Single transport mode (request -> route tool -> scenario -> response) --
TRANSPORT_MODES = ("car", "foot")
DEFAULT_TRANSPORT_MODE = "car"
INVALID_TRANSPORT_MODE = "invalid_transport_mode: expected 'car' or 'foot'"
ROUTE_PROFILE_MISMATCH = "route_profile_mismatch"
ROUTE_PROFILE_MISMATCH_DETAIL = (
    "route profile does not match requested transport mode")


def request_transport_mode(request: Any) -> Tuple[Optional[str], str]:
    """Return ``(mode, source)`` for an explicit request object or mapping.

    ``source`` is ``"explicit"`` when the caller supplied the field and
    ``"default"`` when the backward-compatible ``car`` policy default applies.
    A present invalid value returns ``(None, source)``; it is never coerced.
    """
    if isinstance(request, dict):
        present = "transport_mode" in request
        raw = request.get("transport_mode")
    else:
        present = "transport_mode" in getattr(request, "model_fields_set", set())
        raw = getattr(request, "transport_mode", None)
    source = "explicit" if present else "default"
    if raw is None and not present:
        return DEFAULT_TRANSPORT_MODE, source
    if type(raw) is not str or raw not in TRANSPORT_MODES:
        return None, source
    return raw, source


def _require_transport_mode(mode: Any) -> str:
    """Fail closed before any route tool call with a constant ValueError."""
    if type(mode) is not str or mode not in TRANSPORT_MODES:
        raise ValueError(INVALID_TRANSPORT_MODE)
    return mode


def _route_provenance(mode: str) -> str:
    return f"get_itinerary_route:mcp:{mode}"


_COST_POLICY = {
    "status": "unknown",
    "reason": "get_poi_details exposes no explicit admission/visit cost; "
              "menu offer prices are not admission costs",
    "menu_offers_repurposed": False,
    "model_budget_promoted": False,
}
COST_POLICY = _COST_POLICY


class AdapterError(Exception):
    """Structured rejection while building the planning scenario."""

    __slots__ = ("code", "message")

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Request constraints
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BudgetConstraint:
    amount: Decimal
    currency: str
    unit: str  # normalized to per_party for the trip budget
    source: str  # "explicit_field" | "budget_range"


_SINGLE_AMOUNT_RE = re.compile(r"^\s*([0-9][0-9,._]*)\s*([A-Za-z]{3})\s*$")

# Budget parse outcomes split into two classes. An *explicit* malformed/incomplete
# typed field must fail validation (never silently degrade to "no budget"); an
# absent or legacy free-form/ambiguous ``budget_range`` stays a disclosed unknown.
FATAL_BUDGET_REASONS = frozenset({
    "budget_amount_requires_positive_amount_and_currency",
    "invalid_budget_unit",
    "per_person_budget_requires_party_size",
    "incomplete_budget_fields",
})
LEGACY_UNKNOWN_BUDGET_REASONS = frozenset({
    "no_budget_supplied",
    "ambiguous_or_unsupported_budget_range_not_parsed",
    "unparsable_budget_amount",
})


def budget_reason_is_fatal(reason: Optional[str]) -> bool:
    """True when a budget parse reason must fail closed (explicit malformed)."""
    return reason in FATAL_BUDGET_REASONS


def _decimal_amount(value: Any) -> Optional[Decimal]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("_", "")
        if not text:
            return None
        try:
            amount = Decimal(text)
        except InvalidOperation:
            return None
        return amount if amount.is_finite() and amount > 0 else None
    return None


def parse_budget_constraint(request: Any) -> Tuple[Optional[BudgetConstraint], Optional[str]]:
    """Return ``(constraint, rejection_reason)``.

    An explicit ``budget_amount`` + ``budget_currency`` field is trusted (with an
    optional ``budget_unit`` normalized to ``per_party`` using the party size).
    The free-form ``budget_range`` string is parsed *only* when it is a single
    unambiguous ``<amount> <CUR>`` token; ranges/ambiguity are rejected rather
    than guessed, and the legacy estimate stays separate.
    """
    def get(name):
        if isinstance(request, dict):
            return request.get(name)
        return getattr(request, name, None)

    explicit_amount = get("budget_amount")
    explicit_currency = grounding.nonblank_str(get("budget_currency"))
    explicit_unit = grounding.nonblank_str(get("budget_unit"))
    if explicit_amount is not None:
        amount = _decimal_amount(explicit_amount)
        if amount is None or explicit_currency is None:
            return None, "budget_amount_requires_positive_amount_and_currency"
        unit = explicit_unit or "per_party"
        if unit not in ("per_party", "per_person"):
            return None, "invalid_budget_unit"
        if unit == "per_person":
            party = get("num_travelers")
            if not isinstance(party, int) or isinstance(party, bool) or party < 1:
                return None, "per_person_budget_requires_party_size"
            amount = amount * party
            unit = "per_party"
        return BudgetConstraint(amount=amount, currency=explicit_currency,
                                unit=unit, source="explicit_field"), None

    # Currency/unit supplied *without* an amount is an incomplete explicit budget.
    if explicit_currency is not None or explicit_unit is not None:
        return None, "incomplete_budget_fields"

    raw = grounding.nonblank_str(get("budget_range"))
    if raw is None:
        return None, "no_budget_supplied"
    match = _SINGLE_AMOUNT_RE.match(raw)
    if match is None:
        return None, "ambiguous_or_unsupported_budget_range_not_parsed"
    amount = _decimal_amount(match.group(1))
    if amount is None:
        return None, "unparsable_budget_amount"
    return BudgetConstraint(amount=amount, currency=match.group(2).upper(),
                            unit="per_party", source="budget_range"), None


# ---------------------------------------------------------------------------
# Opening-hours policy (narrow, documented)
# ---------------------------------------------------------------------------
_DAILY_RANGE_RE = re.compile(
    r"^\s*(\d{1,2}):(\d{2})\s*[-\u2013\u2014~]\s*(\d{1,2}):(\d{2})\s*$")


@dataclass(frozen=True)
class HoursParse:
    original: Optional[str]
    status: str  # absent | always_open | daily_window | unsupported
    start_hm: Optional[str] = None
    end_hm: Optional[str] = None
    detail: Optional[str] = None


def parse_operation_time(value: Any) -> HoursParse:
    """Parse only a documented narrow hours format.

    Supported: an explicit ``24/7`` token (always open) or a single daily
    ``HH:MM-HH:MM`` range. Everything else (weekday lists, holidays, multiple
    ranges, overnight spans, month/seasonal text) is ``unsupported`` so hours
    stay unknown \u2014 never "always open". The original text is always retained.
    """
    raw = grounding.nonblank_str(value)
    if raw is None:
        return HoursParse(original=None, status="absent")
    folded = raw.strip().casefold()
    if folded in ("24/7", "24x7", "24\u00d77", "24/7 open", "always open",
                  "open 24/7", "open 24 hours", "24 hours"):
        return HoursParse(original=raw, status="always_open")
    match = _DAILY_RANGE_RE.match(raw)
    if match is not None:
        start_h, start_m, end_h, end_m = (int(part) for part in match.groups())
        if (0 <= start_h <= 23 and 0 <= end_h <= 23
                and 0 <= start_m <= 59 and 0 <= end_m <= 59
                and (end_h, end_m) > (start_h, start_m)):
            return HoursParse(original=raw, status="daily_window",
                              start_hm=f"{start_h:02d}:{start_m:02d}",
                              end_hm=f"{end_h:02d}:{end_m:02d}")
        return HoursParse(original=raw, status="unsupported",
                          detail="range is not a same-day ordered HH:MM-HH:MM span")
    return HoursParse(original=raw, status="unsupported",
                      detail="not a 24/7 token or a single daily HH:MM-HH:MM range")


# ---------------------------------------------------------------------------
# Route evidence collection
# ---------------------------------------------------------------------------
@dataclass
class RouteRecord:
    from_poi_id: str
    to_poi_id: str
    status: str  # success | failed
    code: Optional[str] = None
    detail: Optional[str] = None
    provenance: str = ROUTE_PROVENANCE
    duration_minutes: Optional[int] = None
    distance_km: Optional[str] = None
    raw_duration_seconds: Optional[int] = None
    raw_distance_meters: Optional[int] = None
    stops_mapped: Optional[int] = None
    transport_mode: str = DEFAULT_TRANSPORT_MODE
    # absent | matched | mismatch. ``absent`` is legacy compatibility and is
    # never presented as provider-confirmed mode evidence.
    profile_echo: Optional[str] = None
    # Actual provider GeoJSON LineString and turn-by-turn steps. These stay
    # private to the record: ``as_dict`` is the model/candidate-pool evidence
    # and must never carry huge polylines or prompt text.
    geometry: Optional[Dict[str, Any]] = None
    instructions: Optional[List[str]] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "from_poi_id": self.from_poi_id,
            "to_poi_id": self.to_poi_id,
            "status": self.status,
            "code": self.code,
            "detail": self.detail,
            "provenance": self.provenance,
            "transport_mode": self.transport_mode,
            "profile_echo": self.profile_echo,
            "duration_minutes": self.duration_minutes,
            "distance_km": self.distance_km,
            "raw_duration_seconds": self.raw_duration_seconds,
            "raw_distance_meters": self.raw_distance_meters,
            "stops_mapped": self.stops_mapped,
        }


@dataclass
class RouteEvidence:
    selected_pairs: List[Tuple[str, str]] = field(default_factory=list)
    attempted_pairs: List[Tuple[str, str]] = field(default_factory=list)
    skipped_pairs: List[Tuple[str, str]] = field(default_factory=list)
    records: List[RouteRecord] = field(default_factory=list)
    cap_reason: Optional[str] = None
    coverage: str = "empty"  # empty | complete | partial
    transport_mode: Optional[str] = None
    transport_mode_source: Optional[str] = None
    # --- bounded pair-selection provenance (CORE-071) ----------------------
    candidate_count: int = 0
    total_directed_pairs: int = 0
    origins_total: int = 0
    origins_attempted: List[str] = field(default_factory=list)
    # Validated model-proposal priority: exact candidate ids only, deduplicated.
    priority_sequence: List[str] = field(default_factory=list)
    # Pairs that the priority tiers actually claimed before the cap applied.
    priority_pairs: List[Tuple[str, str]] = field(default_factory=list)
    # Foreign/unknown/blank priority entries were dropped, never called.
    priority_ignored_count: int = 0

    def as_dict(self) -> Dict[str, Any]:
        succeeded = [r for r in self.records if r.status == "success"]
        failed = [r for r in self.records if r.status != "success"]
        return {
            "coverage_scope": CANDIDATE_POOL_COVERAGE_SCOPE,
            "transport_mode": self.transport_mode,
            "transport_mode_source": self.transport_mode_source,
            "selected_pairs": [list(p) for p in self.selected_pairs],
            "attempted_pairs": [list(p) for p in self.attempted_pairs],
            "skipped_pairs": [list(p) for p in self.skipped_pairs],
            "attempted": len(self.attempted_pairs),
            "succeeded": [(r.from_poi_id, r.to_poi_id) for r in succeeded],
            "failed": [{"pair": [r.from_poi_id, r.to_poi_id], "code": r.code,
                        "detail": r.detail} for r in failed],
            "coverage": self.coverage,
            "cap_reason": self.cap_reason,
            "candidate_count": self.candidate_count,
            "total_directed_pairs": self.total_directed_pairs,
            "origins_total": self.origins_total,
            "origins_attempted": list(self.origins_attempted),
            "priority_sequence": list(self.priority_sequence),
            "priority_pairs": [list(p) for p in self.priority_pairs],
            "priority_ignored_count": self.priority_ignored_count,
            "records": [r.as_dict() for r in self.records],
        }


def _directed_pairs(poi_ids: Sequence[str]) -> List[Tuple[str, str]]:
    return [(a, b) for a in poi_ids for b in poi_ids if a != b]


def _validated_route_priority(
        priority: Optional[Sequence[str]], ordered: Sequence[str]
) -> Tuple[List[str], int]:
    """Validate a model-proposal priority sequence against the candidate pool.

    Only exact, non-blank candidate ids survive; foreign/unknown entries are
    dropped (never ordered into a route call, so a supplied sequence can never
    widen the capped pool) and counted for honest metadata. Duplicates collapse
    silently while preserving first occurrence order.
    """
    if priority is None or isinstance(priority, (str, bytes)):
        return [], 0
    allowed = set(ordered)
    validated: List[str] = []
    seen: set = set()
    ignored = 0
    for raw in priority:
        if not isinstance(raw, str) or not raw.strip():
            ignored += 1
            continue
        if raw not in allowed:
            ignored += 1
            continue
        if raw in seen:
            continue
        seen.add(raw)
        validated.append(raw)
    return validated, ignored


def _prioritized_directed_pairs(
        ordered: Sequence[str], priority: Sequence[str], max_pairs: int
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    """Choose at most ``max_pairs`` directed pairs in three explicit tiers.

    1. the model proposal's consecutive legs, in proposal order;
    2. the reverse direction of those same legs (each direction is a real,
       separate route; nothing is mirrored or inferred);
    3. a deterministic balanced round-robin over *every* remaining origin so a
       lexicographic row prefix cannot starve later ids (CORE-071).

    Returns ``(selected_pairs, priority_pairs)`` where ``priority_pairs`` are
    the tier-1/tier-2 pairs that actually fit under the cap.
    """
    selected: List[Tuple[str, str]] = []
    priority_pairs: List[Tuple[str, str]] = []
    taken: set = set()

    def take(pair: Tuple[str, str], *, is_priority: bool) -> None:
        if len(selected) >= max_pairs:
            return
        a, b = pair
        if a == b or pair in taken:
            return
        taken.add(pair)
        selected.append(pair)
        if is_priority:
            priority_pairs.append(pair)

    priority_set = set(priority)
    legs = list(zip(priority, priority[1:]))
    for leg in legs:
        take(leg, is_priority=True)
    for a, b in legs:
        take((b, a), is_priority=True)

    tail = [pid for pid in ordered if pid not in priority_set]
    origins = list(priority) + tail
    target_order = list(priority) + tail
    for index in range(len(target_order)):
        for origin in origins:
            if len(selected) >= max_pairs:
                return selected, priority_pairs
            targets = [t for t in target_order if t != origin]
            if index < len(targets):
                take((origin, targets[index]), is_priority=False)
    return selected, priority_pairs


def _route_duration_fields(time_minutes: Any) -> Tuple[Optional[int], Optional[int]]:
    if isinstance(time_minutes, bool) or not isinstance(time_minutes, (int, float)):
        return None, None
    value = float(time_minutes)
    if not (value == value) or value in (float("inf"), float("-inf")) or value < 0:
        return None, None
    raw_seconds = int(round(value * 60.0))
    return raw_seconds, ceil_minutes_from_seconds(raw_seconds)


def _route_distance_fields(distance_km: Any) -> Tuple[Optional[str], Optional[int]]:
    if isinstance(distance_km, bool) or not isinstance(distance_km, (int, float)):
        return None, None
    value = float(distance_km)
    if not (value == value) or value in (float("inf"), float("-inf")) or value < 0:
        return None, None
    raw_meters = int(round(value * 1000.0))
    # Exact decimal string reconciling with the integer meter provenance.
    distance = (Decimal(raw_meters) / Decimal(1000)).normalize()
    return format(distance, "f"), raw_meters


def _route_profile_echo(data: Dict[str, Any], requested: str
                        ) -> Tuple[str, Optional[str]]:
    """Validate optional upstream ``vehicle``/``profile`` echoes.

    Returns ``(echo_status, mismatch_detail)``. Absence is accepted as legacy
    compatibility and reported as ``absent`` (never as observed confirmation).
    Any present field must be the exact requested mode; null, non-string,
    unsupported or contradictory values fail closed.
    """
    present = [name for name in ("vehicle", "profile") if name in data]
    if not present:
        return "absent", None
    for name in present:
        value = data.get(name)
        if type(value) is not str or value != requested:
            # Constant detail only: never interpolate the untrusted provider
            # value/name/repr into a user-visible or serialized error.
            return "mismatch", ROUTE_PROFILE_MISMATCH_DETAIL
    return "matched", None


MAX_ROUTE_GEOMETRY_POINTS = 20000
MAX_ROUTE_INSTRUCTIONS = 500
MAX_ROUTE_INSTRUCTION_CHARS = 500


def _validated_route_geometry(value: Any) -> Optional[Dict[str, Any]]:
    """Accept only a finite GeoJSON LineString; never fabricate a path."""
    if not isinstance(value, dict) or value.get("type") != "LineString":
        return None
    coordinates = value.get("coordinates")
    if not isinstance(coordinates, list) or not (
        2 <= len(coordinates) <= MAX_ROUTE_GEOMETRY_POINTS
    ):
        return None
    cleaned: List[List[float]] = []
    for position in coordinates:
        if not isinstance(position, (list, tuple)) or len(position) != 2:
            return None
        longitude, latitude = position
        if isinstance(longitude, bool) or isinstance(latitude, bool):
            return None
        if not isinstance(longitude, (int, float)) or not isinstance(latitude, (int, float)):
            return None
        longitude = float(longitude)
        latitude = float(latitude)
        if not math.isfinite(longitude) or not math.isfinite(latitude):
            return None
        if not (-180.0 <= longitude <= 180.0) or not (-90.0 <= latitude <= 90.0):
            return None
        cleaned.append([longitude, latitude])
    return {"type": "LineString", "coordinates": cleaned}


def _validated_route_instructions(value: Any) -> Optional[List[str]]:
    if not isinstance(value, list) or not value:
        return None
    kept: List[str] = []
    for item in value[:MAX_ROUTE_INSTRUCTIONS]:
        text = grounding.nonblank_str(item)
        if text is not None:
            kept.append(text[:MAX_ROUTE_INSTRUCTION_CHARS])
    return kept or None


def _parse_route_payload(a: str, b: str, outcome: grounding.ToolOutcome,
                         transport_mode: str
                         ) -> Tuple[Optional[Dict[str, Any]], RouteRecord]:
    provenance = _route_provenance(transport_mode)

    def _failed(code: Optional[str], detail: Optional[str],
                profile_echo: Optional[str] = None) -> Tuple[None, RouteRecord]:
        return None, RouteRecord(
            a, b, "failed", code=code, detail=detail, provenance=provenance,
            transport_mode=transport_mode, profile_echo=profile_echo)

    if not outcome.ok:
        return _failed(outcome.code, outcome.detail)
    data = outcome.data or {}
    if not isinstance(data, dict):
        return _failed("malformed_route", "route payload is not an object")
    if data.get("success") is False:
        return _failed("provider_error", "route tool reported success=false")

    profile_echo, profile_error = _route_profile_echo(data, transport_mode)
    if profile_error is not None:
        return _failed(ROUTE_PROFILE_MISMATCH, profile_error,
                       profile_echo="mismatch")

    raw_seconds, duration = _route_duration_fields(data.get("time_minutes"))
    distance_km, raw_meters = _route_distance_fields(data.get("distance_km"))
    if duration is None or distance_km is None:
        return _failed("malformed_route",
                       "missing/non-finite distance or time", profile_echo)

    stops_mapped = data.get("stops_mapped")
    if stops_mapped is not None and (isinstance(stops_mapped, bool)
                                     or not isinstance(stops_mapped, int)
                                     or stops_mapped != 2):
        return _failed("stops_mapped_mismatch",
                       f"expected 2 mapped stops, got {stops_mapped!r}",
                       profile_echo)

    # ``stops`` is optional upstream (absence = no ordered-id evidence). But if
    # the field is present it must be a well-formed non-empty list of stop
    # objects with nonblank ids: an empty/malformed present field is a malformed
    # binding, not an absence of identities.
    if "stops" in data:
        stops = data.get("stops")
        if not isinstance(stops, list) or not stops:
            return _failed("malformed_stops",
                           "stops present but not a non-empty list", profile_echo)
        returned_ids: List[str] = []
        for stop in stops:
            if not isinstance(stop, dict):
                return _failed("malformed_stops",
                               "stops entry is not an object", profile_echo)
            stop_id = grounding.nonblank_str(stop.get("id"))
            if stop_id is None:
                return _failed("malformed_stops",
                               "stops entry is missing a nonblank id",
                               profile_echo)
            returned_ids.append(stop_id)
        if returned_ids != [a, b]:
            return _failed(
                "ordered_ids_mismatch",
                f"tool returned ordered ids {returned_ids!r} != [{a!r}, {b!r}]",
                profile_echo)

    edge = {
        "from_poi_id": a,
        "to_poi_id": b,
        "raw_duration_seconds": raw_seconds,
        "duration_minutes": duration,
        "distance_km": distance_km,
        "raw_distance_meters": raw_meters,
        "transport_mode": transport_mode,
        # The POI route tool is not required to echo a profile; this metadata
        # states only that the mode came from the request, never that the
        # provider confirmed it.
        "transport_mode_source": "request",
        "profile_echo": profile_echo,
        "provenance": provenance,
    }
    record = RouteRecord(a, b, "success", duration_minutes=duration,
                         distance_km=distance_km,
                         raw_duration_seconds=raw_seconds,
                         raw_distance_meters=raw_meters,
                         stops_mapped=stops_mapped,
                         provenance=provenance,
                         transport_mode=transport_mode,
                         profile_echo=profile_echo,
                         geometry=_validated_route_geometry(
                             data.get("route_geometry")),
                         instructions=_validated_route_instructions(
                             data.get("turn_by_turn")))
    return edge, record


async def collect_route_edges(
    call_tool: Callable[[str, Dict[str, Any]], Awaitable[Any]],
    poi_ids: Sequence[str],
    *,
    transport_mode: str = "car",
    max_pairs: int = MAX_ROUTE_PAIRS,
    concurrency: int = MAX_ROUTE_CONCURRENCY,
    timeout: float = ROUTE_CALL_TIMEOUT_SECONDS,
    priority_sequence: Optional[Sequence[str]] = None,
) -> Tuple[List[Dict[str, Any]], RouteEvidence]:
    """Collect directed route edges for the explicit, capped candidate pool.

    ``priority_sequence`` is an optional *validated preference hint* (the actual
    grounded model proposal order). It only reorders which directed pairs are
    attempted first; it never adds call targets outside ``poi_ids``, never
    changes the cap and never invents an edge. When the pool fits under the cap
    the legacy behaviour is unchanged: every directed pair is attempted.
    """
    mode = _require_transport_mode(transport_mode)
    ordered = sorted({pid for pid in poi_ids if isinstance(pid, str) and pid.strip()})
    evidence = RouteEvidence(transport_mode=mode, transport_mode_source="request")
    evidence.candidate_count = len(ordered)
    evidence.origins_total = len(ordered)
    if len(ordered) < 2:
        evidence.coverage = "empty"
        return [], evidence

    priority, ignored = _validated_route_priority(priority_sequence, ordered)
    evidence.priority_sequence = priority
    evidence.priority_ignored_count = ignored

    all_pairs = _directed_pairs(ordered)
    evidence.total_directed_pairs = len(all_pairs)
    if len(all_pairs) > max_pairs:
        evidence.selected_pairs, evidence.priority_pairs = _prioritized_directed_pairs(
            ordered, priority, max_pairs)
        chosen = set(evidence.selected_pairs)
        evidence.skipped_pairs = [pair for pair in all_pairs if pair not in chosen]
        evidence.cap_reason = ROUTE_CAP_REASON
    else:
        evidence.selected_pairs = all_pairs

    semaphore = asyncio.Semaphore(max(1, concurrency))
    edges: List[Dict[str, Any]] = []

    async def _attempt(a: str, b: str) -> None:
        async with semaphore:
            try:
                raw = await asyncio.wait_for(
                    call_tool("get_itinerary_route",
                              {"ordered_poi_ids": [a, b], "vehicle": transport_mode}),
                    timeout=timeout)
                outcome = grounding.parse_mcp_tool_result(raw)
            except asyncio.TimeoutError:
                evidence.records.append(RouteRecord(
                    a, b, "failed", code="route_timeout",
                    detail=f"no response within {timeout}s",
                    provenance=_route_provenance(mode), transport_mode=mode))
                return
            except Exception as exc:  # noqa: BLE001 - record, never propagate
                evidence.records.append(RouteRecord(
                    a, b, "failed", code="route_transport_error",
                    detail=type(exc).__name__,
                    provenance=_route_provenance(mode), transport_mode=mode))
                return
            edge, record = _parse_route_payload(a, b, outcome, mode)
            evidence.records.append(record)
            if edge is not None:
                edges.append(edge)

    tasks = [_attempt(a, b) for (a, b) in evidence.selected_pairs]
    if tasks:
        await asyncio.gather(*tasks)

    evidence.attempted_pairs = list(evidence.selected_pairs)
    evidence.origins_attempted = sorted({a for (a, _b) in evidence.attempted_pairs})
    edge_keys = {(e["from_poi_id"], e["to_poi_id"]) for e in edges}
    if evidence.skipped_pairs:
        evidence.coverage = "partial"
    elif len(edge_keys) == len(evidence.selected_pairs):
        evidence.coverage = "complete"
    else:
        evidence.coverage = "partial"
    return edges, evidence


def _required_day_legs(
        day_ids: Sequence[str], *, start_depot_id: Optional[str],
        end_depot_id: Optional[str]) -> List[Tuple[str, str]]:
    """Directed legs of one actual scheduled day, in chronological order.

    A day's legs are its declared start-depot leg, its within-day adjacent
    pairs and its declared end-depot leg. Days never contribute a leg to
    another day, so no cross-day edge is invented.
    """
    ids = [pid for pid in day_ids if isinstance(pid, str) and pid.strip()]
    legs: List[Tuple[str, str]] = []
    seen: set = set()

    def add(a: Optional[str], b: Optional[str]) -> None:
        if not a or not b or a == b:
            return
        pair = (a, b)
        if pair in seen:
            return
        seen.add(pair)
        legs.append(pair)

    if not ids:
        return legs
    if start_depot_id:
        add(start_depot_id, ids[0])
    for a, b in zip(ids, ids[1:]):
        add(a, b)
    if end_depot_id:
        add(ids[-1], end_depot_id)
    return legs


def _coverage_outcome(
        legs: Sequence[Tuple[str, str]], covered: set
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]], str]:
    successful = [pair for pair in legs if pair in covered]
    missing = [pair for pair in legs if pair not in covered]
    if not legs:
        return successful, missing, "not_applicable"
    return successful, missing, ("partial" if missing else "complete")


def _covered_directed_pairs(
        route_evidence: Optional[RouteEvidence], mode: Optional[str]
) -> set:
    """Successful directed pairs for the requested transport mode only.

    Nothing is mirrored or inferred: a successful ``b -> a`` edge never proves
    ``a -> b``, and an edge collected for another mode is not reused.
    """
    covered: set = set()
    records = route_evidence.records if route_evidence is not None else []
    for record in records:
        if record.status != "success":
            continue
        if mode is not None and record.transport_mode != mode:
            continue
        covered.add((record.from_poi_id, record.to_poi_id))
    return covered


def _normalize_planned_days(days: Sequence[Any]) -> List[Tuple[str, List[str]]]:
    normalized: List[Tuple[str, List[str]]] = []
    for entry in days or []:
        if isinstance(entry, dict):
            day_id = entry.get("day_id")
            ids = entry.get("poi_ids")
        elif isinstance(entry, (tuple, list)) and len(entry) == 2:
            day_id, ids = entry
        else:
            continue
        if not isinstance(day_id, str) or not day_id.strip():
            day_id = f"d{len(normalized)}"
        if not isinstance(ids, (list, tuple)):
            ids = []
        normalized.append((day_id, [pid for pid in ids
                                    if isinstance(pid, str) and pid.strip()]))
    return normalized


def selected_plan_day_route_coverage(
    days: Sequence[Any],
    route_evidence: Optional[RouteEvidence] = None,
    *,
    transport_mode: Optional[str] = None,
    start_depot_id: Optional[str] = None,
    end_depot_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Selected-plan coverage computed per *actual scheduled day*.

    ``days`` is the delivered schedule's real structure: a sequence of
    ``{"day_id": ..., "poi_ids": [...]}`` mappings (or ``(day_id, ids)``
    tuples). Every non-empty day contributes its declared start-depot leg, its
    within-day adjacent legs and its declared end-depot leg. A missing daily
    depot leg stays missing even when the global first/last legs happen to be
    covered. An empty day contributes nothing. Required pairs are unioned only
    for the actual-edge proof; per-day detail is reported separately.
    """
    mode = transport_mode
    if mode is None and route_evidence is not None:
        mode = route_evidence.transport_mode
    covered = _covered_directed_pairs(route_evidence, mode)

    day_reports: List[Dict[str, Any]] = []
    union_required: List[Tuple[str, str]] = []
    union_seen: set = set()
    for day_id, ids in _normalize_planned_days(days):
        legs = _required_day_legs(ids, start_depot_id=start_depot_id,
                                  end_depot_id=end_depot_id)
        successful, missing, coverage = _coverage_outcome(legs, covered)
        if not legs:
            coverage = "empty"
        for pair in legs:
            if pair not in union_seen:
                union_seen.add(pair)
                union_required.append(pair)
        day_reports.append({
            "day_id": day_id,
            "stop_ids": list(ids),
            "required_pairs": [list(p) for p in legs],
            "successful_pairs": [list(p) for p in successful],
            "missing_pairs": [list(p) for p in missing],
            "coverage": coverage,
            "verified": coverage == "complete",
        })

    successful_pairs, missing_pairs, coverage = _coverage_outcome(
        union_required, covered)
    return {
        "scope": SELECTED_PLAN_COVERAGE_SCOPE,
        "transport_mode": mode,
        "daily_legs": True,
        "day_count": len(day_reports),
        "non_empty_day_count": sum(1 for d in day_reports if d["stop_ids"]),
        "required_pairs": [list(p) for p in union_required],
        "successful_pairs": [list(p) for p in successful_pairs],
        "missing_pairs": [list(p) for p in missing_pairs],
        "coverage": coverage,
        "verified": coverage == "complete",
        "days": day_reports,
        "directions_required": True,
        "start_depot_id": start_depot_id,
        "end_depot_id": end_depot_id,
        # The global figure answers a different question and is kept as-is.
        "candidate_pool_coverage": (None if route_evidence is None
                                    else route_evidence.coverage),
        "uncovered_legs_are_not_mirrored": True,
        "cross_day_legs_invented": False,
    }


def selected_plan_route_coverage(
    ordered_poi_ids: Sequence[str],
    route_evidence: Optional[RouteEvidence] = None,
    *,
    transport_mode: Optional[str] = None,
    start_depot_id: Optional[str] = None,
    end_depot_id: Optional[str] = None,
) -> Dict[str, Any]:
    """One-day/one-sequence compatibility wrapper around the daily helper."""
    return selected_plan_day_route_coverage(
        [("d1", list(ordered_poi_ids))], route_evidence,
        transport_mode=transport_mode, start_depot_id=start_depot_id,
        end_depot_id=end_depot_id)


def selected_plan_day_route_geometry(
    days: Sequence[Any],
    route_evidence: Optional[RouteEvidence] = None,
    *,
    transport_mode: Optional[str] = None,
    start_depot_id: Optional[str] = None,
    end_depot_id: Optional[str] = None,
) -> Dict[str, Any]:
    """GeoJSON FeatureCollection for the actual selected directed daily legs.

    Only a successful record for the exact ``(from, to)`` pair in the requested
    mode that carries real provider geometry contributes a feature. Cross-day
    stops, reverse edges and candidate-only legs are never connected, and a
    missing leg is reported (never drawn as a straight line).
    """
    mode = transport_mode
    if mode is None and route_evidence is not None:
        mode = route_evidence.transport_mode

    by_pair: Dict[Tuple[str, str], RouteRecord] = {}
    for record in (route_evidence.records if route_evidence is not None else []):
        if record.status != "success" or record.geometry is None:
            continue
        if mode is not None and record.transport_mode != mode:
            continue
        by_pair.setdefault((record.from_poi_id, record.to_poi_id), record)

    features: List[Dict[str, Any]] = []
    instructions: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    required = 0
    for day_id, ids in _normalize_planned_days(days):
        legs = _required_day_legs(ids, start_depot_id=start_depot_id,
                                  end_depot_id=end_depot_id)
        for a, b in legs:
            required += 1
            record = by_pair.get((a, b))
            if record is None or record.geometry is None:
                missing.append({
                    "day_id": day_id,
                    "from_poi_id": a,
                    "to_poi_id": b,
                    "transport_mode": mode,
                })
                continue
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [list(position)
                                    for position in record.geometry["coordinates"]],
                },
                "properties": {
                    "day_id": day_id,
                    "from_poi_id": a,
                    "to_poi_id": b,
                    "transport_mode": mode,
                    "provenance": "graphhopper",
                },
            })
            if record.instructions:
                instructions.append({
                    "day_id": day_id,
                    "from_poi_id": a,
                    "to_poi_id": b,
                    "transport_mode": mode,
                    "provenance": "graphhopper",
                    "steps": list(record.instructions),
                })

    return {
        "type": "FeatureCollection",
        "features": features,
        "provenance": "graphhopper",
        "transport_mode": mode,
        "requested_leg_count": required,
        "missing_geometry_count": len(missing),
        "missing_legs": missing,
        "straight_line_fallback": False,
        "instructions": instructions,
    }


# ---------------------------------------------------------------------------
# Scenario construction
# ---------------------------------------------------------------------------
@dataclass
class PlanningInputs:
    scenario: Optional[Scenario]
    assumptions: List[str] = field(default_factory=list)
    unknowns: List[str] = field(default_factory=list)
    hours_status: Dict[str, str] = field(default_factory=dict)
    hours_source: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    cost_policy: Dict[str, Any] = field(default_factory=dict)
    route_evidence: Optional[RouteEvidence] = None
    request_constraints: Dict[str, Any] = field(default_factory=dict)
    build_error: Optional[Tuple[str, str]] = None


def _request_get(request: Any, name: str) -> Any:
    if isinstance(request, dict):
        return request.get(name)
    return getattr(request, name, None)


def _day_id(date_str: str) -> str:
    return f"d_{date_str}"


def _hm_to_instant(date_str: str, hm: str) -> str:
    return f"{date_str}T{hm}:00+07:00"


def _trip_dates(start_date: Any, duration_days: Any) -> Optional[List[str]]:
    if not isinstance(start_date, str):
        return None
    try:
        base = datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError:
        return None
    return [(base + timedelta(days=offset)).isoformat()
            for offset in range(duration_days)]


def _poi_category_ids(evidence: Dict[str, Any], candidate_category_ids: Dict[str, List[str]],
                      poi_id: str) -> List[str]:
    category_ids = [cid for cid in (candidate_category_ids.get(poi_id) or [])
                    if isinstance(cid, str) and cid.strip()]
    for ref in evidence.get("POI_Categories") or []:
        if isinstance(ref, dict):
            cid = grounding.nonblank_str(ref.get("id"))
            if cid is not None and cid not in category_ids:
                category_ids.append(cid)
    return category_ids


def _known_category_ids(verified_evidence: Dict[str, Dict[str, Any]],
                        candidate_category_ids: Dict[str, List[str]]) -> set:
    known: set = set()
    for poi_id, evidence in verified_evidence.items():
        known.update(_poi_category_ids(evidence or {}, candidate_category_ids, poi_id))
    return known


def _local_date(iso_value: str) -> str:
    return (datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
            .astimezone(VN_TZ).date().isoformat())


def _resolve_day_windows(request: Any, trip_dates: Sequence[str]
                         ) -> Tuple[Optional[Dict[str, Tuple[str, str]]], Optional[Tuple[str, str]]]:
    """Validate explicit day windows; reject out-of-trip/duplicate/mismatched."""
    raw_windows = _request_get(request, "day_windows")
    if raw_windows is None:
        return {}, None
    if not isinstance(raw_windows, list):
        return None, ("invalid_request", "day_windows must be a list")
    explicit: Dict[str, Tuple[str, str]] = {}
    for entry in raw_windows:
        if not isinstance(entry, dict):
            return None, ("invalid_request", "each day_windows entry must be an object")
        date_str = grounding.nonblank_str(entry.get("date"))
        start = grounding.nonblank_str(entry.get("start"))
        end = grounding.nonblank_str(entry.get("end"))
        if date_str is None or start is None or end is None:
            return None, ("invalid_request", "day_windows entry needs date + start + end")
        try:
            start_min = parse_instant(start, "day_windows.start")
            end_min = parse_instant(end, "day_windows.end")
        except ScenarioError as exc:
            return None, ("invalid_request", f"day_windows.{exc.field}: {exc.detail}")
        if start_min >= end_min:
            return None, ("invalid_request", "day_windows start must precede end")
        if date_str not in trip_dates:
            return None, ("invalid_request", f"day_window:{date_str} is outside the trip")
        if date_str in explicit:
            return None, ("invalid_request", f"duplicate_day_window:{date_str}")
        if _local_date(start) != date_str:
            return None, ("invalid_request",
                          f"day_window:{date_str} date does not match its start timestamp")
        explicit[date_str] = (start, end)
    return explicit, None


def _resolve_meal_windows(request: Any, known_categories: set, trip_dates: Sequence[str],
                          day_windows: Dict[str, Tuple[str, str]]
                          ) -> Tuple[Optional[Dict[str, List[Dict[str, Any]]]], Optional[Tuple[str, str]]]:
    """Validate meal windows; reject unknown category/out-of-trip/overnight/naive."""
    raw_meals = _request_get(request, "meal_windows")
    if raw_meals is None or raw_meals == []:
        return {}, None
    if not isinstance(raw_meals, list):
        return None, ("invalid_request", "meal_windows must be a list")
    by_date: Dict[str, List[Dict[str, Any]]] = {}
    for meal in raw_meals:
        if not isinstance(meal, dict):
            return None, ("invalid_request", "meal window must be an object")
        cid = grounding.nonblank_str(meal.get("category_id"))
        if cid is None:
            return None, ("invalid_request", "meal window needs a category_id")
        if cid not in known_categories:
            return None, ("invalid_request", f"unknown_meal_category:{cid}")
        start = grounding.nonblank_str(meal.get("start"))
        end = grounding.nonblank_str(meal.get("end"))
        if start is None or end is None:
            return None, ("invalid_request", "meal window needs start and end")
        try:
            start_min = parse_instant(start, "meal_window.start")
            end_min = parse_instant(end, "meal_window.end")
        except ScenarioError as exc:
            return None, ("invalid_request", f"meal_window.{exc.field}: {exc.detail}")
        if start_min >= end_min:
            return None, ("invalid_request", "meal window start must precede end")
        start_date = _local_date(start)
        if _local_date(end) != start_date:
            return None, ("invalid_request", "overnight_meal_window_unsupported")
        if start_date not in trip_dates:
            return None, ("invalid_request", f"meal_window:{start_date} is outside the trip")
        window = day_windows.get(start_date)
        if window is None:
            window = (_hm_to_instant(start_date, DEFAULT_DAY_WINDOW[0]),
                      _hm_to_instant(start_date, DEFAULT_DAY_WINDOW[1]))
        if start_min < parse_instant(window[0], "day.window.start") \
                or end_min > parse_instant(window[1], "day.window.end"):
            return None, ("invalid_request",
                          f"meal_window:{start_date} is outside the day window")
        by_date.setdefault(start_date, []).append(
            {"category_id": cid, "start": start, "end": end})
    return by_date, None


def _resolve_required_categories(request: Any, known_categories: set
                                 ) -> Tuple[Optional[List[str]], List[str], Optional[Tuple[str, str]]]:
    """Return ``(required, unknowns, error)``.

    An unknown required category is a *preserved impossibility*: it is carried
    into the scenario so the validator reports it unsatisfied (never dropped to
    deliver an unconstrained substitute).
    """
    raw_required = _request_get(request, "required_categories")
    if raw_required is None:
        return [], [], None
    if not isinstance(raw_required, list):
        return None, [], ("invalid_request", "required_categories must be a list")
    required: List[str] = []
    unknowns: List[str] = []
    for cid in raw_required:
        cid = grounding.nonblank_str(cid)
        if cid is None:
            return None, [], ("invalid_request", "required category must be nonblank")
        if cid not in known_categories:
            unknowns.append(f"required_category_unknown:{cid}")
        if cid not in required:
            required.append(cid)
    return required, unknowns, None


def validate_constraints(request: Any, verified_evidence: Dict[str, Dict[str, Any]],
                         candidate_category_ids: Dict[str, List[str]]
                         ) -> Optional[Tuple[str, str]]:
    """Validate explicit request constraints *before* any route call.

    Returns ``(code, detail)`` on a fail-closed constraint, else ``None``. Must
    agree with :func:`build_scenario` (both share the same helpers).
    """
    transport_mode, _ = request_transport_mode(request)
    if transport_mode is None:
        return ("invalid_request", INVALID_TRANSPORT_MODE)
    duration_days = _request_get(request, "duration_days")
    start_date = _request_get(request, "start_date")
    if not isinstance(duration_days, int) or isinstance(duration_days, bool):
        return ("invalid_request", "duration_days must be an integer")
    if grounding.trip_window(start_date, duration_days) is None:
        return ("invalid_request", "start_date/duration_days are invalid")
    trip_dates = _trip_dates(start_date, duration_days)
    if trip_dates is None:
        return ("invalid_request", "start_date is not an ISO date")
    explicit, error = _resolve_day_windows(request, trip_dates)
    if error is not None:
        return error
    known_categories = _known_category_ids(verified_evidence, candidate_category_ids)
    _, error = _resolve_meal_windows(request, known_categories, trip_dates, explicit)
    if error is not None:
        return error
    _, _, error = _resolve_required_categories(request, known_categories)
    if error is not None:
        return error
    return None


def build_scenario(
    request: Any,
    verified_evidence: Dict[str, Dict[str, Any]],
    candidate_category_ids: Dict[str, List[str]],
    route_edges: List[Dict[str, Any]],
    budget: Optional[BudgetConstraint],
    *,
    model_category_weights: Optional[Dict[str, int]] = None,
) -> PlanningInputs:
    """Build a typed :class:`Scenario` from verified evidence + constraints.

    Missing source facts stay unknown; every fallback (day window, visit
    duration) is recorded as an explicit assumption rather than a POI fact.
    """
    inputs = PlanningInputs(
        scenario=None,
        cost_policy=dict(_COST_POLICY),
        request_constraints={},
    )

    transport_mode, transport_mode_source = request_transport_mode(request)
    if transport_mode is None:
        inputs.build_error = ("invalid_request", INVALID_TRANSPORT_MODE)
        return inputs
    # Keep the requested mode/source visible even when another constraint
    # aborts scenario construction before the full constraint block is built.
    inputs.request_constraints = {
        "transport_mode": transport_mode,
        "transport_mode_source": transport_mode_source,
    }

    duration_days = _request_get(request, "duration_days")
    start_date = _request_get(request, "start_date")
    party_size = _request_get(request, "num_travelers")
    if not isinstance(duration_days, int) or isinstance(duration_days, bool):
        inputs.build_error = ("invalid_request", "duration_days must be an integer")
        return inputs
    if not isinstance(party_size, int) or isinstance(party_size, bool) or party_size < 1:
        inputs.build_error = ("invalid_request", "num_travelers must be a positive integer")
        return inputs
    start = grounding.trip_window(start_date, duration_days)
    if start is None:
        inputs.build_error = ("invalid_request", "start_date/duration_days are invalid")
        return inputs

    # --- day windows (shared helper; detects out-of-trip/duplicate/mismatch)
    trip_dates = _trip_dates(start_date, duration_days)
    if trip_dates is None:
        inputs.build_error = ("invalid_request", "start_date is not an ISO date")
        return inputs
    explicit_windows, error = _resolve_day_windows(request, trip_dates)
    if error is not None:
        inputs.build_error = error
        return inputs

    days: List[Dict[str, Any]] = []
    for day_date in trip_dates:
        if day_date in explicit_windows:
            window_start, window_end = explicit_windows[day_date]
        else:
            window_start, window_end = (
                _hm_to_instant(day_date, DEFAULT_DAY_WINDOW[0]),
                _hm_to_instant(day_date, DEFAULT_DAY_WINDOW[1]))
            inputs.assumptions.append(
                f"day_window:{day_date}={DEFAULT_DAY_WINDOW[0]}-{DEFAULT_DAY_WINDOW[1]} "
                f"({DEFAULT_DAY_WINDOW_POLICY})")
        days.append({
            "day_id": _day_id(day_date),
            "date": day_date,
            "window": {"start": window_start, "end": window_end},
        })

    # --- visit-duration policy --------------------------------------------
    visit_minutes = _request_get(request, "visit_minutes")
    if visit_minutes is None:
        visit_minutes = DEFAULT_VISIT_MINUTES
        inputs.assumptions.append(f"visit_minutes:{DEFAULT_VISIT_MINUTES} ({DEFAULT_VISIT_POLICY})")
    if not isinstance(visit_minutes, int) or isinstance(visit_minutes, bool) \
            or not (1 <= visit_minutes <= 24 * 60):
        inputs.build_error = ("invalid_request", "visit_minutes must be in 1..1440")
        return inputs

    # --- POIs (facts from verified evidence only) -------------------------
    currency = budget.currency if budget is not None else DEFAULT_CURRENCY
    if budget is None:
        inputs.unknowns.append("budget_unknown:no_unambiguous_source_or_field")
    pois: List[Dict[str, Any]] = []
    for poi_id in sorted(verified_evidence):
        evidence = verified_evidence[poi_id] or {}
        category_ids = _poi_category_ids(evidence, candidate_category_ids, poi_id)
        if not category_ids:
            inputs.unknowns.append(f"poi_category_unknown:{poi_id}")
            continue
        hours = parse_operation_time(evidence.get("operation_time"))
        inputs.hours_status[poi_id] = hours.status
        inputs.hours_source[poi_id] = {
            "status": hours.status,
            "source_text": hours.original,
            "start_hm": hours.start_hm,
            "end_hm": hours.end_hm,
            "detail": hours.detail,
        }
        windows: List[Dict[str, Any]] = []
        if hours.status == "always_open":
            for day in days:
                windows.append({"day_id": day["day_id"],
                                "start": day["window"]["start"],
                                "end": day["window"]["end"]})
        elif hours.status == "daily_window":
            for day in days:
                windows.append({"day_id": day["day_id"],
                                "start": _hm_to_instant(day["date"], hours.start_hm),
                                "end": _hm_to_instant(day["date"], hours.end_hm)})
        else:
            inputs.unknowns.append(f"hours_unknown:{poi_id}:{hours.status}")
        pois.append({
            "poi_id": poi_id,
            "category_ids": category_ids,
            "visit_minutes": visit_minutes,
            "opening_windows": windows,
            # cost intentionally omitted => unknown (see _COST_POLICY)
        })
    if not pois:
        inputs.build_error = ("insufficient_data", "no POI had a verified category id")
        return inputs

    # --- required categories / meal windows (shared helpers) --------------
    known_categories = {cid for poi in pois for cid in poi["category_ids"]}
    required, required_unknowns, error = _resolve_required_categories(request, known_categories)
    if error is not None:
        inputs.build_error = error
        return inputs
    inputs.unknowns.extend(required_unknowns)

    meals_by_date, error = _resolve_meal_windows(
        request, known_categories, trip_dates, explicit_windows)
    if error is not None:
        inputs.build_error = error
        return inputs
    for day in days:
        if day["date"] in meals_by_date:
            day["meal_windows"] = meals_by_date[day["date"]]

    # --- min/max stops ----------------------------------------------------
    minimum_stops = _request_get(request, "minimum_stops")
    if minimum_stops is not None and (not isinstance(minimum_stops, int)
                                      or isinstance(minimum_stops, bool)
                                      or minimum_stops < 0):
        inputs.build_error = ("invalid_request", "minimum_stops must be a non-negative integer")
        return inputs
    maximum_stops = _request_get(request, "maximum_stops")
    if maximum_stops is not None:
        if (not isinstance(maximum_stops, int) or isinstance(maximum_stops, bool)
                or maximum_stops < 1):
            inputs.build_error = ("invalid_request", "maximum_stops must be a positive integer")
            return inputs
        for day in days:
            day["max_stops"] = maximum_stops

    preferences = {"category_weights": dict(model_category_weights or {})}

    raw: Dict[str, Any] = {
        "scenario_id": f"plan:{start_date}:{_request_get(request, 'target_district')}:{duration_days}d",
        "seed": 0,
        "currency": currency,
        "party_size": party_size,
        "days": days,
        "pois": pois,
        "route_edges": route_edges,
        "transport_mode": transport_mode,
        "required_categories": required,
        "preferences": preferences,
        "allow_duplicate_pois": False,
    }
    if budget is not None:
        raw["budget"] = {"amount": format(budget.amount, "f"),
                         "currency": budget.currency, "unit": "per_party"}
    if minimum_stops is not None:
        raw["minimum_stops"] = minimum_stops

    try:
        inputs.scenario = parse_scenario(raw)
    except ScenarioError as exc:
        inputs.build_error = (exc.code, f"{exc.field}: {exc.detail}")
        return inputs

    inputs.request_constraints = {
        "party_size": party_size,
        "currency": currency,
        "transport_mode": transport_mode,
        "transport_mode_source": transport_mode_source,
        "budget": (None if budget is None else {
            "amount": format(budget.amount, "f"), "currency": budget.currency,
            "unit": budget.unit, "source": budget.source}),
        "minimum_stops": minimum_stops,
        "maximum_stops_per_day": maximum_stops,
        "visit_minutes": visit_minutes,
        "visit_minutes_source": ("user" if _request_get(request, "visit_minutes") is not None
                                 else "assumption"),
        "day_window_source": ("user" if explicit_windows else "assumption"),
        "required_categories": required,
        "meal_windows": bool(meals_by_date),
    }
    # Preserve the explicit source selection as request provenance. The adapter
    # never derives, selects or changes a selector; it only carries the value
    # the request boundary validated.
    source_scope = _request_get(request, "source_scope")
    if source_scope is not None:
        model_dump = getattr(source_scope, "model_dump", None)
        if callable(model_dump):
            source_scope = model_dump()
        if isinstance(source_scope, dict):
            inputs.request_constraints["scope_mode"] = grounding.SOURCE_SCOPE_CONTRACT
            inputs.request_constraints["source_scope"] = dict(source_scope)
    return inputs


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------
def epoch_to_vn_iso(minutes: int) -> str:
    """Render epoch minutes as an ISO-8601 instant in Vietnam time (UTC+07:00)."""
    utc = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minutes)
    return utc.astimezone(VN_TZ).isoformat()


def render_validation(report: Any) -> Dict[str, Any]:
    """JSON-safe summary of the independent validator's report."""
    return {
        "status": report.status,
        "no_plan_reason": report.no_plan_reason,
        "known_violations": [
            {"code": v.code, "day_id": v.day_id, "poi_id": v.poi_id, "detail": v.detail}
            for v in report.known_violations],
        "unknown_reasons": list(report.unknown_reasons),
        "unsatisfied_required": list(report.unsatisfied_required),
        "recomputed_total_cost_party": (None if report.recomputed_total_cost_party is None
                                        else format(report.recomputed_total_cost_party, "f")),
        "recomputed_total_travel_minutes": report.recomputed_total_travel_minutes,
        "recomputed_total_distance_km": (None if report.recomputed_total_distance_km is None
                                         else format(report.recomputed_total_distance_km, "f")),
        "stop_count": report.stop_count,
        "checks": dict(report.checks),
    }


def render_plan(plan: Any) -> Dict[str, Any]:
    """JSON-safe summary of the scheduler's repaired schedule."""
    days = []
    for day in plan.days:
        days.append({
            "day_id": day.day_id,
            "stops": [
                {
                    "poi_id": stop.poi_id,
                    "arrival": epoch_to_vn_iso(stop.arrival),
                    "departure": epoch_to_vn_iso(stop.departure),
                    "visit_minutes": stop.visit_minutes,
                    "travel_from_prev_minutes": stop.travel_from_prev_minutes,
                    "travel_from_prev_distance_km": (
                        None if stop.travel_from_prev_distance_km is None
                        else format(stop.travel_from_prev_distance_km, "f")),
                    "cost_party": (None if stop.cost_party is None
                                   else format(stop.cost_party, "f")),
                    "cost_currency": stop.cost_currency,
                }
                for stop in day.stops
            ],
        })
    return {
        "scenario_id": plan.scenario_id,
        "scheduler_status": "unverifiable" if plan.status == "unverifiable" else plan.status,
        "sequence": list(plan.sequence),
        "days": days,
        "total_cost_party": (None if plan.total_cost_party is None
                             else format(plan.total_cost_party, "f")),
        "total_cost_currency": plan.total_cost_currency,
        "total_travel_minutes": plan.total_travel_minutes,
        "total_distance_km": (None if plan.total_distance_km is None
                              else format(plan.total_distance_km, "f")),
        "excluded": [{"poi_id": e.poi_id, "day_id": e.day_id, "reason": e.reason}
                     for e in plan.excluded],
        "unsatisfied_required": list(plan.unsatisfied_required),
        "unknown_reasons": list(plan.unknown_reasons),
        "iterations": plan.iterations,
        "notes": list(plan.notes),
    }
