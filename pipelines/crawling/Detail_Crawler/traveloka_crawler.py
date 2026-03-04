from typing import Callable, List, Optional, Callable, Tuple

from crawl4ai import DefaultMarkdownGenerator

from playwright.async_api import Page, BrowserContext

from config.settings import LoadPipelineSetting
from config.exceptions import IntentedNotImplementedException
from pipelines.crawling.base.detail_crawler import BaseDetailCrawler
from utils.LoadExtraction import LoadExtractionScript

class TravelokaCrawler(BaseDetailCrawler):
    def __init__(self, cfg: LoadPipelineSetting,
                 markdown_creator: Optional[DefaultMarkdownGenerator] = None):
    
        super().__init__(cfg, markdown_creator=markdown_creator)
        extract_cfg = cfg.extractor_cfg
        extract_cfg.set_domain(self.get_domain_name())
        
        
    def get_domain_name(self) -> str: return "traveloka"

    @staticmethod
    async def _goto_home(page: Page, context:BrowserContext, url:str, **kwagrs):
        print("[HOOK] Go to home page to load session cookie.")
        await page.goto("https://www.traveloka.com/vi-vn", wait_until="networkidle")
        print("[HOOK] Successfully to home page.")
        return page

    def get_hook(self) -> Tuple[Callable, str]:
        return self._goto_home, "before_goto"
    
    def _load_extractor(self, crawl_type:str):
        # TODO: Implement extractor for Hotel and Blog
        extractor = None

        if crawl_type == "hotel":
            raise IntentedNotImplementedException("Hotel extractor hasn't been implemented yet.")
        elif crawl_type == "destinations":
            extractor = LoadExtractionScript(self.cfg.extractor_cfg, name=crawl_type)
        elif crawl_type == "activities":
            extractor = LoadExtractionScript(self.cfg.extractor_cfg, name=crawl_type)
        elif crawl_type == "explore":
            raise IntentedNotImplementedException("Blog extractor hasn't been implemented yet.")

        if extractor:
            self.schemas = extractor.load_schema()
            self.cfg.crawler_cfg.run_cfg.js_code = extractor.load_js()
            if self.schemas or self.cfg.crawler_cfg.run_cfg.js_code:
                self.logger.info("Successfully load extractor.")
                return
            self.logger.warning("No schema nor js has found")
            return

        self.logger.info("No valid extractor has found. Run without extractor...")

    async def crawl_with_schema(self, url: str | List[str], verbose: bool = True, crawl_type="activities"):
        self._load_extractor(crawl_type=crawl_type)
        results = await super().crawl_with_schema(url, verbose)
        return results
