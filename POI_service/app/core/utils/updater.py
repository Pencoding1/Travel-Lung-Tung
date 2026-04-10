import logging
from typing import List, Optional, Callable

from fastapi import BackgroundTasks
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.base.service import AbstractUnitOfWork
from app.core.interfaces.updater import ISpatialUpdate

logger = logging.getLogger(__file__)

class SpatialUpdater(ISpatialUpdate):
    
    def trigger_update(self, 
                       affected_districts: List[str], 
                       uow_factory: Callable[[], AbstractUnitOfWork], 
                       background_tasks: Optional[BackgroundTasks] = None):
        if not background_tasks:
            logger.warning("No BackgroundTasks provided. Spatial update will run synchronously.")
            self._execute_update(affected_districts, uow_factory)
            return

        background_tasks.add_task(self._execute_update, affected_districts, uow_factory)

    def _execute_update(self, districts: List[str], uow_factory: Callable[[], AbstractUnitOfWork]):
        print(f"🔥 DEBUG: _execute_update triggered for districts: {districts}")
        total_edges = 0
        
        for district_id in districts:
            try:
                # Call the retryable method!
                edges = self._build_district_with_retry(district_id, uow_factory)
                total_edges += edges
            except Exception as e:
                # If it permanently fails after 5 retries, log it and move to the next district
                print(f"❌ DEBUG: Permanently failed spatial edges for {district_id}: {str(e)}")
                
        print(f"🔥 DEBUG: Background Task Complete. Total new spatial edges: {total_edges}")

    # ---> THE 50N42 SHIELD <---
    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
    def _build_district_with_retry(self, district_id: str, uow_factory: Callable[[], AbstractUnitOfWork]) -> int:
        print(f"🔥 DEBUG: Calling repository for {district_id}...")
        
        # Instantiate a fresh, living connection using the factory
        uow = uow_factory() 
        
        # Open the clean transaction
        with uow:
            edges = uow.pois.build_nearby_edges_for_district(district_id, radius_km=3.0)
            print(f"✅ DEBUG: District {district_id} complete. {edges} edges generated.")
            return edges