from pydantic import BaseModel
from typing import Tuple, List
from datetime import datetime

class Stop(BaseModel):
    poi_id: str
    date: datetime
    description: str
    end_time: datetime
    visit_time: datetime
    budget: float


class Itinerary(BaseModel):
    id: str
    start_place: str
    end_place: str
    stops: List[Stop]
