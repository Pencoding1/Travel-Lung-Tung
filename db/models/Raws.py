from abc import ABC, abstractmethod
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, HttpUrl, field_validator
from ...utils.datachef import ImageProcessor
from datetime import datetime

class RawTripInfo(BaseModel):
    id: str = Field(..., alias="ID")
    title: str
    summary: str
    raw_text: str
    doc_type: Literal["pdf", "doc", "html"]
    images: List[str] = Field(default_factory=list)
    source_url: HttpUrl = Field(..., alias="sourceUrl")
    crawled_at: datetime
    source_published_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def add_images(self, raw_bytes: bytes) -> None:
        b64_str = ImageProcessor.bytes_to_base64(raw_bytes)
        self.images.append(b64_str)

    def get_images_as_bytes(self) -> List[bytes]:
        return [ImageProcessor.base64_to_bytes(s) for s in self.images]