from abc import abstractmethod, ABC
from typing import List, Optional

from app.core.base.repository import BaseRepository
from app.core.domain.graph_entities import (
    POI, 
    Category,
    Tag, 
)


class IPOIRepository(BaseRepository[POI]):
    """
    Handles POI and its nested value objects: Address, ContactInfo, Product.
    """
    @abstractmethod
    def create(self, entity: POI) -> POI: 
        pass

    @abstractmethod
    def batch_create(self, poi_batch: list[dict]) -> int:
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


class ICategoryRepository(BaseRepository[Category]):
    @abstractmethod
    def get_by_name(self, name: str) -> Optional[Category]:
        pass


class ITagRepository(BaseRepository[Tag]):
    @abstractmethod
    def get_by_name(self, name: str) -> Optional[Tag]:
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


class AbstractUnitOfWork(ABC):
    pois: IPOIRepository
    cats: ICategoryRepository

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, traceback):
        if exc_type:
            self.rollback()
        else:
            self.commit()

    @abstractmethod
    def commit(self):
        pass

    @abstractmethod
    def rollback(self):
        pass