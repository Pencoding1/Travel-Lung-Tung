from typing import List
from abc import abstractmethod

from app.core.domain.Itinerary import Itinerary
from app.core.domain.Stops import Stop
from app.core.base.repository import BaseRepository


class IItineraryRepository(BaseRepository[Itinerary]):
    """
    Handles Itinerary and its nested list of Stops.
    """
    @abstractmethod
    def get_by_start_poi(self, poi_id: str) -> List[Itinerary]:
        pass

    @abstractmethod
    def get_by_end_poi(self, poi_id: str) -> List[Itinerary]:
        pass
    
    @abstractmethod
    def get_stops_list(self, id) -> List[Stop]:
        pass
