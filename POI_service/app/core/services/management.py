from typing import Dict, Any, Optional, List
from app.core.base.service import BaseManagementService
from app.core.domain.graph_entities import POI, Category

class POIManagementService(BaseManagementService[POI]):
    """
    Concrete implementation of the management flow strictly for POIs.
    """

    def _validate_payload(self, payload: Dict[str, Any]) -> POI:
        # Pydantic handles the location mapping and ID generation via the model_validator
        return POI.model_validate(payload)

    def _get_existing(self, entity_id: str) -> Optional[POI]:
        # Utilizing the UoW's active transaction to check the DB
        return self.uow.pois.get_by_id(entity_id)

    def _execute_create(self, entity: POI) -> POI:
        return self.uow.pois.create(entity)

    def _execute_update(self, entity_id: str, entity: POI) -> POI:
        return self.uow.pois.update(entity_id, entity)

    def _execute_delete(self, entity_id: str) -> bool:
        return self.uow.pois.delete(entity_id)
    
    def get_all(self, skip:int=0, limit:int=20) -> List[Dict[str, Any]]:
        """Fetchs a paginated list of all POIs."""
        with self.uow:
            pois = self.uow.pois.get_all(skip=skip, limit=limit)
            return [poi.model_dump() for poi in pois]

    def get_pois_by_city(self, city_name: str, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetches POIs filtered by city."""
        with self.uow:
            pois = self.uow.pois.get_by_city(city_name, skip=skip, limit=limit)
            return [poi.model_dump() for poi in pois]

    def get_pois_by_category(self, category_id: str) -> List[Dict[str, Any]]:
        """Fetches POIs linked to a specific category ID."""
        with self.uow:
            pois = self.uow.pois.get_by_category_id(category_id)
            return [poi.model_dump() for poi in pois]
        


class CategoryManagementService(BaseManagementService[Category]):

    def _validate_payload(self, payload: Dict[str, Any]) -> Category:
        return Category.model_validate(payload)
    
    def _get_existing(self, entity_id: str) -> Category | None:
        return self.uow.cats.get_by_id(entity_id)
    
    def _execute_create(self, entity: Category) -> Category:
        return self.uow.cats.create(entity)
    
    def _execute_update(self, entity_id: str, entity: Category) -> Category:
        return self.uow.cats.update(entity_id, entity)