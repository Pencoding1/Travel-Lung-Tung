from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin

def discover_static_urls(seed_url: str, domain: str) -> list[str]:
    html = requests.get(seed_url, timeout=10).text
    soup = BeautifulSoup(html, "html.parser")

    urls = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(seed_url, a["href"]) # type:ignore
        if domain in href:
            urls.add(href)

    return list(urls)
