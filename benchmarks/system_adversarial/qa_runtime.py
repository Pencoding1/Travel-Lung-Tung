"""SYS098 opt-in QA seam for controlled HTTP fault injection (OFFLINE by default).

This module deliberately performs **no** application import and installs **no**
patch at import time.  ``install()`` may only be called by this task's owned
child launcher after the launcher set ``SYS098_ENABLE_QA=1``.  It then:

* installs a per-request ContextVar selected from ``X-TVLT-QA-Case`` and rejects
  unknown cases before any tool or provider call;
* delegates ``main.open_mcp_session`` to the real MCP client, wrapping only
  ``call_tool`` so the real call is counted first and a *registered* controlled
  response is substituted afterwards for the named stage;
* delegates ``main.gemini_chat_completion`` to the real provider exactly once,
  then perturbs only the parsed plan content for the two ``B_*`` cases;
* adds sanitized ``_sys098`` counters/flags to JSON responses.

Responses produced by an injection are labelled controlled evidence.  They are
never graph facts, never a native-call count, and never proof of a hallucination
rate.  No mutating MCP RPC is permitted by the registered cases.
"""

from __future__ import annotations

import contextlib
import copy
import json
import os
import re
from typing import Any, Dict, Mapping, Optional

CASE_HEADER = "x-tvlt-qa-case"
ENABLE_ENV = "SYS098_ENABLE_QA"

CASE_IDS = (
    "A_empty",
    "A_enrichment_failed",
    "C_no_match_native",
    "C_ambiguous",
    "C_wrong_parent",
    "C_partial_collision",
    "B_unknown_id",
    "B_unsupported_fields",
    "S_native_control",
)
GENERATIVE_CASES = frozenset({"B_unknown_id", "B_unsupported_fields", "S_native_control"})
READ_ONLY_TOOLS = frozenset({
    "get_available_categories",
    "explore_pois",
    "get_poi_details",
    "resolve_geographic_id",
    "get_itinerary_route",
})
GHOST_ID = "SYS098_GHOST_ID"
_AUTHORED_FIELDS = {
    "name": "SYS098 authored venue name",
    "address": "SYS098 authored address, not source truth",
    "price": "SYS098 authored price (unverified)",
    "hours": "SYS098 authored hours (unverified)",
    "description": "SYS098 authored description (not source truth)",
}

_state: Dict[str, Any] = {"installed": False}


class QARuntimeError(RuntimeError):
    """Constant, sanitized failure raised by the opt-in seam."""


def _new_counters(case: Optional[str]) -> Dict[str, Any]:
    return {
        "case": case,
        "real_tool_calls": 0,
        "tool_calls_by_name": {},
        "real_provider_calls": 0,
        "provider_ok_calls": 0,
        "injection_counts": {},
        "injection_exercised": False,
        "not_exercised": [],
        "controlled_response_used": False,
        "source_candidate_ids": [],
        "qualified_source_ids": [],
    }


import contextvars  # noqa: E402 - not an application import

_case_var = contextvars.ContextVar("sys098_qa_case", default=None)
_counters_var = contextvars.ContextVar("sys098_qa_counters", default=None)


def resolve_case_header(value: Optional[str]) -> Optional[str]:
    """Return a registered case id, ``None`` for absent, raise for unknown."""
    if value is None or value == "":
        return None
    if value not in CASE_IDS:
        raise QARuntimeError("unknown_qa_case")
    return value


@contextlib.contextmanager
def case_context(case: Optional[str]):
    """Explicit case scope for tests/direct delegation (always resets)."""
    normalized = resolve_case_header(case)
    token = _case_var.set(normalized)
    counter_token = _counters_var.set(_new_counters(normalized))
    try:
        yield _counters_var.get()
    finally:
        _counters_var.reset(counter_token)
        _case_var.reset(token)


def current_case() -> Optional[str]:
    return _case_var.get()


def current_counters() -> Optional[Dict[str, Any]]:
    return _counters_var.get()


