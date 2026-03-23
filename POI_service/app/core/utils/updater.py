import logging
from typing import List, Optional

from app.core.interfaces.updater import ISpatialUpdate
from app.core.interfaces.repositories import IPOIRepository
from fastapi import BackgroundTasks

logger = logging.getLogger(__file__)

class SpatialUpdater(ISpatialUpdate):
    """
    Fires off a non-blocking background thread using FastAPI's native capabilities.
    Perfect for quick implementation without external infrastructure.
    """
    
    def trigger_update(self, 
                       affected_districts: List[str], 
                       repository: IPOIRepository, 
                       background_tasks: Optional[BackgroundTasks] = None
                    ):
        if not background_tasks:
            logger.warning("No BackgroundTasks provided. Spatial update will run synchronously, which may cause latency.")
            self._execute_update(affected_districts, repository)
            return

        # Hand the execution off to FastAPI's background thread pool
        background_tasks.add_task(self._execute_update, affected_districts, repository)

    def _execute_update(self, districts: List[str], repository: IPOIRepository):
        """The actual work performed in the background."""
        logger.info(f"Background Task Started: Updating NEAR_BY edges for districts: {districts}")
        total_edges = 0
        
        for district_id in districts:
            try:
                # This calls the Memgraph script we wrote earlier
                edges = repository.build_nearby_edges_for_district(district_id, radius_km=3.0)
                total_edges += edges
                logger.info(f"District {district_id} complete. {edges} edges generated.")
            except Exception as e:
                logger.error(f"Failed to update spatial edges for {district_id}: {str(e)}")
                
        logger.info(f"Background Task Complete. Total new spatial edges: {total_edges}")