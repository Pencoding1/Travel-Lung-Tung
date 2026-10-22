"""Fakes and fixtures for the OC-009 chat/memory tests.

Every external collaborator (model endpoint, MCP session) is replaced through
the module seams in ``ai_service.main`` or injected directly into the pure
``domains.chat_agent`` loop. No network, live model, database server or
credential is used. Evidence produced here is **mocked contract evidence**.

The five-profile integration fixtures are synthetic test fixtures, not human
participants and not an H3 model run.
"""

import json
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from domains import jev_intent

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = REPO_ROOT / "ai_service"
if str(AI_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_ROOT))


# ---------------------------------------------------------------------------
# CallToolResult stand-ins
# ---------------------------------------------------------------------------
class _Text:
    def __init__(self, text):
        self.text = text


class ToolResult:
    def __init__(self, text=None, is_error=False):
        self.isError = is_error
        self.content = [] if text is None else [_Text(text)]


def ok_json(payload):
    return ToolResult(json.dumps(payload))


def err_json(payload):
    return ToolResult(json.dumps(payload), is_error=True)


# ---------------------------------------------------------------------------
# Model fakes
# ---------------------------------------------------------------------------
def model_message(content=None, tool_calls=None, usage=None):
    message = {}
    if content is not None:
        message["content"] = content
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    response = {"choices": [{"message": message}]}
    if usage is not None:
        response["usage"] = usage
    return response


def tool_call(name, args, call_id="call_1"):
    args = args if isinstance(args, str) else json.dumps(args)
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": args}}


class ScriptedModel:
    """Returns queued responses in order; records every call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def __call__(self, messages, tools):
        self.calls.append({"messages": list(messages), "tools": list(tools)})
        if not self.responses:
            raise AssertionError("no scripted model response left")
        return self.responses.pop(0)


class ScriptedTools:
    def __init__(self, handlers=None):
        self.handlers = handlers or {}
        self.calls = []

    async def __call__(self, name, args):
        self.calls.append({"tool": name, "args": dict(args)})
        handler = self.handlers.get(name)
        if handler is None:
            raise AssertionError(f"unexpected tool call: {name}")
        return handler(args)


# ---------------------------------------------------------------------------
# MCP session fake (for the main-module seams)
# ---------------------------------------------------------------------------
class _MCPTool:
    def __init__(self, name, description="d", schema=None):
        self.name = name
        self.description = description
        self.inputSchema = schema or {"type": "object"}


class _MCPToolList:
    def __init__(self, tools):
        self.tools = tools


class FakeMCPSession:
    def __init__(self, tool_names, handlers=None):
        self.tool_names = list(tool_names)
        self.handlers = handlers or {}
        self.calls = []

    async def initialize(self):
        return None

    async def list_tools(self):
        return _MCPToolList([_MCPTool(n) for n in self.tool_names])

    async def call_tool(self, name, arguments=None):
        self.calls.append({"tool": name, "args": dict(arguments or {})})
        handler = self.handlers.get(name)
        if handler is None:
            raise AssertionError(f"unexpected tool call: {name}")
        return handler(arguments or {})


def mcp_seam(session):
    @asynccontextmanager
    async def _seam():
        yield session

    return _seam


# ---------------------------------------------------------------------------
# Jev transport fake: intent classification never uses the generation model
# ---------------------------------------------------------------------------
def jev_choice_response(choice="TRAVEL", confidence=0.9, probabilities=None,
                        model="jev-test-1", usage=None):
    """Canned TypeSafe response. Total is deliberately absent (undocumented)."""
    if probabilities is None:
        probabilities = {
            "CHITCHAT": 0.05 if choice != "CHITCHAT" else 0.8,
            "TRAVEL": 0.9 if choice == "TRAVEL" else 0.1,
            "UNCERTAIN": 0.05 if choice != "UNCERTAIN" else 0.8,
        }
        if choice == "CHITCHAT":
            probabilities = {"CHITCHAT": 0.9, "TRAVEL": 0.05,
                             "UNCERTAIN": 0.05}
        elif choice == "UNCERTAIN":
            probabilities = {"CHITCHAT": 0.05, "TRAVEL": 0.05,
                             "UNCERTAIN": 0.9}
    if usage is None:
        usage = {"input_tokens": 4, "output_tokens": 1}
    return {
        "model": model,
        "answers": {
            "intent": {
                "type": "choice",
                "choice": choice,
                "probabilities": probabilities,
                "confidence": confidence,
            }
        },
        "usage": usage,
    }


def install_fake_jev(choice="TRAVEL", *, confidence=0.9, probabilities=None,
                     model="jev-test-1", usage=None, handler=None, env=None,
                     response=None):
    """Inject a canned Jev HTTP transport into the process-local router."""
    payload = response if response is not None else jev_choice_response(
        choice=choice, confidence=confidence, probabilities=probabilities,
        model=model, usage=usage)

    def _default_handler(request):
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler or _default_handler)
    mapping = env if env is not None else {
        "TYPESAFE_API_KEY": "dummy-test-key",
        "JEV_MIN_CONFIDENCE": "0.5",
    }
    config = jev_intent.configure_intent_router(mapping, transport=transport)
    return {"config": config, "payload": payload, "transport": transport}


# ---------------------------------------------------------------------------
# Generation-model fake: only agent/chitchat calls reach this seam now.
# ---------------------------------------------------------------------------
def hub_llm(agent_responses=None):
    responses = list(agent_responses or [])
    state = {"agent_calls": 0, "payloads": []}

    async def _call(payload):
        state["agent_calls"] += 1
        state["payloads"].append(payload)
        if not responses:
            raise AssertionError("no scripted agent response left")
        return responses.pop(0)

    _call.state = state
    return _call


# ---------------------------------------------------------------------------
# JWT helper (synthetic secret only)
# ---------------------------------------------------------------------------
def make_token(subject="user-1", secret="test-secret", exp_offset=3600,
               algorithm="HS256", include_sub=True, include_exp=True):
    import jwt
    claims = {}
    if include_sub:
        claims["sub"] = subject
    if include_exp:
        claims["exp"] = int(time.time()) + exp_offset
    return jwt.encode(claims, secret, algorithm=algorithm)


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def bearer_value(token):
    return f"Bearer {token}"


# ---------------------------------------------------------------------------
# Five synthetic profiles (fixtures, NOT human participants / not H3)
# ---------------------------------------------------------------------------
def five_profiles():
    categories = ["cat_coffee", "cat_museum", "cat_streetfood",
                  "cat_park", "cat_nightlife"]
    profiles = []
    for index, category in enumerate(categories, start=1):
        profiles.append({
            "subject": f"synthetic-user-{index}",
            "profile": {
                "preferred_categories": {category: 9.0},
                "tags": [f"fixture-{index}"],
                "budget": 100000.0 * index,
                "currency": "VND",
                "pace": ["relaxed", "moderate", "packed"][index % 3],
            },
        })
    return profiles