def evidence_snapshot(counters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Sanitized counters only: no prompts, provider text, headers or secrets."""
    value = dict(counters if counters is not None else (_counters_var.get() or {}))
    if not value:
        return {"case": _case_var.get(), "real_tool_calls": 0,
                "real_provider_calls": 0, "injection_exercised": False}
    snapshot = {
        "case": value.get("case"),
        "real_tool_calls": int(value.get("real_tool_calls", 0)),
        "tool_calls_by_name": dict(value.get("tool_calls_by_name") or {}),
        "real_provider_calls": int(value.get("real_provider_calls", 0)),
        "provider_ok_calls": int(value.get("provider_ok_calls", 0)),
        "injection_counts": dict(value.get("injection_counts") or {}),
        "injection_exercised": bool(value.get("injection_exercised")),
        "not_exercised": list(value.get("not_exercised") or []),
        "controlled_response_used": bool(value.get("controlled_response_used")),
    }
    if "field_comparisons" in value:
        snapshot["field_comparisons"] = dict(value.get("field_comparisons") or {})
    if "control_checks" in value:
        snapshot["control_checks"] = {
            key: item for key, item in (value.get("control_checks") or {}).items()
            if isinstance(key, str) and (isinstance(item, bool) or item is None)}
    return snapshot


def _count(counters: Dict[str, Any], name: str) -> None:
    counters["real_tool_calls"] = int(counters.get("real_tool_calls", 0)) + 1
    by_name = counters.setdefault("tool_calls_by_name", {})
    by_name[name] = int(by_name.get(name, 0)) + 1


def _inject(counters: Dict[str, Any], stage: str) -> None:
    counts = counters.setdefault("injection_counts", {})
    counts[stage] = int(counts.get(stage, 0)) + 1
    counters["injection_exercised"] = True
    counters["controlled_response_used"] = True


# ---------------------------------------------------------------------------
# Result-envelope replacement (preserve the real type/schema)
# ---------------------------------------------------------------------------
def make_result_like(raw: Any, payload: Any, *, is_error: bool = False) -> Any:
    """Return a tool-result envelope of the same family as ``raw``."""
    text = payload if isinstance(payload, str) else json.dumps(
        payload, ensure_ascii=False, sort_keys=True)

    content = list(getattr(raw, "content", None) or [])
    item = content[0] if content else None
    if hasattr(raw, "model_copy") and item is not None:
        if hasattr(item, "model_copy"):
            new_item = item.model_copy(update={"text": text})
        else:
            try:
                from mcp.types import TextContent
                new_item = TextContent(type="text", text=text)
            except Exception:  # pragma: no cover - only exotic clients
                new_item = item
        return raw.model_copy(update={"content": [new_item], "isError": is_error})

    if item is not None:
        try:
            item_type = type(item)
            new_item = item_type(text=text)
            return type(raw)(content=[new_item], isError=is_error)
        except Exception:
            pass
    try:
        from mcp.types import TextContent
        return type(raw)(content=[TextContent(type="text", text=text)],
                         isError=is_error)
    except Exception:
        pass
    # Synthetic unit-test envelope: ToolResult(text=..., is_error=...)
    return type(raw)(text=text, is_error=is_error)


def _json_result(raw: Any, payload: Any) -> Any:
    return make_result_like(raw, payload)


def _error_result(raw: Any) -> Any:
    return make_result_like(
        raw, {"success": False, "code": "controlled_injected_error"}, is_error=True)


def _district_matches(raw: Any, matches: Any) -> Any:
    return _json_result(raw, {"success": True, "matches": matches})


DISTRICT_A = {"type": "District", "id": "sys098_d1_a", "name": "District 1"}
DISTRICT_B = {"type": "District", "id": "sys098_d1_b", "name": "District 1"}
CITY_FIXTURE = {"type": "City", "id": "sys098_hcmc",
                "name": "Ho Chi Minh City"}
WRONG_PARENT_DISTRICT = {
    "type": "District", "id": "sys098_d1_wrong_parent", "name": "District 1",
    "parent_city_id": "sys098_other_city", "parent_city_name": "Other City",
}
DISTRICT_10_FIXTURE = {"type": "District", "id": "sys098_d10",
                       "name": "District 10"}


def transform_tool_result(case: Optional[str], name: str, raw: Any,
                          arguments: Optional[Dict[str, Any]] = None,
                          counters: Optional[Dict[str, Any]] = None) -> Any:
    """Apply the registered controlled replacement for one named tool stage.

    The real tool has already been called and counted by the caller.  Only the
    five fixed read-only tool names are eligible; everything else is delegated.
    """
    if case is None or counters is None or name not in READ_ONLY_TOOLS:
        return raw
    try:
        if case == "A_empty" and name == "explore_pois":
            _inject(counters, "explore_pois:empty")
            return _json_result(raw, {"success": True, "results": []})
        if case == "A_enrichment_failed" and name == "get_poi_details":
            _inject(counters, "get_poi_details:isError")
            return _error_result(raw)
        if case == "C_ambiguous" and name == "resolve_geographic_id":
            keyword = (arguments or {}).get("keyword")
            if keyword == "District 1":
                _inject(counters, "resolve_geographic_id:ambiguous")
                return _district_matches(raw, [DISTRICT_A, DISTRICT_B])
            return raw
        if case == "C_wrong_parent" and name == "resolve_geographic_id":
            keyword = (arguments or {}).get("keyword")
            if keyword == "District 1":
                _inject(counters, "resolve_geographic_id:wrong_parent")
                return _district_matches(raw, [WRONG_PARENT_DISTRICT])
            if keyword == "Ho Chi Minh City":
                _inject(counters, "resolve_geographic_id:wrong_parent_city")
                return _district_matches(raw, [CITY_FIXTURE])
            return raw
        if case == "C_partial_collision" and name == "resolve_geographic_id":
            keyword = (arguments or {}).get("keyword")
            if keyword == "District 1":
                _inject(counters, "resolve_geographic_id:partial_collision")
                return _district_matches(raw, [DISTRICT_10_FIXTURE])
            return raw
    except Exception:
        # A replacement failure must never be misread as a real tool result.
        counters.setdefault("not_exercised", []).append("tool_replacement_failed")
        return raw
    return raw


class SessionProxy:
    """Delegating session proxy: real calls only, then controlled replacement."""

    def __init__(self, session: Any, counters: Optional[Dict[str, Any]] = None):
        self._session = session
        self._counters = counters

    def __getattr__(self, item: str) -> Any:
        return getattr(self._session, item)

    def _state(self) -> Dict[str, Any]:
        return self._counters if self._counters is not None else _counters_var.get()

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None):
        if name not in READ_ONLY_TOOLS:
            raise QARuntimeError("mutating_or_unknown_tool_forbidden")
        raw = await self._session.call_tool(name, arguments=arguments)
        counters = self._state()
        if counters is not None:
            _count(counters, name)
            if name == "get_poi_details":
                _capture_evidence(counters, raw)
            elif name == "explore_pois":
                _capture_source_candidates(counters, raw)
            return transform_tool_result(_case_var.get(), name, raw,
                                         arguments=dict(arguments or {}),
                                         counters=counters)
        return raw


def _capture_evidence(counters: Dict[str, Any], raw: Any) -> None:
    """RAM-only minimal evidence for later boolean comparisons (never persisted)."""
    content = list(getattr(raw, "content", None) or [])
    if not content:
        return
    text = getattr(content[0], "text", None)
    if not isinstance(text, str):
        return
    try:
        payload = json.loads(text)
    except ValueError:
        return
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        return
    poi_id = result.get("POI_ID")
    if not isinstance(poi_id, str) or not poi_id:
        return
    counters.setdefault("evidence", {})[poi_id] = {
        "name": result.get("POI_Name"),
        "address": result.get("POI_Address"),
        "operation_time": result.get("operation_time"),
    }
    counters.setdefault("qualified_source_ids", []).append(poi_id)


def _capture_source_candidates(counters: Dict[str, Any], raw: Any) -> None:
    """RAM-only actual explore result ids; never persisted as raw payloads."""
    content = list(getattr(raw, "content", None) or [])
    if not content:
        return
    text = getattr(content[0], "text", None)
    if not isinstance(text, str):
        return
    try:
        payload = json.loads(text)
    except ValueError:
        return
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return
    for item in results:
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]:
            counters.setdefault("source_candidate_ids", []).append(item["id"])


NEUTRAL_DESCRIPTION = (
    "Stop selected from the verified candidate set retrieved for the requested area."
)


def _merge_boolean(target: Dict[str, bool], key: str, value: bool) -> None:
    target[key] = bool(target.get(key, True)) and bool(value)


SOURCE_ADDRESS_KEYS = frozenset(
    {"street_name", "ward", "district", "city", "nation"})
_ADMIN_ADDRESS_KEYS = frozenset({"ward", "district", "city", "nation"})


def _normalize_source_address(value: Any) -> Optional[str]:
    """Production ``nonblank_str`` semantics, stripped for comparison only."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def compare_source_address(observed: Any,
                           actual: Mapping[str, Any]) -> bool:
    """Pure source-mode address comparison (no application import).

    ``actual`` is one RAM-only evidence record captured from the real
    ``get_poi_details`` result.  The ``address`` key must be explicitly
    present: missing evidence is not the same as an unknown address.

    Structured branch (the shape produced by production
    ``grounding._reconstruct_source_address``) requires exactly the five keys
    ``street_name/ward/district/city/nation``.  ``street_name`` must equal the
    normalized source string, or be ``None`` only when the source is blank.
    Every administrative field must remain ``None`` in source-snapshot mode;
    invented and extra fields are rejected.

    Legacy flat-string branch: older synthetic fixtures deliver a bare string.
    A nonblank stripped string is accepted only against a nonblank source.
    That is a compatibility representation, not proof that a production
    address object was tested.
    """
    if not isinstance(actual, Mapping) or "address" not in actual:
        return False
    source = _normalize_source_address(actual.get("address"))

    if isinstance(observed, Mapping):
        if set(observed.keys()) != SOURCE_ADDRESS_KEYS:
            return False
        street = observed.get("street_name")
        if street is not None:
            if not isinstance(street, str) or not street.strip():
                return False
            if source is None or street.strip() != source:
                return False
        elif source is not None:
            return False
        return all(observed.get(key) is None for key in _ADMIN_ADDRESS_KEYS)

    if isinstance(observed, str):
        value = observed.strip()
        return bool(value) and source is not None and value == source

    return False


