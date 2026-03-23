import uuid
import json

from typing import List, Dict, Any
from sse_starlette.sse import EventSourceResponse
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks


from app.core.security.auth import verify_jwt_token
from app.core.utils.broadcaster import broadcaster
from app.api.dependencies.services import get_poi_ingestion_service
from app.core.services.ingestion import POIIngestionService

# Initialize the router ONLY ONCE
router = APIRouter(prefix="/ingestion", tags=["Data Ingestion"], dependencies=[Depends(verify_jwt_token)])

@router.get("/", status_code=status.HTTP_200_OK)
def health_check():
    return {"status": "online", "message": "POI Ingestion Service is reachable"}

@router.post("/batch", status_code=status.HTTP_202_ACCEPTED)
async def start_ingestion(
    payload: List[Dict[str, Any]], 
    background_tasks: BackgroundTasks,
    service: POIIngestionService = Depends(get_poi_ingestion_service)
):
    # 1. Generate a unique tracking ID
    job_id = str(uuid.uuid4())
    canary_result, remainder = service.process_canary_and_split(payload, limit=10)
    
    # 3. Fast-fail: Expose the actual error details to the client
    if not canary_result.get("is_success"):
        # We are going to dump the ENTIRE canary result straight to the terminal
        # so nothing gets filtered out by mistake.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, 
            detail={
                "status": "failed",
                "message": "Raw Database Exception Dump",
                "RAW_CANARY_RESULT": canary_result 
            }
        )
    # 4. Hand off the heavy items to the background (if any remain)
    if remainder:
        background_tasks.add_task(service.process_background_remainder, remainder, job_id)

    # 5. Return the tracking info
    return {
        "is_success": True, 
        "job_id": job_id, 
        "message": f"Canary passed. {len(remainder)} items are processing in the background.",
        "canary_summary": canary_result["payload"].get("summary", {})
    }

@router.get("/stream/{job_id}")
async def stream_updates(job_id: str):
    """The SSE umbilical cord."""
    async def event_generator():
        queue = broadcaster.get_queue(job_id)
        try:
            while True:
                data = await queue.get()
                # Safely convert the dictionary to a JSON string for the SSE stream
                yield {"event": "message", "data": json.dumps(data)}
                
                if data.get("type") == "complete":
                    break
        finally:
            # Clean up the memory once the stream finishes or the client disconnects!
            broadcaster.remove_queue(job_id)

    return EventSourceResponse(event_generator())