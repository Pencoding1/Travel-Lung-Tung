from fastapi import APIRouter, BackgroundTasks, Depends
from typing import List

from app.core.utils.updater import SpatialUpdater
from app.core.security.auth import verify_jwt_token
from app.core.infrastructure.db.uow import MemgraphUnitOfWork
from app.api.dependencies.services import get_memgraph_connector

router = APIRouter(prefix="/management", tags=["Data Management"],dependencies=[Depends(verify_jwt_token)])

@router.post("/pois/spatial-rebuild")
async def rebuild_spatial_network(
    districts: List[str], 
    background_tasks: BackgroundTasks,
    # Inject your factory or components here depending on your setup
):
    """Manually trigger the spatial network calculation for specific districts."""
    updater = SpatialUpdater()
    
    # We pass the UoW factory exactly like we did before!
    updater.trigger_update(
        affected_districts=districts,
        uow_factory=lambda: MemgraphUnitOfWork(get_memgraph_connector()), # Adjust based on your actual imports
        background_tasks=background_tasks
    )
    
    return {"status": "success", "message": f"Spatial rebuild started for {len(districts)} districts."}