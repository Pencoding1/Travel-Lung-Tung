import asyncio
import json
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import os
import logging
import fnmatch
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, DefaultMarkdownGenerator, CacheMode
from pipelines.crawling.utils import create_best_first_strategy, is_relevant
from pipelines.crawling.config import CrawlerGlobalConfig

# Setup Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('BaseCrawler')


class BasePipelineCrawler(ABC):
    def __init__(
            self,
            config: CrawlerGlobalConfig = CrawlerGlobalConfig(),
            logger=None
    ):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.cfg = config
        self.browser_cfg = self.cfg.to_browser_config()
        self.run_config = None
        self.results_data = []
        self.city_data = {}

    @abstractmethod
    def get_domain_name(self) -> str:
        pass

    @abstractmethod
    def get_css_selectors(self) -> List[str]:
        pass

    @abstractmethod
    def get_specific_keywords(self) -> List[str]:
        pass

    @abstractmethod
    def get_place_patterns(self) -> List[str]:
        pass

    def get_js_actions(self) -> Optional[str]:
        return None

    def get_excluded_selectors(self) -> List[str]:
        return []

    def _build_strategy(self):
        keywords = self.get_specific_keywords()
        max_depth = getattr(self.cfg, 'max_depth', 5)
        max_pages = getattr(self.cfg, 'max_pages', 10000)
        self.logger.info(f"Strategy Config -> Depth: {max_depth}, Max Pages: {max_pages}")

        return create_best_first_strategy(
            keywords=keywords,
            max_depth=max_depth,
            max_pages=max_pages
        )

    def create_run_config(self, strategy, md_generator) -> CrawlerRunConfig:
        js_execution = self.get_js_actions()
        return CrawlerRunConfig(
            deep_crawl_strategy=strategy,
            markdown_generator=md_generator,
            scraping_strategy=LXMLWebScrapingStrategy(),
            js_code=js_execution,
            word_count_threshold=10,
            excluded_tags=['form', 'header', 'footer', 'nav', 'icon', 'svg'],
            exclude_external_links=True,
            excluded_selector=", ".join(self.get_excluded_selectors()),
            exclude_social_media_links=True,
            magic=True,
            verbose=True,
            wait_for="js:() => document.readyState == 'complete'",
            wait_until="domcontentloaded",
            page_timeout=60000,
            delay_before_return_html=5.0,
            scan_full_page=True,
            cache_mode=CacheMode.BYPASS,
            mean_delay=2.0
        )

    def _generate_filename(self, stt: Any, ext: str) -> str:
        place = getattr(self, 'place_name', 'unknown').lower().replace(" ", "_")
        topic = getattr(self, 'topic_keyword', 'general_scan')
        domain = self.get_domain_name()
        lang = getattr(self, 'lang_code', 'vi')
        return f"{place}_{topic}_{domain}_{lang}_{stt}.{ext}"

    def _generate_list_filename(self) -> str:
        place = getattr(self, 'place_name', 'unknown').lower().replace(" ", "_")
        topic = getattr(self, 'topic_keyword', 'general_scan')
        domain = self.get_domain_name()
        lang = getattr(self, 'lang_code', 'vi')
        return f"{place}_{topic}_{domain}_{lang}_List.json"

    def save_item_to_disk(self, data: Dict, folder: str):
        domain = self.get_domain_name()
        place = getattr(self, 'place_name', 'general')
        path = os.path.join(folder, domain, place)
        os.makedirs(path, exist_ok=True)

        stt = len(self.results_data) + 1
        filename_md = self._generate_filename(stt, "md")
        file_path = os.path.join(path, filename_md)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(data['content'])

        meta = {
            "stt": stt,
            "filename": filename_md,
            "url": data.get("url"),
            "source": domain,
            "local_path": file_path
        }
        self.results_data.append(meta)
        print(f"Saved: {filename_md}")

    def save_metadata_json(self, output_folder: str):
        if not self.results_data:
            self.logger.warning("No data to save to JSON list.")
            return

        domain = self.get_domain_name()
        place = getattr(self, 'place_name', 'general')
        path = os.path.join(output_folder, domain, place)
        os.makedirs(path, exist_ok=True)

        json_filename = self._generate_list_filename()
        json_path = os.path.join(path, json_filename)

        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(self.results_data, f, ensure_ascii=False, indent=4)
            self.logger.info(f" Saved List JSON: {json_path}")
        except Exception as e:
            self.logger.error(f"Failed to save JSON list: {e}")

    def get_markdown_options(self) -> Dict[str, Any]:
        return {
            "css_selector": ", ".join(self.get_css_selectors()),
            "ignore_links": True,
            "ignore_images": False
        }

    async def execute(self, urls: List[str], output_folder: str = "./data"):
        logger.info(f"Starting crawl for {self.get_domain_name()}...")

        strategy = self._build_strategy()

        md_gen = DefaultMarkdownGenerator(
            content_source="body",
            options=self.get_markdown_options()
        )
        self.run_config = self.create_run_config(strategy, md_gen)

        async with AsyncWebCrawler(config=self.browser_cfg,
                                   run_config=self.run_config) as crawler:
            all_results = []

            for url in urls:
                if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                    self.logger.warning(f"Invalid URL skipped: {url}")
                    continue

                try:
                    results = await crawler.arun(url, config=self.run_config)
                    items_to_process = results if isinstance(results, list) else [results]
                    for item in items_to_process:
                        processed_data = self.process_item(item)
                        if not processed_data: continue
                        current_url = processed_data['url']
                        if "keyword=" in current_url or "page=" in current_url or "/tim-kiem" in current_url:
                            self.logger.info(f"Skipped seed/nav page: {current_url}")
                            continue
                        target_patterns = self.city_data.get("place_patterns", [])
                        is_target_url = False
                        if target_patterns:
                            is_target_url = any(fnmatch.fnmatch(current_url, pattern) for pattern in target_patterns)
                        should_save = False

                        if is_target_url:
                            self.logger.info(f" Golden Ticket matched (Config): {current_url}")
                            should_save = True
                        else:
                            if is_relevant(processed_data['content'], threshold=0.4):
                                self.logger.info(f" AI Content matched: {current_url}")
                                should_save = True
                            else:
                                self.logger.info(f"Skipped low relevance: {current_url}")
                        if should_save:
                            self.save_item_to_disk(processed_data, output_folder)
                    all_results.extend(results)
                except Exception as e:
                    self.logger.error(f"Error crawling {url}: {e}")

            self.save_metadata_json(output_folder)
            logger.info(f"Completed {self.get_domain_name()}. Total items: {len(self.results_data)}")
    def process_item(self, result):
        if not result.markdown or len(result.markdown) < 100:
            return None
        self.logger.info(f"Markdown length: {len(result.markdown)}")

        return {
            "url": result.url,
            "content": result.markdown
        }

