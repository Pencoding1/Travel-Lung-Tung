from typing import Optional
from fastapi import HTTPException, status

from app.core.interfaces.repositories import IPOIRepository, IDocumentRepository
from app.core.domain.get_payload import (
    POIGetResponse, 
    POIResult, 
    POIDescription, 
    ReviewDetail, 
    POIContactInfo, 
    NearbyPOI, 
    POILite
)

class POIService:
    def __init__(self, poi_repo: IPOIRepository, doc_repo: IDocumentRepository):
        self.poi_repo = poi_repo
        self.doc_repo = doc_repo

    def get_poi_details(self, poi_id: str) -> POIGetResponse:
        """
        Orchestrates Graph RAG and Document RAG to build the Agentic payload.
        """
        # 1. Fetch Structured Graph Data & Spatial Tier 1 Filter
        graph_data = self.poi_repo.get_poi_graph_payload(id=poi_id, radius_km=3.0, limit=5)
        
        if not graph_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"POI with ID '{poi_id}' not found in the Knowledge Graph."
            )

        # 2. Fetch Unstructured Vector Data (Document RAG)
        # In a real scenario, the graph_data might contain specific vector_ids to query.
        # Here we use the POI_ID as the anchor for the Vector DB.
        try:
            doc_data = self.doc_repo.get_poi_documents(poi_id=poi_id)
        except Exception as e:
            # Fallback gracefully if Vector DB fails, to keep the agent moving
            doc_data = {
                "insight": "Information temporarily unavailable.",
                "seo_article": "",
                "review": {"rating": 0.0, "review": "No reviews available."}
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
                continue # Skip malformed nearby nodes rather than crashing

        # 5. Construct the Final Result Schema
        result = POIResult(
            POI_ID=graph_data["POI_ID"],
            POI_Name=graph_data["POI_Name"],
            POI_Address=graph_data["POI_Address"],
            POI_Category=graph_data["POI_Category"],
            POI_Description=description,
            POI_Contact_Info=contact_info,
            NEAR_BY=nearby_list
        )

        # 6. Wrap in the Egress format
        return POIGetResponse(success=True, result=result)