"""Shared fake collaborators and fixtures for the OC-005 grounding tests.

All external collaborators (MCP server session and Gemini HTTP endpoint) are
replaced with in-process fakes through the seams defined in ``ai_service.main``.
The production ``main`` and ``domains.grounding`` modules are imported and
exercised for real. No database, network, graph, credential or live model call
is made anywhere in this package.

Evidence produced by this suite is therefore **mocked contract evidence**, not a
deployed-system or model-quality experiment.
"""

import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = REPO_ROOT / "ai_service"
if str(AI_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_ROOT))


# ---------------------------------------------------------------------------
# Minimal stand-ins for mcp.types.TextContent / CallToolResult
# ---------------------------------------------------------------------------
class _Text:
    def __init__(self, text):
        self.text = text


class ToolResult:
    def __init__(self, text=None, is_error=False, content=None):
        self.isError = is_error
        if content is not None:
            self.content = content
        elif text is None:
            self.content = []
        else:
            self.content = [_Text(text)]


def ok_json(payload):
    return ToolResult(json.dumps(payload))


# ---------------------------------------------------------------------------
# Scripted MCP session
# ---------------------------------------------------------------------------
class ScriptedMCPSession:
    """Calls the handler registered for each tool name; records every call."""

    def __init__(self, handlers):
        self.handlers = handlers
        self.calls = []

    async def initialize(self):
        return None

    async def list_tools(self):
        raise NotImplementedError("list_tools is not used by the itinerary endpoint")

    async def call_tool(self, name, arguments=None):
        self.calls.append({"tool": name, "args": dict(arguments or {})})
        handler = self.handlers.get(name)
        if handler is None:
            raise AssertionError(f"unexpected tool call: {name}")
        return handler(arguments or {})


def session_seam(session):
    @asynccontextmanager
    async def _seam():
        yield session

    return _seam


class FakeLLM:
    def __init__(self, response=None, exc=None):
        self.calls = []
        self.response = response
        self.exc = exc

    async def __call__(self, payload):
        self.calls.append(payload)
        if self.exc is not None:
            raise self.exc
        return self.response


def llm_text(content):
    return {"choices": [{"message": {"content": content}}]}


# ---------------------------------------------------------------------------
# Evidence / plan builders
# ---------------------------------------------------------------------------
DEFAULT_ADMIN_CONTEXT = {
    "city_id": "hcmc",
    "district_id": "quan_1",
    "city_name": "Ho Chi Minh City",
    "district_name": "District 1",
}


def evidence(poi_id, name, address, latitude=10.77, longitude=106.7,
             category="Cafe", rating=0.0, contact=None, offers=None,
             admin="default", rating_sources=None, operation_time=None):
    """Build a ``get_poi_details`` evidence payload.

    ``admin="default"`` supplies a valid structured ``administrative_context``
    matching the default resolved geography; pass ``admin=None`` to omit it or a
    dict to override it.
    """
    if admin == "default":
        admin = dict(DEFAULT_ADMIN_CONTEXT)
    payload = {
        "POI_ID": poi_id,
        "POI_Name": name,
        "POI_Address": address,
        "POI_Category": category,
        "latitude": latitude,
        "longitude": longitude,
        "POI_Description": {
            "insight": "",
            "seo_article": "",
            "review": {"rating": rating, "review": ""},
        },
        "POI_Contact_Info": contact or {"website": "", "fanpage": "", "phonenumber": ""},
        "Offers": offers or [],
        "NEAR_BY": [],
    }
    if admin is not None:
        payload["administrative_context"] = admin
    if rating_sources is not None:
        payload["rating_sources"] = rating_sources
    if operation_time is not None:
        payload["operation_time"] = operation_time
    return payload


def plan(stops, start_poi_id=None, end_poi_id=None, total=None,
         itinerary_id="itin-1", uid="uid-1"):
    stop_payloads = []
    budget_sum = 0.0
    for pid, day, visit, end, budget in stops:
        stop_payloads.append({
            "date": day,
            "visit_time": visit,
            "end_time": end,
            "description": "model free text that must be replaced",
            "budget": budget,
            "poi": {"id": pid},
        })
        try:
            budget_sum += float(budget)
        except (TypeError, ValueError):
            pass
    if start_poi_id is None and stops:
        start_poi_id = stops[0][0]
    if end_poi_id is None and stops:
        end_poi_id = stops[-1][0]
    if total is None:
        total = budget_sum
    return {
        "id": itinerary_id,
        "uid": uid,
        "start_poi_id": start_poi_id,
        "end_poi_id": end_poi_id,
        "total_estimated_budget": total,
        "stops": stop_payloads,
    }


def make_request(**overrides):
    from domains.payloads import ItineraryRequest

    values = {
        "session_id": "sess-1",
        "current_city": "Ho Chi Minh City",
        "travel_type": "self-explore, relaxing",
        "num_travelers": 2,
        "start_date": "2026-01-01",
        "target_district": "District 1",
        "duration_days": 1,
        "budget_range": "500000-1500000 VND",
        "user_description": "quiet cafes",
    }
    values.update(overrides)
    return ItineraryRequest(**values)


# ---------------------------------------------------------------------------
# Fully valid retrieval graph by default
# ---------------------------------------------------------------------------
DISTRICT_MATCH = {"type": "District", "id": "quan_1", "name": "District 1"}
CITY_MATCH = {"type": "City", "id": "hcmc", "name": "Ho Chi Minh City"}


def default_handlers(district_matches=None, city_matches=None, categories=None,
                     candidates=None, enrichments=None):
    district_matches = [DISTRICT_MATCH] if district_matches is None else district_matches
    city_matches = [CITY_MATCH] if city_matches is None else city_matches
    categories = [{"id": "cat_coffee", "name": "Cafe"}] if categories is None else categories
    candidates = ["poi_a"] if candidates is None else candidates
    if enrichments is None:
        enrichments = {
            "poi_a": evidence("poi_a", "Verified Cafe A",
                              "12 Le Loi, Quan 1, Ho Chi Minh City"),
        }

    def resolve(args):
        keyword = args.get("keyword", "")
        if "City" in keyword or "Ho Chi Minh" in keyword:
            return ok_json({"success": True, "matches": city_matches})
        return ok_json({"success": True, "matches": district_matches})

    def get_categories(_args):
        return ok_json({"success": True, "categories": categories})

    def explore(_args):
        return ok_json({"success": True, "count": len(candidates),
                        "results": [{"id": pid} for pid in candidates]})

    def details(args):
        pid = args.get("poi_id")
        item = enrichments.get(pid)
        if item is None:
            return ok_json({"success": False, "result": None, "detail": "not found"})
        return ok_json({"success": True, "result": item})

    def route(args):
        # Route fake for the real ``get_itinerary_route`` tool contract. Returns
        # a modest bidirectional transfer so the scheduler can place candidates;
        # the ordered ids are echoed so exact-id validation is exercised.
        ids = args.get("ordered_poi_ids") or []
        return ok_json({
            "success": True,
            "distance_km": 1.0,
            "time_minutes": 10.0,
            "stops_mapped": len(ids),
            "stops": [{"id": pid, "latitude": 10.77, "longitude": 106.7}
                      for pid in ids],
            "turn_by_turn": [],
        })

    return {
        "resolve_geographic_id": resolve,
        "get_available_categories": get_categories,
        "explore_pois": explore,
        "get_poi_details": details,
        "get_itinerary_route": route,
    }
