import asyncio
import os
import json
import logging
from typing import List, Optional, Dict, Any
from pipelines.crawling.base.PipelineBase import BasePipelineCrawler
from pipelines.crawling.config import CrawlerGlobalConfig
from pipelines.crawling.utils import load_js

logger = logging.getLogger('TravelokaCrawler')


class TravelokaCrawler(BasePipelineCrawler):
    def __init__(self, place_name: str, topic_keyword: str = "general_scan", lang_code: str = "vi", **kwargs):
        super().__init__(**kwargs)
        self.place_name = place_name
        self.topic_keyword = topic_keyword
        self.lang_code = lang_code
        self.webpage_name = "traveloka"
        self.results_data = []

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
        slug = self.place_name.lower().replace(" ", "-")
        return [
            f"*{slug}*",
            "*vi-vn*"
        ]

    def get_js_actions(self) -> Optional[str]:
        return load_js()

    def get_excluded_selectors(self) -> List[str]:
        return [".css-1dbjc4n.r-5kkj8d.r-18u37iz.r-1w6e6rj.r-f4gmv6.r-zd98yo.r-10fj5tc.r-fd4yh7"]

    def _generate_filename(self, stt: Any, ext: str) -> str:
        key_safe = self.topic_keyword.replace(" ", "_")
        return f"{self.place_name}_{key_safe}_{self.webpage_name}_{self.lang_code}_{stt}.{ext}"

    def save_item_to_disk(self, data: Dict, folder: str):
        path = os.path.join(folder, self.get_domain_name(), self.place_name)
        os.makedirs(path, exist_ok=True)

        stt = len(self.results_data) + 1
        filename_md = self._generate_filename(stt, "md")

        with open(os.path.join(path, filename_md), "w", encoding="utf-8") as f:
            f.write(data['content'])
        data['stt'] = stt
        data['filename'] = filename_md
        self.results_data.append(data)
        print(f"Saved content: {filename_md}")

    async def execute(self, start_url: str, output_folder: str = "./data"):
        await super().execute(start_url, output_folder)
        if self.results_data:
            summary_path = os.path.join(output_folder, "crawled_data", self.get_domain_name(), self.place_name)
            os.makedirs(summary_path, exist_ok=True)

            filename_list = self._generate_filename("List", "json")
            json_file_path = os.path.join(summary_path, filename_list)

            with open(json_file_path, "w", encoding="utf-8") as f:
                json.dump(self.results_data, f, indent=4, ensure_ascii=False)
            print(f"✅ Exported Summary: {json_file_path}")


async def main():
    city_configs = {
        "HCM": {
            "place_patterns": ["*ho-chi-minh-city*", "*tp-hcm*",
                               "*saigon*", "*hcmc*", "*ho-chi-minh*"],
            "url": "https://www.traveloka.com/vi-vn/destination/area/ho-chi-minh-city-10009794"
        }
    }
    target_city = "HCM"
    city_data = city_configs.get(target_city)
    if not city_data:
        print("not found")
        return
    #Tách main thì set headless = True
    config = CrawlerGlobalConfig(headless=False, max_pages=100)

    crawler = TravelokaCrawler(
        place_name=target_city,
        topic_keyword="general_scan",
        lang_code="vi",
        config=config
    )

    await crawler.execute(city_data["url"])

if __name__ == "__main__":
    asyncio.run(main())