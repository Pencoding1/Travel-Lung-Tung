import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# 1. Load Environment Variables First
load_dotenv()

# 2. Trigger Security Fail-Fast 
# Importing this here ensures the app crashes immediately if JWT_SECRET is missing.
from app.core.security.auth import JWT_SECRET  # noqa: F401
from app.core.infrastructure.db.database.connector import (
    dependency_health,
    firestore_db,
    memgraph_db,
    shutdown_databases,
    startup_databases,
)

# 3. Import Routers
from app.api.rest.v1.endpoint_ingestion import router as ingestion_router
from app.api.rest.v1.endpoint_management import router as management_router
from app.api.rest.v1.endpoint_poi_router import router as poi_router
from app.api.rest.v1.endpoint_spatial_rebuild import router as spatial_router

# ---------------------------------------------------------
# LIFECYCLE MANAGEMENT (The "Heartbeat")
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown logic.
    Ensures database drivers are ready before any requests hit the API.
    """
    logging.info("Travel Lung Tung POI Service starting up...")
    try:
        # Graph DB is always required; Firestore is opt-in via FIRESTORE_ENABLED.
        # On any failure this cleans up already-initialized resources and raises
        # a sanitized error, so the app never serves in a degraded state.
        await startup_databases(memgraph_db, firestore_db)
    except Exception:
        logging.critical("POI service startup failed; refusing to serve requests.")
        raise

    try:
        yield
    finally:
        # Shutdown: cleanly close both drivers even if shutdown is triggered by
        # an exception escaping the application.
        logging.info("Shutting down. Cleaning up external connections...")
        await shutdown_databases(memgraph_db, firestore_db)


# ---------------------------------------------------------
# APP INITIALIZATION
# ---------------------------------------------------------
app = FastAPI(
    title="Travel Lung Tung POI API",
    description="Knowledge Graph ingestion and management for AI-powered travel.",
    version="1.0.0",
    lifespan=lifespan
)

# 4. CORS Middleware 
# Essential for your student startup competition UI to talk to this backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Adjust to specific domains for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 5. Global Exception Handler
# Ensures that even unhandled logic crashes return a clean 500 JSON response.
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Constant event, safe request method and exception type only. The URL,
    # query string and raw exception text are never logged here because they
    # can carry user input or credentials.
    logging.error("POI_UNHANDLED_EXCEPTION method=%s type=%s",
                  request.method, type(exc).__name__)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "is_success": False,
            "error_type": "internal_server_error",
            "payload": {"message": "An unexpected error occurred on the Z390 server."}
        }
    )

# ---------------------------------------------------------
# ROUTER INCLUSION
# ---------------------------------------------------------
# Health check remains public
@app.get("/", tags=["Health"])
def root():
    return {
        "status": "online",
        "message": "Travel Lung Tung POI Service is live",
        "architecture": "Event-Driven Hybrid Ingestion",
        "dependencies": dependency_health(memgraph_db, firestore_db),
    }

# Attach our specialized routers
app.include_router(ingestion_router)
app.include_router(management_router)
app.include_router(poi_router)
app.include_router(spatial_router)