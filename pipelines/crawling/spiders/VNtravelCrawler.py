import urllib.parse
from typing import List, Optional, Dict
from pipelines.crawling.base.PipelineBase import BasePipelineCrawler, logger
from crawl4ai import CrawlerRunConfig, CacheMode
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy


class VNTravelCrawler(BasePipelineCrawler):
    def __init__(self, place_name: str, city_data: Dict = None, **kwargs):
        super().__init__(**kwargs)
        self.place_name = place_name
        self.city_data = city_data or {}
        self.webpage_name = "vntravel"
        self.lang_code = "vi"
        self.results_data = []
        self.browser_cfg.user_data_dir = None
        self.browser_cfg.user_agent = None
        self.browser_cfg.enable_stealth = True

    def get_domain_name(self) -> str:
        return self.webpage_name

    def get_css_selectors(self) -> List[str]:
        # Selector cho nội dung bài viết trên vntravel.org.vn
        return [
            '.detail-content',
            '.content_detail',
            'h1.title-detail',
            '.sapo_detail',
            '#main-content'
        ]

    def get_place_patterns(self) -> List[str]:
        return [
            "*/news/*",
            "*/chi-tiet/*",
            "*/trai-nghiem/*",
            "*.html"
        ]

    def get_pagination_patterns(self) -> List[str]:
        return ["*p=*", "*page=*"]

    def get_specific_keywords(self) -> List[str]:
        return [self.place_name, "du lịch", "khám phá", "ẩm thực", "kinh nghiệm", "trải nghiệm"]

    def get_excluded_selectors(self) -> List[str]:
        return [
            ".header", ".footer", ".sidebar", ".related-news",
            ".comment-box", ".banner", ".menu-mobile"
        ]

    def get_url_filter_patterns(self) -> List[str]:
        return self.get_place_patterns() + self.get_pagination_patterns()

    def create_run_config(self, strategy, md_generator) -> CrawlerRunConfig:
        return CrawlerRunConfig(
            deep_crawl_strategy=strategy,
            markdown_generator=md_generator,
            scraping_strategy=LXMLWebScrapingStrategy(),
            word_count_threshold=20,
            excluded_tags=['form', 'header', 'footer', 'nav', 'icon', 'svg'],
            exclude_external_links=True,
            excluded_selector=", ".join(self.get_excluded_selectors()),
            exclude_social_media_links=True,
            magic=True,
            verbose=True,
            delay_before_return_html=2.0,
            wait_until="domcontentloaded",
            scan_full_page=True,
            cache_mode=CacheMode.ENABLED,
        )

    async def execute(self, start_url: str, output_folder: str = "./data"):
        base_search_url = "https://vntravel.org.vn/tim-kiem.html"
        params = {
            "keyword": self.place_name,
            # "c": "news" # Nếu muốn lọc
        }
        query_string = urllib.parse.urlencode(params)
        search_url = f"{base_search_url}?{query_string}"

        logger.info(f"Generated Search URL for {self.place_name}: {search_url}")
        return await super().execute(search_url, output_folder)