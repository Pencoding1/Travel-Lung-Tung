from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, Set, List
from crawl4ai import AdaptiveConfig, BrowserConfig
from pathlib import Path

PARENT = Path(__file__).parent.parent

cache_path = PARENT / "cache"
graph_path = PARENT / "reports" / "graph"
stats_path = PARENT / "reports" / "stats"
plot_path  = PARENT / "reports" / "graph" / "plot"


class DiscoverSettings(BaseSettings):
    # --- Logic & Strategy ---
    strategy_type: str = Field(default="statistical", pattern="^(statistical|embedding)$")
    
    embedding_model: Optional[str] = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        validation_alias=AliasChoices("EMBEDDING_MODEL", "DISCOVER_EMBEDDING_MODEL")
    )
    
    query: Optional[str] = "travel destinations in Ho Chi Minh City"
    top_k: int = 10
    weight_threshold: float = 0.1
    get_knowledge_base: bool = False

    base_directory: Path | str = Field(default=cache_path)
    graph_output_path: Path | str = Field(default=graph_path)
    stats_file: Path | str = Field(default=stats_path)
    visual_report_html: Path | str = Field(default="weighted_travel_graph.html")

    relevant_threshold: float = 0.1

    excluded_urls: Set[str] = Field(default_factory=lambda: {
        "https://www.traveloka.com/vi-vn",
        "https://www.traveloka.com/vi-vn/promotion",
        "https://www.traveloka.com/vi-vn/partnership",
        "https://www.traveloka.com/vi-vn/hotel",
        "https://www.traveloka.com/vi-vn/flight",
        "https://www.traveloka.com/vi-vn/airport-transfer",
        "https://www.traveloka.com/vi-vn/car-rental", 
        "https://www.traveloka.com/vi-vn/activities",
        "https://www.traveloka.com/vi-vn/bus-and-shuttle"
    })

    model_config = SettingsConfigDict(
        env_prefix="DISCOVER_", 
        env_file=".env", 
        extra="ignore",
        env_file_encoding="utf-8"
    )

    def ensure_paths(self):
        self.base_directory.mkdir(parents=True, exist_ok=True) #type: ignore
        self.graph_output_path.parent.mkdir(parents=True, exist_ok=True) #type: ignore
        self.stats_file.parent.mkdir(parents=True, exist_ok=True) #type: ignore

    def get_browser_config(self, user_config: Optional[BrowserConfig] = None) -> BrowserConfig:
        return user_config or BrowserConfig(headless=False, verbose=True)

    def get_adaptive_config(self, user_config: Optional[AdaptiveConfig] = None) -> AdaptiveConfig:
        default_config = {
                            "confidence_threshold": 0.6,    # Threshold for "stopping" the adaptive crawl
                            "consistency_threshold": 0.5,
                            "min_gain_threshold": 0.1,
                            "max_pages": 100,
                            "max_depth": 4
                        }
        return user_config or AdaptiveConfig(**default_config)