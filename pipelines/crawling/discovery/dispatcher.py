from .static_discovery import discover_static_urls
from .dynamic_discovery import discover_dynamic_urls
from utils.crawling_utils import is_dynamic_site

async def discover_urls(seed_url: str, domain: str) -> list[str]:
    if is_dynamic_site(seed_url):
        return await discover_dynamic_urls(seed_url, domain)
    else:
        return discover_static_urls(seed_url, domain)
