import traceback
import json
import logging
import httpx

from typing import List, Optional
from mcp.server.fastmcp import FastMCP

# Database & UoW Imports
from app.core.infrastructure.db.uow import MemgraphUnitOfWork
from app.api.mcp.tool_description import (GET_ITINERARY_ROUTE_DESC, 
                                          GET_POI_DETAILS_DESC,
                                          GET_EXPLORE_DESC,
                                          GET_ALL_AVAILABLE_CATEGORIES)

from app.core.infrastructure.db.database.connector import memgraph_db

# Service Imports
from app.core.services.management import POIManagementService

# RAG Imports & Exceptions
from app.core.interfaces.repositories import IDocumentRepository
from travel_shared.exceptions import IntentedNotImplementedException

logger = logging.getLogger(__file__)
mcp = FastMCP("POI_Admin_Server", host="0.0.0.0", port=8001)

class PendingDocumentRepository(IDocumentRepository):
    """
    A temporary mock repository that intentionally fails open.
    This prevents the Retrieval Agent from crashing while the Vector DB is unbuilt.
    """
    def get_poi_documents(self, poi_id: str) -> dict:
        raise IntentedNotImplementedException("Document RAG is on the roadmap but not yet implemented.")


@mcp.tool(
    name="get_poi_details",
    description=GET_POI_DETAILS_DESC)
def get_poi_details(poi_id: str) -> str:
    """
    AI Agent Tool: Provide the exact POI_ID string (e.g., 'cafe_123_hcmc').
    Returns a JSON string containing the POI details, offers, and a NEAR_BY array.
    """
    try:
        uow = MemgraphUnitOfWork(memgraph_db)
        poi_service = POIManagementService(uow)
        doc_repo = PendingDocumentRepository()

        response_payload = poi_service.get_agentic_poi_details(poi_id=poi_id, doc_repo=doc_repo)
        
        return response_payload.model_dump_json(indent=2)

    except ValueError as e:
        error_payload = {"success": False, "result": None, "detail": str(e)}
        return json.dumps(error_payload, indent=2)
        
    except IntentedNotImplementedException as e:
        reject_payload = {"success": False, "result": None, "detail": "This feature is not implemented yet."}
        return json.dumps(reject_payload, indent=2)
    
    except Exception as e:
        error_payload = {"success": False, "result": None, "detail": f"Internal system error during retrieval: {str(e)}"}
        return json.dumps(error_payload, indent=2)


@mcp.tool(
    name="get_itinerary_route",
    description=GET_ITINERARY_ROUTE_DESC
)
def get_itinerary_route(ordered_poi_ids: List[str], vehicle: str="car") -> str:
    """
    AI Agent Tool: Pass an array of exact POI_IDs in the order they should be visited.
    Valid vehicles: 'car', 'foot', 'bike'.
    """
    GRAPHHOPPER_URL = "http://graphhopper:8989/route"
    
    if len(ordered_poi_ids) < 2:
        return json.dumps({"success": False, "error": "An itinerary must have at least 2 stops."})

    uow = MemgraphUnitOfWork(memgraph_db)
    poi_service = POIManagementService(uow)

    waypoints = []
    
    for poi in ordered_poi_ids:
        with uow:
            poi_data = poi_service.get_poi(poi) 
            if poi_data and poi_data.latitude and poi_data.longitude:
                waypoints.append((poi_data.latitude, poi_data.longitude))
            else:
                logger.warning(f"Could not find coordinates for POI {poi}")
            
    if len(waypoints) < 2:
        return json.dumps({"success": False, "error": "Not enough valid coordinates to calculate a route."})
    
    params = {
        "profile": vehicle,
        "locale": "en",
        "calc_points": "true", 
        "instructions": "true" 
    }

    query_string = "&".join([f"point={lat},{lon}" for lat, lon in waypoints])
    full_url = f"{GRAPHHOPPER_URL}?{query_string}"

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(full_url, params=params)
            response.raise_for_status()
            route_data = response.json()

        best_path = route_data["paths"][0]
        
        result_payload = {
            "success": True,
            "total_distance_km": round(best_path["distance"] / 1000, 2),
            "total_time_minutes": round(best_path["time"] / (1000 * 60)),
            "turn_by_turn": [instruction["text"] for instruction in best_path["instructions"]],
            "stops_mapped": len(waypoints)
        }
        return json.dumps(result_payload, indent=2)

    except Exception as e:
        error_traceback = traceback.format_exc()
        logger.error(f"Critical Tool Failure:\n{error_traceback}")
        
        error_payload = {"success": False, "error_message": str(e), "traceback": error_traceback}
        return json.dumps(error_payload, indent=2)
        

