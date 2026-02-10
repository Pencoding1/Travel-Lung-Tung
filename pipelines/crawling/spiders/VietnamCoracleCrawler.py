import logging
from typing import List, Optional, Dict, Any
import fnmatch
from crawl4ai import (
    AsyncWebCrawler,
    CrawlerRunConfig,
    CacheMode,
    LXMLWebScrapingStrategy,
    DefaultMarkdownGenerator,
    UndetectedAdapter,
)
from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy
from pipelines.crawling.base.PipelineBase import BasePipelineCrawler
from utils.crawling_utils import load_js, is_relevant

logger = logging.getLogger("VietnamCoracleCrawler")


class VietnamCoracleCrawler(BasePipelineCrawler):

    def __init__(self, place_name: str, city_data: Dict = {}, **kwargs):
        super().__init__(**kwargs)
        self.place_name = place_name
        self.city_data = city_data or {}
        self.webpage_name = "vietnamcoracle"
        self.lang_code = "en"
        self.browser_cfg.enable_stealth = True
        # Headless dễ bị antibot phát hiện — bắt buộc mở browser có giao diện cho site này
        self.browser_cfg.headless = False
        self.results_data = []

    def get_domain_name(self) -> str:
        return self.webpage_name

    def get_specific_keywords(self) -> List[str]:
        return [
            self.place_name,
            "guide", "review", "travel", "motorcycle", "stay",
            "browse", "destinations", "category", "tag"
        ]

    def get_css_selectors(self) -> List[str]:
        return [
            '.entry-content',
            '.post-content',
            '#content',
            '.site-main',
            '.archive',
            'article'
        ]

    def get_place_patterns(self) -> List[str]:
        target_patterns = []
        if "place_patterns" in self.city_data:
            target_patterns = self.city_data["place_patterns"]
        else:
            slug = self.place_name.lower().replace(" ", "-")
            target_patterns = [f"*{slug}*"]

        navigation_patterns = [
            "*/browse/*",
            "*/destinations/*",
            "*/category/*",
            "*/tag/*",
            "*/page/*",
            "*/topic/*"
        ]
        return target_patterns + navigation_patterns

    def get_js_actions(self) -> Optional[str]:
        return load_js()

    def create_run_config(self, strategy, md_generator) -> CrawlerRunConfig:
        return CrawlerRunConfig(
            deep_crawl_strategy=strategy,
            markdown_generator=md_generator,
            scraping_strategy=LXMLWebScrapingStrategy(),
            magic=True,
            js_code=self.get_js_actions(), # type: ignore
            wait_until="domcontentloaded",
            # Chờ lâu hơn để trang vượt verification (antibot)
            delay_before_return_html=15.0,
            page_timeout=90000,
            # Đợi đến khi có nội dung chính (tránh lấy trang "fail to verify")
            wait_for="js:() => document.querySelector('.entry-content, .post-content, #content, article') !== null || document.body.innerText.length > 500",
            excluded_tags=['form', 'header', 'footer', 'nav', 'icon', 'svg'],
            exclude_external_links=True,
            excluded_selector=", ".join(self.get_excluded_selectors()),
            exclude_social_media_links=True,
            cache_mode=CacheMode.BYPASS,
            verbose=True,
            mean_delay=3.0,
        )

    def use_semantic_filter(self) -> bool:
        return True

    def get_embedding_query(self) -> str:
        return f"Travel guide, road trip, experience in {self.place_name}"

    def get_excluded_selectors(self) -> List[str]:
        return [
            ".sidebar",
            "#comments",
            ".author-bio",
            ".sharedaddy",
            ".jp-relatedposts",
            ".footer-widgets",
        ]

    async def execute(self, urls: List[str], output_folder: str = "./data"):
        """Chạy crawl với UndetectedAdapter để vượt antibot 'fail to verify'."""
        logger.info("VietnamCoracleCrawler: starting with UndetectedAdapter (antibot bypass)...")

        strategy = self._build_strategy()
        md_gen = DefaultMarkdownGenerator(
            content_source="body",
            options=self.get_markdown_options()
        )
        self.run_config = self.create_run_config(strategy, md_gen)

        # UndetectedAdapter + AsyncPlaywrightCrawlerStrategy để giảm "fail to verify"
        undetected_adapter = UndetectedAdapter()
        crawler_strategy = AsyncPlaywrightCrawlerStrategy(
            browser_config=self.browser_cfg,
            browser_adapter=undetected_adapter
        )

        async with AsyncWebCrawler(
            crawler_strategy=crawler_strategy,
            config=self.browser_cfg,
            run_config=self.run_config,
        ) as crawler:
            for url in urls:
                if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                    self.logger.warning(f"Invalid URL skipped: {url}")
                    continue
                try:
                    results = await crawler.arun(url, config=self.run_config)
                    items_to_process = results if isinstance(results, list) else [results]
                    for item in items_to_process:
                        processed_data = self.process_item(item)
                        if not processed_data:
                            continue
                        current_url = processed_data["url"]
                        if "keyword=" in current_url or "page=" in current_url or "/tim-kiem" in current_url:
                            self.logger.info(f"Skipped seed/nav page: {current_url}")
                            continue
                        target_patterns = self.city_data.get("place_patterns", [])
                        is_target_url = bool(
                            target_patterns
                            and any(fnmatch.fnmatch(current_url, p) for p in target_patterns)
                        )
                        if is_target_url:
                            self.logger.info(f" Golden Ticket matched (Config): {current_url}")
                            self.save_item_to_disk(processed_data, output_folder)
                        elif is_relevant(processed_data["content"], threshold=0.4):
                            self.logger.info(f" AI Content matched: {current_url}")
                            self.save_item_to_disk(processed_data, output_folder)
                        else:
                            self.logger.info(f"Skipped low relevance: {current_url}")
                except Exception as e:
                    self.logger.error(f"Error crawling {url}: {e}")

        self.save_metadata_json(output_folder)
        logger.info(f"Completed {self.get_domain_name()}. Total items: {len(self.results_data)}")
