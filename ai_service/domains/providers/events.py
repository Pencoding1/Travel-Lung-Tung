"""Strict parser for ``opencode run --format json`` JSONL event streams.

Two installed-CLI stream shapes are accepted:

* V1: an explicit ``step_finish`` reason ``stop`` with assistant text, no tool
  events, no error events and a consistent tail (no text/step-start after the
  terminal finish). Usage comes from the step-finish token block.
* V2 (observed with v2.0.32): only ``text`` parts plus optional ``tool_use`` /
  ``error`` events; there is **no** ``step_finish`` and no usage. The end of
  such a stream is therefore only *provisional*: the session export must prove
  the assistant finish reason, text and usage before a response is accepted.

Absent usage stays unknown (``None``), never a fabricated zero; per-component
values are kept separate so cache/reasoning are not double-counted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

SUCCESS_FINISH_REASON = "stop"
COMPONENTS = ("input", "output", "reasoning", "cache_read", "cache_write")


@dataclass(frozen=True)
class EventUsage:
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    reasoning_tokens: Optional[int]
    cache_read_tokens: Optional[int]
    cache_write_tokens: Optional[int]
    total_tokens: Optional[int]
    complete: bool
    lower_bounds: Mapping[str, int]
    invalid_fields: Tuple[str, ...]


@dataclass
class ParsedStream:
    malformed_lines: Tuple[int, ...] = field(default_factory=tuple)
    session_ids: Tuple[str, ...] = field(default_factory=tuple)
    observed_model_ids: Tuple[str, ...] = field(default_factory=tuple)
    observed_provider_ids: Tuple[str, ...] = field(default_factory=tuple)
    assistant_message_ids: Tuple[str, ...] = field(default_factory=tuple)
    part_ids: Tuple[str, ...] = field(default_factory=tuple)
    text_parts: Tuple[str, ...] = field(default_factory=tuple)
    finish_reasons: Tuple[str, ...] = field(default_factory=tuple)
    tool_use_count: int = 0
    error_count: int = 0
    usage: Optional[EventUsage] = None
    terminal_present: bool = False
    terminal_note: Optional[str] = None
    stream_format: str = "unknown"

    @property
    def provisional_terminal(self) -> bool:
        """True when the end of stream is not self-evidencing (V2)."""
        return self.stream_format == "v2"

    @property
    def session_id(self) -> Optional[str]:
        distinct = {value for value in self.session_ids if value}
        return next(iter(distinct)) if len(distinct) == 1 else None

    @property
    def combined_text(self) -> str:
        return "".join(self.text_parts)

    @property
    def terminal_reason(self) -> Optional[str]:
        return self.finish_reasons[-1] if self.finish_reasons else None


def _nonblank(value: Any) -> Optional[str]:
    if isinstance(value, bool) or not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _valid_count(value: Any) -> Tuple[bool, Optional[int]]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return False, None
    return True, value


def _part_id(part: Mapping[str, Any]) -> Optional[str]:
    return _nonblank(part.get("id")) or _nonblank(part.get("partID"))


def _part_message_id(part: Mapping[str, Any], event: Mapping[str, Any]) -> Optional[str]:
    return (_nonblank(part.get("messageID")) or _nonblank(part.get("messageId"))
            or _nonblank(event.get("messageID")))


def _extract_block(tokens: Mapping[str, Any]
                   ) -> Tuple[Dict[str, Optional[int]], List[str], bool]:
    block: Dict[str, Optional[int]] = {}
    invalid: List[str] = []
    for name in ("input", "output", "reasoning"):
        valid, value = _valid_count(tokens.get(name))
        block[name] = value
        if name in tokens and not valid:
            invalid.append(name)
    cache = tokens.get("cache")
    cache = cache if isinstance(cache, dict) else {}
    for name, key in (("cache_read", "read"), ("cache_write", "write")):
        valid, value = _valid_count(cache.get(key))
        block[name] = value
        if key in cache and not valid:
            invalid.append(name)
    valid, value = _valid_count(tokens.get("total"))
    block["total"] = value
    if "total" in tokens and not valid:
        invalid.append("total")
    return block, invalid, bool(tokens)


def _aggregate(step_finish_count: int, blocks: List[Dict[str, Optional[int]]],
               invalid: List[str]) -> Optional[EventUsage]:
    if step_finish_count == 0 or not blocks:
        return None

    all_steps_have_blocks = len(blocks) == step_finish_count
    lower_bounds = {
        name: sum(block[name] for block in blocks if block[name] is not None)
        for name in COMPONENTS
    }

    def component(name: str) -> Optional[int]:
        if not all_steps_have_blocks:
            return None
        values = [block[name] for block in blocks]
        if any(value is None for value in values):
            return None
        return sum(values)  # explicit zeros are values

    named = {name: component(name) for name in COMPONENTS}
    total = component("total")
    complete = all(named[name] is not None for name in COMPONENTS) and total is not None
    return EventUsage(
        input_tokens=named["input"],
        output_tokens=named["output"],
        reasoning_tokens=named["reasoning"],
        cache_read_tokens=named["cache_read"],
        cache_write_tokens=named["cache_write"],
        total_tokens=total,
        complete=complete,
        lower_bounds=lower_bounds,
        invalid_fields=tuple(sorted(set(invalid))),
    )


def _model_hints(event: Mapping[str, Any]) -> Tuple[List[str], List[str]]:
    models: List[str] = []
    providers: List[str] = []

    def scan(node: Any) -> None:
        if not isinstance(node, dict):
            return
        for key in ("modelID", "modelId", "model"):
            value = _nonblank(node.get(key))
            if value:
                models.append(value)
        for key in ("providerID", "providerId", "provider"):
            value = _nonblank(node.get(key))
            if value:
                providers.append(value)

    part = event.get("part")
    scan(part)
    if isinstance(part, dict):
        scan(part.get("message"))
        scan(part.get("model"))
    scan(event.get("message"))
    return models, providers


def _has_error(event: Mapping[str, Any], part: Mapping[str, Any]) -> bool:
    return (event.get("type") == "error" or part.get("type") == "error"
            or bool(event.get("error")))


def _has_tool_use(event: Mapping[str, Any], part: Mapping[str, Any]) -> bool:
    return (event.get("type") == "tool_use"
            or event.get("type") == "tool_call"
            or part.get("type") == "tool")


def parse_event_bytes(raw: bytes) -> ParsedStream:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return ParsedStream(malformed_lines=(1,),
                            terminal_note="event stream is not UTF-8")
    return parse_event_lines(text.splitlines())


def parse_event_lines(lines: List[str]) -> ParsedStream:
    parsed = ParsedStream()
    malformed: List[int] = []
    sessions: List[str] = []
    models: List[str] = []
    providers: List[str] = []
    message_ids: List[str] = []
    part_ids: List[str] = []
    texts: List[str] = []
    reasons: List[str] = []

    step_finish_count = 0
    blocks: List[Dict[str, Optional[int]]] = []
    invalid_fields: List[str] = []
    last_text_idx = -1
    last_finish_idx = -1
    last_start_idx = -1

    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            malformed.append(index)
            continue
        if not isinstance(event, dict):
            malformed.append(index)
            continue

        part = event.get("part") if isinstance(event.get("part"), dict) else {}
        session = (_nonblank(event.get("sessionID"))
                   or _nonblank(event.get("sessionId")))
        if session:
            sessions.append(session)

        got_models, got_providers = _model_hints(event)
        models.extend(got_models)
        providers.extend(got_providers)

        part_id = _part_id(part)
        if part_id:
            part_ids.append(part_id)
        message_id = _part_message_id(part, event)
        if message_id:
            message_ids.append(message_id)

        event_type = _nonblank(event.get("type")) or "unknown"
        part_type = _nonblank(part.get("type"))

        if event_type == "step_start" or part_type == "step-start":
            last_start_idx = index

        if _has_tool_use(event, part):
            parsed.tool_use_count += 1

        if _has_error(event, part):
            parsed.error_count += 1

        if event_type == "step_finish":
            step_finish_count += 1
            last_finish_idx = index
            reason = _nonblank(part.get("reason"))
            reasons.append(reason or "")
            tokens = part.get("tokens")
            if isinstance(tokens, dict):
                block, invalid, has_block = _extract_block(tokens)
                if has_block:
                    blocks.append(block)
                invalid_fields.extend(invalid)

        if event_type == "text" or part_type == "text":
            last_text_idx = index
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text)

    parsed.malformed_lines = tuple(malformed)
    parsed.session_ids = tuple(sorted(set(sessions)))
    parsed.observed_model_ids = tuple(sorted(set(models)))
    parsed.observed_provider_ids = tuple(sorted(set(providers)))
    parsed.assistant_message_ids = tuple(sorted(set(message_ids)))
    parsed.part_ids = tuple(sorted(set(part_ids)))
    parsed.text_parts = tuple(texts)
    parsed.finish_reasons = tuple(reasons)
    parsed.usage = _aggregate(step_finish_count, blocks, invalid_fields)
    if step_finish_count:
        parsed.stream_format = "v1"
    elif texts:
        parsed.stream_format = "v2"
    else:
        parsed.stream_format = "unknown"
    parsed.terminal_present, parsed.terminal_note = _terminal_state(
        step_finish_count=step_finish_count,
        last_reason=(reasons[-1] if reasons else None),
        has_text=bool(texts),
        tool_use_count=parsed.tool_use_count,
        error_count=parsed.error_count,
        last_text_idx=last_text_idx,
        last_finish_idx=last_finish_idx,
        last_start_idx=last_start_idx,
        stream_format=parsed.stream_format,
    )
    return parsed


def _terminal_state(*, step_finish_count: int, last_reason: Optional[str],
                    has_text: bool, tool_use_count: int, error_count: int,
                    last_text_idx: int, last_finish_idx: int,
                    last_start_idx: int,
                    stream_format: str = "v1") -> Tuple[bool, Optional[str]]:
    if tool_use_count:
        return False, "tool_use_present"
    if error_count:
        return False, "error_present"
    if step_finish_count == 0:
        if stream_format == "v2" and has_text:
            # V2 emits no terminal event. The session export is the authority
            # for finish/text/usage; this is only a provisional clean end.
            return True, "v2_stream_without_step_finish"
        return False, "no_step_finish"
    if last_reason != SUCCESS_FINISH_REASON:
        return False, f"non_success_finish_reason:{last_reason or 'missing'}"
    if not has_text:
        return False, "no_assistant_text"
    if last_text_idx > last_finish_idx:
        return False, "text_after_terminal_finish"
    if last_start_idx > last_finish_idx:
        return False, "incomplete_step_after_terminal_finish"
    return True, None
