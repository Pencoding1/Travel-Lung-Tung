"""Authenticated itinerary-draft REST endpoints (OC-027).

Four operations over the caller's *own* drafts:

* ``POST   /api/v1/itineraries``       create (server id + creation time)
* ``GET    /api/v1/itineraries``       bounded, owner-scoped list
* ``GET    /api/v1/itineraries/{id}``  owner-scoped retrieve
* ``DELETE /api/v1/itineraries/{id}``  owner-scoped delete

The owner is always the verified JWT subject; the storage layer filters by owner,
so a request for another subject's id is indistinguishable from a missing record
(404). The client payload is validated for structural/resource bounds only and is
stored verbatim — it is never executed and never re-verified (see ADR 014).
"""

from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.core.domain.itinerary_draft import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    MAX_PAGE_OFFSET,
    DraftCreateRequest,
    DraftDetail,
    DraftListResponse,
    DraftSummary,
    PayloadError,
    payload_summary,
    validate_draft_payload,
)
from app.core.repositories.itinerary_draft import (
    DuplicateDraftId,
    ItineraryDraftRecord,
    ItineraryDraftRepository,
    RepositoryClosed,
    RepositoryError,
    RepositoryUnavailable,
)
from app.core.security.auth import AuthError, verify_bearer

router = APIRouter(prefix="/itineraries", tags=["itineraries"])

_DRAFT_ID_RE = re.compile(r"^draft_[0-9a-f]{32}$")


def get_repository(request: Request) -> ItineraryDraftRepository:
    """FastAPI dependency returning the app's injected repository."""
    return request.app.state.repository


def require_subject(authorization: Optional[str] = Header(default=None)) -> str:
    """Authenticate the request, returning the verified JWT subject as owner."""
    try:
        return verify_bearer(authorization)
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


def _storage_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": "storage_unavailable",
                "message": "No itinerary-draft storage is configured."},
    )


def _to_summary(record: ItineraryDraftRecord) -> DraftSummary:
    return DraftSummary(
        id=record.id, start_poi_id=record.start_poi_id,
        end_poi_id=record.end_poi_id, stop_count=record.stop_count,
        created_at=record.created_at)


def _to_detail(record: ItineraryDraftRecord) -> DraftDetail:
    return DraftDetail(
        id=record.id, start_poi_id=record.start_poi_id,
        end_poi_id=record.end_poi_id, stop_count=record.stop_count,
        created_at=record.created_at, payload=record.payload)


def _valid_draft_id(draft_id: str) -> bool:
    return bool(_DRAFT_ID_RE.match(draft_id))


@router.post("", response_model=DraftDetail, status_code=status.HTTP_201_CREATED)
def create_draft(body: DraftCreateRequest,
                 owner: str = Depends(require_subject),
                 repository: ItineraryDraftRepository = Depends(get_repository),
                 ) -> DraftDetail:
    if not repository.available:
        raise _storage_unavailable()
    try:
        payload = validate_draft_payload(body.payload)
    except PayloadError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": exc.message}) from None
    summary = payload_summary(payload)
    try:
        record = repository.create(
            owner, payload,
            start_poi_id=summary["start_poi_id"],
            end_poi_id=summary["end_poi_id"],
            stop_count=summary["stop_count"])
    except RepositoryUnavailable:
        raise _storage_unavailable() from None
    except DuplicateDraftId:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "duplicate_draft_id",
                    "message": "A draft with the generated id already exists."},
        ) from None
    except (RepositoryClosed, RepositoryError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "storage_error",
                    "message": "The itinerary-draft store is unavailable."},
        ) from None
    return _to_detail(record)


@router.get("", response_model=DraftListResponse)
def list_drafts(owner: str = Depends(require_subject),
                repository: ItineraryDraftRepository = Depends(get_repository),
                limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
                offset: int = Query(0, ge=0, le=MAX_PAGE_OFFSET),
                ) -> DraftListResponse:
    try:
        records, total = repository.list(owner, limit=limit, offset=offset)
    except (RepositoryClosed, RepositoryError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "storage_error",
                    "message": "The itinerary-draft store is unavailable."},
        ) from None
    return DraftListResponse(items=[_to_summary(r) for r in records],
                             total=total, limit=limit, offset=offset)


@router.get("/{draft_id}", response_model=DraftDetail)
def get_draft(draft_id: str,
              owner: str = Depends(require_subject),
              repository: ItineraryDraftRepository = Depends(get_repository),
              ) -> DraftDetail:
    if not _valid_draft_id(draft_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "Draft not found."})
    try:
        record = repository.get(owner, draft_id)
    except (RepositoryClosed, RepositoryError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "storage_error",
                    "message": "The itinerary-draft store is unavailable."},
        ) from None
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "Draft not found."})
    return _to_detail(record)


@router.delete("/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_draft(draft_id: str,
                 owner: str = Depends(require_subject),
                 repository: ItineraryDraftRepository = Depends(get_repository),
                 ) -> None:
    if not _valid_draft_id(draft_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "Draft not found."})
    try:
        deleted = repository.delete(owner, draft_id)
    except (RepositoryClosed, RepositoryError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "storage_error",
                    "message": "The itinerary-draft store is unavailable."},
        ) from None
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "Draft not found."})
    return None
