"""Fake opencode JSON event builders used by the collector tests.

These are hand-authored engineering fixtures only. They never represent a live
call and never exercise the network.
"""

from __future__ import annotations

import json

MODEL = "aibox/ds/deepseek-flash"
PROVIDER = "aibox"
SESSION = "ses_fake00000000000000000000000001"
TS = 1792118857279


def _line(event: dict) -> str:
    return json.dumps(event)


def step_start(session: str = SESSION) -> str:
    return _line({"type": "step_start", "timestamp": TS, "sessionID": session,
                  "part": {"type": "step-start"}})


def model_event(session: str = SESSION, model: str = MODEL,
                provider: str = PROVIDER) -> str:
    return _line({"type": "message", "timestamp": TS, "sessionID": session,
                  "part": {"type": "message", "providerID": provider, "modelID": model}})


def text(session: str = SESSION, value: str = "{}") -> str:
    return _line({"type": "text", "timestamp": TS, "sessionID": session,
                  "part": {"type": "text", "text": value}})


_DEFAULT_TOKENS = object()


def step_finish(session: str = SESSION, reason: str = "stop",
                tokens=_DEFAULT_TOKENS) -> str:
    """Build a step_finish. ``tokens=None`` omits the token block entirely."""
    if tokens is _DEFAULT_TOKENS:
        tokens = {"total": 100, "input": 60, "output": 30, "reasoning": 5,
                  "cache": {"write": 0, "read": 5}}
    part = {"type": "step-finish", "reason": reason, "cost": 0}
    if tokens is not None:
        part["tokens"] = tokens
    return _line({"type": "step_finish", "timestamp": TS, "sessionID": session,
                  "part": part})


def tool_use(name: str = "bash", session: str = SESSION) -> str:
    return _line({"type": "tool_use", "timestamp": TS, "sessionID": session,
                  "part": {"type": "tool", "tool": name}})


def error(message: str = "provider error", session: str = SESSION) -> str:
    return _line({"type": "error", "timestamp": TS, "sessionID": session,
                  "error": {"message": message}})


def stream(*events: str) -> list:
    return list(events)
