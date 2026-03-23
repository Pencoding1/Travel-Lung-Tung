import json
import os
from mcp.server.fastmcp import FastMCP

# Database & UoW Imports
from app.core.infrastructure.db.database.connector import memgraph_db
from app.core.infrastructure.db.uow import MemgraphUnitOfWork

# Service Imports
from app.core.services.ingestion import POIIngestionService
from app.core.services.management import POIManagementService

# RAG Imports & Exceptions
from app.core.interfaces.repositories import IDocumentRepository
from app.api.dependencies.services import get_document_repository

from travel_shared.exceptions import IntentedNotImplementedException


mcp = FastMCP("POI_Admin_Server", host="0.0.0.0", port=8001)

class PendingDocumentRepository(IDocumentRepository):
    """
    A temporary mock repository that intentionally fails open.
    This prevents the Retrieval Agent from crashing while the Vector DB is unbuilt.
    """
    def get_poi_documents(self, poi_id: str) -> dict:
        raise IntentedNotImplementedException("Document RAG is on the roadmap but not yet implemented.")


@mcp.tool(
    name="ingest_local_ota_file",
    description="Reads a local JSON file containing a massive array of raw POI data and ingests it into the Memgraph database using chunked ACID transactions."
)

def ingest_local_ota_file(file_path: str) -> str:
    """
    AI Agent Tool: Provide the absolute path to a JSON file (e.g., '/data/raw_cafes.json').
    """
    if not os.path.exists(file_path):
        return f"Error: Could not find file at {file_path}"

    try:
        # 1. Load the massive JSON file from disk (bypassing the LLM context limit)
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            
        if not isinstance(raw_data, list):
            return "Error: The JSON file must contain a top-level array of POI objects."

        # 2. Manually wire the dependencies for the MCP tool
        uow = MemgraphUnitOfWork(memgraph_db)
        service = POIIngestionService(uow)
        
        # 3. Execute the pipeline
        results = service.process_ota_batch(raw_data)
        
        # 4. Return the summary to the AI Agent
        return (
            f"Ingestion Complete. "
            f"Successfully inserted: {results['inserted']} records. "
            f"Failed validations: {results['failed']}. "
            f"Check system logs for validation details."
        )

    except json.JSONDecodeError:
        return f"Error: The file at {file_path} is not valid JSON."
    except Exception as e:
        return f"A critical error occurred during ingestion: {str(e)}"
    

@mcp.tool(
    name="get_poi_details",
    description="Fetches comprehensive structured data, contact info, and geographically nearby locations for a specific Point of Interest (POI) ID."
)
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
        # The service internally handles the IntentedNotImplementedException
        # and returns a Pydantic POIGetResponse object.
        response_payload = poi_service.get_agentic_poi_details(poi_id=poi_id, doc_repo=doc_repo)
        
        # 3. Serialize for the LLM Context Window
        # The agent needs a raw string to parse, not a Python object
        return response_payload.model_dump_json(indent=2)

    except ValueError as e:
        # Handles the 404 case where Memgraph returns nothing
        error_payload = {
            "success": False,
            "result": None,
            "detail": str(e)
        }
        return json.dumps(error_payload, indent=2)
        
    except Exception as e:
        # Handles critical backend failures (e.g., DB offline)
        error_payload = {
            "success": False,
            "result": None,
            "detail": f"Internal system error during retrieval: {str(e)}"
        }
        return json.dumps(error_payload, indent=2)


if __name__ == "__main__":
    mcp.run(transport="sse")