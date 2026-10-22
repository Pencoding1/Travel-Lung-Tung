"""Bounded request/response contracts for the itinerary-draft workflow (OC-027).

An itinerary draft is **not** independently verified by this backend. The client
submits the exact JSON document returned by the AI service's
``POST /generate_itinerary`` and the backend persists it. The contract here does
two jobs only:

1. **Structural bounds.** The payload is validated for shape and resource bounds
   (size, depth, node count, string length, list length, finite numbers) so a
   hostile or accidental client cannot exhaust storage or memory. Validation is
   *bounded*, not a re-derivation of trip feasibility.
2. **Preservation, never promotion.** Unknown cost/status/provenance values are
   carried through verbatim. This module never converts ``null`` budgets,
   unknown planning status or violations into ``"feasible"`` or any other claim,
   never invents POIs/geography, and never invents an owner.

The payload skeleton follows the real ``/generate_itinerary`` response: a JSON
object whose ``reply`` object carries the itinerary ``stops``. The draft's own id
and creation time are generated server-side by the repository, never taken from
the client payload.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# --- Resource bounds. Exceeding any bound is a hard rejection (never truncated).
MAX_PAYLOAD_BYTES = 256 * 1024
MAX_JSON_DEPTH = 16
MAX_JSON_NODES = 20_000
MAX_STRING_CHARS = 65_536
MAX_LIST_ITEMS = 2_000
MAX_STOPS = 200

# --- Pagination bounds for the list endpoint.
DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100
MAX_PAGE_OFFSET = 1_000_000


class PayloadError(ValueError):
    """Structured rejection of a malformed or out-of-bounds draft payload."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _reject(code: str, message: str) -> "PayloadError":
    return PayloadError(code, message)


def _walk(value: Any, *, depth: int, budget: List[int]) -> None:
    """Recursively enforce depth/node/string/list bounds and finite numbers."""
    budget[0] -= 1
    if budget[0] < 0:
        raise _reject("payload_too_complex",
                      f"payload exceeds {MAX_JSON_NODES} total nodes")
    if depth > MAX_JSON_DEPTH:
        raise _reject("payload_too_deep", f"payload exceeds depth {MAX_JSON_DEPTH}")

    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        if len(value) > MAX_STRING_CHARS:
            raise _reject("string_too_long",
                          f"a string exceeds {MAX_STRING_CHARS} characters")
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _reject("non_finite_number",
                          "payload contains a NaN or Infinity number")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise _reject("invalid_key", "object keys must be strings")
            if len(key) > MAX_STRING_CHARS:
                raise _reject("string_too_long",
                              f"an object key exceeds {MAX_STRING_CHARS} characters")
            _walk(item, depth=depth + 1, budget=budget)
        return
    if isinstance(value, list):
        if len(value) > MAX_LIST_ITEMS:
            raise _reject("list_too_long",
                          f"a list exceeds {MAX_LIST_ITEMS} items")
        for item in value:
            _walk(item, depth=depth + 1, budget=budget)
        return
    raise _reject("invalid_type", f"unsupported JSON value: {type(value).__name__}")


def _bounded_optional_str(payload: Dict[str, Any], key: str) -> Optional[str]:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, str) or not value.strip():
        return None
    return value


def validate_draft_payload(raw: Any) -> Dict[str, Any]:
    """Validate and return the client-supplied ``/generate_itinerary`` document.

    Raises :class:`PayloadError` on any structural or bound violation. Nothing is
    coerced, defaulted or invented; the returned object is the same document.
    """
    if not isinstance(raw, dict):
        raise _reject("payload_not_object", "payload must be a JSON object")

    # Bound depth/node/string/list structure FIRST with an early-exit walk, so a
    # pathological document is rejected before any recursive serialization is
    # attempted (a deep document must never reach json.dumps and blow the stack).
    _walk(raw, depth=0, budget=[MAX_JSON_NODES])

    # Byte size is measured on the exact stored serialization to bound durable
    # storage independently of the in-memory node/string checks.
    try:
        encoded = json.dumps(raw, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        raise _reject("payload_not_serializable",
                      "payload contains a value that is not JSON-serializable")
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise _reject("payload_too_large",
                      f"payload exceeds {MAX_PAYLOAD_BYTES} bytes")

    reply = raw.get("reply")
    if not isinstance(reply, dict):
        raise _reject("missing_reply",
                      "payload.reply must be the itinerary object from "
                      "generate_itinerary")
    stops = reply.get("stops")
    if not isinstance(stops, list):
        raise _reject("missing_stops", "payload.reply.stops must be a JSON array")
    if len(stops) > MAX_STOPS:
        raise _reject("too_many_stops", f"reply.stops exceeds {MAX_STOPS} stops")
    for index, stop in enumerate(stops):
        if not isinstance(stop, dict):
            raise _reject("invalid_stop", f"reply.stops[{index}] must be a JSON object")
    return raw


def payload_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Derive the bounded list/detail summary from a validated payload.

    Only fields the AI response actually carries are read; missing values stay
    ``None`` and are never fabricated.
    """
    reply = payload.get("reply") if isinstance(payload.get("reply"), dict) else {}
    stops = reply.get("stops") if isinstance(reply.get("stops"), list) else []
    return {
        "start_poi_id": _bounded_optional_str(reply, "start_poi_id"),
        "end_poi_id": _bounded_optional_str(reply, "end_poi_id"),
        "stop_count": len(stops),
    }


# ---------------------------------------------------------------------------
# HTTP request / response contracts
# ---------------------------------------------------------------------------
class DraftCreateRequest(BaseModel):
    """Create body.

    ``extra="forbid"`` means a client-supplied ``owner``/``uid``/``id`` at the top
    level is *rejected* with 422 — the owner is always the verified JWT subject and
    the id is always server-generated. The AI response's own ``reply.uid`` is kept
    as inert provenance inside ``payload`` and never used as the owner.
    """

    model_config = ConfigDict(extra="forbid")

    payload: Dict[str, Any] = Field(
        ..., description="The exact JSON body returned by POST /generate_itinerary")


class DraftSummary(BaseModel):
    id: str
    start_poi_id: Optional[str] = None
    end_poi_id: Optional[str] = None
    stop_count: int
    created_at: str


class DraftDetail(DraftSummary):
    payload: Dict[str, Any]


class DraftListResponse(BaseModel):
    items: List[DraftSummary]
    total: int
    limit: int
    offset: int


class RepositoryHealth(BaseModel):
    available: bool
    backend: str
    detail: Optional[str] = None
