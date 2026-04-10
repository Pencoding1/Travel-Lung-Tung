from typing import List, Optional
from pydantic import BaseModel, Field

class CrawlPayload(BaseModel):
    discover: bool = Field(default=False)
    crawl_type: Optional[str] = Field(default=None)
    target_url: str
    target_urls: List[str]