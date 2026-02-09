from pydantic import Field
from datetime import datetime
from db.models.base.BaseEntity import BaseEntity
from typing import List, Literal, Dict, Any, Optional

class RawTripInfo(BaseEntity):
    id: str = Field(..., alias="ID")
    title: str
    summary: str
    raw_text: str
    doc_type: Literal["pdf", "doc", "html", "md", "lxml"]
    images_url: List[str] = Field(default_factory=list)
    source_url: str = Field(..., alias="sourceUrl")
    crawled_at: datetime
    source_published_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    