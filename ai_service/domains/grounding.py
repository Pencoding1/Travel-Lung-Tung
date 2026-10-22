"""Grounding boundary for the itinerary endpoint (OC-005).

This module contains *pure* validation/reconstruction logic. It performs no
network, MCP, graph or model calls. ``main.py`` is responsible for I/O; every
external response is passed through the parsers below before it can influence a
response, so no unverified tool output is ever treated as fact.

Design constraints (see docs/decisions/004-itinerary-grounding.md):

* Existence of a POI and correctness of its attributes are separate claims.
* Scope is decided from a *structured* ``administrative_context`` on the
  enrichment payload, never from free-text address substrings.
* Only fields that came back from ``get_poi_details`` may be reconstructed into
  the plan; model-supplied names/coordinates/hours/prices/addresses/descriptions
  are never copied.
* Missing evidence stays ``None``/empty and is listed in ``missing_data``.
* A fallback ``rating`` of ``0`` is *not* a verified rating, and no rating
  provider is invented.
* Budgets are estimates, never verified prices.
* Route and opening-hours feasibility stay ``unverified`` while the respective
  data/integration is absent.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Bounds (domain invariants; documented in ADR 004)
# ---------------------------------------------------------------------------
MIN_DURATION_DAYS = 1
MAX_DURATION_DAYS = 14
MIN_TRAVELERS = 1
MAX_TRAVELERS = 50
MAX_CATEGORIES = 8
MAX_CANDIDATES = 18

# ---------------------------------------------------------------------------
# Explicit source-snapshot scope (T049 AI/planner retention)
# ---------------------------------------------------------------------------
SCOPE_MODE_CURRENT = "current_administration"
SOURCE_SCOPE_CONTRACT = "source_snapshot_area"
SOURCE_QUALIFICATION = "exact_source_snapshot_tuple"
SOURCE_ADMIN_STATUS = "unverified_source_area"
SOURCE_ADMIN_SCOPE = "source_snapshot_area_only"

SOURCE_SELECTION_FIELDS = ("dataset_namespace", "input_sha256", "source_area_id")
SOURCE_SELECTION_MULTI_FIELDS = (
    "dataset_namespace", "input_sha256", "source_area_ids")
SOURCE_AREA_IDS_MAX = 64
SOURCE_AREA_ID_RE = re.compile(r"^source_area_v1:[0-9a-f]{64}$")
SOURCE_INPUT_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

SOURCE_CONTEXT_REQUIRED_FIELDS = frozenset({
    "dataset_namespace",
    "input_sha256",
    "source_area_id",
    "source_area_label",
    "area_assignment",
    "current_admin_status",
    "current_boundary_uncertainty",
    "lineage_reference",
    "qualification",
})
SOURCE_CONTEXT_OPTIONAL_FIELDS = frozenset({"raw_city", "raw_area"})
SOURCE_CONTEXT_ALLOWED_FIELDS = (
    SOURCE_CONTEXT_REQUIRED_FIELDS | SOURCE_CONTEXT_OPTIONAL_FIELDS
)
# Client-facing plan evidence: the compact claim and its uncertainty, never the
# server-side audit pointer (``lineage_reference``).
SOURCE_PLAN_FIELDS = (
    "dataset_namespace",
    "input_sha256",
    "source_area_id",
    "raw_city",
    "raw_area",
    "source_area_label",
    "area_assignment",
    "current_admin_status",
    "current_boundary_uncertainty",
    "qualification",
)
# Declared destination scope is Vietnam; plan-local naive datetimes are
# interpreted in this fixed offset.
VN_TZ = timezone(timedelta(hours=7))
RATING_PROVIDERS = ("google_maps", "tripadvisor")

# ---------------------------------------------------------------------------
# Error codes (stable, returned to callers instead of raw tracebacks)
# ---------------------------------------------------------------------------
INVALID_REQUEST = "invalid_request"
INSUFFICIENT_DATA = "insufficient_data"
LOCATION_NOT_RESOLVED = "location_not_resolved"
LOCATION_AMBIGUOUS = "location_ambiguous"
LOCATION_TYPE_MISMATCH = "location_type_mismatch"
CATEGORY_DISCOVERY_FAILED = "category_discovery_failed"
CANDIDATE_RETRIEVAL_FAILED = "candidate_retrieval_failed"
ENRICHMENT_FAILED = "enrichment_failed"
ENRICHMENT_MISMATCH = "enrichment_id_mismatch"
SCOPE_CONFLICT = "scope_conflict"
SCOPE_UNVERIFIED = "scope_unverified"
SOURCE_SCOPE_UNVERIFIED = "source_scope_unverified"
BUDGET_INVALID = "budget_invalid"
TOOL_PROTOCOL_ERROR = "tool_protocol_error"
LLM_ERROR = "llm_error"
PLAN_INVALID = "plan_invalid"
UNKNOWN_POI = "unknown_poi"
DUPLICATE_STOPS = "duplicate_stops"
START_END_MISMATCH = "start_end_mismatch"
TIME_ORDER_INVALID = "time_order_invalid"

NEUTRAL_DESCRIPTION = (
    "Stop selected from the verified candidate set retrieved for the requested area."
)

# ---------------------------------------------------------------------------
# Text normalisation / primitive coercion
# ---------------------------------------------------------------------------
def _strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return without_marks.replace("đ", "d").replace("Đ", "D")


def normalize_text(value: Any) -> str:
    """Accent/case/whitespace folded text. ``None`` and non-strings become ""."""
    if value is None:
        return ""
    text = _strip_accents(str(value))
    return " ".join(text.casefold().split())


def normalize_area_token(value: Any) -> str:
    """Normalise an administrative name.

    Explicit ``District``/``Quan``/``Quận`` aliases are folded to the single
    token ``quan`` so that "District 1", "Quan 1" and "Quận 1" compare equal.
    Crucially, "District 1" and "District 10" still compare *different*
    (``quan 1`` vs ``quan 10``).
    """
    normalized = normalize_text(value)
    tokens = normalized.split(" ")
    tokens = ["quan" if tok == "district" else tok for tok in tokens]
    return " ".join(tokens)


def nonblank_str(value: Any) -> Optional[str]:
    """Return ``value`` only if it is an actual nonblank ``str``.

    Rejects ``None``, bools, ints, lists, dicts and whitespace-only strings.
    """
    if isinstance(value, str) and value.strip():
        return value
    return None


def _as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


# ---------------------------------------------------------------------------
# MCP tool envelope parsing
# ---------------------------------------------------------------------------
class ToolOutcome:
    """Uniform result of parsing one MCP tool call."""

    __slots__ = ("ok", "data", "code", "detail")

    def __init__(self, ok: bool, data: Any = None, code: Optional[str] = None,
                 detail: Optional[str] = None):
        self.ok = ok
        self.data = data
        self.code = code
        self.detail = detail

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"ToolOutcome(ok={self.ok!r}, code={self.code!r}, detail={self.detail!r})"


def _extract_text(result: Any) -> Tuple[Optional[str], Optional[str]]:
    """Return (text, error). Handles non-dict content items conservatively."""
    content = getattr(result, "content", None)
    if not content:
        return None, "empty tool content"
    first = content[0]
    text = getattr(first, "text", None)
    if text is None:
        return None, "tool content item is not textual"
    return text, None


def parse_mcp_tool_result(result: Any) -> ToolOutcome:
    """Parse a ``CallToolResult``.

    Rejects: missing result, transport failure, empty content, non-textual
    content, malformed JSON, non-dict payloads, and a payload with ``success``
    explicitly ``False``.
    """
    if result is None:
        return ToolOutcome(False, code=TOOL_PROTOCOL_ERROR, detail="no tool result")

    is_error = bool(getattr(result, "isError", False))
    text, extract_error = _extract_text(result)
    if extract_error:
        return ToolOutcome(False, code=TOOL_PROTOCOL_ERROR, detail=extract_error)

    if is_error:
        return ToolOutcome(False, code=TOOL_PROTOCOL_ERROR,
                           detail="tool reported isError")

    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return ToolOutcome(False, code=TOOL_PROTOCOL_ERROR, detail="malformed tool JSON")

    if not isinstance(payload, dict):
        return ToolOutcome(False, code=TOOL_PROTOCOL_ERROR,
                           detail="tool payload is not a JSON object")

    if payload.get("success") is False:
        detail = str(payload.get("detail") or payload.get("message") or "success=false")
        return ToolOutcome(False, data=payload, code="success_false", detail=detail)

    return ToolOutcome(True, data=payload)


# ---------------------------------------------------------------------------
# Geographic resolution
# ---------------------------------------------------------------------------
def _parent_city(match: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Preserve optional resolver-provided parent city info on a district match."""
    for id_key, name_key in (("city_id", "city_name"),
                             ("parent_city_id", "parent_city_name")):
        city_id = nonblank_str(match.get(id_key))
        if city_id:
            return city_id, nonblank_str(match.get(name_key))
    return None, None


