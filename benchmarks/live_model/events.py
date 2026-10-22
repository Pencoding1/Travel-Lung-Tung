"""Parse an opencode ``run --format json`` event stream.

The stream is JSONL: one JSON object per line, generally shaped like::

    {"type": "step_start",  "timestamp": ..., "sessionID": "ses_...", "part": {...}}
    {"type": "text",        "timestamp": ..., "sessionID": "ses_...", "part": {"type": "text", "text": "..."}}
    {"type": "step_finish", "timestamp": ..., "sessionID": "ses_...", "part": {"reason": "stop", "tokens": {...}}}

This parser makes no network call and treats the *absence* of evidence as
unknown, never as a negative fact.

Usage rules (repair OC-021-R1):

* Each token component (input/output/reasoning/cache read/cache write) is kept
  separately. A component is *complete* only when every ``step_finish`` carried a
  valid value for it; only complete components are aggregated. A component that
  is absent/invalid in any step (or in a step with no token block at all) stays
  ``None`` — never a fabricated zero.
* An explicitly supplied ``0`` is a valid value and is preserved.
* Negative or boolean counts are rejected as values (component unknown) and
  recorded in ``invalid_fields``.
* Per-component lower bounds are reported separately (``lower_bounds``) and are
  labelled as such; the provider ``total`` is taken verbatim and never recomputed
  from components, so reasoning/cache are never double-counted.

Terminal rules (repair OC-021-R1):

* Only the explicit provider success reason ``stop`` can terminate a successful
  observation. ``length``, ``tool-calls``, ``error``, a missing reason or any
  unknown reason is never successful, even when text is present.
* Final-stream consistency is required: the last event must not be an incomplete
  ``step_start`` and no assistant text may appear after the terminal
  ``step_finish``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

# The single provider finish reason that denotes a normal successful completion.
SUCCESS_FINISH_REASON = "stop"

# Components kept separate. Cache is nested in the provider payload.
COMPONENTS = ("input", "output", "reasoning", "cache_read", "cache_write")


@dataclass(frozen=True)
class Usage:
    """Provider token usage, component-aware and never zero-fabricated."""

    input_tokens: Optional[int]
    output_tokens: Optional[int]
    reasoning_tokens: Optional[int]
    cache_read_tokens: Optional[int]
    cache_write_tokens: Optional[int]
    total_tokens: Optional[int]
    step_finish_count: int
    token_block_count: int
    complete: bool
    partial: bool
    lower_bounds: Mapping[str, int]
    invalid_fields: Tuple[str, ...]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ParsedEvents:
    line_count: int = 0
    malformed_lines: Tuple[int, ...] = field(default_factory=tuple)
    session_ids: Tuple[str, ...] = field(default_factory=tuple)
    observed_model_ids: Tuple[str, ...] = field(default_factory=tuple)
    observed_provider_ids: Tuple[str, ...] = field(default_factory=tuple)
    event_types: Tuple[str, ...] = field(default_factory=tuple)
    tool_use_count: int = 0
    tool_names: Tuple[str, ...] = field(default_factory=tuple)
    error_count: int = 0
    error_messages: Tuple[str, ...] = field(default_factory=tuple)
    step_finish_reasons: Tuple[str, ...] = field(default_factory=tuple)
    text_parts: Tuple[str, ...] = field(default_factory=tuple)
    # Part identity, retained so an authoritative session export can be bound to
    # the exact raw event parts. These never invent model/provider facts.
    part_ids: Tuple[str, ...] = field(default_factory=tuple)
    part_message_ids: Tuple[str, ...] = field(default_factory=tuple)
    text_message_ids: Tuple[str, ...] = field(default_factory=tuple)
    step_finish_message_ids: Tuple[str, ...] = field(default_factory=tuple)
    terminal_message_id: Optional[str] = None
    usage: Optional[Usage] = None
    terminal_present: bool = False
    terminal_note: Optional[str] = None

    @property
    def session_id(self) -> Optional[str]:
        """The single observed session id, or ``None`` if absent/ambiguous."""
        distinct = {value for value in self.session_ids if value}
        if len(distinct) == 1:
            return next(iter(distinct))
        return None

    @property
    def combined_text(self) -> str:
        return "".join(self.text_parts)

    @property
    def assistant_message_ids(self) -> Tuple[str, ...]:
        """Distinct messageIDs that own assistant text or a step_finish part."""
        return tuple(sorted(set(self.text_message_ids) | set(self.step_finish_message_ids)))

    @property
    def terminal_reason(self) -> Optional[str]:
        """The last ``step_finish`` reason, or ``None`` when absent."""
        return self.step_finish_reasons[-1] if self.step_finish_reasons else None


def _nonblank(value: Any) -> Optional[str]:
    if isinstance(value, bool) or not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _part_id(part: Any) -> Optional[str]:
    if isinstance(part, dict):
        return _nonblank(part.get("id")) or _nonblank(part.get("partID"))
    return None


def _part_message_id(part: Any, event: Any) -> Optional[str]:
    if isinstance(part, dict):
        value = _nonblank(part.get("messageID")) or _nonblank(part.get("messageId"))
        if value:
            return value
    if isinstance(event, dict):
        return _nonblank(event.get("messageID"))
    return None


def _model_hints(event: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """Best-effort model/provider ids from structured event fields only."""
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


def _extract_error(event: Dict[str, Any]) -> Optional[str]:
    event_type = _nonblank(event.get("type"))
    part = event.get("part") if isinstance(event.get("part"), dict) else {}
    part_type = _nonblank(part.get("type"))
    if event_type != "error" and part_type != "error" and not event.get("error"):
        return None
    for node in (event.get("error"), part.get("error"), event, part):
        if isinstance(node, dict):
            for key in ("message", "detail", "reason", "name"):
                text = _nonblank(node.get(key))
                if text:
                    return text
        elif isinstance(node, str) and node.strip():
            return node.strip()
    return "error event"


def _valid_count(value: Any) -> Tuple[bool, Optional[int]]:
    """A non-negative, non-bool integer is valid; anything else is unknown."""
    if isinstance(value, bool) or not isinstance(value, int):
        return False, None
    if value < 0:
        return False, None
    return True, value


def _extract_block(tokens: Mapping[str, Any]) -> Tuple[Dict[str, Optional[int]], List[str]]:
    """Return per-component values (None when absent/invalid) and invalid names."""
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
    return block, invalid


def _aggregate(step_finish_count: int, blocks: List[Dict[str, Optional[int]]],
               invalid: List[str]) -> Optional[Usage]:
    if step_finish_count == 0:
        return None
    if not blocks:
        # Every step_finish lacked a usable token block: usage is unknown.
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
        return sum(values)  # explicit zeros are included, not fabricated

    total = component("total")
    named = {name: component(name) for name in COMPONENTS}
    complete = all(named[name] is not None for name in COMPONENTS) and total is not None
    return Usage(
        input_tokens=named["input"],
        output_tokens=named["output"],
        reasoning_tokens=named["reasoning"],
        cache_read_tokens=named["cache_read"],
        cache_write_tokens=named["cache_write"],
        total_tokens=total,
        step_finish_count=step_finish_count,
        token_block_count=len(blocks),
        complete=complete,
        partial=not complete,
        lower_bounds=lower_bounds,
        invalid_fields=tuple(sorted(set(invalid))),
    )


def parse_event_lines(lines: List[str]) -> ParsedEvents:
    parsed = ParsedEvents()
    malformed: List[int] = []
    sessions: List[str] = []
    models: List[str] = []
    providers: List[str] = []
    types: List[str] = []
    tool_names: List[str] = []
    errors: List[str] = []
    reasons: List[str] = []
    texts: List[str] = []
    part_ids: List[str] = []
    part_message_ids: List[str] = []
    text_message_ids: List[str] = []
    finish_message_ids: List[str] = []

    step_finish_total = 0
    token_blocks: List[Dict[str, Optional[int]]] = []
    invalid_fields: List[str] = []
    last_text_idx = -1
    last_finish_idx = -1
    last_start_idx = -1
    last_finish_message_id: Optional[str] = None

    for index, line in enumerate(lines, start=1):
        parsed.line_count += 1
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

        event_type = _nonblank(event.get("type")) or "unknown"
        types.append(event_type)
        session = _nonblank(event.get("sessionID")) or _nonblank(event.get("sessionId"))
        if session:
            sessions.append(session)

        got_models, got_providers = _model_hints(event)
        models.extend(got_models)
        providers.extend(got_providers)

        part = event.get("part") if isinstance(event.get("part"), dict) else {}
        part_id = _part_id(part)
        if part_id:
            part_ids.append(part_id)
        part_message_id = _part_message_id(part, event)
        if part_message_id:
            part_message_ids.append(part_message_id)

        if event_type == "step_start" or _nonblank(part.get("type")) == "step-start":
            last_start_idx = index

        if event_type == "tool_use" or _nonblank(part.get("type")) == "tool":
            parsed.tool_use_count += 1
            name = _nonblank(part.get("tool")) or _nonblank(part.get("name"))
            if name:
                tool_names.append(name)

        error = _extract_error(event)
        if error is not None:
            parsed.error_count += 1
            errors.append(error)

        if event_type == "step_finish":
            step_finish_total += 1
            last_finish_idx = index
            last_finish_message_id = part_message_id
            if part_message_id:
                finish_message_ids.append(part_message_id)
            reason = _nonblank(part.get("reason"))
            reasons.append(reason or "")
            tokens = part.get("tokens")
            if isinstance(tokens, dict):
                block, invalid = _extract_block(tokens)
                token_blocks.append(block)
                invalid_fields.extend(invalid)

        if event_type == "text" or _nonblank(part.get("type")) == "text":
            last_text_idx = index
            if part_message_id:
                text_message_ids.append(part_message_id)
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text)

    parsed.malformed_lines = tuple(malformed)
    parsed.session_ids = tuple(sorted(set(sessions)))
    parsed.observed_model_ids = tuple(sorted(set(models)))
    parsed.observed_provider_ids = tuple(sorted(set(providers)))
    parsed.event_types = tuple(types)
    parsed.tool_names = tuple(sorted(set(tool_names)))
    parsed.error_messages = tuple(errors)
    parsed.step_finish_reasons = tuple(reasons)
    parsed.text_parts = tuple(texts)
    parsed.part_ids = tuple(sorted(set(part_ids)))
    parsed.part_message_ids = tuple(sorted(set(part_message_ids)))
    parsed.text_message_ids = tuple(sorted(set(text_message_ids)))
    parsed.step_finish_message_ids = tuple(sorted(set(finish_message_ids)))
    parsed.usage = _aggregate(step_finish_total, token_blocks, invalid_fields)

    parsed.terminal_present, parsed.terminal_note = _terminal_state(
        step_finish_count=step_finish_total,
        last_reason=(reasons[-1] if reasons else None),
        has_text=bool(texts),
        tool_use_count=parsed.tool_use_count,
        error_count=parsed.error_count,
        last_text_idx=last_text_idx,
        last_finish_idx=last_finish_idx,
        last_start_idx=last_start_idx,
    )
    if parsed.terminal_present:
        parsed.terminal_message_id = last_finish_message_id
    return parsed


def _terminal_state(*, step_finish_count: int, last_reason: Optional[str], has_text: bool,
                    tool_use_count: int, error_count: int, last_text_idx: int,
                    last_finish_idx: int, last_start_idx: int) -> Tuple[bool, Optional[str]]:
    if step_finish_count == 0:
        return False, "no_step_finish"
    if tool_use_count:
        return False, "tool_use_present"
    if error_count:
        return False, "error_present"
    if last_reason != SUCCESS_FINISH_REASON:
        return False, f"non_success_finish_reason:{last_reason or 'missing'}"
    if not has_text:
        return False, "no_assistant_text"
    if last_text_idx > last_finish_idx:
        return False, "text_after_terminal_finish"
    if last_start_idx > last_finish_idx:
        return False, "incomplete_step_after_terminal_finish"
    return True, None


def parse_event_file(path) -> ParsedEvents:
    from pathlib import Path

    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return parse_event_lines(text.splitlines())
