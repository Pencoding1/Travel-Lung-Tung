"""Authoritative OpenCode session-export binding for one CLI call.

The raw ``run --format json`` stream carries session/message/part ids but may
omit model identity and usage (the installed V2 stream omits both, and has no
terminal event). A read-only ``opencode session export --standalone <sessionID>``
is therefore the only source of the *observed* agent, ``providerID/modelID``,
finish reason and token block. The requested alias is never injected as
observed proof.

Supported export shapes:

* V1: ``{"info": {...}, "messages": [{"info": ..., "parts": [...]}, ...]}``
* V2 (observed with v2.0.32): ``{"info": {...}, "messages": [{..., "type":
  "assistant", "agent": ..., "model": {"id", "providerID"}, "content": [...],
  "finish": "stop", "tokens": {...}}, ...]}``

Any contradiction (session/agent/message/part/model/finish/text/usage) fails
closed. Missing metadata is an explicit gap, not a guessed value. This module is
a focused production helper; it does not import the development benchmarks tree.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .events import SUCCESS_FINISH_REASON, EventUsage, ParsedStream


class ExportError(ValueError):
    """The session export is absent or malformed."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _nonblank(value: Any) -> Optional[str]:
    if isinstance(value, bool) or not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


@dataclass(frozen=True)
class ExportedPart:
    part_id: Optional[str]
    session_id: Optional[str]
    message_id: Optional[str]
    type: Optional[str]


@dataclass(frozen=True)
class AssistantMessage:
    message_id: str
    session_id: Optional[str]
    role: str
    model_id: Optional[str]
    provider_id: Optional[str]
    finish: Optional[str]
    tokens: Optional[Mapping[str, Any]]
    parts: Tuple[ExportedPart, ...]
    part_ids: Tuple[str, ...]
    text: str
    agent: Optional[str] = None
    # Fixed error code only; reasoning text/state/time are deliberately never
    # retained here, so no debug repr or evidence can carry reasoning content.
    content_error: Optional[str] = None


@dataclass(frozen=True)
class SessionExport:
    session_id: Optional[str]
    version: Optional[str]
    assistant_messages: Tuple[AssistantMessage, ...] = field(default_factory=tuple)
    shape: str = "v1"
    session_agent: Optional[str] = None


@dataclass(frozen=True)
class ExportVerdict:
    ok: bool
    reason: Optional[str]
    observed_model_id: Optional[str] = None
    observed_provider_id: Optional[str] = None
    qualified_model_id: Optional[str] = None
    assistant_message_id: Optional[str] = None
    usage_components: Optional[Mapping[str, Optional[int]]] = None
    usage_total: Optional[int] = None


def _v1_assistant(entry: Mapping[str, Any]) -> Optional[AssistantMessage]:
    info = entry.get("info")
    if not isinstance(info, dict):
        return None
    role = _nonblank(info.get("role")) or "unknown"
    if role != "assistant":
        return None

    model_block = info.get("model") if isinstance(info.get("model"), dict) else {}
    model_id = (_nonblank(info.get("modelID"))
                or _nonblank(model_block.get("modelID"))
                or _nonblank(model_block.get("id")))
    provider_id = (_nonblank(info.get("providerID"))
                   or _nonblank(model_block.get("providerID")))

    raw_parts = entry.get("parts") if isinstance(entry.get("parts"), list) else []
    parts: List[ExportedPart] = []
    part_ids: List[str] = []
    text_chunks: List[str] = []
    for part in raw_parts:
        if not isinstance(part, dict):
            continue
        part_id = _nonblank(part.get("id"))
        if part_id:
            part_ids.append(part_id)
        parts.append(ExportedPart(
            part_id=part_id,
            session_id=(_nonblank(part.get("sessionID"))
                        or _nonblank(part.get("sessionId"))),
            message_id=(_nonblank(part.get("messageID"))
                        or _nonblank(part.get("messageId"))),
            type=_nonblank(part.get("type")),
        ))
        if _nonblank(part.get("type")) == "text":
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                text_chunks.append(text)

    tokens = info.get("tokens") if isinstance(info.get("tokens"), dict) else None
    return AssistantMessage(
        message_id=_nonblank(info.get("id")) or "",
        session_id=_nonblank(info.get("sessionID")),
        role=role,
        model_id=model_id,
        provider_id=provider_id,
        finish=_nonblank(info.get("finish")),
        tokens=tokens,
        parts=tuple(parts),
        part_ids=tuple(part_ids),
        text="".join(text_chunks),
        agent=_nonblank(info.get("agent")),
    )


def _finite_number(value: Any) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)))


