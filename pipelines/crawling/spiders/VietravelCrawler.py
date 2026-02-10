import logging
from typing import List, Optional, Dict, Any
from pipelines.crawling.base.PipelineBase import BasePipelineCrawler
from utils.crawling_utils import load_js

logger = logging.getLogger("VietravelCrawler")


class VietravelCrawler(BasePipelineCrawler):
    def __init__(self, place_name: str, city_data: Dict = {}, **kwargs):
        super().__init__(**kwargs)
        self.place_name = place_name
        self.city_data = city_data or {}
        self.webpage_name = "vietravel"
        self.lang_code = "vi"
        self.browser_cfg.enable_stealth = True
        self.results_data = []

    def get_domain_name(self) -> str:
        return self.webpage_name

    def get_specific_keywords(self) -> List[str]:
        return [self.place_name, "dịch vụ", "tour", "khởi hành"]

    def get_css_selectors(self) -> List[str]:
        return [
            '.tour-introduction',
            '.tour-itinerary',
            '.content-news',
            '.box-common-content',
            '.tour-detail-info'
        ]

    def get_excluded_selectors(self) -> List[str]:
        return [
            "header", "footer", "nav", "aside",
            "script", "style", "iframe", "svg",
            ".btn-book-tour", ".hotline-fixed", ".footer-vtv", ".sidebar-tour",
            ".promoBanner", ".newsletter", ".breadcrumbs",
            ".ad", ".advertisement", ".sponsor", ".promo",
            "img[src*='icon']", "img[src*='logo']", "img[src*='badge']",
            "img[src*='sprite']", "img[src*='imageresource']", "img[src*='.svg']",
            ".ad img", ".advertisement img", ".sponsor img", ".promo img",
            "[class*='ad'] img", "[class*='sponsor'] img", "[class*='promo'] img",
            "[class*='icon'] img", "[class*='logo'] img", "[class*='badge'] img",
            "[class*='button'] img", "[class*='arrow'] img", "[class*='chevron'] img",
        ]

    def get_place_patterns(self) -> List[str]:
        if "place_patterns" in self.city_data:
            return self.city_data["place_patterns"]
        slug = self.place_name.lower().replace(" ", "-")
        return [
            f"*{slug}*",
            "*/tour/*",
            "*/du-lich/*",
            "*/tin-tuc-du-lich/*",
            "*.aspx"
        ]

    def get_js_actions(self) -> Optional[str]:
        return load_js()

    def use_semantic_filter(self) -> bool:
        return True

    def get_embedding_query(self) -> str:
        return f"Travel guide, road trip, experience in {self.place_name}"

    def process_item(self, result):
        processed = super().process_item(result)
        if not processed:
            return None
        content = processed.get("content", "")
        if content:
            lines, filtered = content.split("\n"), []
            for line in lines:
                if "![" in line and "](" in line:
                    part = line.split("](")[1].split(")")[0] if "](" in line else ""
                    low = part.lower()
                    if any(k in low for k in [
                        "icon", "logo", "badge", "sprite", "imageresource",
                        ".svg", "ad", "sponsor", "promo", "button", "arrow"
                    ]):
                        continue
                filtered.append(line)
            processed["content"] = "\n".join(filtered)
        return processed

