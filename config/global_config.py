from enum import Enum

class City(str, Enum):
    HCM = "hcm"
    HANOI = "hanoi"
    DALAT = "dalat"
    DANANG = "danang"

class Agency(str, Enum):
    TRAVELOKA = "traveloka"
    VIETRAVEL = "vietravel"
    VIETNAM_CORACLE = "vietnamcoracle"
    VIETNAM_TRAVEL = "vietnam_travel"

CITY_CONFIGS = {
    City.HANOI: {
            "place_patterns": ["*ha-noi*", "*hanoi*"],
            "urls": {
                "traveloka": "https://www.traveloka.com/vi-vn/activities/vietnam/region/hanoi-10009843",
                "vietravel": "https://travel.com.vn/du-lich-ha-noi.aspx",
                "vietnamcoracle": "https://www.vietnamcoracle.com/tag/hanoi/",
                "vietnam_travel": "https://vietnam.travel/places-to-go/northern-vietnam/ha-noi",
            }
        },
    City.DALAT: {
        "place_patterns": ["*da-lat*", "*dalat*"],
        "urls": {
            "traveloka": "https://www.traveloka.com/vi-vn/activities/vietnam/city/da-lat-10010169",
            "vietravel": "https://travel.com.vn/du-lich-da-lat.aspx",
            "vietnamcoracle": "https://www.vietnamcoracle.com/tag/dalat/",
            "vietnam_travel": "https://vietnam.travel/places-to-go/central-vietnam/dalat",
        }
    },
    City.HCM: {
        "place_patterns": ["*ho-chi-minh-city*",
                           "*saigon*", "*hcmc*",
                           "*ho-chi-minh*",
                           "*sai-gon*",
                           "*sg*", "*near-saigon*",
                           "*tp-ho-chi-minh*", "*ho-chi-minh-tour"],
        "urls": {
            "traveloka": "https://www.traveloka.com/vi-vn/activities/vietnam/region/ho-chi-minh-city-10009794",
            "vietravel": "https://travel.com.vn/du-lich-ho-chi-minh.aspx",
            "vietnamcoracle": "https://www.vietnamcoracle.com/browse/destinations/saigon/",
            "vietnam_travel": "https://vietnam.travel/places-to-go/southern-vietnam/ho-chi-minh-city",
        }
    },
    City.DANANG: {
        "place_patterns": ["*da-nang*", "*danang*"],
        "urls": {
            "traveloka": "https://www.traveloka.com/vi-vn/activities/vietnam/region/da-nang-10010083",
            "vietravel": "https://travel.com.vn/du-lich-da-nang.aspx",
            "vietnamcoracle": "https://www.vietnamcoracle.com/tag/danang/",
            "vietnam_travel": "https://vietnam.travel/places-to-go/central-vietnam/da-nang",
        }
    },
}

GLOBAL_CRAWL_SETTINGS = {
    "max_depth": 4,
    "max_pages": 1000,
    "headless": False,
}
