import json
import logging
import math
import os

from typing import Callable, List, Optional

import httpx
from mcp.server.fastmcp import FastMCP

from app.api.mcp.tool_description import (
    GET_ALL_AVAILABLE_CATEGORIES,
    GET_EXPLORE_DESC,
    GET_ITINERARY_ROUTE_DESC,
    GET_POI_DETAILS_DESC,
)
from travel_shared.exceptions import IntentedNotImplementedException

logger = logging.getLogger(__name__)

MCP_HOST_ENV = "MCP_HOST"
MCP_PORT_ENV = "MCP_PORT"
DEFAULT_MCP_HOST = "0.0.0.0"
DEFAULT_MCP_PORT = 8001


def _listen_port() -> int:
    """Read MCP_PORT at process start; an invalid value fails closed."""
    raw = os.environ.get(MCP_PORT_ENV)
    if raw is None:
        return DEFAULT_MCP_PORT
    try:
        port = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{MCP_PORT_ENV} must be an integer port") from None
    if not 1 <= port <= 65535:
        raise ValueError(f"{MCP_PORT_ENV} must be between 1 and 65535")
    return port


mcp = FastMCP(
    "POI_Admin_Server",
    host=os.environ.get(MCP_HOST_ENV) or DEFAULT_MCP_HOST,
    port=_listen_port(),
)

# ---------------------------------------------------------------------------
# Configuration (environment only; no .env loading, no credentials)
# ---------------------------------------------------------------------------
GRAPHHOPPER_URL_ENV = "GRAPHHOPPER_URL"
GRAPHHOPPER_PROFILES_ENV = "GRAPHHOPPER_PROFILES"
DEFAULT_GRAPHHOPPER_URL = "http://graphhopper:8989/route"
# The deployed GraphHopper config (graphhopper/data/config.yml) enables exactly
# the "car" profile, so that is the only profile accepted unless an operator
# explicitly configures more through GRAPHHOPPER_PROFILES.
DEFAULT_SUPPORTED_PROFILES = ("car",)
# Contraction hierarchies are built per profile. The deployed config builds CH
# only for "car" (`.runtime-native/graphhopper-11.1/config/config.yml`, measured
# 18/10/2026), so every other accepted profile must send ch.disable=true.
GRAPHHOPPER_CH_PROFILES_ENV = "GRAPHHOPPER_CH_PROFILES"
DEFAULT_CH_PROFILES = ("car",)


# ---------------------------------------------------------------------------
# Injectable collaborators
#
# The concrete UnitOfWork / connector / service imports happen *lazily*, inside
# this one factory, so importing this module never opens a database connection
# nor reads real credentials. Tests inject a fake factory instead of patching
# ``sys.modules``.
# ---------------------------------------------------------------------------
_uow_factory: Optional[Callable[[], object]] = None
_http_client_factory: Optional[Callable[[], object]] = None


def set_uow_factory(factory: Optional[Callable[[], object]]) -> None:
    global _uow_factory
    _uow_factory = factory


def reset_uow_factory() -> None:
    set_uow_factory(None)


def set_http_client_factory(factory: Optional[Callable[[], object]]) -> None:
    global _http_client_factory
    _http_client_factory = factory


def reset_http_client_factory() -> None:
    set_http_client_factory(None)


def _default_uow_factory():
    # Imported here so module import stays free of connector/settings effects.
    from app.core.infrastructure.db.database.connector import memgraph_db
    from app.core.infrastructure.db.uow import MemgraphUnitOfWork

    return MemgraphUnitOfWork(memgraph_db)


def _get_uow():
    factory = _uow_factory or _default_uow_factory
    return factory()


def _management_module():
    from app.core.services import management

    return management


def _build_doc_repo():
    from app.core.interfaces.repositories import IDocumentRepository

    class PendingDocumentRepository(IDocumentRepository):
        """Fails open with an explicit "unimplemented" signal.

        The service converts this into ``POIDescription.status == "unavailable"``
        with a null rating, so the Retrieval Agent never crashes and never sees an
        invented rating.
        """

        def get_poi_documents(self, poi_id: str) -> dict:
            raise IntentedNotImplementedException(
                "Document RAG is on the roadmap but not yet implemented."
            )

    return PendingDocumentRepository()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _error(code: str, detail: str, **extra) -> str:
    """Stable, sanitized error envelope (no tracebacks / provider raw messages)."""
    payload = {
        "success": False,
        "code": code,
        "detail": detail,
        "message": detail,
    }
    payload.update(extra)
    return json.dumps(payload, indent=2)


