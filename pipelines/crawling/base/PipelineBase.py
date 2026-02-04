# FILE: pipelines/crawling/base/base.py
import asyncio
import json
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
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
        self.results_data = []

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

    def _generate_filename(self, stt: Any, ext: str) -> str:
        """Tạo tên file chuẩn hóa: {place}_{topic}_{domain}_{lang}_{stt}.{ext}"""
        place = getattr(self, 'place_name', 'unknown').lower().replace(" ", "_")
        topic = getattr(self, 'topic_keyword', 'general_scan')
        domain = self.get_domain_name()
        lang = getattr(self, 'lang_code', 'vi')  # Mặc định vi nếu không có

        return f"{place}_{topic}_{domain}_{lang}_{stt}.{ext}"

    def save_item_to_disk(self, data: Dict, folder: str):
        """Lưu nội dung Markdown và lưu vết vào results_data"""
        domain = self.get_domain_name()
        place = getattr(self, 'place_name', 'general')

        # Cấu trúc: folder/domain/place/
        path = os.path.join(folder, domain, place)
        os.makedirs(path, exist_ok=True)

        stt = len(self.results_data) + 1
        filename_md = self._generate_filename(stt, "md")

        file_path = os.path.join(path, filename_md)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(data['content'])

        # Lưu metadata để xuất file JSON summary sau này
        meta = {
            "stt": stt,
            "filename": filename_md,
            "url": data.get("url"),
            "source": domain,
            "local_path": file_path
        }
        self.results_data.append(meta)
        print(f"Saved: {filename_md}")

    async def execute(self, start_url: str, output_folder: str = "./data"):
        logger.info(f"Starting crawl for {self.get_domain_name()}...")
        strategy = self._build_strategy()
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


        async with AsyncWebCrawler(config=self.browser_cfg) as crawler:
            if not self.cfg.headless:
                await asyncio.sleep(10)
            results = await crawler.arun(start_url, config=self.run_config)
            for res in results:
                if res.success:
                    processed = self.process_item(res)
                    if processed:
                        self.save_item_to_disk(processed, output_folder)

            if self.results_data:
                summary_path = os.path.join(output_folder, "crawled_data", self.get_domain_name(),
                                            getattr(self, 'place_name', 'general'))
                os.makedirs(summary_path, exist_ok=True)

                summary_file = os.path.join(summary_path, self._generate_filename("List", "json"))
                with open(summary_file, "w", encoding="utf-8") as f:
                    json.dump(self.results_data, f, indent=4, ensure_ascii=False)
                logger.info(f"✅ Completed. Summary exported to: {summary_file}")

        logger.info(f"✅ Completed {self.get_domain_name()}. Total items: {len(self.results_data)}")

    def process_item(self, result) -> Optional[Dict]:
        if not result.markdown or len(result.markdown) < 200: return None
        return {
            "url": result.url,
            "content": result.markdown,
            "source": self.get_domain_name()
        }