def select_unique_area(matches: Any, requested: Any,
                       expected_type: str) -> ToolOutcome:
    """Select a unique normalized exact match of ``requested`` and type.

    Only records carrying a valid nonblank string ``id`` are considered, so an
    invalid record preceding a valid one cannot be selected. Resolver-provided
    parent city info is preserved when present.
    """
    if not isinstance(matches, list):
        return ToolOutcome(False, code=LOCATION_NOT_RESOLVED,
                           detail="no location matches returned")

    norm_requested = normalize_area_token(requested)
    if not norm_requested:
        return ToolOutcome(False, code=INVALID_REQUEST,
                           detail="requested area is blank")

    exact = [
        m for m in matches
        if isinstance(m, dict)
        and normalize_area_token(m.get("name")) == norm_requested
    ]
    typed = [
        m for m in exact
        if normalize_text(m.get("type")) == normalize_text(expected_type)
    ]

    by_id: Dict[str, Dict[str, Any]] = {}
    for match in typed:
        match_id = nonblank_str(match.get("id"))
        if match_id is not None and match_id not in by_id:
            by_id[match_id] = match

    if len(by_id) == 1:
        match_id, match = next(iter(by_id.items()))
        parent_city_id, parent_city_name = _parent_city(match)
        return ToolOutcome(True, {
            "id": match_id,
            "name": match.get("name"),
            "type": match.get("type"),
            "parent_city_id": parent_city_id,
            "parent_city_name": parent_city_name,
        })
    if len(by_id) > 1:
        return ToolOutcome(False, code=LOCATION_AMBIGUOUS,
                           detail=f"multiple {expected_type} matches for '{requested}'")
    if exact and not typed:
        return ToolOutcome(False, code=LOCATION_TYPE_MISMATCH,
                           detail=f"'{requested}' matched a non-{expected_type} entity")
    return ToolOutcome(False, code=LOCATION_NOT_RESOLVED,
                       detail=f"no exact {expected_type} match for '{requested}'")


