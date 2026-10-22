"""Server-owned source-selection and travel-mode gate for chat tool calls.

The explicit request (``ChatRequest.source_scope`` / ``ChatRequest.transport_mode``)
is the only authority. The model may propose tool arguments, but it can never
select, widen or replace the source area, use current administrative filters, or
change the travel mode. Everything here is pure (no I/O): ``main._run_travel_turn``
injects the actual MCP call and routes arguments through :meth:`ScopeGate.prepare`
and results through :meth:`ScopeGate.filter_result`.

Two invariants drive the implementation:

* **Arguments actually sent** are rebuilt server-side. In source mode the exact
  selection tuple is injected into ``explore_pois``; a model-supplied selector
  that differs is refused rather than silently replaced.
* **Evidence actually shown** is re-qualified from the returned record before it
  reaches the model, the trace or working memory. Out-of-scope detail records,
  mixed-area ``NEAR_BY`` entries and unverified route ids are removed; the call
  is reported as a structured failure instead of a grounded result.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from domains import grounding

SOURCE_SCOPE_VIOLATION = "source_scope_violation"
SOURCE_SELECTION_MISMATCH = "source_selection_mismatch"
SOURCE_DISCOVERY_BLOCKED = "source_discovery_blocked"
CURRENT_GEOGRAPHY_BLOCKED = "current_geography_blocked"
UNVERIFIED_POI_ID = "unverified_poi_id"
ROUTE_IDS_UNVERIFIED = "route_ids_unverified"
TRANSPORT_MODE_MISMATCH = "transport_mode_mismatch"
INVALID_ROUTE_REQUEST = "invalid_route_request"

EXPLORE_TOOL = "explore_pois"
DETAILS_TOOL = "get_poi_details"
ROUTE_TOOL = "get_itinerary_route"
RESOLVER_TOOL = "resolve_geographic_id"

TRANSPORT_MODES = ("car", "foot")

# Bounded, non-secret per-call metadata (a hostile model cannot grow it).
MAX_RECORDED_REJECTIONS = 16
MAX_RECORDED_ROUTES = 16
MAX_ROUTE_STOPS = 32

# The only codes that may be surfaced to the model/trace for a refused tool
# call, each with a fixed server-owned message. Upstream ``success:false``
# payloads can echo arbitrary strings; anything not in this table becomes the
# generic constant in ``chat_agent``.
REJECTION_MESSAGES: Dict[str, str] = {
    "malformed_arguments": "Tool arguments were not a JSON object.",
    "invalid_request": "The tool request is missing a required value.",
    SOURCE_SCOPE_VIOLATION: (
        "The tool call is outside the explicitly selected source area."),
    SOURCE_SELECTION_MISMATCH: (
        "The tool call does not match the request source selection."),
    SOURCE_DISCOVERY_BLOCKED: (
        "Source discovery is not part of this request."),
    CURRENT_GEOGRAPHY_BLOCKED: (
        "Current city/district resolution is not part of the selected source area."),
    UNVERIFIED_POI_ID: (
        "The POI id was not verified inside the selected source area."),
    ROUTE_IDS_UNVERIFIED: (
        "Every route stop must be a verified POI inside the selected source area."),
    TRANSPORT_MODE_MISMATCH: (
        "The route profile must equal the request travel mode."),
    INVALID_ROUTE_REQUEST: "The route request is not a valid itinerary.",
    "scope_violation": "The tool call was refused by the server scope gate.",
}

_SOURCE_ARGUMENTS = ("source_scope", "source_discovery", "source_snapshot")
_ADMIN_FILTERS = ("city_id", "district_id", "street_id")


@dataclass
class Decision:
    """The outcome of gating one proposed tool call."""

    ok: bool
    args: Optional[Dict[str, Any]] = None
    code: Optional[str] = None
    detail: Optional[str] = None


class _TextContent:
    """Minimal textual tool-result content (only ``.text`` is read)."""

    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text


class _ToolResult:
    """Minimal ``CallToolResult`` shape understood by ``domains.grounding``."""

    __slots__ = ("content", "isError")

    def __init__(self, text: str) -> None:
        self.content = [_TextContent(text)]
        self.isError = False


def canonical_selection(value: Any) -> Optional[Dict[str, Any]]:
    """Return the exact canonical selection, or ``None`` when invalid."""
    parsed = grounding.parse_source_selection(value)
    if not parsed.ok or not isinstance(parsed.data, dict):
        return None
    return grounding.copy_source_selection(parsed.data)


def _same_selection(left: Any, right: Any) -> bool:
    canonical = canonical_selection(left)
    if canonical is None:
        return False
    return canonical == canonical_selection(right)


class ScopeGate:
    """Gate one chat turn's tool calls against the explicit request context."""

    def __init__(self, *, source_selection: Optional[Dict[str, str]] = None,
                 transport_mode: str = "car") -> None:
        self.selection = (canonical_selection(source_selection)
                          if source_selection is not None else None)
        self.transport_mode = (transport_mode
                               if transport_mode in TRANSPORT_MODES else "car")
        # Ids a source-scoped explore actually returned as qualified evidence.
        self.discovered_ids: Set[str] = set()
        # Ids whose own detail record was re-qualified against the selection.
        self.verified_ids: Set[str] = set()
        self.rejections: List[Dict[str, str]] = []
        self.route_calls: List[Dict[str, Any]] = []
        # Only a validated successful MCP route is retained as route evidence.
        self.route_evidence: Optional[Dict[str, Any]] = None
        self.filtered_entries = 0

    # ------------------------------------------------------------------
    # Argument gating
    # ------------------------------------------------------------------
    @property
    def source_mode(self) -> bool:
        return self.selection is not None

    def _reject(self, code: str, detail: str) -> Decision:
        if len(self.rejections) < MAX_RECORDED_REJECTIONS:
            self.rejections.append({"code": code, "detail": detail})
        return Decision(False, code=code, detail=detail)

    def prepare(self, name: str, args: Any) -> Decision:
        """Return the exact arguments to send, or a structured refusal."""
        if not isinstance(args, dict):
            return self._reject("malformed_arguments",
                                "tool arguments must be a JSON object")
        clean = dict(args)

        if name == EXPLORE_TOOL:
            return self._prepare_explore(clean)
        if name == DETAILS_TOOL:
            return self._prepare_details(clean)
        if name == ROUTE_TOOL:
            return self._prepare_route(clean)
        if name == RESOLVER_TOOL and self.source_mode:
            return self._reject(
                CURRENT_GEOGRAPHY_BLOCKED,
                "current city/district resolution is not part of the selected "
                "source area")
        return Decision(True, args=clean)

    def _prepare_explore(self, args: Dict[str, Any]) -> Decision:
        if not self.source_mode:
            if any(args.get(key) is not None for key in _SOURCE_ARGUMENTS):
                return self._reject(
                    SOURCE_DISCOVERY_BLOCKED,
                    "source selection/discovery is not part of this request")
            return Decision(True, args=args)

        if args.get("source_discovery") is not None:
            return self._reject(
                SOURCE_DISCOVERY_BLOCKED,
                "snapshot discovery is not evidence and cannot run inside a "
                "source-scoped turn")
        for key in _ADMIN_FILTERS:
            if args.get(key) is not None:
                return self._reject(
                    SOURCE_SCOPE_VIOLATION,
                    "current administrative filters cannot be combined with the "
                    "selected source area")

        supplied = args.get("source_scope")
        if supplied is not None and not _same_selection(supplied, self.selection):
            return self._reject(
                SOURCE_SELECTION_MISMATCH,
                "the tool argument selector differs from the request selection")

        # Server-side authority: the exact selection is injected, never inferred.
        args["source_scope"] = grounding.copy_source_selection(self.selection)
        args.pop("source_snapshot", None)
        return Decision(True, args=args)

    def _prepare_details(self, args: Dict[str, Any]) -> Decision:
        poi_id = grounding.nonblank_str(args.get("poi_id"))
        if poi_id is None:
            return self._reject("invalid_request", "poi_id must be a nonblank string")
        if self.source_mode and poi_id not in (self.discovered_ids
                                               | self.verified_ids):
            return self._reject(
                UNVERIFIED_POI_ID,
                "poi_id was not returned by a source-scoped explore call")
        args["poi_id"] = poi_id
        return Decision(True, args=args)

    def _prepare_route(self, args: Dict[str, Any]) -> Decision:
        ordered = args.get("ordered_poi_ids")
        if not isinstance(ordered, list) or len(ordered) < 2:
            return self._reject(INVALID_ROUTE_REQUEST,
                                "an itinerary needs at least two stops")
        if len(ordered) > MAX_ROUTE_STOPS:
            return self._reject(INVALID_ROUTE_REQUEST,
                                "the itinerary has too many stops")
        ids: List[str] = []
        for raw in ordered:
            poi_id = grounding.nonblank_str(raw)
            if poi_id is None:
                return self._reject(INVALID_ROUTE_REQUEST,
                                    "every stop must be a nonblank string id")
            ids.append(poi_id)
        if len(set(ids)) != len(ids):
            return self._reject(INVALID_ROUTE_REQUEST,
                                "every route stop must be distinct")

        vehicle = args.get("vehicle", self.transport_mode)
        if type(vehicle) is not str or vehicle != self.transport_mode:
            return self._reject(
                TRANSPORT_MODE_MISMATCH,
                "the route profile must equal the explicit request travel mode")
        if self.source_mode:
            unverified = [pid for pid in ids if pid not in self.verified_ids]
            if unverified:
                return self._reject(
                    ROUTE_IDS_UNVERIFIED,
                    "every route stop must be a detail-verified in-scope POI")

        args["ordered_poi_ids"] = ids
        args["vehicle"] = self.transport_mode
        if len(self.route_calls) < MAX_RECORDED_ROUTES:
            self.route_calls.append({
                "stop_count": len(ids),
                "vehicle": self.transport_mode,
                "success": None,
            })
        return Decision(True, args=args)

    # ------------------------------------------------------------------
    # Result gating
    # ------------------------------------------------------------------
    def filter_result(self, name: str, args: Dict[str, Any], raw: Any) -> Any:
        """Return the only evidence the model/trace/memory may see."""
        outcome = grounding.parse_mcp_tool_result(raw)
        if name == ROUTE_TOOL:
            return self._filter_route(outcome, args, raw)
        if not outcome.ok or not self.source_mode:
            return raw
        if name == EXPLORE_TOOL:
            return self._filter_explore(outcome.data or {})
        if name == DETAILS_TOOL:
            return self._filter_details(outcome.data or {},
                                        grounding.nonblank_str(args.get("poi_id")))
        return raw

    def _filter_explore(self, data: Dict[str, Any]) -> Any:
        echo = data.get("source_scope")
        if isinstance(echo, dict) and not _same_selection(echo, self.selection):
            return self.rejection_result(self._reject(
                SOURCE_SELECTION_MISMATCH,
                "the tool response describes a different source selection"))

        results = data.get("results")
        if not isinstance(results, list):
            return self._result_from_payload(data, filtered=0)

        kept: List[Dict[str, Any]] = []
        dropped = 0
        for item in results:
            poi_id = (grounding.nonblank_str(item.get("id"))
                      if isinstance(item, dict) else None)
            if poi_id is None:
                dropped += 1
                continue
            status = grounding.poi_source_scope_status(item, self.selection)
            if status != "qualified":
                dropped += 1
                continue
            kept.append(item)
            self.discovered_ids.add(poi_id)

        self.filtered_entries += dropped
        payload = dict(data)
        payload["results"] = kept
        payload["count"] = len(kept)
        payload["filtered_out_of_scope"] = dropped
        return self._result_from_payload(payload, filtered=dropped)

    def _filter_details(self, data: Dict[str, Any],
                        requested_id: Optional[str]) -> Any:
        record = data.get("result")
        if requested_id is None or not isinstance(record, dict):
            return self.rejection_result(self._reject(
                SOURCE_SCOPE_VIOLATION,
                "the detail response carries no usable in-scope record"))
        returned_id = grounding.nonblank_str(record.get("POI_ID"))
        if returned_id != requested_id:
            return self.rejection_result(self._reject(
                SOURCE_SCOPE_VIOLATION,
                "the detail response does not describe the requested POI"))
        if grounding.poi_source_scope_status(record, self.selection) != "qualified":
            return self.rejection_result(self._reject(
                SOURCE_SCOPE_VIOLATION,
                "the detail record does not match the selected source area"))

        self.verified_ids.add(requested_id)
        allowed = self.discovered_ids | self.verified_ids
        filtered: List[Dict[str, Any]] = []
        dropped = 0
        nearby = record.get("NEAR_BY")
        if isinstance(nearby, list):
            for entry in nearby:
                poi = entry.get("poi") if isinstance(entry, dict) else None
                nearby_id = (grounding.nonblank_str(poi.get("id"))
                             if isinstance(poi, dict) else None)
                if nearby_id is not None and nearby_id in allowed:
                    filtered.append(entry)
                else:
                    dropped += 1
        self.filtered_entries += dropped

        sanitized = dict(record)
        if isinstance(nearby, list):
            sanitized["NEAR_BY"] = filtered
            sanitized["nearby_filtered_out_of_scope"] = dropped
        payload = dict(data)
        payload["result"] = sanitized
        return self._result_from_payload(payload, filtered=dropped)

    def _record_route_attempt(self, success: bool,
                              error_code: Optional[str] = None) -> None:
        if self.route_calls:
            self.route_calls[-1]["success"] = success
            if error_code is not None:
                self.route_calls[-1]["error_code"] = error_code

    @staticmethod
    def _finite_nonnegative(value: Any) -> Optional[float]:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        number = float(value)
        if not math.isfinite(number) or number < 0:
            return None
        return number

    @staticmethod
    def _finite_number(value: Any) -> Optional[float]:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        number = float(value)
        return number if math.isfinite(number) else None

    def _validate_route(self, data: Dict[str, Any],
                        args: Dict[str, Any]) -> Tuple[
                            Optional[str], Optional[Dict[str, Any]]]:
        """Return ``(error_code, evidence)``; never infer or fill a route."""
        ordered = args.get("ordered_poi_ids")
        vehicle = args.get("vehicle")
        if not isinstance(ordered, list) or len(ordered) < 2:
            return "route_invalid_request", None
        if vehicle != self.transport_mode:
            return "transport_mode_mismatch", None
        if len(set(ordered)) != len(ordered):
            return "route_invalid_request", None
        if any(pid not in self.verified_ids for pid in ordered):
            return "route_ids_unverified", None
        if data.get("success") is not True:
            return "route_not_success", None

        distance = self._finite_nonnegative(data.get("distance_km"))
        duration = self._finite_nonnegative(data.get("time_minutes"))
        if distance is None or duration is None:
            return "route_invalid_numeric", None

        stops = data.get("stops")
        if not isinstance(stops, list) or len(stops) != len(ordered):
            return "route_stops_mismatch", None
        mapped = data.get("stops_mapped")
        if isinstance(mapped, bool) or not isinstance(mapped, int) \
                or mapped != len(stops) or mapped < 2:
            return "route_stops_mismatch", None

        ids: List[str] = []
        coordinates: List[Dict[str, Any]] = []
        for item in stops:
            if not isinstance(item, dict):
                return "route_stops_mismatch", None
            poi_id = grounding.nonblank_str(item.get("id"))
            latitude = self._finite_number(item.get("latitude"))
            longitude = self._finite_number(item.get("longitude"))
            if poi_id is None or latitude is None or longitude is None \
                    or not (-90.0 <= latitude <= 90.0) \
                    or not (-180.0 <= longitude <= 180.0):
                return "route_stops_mismatch", None
            ids.append(poi_id)
            coordinates.append({
                "id": poi_id,
                "latitude": latitude,
                "longitude": longitude,
            })
        if ids != ordered or len(set(ids)) < 2:
            return "route_stops_mismatch", None

        return None, {
            "tool": ROUTE_TOOL,
            "origin": "mcp",
            "ordered_poi_ids": list(ordered),
            "vehicle": self.transport_mode,
            "distance_km": distance,
            "time_minutes": duration,
            "stops_mapped": mapped,
            "stops": coordinates,
            "source_scope": (grounding.copy_source_selection(self.selection)
                             if self.selection else None),
            "success": True,
        }

    @staticmethod
    def _model_route_payload(data: Dict[str, Any]) -> Any:
        """Model-facing route payload without the provider polyline.

        The chat model only needs distance/time/stops/instructions and the
        route-validity metadata. The raw GeoJSON LineString is planner
        material: ``planning_adapter.collect_route_edges`` reads it straight
        from the MCP result, so removing it here changes neither route evidence
        nor ``get_itinerary_route``. Every other field is preserved verbatim.
        """
        sanitized = dict(data)
        sanitized.pop("route_geometry", None)
        return ScopeGate._result_from_payload(sanitized, filtered=0)

    def _filter_route(self, outcome: grounding.ToolOutcome,
                      args: Dict[str, Any], raw: Any) -> Any:
        # Genuine tool errors and non-route payloads stay byte-identical.
        if not outcome.ok:
            if self.source_mode:
                self._record_route_attempt(False, "route_not_success")
            return raw
        data = outcome.data if isinstance(outcome.data, dict) else {}
        if data.get("success") is not True:
            if self.source_mode:
                self._record_route_attempt(False, "route_not_success")
            return raw

        # Validation always reads the original payload (geometry included).
        if self.source_mode:
            error_code, evidence = self._validate_route(data, args)
            if error_code is not None:
                self._record_route_attempt(False, error_code)
                return self._model_route_payload(data)
            self._record_route_attempt(True)
            self.route_evidence = evidence
        return self._model_route_payload(data)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _result_from_payload(payload: Dict[str, Any], *, filtered: int) -> Any:
        text = json.dumps(payload, ensure_ascii=False)
        return _ToolResult(text)

    def rejection_result(self, decision: Decision) -> Any:
        """A structured, non-grounded tool failure (never model evidence)."""
        return _ToolResult(json.dumps({
            "success": False,
            "code": decision.code or "scope_violation",
            "detail": decision.detail or "rejected by the server scope gate",
            "scope_enforced": True,
        }))

    def as_meta(self) -> Dict[str, Any]:
        """Bounded, non-secret call metadata for the response/trace."""
        return {
            "mode": (grounding.SOURCE_SCOPE_CONTRACT if self.source_mode
                     else grounding.SCOPE_MODE_CURRENT),
            "source_scope": (grounding.copy_source_selection(self.selection)
                             if self.selection else None),
            "transport_mode": self.transport_mode,
            "discovered_poi_count": len(self.discovered_ids),
            "verified_poi_count": len(self.verified_ids),
            "filtered_out_of_scope": self.filtered_entries,
            "rejections": list(self.rejections),
            "route_calls": list(self.route_calls),
            "route_evidence": (dict(self.route_evidence)
                               if self.route_evidence is not None else None),
        }
