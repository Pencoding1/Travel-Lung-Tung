from pydantic import BaseModel, HttpUrl, Field
from typing import List, Optional, Dict


class Description(BaseModel):
    # Except the faq, all attritbutes are doc's id in vector database
    poi_id: str
    review_id: str 
    summary_id: str
    seo_doc_id: str
    faq: Dict

class Category(BaseModel):
    id: str
    name: str
    context: str

class Tag(BaseModel):
    id: str
    name: str

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