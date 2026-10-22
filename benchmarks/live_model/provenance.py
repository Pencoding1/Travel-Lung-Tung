"""Authoritative session-export provenance binding (OC-033).

The DS-004 diagnostic (``docs/project/handoffs/DS-004``) showed a real
``opencode run --format json`` stream that **omits** the provider/model identity:
the raw events carry only a ``sessionID`` and assistant ``messageID``/part ids.
``opencode export <sessionID>`` returns that same session's assistant message
metadata (``modelID``, ``providerID``, ``finish``, ``tokens``) plus the exact
part ids.

This module treats the export as an *authoritative sidecar*, never as ground
truth about a provider's upstream checkpoint:

* It is captured read-only by the existing bounded process-tree capture.
* The raw JSONL is preserved byte-for-byte; the export is stored separately and
  hashed.
* The exported assistant message is strictly bound to the raw observation by
  session id, messageID, part ids, text and (when present) terminal completion.
* The observed model is ``providerID + "/" + modelID`` and must equal the
  requested full id **exactly** (no blind suffix match). A matching alias is not
  evidence that an upstream "4.1" checkpoint was served.
* Any contradiction fails closed; missing/unknown export stays a gap. The
  requested model is never reported as observed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# The sidecar source label. It names the OpenCode session metadata, *not* an
# upstream model guarantee.
SOURCE_LABEL = "OpenCode session metadata"
SOURCE_NOTE = ("OpenCode session metadata (assistant message modelID/providerID); "
               "not an upstream model/checkpoint guarantee")

# Verdict reasons that mean a *captured* export contradicts the observation.
CONFLICT_REASONS = frozenset({
    "export_session_mismatch",
    "export_missing_assistant_session",
    "export_assistant_session_mismatch",
    "ambiguous_assistant_identity",
    "wrong_role",
    "export_missing_message_id",
    "export_message_unbound",
    "export_part_unbound",
    "export_part_binding_failed",
    "export_part_session_mismatch",
    "export_part_message_mismatch",
    "duplicate_part_id",
    "model_mismatch",
    "completion_conflict",
    "text_conflict",
    "invalid_export_usage",
    "usage_conflict",
})

# Verdict reasons that mean the export could not supply the missing metadata.
MISSING_REASONS = frozenset({
    "unknown_session_provenance",
    "export_missing_session",
    "export_missing_model_metadata",
    "missing_message_identity",
    "export_not_terminal",
})


class ProvenanceError(ValueError):
    """The session export is absent, malformed, or of the wrong shape."""


def _nonblank(value: Any) -> Optional[str]:
    if isinstance(value, bool) or not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _valid_count(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def qualified_model_id(provider_id: str, model_id: str) -> str:
    """The observed identity as ``providerID + '/' + modelID``."""
    return f"{provider_id}/{model_id}"


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
    part_message_ids: Tuple[str, ...]
    text: str
    text_part_ids: Tuple[str, ...]


@dataclass(frozen=True)
class SessionExport:
    session_id: Optional[str]
    version: Optional[str]
    assistant_messages: Tuple[AssistantMessage, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProvenanceVerdict:
    ok: bool
    reason: Optional[str]
    observed_model_id: Optional[str] = None
    observed_provider_id: Optional[str] = None
    qualified_model_id: Optional[str] = None
    assistant_message_id: Optional[str] = None


def _assistant_from_entry(entry: Any) -> Optional[AssistantMessage]:
    if not isinstance(entry, dict):
        return None
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
    part_message_ids: List[str] = []
    text_chunks: List[str] = []
    text_part_ids: List[str] = []
    for part in raw_parts:
        if not isinstance(part, dict):
            continue
        part_id = _nonblank(part.get("id"))
        part_message = _nonblank(part.get("messageID")) or _nonblank(part.get("messageId"))
        part_session = _nonblank(part.get("sessionID")) or _nonblank(part.get("sessionId"))
        part_type = _nonblank(part.get("type"))
        parts.append(ExportedPart(part_id=part_id, session_id=part_session,
                                  message_id=part_message, type=part_type))
        if part_id:
            part_ids.append(part_id)
        if part_message:
            part_message_ids.append(part_message)
        if part_type == "text":
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                text_chunks.append(text)
                if part_id:
                    text_part_ids.append(part_id)

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
        part_message_ids=tuple(part_message_ids),
        text="".join(text_chunks),
        text_part_ids=tuple(text_part_ids),
    )


def parse_session_export(value: Any) -> SessionExport:
    """Parse an ``opencode export`` payload into a typed, defensive view."""
    if not isinstance(value, dict):
        raise ProvenanceError("session export is not a JSON object")
    info = value.get("info")
    if not isinstance(info, dict):
        raise ProvenanceError("session export has no 'info' object")
    messages = value.get("messages")
    if not isinstance(messages, list):
        raise ProvenanceError("session export has no 'messages' array")

    assistant = [_assistant_from_entry(entry) for entry in messages]
    return SessionExport(
        session_id=_nonblank(info.get("id")),
        version=_nonblank(info.get("version")),
        assistant_messages=tuple(msg for msg in assistant if msg is not None),
    )


def parse_session_export_bytes(data: bytes) -> SessionExport:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProvenanceError(f"session export is not UTF-8: {exc}")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProvenanceError(f"session export is not valid JSON: {exc}")
    return parse_session_export(value)


def flatten_tokens(tokens: Optional[Mapping[str, Any]]) -> Dict[str, int]:
    """Flat, valid-only component view of a provider token block."""
    flat: Dict[str, int] = {}
    if not isinstance(tokens, dict):
        return flat
    for key in ("input", "output", "reasoning", "total"):
        value = _valid_count(tokens.get(key))
        if value is not None:
            flat[key] = value
    cache = tokens.get("cache")
    if isinstance(cache, dict):
        for key, out in (("read", "cache_read"), ("write", "cache_write")):
            value = _valid_count(cache.get(key))
            if value is not None:
                flat[out] = value
    return flat


def invalid_token_components(tokens: Optional[Mapping[str, Any]]) -> Tuple[str, ...]:
    """Names of explicitly provided-but-invalid token components.

    A component is invalid when it is present but negative, boolean, or not an
    integer (including a malformed ``cache`` block). This is checked *before*
    any comparison so an invalid provider component is never silently dropped.
    """
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
    return tuple(invalid)


def _usage_conflict(export_tokens: Mapping[str, int],
                    raw_usage: Mapping[str, Optional[int]]) -> bool:
    for key, raw_value in raw_usage.items():
        if raw_value is None:
            continue
        if key in export_tokens and export_tokens[key] != raw_value:
            return True
    return False


def _gap(reason: str) -> ProvenanceVerdict:
    return ProvenanceVerdict(ok=False, reason=reason)


def validate_session_export(
    export: SessionExport,
    *,
    requested_model_id: str,
    raw_session_id: Optional[str],
    raw_assistant_message_ids: Sequence[str],
    raw_part_ids: Sequence[str],
    raw_text: str,
    raw_terminal_present: bool,
    raw_terminal_reason: Optional[str],
    raw_usage: Mapping[str, Optional[int]],
) -> ProvenanceVerdict:
    """Bind a parsed export to one raw observation, fail-closed."""
    if not _nonblank(raw_session_id):
        return _gap("unknown_session_provenance")
    if not _nonblank(export.session_id):
        return _gap("export_missing_session")
    if export.session_id != raw_session_id:
        return _gap("export_session_mismatch")

    raw_ids = {value for value in raw_assistant_message_ids if value}
    if not raw_ids:
        return _gap("missing_message_identity")
    if len(raw_ids) != 1:
        return _gap("ambiguous_assistant_identity")

    if len(export.assistant_messages) != 1:
        return _gap("ambiguous_assistant_identity")
    message = export.assistant_messages[0]

    if message.role != "assistant":
        return _gap("wrong_role")
    if not _nonblank(message.message_id):
        return _gap("export_missing_message_id")
    if message.message_id not in raw_ids:
        return _gap("export_message_unbound")

    # The selected assistant message must itself carry the raw session id.
    if not _nonblank(message.session_id):
        return _gap("export_missing_assistant_session")
    if message.session_id != raw_session_id:
        return _gap("export_assistant_session_mismatch")

    # Every exported part must be bound to that assistant message and session,
    # and every raw part id must appear in the export. A wrong part messageID or
    # sessionID must fail closed (a bare part-id subset check is insufficient).
    raw_parts = {value for value in raw_part_ids if value}
    if not raw_parts.issubset(set(message.part_ids)):
        return _gap("export_part_binding_failed")
    if len(message.part_ids) != len(set(message.part_ids)):
        return _gap("duplicate_part_id")
    for part in message.parts:
        if not _nonblank(part.part_id):
            continue
        if not _nonblank(part.session_id) or not _nonblank(part.message_id):
            return _gap("export_part_unbound")
        if part.session_id != raw_session_id:
            return _gap("export_part_session_mismatch")
        if part.message_id != message.message_id:
            return _gap("export_part_message_mismatch")

    if not _nonblank(message.model_id) or not _nonblank(message.provider_id):
        return _gap("export_missing_model_metadata")

    qualified = qualified_model_id(message.provider_id, message.model_id)
    if qualified != requested_model_id:
        return _gap("model_mismatch")

    if raw_terminal_present and message.finish != raw_terminal_reason:
        return _gap("completion_conflict")
    if message.text != raw_text:
        return _gap("text_conflict")
    if invalid_token_components(message.tokens):
        return _gap("invalid_export_usage")
    if _usage_conflict(flatten_tokens(message.tokens), raw_usage):
        return _gap("usage_conflict")

    return ProvenanceVerdict(
        ok=True, reason=None, observed_model_id=message.model_id,
        observed_provider_id=message.provider_id, qualified_model_id=qualified,
        assistant_message_id=message.message_id)


def raw_usage_map(usage: Any) -> Dict[str, Optional[int]]:
    """The evidence keys used for conflict comparison, from a parsed ``Usage``."""
    if usage is None:
        return {}
    return {
        "input": getattr(usage, "input_tokens", None),
        "output": getattr(usage, "output_tokens", None),
        "reasoning": getattr(usage, "reasoning_tokens", None),
        "total": getattr(usage, "total_tokens", None),
        "cache_read": getattr(usage, "cache_read_tokens", None),
        "cache_write": getattr(usage, "cache_write_tokens", None),
    }


def validate_observation_export(parsed: Any, export: SessionExport,
                                requested_model_id: str) -> ProvenanceVerdict:
    """Convenience wrapper binding a parsed event stream to an export."""
    return validate_session_export(
        export,
        requested_model_id=requested_model_id,
        raw_session_id=parsed.session_id,
        raw_assistant_message_ids=parsed.assistant_message_ids,
        raw_part_ids=parsed.part_ids,
        raw_text=parsed.combined_text,
        raw_terminal_present=parsed.terminal_present,
        raw_terminal_reason=parsed.terminal_reason,
        raw_usage=raw_usage_map(parsed.usage),
    )


def build_sidecar_metadata(*, export: SessionExport, verdict: ProvenanceVerdict,
                           requested_model_id: str, export_path: str,
                           export_sha256: Optional[str],
                           captured: bool) -> Dict[str, Any]:
    """A hashed sidecar record for the persisted export (never a raw rewrite).

    ``assistant_tokens`` is the export's observed assistant usage, kept separate
    from the run-stream ``provider_usage``; it is not assumed to cover CLI
    auxiliary/title/network overhead and the total is never recomputed.
    """
    assistant_tokens = None
    if len(export.assistant_messages) == 1:
        tokens = export.assistant_messages[0].tokens
        assistant_tokens = dict(tokens) if isinstance(tokens, dict) else None
    return {
        "source": SOURCE_LABEL,
        "source_note": SOURCE_NOTE,
        "export_path": export_path,
        "export_sha256": export_sha256,
        "captured": bool(captured),
        "session_id": export.session_id,
        "cli_version": export.version,
        "requested_model_id": requested_model_id,
        "observed_provider_id": verdict.observed_provider_id,
        "observed_model_id": verdict.observed_model_id,
        "qualified_model_id": verdict.qualified_model_id,
        "assistant_message_id": verdict.assistant_message_id,
        "assistant_tokens": assistant_tokens,
        "provenance_ok": verdict.ok,
        "reason": verdict.reason,
    }
