import random
import os

from crawl4ai import BrowserConfig
from dotenv import load_dotenv

from dataclasses import dataclass, field, replace
from typing import List, Literal, Optional

load_dotenv()

@dataclass
class CrawlerGlobalConfig:
    max_depth: int = 4
    max_pages: int = 100
    headless: bool = False
    use_embedding: bool = False
    h = random.choice([768, 900, 864, 1080])
    w = random.choice([1366, 1440, 1536, 1920])
    store_destination: Literal["db", "local"] = "local"
    user_agent: str ="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    browser_config: BrowserConfig = field(default_factory=lambda: BrowserConfig(
        headless=False, # Will be overridden by 'headless' field logic if needed
        viewport_width=random.choice([1366, 1440, 1536, 1920]),
        viewport_height=random.choice([768, 900, 864, 1080]),
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        verbose=True,
        # enable_stealth=True, # Note: Verify if your version of crawl4ai supports this param in __init__
        extra_args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--disable-infobars",
            "--start-maximized",
            "--disable-popup-blocking",
        ]
    )
)
    
    # Từ khóa lọc rác dùng chung (Global Blacklist/Whitelist)
    global_keywords: List[str] = field(default_factory=lambda: [
        "*/vi-vn/*", "*vietnam*", "*viet-nam*", "*destinations*",
        "*destination*", "*tour*", "*travel*", "*guide*",
        "*activity*", "*activities*", "*attraction*", "*attractions*",
        "*/viet nam/*", "*/viet nam/*", "*/du-lich/*"
    ])