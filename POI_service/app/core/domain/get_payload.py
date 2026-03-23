from pydantic import BaseModel, Field
from typing import List, Optional

class ReviewDetail(BaseModel):
    rating: float = Field(..., description="Average rating of the POI")
    review: str = Field(..., description="A summarized review text")

class POIDescription(BaseModel):
    insight: str = Field(default="", description="Key insights or vibe of the POI")
    seo_article: str = Field(default="", description="SEO optimized descriptive text")
    review: ReviewDetail

class POIContactInfo(BaseModel):
    website: Optional[str] = ""
    fanpage: Optional[str] = ""
    phonenumber: Optional[str] = ""
    

class POILite(BaseModel):
    POI_ID: str
    POI_Name: str
    POI_Address: str
    POI_Category: str

class NearbyPOI(BaseModel):
    poi: POILite
    distance: float = Field(..., description="Spatial distance in kilometers or meters")

class POIResult(BaseModel):
    POI_ID: str
    POI_Name: str
    POI_Address: str
    POI_Description: POIDescription
    POI_Category: str
    POI_Contact_Info: POIContactInfo
    NEAR_BY: List[NearbyPOI] = Field(default_factory=list)


class POIGetResponse(BaseModel):
    success: bool = Field(default=True)
    result: POIResult