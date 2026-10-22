"""Inbound JSON body guard (OC-027-R1).

FastAPI/Starlette decode the request body with ``json.loads`` before any route
code runs, so a pathologically deep document can raise ``RecursionError`` during
parsing — surfacing as an opaque ``400`` (or ``500``) with no bounded, structured
rejection. This ASGI middleware buffers JSON request bodies, applies an iterative
(non-recursive) depth/size guard, and rejects out-of-bounds bodies with a
structured ``422``/``413`` *before* they reach the parser. In-bounds bodies are
replayed unchanged, so normal request handling is unaffected.

The guard is deliberately generous (it only needs to stay well below the parser's
recursion limit); the precise payload bounds are still enforced by
``app.core.domain.itinerary_draft.validate_draft_payload``.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, List

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_REQUEST_BODY_BYTES = 512 * 1024
MAX_REQUEST_JSON_DEPTH = 64
_JSON_METHODS = frozenset({"POST", "PUT", "PATCH"})


def _is_json_content_type(scope: Scope) -> bool:
    for name, value in scope.get("headers", ()):
        if name == b"content-type":
            return b"application/json" in value.lower()
    return False


def _max_depth(body: bytes) -> int:
    """Iteratively compute maximum container nesting depth (no recursion)."""
    depth = 0
    max_seen = 0
    in_string = False
    escaped = False
    for byte in body:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:  # backslash
                escaped = True
            elif byte == 0x22:  # double quote
                in_string = False
            continue
        if byte == 0x22:
            in_string = True
        elif byte in (0x7B, 0x5B):  # { or [
            depth += 1
            if depth > max_seen:
                max_seen = depth
        elif byte in (0x7D, 0x5D):  # } or ]
            if depth > 0:
                depth -= 1
    return max_seen


def _error_response(status_code: int, code: str, message: str):
    return JSONResponse(status_code=status_code,
                        content={"detail": {"code": code, "message": message}})


class BoundedJsonBodyMiddleware:
    """Reject over-deep / over-large JSON bodies with a structured response."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (scope.get("type") != "http"
                or scope.get("method") not in _JSON_METHODS
                or not _is_json_content_type(scope)):
            await self.app(scope, receive, send)
            return

        body = b""
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            body += message.get("body", b"")
            if len(body) > MAX_REQUEST_BODY_BYTES:
                await _error_response(
                    413, "payload_too_large",
                    "Request body is too large.")(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        if _max_depth(body) > MAX_REQUEST_JSON_DEPTH:
            await _error_response(
                422, "payload_too_deep",
                "Request JSON nesting is too deep.")(scope, receive, send)
            return

        replayed: List[bool] = []

        async def replay() -> Message:
            if not replayed:
                replayed.append(True)
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, replay, send)
