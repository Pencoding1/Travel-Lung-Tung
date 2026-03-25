import traceback
import json
import logging
import requests

from typing import List
from mcp.server.fastmcp import FastMCP

# Database & UoW Imports
from app.core.infrastructure.db.uow import MemgraphUnitOfWork
from app.api.mcp.tool_description import GET_ITINERARY_ROUTE_DESC, GET_POI_DETAILS_DESC  
from app.core.infrastructure.db.database.connector import memgraph_db

# Service Imports
from app.core.services.management import POIManagementService

# RAG Imports & Exceptions
from app.core.interfaces.repositories import IDocumentRepository
from app.api.dependencies.services import get_document_repository, get_poi_management_service

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


# @mcp.tool(
#     name="ingest_local_ota_file",
#     description="Reads a local JSON file containing a massive array of raw POI data and ingests it into the Memgraph database using chunked ACID transactions."
# )
# def ingest_local_ota_file(file_path: str):...
    

@mcp.tool(
    name="get_poi_details",
    description=GET_POI_DETAILS_DESC)
def get_poi_details(poi_id: str) -> str:
    """
    AI Agent Tool: Provide the exact POI_ID string (e.g., 'cafe_123_hcmc').
    Returns a JSON string containing the POI details and a NEAR_BY array.
    """
    try:
        # 1. Wire Dependencies
        uow = MemgraphUnitOfWork(memgraph_db)
        poi_service = POIManagementService(uow)
        doc_repo = PendingDocumentRepository()

        # 2. Execute Orchestrator
        response_payload = poi_service.get_agentic_poi_details(poi_id=poi_id, doc_repo=doc_repo)
        
        # 3. Serialize for the LLM Context Window
        return response_payload.model_dump_json(indent=2)

    except ValueError as e:
        # Handles the 404 case where Memgraph returns nothing
        error_payload = {
            "success": False,
            "result": None,
            "detail": str(e)
        }
        return json.dumps(error_payload, indent=2)
        
    except IntentedNotImplementedException as e:
        reject_payload = {
            "success": False,
            "result": None,
            "detail": f"This feature is not implemented yet."
        }
        return json.dumps(
            reject_payload,
            indent=2
        )
    
    except Exception as e:
        # Handles critical backend failures (e.g., DB offline)
        error_payload = {
            "success": False,
            "result": None,
            "detail": f"Internal system error during retrieval: {str(e)}"
        }
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
        return json.dumps({
            "success": False,
            "error": "An itinerary must have at least 2 stops."
        })

    # 1. Wire Dependencies Manually (Fixes the RuntimeError!)
    uow = MemgraphUnitOfWork(memgraph_db)
    poi_service = POIManagementService(uow)

    waypoints = []
    
    # 2. Extract Coordinates safely
    for poi in ordered_poi_ids:
        with uow:
        # We use the wired poi_service, NOT the FastAPI dependency injection
            poi_data = poi_service.get_poi(poi) 
            if poi_data and poi_data.latitude and poi_data.longitude:
                waypoints.append((poi_data.latitude, poi_data.longitude))
            else:
                logger.warning(f"Could not find coordinates for POI {poi}") # NO BACKSLASH HERE!
            
    if len(waypoints) < 2:
        return json.dumps({"success": False, "error": "Not enough valid coordinates to calculate a route."})
    
    # 3. Build GraphHopper Request
    params = {
        "profile": vehicle,
        "locale": "en",
        "calc_points": "true", 
        "instructions": "true" 
    }

    query_string = "&".join([f"point={lat},{lon}" for lat, lon in waypoints])
    full_url = f"{GRAPHHOPPER_URL}?{query_string}"

    try:
        response = requests.get(full_url, params=params)
        response.raise_for_status()
        route_data = response.json()

        best_path = route_data["paths"][0]
        
        # 4. Return formatted JSON string to the LLM
        result_payload = {
            "success": True,
            "total_distance_km": round(best_path["distance"] / 1000, 2),
            "total_time_minutes": round(best_path["time"] / (1000 * 60)),
            "turn_by_turn": [instruction["text"] for instruction in best_path["instructions"]],
            # Optionally remove encoded_polyline if you hit token limits!
            "encoded_polyline": best_path["points"], 
            "stops_mapped": len(waypoints)
        }
        return json.dumps(result_payload, indent=2)

    except Exception as e:
        # Grabs the exact line number and file where it crashed!
        error_traceback = traceback.format_exc()
        
        logger.error(f"Critical Tool Failure:\n{error_traceback}")
        
        error_payload = {
            "success": False,
            "error_message": str(e),
            "traceback": error_traceback
        }
        return json.dumps(error_payload, indent=2)
        

if __name__ == "__main__":
    import asyncio
    
    
    logger.info("Initializing Memgraph connection for MCP Server...")
    asyncio.run(memgraph_db.connect())
    mcp.run(transport="sse")