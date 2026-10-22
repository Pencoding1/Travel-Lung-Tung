from abc import abstractmethod, ABC
from typing import List, Optional, Dict, Any

from app.core.base.repository import BaseRepository
from app.core.domain.graph_entities import (
    POI, 
    Category,
    Tag, 
)
from app.core.domain.get_payload import POILite, POICompoundLite
from app.core.domain.source_scope import SourceSnapshotSelection


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

    @abstractmethod
    def get_compound_explore_lite(
        self,
        city_id: Optional[str] = None,
        district_id: Optional[str] = None,
        street_id: Optional[str] = None,
        category_id: Optional[str] = None,
        product_keyword: Optional[str] = None,
        limit: int = 15,
        offset: int = 0,
    ) -> List['POICompoundLite']:
        """Conjunctive, exact-id exploration.

        All supplied administrative/category ids are applied together *before*
        the limit, category ids are never translated to display names, and the
        result is deterministically ordered by ``p.id`` with relationship
        duplicates removed. Each item carries its structured category ids and
        parent ``administrative_context``.
        """
        pass

    @abstractmethod
    def get_compound_explore_source(
        self,
        selection: 'SourceSnapshotSelection',
        city_id: Optional[str] = None,
        district_id: Optional[str] = None,
        street_id: Optional[str] = None,
        category_id: Optional[str] = None,
        product_keyword: Optional[str] = None,
        limit: int = 15,
        offset: int = 0,
    ) -> tuple[List['POICompoundLite'], Dict[str, Any]]:
        """Retrieve only records that fail-closed qualify for ``selection``.

        Stored metadata/SHA, the actual POI id and any cached flat selector are
        validated before a record can match. Returns the page plus a scan report
        so callers cannot silently claim an incomplete scan was complete.
        """
        pass

    @abstractmethod
    def iter_source_scope_records(
        self,
        after_id: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Bounded keyset page over metadata-bearing records for discovery.

        Records written before flat selector properties existed are included and
        qualified from their stored metadata on read.
        """
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

        The rebuild is a *replacement*: every ``:NEAR_BY`` edge incident to an
        anchor POI of the district is removed (including anchors with
        missing/invalid coordinates, so their stale edges are cleaned) and the
        valid canonical pairs are re-created, all inside the caller's
        transaction. Edges that belong only to other districts are never
        touched.
        """
        pass

    @abstractmethod
    def build_nearby_edges_for_poi(self,
                                   poi_id: str,
                                   radius_km: float = 3.0) -> int:
        """
        Explicit single-POI rebuild of incident ``:NEAR_BY`` edges.

        Required when an anchor moves out of its district: a district-scoped
        rebuild cannot clean the edges the moved POI left behind in its old
        district. Added as a documented new repository contract; live
        integration is pending and not claimed by district rebuilds alone.
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
    # ``cats`` is the name every management service uses; ``categories`` is the
    # descriptive alias kept for direct callers. A concrete UnitOfWork must
    # assign the *same* repository instance to both names so a wiring mistake
    # cannot silently route two code paths to different transactions.
    pois: IPOIRepository
    cats: ICategoryRepository
    categories: ICategoryRepository
    tags: ITagRepository
    users: IUserBehaviorRepository

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