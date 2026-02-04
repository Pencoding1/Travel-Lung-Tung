# FILE: main.py
import asyncio
from pipelines.crawling.config import CrawlerGlobalConfig
from pipelines.crawling.spiders.VietravelCrawler import VietravelCrawler
from pipelines.crawling.spiders.TravelokaCrawler import TravelokaCrawler
from pipelines.crawling.spiders.VietnamCoracleCrawler import VietnamCoracleCrawler
from pipelines.crawling.spiders.VietnamTravel import VietnamTravelCrawler

CITY_CONFIGS = {
    "DaLat": {
        "place_patterns": ["*da-lat*", "*dalat*"],
        "urls": {
            "traveloka": "https://www.traveloka.com/vi-vn/destination/area/da-lat-10010169",
            "Vietravel": "https://www.agoda.com/vi-vn/city/dalat-vn.html"
        }
    },
    "HCM": {
        "place_patterns": ["*ho-chi-minh-city*",
                           "*saigon*", "*hcmc*",
                           "*ho-chi-minh*",
                           "*sai-gon*",
                           "*sg*", "*near-saigon*"
                           "*tp-ho-chi-minh*"],
        "urls": {
            "traveloka": "https://www.traveloka.com/vi-vn/destination/area/ho-chi-minh-city-10009794",
            "Vietravel": "https://travel.com.vn/du-lich-ho-chi-minh",
            "VietnamCoracle": "https://www.vietnamcoracle.com/browse/destinations/",
            "VietnamTravel": "https://vietnam.travel/places-to-go/southern-vietnam/ho-chi-minh-city/"
        }
    },
}

SPIDER_MAP = {
    "traveloka": TravelokaCrawler,
    "Vietravel": VietravelCrawler,
    "VietnamCoracle": VietnamCoracleCrawler,
    "VietnamTravel": VietnamTravelCrawler,
}


async def run_crawler(web_id: str, city_id: str):
    city_info = CITY_CONFIGS.get(city_id)
    url = city_info["urls"].get(web_id)

    if not url:
        print(f"Not found {web_id} at {city_id}")
        return

    # Set headless=True nếu muốn chạy ngầm
    config = CrawlerGlobalConfig(headless=False, max_pages=50)

    # Khởi tạo Crawler
    SpiderClass = SPIDER_MAP[web_id]
    bot = SpiderClass(
        place_name=city_id,
        city_data=city_info,
        config=config
    )
    await bot.execute(url, output_folder="./data")


if __name__ == "__main__":
    # Đổi 2 tham số
    TARGET_WEB = "traveloka"
    TARGET_CITY = "HCM"

    asyncio.run(run_crawler(TARGET_WEB, TARGET_CITY))