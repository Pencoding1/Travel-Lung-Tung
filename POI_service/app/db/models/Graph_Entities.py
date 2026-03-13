from app.db.models.enum import BudgetLevel, TravelPace

from pydantic import BaseModel, HttpUrl, Field, model_validator
from typing import List, Optional, Dict
from datetime import datetime

class Category(BaseModel):
    id: str
    name: str
    context: str

class Tag(BaseModel):
    id: str
    name: str

class UserPreference(BaseModel):
    user_id: str
    
    # 1. GRAPH EDGE ATTRIBUTES (Used in Stage 1: Cypher Clustering)
    category_weights: Dict[str, float] = Field(default_factory=dict)
    tag_weights: Dict[str, float] = Field(default_factory=dict)
    
    # 2. HARD CONSTRAINTS (Used in Stage 1 & Stage 3)
    daily_budget: Optional[float] = Field(None, description="Exact target spending per day")
    budget_level: BudgetLevel = Field(
        default=BudgetLevel.STANDARD,
        description="The classified budget tier that dictates price filtering."
    )
    
    travel_pace: TravelPace = Field(
        default=TravelPace.MODERATE,
        description="The preferred speed of travel, dictating how long the user stays at each POI."
    )
    dietary_restrictions: List[str] = Field(default_factory=list) # e.g., ["vegan", "halal"]
    requires_accessibility: bool = False # e.g., Wheelchair access needed
    
    # 3. QUALITATIVE CONTEXT (Used in Stage 2: LLM Scoring)
    personal_vibe: Optional[str] = Field(
        None, 
        description="e.g., 'I am a photographer who hates crowds and loves hidden indie cafes.'"
    )

    @model_validator(mode='after')
    def assign_budget_bin(self) -> 'UserPreference':
        if self.daily_budget is not None:
            if self.daily_budget < 50.0:
                self.budget_level = BudgetLevel.BUDGET
            elif self.daily_budget <= 150.0:
                self.budget_level = BudgetLevel.STANDARD
            else:
                self.budget_level = BudgetLevel.LUXURY
        return self


# 1. Flattened Address for pristine data ingestion
class Address(BaseModel):
    street_name: str
    province: str
    city: str
    nation: str = "Vietnam"

class Product(BaseModel):
    id: str
    price: float
    product_name: str

class ContactInfo(BaseModel):
    phone_number: str
    fanpage: Optional[HttpUrl] = None
    website: Optional[HttpUrl] = None

# 2. The Core Aggregate Root
class POI(BaseModel):
    id: str
    name: str
    poi_categories: List[Category]
    tag: Tag
    longitude: float
    latitude: float
    address: Address
    contact_info: Optional[ContactInfo] = None
    
    # 3. Dissolved the "Other" class into direct properties
    operation_time: str
    rating: Optional[Dict] = None
    menu: List[Product] = Field(default_factory=list)

class Description(BaseModel):
    # Except the faq, all attritbutes are doc's id in vector database
    poi_id: str
    review_id: str 
    summary_id: str
    seo_doc_id: str
    faq: Dict

class Stop(BaseModel):
    poi_id: str  # Reference to the POI node
    image: str # image url
    date: datetime
    description: str # AI Generated to describe the activities
    visit_time: datetime
    end_visit_time: datetime
    budget: float

class Itinerary(BaseModel):
    id: str
    start_poi_id: str  # Converted to reference for consistency
    end_poi_id: str    # Converted to reference for consistency
    stops: List[Stop]