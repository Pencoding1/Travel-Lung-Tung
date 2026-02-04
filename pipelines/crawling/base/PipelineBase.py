# FILE: pipelines/crawling/base/base.py
import asyncio
from abc import ABC, abstractmethod
from typing import List, Optional, Dict
import os
import logging
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, DefaultMarkdownGenerator, CacheMode
from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
from crawl4ai.deep_crawling.filters import FilterChain, URLPatternFilter
from pygments.lexer import combined

# Import Config từ file bên ngoài
from pipelines.crawling.config import CrawlerGlobalConfig

# Setup Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('BaseCrawler')


class BasePipelineCrawler(ABC):
    def __init__(self, config: CrawlerGlobalConfig = CrawlerGlobalConfig()):
        # Dependency Injection: Nhận config từ ngoài vào
        self.cfg = config
        self.browser_cfg = self.cfg.to_browser_config()
        self.run_config = None

    # --- ABSTRACT METHODS (CON PHẢI LÀM) ---
    #domain
    @abstractmethod
    def get_domain_name(self) -> str:
        pass

    #css selectors
    @abstractmethod
    def get_css_selectors(self) -> List[str]:
        pass


    @abstractmethod
    def get_specific_keywords(self) -> List[str]:
        pass

    @abstractmethod
    def get_place_patterns(self) -> List[str]:
        pass

    def get_js_action(self) ->Optional[str]:
        return None

    def get_excluded_selectors(self) -> List[str]:
        return []

    # --- TEMPLATE METHOD (CORE LOGIC) ---
    def _build_strategy(self):

        #specific_patterns = self.get_place_patterns()
        combined_keywords = self.cfg.global_keywords + self.get_specific_keywords()
        combined_patterns = self.get_place_patterns() + self.cfg.global_keywords

        scorer = KeywordRelevanceScorer(keywords=combined_keywords, weight=0.8)
        filters = FilterChain([URLPatternFilter(patterns=combined_patterns)])

        return BestFirstCrawlingStrategy(
            max_depth=self.cfg.max_depth,
            filter_chain=filters,
            url_scorer=scorer,
            max_pages=self.cfg.max_pages,
            include_external=False
        )

    async def execute(self, start_url: str, output_folder: str = "./data"):
        logger.info(f"Starting crawl for {self.get_domain_name()}...")

        strategy = self._build_strategy()
        # Generator markdown (có thể tách ra nếu cần custom sâu hơn)
        md_gen = DefaultMarkdownGenerator(
            content_source="body",
            options={
                "css_selector": ", ".join(self.get_css_selectors()),
                "ignore_links": False,
                "ignore_images": True
            }
        )

        self.run_config = CrawlerRunConfig(
            deep_crawl_strategy=strategy,
            markdown_generator=md_gen,
            word_count_threshold=10,
            excluded_tags=['form', 'header', 'footer', 'nav','icon','svg'],
            exclude_external_links=True,
            excluded_selector=", ".join(self.get_excluded_selectors()),
            exclude_social_media_links=True,
            magic=True,
            verbose=True,
            wait_for="js:() => document.readyState == 'complete'",
            wait_until="domcontentloaded",
            delay_before_return_html=5.0,
            scan_full_page=True,
            cache_mode=CacheMode.BYPASS,

        )

        results_data = []
        async with AsyncWebCrawler(config=self.browser_cfg) as crawler:
            if not self.cfg.headless:
                await asyncio.sleep(10)
            results = await crawler.arun(start_url, config=self.run_config)

            for res in results:
                if res.success:
                    processed = self.process_item(res)
                    if processed:
                        self.save_item_to_disk(processed, output_folder)
                        results_data.append(processed)

        logger.info(f"✅ Completed {self.get_domain_name()}. Total items: {len(results_data)}")

    def process_item(self, result) -> Optional[Dict]:
        if not result.markdown or len(result.markdown) < 200: return None
        return {
            "url": result.url,
            "content": result.markdown,
            "source": self.get_domain_name()
        }

    def save_item_to_disk(self, data: Dict, folder: str):
        path = os.path.join(folder, self.get_domain_name())
        os.makedirs(path, exist_ok=True)
        safe_name = data['url'].split('/')[-1][-30:].replace("?", "_")  # Simple sanitize
        filename = f"{path}/{safe_name}.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(data['content'])
        print(f"Saved: {filename}")