def _v2_item_error(item: Any) -> Optional[str]:
    """Validate one V2 content item without retaining its text/state/time."""
    if not isinstance(item, dict):
        return "export_malformed_content"
    kind = item.get("type")
    if not isinstance(kind, str):
        return "export_non_text_content"
    if kind not in ("text", "reasoning"):
        # Tool/file/action/unknown content is never accepted, alone or beside
        # valid text/reasoning.
        return "export_non_text_content"
    text = item.get("text")
    if not isinstance(text, str):
        return "export_malformed_content"
    if "state" in item and not isinstance(item.get("state"), dict):
        return "export_malformed_content"
    if kind == "text":
        return None
    if "time" in item:
        time_block = item.get("time")
        if not isinstance(time_block, dict):
            return "export_malformed_content"
        if set(time_block) - {"created", "completed"}:
            return "export_malformed_content"
        if "created" not in time_block or not _finite_number(
                time_block.get("created")):
            return "export_malformed_content"
        if "completed" in time_block and not _finite_number(
                time_block.get("completed")):
            return "export_malformed_content"
    return None


def _v2_assistant(entry: Mapping[str, Any]) -> Optional[AssistantMessage]:
    """Parse one flat V2 export message (``type``/``content``/``model``)."""
    if _nonblank(entry.get("type")) != "assistant":
        return None
    model_block = entry.get("model") if isinstance(entry.get("model"), dict) else {}
    raw_content = entry.get("content")
    content_error: Optional[str] = None
    if not isinstance(raw_content, list):
        content = []
        content_error = "export_malformed_content"
    else:
        content = raw_content
    parts: List[ExportedPart] = []
    part_ids: List[str] = []
    text_chunks: List[str] = []
    for item in content:
        item_error = _v2_item_error(item)
        if item_error is not None and content_error is None:
            content_error = item_error
        if not isinstance(item, dict):
            continue
        kind = item.get("type") if isinstance(item.get("type"), str) else None
        part_id = _nonblank(item.get("id")) or _nonblank(item.get("partID"))
        if part_id:
            part_ids.append(part_id)
        parts.append(ExportedPart(
            part_id=part_id,
            session_id=None,
            message_id=_nonblank(entry.get("id")),
            type=kind,
        ))
        if kind == "text":
            text = item.get("text")
            if isinstance(text, str):
                # Exact equality with the raw stream; whitespace-only text is
                # still rejected below as not a usable final answer.
                text_chunks.append(text)
    tokens = entry.get("tokens") if isinstance(entry.get("tokens"), dict) else None
    return AssistantMessage(
        message_id=_nonblank(entry.get("id")) or "",
        session_id=None,
        role="assistant",
        model_id=_nonblank(model_block.get("id")),
        provider_id=_nonblank(model_block.get("providerID")),
        finish=_nonblank(entry.get("finish")),
        tokens=tokens,
        parts=tuple(parts),
        part_ids=tuple(part_ids),
        text="".join(text_chunks),
        agent=_nonblank(entry.get("agent")),
        content_error=content_error,
    )


def _assistant_from_entry(entry: Any,
                          ) -> Tuple[Optional[AssistantMessage], Optional[str]]:
    if not isinstance(entry, dict):
        return None, None
    if isinstance(entry.get("info"), dict):
        return _v1_assistant(entry), "v1"
    if _nonblank(entry.get("type")):
        return _v2_assistant(entry), "v2"
    return None, None


def parse_export_bytes(raw: bytes) -> SessionExport:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ExportError("export_not_utf8")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        raise ExportError("export_not_json")
    if not isinstance(value, dict):
        raise ExportError("export_not_object")
    info = value.get("info")
    messages = value.get("messages")
    if not isinstance(info, dict):
        raise ExportError("export_missing_info")
    if not isinstance(messages, list):
        raise ExportError("export_missing_messages")

    assistants: List[AssistantMessage] = []
    shapes: List[str] = []
    for entry in messages:
        message, shape = _assistant_from_entry(entry)
        if shape:
            shapes.append(shape)
        if message is not None:
            assistants.append(message)
    if len(set(shapes)) > 1:
        raise ExportError("export_mixed_shapes")
    session_model = info.get("model") if isinstance(info.get("model"), dict) else {}
    session_agent = _nonblank(info.get("agent"))
    if session_agent is None:
        session_agent = _nonblank(session_model.get("agent"))
    return SessionExport(
        session_id=_nonblank(info.get("id")),
        version=_nonblank(info.get("version")),
        assistant_messages=tuple(assistants),
        shape=(shapes[0] if shapes else "unknown"),
        session_agent=session_agent,
    )


def flatten_tokens(tokens: Optional[Mapping[str, Any]]
                   ) -> Dict[str, Optional[int]]:
    flat: Dict[str, Optional[int]] = {
        "input": None, "output": None, "reasoning": None,
        "cache_read": None, "cache_write": None, "total": None,
    }
    if not isinstance(tokens, dict):
        return flat
    for key in ("input", "output", "reasoning", "total"):
        value = tokens.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            flat[key] = value
    cache = tokens.get("cache")
    if isinstance(cache, dict):
        for key, out in (("read", "cache_read"), ("write", "cache_write")):
            value = cache.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                flat[out] = value
    return flat


