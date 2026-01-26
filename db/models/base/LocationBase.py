from pydantic import Field
from BaseEntity import BaseEntity
from typing import List, Optional

class LocationBase(BaseEntity):
    name: str
    province: str
    description: Optional[str] = None
