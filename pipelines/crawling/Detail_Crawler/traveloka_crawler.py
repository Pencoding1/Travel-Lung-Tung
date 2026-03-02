from typing import Callable, List, Optional, Callable, Tuple

from crawl4ai import CrawlerRunConfig, DefaultMarkdownGenerator, BrowserConfig

from playwright.async_api import Page, BrowserContext

from config.crawling_cofig import CrawlerGlobalConfig
from config.exceptions import IntentedNotImplementedException
from pipelines.crawling.base.detail_crawler import BaseDetailCrawler
from pipelines.crawling.extractors.tour import TourExtractor
from config.crawling_cofig import ExtractorConfig

class TravelokaCrawler(BaseDetailCrawler):
    def __init__(self, cfg: Optional[CrawlerGlobalConfig] = None,
                 crawler_config: Optional[CrawlerRunConfig]= None,
                 markdown_creator: Optional[DefaultMarkdownGenerator] = None, 
                 browser_config: Optional[BrowserConfig] = None,
                 extractor_config: Optional[ExtractorConfig]=None):
        super().__init__(cfg, crawler_config, markdown_creator, browser_config)

        extract_cfg = extractor_config if extractor_config else ExtractorConfig()
        extract_cfg.set_domain(self.get_domain_name())
        
        self.tour_extractor = TourExtractor(extract_cfg)
        
    def get_domain_name(self) -> str: return "traveloka"

    @staticmethod
    async def _goto_home(page: Page, context:BrowserContext, url:str, **kwagrs):
        print("[HOOK] Go to home page to load session cookie.")
        await page.goto("https://www.traveloka.com/vi-vn", wait_until="networkidle")
        print("[HOOK] Successfully to home page.")
        return page

    def get_hook(self) -> Tuple[Callable, str]:
        return self._goto_home, "before_goto"
    
    def _load_extractor(self, name:List[str]=["tour_modal_extractor.js"]):
        self.schemas = self.tour_extractor.load_schema()
        self.crawler_config.js_code = self.tour_extractor.load_js(name)

    async def crawl_with_schema(self, url: str | List[str], verbose: bool = True):
        self._load_extractor()
        results = await super().crawl_with_schema(url, verbose)
        try:
            return self.tour_extractor.parse_clean(results) # thêm key nếu không muốn xử lý cả cục result cào
        except IntentedNotImplementedException:
            self.logger.warning("Parser wasn't implemented.")
            return results


if __name__ == "__main__":
    import asyncio
    async def test():
        import json
        from crawl4ai import CrawlResult
        START_URL = "https://www.traveloka.com/en-vn/activities/vietnam/product/sun-world-ba-den-mountain-4234684001188"
        
        crawler_config = CrawlerRunConfig(
            excluded_selector="div.articleTableOfContent",
            wait_for_timeout=7000,
            delay_before_return_html=10,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            magic=True,
            scan_full_page=True,
            scroll_delay=0.5,
            simulate_user=True,
            session_id="hn_"
        )

        crawler = TravelokaCrawler(crawler_config=crawler_config) # type: ignore
        # 1. Run the crawler 
        results:CrawlResult = await crawler.crawl_with_schema(START_URL) # type: ignore
        if results.success:
            try:
                if isinstance(results.extracted_content, str):
                    data = json.loads(results.extracted_content)
                else:
                    data = results.extracted_content

                with open("./test_extraction.json", 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                    
                print("Extraction successful! Saved to test_extraction.json")

            except Exception as e:
                    print(f"Error processing extracted content: {e}")
        else:
            print(f"Crawl failed: {results.error_message}")
    asyncio.run(test())