# ---------------------------------------------------------------------------
# Category discovery + candidate retrieval
# ---------------------------------------------------------------------------
def parse_categories(outcome: ToolOutcome) -> ToolOutcome:
    """Validate and deterministically order the ``get_available_categories`` payload."""
    if not outcome.ok:
        return ToolOutcome(False, code=CATEGORY_DISCOVERY_FAILED, detail=outcome.detail)
    data = outcome.data or {}
    raw = data.get("categories")
    if not isinstance(raw, list):
        return ToolOutcome(False, code=CATEGORY_DISCOVERY_FAILED,
                           detail="categories payload missing list")
    categories: List[Dict[str, str]] = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        cid = nonblank_str(item.get("id"))
        if cid is None or cid in seen:
            continue
        seen.add(cid)
        name = nonblank_str(item.get("name")) or ""
        categories.append({"id": cid, "name": name})
    if not categories:
        return ToolOutcome(False, code=CATEGORY_DISCOVERY_FAILED,
                           detail="no valid categories discovered")
    # Deterministic: sort by id before applying the cap so the selected subset
    # does not depend on MCP response ordering.
    categories.sort(key=lambda c: c["id"])
    return ToolOutcome(True, categories[:MAX_CATEGORIES])


def parse_explore(outcome: ToolOutcome) -> ToolOutcome:
    if not outcome.ok:
        return ToolOutcome(False, code=CANDIDATE_RETRIEVAL_FAILED, detail=outcome.detail)
    data = outcome.data or {}
    results = data.get("results")
    if not isinstance(results, list):
        return ToolOutcome(False, code=CANDIDATE_RETRIEVAL_FAILED,
                           detail="explore payload missing results list")
    candidates = []
    for poi in results:
        if not isinstance(poi, dict):
            continue
        pid = nonblank_str(poi.get("id")) or nonblank_str(poi.get("POI_ID"))
        if pid is not None:
            candidates.append({"id": pid, "raw": poi})
    return ToolOutcome(True, candidates)


def collect_candidate_ids(per_category: List[List[Dict[str, Any]]],
                          cap: int = MAX_CANDIDATES) -> List[str]:
    """Deterministic de-duplication + sort + cap.

    Sorting the unique ids makes the selected subset invariant to MCP response
    ordering (permutation of categories or candidates yields the same subset).
    """
    unique = set()
    for group in per_category:
        for poi in group:
            pid = nonblank_str(poi.get("id"))
            if pid is not None:
                unique.add(pid)
    return sorted(unique)[:cap]


def parse_enrichment(outcome: ToolOutcome, requested_id: str) -> ToolOutcome:
    """Validate an enrichment result against the requested id.

    Requires: parseable envelope, a ``result`` object with a valid nonblank
    ``POI_ID`` exactly equal to ``requested_id``, and coordinates that are
    absent or finite and in range. Unusable evidence is rejected so it is never
    propagated.
    """
    if not outcome.ok:
        return ToolOutcome(False, code=ENRICHMENT_FAILED, detail=outcome.detail)
    data = outcome.data or {}
    result = data.get("result")
    if not isinstance(result, dict):
        return ToolOutcome(False, code=ENRICHMENT_FAILED,
                           detail="enrichment payload missing result object")
    returned_id = nonblank_str(result.get("POI_ID"))
    if returned_id is None:
        return ToolOutcome(False, code=ENRICHMENT_FAILED,
                           detail="enrichment result missing POI_ID")
    if returned_id != requested_id:
        return ToolOutcome(False, code=ENRICHMENT_MISMATCH,
                           detail="enrichment returned a different POI_ID")

    for field, lo, hi in (("latitude", -90.0, 90.0), ("longitude", -180.0, 180.0)):
        raw = result.get(field)
        if raw is None:
            continue
        number = _as_float(raw)
        if number is None or not (lo <= number <= hi):
            return ToolOutcome(False, code=ENRICHMENT_FAILED,
                               detail=f"unusable {field} in enrichment")
    return ToolOutcome(True, result)


def build_enriched_index(outcomes: List[Tuple[str, ToolOutcome]]
                         ) -> Dict[str, Dict[str, Any]]:
    """Map requested poi id -> evidence result, only for successful enrichments.

    The evidence is always keyed by the *requested* id (and ``parse_enrichment``
    has already verified the returned id equals it).
    """
    index: Dict[str, Dict[str, Any]] = {}
    for requested_id, outcome in outcomes:
        if not outcome.ok or not isinstance(outcome.data, dict):
            continue
        index[requested_id] = outcome.data
    return index


