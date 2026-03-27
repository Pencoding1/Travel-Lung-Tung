import uuid
import re

from datetime import datetime
from typing import List, Optional, Dict, Any
import phonenumbers
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.domain.enum import BudgetLevel, TravelPace
from app.core.utils.helper import normalize_for_id


class Category(BaseModel):
    id: str = Field(..., min_length=1, description="Unique identifier for the category")
    name: str = Field(..., min_length=1, description="Display name of the category")
    context: str = Field(..., description="Semantic context for the AI agent")

    @field_validator('id', 'name')
    @classmethod
    def sanitize_basic_strings(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Field cannot consist only of whitespace.")
        return cleaned

    @field_validator('context')
    @classmethod
    def validate_context(cls, v: str) -> str:
        cleaned_context = re.sub(r'\s+', ' ', v).strip()
        if not cleaned_context:
            raise ValueError("Category context cannot be empty.")
            
        word_count = len(cleaned_context.split())
        if word_count >= 400:
            raise ValueError(f"Category context must be under 400 words. Current count: {word_count}.")
            
        return cleaned_context


class Tag(BaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)

    @field_validator('id', 'name')
    @classmethod
    def sanitize_tag_strings(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Tag fields cannot be empty or just whitespace.")
        return cleaned


class UserPreference(BaseModel):
    user_id: str
    category_weights: Dict[str, float] = Field(default_factory=dict)
    tag_weights: Dict[str, float] = Field(default_factory=dict)
    daily_budget: Optional[float] = Field(None, description="Exact target spending per day")
    budget_level: BudgetLevel = Field(
        default=BudgetLevel.STANDARD,
        description="The classified budget tier that dictates price filtering."
    )
    travel_pace: TravelPace = Field(
        default=TravelPace.MODERATE,
        description="The preferred speed of travel, dictating how long the user stays at each POI."
    )
    dietary_restrictions: List[str] = Field(default_factory=list)
    requires_accessibility: bool = False
    personal_vibe: Optional[str] = Field(None)

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


class Address(BaseModel):
    street_name: Optional[str] = None
    district: str = Field(..., min_length=1)
    ward: Optional[str] = None
    city: str = Field(..., min_length=1)
    nation: str = Field(default="Vietnam", min_length=1)

    @field_validator('street_name', 'district', 'ward', 'city', 'nation')
    @classmethod
    def sanitize_address_fields(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        cleaned = re.sub(r'\s+', ' ', v).strip()
        if not cleaned:
            raise ValueError("Address fields cannot consist only of whitespace.")
        return cleaned.title()


class Product(BaseModel):
    id: str = Field(..., min_length=1)
    product_name: str = Field(..., min_length=1, max_length=200)
    price: float = Field(..., ge=0.0)

    @field_validator('product_name')
    @classmethod
    def sanitize_product_name(cls, v: str) -> str:
        cleaned_name = re.sub(r'\s+', ' ', v).strip()
        if not cleaned_name:
            raise ValueError("Product name cannot consist only of whitespace.")
        return cleaned_name
        
    @field_validator('id')
    @classmethod
    def sanitize_id(cls, v: str) -> str:
        cleaned_id = v.strip()
        if not cleaned_id:
             raise ValueError("Product ID cannot be empty.")
        return cleaned_id


class ContactInfo(BaseModel):
    email: EmailStr | None = None
    phone_number: Optional[str] = None
    
    # FIX: Changed from HttpUrl to str to prevent crashes on bad data like "Imported from GIS"
    fanpage: Optional[str] = None
    website: Optional[str] = None

    # FIX: Added mode="before" to intercept None before phonenumbers tries to parse it
    @field_validator('phone_number', mode='before')
    @classmethod
    def validate_and_format_phone(cls, v: Optional[str]) -> Optional[str]:
        if not v or str(v).lower() == "none": 
            return None
            
        try:
            parsed_number = phonenumbers.parse(v, "VN")
            if not phonenumbers.is_valid_number(parsed_number):
                return None # Fail gracefully, keep the POI alive
            
            return phonenumbers.format_number(
                parsed_number, 
                phonenumbers.PhoneNumberFormat.E164
            )
        except Exception:
            # If it's a completely garbled string, just ignore it
            return None
            
    # FIX: Removed the ensure_data_exists model_validator! 
    # Sparse GIS data is fine, an empty ContactInfo object shouldn't crash the API.


class POI(BaseModel):
    id: str
    name: str
    poi_categories: List[Category] = Field(default_factory=list)
    tag: Optional[Tag] = None
    longitude: float
    latitude: float
    
    # FIX: Address is now entirely optional
    address: Optional[Address] = None
    contact_info: Optional[ContactInfo] = None
    
    # FIX: Operation time can be missing
    operation_time: Optional[str] = None
    rating: Optional[Dict] = None
    
    # FIX: Default factory for list
    menu: List[Product] = Field(default_factory=list)

    # FIX: Catches explicit `null` from JSON and turns it into []
    @field_validator("menu", mode="before")
    @classmethod
    def ensure_menu_is_list(cls, v):
        if v is None:
            return []
        return v

    @model_validator(mode='after')
    def enforce_rules(self) -> 'POI':
        primary_category = "UNCATEGORIZED"
        if self.poi_categories:
            primary_category = normalize_for_id(self.poi_categories[0].name)
        
        # FIX: Safe Address fallback logic so ID generation doesn't crash on None
        province = "UNKNOWN"
        district = "UNKNOWN"
        id_parts = [primary_category]
        
        if self.address:
            if getattr(self.address, 'city', None):
                province = normalize_for_id(self.address.city, entity_type="city") 
            if getattr(self.address, 'district', None):
                district = normalize_for_id(self.address.district, entity_type="district", context_city=province)
                
            id_parts.extend([province, district])
            
            if getattr(self.address, 'street_name', None):
                street_id = normalize_for_id(self.address.street_name) # type: ignore
                if street_id: 
                    id_parts.append(street_id)
        else:
            id_parts.extend([province, district])
            
        creation_date = datetime.now().strftime("%Y%m%d")
        id_parts.append(creation_date)
        
        valid_parts = [str(part) for part in id_parts if part]
        expected_prefix = "_".join(valid_parts)
        
        if not self.id:
            short_uuid = str(uuid.uuid4()).split('-')[0]
            self.id = f"{expected_prefix}_{short_uuid}"
        elif not self.id.startswith(expected_prefix):
            existing_suffix = self.id.split('_')[-1]
            self.id = f"{expected_prefix}_{existing_suffix}"

        return self


class Description(BaseModel):
    poi_id: str
    review_id: str 
    summary_id: str
    seo_doc_id: str
    faq: Dict

class POILite(BaseModel):
    id: str
    name: str
    full_address: Optional[str] = "Address not specified"
    categories: List[str] = []
    operation_time: Optional[str] = "Hours not specified"