def compare_delivered_fields(payload: Mapping[str, Any],
                             evidence: Mapping[str, Any]) -> Dict[str, bool]:
    """Compare every delivered stop; missing evidence or a bad stop stays false."""
    reply = payload.get("reply") if isinstance(payload, Mapping) else None
    stops = reply.get("stops") if isinstance(reply, Mapping) else None
    if not isinstance(stops, list) or not stops:
        return {"all_stops_covered": False}
    authored = {
        "SYS098 authored venue name",
        "SYS098 authored address, not source truth",
        "SYS098 authored price (unverified)",
        "SYS098 authored hours (unverified)",
        "SYS098 authored description (not source truth)",
    }
    comparisons: Dict[str, bool] = {"all_stops_covered": True}
    for stop in stops:
        if not isinstance(stop, Mapping):
            _merge_boolean(comparisons, "all_stops_covered", False)
            continue
        poi = stop.get("poi")
        if not isinstance(poi, Mapping):
            _merge_boolean(comparisons, "all_stops_covered", False)
            continue
        actual = evidence.get(poi.get("id"))
        if not isinstance(actual, Mapping):
            _merge_boolean(comparisons, "all_stops_covered", False)
            continue
        for field, actual_key in (("name", "name"),
                                  ("operation_time", "operation_time")):
            if field not in poi and actual_key not in actual:
                continue
            observed = poi.get(field)
            _merge_boolean(comparisons, field,
                           observed == actual.get(actual_key)
                           and observed not in authored)
        # Address is validated by the shared pure helper: production delivers
        # a structured object while older fixtures deliver a flat string.
        _merge_boolean(comparisons, "address",
                       compare_source_address(poi.get("address"), actual))
        for field in ("price", "hours"):
            _merge_boolean(comparisons, field,
                           poi.get(field) in (None, "", "unknown")
                           and poi.get(field) not in authored)
        _merge_boolean(
            comparisons, "description",
            stop.get("description") == NEUTRAL_DESCRIPTION
            and (stop.get("description_grounded") is False
                 if "description_grounded" in stop else True)
            and poi.get("description") in (None, NEUTRAL_DESCRIPTION))
        _merge_boolean(
            comparisons, "authored_text_absent",
            all(value not in authored
                for value in list(poi.values()) + list(stop.values())
                if isinstance(value, str)))
    return comparisons



