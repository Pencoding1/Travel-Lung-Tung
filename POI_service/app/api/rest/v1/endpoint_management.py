from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any

# Adjust this import to match where your dependency injection lives
from app.core.security.auth import verify_jwt_token
from app.api.dependencies.services import get_poi_management_service
from app.core.services.management import POIManagementService

router = APIRouter(prefix="/management", tags=["Data Management"],dependencies=[Depends(verify_jwt_token)])

@router.get("/", status_code=status.HTTP_200_OK)
def health_check():
    """Simple health check for the Ingestion Service."""
    return {
        "status": "online",
        "service": "POI Management Service",
        "message": "Ready create."
    }


@router.post("/poi", status_code=status.HTTP_201_CREATED)
def create_single_poi(
    payload: Dict[str, Any], 
    service: POIManagementService = Depends(get_poi_management_service)
):
    result = service.create(payload)
    
    if not result["is_success"]:
        # Map internal error_types to HTTP status codes
        error_mapping = {
            "unprocessable_entity": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "conflict": status.HTTP_409_CONFLICT,
            "internal_error": status.HTTP_500_INTERNAL_SERVER_ERROR
        }
        
        raise HTTPException(
            status_code=error_mapping.get(result["error_type"], 500), 
            detail=result["payload"]
        )
            
    return result["payload"]