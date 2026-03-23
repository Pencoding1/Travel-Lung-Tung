from fastapi import HTTPException, status
from typing import Dict, Any, Optional, List


from app.core.base.service import BaseManagementService
from app.core.domain.get_payload import (
    POIGetResponse, POIResult, POIDescription, 
    ReviewDetail, POIContactInfo, NearbyPOI, POILite
)
from app.core.domain.graph_entities import POI, Category
from app.core.interfaces.repositories import IDocumentRepository

from travel_shared.exceptions import IntentedNotImplementedException

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
    
    def get_agentic_poi_details(self, poi_id: str, doc_repo: IDocumentRepository) -> POIGetResponse:
        # 1. Graph RAG Retrieval
        with self.uow:
            graph_data = self.uow.pois.get_poi_graph_payload(id=poi_id, radius_km=3.0, limit=5)
            
        if not graph_data:
            # Raise a standard ValueError so the Controller knows it's a 404, not a 500
            raise ValueError(f"POI with ID '{poi_id}' not found in the Knowledge Graph.")

        # 2. Document RAG Retrieval (Circuit Breaker Applied)
        try:
            doc_data = doc_repo.get_poi_documents(poi_id=poi_id)
        except IntentedNotImplementedException:
            # Graceful fallback: Bypass unstructured data retrieval without breaking the flow
            doc_data = {
                "insight": "Document RAG integration pending.",
                "seo_article": "",
                "review": {"rating": 0.0, "review": ""}
            }
        except Exception:
            # Catch unexpected Vector DB connection drops in the future
            doc_data = {
                "insight": "Information temporarily unavailable.",
                "seo_article": "",
                "review": {"rating": 0.0, "review": ""}
            }

        # 3. Stitch Document RAG into Pydantic Sub-models
        description = POIDescription(
            insight=doc_data.get("insight", ""),
            seo_article=doc_data.get("seo_article", ""),
            review=ReviewDetail(
                rating=doc_data.get("review", {}).get("rating", 0.0),
                review=doc_data.get("review", {}).get("review", "")
            )
        )

        contact_info = POIContactInfo(
            website=graph_data.get("POI_Contact_Info", {}).get("website", ""),
            fanpage=graph_data.get("POI_Contact_Info", {}).get("fanpage", ""),
            phonenumber=graph_data.get("POI_Contact_Info", {}).get("phonenumber", "")
        )

        # 4. Map the NEAR_BY list safely
        nearby_list = []
        for n in graph_data.get("NEAR_BY", []):
            try:
                nearby_list.append(
                    NearbyPOI(
                        poi=POILite(
                            POI_ID=n["POI_ID"],
                            POI_Name=n["POI_Name"],
                            POI_Address=n["POI_Address"],
                            POI_Category=n["POI_Category"]
                        ),
                        distance=n["distance"]
                    )
                )
            except KeyError:
                continue

        # 5. Construct Final Payload
        result = POIResult(
            POI_ID=graph_data["POI_ID"],
            POI_Name=graph_data["POI_Name"],
            POI_Address=graph_data["POI_Address"],
            POI_Category=graph_data["POI_Category"],
            POI_Description=description,
            POI_Contact_Info=contact_info,
            NEAR_BY=nearby_list
        )

        return POIGetResponse(success=True, result=result)


class CategoryManagementService(BaseManagementService[Category]):

    def _validate_payload(self, payload: Dict[str, Any]) -> Category:
        return Category.model_validate(payload)
    
    def _get_existing(self, entity_id: str) -> Category | None:
        return self.uow.cats.get_by_id(entity_id)
    
    def _execute_create(self, entity: Category) -> Category:
        return self.uow.cats.create(entity)
    
    def _execute_update(self, entity_id: str, entity: Category) -> Category:
        return self.uow.cats.update(entity_id, entity)