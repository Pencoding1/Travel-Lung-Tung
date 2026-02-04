# FILE: pipelines/crawling/spiders/VietnamCoracleCrawler.py
import os
from typing import List, Optional, Dict, Any

# Import các thư viện cần thiết để override config
from crawl4ai import CrawlerRunConfig, CacheMode
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy  # Để bypass Verify
from pipelines.crawling.base.PipelineBase import BasePipelineCrawler


class VietnamCoracleCrawler(BasePipelineCrawler):
    def __init__(self, place_name: str, city_data: Dict = None, **kwargs):
        super().__init__(**kwargs)

        # 1. Cấu hình Session riêng (giữ nguyên logic của bạn)
        session_id = "vietnamcoracle_session_2354"
        user_data_path = os.path.abspath(os.path.join("./user_data", session_id))
        os.makedirs(user_data_path, exist_ok=True)
        # Override Browser Config
        self.browser_cfg.user_data_dir = None
        self.browser_cfg.user_agent = None
        self.browser_cfg.extra_args = []
        self.lang_code = "en"
        self.place_name = place_name
        self.city_data = city_data or {}
        self.webpage_name = "vietnamcoracle"
        self.results_data = []

    # --- CÁC HÀM GETTER CƠ BẢN (GIỮ NGUYÊN) ---
    def get_domain_name(self) -> str: return self.webpage_name

    def get_css_selectors(self) -> List[str]:
        return ['.entry-content', '.post-content', 'article.post', '.entry-inner', '#content']

    def get_place_patterns(self) -> List[str]:
        if "place_patterns" in self.city_data:
            return self.city_data["place_patterns"]
        slug = self.place_name.lower().replace(" ", "-")
        return [f"*{slug}*", "*/category/vietnam/*"]

    def get_specific_keywords(self) -> List[str]:
        return [self.place_name, "guide", "review", "travel", "motorcycle", "stay", ""]

    def get_excluded_selectors(self) -> List[str]:
        return [".sidebar", "#comments", ".author-bio", ".sharedaddy", ".jp-relatedposts", ".footer-widgets",
                "header.entry-header"]

    def get_js_action(self) -> Optional[str]:
        return """
        async () => {
            window.scrollBy(0, 800); await new Promise(r => setTimeout(r, 1000)); 
            window.scrollBy(0, 800); await new Promise(r => setTimeout(r, 1500));
            window.scrollTo(0, document.body.scrollHeight); await new Promise(r => setTimeout(r, 1000));
        };
        """

    # --- QUAN TRỌNG: OVERRIDE CÁC HOOK ĐỂ TÙY BIẾN HÀNH VI ---

    def get_url_filter_patterns(self) -> List[str]:
        """
        Override: Chỉ lọc URL theo địa điểm (HCM/Saigon).
        LOẠI BỎ `self.cfg.global_keywords` khỏi bộ lọc để tránh cào lan man.
        """
        return self.get_place_patterns()

    def create_run_config(self, strategy, md_generator) -> CrawlerRunConfig:
        """
        Override:LXMLWebScrapingStrategy và cấu hình delay riêng.
        """
        return CrawlerRunConfig(
            deep_crawl_strategy=strategy,
            markdown_generator=md_generator,

            # Dùng LXML để tránh bị phát hiện bot và parse nhanh hơn
            scraping_strategy=LXMLWebScrapingStrategy(),

            word_count_threshold=10,
            excluded_tags=['form', 'header', 'footer', 'nav', 'icon', 'svg'],
            exclude_external_links=True,
            excluded_selector=", ".join(self.get_excluded_selectors()),
            exclude_social_media_links=True,
            magic=True,
            verbose=True,

            # Cấu hình thời gian chờ
            wait_for_timeout=2,  # Giây (integer)
            wait_until="networkidle",
            delay_before_return_html=3.0,

            # Scroll & Cache
            scan_full_page=True,
            cache_mode=CacheMode.ENABLED,  # Bật cache
        )