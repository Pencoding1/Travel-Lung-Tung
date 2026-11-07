"""Real ReAct loop, trace and usage accounting for the chat surface (OC-009).

The existing ``execute_agent_loop`` executed tools and then unconditionally
returned a "hitting a limit" string *inside* the first iteration, so the second
model call never happened. This module implements a genuinely bounded loop:

* at most ``MAX_TURNS`` model turns and ``MAX_TOOL_CALLS`` tool invocations;
* the loop continues *after* tool results are appended;
* every tool result message carries the exact ``tool_call_id`` from the model;
* unknown tool names and non-dict arguments are refused with a sanitized trace
  error and never executed;
* MCP envelopes are parsed with the OC-005 ``grounding`` helpers (``isError`` /
  ``success:false`` fail closed);
* an invalid model response or transport failure becomes a structured
  failure/partial result with a trace — never a traceback or raw credentials;
* free-form final answers are labelled ``unverified_free_text`` with the source
  evidence ids, and empty/all-failed tool data yields ``insufficient_data``
  rather than a grounded-looking hallucination.

This module performs no I/O itself; the model and tool calls are injected by
``main.py`` (and by tests) as awaitables.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple

from domains import grounding, source_gate

logger = logging.getLogger("Travel_Lung_Tung_Agent")

MAX_TURNS = 5
MAX_TOOL_CALLS = 8

GENERIC_TOOL_FAILURE = "The tool call did not return usable evidence."
TOOL_UNUSABLE_RESPONSE = "The tool returned an unusable response."

STATUS_SUCCESS = "success"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"
STATUS_INSUFFICIENT = "insufficient_data"

GROUNDING_UNVERIFIED_FREE_TEXT = "unverified_free_text"
GROUNDING_INSUFFICIENT = "insufficient_data"

LOOP_LIMIT_MESSAGE = (
    "I reached my tool-use limit before finishing. Here is what I established "
    "from the information gathered so far; some details are still unverified."
)
INSUFFICIENT_DATA_MESSAGE = (
    "I could not retrieve any usable place data for that request, so I cannot "
    "give a grounded answer. Please try rephrasing or narrowing the area."
)
MODEL_UNAVAILABLE_MESSAGE = (
    "The language model is currently unavailable, so I could not answer."
)

# Secret-ish substrings that must never appear in returned trace/log text.
_FORBIDDEN_MARKERS = ("authorization", "bearer ", "api_key", "apikey", "token")


def _sanitize(code: str) -> str:
    lowered = code.lower()
    for marker in _FORBIDDEN_MARKERS:
        if marker in lowered:
            return "sanitized_error"
    return code


# ---------------------------------------------------------------------------
# Usage accounting
# ---------------------------------------------------------------------------
def new_usage() -> Dict[str, Any]:
    return {
        "model_calls": 0,
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "calls": [],
        "char_estimate": 0,
        "char_estimate_label": (
            "sum of prompt characters (approximate proxy; NOT provider tokens)"),
    }


def _int_or_none(value: Any) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _accumulate(current: Optional[int], value: Optional[int]) -> Optional[int]:
    if value is None:
        return current
    if current is None:
        return value
    return current + value


def record_usage(acc: Dict[str, Any], response_data: Any,
                 prompt_messages: Optional[List[Dict[str, Any]]] = None) -> None:
    """Accumulate provider usage from one model call.

    Unknown values stay ``None`` (never coerced to zero). Every attempted call
    is recorded, including retried/failed-shape calls, so totals include all
    attempts.
    """
    acc["model_calls"] += 1
    entry = {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    usage = response_data.get("usage") if isinstance(response_data, dict) else None
    if isinstance(usage, dict):
        inp = _int_or_none(usage.get("prompt_tokens", usage.get("input_tokens")))
        out = _int_or_none(usage.get("completion_tokens", usage.get("output_tokens")))
        tot = _int_or_none(usage.get("total_tokens"))
        entry.update(input_tokens=inp, output_tokens=out, total_tokens=tot)
        acc["input_tokens"] = _accumulate(acc["input_tokens"], inp)
        acc["output_tokens"] = _accumulate(acc["output_tokens"], out)
        acc["total_tokens"] = _accumulate(acc["total_tokens"], tot)
    acc["calls"].append(entry)
    if prompt_messages:
        acc["char_estimate"] += sum(
            len(str(m.get("content") or "")) for m in prompt_messages
            if isinstance(m, dict))


def record_failed_call(acc: Dict[str, Any],
                       prompt_messages: Optional[List[Dict[str, Any]]] = None
                       ) -> None:
    """Record an attempted call that produced no usable response.

    Counts toward ``model_calls`` (so retries/attempts are included) while all
    token fields stay ``None`` (unknown, not zero).
    """
    acc["model_calls"] += 1
    acc["calls"].append({"input_tokens": None, "output_tokens": None,
                         "total_tokens": None})
    if prompt_messages:
        acc["char_estimate"] += sum(
            len(str(m.get("content") or "")) for m in prompt_messages
            if isinstance(m, dict))


# ---------------------------------------------------------------------------
# Model response parsing
# ---------------------------------------------------------------------------
def extract_assistant_message(response_data: Any
                              ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Return ``(message, error)`` for an OpenAI-compatible response.

    A message carrying ``tool_calls`` may legitimately have no ``content``. A
    message with neither content nor tool calls is invalid.
    """
    if not isinstance(response_data, dict):
        return None, "model response is not an object"
    choices = response_data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None, "model response has no choices"
    first = choices[0]
    if not isinstance(first, dict):
        return None, "model choice is not an object"
    message = first.get("message")
    if not isinstance(message, dict):
        return None, "model message is missing"
    content = message.get("content")
    tool_calls = message.get("tool_calls")
    if content is not None and not isinstance(content, str):
        return None, "model content is not a string"
    if tool_calls is not None and not isinstance(tool_calls, list):
        return None, "model tool_calls is not a list"
    has_content = isinstance(content, str) and content.strip()
    if not has_content and not tool_calls:
        return None, "model message has neither content nor tool_calls"
    return message, None


def _parse_tool_arguments(raw: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Arguments must decode to a JSON object (a dict). Anything else fails."""
    if isinstance(raw, dict):
        return raw, None
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError):
            return None, "arguments are not valid JSON"
        if isinstance(decoded, dict):
            return decoded, None
        return None, "arguments are not a JSON object"
    if raw is None:
        return {}, None
    return None, "arguments are neither an object nor a JSON string"


def _extract_evidence_ids(payload: Any) -> Set[str]:
    """Collect actual POI identifiers from a tool payload.

    Only POI-bearing shapes count: a top-level ``POI_ID``/``poi_id``, an
    enrichment ``result`` object, or entries of an ``explore`` ``results`` list.
    Resolver ``matches``, category lists and other metadata are deliberately
    **not** treated as POI evidence.
    """
    ids: Set[str] = set()
    if not isinstance(payload, dict):
        return ids
    for key in ("POI_ID", "poi_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            ids.add(value)

    result = payload.get("result")
    if isinstance(result, dict):
        for key in ("POI_ID", "poi_id", "id"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                ids.add(value)

    results = payload.get("results")
    if isinstance(results, list):
        for item in results:
            if not isinstance(item, dict):
                continue
            for key in ("POI_ID", "poi_id", "id"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    ids.add(value)
    return ids


def _is_usable_data(payload: Any) -> bool:
    """Whether a successful tool envelope carries actual POI evidence.

    Metadata-only / resolver / category-only results are not usable evidence,
    so the loop reports ``insufficient_data`` rather than letting the model
    present ungrounded travel suggestions.
    """
    return isinstance(payload, dict) and bool(_extract_evidence_ids(payload))


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------
async def run_agent_loop(
    *,
    messages: List[Dict[str, Any]],
    tool_specs: List[Dict[str, Any]],
    known_tool_names: Set[str],
    call_model: Callable[[List[Dict[str, Any]], List[Dict[str, Any]]],
                         Awaitable[Any]],
    call_tool: Callable[[str, Dict[str, Any]], Awaitable[Any]],
    usage: Optional[Dict[str, Any]] = None,
    max_turns: int = MAX_TURNS,
    max_tool_calls: int = MAX_TOOL_CALLS,
    initial_tool_requests: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run a bounded ReAct loop and return a structured result.

    ``messages`` is mutated in place (assistant and tool messages are appended)
    but the mutable history is *not* trimmed here — the caller owns working
    memory so trimming can respect turn boundaries.

    ``initial_tool_requests`` lets the *server* seed normal tool evidence before
    the first model turn (used only for the explicit source bootstrap). The
    seeded assistant/tool pair is marked ``origin=server_bootstrap`` in the
    trace; it is never represented as a model-issued/observed call, consumes
    the same tool-call budget, and produces no model usage. If the seed yields
    no POI evidence, the loop returns ``insufficient_data`` without calling the
    model.
    """
    if usage is None:
        usage = new_usage()

    tool_chain: List[Dict[str, Any]] = []
    turn_messages: List[Dict[str, Any]] = []
    evidence_ids: Set[str] = set()
    executed = 0
    any_tool_success = False
    loop_limit_reached = False

    def trace_entry(tool: str, status: str, summary: str,
                    call_id: Optional[str] = None,
                    origin: Optional[str] = None) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            "step": len(tool_chain) + 1,
            "tool": tool,
            "status": status,
            "summary": _sanitize(summary),
        }
        if call_id is not None:
            entry["tool_call_id"] = call_id
        if origin is not None:
            entry["origin"] = origin
        tool_chain.append(entry)
        return entry

    async def execute_calls(tool_calls: List[Dict[str, Any]],
                            origin: Optional[str] = None) -> None:
        nonlocal executed, any_tool_success, evidence_ids
        for tool_call in tool_calls:
            call_id = tool_call["id"]
            function = tool_call["function"]
            name = function["name"]
            raw_args = function.get("arguments")

            executed += 1

            if name not in known_tool_names:
                # Never echo an arbitrary model-supplied name into the trace.
                trace_entry("rejected_tool", "failed", "unknown_tool", call_id,
                            origin)
                tool_msg = _tool_message(
                    call_id, "rejected_tool",
                    json.dumps({"error": "unknown_tool"}))
                messages.append(tool_msg)
                turn_messages.append(tool_msg)
                continue

            args, arg_error = _parse_tool_arguments(raw_args)
            if arg_error is not None:
                trace_entry(name, "failed", "malformed_arguments", call_id,
                            origin)
                tool_msg = _tool_message(
                    call_id, name, json.dumps({"error": "malformed_arguments"}))
                messages.append(tool_msg)
                turn_messages.append(tool_msg)
                continue

            try:
                raw_result = await call_tool(name, args)
            except Exception as exc:  # noqa: BLE001
                trace_entry(name, "failed", "tool_transport_error", call_id,
                            origin)
                tool_msg = _tool_message(
                    call_id, name, json.dumps({"error": "tool_transport_error"}))
                messages.append(tool_msg)
                turn_messages.append(tool_msg)
                logger.error("Tool transport failure: %s", type(exc).__name__)
                continue

            outcome = grounding.parse_mcp_tool_result(raw_result)
            if outcome.ok:
                evidence = _extract_evidence_ids(outcome.data)
                if evidence:
                    any_tool_success = True
                    evidence_ids |= evidence
                    trace_entry(name, "success", "ok", call_id, origin)
                else:
                    # Metadata/resolver/category-only results are not POI
                    # evidence and cannot justify a travel recommendation.
                    trace_entry(name, "success", "no_poi_evidence", call_id,
                                origin)
                tool_msg = _tool_message(
                    call_id, name, _tool_result_text(raw_result))
            else:
                # Never echo arbitrary upstream text. Only a server-owned
                # ScopeGate rejection code (with scope_enforced) is surfaced,
                # mapped to a fixed message; every other failure is generic.
                payload = _tool_failure_payload(outcome)
                code = payload["error"]
                trace_entry(name, "failed", code, call_id, origin)
                tool_msg = _tool_message(
                    call_id, name, json.dumps(payload))
            messages.append(tool_msg)
            turn_messages.append(tool_msg)

    # Server-authored seed for the explicit source bootstrap. It runs before
    # the first model call and consumes the ordinary tool budget.
    bootstrap_requests = list(initial_tool_requests or [])
    if bootstrap_requests:
        bootstrap_calls: List[Dict[str, Any]] = []
        for index, request in enumerate(bootstrap_requests[:max_tool_calls]):
            if not isinstance(request, dict):
                continue
            name = request.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            arguments = request.get("arguments", {})
            if isinstance(arguments, dict):
                arguments = json.dumps(arguments, ensure_ascii=False)
            elif not isinstance(arguments, str) and arguments is not None:
                continue
            bootstrap_calls.append({
                "id": f"call_server_bootstrap_{index + 1}",
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            })
        if len(bootstrap_requests) > max_tool_calls:
            loop_limit_reached = True
        if not bootstrap_calls:
            return _result(
                status=STATUS_INSUFFICIENT, reply=INSUFFICIENT_DATA_MESSAGE,
                tool_chain=tool_chain, usage=usage,
                turn_messages=turn_messages, evidence_ids=evidence_ids,
                grounding_status=GROUNDING_INSUFFICIENT,
                error_code="insufficient_data", loop_limit=False,
                message=INSUFFICIENT_DATA_MESSAGE)
        assistant_bootstrap = {"role": "assistant",
                               "content": None,
                               "tool_calls": bootstrap_calls}
        messages.append(assistant_bootstrap)
        turn_messages.append(assistant_bootstrap)
        await execute_calls(bootstrap_calls, origin="server_bootstrap")
        if not evidence_ids:
            return _result(
                status=STATUS_INSUFFICIENT, reply=INSUFFICIENT_DATA_MESSAGE,
                tool_chain=tool_chain, usage=usage,
                turn_messages=turn_messages, evidence_ids=evidence_ids,
                grounding_status=GROUNDING_INSUFFICIENT,
                error_code="insufficient_data", loop_limit=False,
                message=INSUFFICIENT_DATA_MESSAGE)

    for turn in range(1, max_turns + 1):
        prompt = list(messages)
        try:
            response_data = await call_model(list(messages), tool_specs)
        except Exception as exc:  # noqa: BLE001 - convert to structured failure
            record_failed_call(usage, prompt)
            logger.error("Agent loop model call failed: %s", type(exc).__name__)
            return _result(
                status=STATUS_PARTIAL if evidence_ids else STATUS_FAILED,
                reply=None,
                tool_chain=tool_chain,
                usage=usage,
                turn_messages=turn_messages,
                evidence_ids=evidence_ids,
                grounding_status=(GROUNDING_UNVERIFIED_FREE_TEXT
                                  if evidence_ids else GROUNDING_INSUFFICIENT),
                error_code="model_unavailable",
                loop_limit=False,
                message=MODEL_UNAVAILABLE_MESSAGE,
            )

        record_usage(usage, response_data, prompt)
        assistant_msg, err = extract_assistant_message(response_data)
        if err is not None:
            logger.warning("Agent loop invalid model response: %s", err)
            return _result(
                status=STATUS_PARTIAL if evidence_ids else STATUS_FAILED,
                reply=None,
                tool_chain=tool_chain,
                usage=usage,
                turn_messages=turn_messages,
                evidence_ids=evidence_ids,
                grounding_status=(GROUNDING_UNVERIFIED_FREE_TEXT
                                  if evidence_ids else GROUNDING_INSUFFICIENT),
                error_code="invalid_model_response",
                loop_limit=False,
                message=MODEL_UNAVAILABLE_MESSAGE,
            )

        assistant_msg = {k: v for k, v in assistant_msg.items() if v is not None}
        assistant_msg["role"] = "assistant"
        announced = assistant_msg.get("tool_calls") or []

        # Normalize announced calls *before* persisting the assistant message:
        # malformed entries are dropped and ids are made nonblank + unique, so
        # the persisted list can be answered one-to-one (no orphan calls).
        normalized: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()
        for index, tool_call in enumerate(announced):
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function")
            if not isinstance(function, dict):
                continue
            name = function.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            call_id = grounding.nonblank_str(tool_call.get("id"))
            if call_id is None or call_id in seen_ids:
                call_id = f"call_{turn}_{index}"
                while call_id in seen_ids:
                    call_id += "_"
            tool_call["id"] = call_id
            seen_ids.add(call_id)
            normalized.append(tool_call)

        # Trim to the remaining tool budget *before* persisting so every
        # announced id is answered (bounded, coherent assistant message).
        remaining = max_tool_calls - executed
        trimmed = len(normalized) > remaining
        if trimmed:
            normalized = normalized[:max(remaining, 0)]
            loop_limit_reached = True
        assistant_msg["tool_calls"] = normalized

        if not normalized:
            content = assistant_msg.get("content")
            messages.append(assistant_msg)
            turn_messages.append(assistant_msg)
            if trimmed:
                return _limit_result(tool_chain, usage, turn_messages,
                                     evidence_ids, any_tool_success)
            if not isinstance(content, str) or not content.strip():
                # Tool-calls were announced but all were malformed and no
                # content was produced.
                return _result(
                    status=STATUS_FAILED, reply=None, tool_chain=tool_chain,
                    usage=usage, turn_messages=turn_messages,
                    evidence_ids=evidence_ids,
                    grounding_status=GROUNDING_INSUFFICIENT,
                    error_code="invalid_model_response", loop_limit=False,
                    message=MODEL_UNAVAILABLE_MESSAGE)
            if any_tool_success:
                return _result(
                    status=STATUS_SUCCESS, reply=content, tool_chain=tool_chain,
                    usage=usage, turn_messages=turn_messages,
                    evidence_ids=evidence_ids,
                    grounding_status=GROUNDING_UNVERIFIED_FREE_TEXT,
                    error_code=None, loop_limit=False, message=None)
            # No usable POI evidence: do not present free-form suggestions.
            return _result(
                status=STATUS_INSUFFICIENT, reply=INSUFFICIENT_DATA_MESSAGE,
                tool_chain=tool_chain, usage=usage,
                turn_messages=turn_messages, evidence_ids=evidence_ids,
                grounding_status=GROUNDING_INSUFFICIENT,
                error_code="insufficient_data", loop_limit=False,
                message=INSUFFICIENT_DATA_MESSAGE)

        assistant_msg.setdefault("content", None)
        messages.append(assistant_msg)
        turn_messages.append(assistant_msg)

        await execute_calls(normalized)

        if loop_limit_reached:
            return _limit_result(tool_chain, usage, turn_messages,
                                 evidence_ids, any_tool_success)

    # Every model turn requested tools and the turn budget was exhausted.
    return _limit_result(tool_chain, usage, turn_messages, evidence_ids,
                         any_tool_success)


