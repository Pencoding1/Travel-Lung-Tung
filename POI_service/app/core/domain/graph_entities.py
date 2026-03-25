import uuid
import re

from datetime import datetime
from typing import List, Optional, Dict
import phonenumbers
from pydantic import BaseModel, EmailStr, HttpUrl, Field, field_validator, model_validator

from app.core.domain.enum import BudgetLevel, TravelPace
from app.core.utils.helper import normalize_for_id



class Category(BaseModel):
    id: str = Field(..., min_length=1, description="Unique identifier for the category")
    name: str = Field(..., min_length=1, description="Display name of the category")
    context: str = Field(..., description="Semantic context for the AI agent")

    @field_validator('id', 'name')
    @classmethod
    def sanitize_basic_strings(cls, v: str) -> str:
        """Strips accidental leading/trailing whitespace."""
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Field cannot consist only of whitespace.")
        return cleaned

    @field_validator('context')
    @classmethod
    def validate_context(cls, v: str) -> str:
        """
        Cleans whitespace and strictly enforces the <400 word limit.
        """
        cleaned_context = re.sub(r'\s+', ' ', v).strip()
        
        if not cleaned_context:
            raise ValueError("Category context cannot be empty.")
            
        # Check word count by splitting on spaces
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


class Address(BaseModel):
    street_name: Optional[str] = None
    district: str = Field(..., min_length=1)
    ward: Optional[str] = None
    city: str = Field(..., min_length=1)
    nation: str = Field(default="Vietnam", min_length=1)

    @field_validator('street_name', 'district', 'ward', 'city', 'nation')
    @classmethod
    def sanitize_address_fields(cls, v: Optional[str]) -> Optional[str]:
        """
        Cleans all address strings. If the field is Optional and missing, it passes.
        """
        if not v:
            return v
            
        cleaned = re.sub(r'\s+', ' ', v).strip()
        
        if not cleaned:
            raise ValueError("Address fields cannot consist only of whitespace.")
            
        return cleaned.title()


class Product(BaseModel):
    id: str = Field(..., min_length=1, description="Unique identifier for the product")
    product_name: str = Field(..., min_length=1, max_length=200, description="Display name of the item")
    
    price: float = Field(..., ge=0.0, description="Price of the product in local currency")

    @field_validator('product_name')
    @classmethod
    def sanitize_product_name(cls, v: str) -> str:
        """
        Cleans up messy OTA data by stripping leading/trailing whitespace 
        and collapsing multiple internal spaces into a single space.
        """
        # "   Iced    Latte   " -> "Iced Latte"
        cleaned_name = re.sub(r'\s+', ' ', v).strip()
        
        if not cleaned_name:
            raise ValueError("Product name cannot consist only of whitespace.")
            
        return cleaned_name
        
    @field_validator('id')
    @classmethod
    def sanitize_id(cls, v: str) -> str:
        """Ensures the ID doesn't contain hidden whitespace."""
        cleaned_id = v.strip()
        if not cleaned_id:
             raise ValueError("Product ID cannot be empty or just whitespace.")
        return cleaned_id


class ContactInfo(BaseModel):
    # Required fields
    phone_number: str
    email: EmailStr | None = None
    
    # Optional fields
    fanpage: Optional[HttpUrl] = None
    website: Optional[HttpUrl] = None

    @field_validator('phone_number')
    @classmethod
    def validate_and_format_phone(cls, v: str) -> str:
        try:
            parsed_number = phonenumbers.parse(v, "VN")
            if not phonenumbers.is_valid_number(parsed_number):
                raise ValueError(f"'{v}' is not a valid phone number.")
            
            standardized_number = phonenumbers.format_number(
                parsed_number, 
                phonenumbers.PhoneNumberFormat.E164
            )
            return standardized_number
            
        except phonenumbers.NumberParseException as e:
            # Catch parsing errors (e.g., letters in the phone number, missing digits)
            raise ValueError(f"Failed to parse phone number '{v}': {str(e)}")
        
    @model_validator(mode='after')
    def ensure_data_exists(self) -> 'ContactInfo':
        # If ContactInfo is instantiated, it should have at least one valid field
        if not self.phone_number and not self.fanpage and not self.website:
            raise ValueError("ContactInfo cannot be empty; provide at least a phone number, fanpage, or website.")
        
        return self

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

    @model_validator(mode='after')
    def enforce_rules(self) -> 'POI':
        if not self.poi_categories:
            raise ValueError("POI must contain at least one Category in 'poi_categories'.")

        # 1. Resolve Primary Category
        primary_category = normalize_for_id(self.poi_categories[0].name)
        
        # 2. Resolve City (e.g., "Hồ Chí Minh" -> "HCMC")
        province = normalize_for_id(self.address.city, entity_type="city") 
        
        # 3. Resolve District using the resolved City as context
        # (e.g., passes "Quận 1" and "HCMC" -> returns "D1")
        district = normalize_for_id(
            self.address.district, 
            entity_type="district", 
            context_city=province
        )
        
        id_parts = [primary_category, province, district]
        
        if self.address.street_name:
            street_id = normalize_for_id(self.address.street_name)
            if street_id: # Only append if it's a valid string
                id_parts.append(street_id)
            
        creation_date = datetime.now().strftime("%Y%m%d")
        id_parts.append(creation_date)
        
        # Filter out any empty strings or Nones before joining!
        valid_parts = [str(part) for part in id_parts if part]
        expected_prefix = "_".join(valid_parts)
        
        # 5. UUID generation/reconciliation
        if not self.id:
            short_uuid = str(uuid.uuid4()).split('-')[0]
            self.id = f"{expected_prefix}_{short_uuid}"
        elif not self.id.startswith(expected_prefix):
            existing_suffix = self.id.split('_')[-1]
            self.id = f"{expected_prefix}_{existing_suffix}"

        return self


class Description(BaseModel):
    # Except the faq, all attritbutes are doc's id in vector database
    poi_id: str
    review_id: str 
    summary_id: str
    seo_doc_id: str
    faq: Dict
