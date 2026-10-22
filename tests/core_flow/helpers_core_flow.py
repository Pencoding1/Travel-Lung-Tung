"""Fakes and fixtures for the CORE-069 flow tests.

Every collaborator (Jev, generation model, MCP session) is replaced through the
existing module seams. No live model, graph, GraphHopper or credential is used.
Evidence produced by this suite is **mocked contract evidence**, not a
scientific experiment.
"""

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = REPO_ROOT / "ai_service"
if str(AI_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_ROOT))

from domains import jev_intent  # noqa: E402

DATASET_NAMESPACE = "hcm_primary_geojson"
INPUT_SHA256 = "a" * 64
AREA_ID = "source_area_v1:" + "b" * 64

SELECTION_A = {
    "dataset_namespace": DATASET_NAMESPACE,
    "input_sha256": INPUT_SHA256,
    "source_area_id": AREA_ID,
}
SELECTION_B = {
    "dataset_namespace": DATASET_NAMESPACE,
    "input_sha256": INPUT_SHA256,
    "source_area_id": "source_area_v1:" + "c" * 64,
}


# ---------------------------------------------------------------------------
# CallToolResult and MCP session stand-ins
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


class _MCPTool:
    def __init__(self, name, schema=None):
        self.name = name
        self.description = name
        self.inputSchema = schema or {"type": "object"}


class _MCPToolList:
    def __init__(self, names):
        self.tools = [_MCPTool(name) for name in names]


class FakeMCPSession:
    def __init__(self, tool_names, handlers=None):
        self.tool_names = list(tool_names)
        self.handlers = handlers or {}
        self.calls = []

    async def initialize(self):
        return None

    async def list_tools(self):
        return _MCPToolList(self.tool_names)

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
# Source-scope evidence fixtures (shape of the real source-mode envelopes)
# ---------------------------------------------------------------------------
def source_context(selection, *, label="Vùng dữ liệu thử",
                   raw_city="Hồ Chí Minh", raw_area="Quận 1"):
    return {
        "dataset_namespace": selection["dataset_namespace"],
        "input_sha256": selection["input_sha256"],
        "source_area_id": selection["source_area_id"],
        "source_area_label": label,
        "raw_city": raw_city,
        "raw_area": raw_area,
        "area_assignment": "qualified",
        "current_admin_status": "unverified_source_area",
        "current_boundary_uncertainty": (
            "Source dataset label; not a present-day administrative boundary."),
        "lineage_reference": "lineage:test",
        "qualification": "exact_source_snapshot_tuple",
    }


def source_explore_record(poi_id, name, selection, *, category="Cafe"):
    return {
        "id": poi_id,
        "POI_Name": name,
        "POI_Category": category,
        "latitude": 10.77,
        "longitude": 106.7,
        "source_context": source_context(selection),
        "administrative_context": None,
        "administrative_context_status": "unverified_source_area",
        "administrative_scope": "source_snapshot_area_only",
    }


def source_detail(poi_id, name, selection, *, nearby=(), category="Cafe",
                  operation_time=None, address="12 Lê Lợi, Quận 1"):
    payload = {
        "POI_ID": poi_id,
        "POI_Name": name,
        "POI_Address": address,
        "POI_Category": category,
        "POI_Categories": [{"id": "cat_coffee", "name": category}],
        "latitude": 10.77,
        "longitude": 106.7,
        "POI_Description": {
            "insight": "",
            "seo_article": "",
            "review": {"rating": 4.2, "review": ""},
        },
        "POI_Contact_Info": {"website": "", "fanpage": "", "phonenumber": ""},
        "Offers": [],
        "NEAR_BY": list(nearby),
        "source_context": source_context(selection),
        "administrative_context": None,
        "administrative_context_status": "unverified_source_area",
        "administrative_scope": "source_snapshot_area_only",
    }
    if operation_time is not None:
        payload["operation_time"] = operation_time
    return payload


# ---------------------------------------------------------------------------
# Scripted model seam (OpenAI-compatible payload -> response)
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
    def __init__(self, responses):
        self.responses = list(responses)
        self.payloads = []

    async def __call__(self, payload):
        self.payloads.append(payload)
        if not self.responses:
            raise AssertionError("no scripted model response left")
        return self.responses.pop(0)

    def messages_at(self, index):
        return list(self.payloads[index].get("messages") or [])


# ---------------------------------------------------------------------------
# Jev fake (intent classification only)
# ---------------------------------------------------------------------------
def _jev_payload(choice="TRAVEL", confidence=0.9):
    rest = round((1.0 - confidence) / 2.0, 4)
    probabilities = {}
    for label in ("CHITCHAT", "TRAVEL", "UNCERTAIN"):
        probabilities[label] = confidence if label == choice else rest
    return {
        "model": "jev-test-1",
        "answers": {
            "intent": {
                "type": "choice",
                "choice": choice,
                "probabilities": probabilities,
                "confidence": confidence,
            }
        },
        "usage": {"input_tokens": 4, "output_tokens": 1},
    }


def install_fake_jev(choice="TRAVEL", *, confidence=0.9, calls=None):
    payload = _jev_payload(choice, confidence)

    def _handler(request):
        if calls is not None:
            calls.append(request.url.path)
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(_handler)
    jev_intent.configure_intent_router(
        {"TYPESAFE_API_KEY": "dummy-test-key", "JEV_MIN_CONFIDENCE": "0.5"},
        transport=transport)
    return payload


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def http_call(method, path, body=None, headers=None):
    import main
    from httpx import ASGITransport, AsyncClient

    async def _run():
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, json=body, headers=headers)

    return asyncio.run(_run())


def chat_body(message="quán cà phê yên tĩnh", *, source=SELECTION_A,
              mode="car", session="sess-1", memory=True):
    body = {
        "session_id": session,
        "message": message,
        "memory_enabled": memory,
        "transport_mode": mode,
    }
    if source is not None:
        body["source_scope"] = dict(source)
    return body


def itinerary_body(*, source=SELECTION_A, mode="car", session="sess-plan"):
    body = {
        "session_id": session,
        "current_city": "Ho Chi Minh City",
        "travel_type": "self-explore, relaxing",
        "num_travelers": 2,
        "start_date": "2026-01-01",
        "target_district": "District 1",
        "duration_days": 1,
        "budget_range": "500000-1500000 VND",
        "user_description": "quán cà phê yên tĩnh",
        "transport_mode": mode,
    }
    if source is not None:
        body["source_scope"] = dict(source)
    return body
