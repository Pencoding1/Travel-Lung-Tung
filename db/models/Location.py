from base.LocationBase import LocationBase
from typing import Optional, List

class Location(LocationBase):
    """
    Class này dùng để chứa thêm các metadata enrich từ AI (ví dụ: vibe vector)
    """
    vibe_vector: Optional[List[float]] = None
    embedding_model: Optional[str] = None