# ---------------------------------------------------------------------------
# Scope evidence (structured contract only)
# ---------------------------------------------------------------------------
def poi_scope_status(evidence: Dict[str, Any], district: Dict[str, Any],
                     city: Dict[str, Any]) -> str:
    """Classify a POI's parent context from structured evidence.

    Requires ``evidence["administrative_context"]`` with nonblank string
    ``city_id``, ``district_id``, ``city_name`` and ``district_name``. Scope is
    verified only when the ids match the resolved geography exactly and the
    names match under ``District``/``Quan`` normalization; otherwise it is a
    ``conflict``. Missing/invalid context is ``unknown``. Free-text address
    substrings are never used.
    """
    admin = evidence.get("administrative_context")
    if not isinstance(admin, dict):
        return "unknown"
    district_id = nonblank_str(admin.get("district_id"))
    city_id = nonblank_str(admin.get("city_id"))
    district_name = nonblank_str(admin.get("district_name"))
    city_name = nonblank_str(admin.get("city_name"))
    if not (district_id and city_id and district_name and city_name):
        return "unknown"

    resolved_district_id = nonblank_str(district.get("id"))
    resolved_city_id = nonblank_str(city.get("id"))
    if district_id == resolved_district_id \
            and city_id == resolved_city_id \
            and normalize_area_token(district_name) == normalize_area_token(district.get("name")) \
            and normalize_text(city_name) == normalize_text(city.get("name")):
        return "verified"
    return "conflict"


# ---------------------------------------------------------------------------
# Explicit source-snapshot scope (pure, fail-closed)
# ---------------------------------------------------------------------------
def _request_field(request: Any, name: str) -> Any:
    if isinstance(request, dict):
        return request.get(name)
    return getattr(request, name, None)


def request_scope_mode(request: Any) -> str:
    """The one mode switch: only a supplied ``source_scope`` selects source mode."""
    if _request_field(request, "source_scope") is not None:
        return SOURCE_SCOPE_CONTRACT
    return SCOPE_MODE_CURRENT


def parse_source_selection(value: Any) -> ToolOutcome:
    """Validate and return the exact canonical selection (no normalisation).

    Accepts exactly one selector: legacy ``source_area_id`` or the alternate
    concrete ``source_area_ids`` list. Rejects missing/both selectors, extra
    keys, non-string values, bools, uppercase/malformed hashes, sentinels such
    as ``*``/``ALL``, current administrative ids, blank values and a namespace
    with leading/trailing whitespace. Multi ids are sorted for stable equality;
    duplicates are rejected rather than silently widened. The AI never derives
    an id; it only transports the selector produced by server discovery.
    """
    if value is None:
        return ToolOutcome(False, code=INVALID_REQUEST,
                           detail="source_scope is required for source mode")
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            value = model_dump()
        except Exception:  # noqa: BLE001 - malformed request object
            return ToolOutcome(False, code=INVALID_REQUEST,
                               detail="source_scope could not be read")
    if not isinstance(value, dict):
        return ToolOutcome(False, code=INVALID_REQUEST,
                           detail="source_scope must be a typed object")

    keys = set(value.keys())
    single = keys == set(SOURCE_SELECTION_FIELDS)
    multi = keys == set(SOURCE_SELECTION_MULTI_FIELDS)
    if not single and not multi:
        return ToolOutcome(
            False, code=INVALID_REQUEST,
            detail="source_scope must contain exactly dataset_namespace, "
                   "input_sha256 and one of source_area_id or source_area_ids")

    namespace = value["dataset_namespace"]
    input_sha256 = value["input_sha256"]
    for field, raw in (("dataset_namespace", namespace),
                       ("input_sha256", input_sha256)):
        if isinstance(raw, bool) or not isinstance(raw, str) or not raw:
            return ToolOutcome(False, code=INVALID_REQUEST,
                               detail=f"source_scope.{field} must be a nonblank string")
    if not namespace.strip() or namespace != namespace.strip():
        return ToolOutcome(
            False, code=INVALID_REQUEST,
            detail="source_scope.dataset_namespace must be nonblank without "
                   "leading/trailing whitespace")
    if not SOURCE_INPUT_SHA256_RE.fullmatch(input_sha256):
        return ToolOutcome(
            False, code=INVALID_REQUEST,
            detail="source_scope.input_sha256 must be a lowercase 64-character "
                   "SHA256 hex digest")

    if single:
        area_id = value["source_area_id"]
        if isinstance(area_id, bool) or not isinstance(area_id, str) or not area_id:
            return ToolOutcome(False, code=INVALID_REQUEST,
                               detail="source_scope.source_area_id must be a "
                                      "nonblank string")
        if not SOURCE_AREA_ID_RE.fullmatch(area_id):
            return ToolOutcome(
                False, code=INVALID_REQUEST,
                detail="source_scope.source_area_id must use the "
                       "source_area_v1:<64 lowercase hex> form")
        return ToolOutcome(True, data={
            "dataset_namespace": namespace,
            "input_sha256": input_sha256,
            "source_area_id": area_id,
        })

    raw_ids = value["source_area_ids"]
    if not isinstance(raw_ids, list):
        return ToolOutcome(False, code=INVALID_REQUEST,
                           detail="source_scope.source_area_ids must be a list")
    if not (1 <= len(raw_ids) <= SOURCE_AREA_IDS_MAX):
        return ToolOutcome(
            False, code=INVALID_REQUEST,
            detail=f"source_scope.source_area_ids must contain 1.."
                   f"{SOURCE_AREA_IDS_MAX} ids")
    ids: List[str] = []
    for item in raw_ids:
        if isinstance(item, bool) or not isinstance(item, str) or not item:
            return ToolOutcome(False, code=INVALID_REQUEST,
                               detail="every source_scope.source_area_ids entry "
                                      "must be a nonblank string")
        if not SOURCE_AREA_ID_RE.fullmatch(item):
            return ToolOutcome(
                False, code=INVALID_REQUEST,
                detail="every source_scope.source_area_ids entry must use the "
                       "source_area_v1:<64 lowercase hex> form")
        ids.append(item)
    if len(set(ids)) != len(ids):
        return ToolOutcome(False, code=INVALID_REQUEST,
                           detail="source_scope.source_area_ids must not contain "
                                  "duplicates")
    return ToolOutcome(True, data={
        "dataset_namespace": namespace,
        "input_sha256": input_sha256,
        "source_area_ids": sorted(ids),
    })


