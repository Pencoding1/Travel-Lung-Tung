import os

from pathlib import Path
from dotenv import load_dotenv
from crawl4ai import BrowserConfig, AdaptiveConfig, CrawlerRunConfig
from pydantic import Field, AliasChoices, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from enum import Enum
from typing import Literal, Set, List, Optional, Tuple


load_dotenv()
PARENT = Path(__file__).parent.parent

class CACHE_MODE(str, Enum):
    WRITE = "write"
    READ = "read"

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




DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"

class CrawlerSetting(BaseSettings):
    # Dùng default_factory để mỗi instance có một object cấu hình độc lập, tránh bị share chung (share state)
    run_cfg: CrawlerRunConfig = Field(default_factory=lambda: CrawlerRunConfig(
            excluded_selector="div.articleTableOfContent",
            wait_for_timeout=7000,
            delay_before_return_html=10,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            magic=True,
            scan_full_page=True,
            scroll_delay=0.5,
            simulate_user=True,
            session_id="hn_"
    ))
    max_depth: int = 4
    max_pages: int = 100
    headless: bool = False
    use_embedding: bool = False
    store_destination: Literal["db", "local"] = "local"
    user_agent: str = DEFAULT_USER_AGENT
    
    browser_config: BrowserConfig = Field(
        default_factory=lambda: BrowserConfig(
            headless=False,
            # use_managed_browser=True,
            # browser_type="chromium",
            user_data_dir=str(PARENT / "chromium_profile"),
            verbose=True,
            extra_args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-extensions",
                "--disable-infobars",
                "--start-maximized",
                "--disable-popup-blocking",
            ]
        )
    )
    
    # Pydantic v2 tự động copy list mặc định nên không cần dùng Field(default_factory=lambda: [...]) rườm rà
    global_keywords: List[str] = [
        "*/vi-vn/*", "*vietnam*", "*viet-nam*", "*destinations*",
        "*destination*", "*tour*", "*travel*", "*guide*",
        "*activity*", "*activities*", "*attraction*", "*attractions*",
        "*/viet nam/*", "*/du-lich/*"
    ]
    
    @model_validator(mode='after')
    def sync_headless_state(self) -> 'CrawlerSetting':
        """
        Hàm này tự động chạy sau khi CrawlerSetting được tạo.
        Nó lấy giá trị của self.headless và gán đè vào self.browser_config.headless.
        """
        if self.browser_config is not None:
            self.browser_config.headless = self.headless
        return self
    

class ExtractorSettings(BaseSettings):
    domain: Agency = Agency.TRAVELOKA
    root_dir: Path = PARENT
    def set_domain(self, domain_name: str):
        try:
            self.domain = Agency[domain_name.upper()]
        except KeyError:
            raise ValueError(f"Invalid domain name: '{domain_name}'. Valid options are: {[e.name.lower() for e in Agency]}")


class IngestionSettings(BaseSettings):
    BATCH_SIZE: int = 32
    DATA_SOURCE: Literal["db", "local"] = "local"
    AGENCIES: Set[Agency] = set(Agency) 
    CITIES:   Set[City] = set(City)
    MODEL_NAME: str = os.environ['EMBEDDING_MODEL']
    DESTINATION: Literal["local", "vector", "graph"] = "local"
    OUTPUT_PATH: str = "" if  DESTINATION != "local" else os.getenv("LOCAL_STORAGE", "./data")
    ACCEPTED_THRESHOLD: float = 0.7

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class DiscoverSettings(BaseSettings):
    # --- Logic & Strategy ---
    strategy_type: str = Field(default="statistical", pattern="^(statistical|embedding)$")
    cache_path: Path = PARENT / "cache" / "discovery"
    embedding_model: Optional[str] = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        validation_alias=AliasChoices("EMBEDDING_MODEL", "DISCOVER_EMBEDDING_MODEL")
    )
    
    queries: Optional[List[str]] = [
        "Tìm địa điểm nghỉ ngơi, khách sạn, resort và homestay yên tĩnh tại Thành phố Hồ Chí Minh.",
        "Danh sách các địa điểm vui chơi, khu giải trí, bảo tàng và điểm tham quan nổi tiếng ở Sài Gòn.",
        "Gợi ý những địa điểm ăn uống, nhà hàng, ẩm thực đường phố và quán ngon tại Thành phố Hồ Chí Minh.",
        "Kinh nghiệm du lịch Sài Gòn: địa điểm vui chơi, chỗ ăn uống đặc sản và nơi nghỉ ngơi thư giãn cuối tuần."]
    
    top_k: int = 10
    weight_threshold: float = 0.1
    get_knowledge_base: bool = False
    base_directory: Path = PARENT / "secrets" / "crawl_cache"
    relevant_threshold: float = 0.1

    excluded_urls: Set[str] = Field(default_factory=lambda: {
        "https://www.traveloka.com/vi-vn",
        "https://www.traveloka.com/vi-vn/promotion",
        "https://www.traveloka.com/vi-vn/partnership",
        "https://www.traveloka.com/vi-vn/car-rental",
        "https://www.traveloka.com/vi-vn/bus-and-shuttle",
        "https://www.traveloka.com/vi-vn/airport-transfer",
        "https://www.traveloka.com/vi-vn/how-to",
        "https://www.traveloka.com/vi-vn/activities",
        "https://www.traveloka.com/vi-vn/flight",
        "https://www.traveloka.com/vi-vn/hotel",
        "https://www.traveloka.com/vi-vn/how-to/bookflight"
    })
    disallowed_endings: Tuple = (
                            "activities",   
                            "hotel",
                            "flight",
                        )

    model_config = SettingsConfigDict(
        env_prefix="DISCOVER_", 
        env_file=".env", 
        extra="ignore",
        env_file_encoding="utf-8"
    )

    excluded_patterns: List[str] = [
        r"promotions",
        r"hotels",
    ]
    included_patterns: List[str] = [] 

    def get_adaptive_config(self, user_config: Optional[AdaptiveConfig] = None) -> AdaptiveConfig:
        default_config = {
                            "confidence_threshold": 0.6,    # Threshold for "stopping" the adaptive crawl
                            "consistency_threshold": 0.5,
                            "min_gain_threshold": 0.1,
                            "max_pages": 100,
                            "max_depth": 4
                        }
        return user_config or AdaptiveConfig(**default_config)


class LoadPipelineSetting(BaseSettings):
    cache_mode: CACHE_MODE = CACHE_MODE.READ 
    crawler_cfg: CrawlerSetting
    discover_cfg: DiscoverSettings
    extractor_cfg: ExtractorSettings
    graph_output_path: Path =PARENT / "secrets" / "discover_reports" / "knowledge_base"


class ExtractPipelineSetting(BaseSettings):
    pipeline_cfg: IngestionSettings


class AppSettings(BaseSettings):
    DEBUG: bool=True
    LOCAL_STORAGE: str="data"
    STORAGE: str="local"
    
    storage_path:Path = PARENT / LOCAL_STORAGE
    load_settings: List[LoadPipelineSetting]
    extract_settings: List[ExtractPipelineSetting]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")