def _limit_result(tool_chain: List[Dict[str, Any]], usage: Dict[str, Any],
                  turn_messages: List[Dict[str, Any]], evidence_ids: Set[str],
                  any_tool_success: bool) -> Dict[str, Any]:
    return _result(
        status=STATUS_PARTIAL, reply=LOOP_LIMIT_MESSAGE, tool_chain=tool_chain,
        usage=usage, turn_messages=turn_messages, evidence_ids=evidence_ids,
        grounding_status=(GROUNDING_UNVERIFIED_FREE_TEXT if any_tool_success
                          else GROUNDING_INSUFFICIENT),
        error_code="loop_limit", loop_limit=True, message=LOOP_LIMIT_MESSAGE)


def _tool_failure_payload(outcome: grounding.ToolOutcome) -> Dict[str, str]:
    """Return only server-owned codes and fixed messages for a failed call."""
    data = outcome.data if isinstance(outcome.data, dict) else {}
    code = data.get("code")
    if data.get("scope_enforced") is True and isinstance(code, str):
        message = source_gate.REJECTION_MESSAGES.get(code)
        if message is not None:
            return {"error": code, "detail": message}
    if outcome.code == grounding.TOOL_PROTOCOL_ERROR:
        return {"error": "tool_protocol_error", "detail": TOOL_UNUSABLE_RESPONSE}
    return {"error": "tool_error", "detail": GENERIC_TOOL_FAILURE}


