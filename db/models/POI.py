from pydantic import BaseModel, HttpUrl, Field
from typing import List, Optional, Dict

class Category(BaseModel):
    id: str
    name: str


class Tag(BaseModel):
    id: str
    name: str


class Address(BaseModel):
    street_name: str
    ward: str
    district: str
    city: str
    nation: str = "Vietnam"


class Product(BaseModel):
    id: str
    price: float
    product_name: str


class ContactInfo(BaseModel):
    id: str
    phone_number: str
    Fanpage: Optional[HttpUrl] = Field(default=None)
    Website: Optional[HttpUrl] = Field(default=None)


class POI(BaseModel):
    id: str
    name: str
    poi_categories: List[Category]
    tag: Tag
    longitude: float
    latitude: float
    address: Address
    contract_info: Optional[ContactInfo] = Field(default=None)

    operation_time: str
    rating: Optional[Dict] = None
    menu: List[Product] = Field(default_factory=list)


class Description(BaseModel):
    poi_id: str
    review_id: str
    summary_id: str
    seo_doc_id: str
    FAQ: Dict
