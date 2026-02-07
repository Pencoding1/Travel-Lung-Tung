# FILE: main.py
import asyncio
from pipelines.crawling.config import CrawlerGlobalConfig
from pipelines.crawling.spiders.VNtravelCrawler import VNTravelCrawler
from pipelines.crawling.spiders.VietravelCrawler import VietravelCrawler
from pipelines.crawling.spiders.TravelokaCrawler import TravelokaCrawler
from pipelines.crawling.spiders.VietnamCoracleCrawler import VietnamCoracleCrawler
from pipelines.crawling.spiders.VietnamTravel import VietnamTravelCrawler
from pipelines.crawling.utils import init_semantic_filter

CITY_CONFIGS = {
    "HaNoi": {
            "place_patterns": ["*ha-noi*", "*hanoi*"],
            "urls": {
                "traveloka": "https://www.traveloka.com/vi-vn/activities/vietnam/region/hanoi-10009843",
                "Vietravel": "https://travel.com.vn/du-lich-ha-noi.aspx",
                "VietnamCoracle": "https://www.vietnamcoracle.com/tag/hanoi/",
                "VietnamTravel": "https://vietnam.travel/places-to-go/northern-vietnam/ha-noi",
                "Vntravel": "https://vntravel.org.vn/tim-kiem.html?keyword=H%C3%A0+N%E1%BB%99i"
            }
        },
    "DaLat": {
        "place_patterns": ["*da-lat*", "*dalat*"],
        "urls": {
            "traveloka": "https://www.traveloka.com/vi-vn/activities/vietnam/city/da-lat-10010169",
            "Vietravel": "https://travel.com.vn/du-lich-da-lat.aspx",
            "VietnamCoracle": "https://www.vietnamcoracle.com/tag/dalat/",
            "VietnamTravel": "https://vietnam.travel/places-to-go/central-vietnam/dalat",
            "Vntravel": "https://vntravel.org.vn/tim-kiem.html?keyword=%C4%90%C3%A0+L%E1%BA%A1t"
        }
    },
    "HCM": {
        "place_patterns": ["*ho-chi-minh-city*",
                           "*saigon*", "*hcmc*",
                           "*ho-chi-minh*",
                           "*sai-gon*",
                           "*sg*", "*near-saigon*",
                           "*tp-ho-chi-minh*", "*ho-chi-minh-tour"],
        "urls": {
            "traveloka": "https://www.traveloka.com/vi-vn/activities/vietnam/region/ho-chi-minh-city-10009794",
            "Vietravel": "https://travel.com.vn/du-lich-ho-chi-minh.aspx",
            "VietnamCoracle": "https://www.vietnamcoracle.com/browse/destinations/saigon/",
            "VietnamTravel": "https://vietnam.travel/places-to-go/southern-vietnam/ho-chi-minh-city",
            "Vntravel": "https://vntravel.org.vn/tim-kiem.html?keyword=h%E1%BB%93+ch%C3%AD+minh"
        }
    },
    "DaNang": {
        "place_patterns": ["*da-nang*", "*danang*"],
        "urls": {
            "traveloka": "https://www.traveloka.com/vi-vn/activities/vietnam/region/da-nang-10010083",
            "Vietravel": "https://travel.com.vn/du-lich-da-nang.aspx",
            "VietnamCoracle": "https://www.vietnamcoracle.com/tag/danang/",
            "VietnamTravel": "https://vietnam.travel/places-to-go/central-vietnam/da-nang",
            "Vntravel": "https://vntravel.org.vn/tim-kiem.html?keyword=%C4%91%C3%A0+n%E1%BA%B5ng"
        }
    },
}

init_semantic_filter(
    model_name="AITeamVN/Vietnamese_Embedding_v2",
    query="Bài viết chi tiết về du lịch thành phố Hồ Chí Minh, Sài Gòn, tphcm. Các địa điểm vui chơi, ăn uống, tham quan tại Sài Gòn."
)

SPIDER_MAP = {
    "traveloka": TravelokaCrawler,
    "Vietravel": VietravelCrawler,
    "VietnamCoracle": VietnamCoracleCrawler,
    "VietnamTravel": VietnamTravelCrawler,
    "Vntravel": VNTravelCrawler,
}


GLOBAL_CRAWL_SETTINGS = {
    "max_depth": 4,
    "max_pages": 1000,
    "headless": False
}

async def run_crawler(web_id: str, city_id: str):
    city_info = CITY_CONFIGS.get(city_id)
    url = city_info["urls"].get(web_id)

    if not url:
        print(f"Not found {web_id} at {city_id}")
        return
    print(f"Config: Depth={GLOBAL_CRAWL_SETTINGS['max_depth']}, MaxPages={GLOBAL_CRAWL_SETTINGS['max_pages']}")
    config = CrawlerGlobalConfig(
        headless=GLOBAL_CRAWL_SETTINGS["headless"],
        max_depth=GLOBAL_CRAWL_SETTINGS["max_depth"],
        max_pages=GLOBAL_CRAWL_SETTINGS["max_pages"]
    )

    SpiderClass = SPIDER_MAP[web_id]
    bot = SpiderClass(
        place_name=city_id,
        city_data=city_info,
        config=config
    )
    await bot.execute([url], output_folder="./data")

if __name__ == "__main__":
    TARGET_WEB = "Vntravel"
    TARGET_CITY = "DaNang"
    asyncio.run(run_crawler(TARGET_WEB, TARGET_CITY))