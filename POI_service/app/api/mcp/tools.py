import json
import os
from mcp.server.fastmcp import FastMCP

from app.core.infrastructure.db.database.connector import memgraph_db
from app.core.infrastructure.db.uow import MemgraphUnitOfWork
from app.core.services.ingestion import POIIngestionService
mcp = FastMCP("POI_Admin_Server", host="0.0.0.0", port=8001)

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
    

if __name__ == "__main__":
    mcp.run(transport="sse")