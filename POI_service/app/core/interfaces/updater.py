from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable

from fastapi import BackgroundTasks
from app.core.interfaces.repositories import AbstractUnitOfWork, IPOIRepository

class ISpatialUpdate(ABC):
    """
    The spatial distance within a district updater interface that define the background
    task for updating NEAR_BY relationship of POIs.
    """
    @abstractmethod
    def trigger_update(self,
                       affected_districts: List[str],
                       repository: Callable[[], AbstractUnitOfWork],
                       background_tasks: Optional[BackgroundTasks] = None):
        pass

    @abstractmethod
    def rebuild_pois(self,
                     poi_ids: List[str],
                     uow_factory: Callable[[], AbstractUnitOfWork]) -> Dict[str, Any]:
        """Transactionally replace the incident ``:NEAR_BY`` edges of each POI id.

        Implementations must return a *structured* report that distinguishes the
        POIs that were rebuilt from those that failed (sanitized error types
        only). This is the bulk-ingestion spatial stage: it runs **after** the
        POI writes have committed, so a spatial failure is reported separately
        and never rewrites a successful insert into a failed one.
        """
        pass