def _tool_result_text(result: Any) -> str:
    """Extract the textual content of a successful ``CallToolResult``.

    Mirrors the OC-005 ``grounding`` extraction (content[0].text) without
    depending on its private helpers; a non-textual but successful envelope
    degrades to an empty string rather than raising.
    """
    content = getattr(result, "content", None)
    if content:
        text = getattr(content[0], "text", None)
        if isinstance(text, str):
            return text
    return ""


def _tool_message(call_id: str, name: str, content: str) -> Dict[str, Any]:
    return {"role": "tool", "tool_call_id": call_id, "name": name,
            "content": content}


def _result(*, status: str, reply: Optional[str],
            tool_chain: List[Dict[str, Any]], usage: Dict[str, Any],
            turn_messages: List[Dict[str, Any]], evidence_ids: Set[str],
            grounding_status: str, error_code: Optional[str],
            loop_limit: bool, message: Optional[str]) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "status": status,
        "reply": reply,
        "tool_chain": tool_chain,
        "usage": usage,
        "loop_limit": loop_limit,
        "source_evidence_ids": sorted(evidence_ids),
        "grounding_status": grounding_status,
        # The caller (main.py) commits this into working memory; dropping it
        # silently reduces every later turn to the bare user message.
        "turn_messages": list(turn_messages),
    }
    if error_code is not None:
        result["error"] = {"code": _sanitize(error_code),
                           "message": _sanitize(message or error_code)}
    return result
