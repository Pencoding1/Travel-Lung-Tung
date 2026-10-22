"""FastAPI application factory for the backend service (OC-027).

The app is created with an injected :class:`ItineraryDraftRepository`. When none
is supplied the factory builds one from environment settings: the default is
``none`` (no storage), so importing this module never imports ``firebase_admin``,
opens a socket or requires a credential. A test or embedder can pass a fake
repository and the whole HTTP surface runs with no database or network.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.rest.v1.endpoint_itinerary import router as itinerary_router
from app.core.middleware import BoundedJsonBodyMiddleware
from app.core.repositories.itinerary_draft import ItineraryDraftRepository
from app.core.settings import BackendSettings, build_repository, load_settings


def _repository_health(repository: ItineraryDraftRepository) -> Dict[str, Any]:
    try:
        return repository.health()
    except Exception:  # noqa: BLE001 - health must never raise
        return {"available": False,
                "backend": getattr(repository, "backend", "unknown"),
                "detail": "health check failed"}


def create_app(*, repository: Optional[ItineraryDraftRepository] = None,
               settings: Optional[BackendSettings] = None) -> FastAPI:
    """Build the application, injecting a repository or resolving one from env."""
    if settings is None:
        settings = load_settings()
    if repository is None:
        repository = build_repository(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # Owned lifespan. Startup is the deliberate initialization boundary: a
        # repository that owns durable storage (SQLite) is initialized here, and
        # only here — never from a health probe or an ordinary request. A
        # pre-existing invalid database fails startup loudly (fail-closed) rather
        # than being silently replaced. The repository is closed on shutdown.
        initialize = getattr(repository, "initialize", None)
        if callable(initialize):
            initialize()
        try:
            yield
        finally:
            repository.close()

    app = FastAPI(title="TVLT Backend Service", version="0.1.0", lifespan=lifespan)
    app.add_middleware(BoundedJsonBodyMiddleware)
    app.state.repository = repository
    app.state.settings = settings
    app.include_router(itinerary_router, prefix="/api/v1")

    @app.exception_handler(RecursionError)
    async def _recursion_handler(_: Request, __: RecursionError) -> JSONResponse:
        # Defense-in-depth: a body that still overflows the parser is reported as
        # a bounded structured rejection, never a 500/traceback.
        return JSONResponse(
            status_code=422,
            content={"detail": {"code": "payload_too_deep",
                                "message": "Request JSON nesting is too deep."}})

    @app.get("/health", tags=["health"])
    def health() -> Dict[str, Any]:
        return {"status": "ok", "repository": _repository_health(repository)}

    @app.get("/ready", tags=["health"])
    def ready() -> Any:
        repo_health = _repository_health(repository)
        if not repo_health.get("available"):
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "repository": repo_health})
        return {"status": "ready", "repository": repo_health}

    return app


app = create_app()
