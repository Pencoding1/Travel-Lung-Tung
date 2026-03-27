from abc import abstractmethod, ABC
from typing import List, Optional, Dict, Any

from app.core.base.repository import BaseRepository
from app.core.domain.graph_entities import (
    POI, 
    Category,
    Tag, 
)
from app.core.domain.get_payload import POILite


class IPOIRepository(ABC):
    """
    Handles POI and its nested value objects: Address, ContactInfo, Product.
    Strictly interfaces with the Graph Database (Memgraph).
    """
    @abstractmethod
    def get_by_id(self, id: str) -> Optional['POI']:
        pass

    @abstractmethod
    def create(self, entity: 'POI') -> 'POI': 
        pass

    @abstractmethod
    def batch_create(self, poi_batch: list[dict]) -> int:
        pass

    @abstractmethod
    def update(self, id: str, entity: 'POI') -> 'POI':
        pass

    @abstractmethod
    def delete(self, id: str) -> bool:
        pass

    @abstractmethod
    def get_all(self, skip: int = 0, limit: int = 100) -> List['POI']:
        pass

    # -------------------------------------------------------------------
    # NEW: Hierarchical Discovery Methods
    # -------------------------------------------------------------------
    
    @abstractmethod
    def get_all_cities(self) -> List[Dict[str, str]]:
        pass

    @abstractmethod
    def get_districts_by_city(self, city_id: str) -> List[Dict[str, str]]:
        pass

    @abstractmethod
    def get_streets_by_district(self, district_id: str) -> List[Dict[str, str]]:
        pass

    @abstractmethod
    def get_all_categories(self) -> List[Dict[str, str]]:
        pass

    # -------------------------------------------------------------------
    # NEW: Token-Optimized "Lite" Exploration Methods (Strict ID-Based)
    # -------------------------------------------------------------------

    @abstractmethod
    def get_by_city_id_lite(self, city_id: str, skip: int = 0, limit: int = 100) -> List['POILite']:
        pass

    @abstractmethod
    def get_by_district_id_lite(self, district_id: str, skip: int = 0, limit: int = 100) -> List['POILite']:
        pass
        
    @abstractmethod
    def get_by_street_id_lite(self, street_id: str, skip: int = 0, limit: int = 100) -> List['POILite']:
        pass

    @abstractmethod
    def get_by_category_id_lite(self, category_id: str, skip: int = 0, limit: int = 100) -> List['POILite']:
        pass

    @abstractmethod
    def get_by_offered_products_lite(self, product_keyword: str, skip: int = 0, limit: int = 100) -> List['POILite']:
        pass

    # -------------------------------------------------------------------
    # Deep Retrieval & Batch Processing
    # -------------------------------------------------------------------

    @abstractmethod
    def get_poi_graph_payload(self, 
                              id: str, 
                              radius_km: float = 3.0, 
                              limit: int = 5) -> Optional[Dict[str, Any]]:
        """
        Fetches the POI and extracts pre-calculated NEAR_BY and OFFER edges.
        Returns a dictionary prepared for the POIResult schema (excluding Vector DB data).
        """
        pass
    
    @abstractmethod
    def build_nearby_edges_for_district(self,
                                        district_id: str,
                                        radius_km: float) -> int:
        """
        Executes an isolated batch job to pre-calculate and draw physical [:NEAR_BY] 
        edges between POIs within the same district to eliminate runtime spatial math.
        """
        pass

    @abstractmethod
    def search_location_id(self, keyword: str) -> List[Dict[str, str]]: pass

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

class IDocumentRepository(ABC):
    @abstractmethod
    def get_poi_documents(self, poi_id: str) -> Dict:
        """ Should return a dict with insight, seo_article, and review """
        pass