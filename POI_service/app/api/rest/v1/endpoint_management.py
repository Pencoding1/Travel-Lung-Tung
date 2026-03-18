from fastapi import APIRouter, Depends, status
from typing import Dict, Any

from app.api.dependencies.services import get_poi_management_service
from app.core.services.management import POIManagementService

router = APIRouter(prefix="/management/pois", tags=["POI Management"])

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_poi(
    payload: Dict[str, Any], 
    service: POIManagementService = Depends(get_poi_management_service)
):
    return service.create(payload)