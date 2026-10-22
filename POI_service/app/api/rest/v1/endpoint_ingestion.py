import asyncio
import json
import logging
import uuid

from typing import Any, List
from sse_starlette.sse import EventSourceResponse
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status


from app.core.security.auth import verify_jwt_token
from app.core.utils.broadcaster import BroadcasterCapacityError, broadcaster
from app.api.dependencies.services import get_poi_ingestion_service
from app.core.services.ingestion import POIIngestionService

logger = logging.getLogger(__name__)

# Number of leading records written synchronously as a canary.
BATCH_CANARY_LIMIT = 10

# Initialize the router ONLY ONCE
router = APIRouter(prefix="/ingestion", tags=["Data Ingestion"], dependencies=[Depends(verify_jwt_token)])


def _failure_detail(error_type: str, summary: dict) -> dict:
    """Sanitized failure payload: never leaks exception text or tracebacks."""
    return {
        "status": "failed",
        "error_type": error_type,
        "message": "The ingestion canary rejected the batch.",
        "summary": summary,
    }


@router.get("/", status_code=status.HTTP_200_OK)
def health_check():
    return {"status": "online", "message": "POI Ingestion Service is reachable"}

@router.post("/batch", status_code=status.HTTP_202_ACCEPTED)
async def start_ingestion(
    payload: List[Any],
    background_tasks: BackgroundTasks,
    service: POIIngestionService = Depends(get_poi_ingestion_service)
):
    # 1. Generate a unique tracking ID and register it BEFORE the canary runs so
    #    events (and the terminal event) are retained for a late subscriber.
    #    Capacity is enforced here, before any write, rather than evicting jobs.
    job_id = str(uuid.uuid4())
    try:
        broadcaster.register(job_id)
    except BroadcasterCapacityError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "failed",
                "error_type": "broadcaster_capacity",
                "message": "Ingestion is at capacity; please retry shortly.",
                "summary": {},
            },
        )

    # 2. The canary performs blocking, retried database writes; offload it so it
    #    does not block the event loop. Any unexpected error is cleaned up and
    #    reported as a sanitized 503.
    try:
        canary_result, remainder = await asyncio.to_thread(
            service.process_canary_and_split, payload, BATCH_CANARY_LIMIT
        )
    except Exception:
        logger.exception("Unexpected canary failure for job %s", job_id)
        broadcaster.evict(job_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "failed",
                "error_type": "internal_error",
                "message": "The ingestion canary failed unexpectedly.",
                "summary": {},
            },
        )

    # 3. Fast-fail: distinguish invalid records (422) from a database outage (503)
    #    without leaking raw tracebacks.
    if not canary_result.get("is_success"):
        broadcaster.evict(job_id)  # cleanup the failed canary job
        error_type = canary_result.get("error_type")
        http_status = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if error_type in ("database_unavailable", "internal_error")
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(
            status_code=http_status,
            detail=_failure_detail(
                error_type, canary_result.get("payload", {}).get("summary", {})
            ),
        )

    # 4. Hand off the heavy items to the background (if any remain), passing the
    #    canary result and the original offset so the terminal totals cover the
    #    entire submitted batch. If nothing remains, this is a canary-only job:
    #    emit its terminal event now.
    if remainder:
        start_index = len(payload) - len(remainder)
        background_tasks.add_task(
            service.process_background_remainder,
            remainder,
            job_id,
            canary_result,
            start_index,
        )
    else:
        await service.finalize_canary_job(job_id, canary_result)

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
    # Reject unknown/expired jobs with 404 instead of hanging on an empty queue.
    if not broadcaster.is_active(job_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown or expired ingestion job.",
        )

    async def event_generator():
        # Replay the retained history from this subscriber's own cursor, then
        # tail live events. Disconnecting only stops this generator; the job
        # (and its terminal event) remains replayable until its TTL expires.
        async for data in broadcaster.subscribe(job_id):
            yield {"event": "message", "data": json.dumps(data)}

    return EventSourceResponse(event_generator())
