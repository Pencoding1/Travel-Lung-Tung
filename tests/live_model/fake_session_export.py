"""Hand-authored session-export fixtures for the OC-033 provenance tests.

These fixtures mirror the *shape* of a real ``opencode export`` payload (the
DS-004 diagnostic), with a synthetic session. Neither the request nor the export
proves an upstream model checkpoint; the tests only exercise strict binding.

The assistant message carries ``modelID``/``providerID`` separately, so the
observed identity is ``providerID + '/' + modelID``.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

REQUESTED = "aibox/ds/deepseek-flash"
PROVIDER = "aibox"
MODEL = "ds/deepseek-flash"
SESSION = "ses_exportfixture000000000000000001"
MESSAGE = "msg_exportfixture00000000000000001"
PART_START = "prt_exportfixture00000000000000001"
PART_REASON = "prt_exportfixture00000000000000002"
PART_TEXT = "prt_exportfixture00000000000000003"
PART_FINISH = "prt_exportfixture00000000000000004"
TS = 1792145062897

DEFAULT_TOKENS = {"total": 213, "input": 194, "output": 6, "reasoning": 13,
                  "cache": {"write": 0, "read": 0}}


def raw_events(text: str = '{"ok":true}', session: str = SESSION,
               message: str = MESSAGE, reason: str = "stop",
               tokens: dict | None = None) -> list:
    """Raw ``run --format json`` lines that carry session/message/part ids but
    deliberately no ``modelID``/``providerID`` (the DS-004 condition)."""
    if tokens is None:
        tokens = DEFAULT_TOKENS
    events = [
        {"type": "step_start", "timestamp": TS, "sessionID": session,
         "part": {"id": PART_START, "messageID": message, "sessionID": session,
                  "type": "step-start"}},
        {"type": "text", "timestamp": TS, "sessionID": session,
         "part": {"id": PART_TEXT, "messageID": message, "sessionID": session,
                  "type": "text", "text": text}},
        {"type": "step_finish", "timestamp": TS, "sessionID": session,
         "part": {"id": PART_FINISH, "reason": reason, "messageID": message,
                  "sessionID": session, "type": "step-finish", "tokens": tokens,
                  "cost": 0}},
    ]
    return [json.dumps(event) for event in events]


def build_export(text: str = '{"ok":true}', session: str = SESSION,
                 message: str = MESSAGE, model: str = MODEL,
                 provider: str = PROVIDER, role: str = "assistant",
                 finish: str | None = "stop", tokens: dict | None = None,
                 include_reasoning: bool = True) -> dict:
    """A well-formed export payload; callers may mutate the returned dict."""
    if tokens is None:
        tokens = DEFAULT_TOKENS
    parts = [{"type": "step-start", "id": PART_START, "messageID": message,
              "sessionID": session}]
    if include_reasoning:
        parts.append({"type": "reasoning", "text": "think",
                      "id": PART_REASON, "messageID": message, "sessionID": session})
    parts.append({"type": "text", "text": text, "id": PART_TEXT,
                  "messageID": message, "sessionID": session})
    parts.append({"type": "step-finish", "reason": finish or "stop", "tokens": tokens,
                  "id": PART_FINISH, "messageID": message, "sessionID": session})
    assistant_info = {"role": role, "mode": "transport-diagnostic", "cost": 0,
                      "id": message, "sessionID": session, "finish": finish,
                      "tokens": tokens}
    if role == "assistant":
        assistant_info["modelID"] = model
        assistant_info["providerID"] = provider
    return {
        "info": {"id": session, "version": "1.18.35", "agent": "transport-diagnostic",
                 "model": {"id": model, "providerID": provider, "variant": "default"}},
        "messages": [
            {"info": {"role": "user", "id": "msg_user", "sessionID": session},
             "parts": [{"type": "text", "text": "prompt", "id": "prt_user",
                        "messageID": "msg_user", "sessionID": session}]},
            {"info": assistant_info, "parts": parts},
        ],
    }


def build_export_bytes(**kwargs) -> bytes:
    return json.dumps(build_export(**kwargs)).encode("utf-8")


def clone(value: dict) -> dict:
    return copy.deepcopy(value)


def ds004_paths() -> tuple[Path, Path]:
    root = Path(__file__).resolve().parents[2]
    base = root / "docs" / "project" / "handoffs" / "DS-004"
    return base / "events.jsonl", base / "session-export.json"
