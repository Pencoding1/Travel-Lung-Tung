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
    id: str
    name: str
    full_address: Optional[str] = "Address not specified"
    categories: List[str] = []
    operation_time: Optional[str] = "Hours not specified"
    offers: List[str] = [] # Example format: ["Iced Latte (2.5)", "Croissant (1.5)"]


class NearbyPOI(BaseModel):
    poi: POILite
    distance: float = Field(..., description="Spatial distance in kilometers or meters")

class OfferLite(BaseModel):
    name: str
    price: float

class POIGetResponse(BaseModel):
    success: bool = Field(default=True)
    result: 'POIResult'

class POIResult(BaseModel):
    POI_ID: str
    POI_Name: str
    POI_Address: str
    POI_Category: str
    
    # NEW: Expose coordinates to the AI!
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    POI_Description: 'POIDescription'
    POI_Contact_Info: 'POIContactInfo'
    
    # The unrolled graph edges
    Offers: List['OfferLite'] = []  
    NEAR_BY: List['NearbyPOI'] = []