def selection_area_ids(selection: Any) -> frozenset:
    """The concrete selected ids from a canonical (or raw) selection."""
    if not isinstance(selection, dict):
        return frozenset()
    multi = selection.get("source_area_ids")
    if isinstance(multi, list):
        return frozenset(item for item in multi if isinstance(item, str))
    single = selection.get("source_area_id")
    return frozenset({single}) if isinstance(single, str) else frozenset()


def copy_source_selection(selection: Any) -> Optional[Dict[str, Any]]:
    """Return an independent canonical copy (multi list is not aliased)."""
    if not isinstance(selection, dict):
        return None
    copied: Dict[str, Any] = {}
    for field in ("dataset_namespace", "input_sha256"):
        if field in selection:
            copied[field] = selection[field]
    if "source_area_ids" in selection:
        copied["source_area_ids"] = list(selection["source_area_ids"])
    elif "source_area_id" in selection:
        copied["source_area_id"] = selection["source_area_id"]
    return copied


def _source_context_type_error(context: Dict[str, Any]) -> bool:
    for field in ("dataset_namespace", "input_sha256", "source_area_id",
                  "source_area_label", "current_boundary_uncertainty",
                  "lineage_reference"):
        if nonblank_str(context.get(field)) is None:
            return True
    for field in ("raw_city", "raw_area"):
        value = context.get(field)
        if value is not None and nonblank_str(value) is None:
            return True
    return False


def poi_source_scope_status(evidence: Dict[str, Any],
                            selection: Dict[str, str]) -> str:
    """Classify one record against an explicit source selection.

    ``qualified`` requires the exact transported selector, the server's exact
    qualification markers and a nonblank compact claim. A missing/non-object
    ``source_context`` is ``unknown``; malformed evidence, any selector
    mismatch, an unassigned area or a mixed administrative context is
    ``conflict``. Display labels and cached flags alone never qualify a record.
    """
    if not isinstance(evidence, dict):
        return "unknown"
    context = evidence.get("source_context")
    if not isinstance(context, dict):
        return "unknown"

    # Two contracts cannot both be active. A source claim is never verified
    # from an administrative context and vice versa.
    if evidence.get("administrative_context") is not None:
        return "conflict"
    if evidence.get("administrative_context_status") != SOURCE_ADMIN_STATUS:
        return "conflict"
    if evidence.get("administrative_scope") != SOURCE_ADMIN_SCOPE:
        return "conflict"

    keys = set(context.keys())
    if keys - SOURCE_CONTEXT_ALLOWED_FIELDS:
        return "conflict"
    if not SOURCE_CONTEXT_REQUIRED_FIELDS <= keys:
        return "conflict"
    if _source_context_type_error(context):
        return "conflict"

    if context.get("dataset_namespace") != selection.get("dataset_namespace"):
        return "conflict"
    if context.get("input_sha256") != selection.get("input_sha256"):
        return "conflict"
    selected_ids = selection_area_ids(selection)
    if not selected_ids or context.get("source_area_id") not in selected_ids:
        return "conflict"
    if not SOURCE_AREA_ID_RE.fullmatch(context.get("source_area_id") or ""):
        return "conflict"
    if not SOURCE_INPUT_SHA256_RE.fullmatch(context.get("input_sha256") or ""):
        return "conflict"
    if context.get("qualification") != SOURCE_QUALIFICATION:
        return "conflict"
    if context.get("area_assignment") != "qualified":
        return "conflict"
    if not nonblank_str(context.get("raw_city")) \
            or not nonblank_str(context.get("raw_area")):
        return "conflict"
    if context.get("current_admin_status") != SOURCE_ADMIN_STATUS:
        return "conflict"
    return "qualified"


def source_snapshot_area_for_plan(context: Dict[str, Any]) -> Dict[str, Any]:
    """Compact claim exposed on every selected stop (no audit pointer)."""
    return {field: context.get(field) for field in SOURCE_PLAN_FIELDS}


