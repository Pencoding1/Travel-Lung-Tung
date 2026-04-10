from app.core.domain.enum import BudgetLevel, TravelPace

from pydantic import BaseModel, HttpUrl, Field, model_validator
from typing import List, Optional, Dict
from datetime import datetime


class Stop(BaseModel):
    poi_id: str  # Reference to the POI node
    image: str # image url
    date: datetime
    description: str # AI Generated to describe the activities
    visit_time: datetime
    end_visit_time: datetime
    budget: float