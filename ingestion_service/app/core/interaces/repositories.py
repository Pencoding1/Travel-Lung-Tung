from abc import abstractmethod
from typing import TypeVar, Generic, List, Optional

from app.core.base.repository import BaseRepository
from app.db.models.Graph_Entities import (
    POI, 
    Itinerary, 
    Category,
    Stop, 
    Tag, 
    Description
)


class IPOIRepository(BaseRepository[POI]):
    """
    Handles POI and its nested value objects: Address, ContactInfo, Product.
    """
    @abstractmethod
    def get_by_city(self, city_name: str, skip: int = 0, limit: int = 100) -> List[POI]:
        pass

    @abstractmethod
    def get_by_category_id(self, category_id: str) -> List[POI]:
        pass
        
    @abstractmethod
    def get_by_tag_id(self, tag_id: str) -> List[POI]:
        pass


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


class ICategoryRepository(BaseRepository[Category]):
    @abstractmethod
    def get_by_name(self, name: str) -> Optional[Category]:
        pass


class ITagRepository(BaseRepository[Tag]):
    @abstractmethod
    def get_by_name(self, name: str) -> Optional[Tag]:
        pass


class IDescriptionRepository(BaseRepository[Description]):
    @abstractmethod
    def get_by_poi_id(self, poi_id: str) -> Optional[Description]:
        pass