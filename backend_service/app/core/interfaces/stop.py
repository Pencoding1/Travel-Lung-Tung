from typing import List
from datetime import datetime
from abc import abstractmethod

from app.core.domain.Stops import Stop
from app.core.base.repository import BaseRepository

class IStopRepository(BaseRepository[Stop]):
    """
    Interface for Stop repository containing specific analytical/UI query methods.
    """
    @abstractmethod
    def get_by_budget(self, max_budget: float, skip: int = 0, limit: int = 100) -> List[Stop]:
        pass

    @abstractmethod
    def get_by_date(self, target_date: datetime, skip: int = 0, limit: int = 100) -> List[Stop]:
        pass

    @abstractmethod
    def get_by_duration_bucket(self, bucket_index: int, skip: int = 0, limit: int = 100) -> List[Stop]:
        pass


