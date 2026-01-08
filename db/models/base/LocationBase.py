from pydantic import BaseModel, Field
from typing import List, Optional

class LocationBase(BaseModel):
    id: str
    name: str
    province: str
    description: Optional[str] = None
