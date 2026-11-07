"""Native AIbox HTTP provider for the AI service (KT-01 / KT-04).

Provides an OpenAI-compatible HTTP transport for ``https://api.ai-box.vn/v1/chat/completions``
with strict request/response validation, safe error diagnostics (never logging
or returning prompt text, headers, or credentials), and tool-turn message
normalization for DeepSeek/OpenAI compatibility.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import stat
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import httpx

from .errors import ModelUnavailableError

logger = logging.getLogger("Travel_Lung_Tung_Agent")

ENDPOINT = "https://api.ai-box.vn/v1/chat/completions"
MODEL = "ds/deepseek-flash"
MAX_BYTES = 2_000_000
MAX_PROMPT = 200_000
REQUEST_DEADLINE = 65
MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}\Z")
SAFE_TOKEN_RE = re.compile(r"[A-Za-z0-9_.\[\]:/-]{1,64}\Z")
FIELDS = {
    "model",
    "messages",
    "tools",
    "tool_choice",
    "temperature",
    "top_p",
    "response_format",
    "max_tokens",
    "max_completion_tokens",
    "stream",
}

ERROR_CATEGORIES = {
    400: "bad_request_schema",
    401: "authentication",
    402: "quota_or_rate_limit",
    403: "forbidden",
    404: "endpoint_or_model_not_found",
    413: "payload_too_large",
    422: "unprocessable_request",
    429: "quota_or_rate_limit",
    500: "upstream_server_error",
    502: "upstream_bad_gateway",
    503: "upstream_unavailable",
    504: "upstream_timeout",
}


class AdapterError(ValueError):
    """Sanitized transport/validation error with safe diagnostic metadata."""

    def __init__(
        self,
        code: str,
        http_status: Optional[int] = None,
        attempts: int = 0,
        *,
        error_category: Optional[str] = None,
        safe_error_type: Optional[str] = None,
        safe_error_param: Optional[str] = None,
        request_shape: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.http_status = http_status
        self.attempts = attempts
        self.error_category = error_category or (
            ERROR_CATEGORIES.get(http_status, "http_error")
            if http_status is not None
            else code
        )
        self.safe_error_type = safe_error_type
        self.safe_error_param = safe_error_param
        self.request_shape = request_shape
        super().__init__(code)


def _safe_identifier(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or not SAFE_TOKEN_RE.fullmatch(cleaned):
        return None
    lowered = cleaned.lower()
    if any(m in lowered for m in ("bearer", "key", "token", "secret", "auth")):
        return "redacted_identifier"
    return cleaned


def summarize_request_shape(body: Mapping[str, Any]) -> Dict[str, Any]:
    """Build a non-sensitive summary of the outgoing request shape (KT-01).

    Never includes message text, tool arguments, headers, or credentials.
    """
    messages = body.get("messages") if isinstance(body, Mapping) else None
    msg_list = messages if isinstance(messages, list) else []
    roles: List[str] = []
    assistant_tool_turns = 0
    tool_result_turns = 0
    missing_assistant_content = 0

    for msg in msg_list:
        if not isinstance(msg, Mapping):
            continue
        role = msg.get("role")
        if isinstance(role, str) and SAFE_TOKEN_RE.fullmatch(role):
            roles.append(role)
        if role == "assistant" and msg.get("tool_calls"):
            assistant_tool_turns += 1
            if "content" not in msg:
                missing_assistant_content += 1
        elif role == "tool":
            tool_result_turns += 1

    tools = body.get("tools") if isinstance(body, Mapping) else None
    tool_count = len(tools) if isinstance(tools, list) else 0
    return {
        "message_count": len(msg_list),
        "roles": roles[:32],
        "has_tools": bool(tool_count),
        "tool_count": tool_count,
        "has_tool_choice": "tool_choice" in body if isinstance(body, Mapping) else False,
        "has_response_format": "response_format" in body if isinstance(body, Mapping) else False,
        "assistant_tool_call_turns": assistant_tool_turns,
        "tool_result_turns": tool_result_turns,
        "missing_assistant_content": missing_assistant_content,
    }


def extract_safe_error_diagnostics(raw_bytes: bytes) -> Dict[str, Optional[str]]:
    """Extract only safe, non-echoing error classification tokens from an HTTP error body."""
    if not raw_bytes or len(raw_bytes) > 16384:
        return {"safe_error_type": None, "safe_error_param": None, "safe_error_code": None}
    try:
        parsed = json.loads(raw_bytes.decode("utf-8", errors="replace"))
    except Exception:
        return {"safe_error_type": None, "safe_error_param": None, "safe_error_code": None}
    if not isinstance(parsed, dict):
        return {"safe_error_type": None, "safe_error_param": None, "safe_error_code": None}
    err = parsed.get("error")
    if not isinstance(err, dict):
        err = parsed
    return {
        "safe_error_type": _safe_identifier(err.get("type")),
        "safe_error_param": _safe_identifier(err.get("param")),
        "safe_error_code": _safe_identifier(err.get("code")),
    }


def _key(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 4096
        or any(ord(c) < 33 or ord(c) > 126 for c in value)
    ):
        raise AdapterError("aibox_credential_invalid")
    return value


def load_key(root: Path, environ: Optional[Mapping[str, str]] = None) -> str:
    """Process presence wins; otherwise read exactly one bounded named file key."""
    source = os.environ if environ is None else environ
    if "AIBOX_API" in source:
        return _key(source["AIBOX_API"])
    target = root / ".env"
    try:
        info = target.lstat()
        if not stat.S_ISREG(info.st_mode) or target.is_symlink() or info.st_size > 65536:
            raise AdapterError("aibox_credential_file_invalid")
        raw = target.read_bytes()
        if len(raw) > 65536 or b"\0" in raw:
            raise AdapterError("aibox_credential_file_invalid")
        text = raw.decode("utf-8-sig")
    except AdapterError:
        raise
    except (OSError, UnicodeError):
        raise AdapterError("aibox_credential_unavailable") from None
    found = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, sep, value = line.partition("=")
        if name.strip() != "AIBOX_API":
            continue
        if not sep:
            raise AdapterError("aibox_credential_file_invalid")
        value = value.strip()
        if value[:1] in ('"', "'"):
            if len(value) < 2 or value[-1] != value[0]:
                raise AdapterError("aibox_credential_file_invalid")
            value = value[1:-1]
        found.append(value)
    if len(found) != 1:
        raise AdapterError("aibox_credential_missing_or_duplicate")
    return _key(found[0])


def _normalize_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensure messages conform strictly to DeepSeek/OpenAI tool-call schema (KT-01).

    * Assistant messages with ``tool_calls`` always carry an explicit ``content``
      key (``None`` when absent).
    * Tool messages strip non-standard extra keys (such as ``name``) that cause
      strict OpenAI v1 / DeepSeek gateways to reject follow-up turns with HTTP 400.
    """
    normalized: List[Dict[str, Any]] = []
    for msg in messages:
        item = dict(msg)
        role = item.get("role")
        if role == "assistant" and item.get("tool_calls"):
            if "content" not in item:
                item["content"] = None
        elif role == "tool":
            content = item.get("content")
            if not isinstance(content, str):
                content = "" if content is None else json.dumps(content, ensure_ascii=False)
            clean_tool: Dict[str, Any] = {
                "role": "tool",
                "tool_call_id": item.get("tool_call_id", ""),
                "content": content,
            }
            item = clean_tool
        normalized.append(item)
    return normalized