@mcp.tool(
    name="explore_pois",
    description="Searches for POIs. You MUST use exact _id parameters (city_id, district_id, street_id, category_id) obtained from the discovery tools. DO NOT pass normal text names here."
)
def explore_pois(
    city_id: Optional[str] = None, 
    district_id: Optional[str] = None,
    street_id: Optional[str] = None,
    category_id: Optional[str] = None,
    product_keyword: Optional[str] = None,
    limit: int = 15
) -> str:
    try:
        uow = MemgraphUnitOfWork(memgraph_db)
        poi_service = POIManagementService(uow)

        raw_results = []
        FETCH_LIMIT = 200 

        # 1. PRIORITY ROUTING: Geography First!
        # Shrink the search radius before looking for specific products
        if street_id:
            raw_results = poi_service.explore_by_street_id(street_id=street_id, limit=FETCH_LIMIT)
        elif district_id:
            raw_results = poi_service.explore_by_district_id(district_id=district_id, limit=FETCH_LIMIT)
        elif city_id:
            raw_results = poi_service.explore_by_city_id(city_id=city_id, limit=FETCH_LIMIT)
        elif category_id:
            raw_results = poi_service.explore_by_category(category_id=category_id, limit=FETCH_LIMIT)
        elif product_keyword:
            raw_results = poi_service.explore_by_product(product_keyword=product_keyword, limit=FETCH_LIMIT)
        else:
            return json.dumps({"success": False, "message": "You must provide at least one valid parameter."})

        # 2. In-Memory Compound Filtering
        filtered_results = []
        for poi in raw_results:
            is_match = True
            
            # Safely extract fields
            address_str = str(poi.get("address", poi.get("full_address", ""))).lower()
            poi_name = str(poi.get("name", "")).lower()
            categories = [str(c).lower() for c in poi.get("categories", [])]
            offers = [str(o).lower() for o in poi.get("offers", poi.get("products", []))]

            # --------------------------------------------------
            # GARBAGE COLLECTOR: Silently drop corrupted OTA data
            # --------------------------------------------------
            if "unknown unknown" in address_str or poi_name == "unknown":
                continue # Skip this loop iteration entirely

            # --------------------------------------------------
            # CATEGORY FILTER
            # --------------------------------------------------
            if category_id and is_match:
                # Clean 'cat_coffee' to 'coffee' to match the string array returned by POILite
                clean_cat = category_id.lower().replace("cat_", "").replace("_", " ")
                if not any(clean_cat in cat for cat in categories):
                    is_match = False
                
            # --------------------------------------------------
            # PRODUCT FILTER
            # --------------------------------------------------
            if product_keyword and is_match:
                if not any(product_keyword.lower() in off for off in offers):
                    is_match = False

            if is_match:
                filtered_results.append(poi)
                
            if len(filtered_results) >= limit:
                break

        return json.dumps({
            "success": True, 
            "count": len(filtered_results), 
            "results": filtered_results
        }, indent=2)

    except Exception as e:
        import logging
        logger = logging.getLogger("Travel_Lung_Tung_Agent")
        logger.error(f"Exploration Tool Failure: {str(e)}")
        return json.dumps({"success": False, "detail": str(e)})


@mcp.tool(
    name="get_available_categories",
    description=GET_ALL_AVAILABLE_CATEGORIES
)
def get_available_categories() -> str:
    """
    AI Agent Tool: Returns a list of dictionaries containing 'id' and 'name'.
    """
    try:
        uow = MemgraphUnitOfWork(memgraph_db)
        poi_service = POIManagementService(uow)
        
        categories = poi_service.get_available_categories()
        
        if not categories:
             return json.dumps({"success": True, "message": "No categories currently exist in the database."})
             
        return json.dumps({
            "success": True,
            "total": len(categories),
            "categories": categories
        }, indent=2)
        
    except Exception as e:
        logger.error(f"Category Fetch Failure: {str(e)}")
        return json.dumps({
            "success": False,
            "detail": f"Failed to retrieve categories: {str(e)}"
        })


@mcp.tool(
    name="resolve_geographic_id",
    description="ALWAYS use this FIRST when a user mentions a city, district, or street to get the exact database ID. Example: keyword='District 1' or 'Hanoi'."
)
def resolve_geographic_id(keyword: str) -> str:
    try:
        uow = MemgraphUnitOfWork(memgraph_db)
        poi_service = POIManagementService(uow)
        matches = poi_service.search_location_id(keyword)
        
        if not matches:
             return json.dumps({"success": True, "message": f"No official IDs found for '{keyword}'."})
             
        return json.dumps({"success": True, "matches": matches}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "detail": str(e)})

if __name__ == "__main__":
    import asyncio
    
    logger.info("Initializing Memgraph connection for MCP Server...")
    asyncio.run(memgraph_db.connect())
    mcp.run(transport="sse")