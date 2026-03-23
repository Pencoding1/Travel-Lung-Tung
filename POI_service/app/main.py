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
from app.core.security.auth import JWT_SECRET 
from app.core.infrastructure.db.database.connector import memgraph_db, firestore_db

# 3. Import Routers
from app.api.rest.v1.endpoint_ingestion import router as ingestion_router
from app.api.rest.v1.endpoint_management import router as management_router
from app.api.rest.v1.endpoint_poi_router import router as poi_router


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
        # 1. Activate Connections explicitly
        firestore_db.connect()
        await memgraph_db.connect()  # Note the 'await' here!
        
        # 2. Verify Firebase (Memgraph verified itself during connect)
        if not firestore_db.verify_connectivity():
            raise ConnectionError("Firebase SDK failed to verify connection.")

    except Exception as e:
        logging.critical(f"Startup check failed: {str(e)}")
        raise RuntimeError(f"Database verification failed: {str(e)}")
        
    yield
    
    # Shutdown: Cleanly close BOTH database drivers
    logging.info("Shutting down. Cleaning up external connections...")
    memgraph_db.close()
    firestore_db.close()


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
    logging.error(f"GLOBAL CRASH: {request.method} {request.url} - {str(exc)}")
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
        "architecture": "Event-Driven Hybrid Ingestion"
    }

# Attach our specialized routers
app.include_router(ingestion_router)
app.include_router(management_router)
app.include_router(poi_router)