def prepare(payload: Any, *, expected_model: str = MODEL) -> Dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) - FIELDS:
        raise AdapterError("aibox_unsupported_control")
    if payload.get("model", expected_model) != expected_model or payload.get("stream", False) is not False:
        raise AdapterError("aibox_model_or_stream_invalid")
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages or any(not isinstance(m, dict) for m in messages):
        raise AdapterError("aibox_messages_invalid")
    body = {k: v for k, v in payload.items() if k not in ("max_completion_tokens", "stream")}
    body["model"] = expected_model
    body["stream"] = False
    body["messages"] = _normalize_messages(messages)
    for name, maximum in [("temperature", 2), ("top_p", 1)]:
        if name in body:
            value = body[name]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 <= value <= maximum
            ):
                raise AdapterError("aibox_sampling_invalid")
    if "max_tokens" in payload and "max_completion_tokens" in payload:
        raise AdapterError("aibox_token_limit_conflict")
    limit = payload.get("max_completion_tokens", payload.get("max_tokens"))
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 65536:
            raise AdapterError("aibox_token_limit_invalid")
        body["max_tokens"] = limit
    try:
        prompt_length = len(json.dumps(body, ensure_ascii=False, allow_nan=False))
    except (ValueError, TypeError, RecursionError):
        raise AdapterError("aibox_payload_invalid") from None
    if prompt_length > MAX_PROMPT:
        raise AdapterError("aibox_prompt_too_large")
    return body


