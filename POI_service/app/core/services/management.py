from typing import Dict, Any, Optional
from app.core.base.service import BaseManagementService
from POI_service.app.core.domain.graph_entities import POI

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