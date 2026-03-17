from abc import abstractmethod
from datetime import datetime
from typing import TypeVar, Generic, List, Optional

from httpx import delete

from app.core.base.repository import BaseRepository
from app.core.domain.Graph_Entities import (
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
    def create(self, entity: POI) -> POI: 
        pass

    @abstractmethod
    def update(self, id: str, entity: POI) -> POI:
        pass

    @abstractmethod
    def delete(self, id:str) -> bool:
        pass

    @abstractmethod
    def get_all(self, skip: int = 0, limit: int = 100) -> List[POI]:
        pass

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


class IUserBehaviorRepository(BaseRepository):
    @abstractmethod
    def set_preference(self, user_id: str, category_id: str, weight: float) -> None:
        """Draws a weighted edge between a user and a category."""
        pass

    @abstractmethod
    def get_preferred_pois(self, user_id: str, city: str, province: Optional[str] = None, street: Optional[str] = None, limit: int = 10) -> List[POI]:
        """Traverses User -> Category -> POI to return recommendations."""
        pass