def wrap_open_mcp_session(original: Any, counters: Optional[Dict[str, Any]] = None):
    """Return a delegating async context-manager factory around ``original``."""
    @contextlib.asynccontextmanager
    async def _wrapped():
        async with original() as session:
            yield SessionProxy(session, counters=counters)

    return _wrapped


# ---------------------------------------------------------------------------
# Provider seam
# ---------------------------------------------------------------------------
def _plan_from_response(response: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(response, dict):
        return None
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        return None
    clean = re.sub(r"```json\s*", "", content)
    clean = re.sub(r"```", "", clean).strip()
    try:
        plan = json.loads(clean)
    except (TypeError, ValueError):
        return None
    if not isinstance(plan, dict):
        return None
    stops = plan.get("stops")
    if not isinstance(stops, list) or not stops:
        return None
    for stop in stops:
        if not isinstance(stop, dict):
            return None
        poi = stop.get("poi")
        if not isinstance(poi, dict) or not isinstance(poi.get("id"), str) or not poi["id"]:
            return None
    return plan


def perturb_plan_response(case: Optional[str], response: Any,
                          counters: Optional[Dict[str, Any]] = None) -> Any:
    """Perturb only a successfully parsed plan for the two B cases."""
    if case not in ("B_unknown_id", "B_unsupported_fields") or counters is None:
        return response
    plan = _plan_from_response(response)
    if plan is None:
        counters.setdefault("not_exercised", []).append("no_valid_plan")
        return response
    try:
        mutated = copy.deepcopy(plan)
        if case == "B_unknown_id":
            mutated["stops"][0]["poi"]["id"] = GHOST_ID
            stage = "plan:ghost_id"
        else:
            for stop in mutated["stops"]:
                stop["description"] = _AUTHORED_FIELDS["description"]
                poi = stop["poi"]
                for field in ("name", "address", "price", "hours", "description"):
                    poi[field] = _AUTHORED_FIELDS[field]
            stage = "plan:unsupported_fields"
        content = json.dumps(mutated, ensure_ascii=False)
        changed = copy.deepcopy(response)
        changed["choices"][0]["message"]["content"] = content
        # Provenance, usage and envelope stay byte-identical apart from content.
        _inject(counters, stage)
        return changed
    except Exception:
        counters.setdefault("not_exercised", []).append("plan_perturbation_failed")
        return response


def wrap_gemini_chat_completion(original: Any,
                                counters: Optional[Dict[str, Any]] = None):
    """Delegating provider wrapper: one real call, then possible perturbation."""

    async def _wrapped(payload: Dict[str, Any]) -> Dict[str, Any]:
        state = counters if counters is not None else _counters_var.get()
        if state is not None:
            state["real_provider_calls"] = int(
                state.get("real_provider_calls", 0)) + 1
        response = await original(payload)
        if state is not None:
            provider = response.get("_provider") if isinstance(response, dict) else None
            if isinstance(provider, dict) and provider.get("ok") is True:
                state["provider_ok_calls"] = int(
                    state.get("provider_ok_calls", 0)) + 1
            return perturb_plan_response(_case_var.get(), response, state)
        return response

    return _wrapped


# ---------------------------------------------------------------------------
# Explicit installation (child launcher only)
# ---------------------------------------------------------------------------
def _estimate_json_body(response: Any) -> Any:
    """Best-effort JSON body extraction used only by the middleware."""
    body = getattr(response, "body", None)
    if isinstance(body, (bytes, bytearray)):
        return json.loads(bytes(body))
    return None


def install() -> Any:
    """Install the opt-in seam.  Requires ``SYS098_ENABLE_QA=1`` exactly."""
    if os.environ.get(ENABLE_ENV) != "1":
        raise QARuntimeError("qa_opt_in_required")
    import main  # noqa: PLC0415 - deliberately lazy, never at import time

    if getattr(main, "_SYS098_QA_INSTALLED", False):
        return main

    original_open = main.open_mcp_session
    original_chat = main.gemini_chat_completion
    main.open_mcp_session = wrap_open_mcp_session(original_open)
    main.gemini_chat_completion = wrap_gemini_chat_completion(original_chat)

    @main.app.middleware("http")
    async def _sys098_middleware(request, call_next):
        raw_case = request.headers.get(CASE_HEADER)
        try:
            case = resolve_case_header(raw_case)
        except QARuntimeError:
            return _json_response(
                400, {"status": "rejected",
                      "error": {"code": "unknown_qa_case"},
                      "_sys098": {"case": None, "rejected_unknown_case": True}})
        token = _case_var.set(case)
        counter_token = _counters_var.set(_new_counters(case))
        try:
            response = await call_next(request)
            path = request.url.path
            if case is not None and not (path.startswith("/catalog")
                                         or path == "/healthz"):
                response = await _attach_evidence(response)
            return response
        finally:
            _counters_var.reset(counter_token)
            _case_var.reset(token)

    main._SYS098_QA_INSTALLED = True
    _state["installed"] = True
    return main


def _json_response(status: int, payload: Any):
    from starlette.responses import JSONResponse
    return JSONResponse(status_code=status, content=payload)


async def _attach_evidence(response: Any) -> Any:
    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("application/json"):
        return response
    chunks = []
    try:
        async for chunk in response.body_iterator:
            chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode())
        body = b"".join(chunks)
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("not an object")
        counters = _counters_var.get() or {}
        if counters.get("case") == "B_unsupported_fields":
            comparisons = compare_delivered_fields(
                payload, counters.get("evidence") or {})
            if comparisons:
                counters["field_comparisons"] = comparisons
        if counters.get("case") == "S_native_control" \
                and payload.get("status") == "success":
            try:
                from benchmarks.system_adversarial import runner as _runner
                counters["control_checks"] = _runner.analyze_native_control(
                    payload,
                    source_ids=counters.get("source_candidate_ids") or None)
            except Exception:
                counters.setdefault("not_exercised", []).append(
                    "control_checks_unavailable")
        payload["_sys098"] = evidence_snapshot()
        from starlette.responses import Response
        headers = {key: value for key, value in response.headers.items()
                   if key.lower() != "content-length"}
        return Response(content=json.dumps(payload, ensure_ascii=False),
                        status_code=response.status_code,
                        media_type="application/json", headers=headers)
    except Exception:
        # Never claim evidence and never return a consumed empty body.
        from starlette.responses import Response
        if chunks:
            headers = {key: value for key, value in response.headers.items()
                       if key.lower() != "content-length"}
            return Response(content=b"".join(chunks),
                            status_code=response.status_code,
                            media_type=content_type.split(";")[0] or "application/json",
                            headers=headers)
        return response
