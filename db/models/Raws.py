from pydantic import Field
from datetime import datetime
from base.BaseEntity import BaseEntity
from utils.datachef import ImageProcessor
from typing import List, Literal, Dict, Any, Optional

class RawTripInfo(BaseEntity):
    id: str = Field(..., alias="ID")
    title: str
    summary: str
    raw_text: str
    doc_type: Literal["pdf", "doc", "html"]
    images: List[str] = Field(default_factory=list)
    images_url: List[str] = Field(default_factory=list)
    source_url: str = Field(..., alias="sourceUrl")
    crawled_at: datetime
    source_published_at: Optional[datetime]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def add_images(self, raw_bytes: bytes) -> None:
        b64_str = ImageProcessor.bytes_to_base64(raw_bytes)
        self.images.append(b64_str)

    def add_images_url(self, url:str) -> None:
        self.images.append(url)

    def get_images_as_bytes(self) -> List[bytes]:
        return [ImageProcessor.base64_to_bytes(s) for s in self.images]