class SourcePayloadSerializationError(Exception):
    """A source-scope payload could not be encoded as JSON.

    Kept distinct from an exploration failure: the query itself succeeded, so
    reporting ``exploration_failed`` would hide a real serialization defect
    behind a generic "Exploration failed." message.
    """


def _dumps_source_payload(envelope: dict) -> str:
    """Encode a source-scope envelope or raise the dedicated error type.

    Logs only the exception class/message; never the payload values.
    """
    try:
        return json.dumps(envelope, indent=2)
    except (TypeError, ValueError) as exc:
        raise SourcePayloadSerializationError(
            "source-scope payload is not JSON serializable"
        ) from exc


def _finite_number(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


# Provider geometry is bounded so a hostile/oversized response cannot bloat the
# tool payload. Values outside these bounds are treated as missing geometry.
MAX_ROUTE_GEOMETRY_POINTS = 20000


def _validated_route_geometry(points):
    """Return ``(geojson_linestring_or_None, status)`` from provider points.

    Only an actual, finite GeoJSON ``LineString`` with at least two
    ``[longitude, latitude]`` positions is accepted. Nothing is interpolated:
    an absent/malformed/oversized geometry is explicitly ``missing``.
    """
    if points is None:
        return None, "missing"
    if not isinstance(points, dict):
        return None, "malformed"
    if points.get("type") != "LineString":
        return None, "malformed"
    coordinates = points.get("coordinates")
    if not isinstance(coordinates, list) or not (
        2 <= len(coordinates) <= MAX_ROUTE_GEOMETRY_POINTS
    ):
        return None, "malformed"
    cleaned = []
    for position in coordinates:
        if not isinstance(position, list) or len(position) != 2:
            return None, "malformed"
        longitude = _finite_number(position[0])
        latitude = _finite_number(position[1])
        if (
            longitude is None
            or latitude is None
            or not (-180.0 <= longitude <= 180.0)
            or not (-90.0 <= latitude <= 90.0)
        ):
            return None, "malformed"
        cleaned.append([longitude, latitude])
    return {"type": "LineString", "coordinates": cleaned}, "available"


def _graphhopper_url() -> str:
    raw = os.getenv(GRAPHHOPPER_URL_ENV)
    if raw is None:
        return DEFAULT_GRAPHHOPPER_URL
    cleaned = raw.strip()
    return cleaned or DEFAULT_GRAPHHOPPER_URL


def _supported_profiles() -> set:
    raw = os.getenv(GRAPHHOPPER_PROFILES_ENV)
    if raw is None or not raw.strip():
        return set(DEFAULT_SUPPORTED_PROFILES)
    return {token.strip() for token in raw.split(",") if token.strip()}


def _ch_enabled_profiles() -> set:
    """Profiles the routing engine built contraction hierarchies for.

    A profile without CH must be requested with ``ch.disable=true``; otherwise
    GraphHopper answers HTTP 400 ("Disable CH using ch.disable=true; available
    CH profiles: [...]"). The default keeps the previously verified car-only
    CH set, so ``car`` keeps its exact current behaviour.
    """
    raw = os.getenv(GRAPHHOPPER_CH_PROFILES_ENV)
    if raw is None or not raw.strip():
        return set(DEFAULT_CH_PROFILES)
    return {token.strip() for token in raw.split(",") if token.strip()}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@mcp.tool(
    name="get_poi_details",
    description=GET_POI_DETAILS_DESC,
)
def get_poi_details(poi_id: str) -> str:
    """
    AI Agent Tool: Provide the exact POI_ID string (e.g., 'cafe_123_hcmc').
    Returns a JSON string containing the POI details, offers, parent
    administrative context and a NEAR_BY array.
    """
    if not isinstance(poi_id, str) or not poi_id.strip():
        return _error("invalid_request", "poi_id must be a nonblank string.",
                      result=None)

    try:
        management = _management_module()
    except Exception:
        logger.error("get_poi_details: POI service dependencies unavailable")
        return _error("internal_error", "POI service is unavailable.",
                      result=None)

    try:
        service = management.POIManagementService(_get_uow())
        doc_repo = _build_doc_repo()
        response_payload = service.get_agentic_poi_details(
            poi_id=poi_id, doc_repo=doc_repo
        )
        return response_payload.model_dump_json(indent=2)
    except management.EntityNotFoundError:
        return _error("not_found", "POI not found.", result=None)
    except IntentedNotImplementedException:
        return _error("not_implemented", "This feature is not implemented yet.",
                      result=None)
    except Exception:
        logger.error("get_poi_details: internal retrieval failure")
        return _error("internal_error", "Internal system error during retrieval.",
                      result=None)


@mcp.tool(
    name="get_itinerary_route",
    description=GET_ITINERARY_ROUTE_DESC,
)
def get_itinerary_route(ordered_poi_ids: List[str], vehicle: str = "car") -> str:
    """
    AI Agent Tool: Pass an array of exact POI_IDs in the order they should be
    visited. The supported profile is configurable through GRAPHHOPPER_PROFILES
    and defaults to 'car'. Profiles the engine did not build a contraction
    hierarchy for (GRAPHHOPPER_CH_PROFILES, default 'car') are requested with
    ch.disable=true; no straight-line fallback is ever substituted.
    """
    if not isinstance(ordered_poi_ids, list) or len(ordered_poi_ids) < 2:
        return _error(
            "invalid_request",
            "An itinerary must have at least 2 stops.",
            error="An itinerary must have at least 2 stops.",
        )

    ordered_ids: List[str] = []
    for raw_id in ordered_poi_ids:
        if not isinstance(raw_id, str) or not raw_id.strip():
            return _error(
                "invalid_request",
                "Every stop must be a nonblank POI id.",
                error="Every stop must be a nonblank POI id.",
            )
        ordered_ids.append(raw_id)

    profile = vehicle.strip() if isinstance(vehicle, str) else ""
    if not profile or profile not in _supported_profiles():
        return _error(
            "invalid_request",
            "Unsupported vehicle profile.",
            error="Unsupported vehicle profile.",
        )

    try:
        management = _management_module()
        uow = _get_uow()
        service = management.POIManagementService(uow)
    except Exception:
        logger.error("get_itinerary_route: POI service dependencies unavailable")
        return _error(
            "internal_error",
            "POI service is unavailable.",
            error="POI service is unavailable.",
        )

    # Resolve every coordinate inside a single, fresh UoW scope. A missing id or
    # coordinate aborts the whole request before any HTTP call is made.
    coordinates: List[tuple] = []
    failing: List[dict] = []
    try:
        with uow:
            for poi_id in ordered_ids:
                poi = service.get_poi(poi_id)
                if poi is None:
                    failing.append({"id": poi_id, "reason": "not_found"})
                    continue
                latitude = _finite_number(getattr(poi, "latitude", None))
                longitude = _finite_number(getattr(poi, "longitude", None))
                if (
                    latitude is None
                    or longitude is None
                    or not (-90.0 <= latitude <= 90.0)
                    or not (-180.0 <= longitude <= 180.0)
                ):
                    failing.append({"id": poi_id, "reason": "missing_coordinates"})
                    continue
                coordinates.append((poi_id, latitude, longitude))
    except Exception:
        logger.error("get_itinerary_route: failed to resolve stops")
        return _error(
            "internal_error",
            "Failed to resolve itinerary stops.",
            error="Failed to resolve itinerary stops.",
        )

    if failing:
        return _error(
            "stops_unresolved",
            "Some stops could not be resolved to coordinates.",
            error="Some stops could not be resolved to coordinates.",
            failing_stops=failing,
        )

    # Repeat "point" as a list of pairs so query encoding is handled correctly.
    # ``points_encoded=false`` returns GeoJSON coordinates from the actual
    # road path instead of an encoded polyline; no geometry is inferred.
    params = [
        ("profile", profile),
        ("locale", "en"),
        ("calc_points", "true"),
        ("instructions", "true"),
        ("points_encoded", "false"),
    ]
    # A profile without a built contraction hierarchy must disable CH explicitly,
    # otherwise GraphHopper rejects the request with HTTP 400. This is a routing
    # mode decision, never a silent fallback: car keeps its exact current params.
    ch_disabled = profile not in _ch_enabled_profiles()
    if ch_disabled:
        params.append(("ch.disable", "true"))
    for _poi_id, latitude, longitude in coordinates:
        params.append(("point", f"{latitude},{longitude}"))

    try:
        factory = _http_client_factory or httpx.Client
        with factory() as client:
            response = client.get(_graphhopper_url(), params=params, timeout=10.0)
            response.raise_for_status()
            route_data = response.json()
    except httpx.HTTPStatusError as exc:
        # Status is diagnostic evidence; the provider's raw message is never
        # echoed into the payload.
        status_code = exc.response.status_code
        logger.error(
            "get_itinerary_route: routing provider returned HTTP %s", status_code
        )
        return _error(
            "route_failed",
            f"Routing provider returned HTTP {status_code}.",
            error=f"Routing provider returned HTTP {status_code}.",
            upstream_status=status_code,
            ch_disabled=ch_disabled,
        )
    except Exception:
        logger.error("get_itinerary_route: routing provider request failed")
        return _error(
            "route_failed",
            "Routing provider request failed.",
            error="Routing provider request failed.",
            ch_disabled=ch_disabled,
        )

    if not isinstance(route_data, dict):
        return _error(
            "route_failed",
            "Routing provider returned a malformed payload.",
            error="Routing provider returned a malformed payload.",
        )

    paths = route_data.get("paths")
    if not isinstance(paths, list) or not paths:
        return _error(
            "no_route",
            "No route could be found between the requested stops.",
            error="No route could be found between the requested stops.",
        )

    best_path = paths[0]
    if not isinstance(best_path, dict):
        return _error(
            "route_failed",
            "Routing provider returned a malformed path.",
            error="Routing provider returned a malformed path.",
        )

    distance_meters = _finite_number(best_path.get("distance"))
    time_ms = _finite_number(best_path.get("time"))
    if (
        distance_meters is None
        or time_ms is None
        or distance_meters < 0
        or time_ms < 0
    ):
        return _error(
            "route_failed",
            "Routing provider returned non-finite distance or time.",
            error="Routing provider returned non-finite distance or time.",
        )

    turn_by_turn: List[str] = []
    for instruction in best_path.get("instructions") or []:
        if isinstance(instruction, dict):
            text = instruction.get("text")
            if isinstance(text, str) and text:
                turn_by_turn.append(text)

    # Only an actual GeoJSON LineString from the provider's best path is
    # accepted. Missing/malformed/NaN/oversized geometry stays explicitly
    # missing: a straight line between stops is never fabricated here.
    route_geometry, geometry_status = _validated_route_geometry(best_path.get("points"))

    result_payload = {
        "success": True,
        # Unrounded so downstream validation can inspect exact values.
        "distance_km": distance_meters / 1000.0,
        "time_minutes": time_ms / 60000.0,
        "turn_by_turn": turn_by_turn,
        "route_geometry": route_geometry,
        "route_geometry_status": geometry_status,
        "route_provenance": "graphhopper",
        "route_profile": profile,
        "stops_mapped": len(coordinates),
        "stops": [
            {"id": poi_id, "latitude": latitude, "longitude": longitude}
            for poi_id, latitude, longitude in coordinates
        ],
    }
    return json.dumps(result_payload, indent=2)


@mcp.tool(
    name="explore_pois",
    description=GET_EXPLORE_DESC,
)
def explore_pois(
    city_id: Optional[str] = None,
    district_id: Optional[str] = None,
    street_id: Optional[str] = None,
    category_id: Optional[str] = None,
    product_keyword: Optional[str] = None,
    limit: int = 15,
    offset: int = 0,
    source_scope: Optional[dict] = None,
    source_snapshot: Optional[dict] = None,
    source_discovery: Optional[str] = None,
) -> str:
    """
    Searches for POIs using exact ids. All supplied ids are applied
    conjunctively; a category id is matched exactly and never replaced by a
    display name.

    Source mode is explicit. ``source_discovery="snapshots"`` lists available
    dataset snapshots; ``source_discovery="source_areas"`` with
    ``source_snapshot={"dataset_namespace","input_sha256"}`` lists qualified
    source areas. ``source_scope={"dataset_namespace","input_sha256",
    "source_area_id"}`` (single) or the alternate
    ``source_scope={"dataset_namespace","input_sha256","source_area_ids":[...]}``
    retrieves only matching source-only records and cannot be combined with
    current city/district/street ids.
    """
    try:
        management = _management_module()
    except Exception:
        logger.error("explore_pois: POI service dependencies unavailable")
        return _error(
            "internal_error", "POI service is unavailable.", count=0, results=[]
        )

    try:
        service = management.POIManagementService(_get_uow())

        if source_discovery is not None:
            if any(
                value is not None
                for value in (
                    city_id,
                    district_id,
                    street_id,
                    category_id,
                    product_keyword,
                    source_scope,
                )
            ):
                return _error(
                    "invalid_request",
                    "source_discovery cannot be combined with search filters or source_scope.",
                    results=[],
                )
            if source_discovery == "snapshots":
                payload = service.list_source_snapshots()
            elif source_discovery == "source_areas":
                if source_snapshot is None:
                    return _error(
                        "invalid_request",
                        "source_snapshot is required for source_areas.",
                        results=[],
                    )
                payload = service.list_source_areas(source_snapshot)
            else:
                return _error(
                    "invalid_request",
                    "source_discovery must be 'snapshots' or 'source_areas'.",
                    results=[],
                )
            return json.dumps(
                {"success": True, "mode": source_discovery, **payload},
                indent=2,
            )

        results = service.explore_compound(
            city_id=city_id,
            district_id=district_id,
            street_id=street_id,
            category_id=category_id,
            product_keyword=product_keyword,
            limit=limit,
            offset=offset,
            source_scope=source_scope,
        )
        if source_scope is not None:
            payload = results if isinstance(results, dict) else {"results": []}
            payload = dict(payload)
            payload.setdefault("results", [])
            return _dumps_source_payload(
                {
                    "success": True,
                    "count": len(payload.get("results") or []),
                    **payload,
                }
            )

        results = results if isinstance(results, list) else []
        return json.dumps(
            {"success": True, "count": len(results), "results": results},
            indent=2,
        )
    except SourcePayloadSerializationError:
        # The query succeeded; only the encoding failed. Never surface this as
        # an exploration failure, and never log payload values.
        logger.error(
            "explore_pois: source-scope payload serialization failure"
        )
        return _error(
            "serialization_failed",
            "Exploration result could not be serialized.",
            count=0,
            results=[],
        )
    except management.InvalidRequestError as exc:
        return _error("invalid_request", str(exc), count=0, results=[])
    except Exception:
        logger.error("explore_pois: exploration failure")
        return _error(
            "exploration_failed",
            "Exploration failed.",
            count=0,
            results=[],
        )


@mcp.tool(
    name="get_available_categories",
    description=GET_ALL_AVAILABLE_CATEGORIES,
)
def get_available_categories() -> str:
    """
    AI Agent Tool: Returns a list of dictionaries containing 'id' and 'name'.
    Always returns a list (possibly empty) with success=true.
    """
    try:
        management = _management_module()
        service = management.POIManagementService(_get_uow())
        categories = service.get_available_categories()
        categories = categories if isinstance(categories, list) else []
        return json.dumps(
            {"success": True, "total": len(categories), "categories": categories},
            indent=2,
        )
    except Exception:
        logger.error("get_available_categories: category fetch failure")
        return _error(
            "category_fetch_failed",
            "Failed to retrieve categories.",
            categories=[],
        )


@mcp.tool(
    name="resolve_geographic_id",
    description=(
        "ALWAYS use this FIRST when a user mentions a city, district, or street to get "
        "the exact database ID. Example: keyword='District 1' or 'Hanoi'. Matches are "
        "candidates only; do not assume a choice when several are returned."
    ),
)
def resolve_geographic_id(keyword: str) -> str:
    if not isinstance(keyword, str) or not keyword.strip():
        return _error(
            "invalid_request",
            "keyword must be a nonblank string.",
            matches=[],
        )
    try:
        management = _management_module()
        service = management.POIManagementService(_get_uow())
        matches = service.search_location_id(keyword)
        matches = matches if isinstance(matches, list) else []
        return json.dumps({"success": True, "matches": matches}, indent=2)
    except Exception:
        logger.error("resolve_geographic_id: location lookup failure")
        return _error(
            "location_lookup_failed",
            "Location lookup failed.",
            matches=[],
        )


if __name__ == "__main__":
    import asyncio

    from app.core.infrastructure.db.database.connector import memgraph_db

    logger.info("Initializing Memgraph connection for MCP Server...")
    asyncio.run(memgraph_db.connect())
    mcp.run(transport="sse")