def compact_source_prompt_fact(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Model-facing POI facts for source mode.

    Keeps real POI data and the readable source label, but removes stored
    provenance blobs, audit references and all current administrative fields.
    """
    context = evidence.get("source_context")
    label = nonblank_str(context.get("source_area_label")) \
        if isinstance(context, dict) else None
    categories: List[str] = []
    for ref in evidence.get("POI_Categories") or []:
        if isinstance(ref, dict):
            category_id = nonblank_str(ref.get("id"))
            if category_id is not None and category_id not in categories:
                categories.append(category_id)
    return {
        "POI_ID": nonblank_str(evidence.get("POI_ID")),
        "POI_Name": nonblank_str(evidence.get("POI_Name")),
        "POI_Address": nonblank_str(evidence.get("POI_Address")),
        "POI_Category": nonblank_str(evidence.get("POI_Category")),
        "latitude": evidence.get("latitude"),
        "longitude": evidence.get("longitude"),
        "operation_time": evidence.get("operation_time"),
        "POI_Description": evidence.get("POI_Description"),
        "POI_Contact_Info": evidence.get("POI_Contact_Info"),
        "Offers": evidence.get("Offers"),
        "POI_Categories": categories,
        "source_area_label": label,
    }


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------
def validate_request(request: Any) -> List[Dict[str, str]]:
    """Return a list of ``{"field", "code"}`` for invalid requests (empty = ok)."""
    errors: List[Dict[str, str]] = []

    def get(name):
        if isinstance(request, dict):
            return request.get(name)
        return getattr(request, name, None)

    source_scope = get("source_scope")
    source_mode = source_scope is not None
    if source_mode:
        if not parse_source_selection(source_scope).ok:
            errors.append({"field": "source_scope",
                           "code": "invalid_source_scope"})

    for field in ("session_id", "current_city", "target_district",
                  "travel_type", "budget_range", "start_date"):
        if field == "target_district" and source_mode:
            # A legacy target label may be carried but is never an active
            # filter in source mode; it is not required there.
            continue
        if not normalize_text(get(field)):
            errors.append({"field": field, "code": "blank"})

    duration = get("duration_days")
    if not isinstance(duration, int) or isinstance(duration, bool):
        errors.append({"field": "duration_days", "code": "not_integer"})
    elif not (MIN_DURATION_DAYS <= duration <= MAX_DURATION_DAYS):
        errors.append({"field": "duration_days", "code": "out_of_range"})

    travelers = get("num_travelers")
    if not isinstance(travelers, int) or isinstance(travelers, bool):
        errors.append({"field": "num_travelers", "code": "not_integer"})
    elif not (MIN_TRAVELERS <= travelers <= MAX_TRAVELERS):
        errors.append({"field": "num_travelers", "code": "out_of_range"})

    start_date = get("start_date")
    if normalize_text(start_date) and not _is_iso_date(start_date):
        errors.append({"field": "start_date", "code": "invalid_iso_date"})

    return errors


def _is_iso_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value.strip())
        return True
    except ValueError:
        return False


def _parse_aware(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def trip_window(start_date: Any, duration_days: Any) -> Optional[Tuple[datetime, datetime]]:
    """Return ``(start, end)`` in Vietnam time for the requested trip window."""
    if not _is_iso_date(start_date):
        return None
    if not isinstance(duration_days, int) or isinstance(duration_days, bool):
        return None
    start = datetime.combine(date.fromisoformat(start_date), time.min, tzinfo=VN_TZ)
    return start, start + timedelta(days=duration_days)


# ---------------------------------------------------------------------------
# Plan validation + reconstruction
# ---------------------------------------------------------------------------
class PlanResult:
    __slots__ = ("ok", "code", "message", "stops", "missing_data", "notes",
                 "scope_verifications", "total_estimated_budget")

    def __init__(self, ok, code=None, message=None, stops=None,
                 missing_data=None, notes=None, scope_verifications=None,
                 total_estimated_budget=None):
        self.ok = ok
        self.code = code
        self.message = message
        self.stops = stops or []
        self.missing_data = missing_data or []
        self.notes = notes or []
        self.scope_verifications = scope_verifications or []
        self.total_estimated_budget = total_estimated_budget


def _coordinate(value: Any, lo: float, hi: float) -> Optional[float]:
    number = _as_float(value)
    if number is None or not (lo <= number <= hi):
        return None
    return number


def _reconstruct_rating(ev: Dict[str, Any], missing: List[str],
                        prefix: str) -> Optional[Dict[str, float]]:
    """Only explicit, per-provider ratings are accepted.

    The generic ``POI_Description.review.rating`` (whose Document-RAG fallback
    is ``0.0``) is never promoted to a named provider. A rating provider is only
    emitted when ``rating_sources`` explicitly names a supported provider with a
    positive finite value.
    """
    sources = ev.get("rating_sources")
    ratings: Dict[str, float] = {}
    if isinstance(sources, dict):
        for provider, value in sources.items():
            if provider not in RATING_PROVIDERS:
                continue
            number = _as_float(value)
            if number is not None and number > 0:
                ratings[provider] = number
    if not ratings:
        missing.append(f"{prefix}.rating")
        return None
    return ratings


def _reconstruct_contact(ev: Dict[str, Any], missing: List[str],
                         prefix: str) -> Optional[Dict[str, Any]]:
    contact = ev.get("POI_Contact_Info")
    if not isinstance(contact, dict):
        missing.append(f"{prefix}.contact_info")
        return None
    phone = nonblank_str(contact.get("phonenumber"))
    fanpage = nonblank_str(contact.get("fanpage"))
    website = nonblank_str(contact.get("website"))
    if not (phone or fanpage or website):
        missing.append(f"{prefix}.contact_info")
        return None
    return {"phone_number": phone, "fanpage": fanpage, "website": website}


def _reconstruct_menu(ev: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Offers are upstream data with no provenance; a price is only surfaced
    when it is a positive finite number, and is never labelled verified."""
    menu: List[Dict[str, Any]] = []
    offers = ev.get("Offers")
    if not isinstance(offers, list):
        return menu
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        name = nonblank_str(offer.get("name"))
        price = _as_float(offer.get("price"))
        if price is not None and price <= 0:
            price = None
        if name is None and price is None:
            continue
        menu.append({
            "id": None,
            "price": price,
            "product_name": name,
            "price_verified": False,
        })
    return menu


def _reconstruct_address(ev: Dict[str, Any], admin: Dict[str, Any],
                         missing: List[str], prefix: str) -> Dict[str, Any]:
    street = nonblank_str(ev.get("POI_Address"))
    if street is None:
        missing.append(f"{prefix}.address.street_name")
    return {
        "street_name": street,
        "ward": None,
        "district": nonblank_str(admin.get("district_name")),
        "city": nonblank_str(admin.get("city_name")),
        "nation": None,
    }


def _reconstruct_source_address(ev: Dict[str, Any], missing: List[str],
                                prefix: str) -> Dict[str, Any]:
    """Source mode: no current city/district is fabricated from labels/ids."""
    street = nonblank_str(ev.get("POI_Address"))
    if street is None:
        missing.append(f"{prefix}.address.street_name")
    missing.append(f"{prefix}.address.district")
    missing.append(f"{prefix}.address.city")
    return {
        "street_name": street,
        "ward": None,
        "district": None,
        "city": None,
        "nation": None,
    }


def _reconstruct_poi(ev: Dict[str, Any], admin: Optional[Dict[str, Any]],
                     missing: List[str], prefix: str,
                     source_context: Optional[Dict[str, Any]] = None
                     ) -> Dict[str, Any]:
    poi_id = nonblank_str(ev.get("POI_ID"))
    name = nonblank_str(ev.get("POI_Name"))
    if name is None:
        missing.append(f"{prefix}.name")

    category_name = nonblank_str(ev.get("POI_Category"))
    categories: List[Dict[str, Any]] = []
    if category_name is not None:
        categories = [{"id": None, "name": category_name, "context": None}]
    else:
        missing.append(f"{prefix}.poi_categories")

    operation_time = nonblank_str(ev.get("operation_time"))
    if operation_time is None:
        missing.append(f"{prefix}.operation_time")

    longitude = _coordinate(ev.get("longitude"), -180.0, 180.0)
    latitude = _coordinate(ev.get("latitude"), -90.0, 90.0)
    if longitude is None:
        missing.append(f"{prefix}.longitude")
    if latitude is None:
        missing.append(f"{prefix}.latitude")

    if source_context is not None:
        address = _reconstruct_source_address(ev, missing, prefix)
    else:
        address = _reconstruct_address(ev, admin or {}, missing, prefix)

    payload = {
        "id": poi_id,
        "name": name,
        "poi_categories": categories,
        "tag": None,
        "longitude": longitude,
        "latitude": latitude,
        "address": address,
        "contact_info": _reconstruct_contact(ev, missing, prefix),
        "operation_time": operation_time,
        "operation_time_feasibility": "unverified",
        "rating": _reconstruct_rating(ev, missing, prefix),
        "menu": _reconstruct_menu(ev),
    }
    if source_context is not None:
        payload["source_snapshot_area"] = source_snapshot_area_for_plan(
            source_context)
        payload["current_admin_status"] = SOURCE_ADMIN_STATUS
    return payload


_BUDGET_TOLERANCE_FLOOR = 1.0
_BUDGET_TOLERANCE_RATIO = 0.01


def validate_and_reconstruct_plan(plan: Any,
                                  enriched_index: Dict[str, Dict[str, Any]],
                                  district: Dict[str, Any],
                                  city: Dict[str, Any],
                                  start_date: Any,
                                  duration_days: Any,
                                  source_selection: Optional[Dict[str, str]] = None
                                  ) -> PlanResult:
    """Validate the model plan and rebuild every factual field from evidence.

    When ``source_selection`` is supplied, every stop is re-qualified against the
    exact source contract and its current city/district stay unverified/None.
    """
    if not isinstance(plan, dict):
        return PlanResult(False, PLAN_INVALID, "plan is not a JSON object")

    if source_selection is not None:
        parsed = parse_source_selection(source_selection)
        if not parsed.ok:
            return PlanResult(False, INVALID_REQUEST,
                              "source_selection is not a valid typed selector")
        source_selection = parsed.data

    window = trip_window(start_date, duration_days)
    if window is None:
        return PlanResult(False, PLAN_INVALID, "trip window is not defined")
    trip_start, trip_end = window

    stops = plan.get("stops")
    if not isinstance(stops, list) or not stops:
        return PlanResult(False, PLAN_INVALID, "plan has no stops")

    missing: List[str] = []
    notes: List[str] = []
    scope_verifications: List[str] = []
    seen_ids: List[str] = []
    reconstructed: List[Dict[str, Any]] = []
    previous_end: Optional[datetime] = None
    stop_budgets: List[Optional[float]] = []

    for index, stop in enumerate(stops):
        prefix = f"stops[{index}]"
        if not isinstance(stop, dict):
            return PlanResult(False, PLAN_INVALID, f"{prefix} is not an object")

        poi = stop.get("poi")
        if not isinstance(poi, dict):
            return PlanResult(False, PLAN_INVALID, f"{prefix} missing poi")
        poi_id = nonblank_str(poi.get("id"))
        if poi_id is None:
            return PlanResult(False, PLAN_INVALID, f"{prefix} missing poi.id")

        evidence = enriched_index.get(poi_id)
        if evidence is None:
            return PlanResult(False, UNKNOWN_POI, f"unknown POI id '{poi_id}'")

        if source_selection is not None \
                and poi_source_scope_status(evidence, source_selection) != "qualified":
            return PlanResult(
                False, SCOPE_CONFLICT,
                f"{prefix} no longer matches the explicitly selected source "
                "snapshot area")

        if poi_id in seen_ids:
            return PlanResult(False, DUPLICATE_STOPS, f"duplicate stop for '{poi_id}'")
        seen_ids.append(poi_id)

        visit = _parse_aware(stop.get("visit_time"))
        end = _parse_aware(stop.get("end_time"))
        if visit is None or end is None:
            return PlanResult(False, TIME_ORDER_INVALID,
                              f"{prefix} has missing or non-aware ISO timestamps")
        if visit >= end:
            return PlanResult(False, TIME_ORDER_INVALID,
                              f"{prefix} visit_time is not before end_time")
        if visit < trip_start or end > trip_end:
            return PlanResult(False, TIME_ORDER_INVALID,
                              f"{prefix} falls outside the requested trip window")

        stop_date = stop.get("date")
        if not _is_iso_date(stop_date) \
                or date.fromisoformat(stop_date) != visit.astimezone(VN_TZ).date():
            return PlanResult(False, TIME_ORDER_INVALID,
                              f"{prefix} date does not match visit_time")
        if previous_end is not None and visit < previous_end:
            return PlanResult(False, TIME_ORDER_INVALID,
                              f"{prefix} overlaps the previous stop")
        previous_end = end

        raw_budget = stop.get("budget")
        budget: Optional[float] = None
        if raw_budget is not None:
            budget = _as_float(raw_budget)
            if budget is None or budget < 0:
                return PlanResult(False, BUDGET_INVALID,
                                  f"{prefix} has a negative or non-finite budget")
        stop_budgets.append(budget)

        admin = evidence.get("administrative_context")
        if source_selection is not None:
            source_context = evidence.get("source_context")
            if not isinstance(source_context, dict):
                return PlanResult(False, SCOPE_CONFLICT,
                                  f"{prefix} has no compact source_context")
            scope_verifications.append("qualified_source_snapshot_area")
            poi_payload = _reconstruct_poi(
                evidence, None, missing, prefix, source_context=source_context)
        else:
            if not isinstance(admin, dict):
                return PlanResult(False, SCOPE_CONFLICT,
                                  f"{prefix} has no structured administrative_context")
            scope_verifications.append("verified")
            poi_payload = _reconstruct_poi(evidence, admin, missing, prefix)
        reconstructed.append({
            "date": stop_date,
            "visit_time": stop["visit_time"],
            "end_time": stop["end_time"],
            "description": NEUTRAL_DESCRIPTION,
            "description_grounded": False,
            "budget": budget,
            "budget_is_estimate": True,
            "poi": poi_payload,
        })
        notes.append(
            f"{prefix}.description replaced with neutral selection text "
            "(model free text was not grounded).")

    if source_selection is not None:
        notes.append(
            "source_snapshot_area: current city/district are unverified; source "
            "labels are not present-day administrative boundaries.")

    start_id = nonblank_str(plan.get("start_poi_id"))
    end_id = nonblank_str(plan.get("end_poi_id"))
    if start_id is None or end_id is None or start_id != seen_ids[0] \
            or end_id != seen_ids[-1]:
        return PlanResult(False, START_END_MISMATCH,
                          "start_poi_id/end_poi_id do not bound the stop list")

    total_raw = plan.get("total_estimated_budget")
    server_total: Optional[float] = None
    if total_raw is not None:
        total = _as_float(total_raw)
        if total is None or total < 0:
            return PlanResult(False, BUDGET_INVALID,
                              "total_estimated_budget is negative or non-finite")
        server_total = total

    known = [b for b in stop_budgets if b is not None]
    if known:
        computed = float(sum(known))
        if server_total is None:
            server_total = computed
        else:
            tolerance = max(_BUDGET_TOLERANCE_FLOOR, _BUDGET_TOLERANCE_RATIO * abs(computed))
            if abs(server_total - computed) > tolerance:
                return PlanResult(False, BUDGET_INVALID,
                                  "total_estimated_budget does not match stop estimates")
            # Reconcile to the server-computed sum.
            server_total = computed

    return PlanResult(True, stops=reconstructed, missing_data=missing,
                      notes=notes, scope_verifications=scope_verifications,
                      total_estimated_budget=server_total)
