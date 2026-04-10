from abc import ABC, abstractmethod
from typing import Any, List, Optional, Callable

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