def invalid_token_components(tokens: Optional[Mapping[str, Any]]) -> Tuple[str, ...]:
    if not isinstance(tokens, dict):
        return ()
    invalid: List[str] = []
    for key in ("input", "output", "reasoning", "total"):
        if key in tokens:
            value = tokens.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                invalid.append(key)
    if "cache" in tokens:
        cache = tokens.get("cache")
        if not isinstance(cache, dict):
            invalid.append("cache")
        else:
            for key, out in (("read", "cache_read"), ("write", "cache_write")):
                if key in cache:
                    value = cache.get(key)
                    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                        invalid.append(out)
    return tuple(sorted(set(invalid)))


def _raw_usage_map(usage: Optional[EventUsage]) -> Dict[str, Optional[int]]:
    if usage is None:
        return {}
    return {
        "input": usage.input_tokens,
        "output": usage.output_tokens,
        "reasoning": usage.reasoning_tokens,
        "cache_read": usage.cache_read_tokens,
        "cache_write": usage.cache_write_tokens,
        "total": usage.total_tokens,
    }


def _fail(reason: str) -> ExportVerdict:
    return ExportVerdict(ok=False, reason=reason)


def validate_export(export: SessionExport, *, requested_model_id: str,
                    raw: ParsedStream,
                    requested_agent: Optional[str] = None) -> ExportVerdict:
    """Bind an export to the one raw observation, fail-closed."""
    raw_session = raw.session_id
    if not raw_session:
        return _fail("unknown_session_provenance")
    if not _nonblank(export.session_id):
        return _fail("export_missing_session")
    if export.session_id != raw_session:
        return _fail("export_session_mismatch")
    if export.shape == "unknown":
        return _fail("export_shape_unknown")

    raw_message_ids = {value for value in raw.assistant_message_ids if value}
    if len(raw_message_ids) != 1:
        return _fail("ambiguous_assistant_identity")
    if len(export.assistant_messages) != 1:
        return _fail("ambiguous_assistant_identity")
    message = export.assistant_messages[0]

    if message.role != "assistant":
        return _fail("wrong_role")
    if not _nonblank(message.message_id):
        return _fail("export_missing_message_id")
    if message.message_id not in raw_message_ids:
        return _fail("export_message_unbound")

    # Agent identity: the export is the only observed proof that the run really
    # used the unique deny-only transport agent.
    if requested_agent is not None:
        observed_agent = message.agent or export.session_agent
        if not _nonblank(observed_agent):
            return _fail("export_missing_agent")
        if observed_agent != requested_agent:
            return _fail("agent_mismatch")

    if export.shape == "v1":
        if not _nonblank(message.session_id):
            return _fail("export_missing_assistant_session")
        if message.session_id != raw_session:
            return _fail("export_assistant_session_mismatch")

        raw_parts = {value for value in raw.part_ids if value}
        if not raw_parts.issubset(set(message.part_ids)):
            return _fail("export_part_binding_failed")
        if len(message.part_ids) != len(set(message.part_ids)):
            return _fail("duplicate_part_id")
        for part in message.parts:
            if not part.part_id:
                continue
            if not part.session_id or not part.message_id:
                return _fail("export_part_unbound")
            if part.session_id != raw_session:
                return _fail("export_part_session_mismatch")
            if part.message_id != message.message_id:
                return _fail("export_part_message_mismatch")
    else:
        # V2 export content items carry no part ids; binding is by the single
        # assistant message id plus exact text equality below. Text and
        # structurally valid reasoning may coexist; reasoning contributes no
        # answer text and is not retained. Every tool/file/action/unknown item
        # remains disqualifying.
        if message.content_error is not None:
            return _fail(message.content_error)
        for part in message.parts:
            if part.type not in (None, "text", "reasoning"):
                return _fail("export_non_text_content")

    if not _nonblank(message.model_id) or not _nonblank(message.provider_id):
        return _fail("export_missing_model_metadata")
    qualified = f"{message.provider_id}/{message.model_id}"
    if qualified != requested_model_id:
        return _fail("model_mismatch")

    if not raw.terminal_present:
        return _fail("unfinished_response")
    if export.shape == "v2" or raw.terminal_reason is None:
        # V2 streams have no terminal event: the exported assistant finish is
        # the completion authority.
        if message.finish != SUCCESS_FINISH_REASON:
            return _fail("completion_conflict")
    elif message.finish != raw.terminal_reason:
        return _fail("completion_conflict")
    if message.text != raw.combined_text:
        return _fail("text_conflict")
    if export.shape == "v2" and not _nonblank(message.text):
        # Reasoning alone (or whitespace-only text) is not a usable final
        # answer; do not turn a reasoning-only export into empty content.
        return _fail("export_missing_text")

    invalid = invalid_token_components(message.tokens)
    if invalid:
        return _fail("invalid_usage")
    export_flat = flatten_tokens(message.tokens)
    for key, raw_value in _raw_usage_map(raw.usage).items():
        if raw_value is None:
            continue
        if export_flat.get(key) is not None and export_flat[key] != raw_value:
            return _fail("usage_conflict")

    return ExportVerdict(
        ok=True,
        reason=None,
        observed_model_id=message.model_id,
        observed_provider_id=message.provider_id,
        qualified_model_id=qualified,
        assistant_message_id=message.message_id,
        usage_components=export_flat,
        usage_total=export_flat.get("total"),
    )
