from pydantic import BaseModel
from typing import List
from app.core.domain.Stops import Stop

class Itinerary(BaseModel):
    id: str
    start_poi_id: str  # Converted to reference for consistency
    end_poi_id: str    # Converted to reference for consistency
    stops: List[Stop]