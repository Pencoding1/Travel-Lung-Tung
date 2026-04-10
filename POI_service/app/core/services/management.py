import json 
from fastapi import HTTPException, status
from typing import Dict, Any, Optional, List


from app.core.base.service import BaseManagementService
from app.core.domain.get_payload import (
    POIGetResponse, POIResult, POIDescription, 
    ReviewDetail, POIContactInfo, NearbyPOI, POILite, OfferLite
)
from app.core.domain.graph_entities import POI, Category
from app.core.interfaces.repositories import IDocumentRepository

from travel_shared.exceptions import IntentedNotImplementedException

import json
from typing import List, Dict, Any, Optional
# Assuming your exceptions, schemas, and base service imports are here...

class POIManagementService(BaseManagementService[POI]):
    """
    Concrete implementation of the management flow strictly for POIs.
    """

    def _validate_payload(self, payload: Dict[str, Any]) -> POI:
        return POI.model_validate(payload)

    def _get_existing(self, entity_id: str) -> Optional[POI]:
        return self.uow.pois.get_by_id(entity_id)

    def _execute_create(self, entity: POI) -> POI:
        return self.uow.pois.create(entity)

    def _execute_update(self, entity_id: str, entity: POI) -> POI:
        return self.uow.pois.update(entity_id, entity)

    def _execute_delete(self, entity_id: str) -> bool:
        return self.uow.pois.delete(entity_id)
    
    def get_poi(self, id: str) -> Optional[POI]:
        return self._get_existing(id)

    def get_all(self, skip: int = 0, limit: int = 20) -> List[Dict[str, Any]]:
        with self.uow:
            pois = self.uow.pois.get_all(skip=skip, limit=limit)
            return [json.loads(poi.model_dump_json()) for poi in pois]

    # -------------------------------------------------------------------
    # NEW: HIERARCHICAL DISCOVERY METHODS
    # -------------------------------------------------------------------
    
    def get_all_cities(self) -> List[Dict[str, str]]:
        with self.uow:
            return self.uow.pois.get_all_cities()

    def get_districts_by_city(self, city_id: str) -> List[Dict[str, str]]:
        with self.uow:
            return self.uow.pois.get_districts_by_city(city_id)

    def get_streets_by_district(self, district_id: str) -> List[Dict[str, str]]:
        with self.uow:
            return self.uow.pois.get_streets_by_district(district_id)

    def get_available_categories(self) -> List[Dict[str, str]]:
        """Retrieves all valid category IDs and names for the Agent."""
        with self.uow:
            return self.uow.pois.get_all_categories()
            
    # -------------------------------------------------------------------
    # EXPLORATION METHODS (Strict ID Based & Context-Window Optimized)
    # -------------------------------------------------------------------

    def explore_by_city_id(self, city_id: str, skip: int = 0, limit: int = 15) -> List[Dict[str, Any]]:
        with self.uow:
            pois = self.uow.pois.get_by_city_id_lite(city_id, skip=skip, limit=limit)
            return [poi.model_dump() for poi in pois]

    def explore_by_district_id(self, district_id: str, skip: int = 0, limit: int = 15) -> List[Dict[str, Any]]:
        with self.uow:
            pois = self.uow.pois.get_by_district_id_lite(district_id, skip=skip, limit=limit)
            return [poi.model_dump() for poi in pois]

    def explore_by_street_id(self, street_id: str, skip: int = 0, limit: int = 15) -> List[Dict[str, Any]]:
        with self.uow:
            pois = self.uow.pois.get_by_street_id_lite(street_id, skip=skip, limit=limit)
            return [poi.model_dump() for poi in pois]

    def explore_by_category(self, category_id: str, skip: int = 0, limit: int = 15) -> List[Dict[str, Any]]:
        with self.uow:
            pois = self.uow.pois.get_by_category_id_lite(category_id, skip=skip, limit=limit)
            return [poi.model_dump() for poi in pois]

    def explore_by_product(self, product_keyword: str, skip: int = 0, limit: int = 15) -> List[Dict[str, Any]]:
        with self.uow:
            pois = self.uow.pois.get_by_offered_products_lite(product_keyword, skip=skip, limit=limit)
            return [poi.model_dump() for poi in pois]

    # -------------------------------------------------------------------
    # DEEP RETRIEVAL METHOD (Full Details & Graph Data)
    # -------------------------------------------------------------------

    def get_agentic_poi_details(self, poi_id: str, doc_repo: 'IDocumentRepository') -> POIGetResponse:
        # 1. Graph RAG Retrieval
        with self.uow:
            graph_data = self.uow.pois.get_poi_graph_payload(id=poi_id, radius_km=3.0, limit=5)
            
        if not graph_data:
            raise ValueError(f"POI with ID '{poi_id}' not found in the Knowledge Graph.")

        # 2. Document RAG Retrieval (Circuit Breaker Applied)
        try:
            doc_data = doc_repo.get_poi_documents(poi_id=poi_id)
        except IntentedNotImplementedException:
            doc_data = {
                "insight": "Document RAG integration pending.",
                "seo_article": "",
                "review": {"rating": 0.0, "review": ""}
            }
        except Exception:
            doc_data = {
                "insight": "Information temporarily unavailable.",
                "seo_article": "",
                "review": {"rating": 0.0, "review": ""}
            }

        # 3. Stitch Document RAG
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

        # 4. Map the Offers safely from the Graph Edge
        offers_list = []
        for offer in graph_data.get("Offers", []):
            if offer:
                raw_name = offer.get("name")
                safe_name = str(raw_name) if raw_name is not None else "Unnamed Product"
                
                raw_price = offer.get("price")
                safe_price = float(raw_price) if raw_price is not None else 0.0
                
                if raw_name is not None or raw_price is not None:
                    offers_list.append(
                        OfferLite(
                            name=safe_name,
                            price=safe_price
                        )
                    )

        # 5. Map the NEAR_BY list safely
        nearby_list = []
        for n in graph_data.get("NEAR_BY", []):
            if n is None:
                continue
            try:
                raw_dist = n.get("distance")
                safe_dist = float(raw_dist) if raw_dist is not None else 0.0
                
                nearby_list.append(
                    NearbyPOI(
                        poi=POILite(
                            id=n.get("POI_ID", ""),
                            name=n.get("POI_Name", ""),
                            full_address=n.get("POI_Address", "Address not specified"),
                            categories=[n.get("POI_Category", "Uncategorized")]
                        ),
                        distance=safe_dist
                    )
                )
            except Exception as e:
                continue

        # ---------------------------------------------------------
        # 🆕 NEW: Defensively extract and cast coordinates to float
        # ---------------------------------------------------------
        raw_lat = graph_data.get("latitude")
        safe_lat = float(raw_lat) if raw_lat is not None else None
        
        raw_lng = graph_data.get("longitude")
        safe_lng = float(raw_lng) if raw_lng is not None else None

        # 6. Construct Final Payload
        result = POIResult(
            POI_ID=graph_data["POI_ID"],
            POI_Name=graph_data["POI_Name"],
            POI_Address=graph_data["POI_Address"],
            POI_Category=graph_data["POI_Category"],
            latitude=safe_lat,     # <-- Injected here
            longitude=safe_lng,    # <-- Injected here
            POI_Description=description,
            POI_Contact_Info=contact_info,
            Offers=offers_list,      
            NEAR_BY=nearby_list      
        )

        return POIGetResponse(success=True, result=result)

    def search_location_id(self, keyword: str) -> List[Dict[str, str]]:
        with self.uow:
            return self.uow.pois.search_location_id(keyword)


class CategoryManagementService(BaseManagementService[Category]):

    def _validate_payload(self, payload: Dict[str, Any]) -> Category:
        return Category.model_validate(payload)
    
    def _get_existing(self, entity_id: str) -> Category | None:
        return self.uow.cats.get_by_id(entity_id)
    
    def _execute_create(self, entity: Category) -> Category:
        return self.uow.cats.create(entity)
    
    def _execute_update(self, entity_id: str, entity: Category) -> Category:
        return self.uow.cats.update(entity_id, entity)