def validate_response(data: Any, *, requested_model: str = MODEL) -> Dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("choices"), list) or not data["choices"]:
        raise AdapterError("aibox_response_invalid")
    for choice in data["choices"]:
        if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
            raise AdapterError("aibox_response_invalid")
        message = choice["message"]
        if message.get("role") != "assistant":
            raise AdapterError("aibox_response_invalid")
        content, calls = message.get("content"), message.get("tool_calls")
        if content is not None and not isinstance(content, str):
            raise AdapterError("aibox_response_invalid")
        if calls is not None:
            if not isinstance(calls, list) or len(calls) > 32:
                raise AdapterError("aibox_response_invalid")
            for call in calls:
                if (
                    not isinstance(call, dict)
                    or call.get("type") != "function"
                    or not isinstance(call.get("id"), str)
                ):
                    raise AdapterError("aibox_response_invalid")
                fn = call.get("function")
                if (
                    not isinstance(fn, dict)
                    or not isinstance(fn.get("name"), str)
                    or not isinstance(fn.get("arguments"), str)
                ):
                    raise AdapterError("aibox_response_invalid")
        if content is None and not calls:
            raise AdapterError("aibox_response_invalid")
    observed = data.get("model")
    if observed is not None and (not isinstance(observed, str) or not MODEL_NAME.fullmatch(observed)):
        raise AdapterError("aibox_response_identity_invalid")
    usage = data.get("usage")
    if usage is not None and not isinstance(usage, dict):
        raise AdapterError("aibox_response_usage_invalid")
    clean = {}
    for name in ["prompt_tokens", "completion_tokens", "total_tokens"]:
        value = (usage or {}).get(name)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise AdapterError("aibox_response_usage_invalid")
        clean[name] = value
    data["usage"] = clean
    data["_provider"] = {
        "provider": "aibox",
        "ok": True,
        "requested_model": requested_model,
        "observed_model": observed,
        "identity_source": "provider_response" if observed else "unavailable",
        "upstream_version_verified": False,
        "usage": clean,
        "attempts": 1,
    }
    return data


class AiboxHttpProvider:
    """Bounded async HTTP client for AIbox chat completions."""

    def __init__(self, root: Path, *, model: str = MODEL, transport: Any = None):
        self.root = root
        self.model = model
        self.transport = transport
        self.semaphore = asyncio.Semaphore(2)

    async def complete(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req_payload = dict(payload) if isinstance(payload, dict) else payload
        if isinstance(req_payload, dict) and "model" not in req_payload:
            req_payload["model"] = self.model
        body = prepare(req_payload, expected_model=self.model)
        shape = summarize_request_shape(body)
        key = load_key(self.root)
        attempted = False
        try:
            async with asyncio.timeout(REQUEST_DEADLINE), self.semaphore:
                async with httpx.AsyncClient(
                    timeout=60.0,
                    follow_redirects=False,
                    transport=self.transport,
                    trust_env=False,
                ) as client:
                    attempted = True
                    async with client.stream(
                        "POST",
                        ENDPOINT,
                        headers={"Authorization": "Bearer " + key},
                        json=body,
                    ) as response:
                        status = response.status_code
                        if status != 200:
                            err_chunks: List[bytes] = []
                            err_size = 0
                            try:
                                async for chunk in response.aiter_bytes():
                                    err_size += len(chunk)
                                    if err_size > 16384:
                                        break
                                    err_chunks.append(chunk)
                            except Exception:
                                pass
                            diag = extract_safe_error_diagnostics(b"".join(err_chunks))
                            codes = {
                                401: "aibox_authentication_failed",
                                403: "aibox_forbidden",
                                402: "aibox_quota_or_rate_limit",
                                429: "aibox_quota_or_rate_limit",
                            }
                            code = codes.get(status, "aibox_http_error")
                            category = ERROR_CATEGORIES.get(status, "http_error")
                            logger.warning(
                                "AIbox HTTP %s (%s): category=%s type=%s param=%s shape=%s",
                                status,
                                code,
                                category,
                                diag.get("safe_error_type"),
                                diag.get("safe_error_param"),
                                shape,
                            )
                            raise AdapterError(
                                code,
                                status,
                                int(attempted),
                                error_category=category,
                                safe_error_type=diag.get("safe_error_type"),
                                safe_error_param=diag.get("safe_error_param"),
                                request_shape=shape,
                            )
                        chunks: List[bytes] = []
                        size = 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > MAX_BYTES:
                                raise AdapterError("aibox_response_too_large", request_shape=shape)
                            chunks.append(chunk)
                try:
                    data = json.loads(b"".join(chunks))
                except (ValueError, UnicodeError, RecursionError):
                    raise AdapterError("aibox_response_invalid", request_shape=shape) from None
                return validate_response(data, requested_model=self.model)
        except AdapterError as exc:
            exc.attempts = int(attempted)
            if exc.request_shape is None:
                exc.request_shape = shape
            raise
        except (httpx.TimeoutException, TimeoutError):
            raise AdapterError(
                "aibox_timeout",
                attempts=int(attempted),
                error_category="timeout",
                request_shape=shape,
            ) from None
        except httpx.HTTPError:
            raise AdapterError(
                "aibox_transport_error",
                attempts=int(attempted),
                error_category="transport_error",
                request_shape=shape,
            ) from None
