from dataclasses import dataclass, field
from typing import List
from crawl4ai import BrowserConfig


@dataclass
class CrawlerGlobalConfig:
    headless: bool = False
    viewport_width: int = 1920
    viewport_height: int = 1080
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    # Từ khóa lọc rác dùng chung (Global Blacklist/Whitelist)
    global_keywords: List[str] = field(default_factory=lambda: [
        "*/vi-vn/*", "*vietnam*", "*viet-nam*", "*destinations*",
        "*destination*", "*tour*", "*travel*", "*guide*",
        "*activity*", "*activities*", "*attraction*", "*attractions*",
        "*/viet nam/*", "*/viet nam/*"
    ])

    max_depth: int = 3
    max_pages: int = 100

    def to_browser_config(self) -> BrowserConfig:
        return BrowserConfig(
            headless=self.headless,
            viewport_width=self.viewport_width,
            viewport_height=self.viewport_height,
            user_agent=self.user_agent,
            verbose=True,
            enable_stealth=True,
            extra_args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )