import asyncio
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.core.utils.updater import SpatialUpdater
from app.core.security.auth import verify_jwt_token
from app.api.dependencies.services import get_memgraph_connector

logger = logging.getLogger(__name__)

# Bounded manual rebuild: cap the number of districts one request may rebuild so
# a single call cannot schedule an unbounded blocking job.
MAX_DISTRICTS_PER_REBUILD = 200

router = APIRouter(prefix="/management", tags=["Data Management"],dependencies=[Depends(verify_jwt_token)])


def _default_uow_factory():
    """Build a UnitOfWork lazily so importing this module never opens a DB.

    The concrete UoW / connector are imported inside the factory, keeping module
    import free of ``neo4j`` / settings side effects (mirrors
    ``app.api.dependencies.services``).
    """
    from app.core.infrastructure.db.uow import MemgraphUnitOfWork

    return MemgraphUnitOfWork(get_memgraph_connector())


def _validate_districts(districts: List[str]) -> List[str]:
    """Validate, strip and de-duplicate the requested district ids.

    Raises ``HTTPException(422)`` for a non-list body, a non-string entry, a
    blank entry, an empty effective input, or a request over the bound.
    """
    if not isinstance(districts, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error_type": "invalid_request", "message": "Body must be a list of district ids."},
        )

    cleaned: List[str] = []
    seen = set()
    for raw in districts:
        if not isinstance(raw, str):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"error_type": "invalid_request", "message": "Every district id must be a string."},
            )
        value = raw.strip()
        if not value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"error_type": "invalid_request", "message": "District ids must not be blank."},
            )
        if value in seen:
            continue
        seen.add(value)
        cleaned.append(value)

    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error_type": "invalid_request", "message": "At least one district id is required."},
        )

    if len(cleaned) > MAX_DISTRICTS_PER_REBUILD:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "error_type": "invalid_request",
                "message": f"Too many districts; at most {MAX_DISTRICTS_PER_REBUILD} per request.",
            },
        )
    return cleaned


@router.post("/pois/spatial-rebuild")
async def rebuild_spatial_network(districts: List[str]):
    """Run a bounded, synchronous per-district ``:NEAR_BY`` rebuild.

    The request blocks until the work outcome is known and returns the real
    per-district terminal report (never an unconditional "started" success). The
    blocking work runs off the event loop. Any provider failure is reported as a
    sanitized exception *type* only.
    """
    requested = _validate_districts(districts)
    updater = SpatialUpdater()

    try:
        report = await asyncio.to_thread(
            updater.trigger_update, requested, _default_uow_factory, None
        )
    except Exception as exc:
        # ``trigger_update`` normally returns a report; a truly unexpected
        # failure is surfaced sanitized, never as a success.
        logger.error("Manual spatial rebuild failed unexpectedly (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "failed",
                "error_type": "internal_error",
                "message": "Spatial rebuild failed unexpectedly.",
            },
        )

    report = dict(report or {})
    report["requested"] = len(requested)
    report["deduplicated"] = max(0, len(districts) - len(requested))
    report["failed"] = report.get("failed", {}) or {}
    report["succeeded"] = report.get("succeeded", {}) or {}

    if report.get("is_success"):
        return report

    # Partial (some districts rebuilt) vs total failure are distinct responses,
    # so a caller can never read a blanket success.
    http_status = (
        status.HTTP_207_MULTI_STATUS
        if report["succeeded"]
        else status.HTTP_502_BAD_GATEWAY
    )
    return JSONResponse(status_code=http_status, content=report)
