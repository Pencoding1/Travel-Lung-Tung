from typing import Callable, Optional, Callable, Tuple

from crawl4ai import CrawlerRunConfig, DefaultMarkdownGenerator, BrowserConfig

from playwright.async_api import Page, BrowserContext

from config.crawling_cofig import CrawlerGlobalConfig
from pipelines.crawling.base.detail_crawler import BaseDetailCrawler


class TravelokaCrawler(BaseDetailCrawler):
    def __init__(self, cfg: Optional[CrawlerGlobalConfig] = None,
                 crawler_config: Optional[CrawlerRunConfig]= None,
                 markdown_creator: Optional[DefaultMarkdownGenerator] = None, 
                 browser_config: Optional[BrowserConfig] = None):
        super().__init__(cfg, crawler_config, markdown_creator, browser_config)
    
    def get_domain_name(self) -> str: return "traveloka"

    @staticmethod
    async def _goto_home(page: Page, context:BrowserContext, url:str, **kwagrs):
        print("[HOOK] Go to home page to load session cookie.")
        await page.goto("https://www.traveloka.com/vi-vn", wait_until="networkidle")
        print("[HOOK] Successfully to home page.")
        return page

    def get_hook(self) -> Tuple[Callable, str]:
        return self._goto_home, "before_goto"
        

if __name__ == "__main__":
    import asyncio
    async def test():
        import json
        from crawl4ai import CrawlResult
        START_URL = "https://www.traveloka.com/en-vn/activities/vietnam/product/sun-world-ba-den-mountain-4234684001188"
        
        test_schema = {
                        "name": "Tour Content",       
                        "baseSelector": "html",
                        "fields": [                   
                            {
                                "name": "seo_article",
                                "selector": "div.seoArticleContent > div.css-1dbjc4n .r-13awgt0",
                                "type" : "html"
                            },
                            {
                                "name": "FAQ_json",
                                "selector": "#faq-section > div > script",
                                "type": "text"
                            },
                            {
                                "name": "Product_schema",
                                "selector": 'script[data-testid="product-schema"]',
                                "type": "text"
                            }
                        ]
        }
        
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
        results:CrawlResult = await crawler.crawl_with_schema(START_URL, schema_css=test_schema) # type: ignore
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