"""Harness for the Agent Chat MVP behaviour tests.

Everything here exists to make the **contract observable**, not to accommodate
the current code. Three collaborators are faked, because they are outside the
feature under test:

* intent classification (an external TypeSafe service),
* the generation model,
* the POI knowledge base (reached only through MCP tools).

The HTTP surface, the chat pipeline, claim extraction, intent resolution,
grounding and hand-off are **real** and must satisfy the tests.

Mock DB fixtures come from the real prepared dataset
(``data/primary_20261016/graph_ready_v2/prepared_pois.jsonl``) so the payload
shape matches what ``POIResult``/``POICompoundLite`` actually emit
(``POI_service/app/core/domain/get_payload.py``). Ids are the dataset's own.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Dataset-backed fixtures (real ids, real field values)
# ---------------------------------------------------------------------------
POI_CAFE_BETTA = "hcm_primary_geojson_internal:033dd327cc9b86b52c8768151afad7f2"
POI_GALLERY_ANH_TUONG = "hcm_primary_geojson_internal:0712657078c2c38d3ab0bf28f20b7a71"
POI_QUAN1_RESTAURANT = "hcm_primary_geojson_internal:01e6dfca9253934966b67649060106c2"

_F4_IDS = [
    POI_CAFE_BETTA,
    POI_GALLERY_ANH_TUONG,
    POI_QUAN1_RESTAURANT,
]


def _description(insight="", rating=None, review=""):
    return {
        "insight": insight,
        "seo_article": "",
        "review": {"rating": rating, "review": review},
        "status": "available" if insight else "unavailable",
    }


def _contact():
    return {"website": "", "fanpage": "", "phonenumber": ""}


def poi_result_known_hours(poi_id=POI_CAFE_BETTA):
    """A record that exists **and** carries opening hours."""
    return {
        "success": True,
        "result": {
            "POI_ID": poi_id,
            "POI_Name": "ca phe betta fish",
            "POI_Address": "152 Võ Văn Kiệt, Quan 1, HCMC",
            "POI_Category": "Coffee",
            "POI_Categories": [{
                "id": "hcm_primary_geojson:source-category:coffee",
                "name": "Coffee",
                "context": "Coffee shops labelled by the primary source.",
            }],
            "latitude": 10.7651367,
            "longitude": 106.6993512,
            "operation_time": "06:00-22:00",
            "POI_Description": _description(),
            "POI_Contact_Info": _contact(),
            "Offers": [],
            "NEAR_BY": [],
            "administrative_context": {
                "city_id": "hcmc",
                "district_id": "quan-1",
                "city_name": "HCMC",
                "district_name": "Quan 1",
            },
            "administrative_context_status": "resolved",
            "missing_data": [],
        },
    }


def poi_result_missing_hours(poi_id=POI_GALLERY_ANH_TUONG):
    """A record that exists but has **no** hours/rating/menu in the dataset."""
    return {
        "success": True,
        "result": {
            "POI_ID": poi_id,
            "POI_Name": "anh tuong my thuat",
            "POI_Address": "Tan Phu, HCMC",
            "POI_Category": "Attractions",
            "POI_Categories": [{
                "id": "hcm_primary_geojson:source-category:attractions",
                "name": "Attractions",
                "context": "Visitor attractions as labelled by the primary source.",
            }],
            "latitude": 10.7840624,
            "longitude": 106.620094,
            "operation_time": None,
            "POI_Description": _description(),
            "POI_Contact_Info": _contact(),
            "Offers": [],
            "NEAR_BY": [],
            "administrative_context": {
                "city_id": "hcmc",
                "district_id": "tan-phu",
                "city_name": "HCMC",
                "district_name": "Tan Phu",
            },
            "administrative_context_status": "resolved",
            "missing_data": ["operation_time", "rating"],
        },
    }


def poi_compound(poi_id, name, operation_time=None):
    return {
        "id": poi_id,
        "name": name,
        "full_address": None,
        "operation_time": operation_time,
        "categories": [],
        "offers": [],
        "administrative_context": None,
        "administrative_context_status": "missing",
    }


def explore_results(*items):
    return {"success": True, "count": len(items), "results": list(items)}


def explore_empty():
    """Absence is expressed the way the real service expresses it: an empty,
    successful result — not a tool error."""
    return {"success": True, "count": 0, "results": []}


def not_found_envelope(message="POI not found."):
    return {"success": False, "code": "not_found", "detail": message,
            "message": message, "result": None}


# ---------------------------------------------------------------------------
# MCP session fake
# ---------------------------------------------------------------------------
class _Text:
    def __init__(self, text):
        self.text = text


class ToolResult:
    def __init__(self, text=None, is_error=False):
        self.isError = is_error
        self.content = [] if text is None else [_Text(text)]


def ok_json(payload):
    return ToolResult(json.dumps(payload, ensure_ascii=False))


def err_json(payload):
    return ToolResult(json.dumps(payload, ensure_ascii=False), is_error=True)


class _ToolSpec:
    def __init__(self, name):
        self.name = name
        self.description = "test tool"
        self.inputSchema = {"type": "object"}


class _ToolList:
    def __init__(self, names):
        self.tools = [_ToolSpec(n) for n in names]


class FakeMCPSession:
    """Minimal MCP session. ``handlers`` maps tool name -> callable(args)."""

    def __init__(self, handlers):
        self.handlers = dict(handlers)
        self.calls = []

    async def initialize(self):
        return None

    async def list_tools(self):
        return _ToolList(list(self.handlers))

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
# Model fake
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
    args = args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": args}}


def scripted_model(*contents):
    """Queue of plain assistant messages; records every payload sent."""

    queue = [c if isinstance(c, dict) else model_message(content=c)
             for c in contents]
    state = {"payloads": []}

    async def _call(payload):
        state["payloads"].append(payload)
        if not queue:
            # The feature asked for more model turns than the scenario planned.
            return model_message(content="")
        return queue.pop(0)

    _call.state = state
    return _call


# ---------------------------------------------------------------------------
# Intent classifier fake (external TypeSafe service)
# ---------------------------------------------------------------------------
def fake_router(intent="CHITCHAT", status="ok", confidence=0.9):
    async def _route(user_message, usage=None):
        return {
            "status": status,
            "intent": intent if status == "ok" else None,
            "confidence": confidence,
            "requested_model": "jev-test-1",
            "observed_model": "jev-test-1",
            "attempts": [{"attempt": 0, "outcome": "success", "usage_known": True,
                          "usage": {"input_tokens": 4, "output_tokens": 1},
                          "requested_model": "jev-test-1",
                          "observed_model": "jev-test-1"}],
            "fallback": False,
            "provenance": {"provider": "typesafe", "operation": "intent_routing"},
        }

    return _route


# ---------------------------------------------------------------------------
# Request plumbing
# ---------------------------------------------------------------------------
def post_chat(body, headers=None):
    import main

    async def _run():
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request("POST", "/chat", json=body, headers=headers)

    return asyncio.run(_run())


def chat(monkeypatch, message, *, intent="CHITCHAT", tools=None, handlers=None,
         model_contents=("",), session_id=None, memory_enabled=False):
    """Wire the three collaborating fakes and send one chat turn."""
    import main

    handlers = handlers or {}
    session = FakeMCPSession(handlers) if tools is None else FakeMCPSession(handlers)
    monkeypatch.setattr(main, "open_mcp_session", mcp_seam(session))
    monkeypatch.setattr(main, "route_intent", fake_router(intent))
    llm = scripted_model(*model_contents)
    monkeypatch.setattr(main, "gemini_chat_completion", llm)
    response = post_chat({
        "session_id": session_id or f"s-{uuid.uuid4().hex[:8]}",
        "message": message,
        "memory_enabled": memory_enabled,
    })
    return response, session, llm


# ---------------------------------------------------------------------------
# Dates: no clock seam by decision (2026-10-22). Tests derive the expected
# value from the system clock with the same documented rule, so they stay
# correct on any run date.
# ---------------------------------------------------------------------------
def upcoming_saturday(today=None):
    """The rule the contract relies on: 'cuối tuần này' = next Saturday
    (today when today is Saturday)."""
    from datetime import date, timedelta

    today = today or date.today()
    # weekday(): Monday=0 .. Sunday=6
    delta = (5 - today.weekday()) % 7
    return today + timedelta(days=delta)


def iso_day(value):
    return value.isoformat()


# ---------------------------------------------------------------------------
# B6 rule (§2.2): two options are meaningfully different when at least two of
# {area, pace, budget, experience} differ and the POI sets are not identical.
# ---------------------------------------------------------------------------
def option_dimensions_differing(a, b):
    differing = 0
    for key in ("area_ids", "pace", "budget", "experience_types"):
        left, right = a.get(key), b.get(key)
        if isinstance(left, list) and isinstance(right, list):
            if set(left) != set(right):
                differing += 1
        elif left != right:
            differing += 1
    return differing


def assert_options_meaningful(options):
    assert isinstance(options, list) and len(options) >= 3, (
        f"contract B6: at least three options are required, got {options!r}"
    )
    for index, option in enumerate(options):
        missing = [k for k in ("poi_ids", "area_ids", "pace", "budget",
                               "experience_types") if k not in option]
        assert not missing, (
            f"contract B6: option {index} cannot be measured, missing {missing}"
        )
    for i in range(len(options)):
        for j in range(i + 1, len(options)):
            a, b = options[i], options[j]
            assert a.get("poi_ids") != b.get("poi_ids"), (
                f"options {i} and {j} are the same itinerary"
            )
            assert option_dimensions_differing(a, b) >= 2, (
                f"options {i} and {j} differ in fewer than two dimensions: "
                f"{a!r} vs {b!r}"
            )



# ---------------------------------------------------------------------------
# Contract assertions (fail with the clause name, never with a bare KeyError)
# ---------------------------------------------------------------------------
def field(body, name, clause):
    assert name in body, (
        f"contract {clause}: response has no '{name}' field; "
        f"present keys: {sorted(body)}"
    )
    return body[name]


def assert_no_availability_claim(reply):
    lowered = (reply or "").lower()
    for phrase in ("còn bàn", "hết bàn", "còn chỗ", "hết chỗ"):
        assert phrase not in lowered, (
            "the system claimed live table availability, but no availability "
            f"source exists (phrase: {phrase!r})"
        )


def assert_turn_accepted(body, clause):
    """A contract clause must be reachable: the turn must not be rejected."""
    assert body.get("error") is None, (
        f"contract {clause}: the turn was rejected before the behaviour could "
        f"happen — status={body.get('status')!r}, error={body.get('error')!r}"
    )


def actions_of(body, clause):
    """The action log is part of the contract surface; absence is a failure."""
    return field(body, "actions", clause)


