from typing import List
from pydantic import BaseModel

class CrawlPayload(BaseModel):
    target_url: str
    target_urls: List[str]