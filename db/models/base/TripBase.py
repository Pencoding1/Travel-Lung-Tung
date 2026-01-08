from typing import List
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl, field_validator


class TripInfoBase(BaseModel):
    id: str = Field(..., alias="ID")
    province: str = Field(..., alias="Province")
    min_price: float = Field(ge=0)
    max_price: float = Field(ge=min_price)
    description: str = Field(default="")
    provider: str
    itinerary: List
    sub_trip: bool = Field(..., alias="subTrip")
    arrival_time: datetime = Field(..., alias="arrivalTime")
    departure_time: datetime = Field(..., alias="departureTime")
    vibe: str
