from fastapi import APIRouter, Depends, status, BackgroundTasks
from typing import List, Dict, Any

from app.api.dependencies.services import get_poi_ingestion_service
from app.core.services.ingestion import POIIngestionService

router = APIRouter(prefix="/ingestion", tags=["Data Ingestion"])

@router.post("/batch", status_code=status.HTTP_202_ACCEPTED)
def ingest_poi_batch(
    payload: List[Dict[str, Any]], 
    background_tasks: BackgroundTasks, # Run massive jobs in the background!
    service: POIIngestionService = Depends(get_poi_ingestion_service)
):
    background_tasks.add_task(service.process_ota_batch, payload)
    
    return {
        "status": "Processing initiated",
        "batch_size": len(payload),
        "message": "The graph is currently unrolling and merging your data."
    }