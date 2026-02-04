import logging
from typing import List, Optional, Dict
from pipelines.crawling.base.PipelineBase import BasePipelineCrawler
from pipelines.crawling.utils import load_js

logger = logging.getLogger('TravelokaCrawler')


class TravelokaCrawler(BasePipelineCrawler):
    def __init__(self, place_name: str, city_data: Dict = None, topic_keyword: str = "general_scan", lang_code: str = "vi", **kwargs):
        super().__init__(**kwargs)
        self.city_data = city_data or {}
        self.place_name = place_name
        self.topic_keyword = topic_keyword
        self.lang_code = lang_code
        self.webpage_name = "traveloka"

    def get_domain_name(self) -> str:
        return self.webpage_name

    def get_css_selectors(self) -> List[str]:
        return [
            '[data-testid="view_articleWrapper"]',
            '[data-testid="ctr_tourItinerary"]',
            '#itinerary-section',
            '#ticketSummaryItinerary',
            '[data-testid="view_articleTableContent"]'
        ]

    def get_specific_keywords(self) -> List[str]:
        return [self.place_name, "tour", "vé máy bay", "khách sạn", "trải nghiệm"]

    def get_place_patterns(self) -> List[str]:
        if "place_patterns" in self.city_data:
            return self.city_data["place_patterns"]

        slug = self.place_name.lower().replace(" ", "-")
        return [
            f"*{slug}*",
            "*vi-vn*"
        ]

    def get_js_actions(self) -> Optional[str]:
        return load_js()

    def get_excluded_selectors(self) -> List[str]:
        return [".css-1dbjc4n.r-5kkj8d.r-18u37iz.r-1w6e6rj.r-f4gmv6.r-zd98yo.r-10fj5tc.r-fd4yh7"]
