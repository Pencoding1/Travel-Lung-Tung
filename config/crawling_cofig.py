import random
from dataclasses import dataclass, field
from typing import List
from crawl4ai import BrowserConfig


@dataclass
class CrawlerGlobalConfig:
    headless: bool = False
    max_depth: int = 4
    max_pages: int = 100
    w = random.choice([1366, 1440, 1536, 1920])
    h = random.choice([768, 900, 864, 1080])
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    # Từ khóa lọc rác dùng chung (Global Blacklist/Whitelist)
    global_keywords: List[str] = field(default_factory=lambda: [
        "*/vi-vn/*", "*vietnam*", "*viet-nam*", "*destinations*",
        "*destination*", "*tour*", "*travel*", "*guide*",
        "*activity*", "*activities*", "*attraction*", "*attractions*",
        "*/viet nam/*", "*/viet nam/*", "*/du-lich/*"
    ])


    def to_browser_config(self) -> BrowserConfig:
        return BrowserConfig(
            headless=self.headless,
            viewport_width=self.w,
            viewport_height=self.h,
            user_agent=self.user_agent,
            verbose=True,
            enable_stealth=True,
            extra_args=["--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-gpu",
                        "--disable-dev-shm-usage",
                        "--disable-extensions",
                        "--disable-infobars",
                        "--disable-blink-features=AutomationControlled",
                        "--start-maximized",
                        "--disable-popup-blocking",
                        ]
        )