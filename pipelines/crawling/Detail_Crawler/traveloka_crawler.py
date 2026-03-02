from typing import Callable, List, Optional, Tuple
import json
from markdownify import markdownify as md
from crawl4ai import CrawlerRunConfig, DefaultMarkdownGenerator, BrowserConfig
from playwright.async_api import Page, BrowserContext

from config.crawling_cofig import CrawlerGlobalConfig
from config.exceptions import IntentedNotImplementedException
from pipelines.crawling.base.detail_crawler import BaseDetailCrawler
from pipelines.crawling.extractors.guide import GuideExtractor
from pipelines.crawling.extractors.tour import TourExtractor
from pipelines.crawling.extractors.blog import BlogExtractor
from config.crawling_cofig import ExtractorConfig


class TravelokaCrawler(BaseDetailCrawler):
    def __init__(self, cfg: Optional[CrawlerGlobalConfig] = None,
                 crawler_config: Optional[CrawlerRunConfig] = None,
                 markdown_creator: Optional[DefaultMarkdownGenerator] = None,
                 browser_config: Optional[BrowserConfig] = None,
                 extractor_config: Optional[ExtractorConfig] = None):
        super().__init__(cfg, crawler_config, markdown_creator, browser_config)

        extract_cfg = extractor_config if extractor_config else ExtractorConfig()
        extract_cfg.set_domain(self.get_domain_name())

        self.tour_extractor = TourExtractor(extract_cfg)
        self.guide_extractor = GuideExtractor(extract_cfg)
        self.blog_extractor = BlogExtractor(extract_cfg)

    def get_domain_name(self) -> str:
        return "traveloka"

    @staticmethod
    async def _goto_home(page: Page, context: BrowserContext, url: str, **kwagrs):
        print("[HOOK] Go to home page to load session cookie.")
        await page.goto("https://www.traveloka.com/vi-vn", wait_until="networkidle")
        print("[HOOK] Successfully to home page.")
        return page

    def get_hook(self) -> Tuple[Callable, str]:
        return self._goto_home, "before_goto"

    def _load_extractor(self, crawl_type: str, js_files: List[str]):
        if crawl_type == "tour":
            self.schemas = self.tour_extractor.load_schema()
            self.crawler_config.js_code = self.tour_extractor.load_js(js_files)
        elif crawl_type == "guide":
            self.schemas = self.guide_extractor.load_schema()
            self.crawler_config.js_code = self.guide_extractor.load_js(js_files)
        elif crawl_type == "blog":
            self.schemas = self.blog_extractor.load_schema()
            self.crawler_config.js_code = self.blog_extractor.load_js(js_files)
        else:
            raise ValueError(f"Loại cào dữ liệu không hợp lệ: {crawl_type}")

    async def crawl_with_schema(self, url: str | List[str], crawl_type: str = "tour", js_files: List[str] = None,
                                verbose: bool = True):
        if js_files is None:
            if crawl_type == "tour":
                js_files = ["tour_modal_extractor.js"]
            elif crawl_type == "guide":
                js_files = ["guide_modal_extractor.js"]
            elif crawl_type == "blog":
                js_files = ["blog_modal_extractor.js"]

        self._load_extractor(crawl_type, js_files)
        results = await super().crawl_with_schema(url, verbose)
        self.results = results
        return results

    def _clean_special_fields(self, data: dict) -> dict:
        if "Product_schema" in data and isinstance(data["Product_schema"], str):
            try:
                data["Product_schema"] = json.loads(data["Product_schema"])
            except Exception as e:
                self.logger.warning(f"Lỗi parse Product_schema: {e}")

        if "FAQ_json" in data and isinstance(data["FAQ_json"], str):
            try:
                data["FAQ_json"] = json.loads(data["FAQ_json"])
            except Exception as e:
                self.logger.warning(f"Lỗi parse FAQ_json: {e}")

        if "all_ticket_details" in data and isinstance(data["all_ticket_details"], str):
            try:
                data["all_ticket_details"] = json.loads(data["all_ticket_details"])
            except Exception as e:
                self.logger.warning(f"Lỗi parse all_ticket_details: {e}")

        if "things_to_know" in data and isinstance(data["things_to_know"], str):
            try:
                raw_html = data["things_to_know"]
                markdown_text = md(raw_html, heading_style="ATX")
                cleaned_md = "\n".join([line for line in markdown_text.splitlines() if line.strip() != ""])
                data["things_to_know"] = cleaned_md
            except Exception as e:
                self.logger.warning(f"Lỗi convert things_to_know sang Markdown: {e}")

        return data

    def return_in_json(self):
        if not hasattr(self, "results") or not self.results:
            return json.dumps({"error": "No crawl results available."}, indent=4, ensure_ascii=False)

        if not self.results.extracted_content:
            return json.dumps({"error": "No extracted content available."}, indent=4, ensure_ascii=False)

        try:
            content = self.results.extracted_content

            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except json.JSONDecodeError:
                    return json.dumps({"error": "Invalid JSON string."}, indent=4, ensure_ascii=False)

            def process_item(item):
                if not isinstance(item, dict):
                    return item
                if "parsed_blog_data" in item:
                    raw_data = item.pop("parsed_blog_data", None)
                    if raw_data:
                        try:
                            parsed_obj = self.blog_extractor.parse_clean(raw_data)
                            item["blog_data"] = parsed_obj
                        except IntentedNotImplementedException:
                            item["warning"] = "Blog Parser wasn't implemented."
                            item["parsed_blog_data"] = raw_data
                        except Exception as e:
                            item["error"] = f"Blog Parse Error: {str(e)}"
                            item["parsed_blog_data"] = raw_data

                elif "parsed_destination_data" in item:
                    raw_data = item.pop("parsed_destination_data", None)
                    if raw_data:
                        try:
                            parsed_obj = self.guide_extractor.parse_clean(raw_data)
                            item["destination_data"] = parsed_obj
                        except IntentedNotImplementedException:
                            item["warning"] = "Guide Parser wasn't implemented."
                            item["parsed_destination_data"] = raw_data
                        except Exception as e:
                            item["error"] = f"Guide Parse Error: {str(e)}"
                            item["parsed_destination_data"] = raw_data

                else:
                    try:
                        item = self._clean_special_fields(item)
                    except IntentedNotImplementedException:
                        item["warning"] = "Tour Parser wasn't implemented."
                    except Exception as e:
                        item["error"] = f"Tour Clean Error: {str(e)}"

                return item

            if isinstance(content, list):
                content = [process_item(item) for item in content]
            elif isinstance(content, dict):
                content = process_item(content)

            return json.dumps(content, indent=4, ensure_ascii=False)

        except Exception as e:
            return json.dumps({"error": f"Unexpected error: {str(e)}"}, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    import asyncio


    async def test():
        from crawl4ai import CrawlResult

        START_URL = "https://www.traveloka.com/vi-vn/explore/destination/bao-tang-o-thanh-pho-ho-chi-minh/258818"

        CRAWL_TARGET = "blog"

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

        crawler = TravelokaCrawler(crawler_config=crawler_config)  # type: ignore
        # 1. Run the crawler
        results: CrawlResult = await crawler.crawl_with_schema(START_URL, crawl_type=CRAWL_TARGET)  # type: ignore
        if results is not None and results.success:
            try:
                # if isinstance(results.extracted_content, str):
                #    data = json.loads(results.extracted_content)
                # else:
                #    data = results.extracted_content

                processed_json_string = crawler.return_in_json()

                # Ghi thẳng chuỗi JSON đã được làm sạch ra file (dùng f.write vì nó đã là string)
                with open("./test_extraction.json", "w", encoding="utf-8") as f:
                    f.write(processed_json_string)

                print("Extraction successful! Saved to test_extraction.json")

            except Exception as e:
                print(f"Error processing extracted content: {e}")
        else:
            print(f"Crawl failed: {results.error_message}")

asyncio.run(test())