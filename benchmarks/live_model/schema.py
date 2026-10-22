"""Strict parsing of the model's JSON-only output.

The model is instructed to return a single JSON object and nothing else. Parsing
is deliberately strict: the *entire* trimmed assistant text must be one JSON
object. A fenced block, a preamble, a trailing note or truncated JSON is a
malformed output and therefore a failed observed run — it is never repaired into
a clean baseline.

No field is invented. Times are validated later by the typed planning contracts
(``parse_instant`` rejects naive/second-resolution instants); this module only
enforces structural shape.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple


class OutputError(ValueError):
    """The model output is not a strict, well-formed object of the expected shape."""


@dataclass(frozen=True)
class Stop:
    poi_id: str
    arrival: str
    departure: str


@dataclass(frozen=True)
class Day:
    day_id: str
    stops: Tuple[Stop, ...]


@dataclass(frozen=True)
class LlmOnlyPlan:
    status: str
    no_plan_reason: Optional[str]
    days: Tuple[Day, ...]


@dataclass(frozen=True)
class HybridOrder:
    ordered_poi_ids: Tuple[str, ...]
    day_assignment: Mapping[str, str] = field(default_factory=dict)


def _obj(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise OutputError(f"{where}: expected a JSON object")
    return value


def _nonblank(value: Any, where: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str) or not value.strip():
        raise OutputError(f"{where}: expected a nonblank string")
    return value.strip()


def parse_strict_json(text: str) -> Mapping[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise OutputError("empty assistant output")
    stripped = text.strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise OutputError(f"assistant output is not a single valid JSON value: {exc}")
    return _obj(value, "root")


def parse_llm_only(text: str) -> LlmOnlyPlan:
    root = parse_strict_json(text)
    status = _nonblank(root.get("status"), "status")
    if status not in ("plan", "no_plan"):
        raise OutputError("status must be 'plan' or 'no_plan'")

    raw_reason = root.get("no_plan_reason")
    no_plan_reason: Optional[str] = None
    if raw_reason is not None:
        no_plan_reason = _nonblank(raw_reason, "no_plan_reason")

    raw_days = root.get("days")
    if raw_days is None:
        raise OutputError("days: required")
    if not isinstance(raw_days, list):
        raise OutputError("days: expected a JSON array")

    days: List[Day] = []
    seen_days = set()
    for day_index, entry in enumerate(raw_days):
        where = f"days[{day_index}]"
        day = _obj(entry, where)
        day_id = _nonblank(day.get("day_id"), f"{where}.day_id")
        if day_id in seen_days:
            raise OutputError(f"{where}.day_id: duplicate '{day_id}'")
        seen_days.add(day_id)
        raw_stops = day.get("stops")
        if not isinstance(raw_stops, list):
            raise OutputError(f"{where}.stops: expected a JSON array")
        stops: List[Stop] = []
        for stop_index, raw_stop in enumerate(raw_stops):
            swhere = f"{where}.stops[{stop_index}]"
            stop = _obj(raw_stop, swhere)
            stops.append(Stop(
                poi_id=_nonblank(stop.get("poi_id"), f"{swhere}.poi_id"),
                arrival=_nonblank(stop.get("arrival"), f"{swhere}.arrival"),
                departure=_nonblank(stop.get("departure"), f"{swhere}.departure"),
            ))
        days.append(Day(day_id=day_id, stops=tuple(stops)))

    if status == "no_plan":
        if no_plan_reason is None:
            raise OutputError("no_plan output must declare a no_plan_reason")
        if any(day.stops for day in days):
            raise OutputError("no_plan output must not contain stops")
    else:
        if no_plan_reason is not None:
            raise OutputError("plan output must not declare a no_plan_reason")
        if not days:
            raise OutputError("plan output must contain at least one day")

    return LlmOnlyPlan(status=status, no_plan_reason=no_plan_reason, days=tuple(days))


def parse_hybrid(text: str) -> HybridOrder:
    root = parse_strict_json(text)
    raw_order = root.get("ordered_poi_ids")
    if not isinstance(raw_order, list):
        raise OutputError("ordered_poi_ids: expected a JSON array")
    ordered: List[str] = []
    seen = set()
    for index, value in enumerate(raw_order):
        poi_id = _nonblank(value, f"ordered_poi_ids[{index}]")
        if poi_id in seen:
            raise OutputError(f"ordered_poi_ids[{index}]: duplicate '{poi_id}'")
        seen.add(poi_id)
        ordered.append(poi_id)

    raw_assignment = root.get("day_assignment")
    assignment: Dict[str, str] = {}
    if raw_assignment is not None:
        mapping = _obj(raw_assignment, "day_assignment")
        for key, value in mapping.items():
            poi_id = _nonblank(key, "day_assignment.<key>")
            if poi_id not in seen:
                raise OutputError(f"day_assignment references unlisted poi_id '{poi_id}'")
            assignment[poi_id] = _nonblank(value, f"day_assignment.{poi_id}")

    return HybridOrder(ordered_poi_ids=tuple(ordered), day_assignment=assignment)


def parse_model_output(condition: str, text: str):
    if condition == "llm_only":
        return parse_llm_only(text)
    if condition == "hybrid":
        return parse_hybrid(text)
    raise OutputError(f"unknown condition '{condition}'")
