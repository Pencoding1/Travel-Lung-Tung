from typing import List, Dict, Any
from pydantic import BaseModel

chat_history: Dict[str, List[Dict[str, Any]]] = {}

class ChatRequest(BaseModel):
    session_id: str
    message: str

class ItineraryRequest(BaseModel):
    session_id: str
    current_city: str = "Ho Chi Minh City"
    travel_type: str  # e.g., "self-explore, relaxing, sightseeing"
    num_travelers: int
    start_date: str
    target_district: str
    duration_days: int
    budget_range: str
    user_description: str