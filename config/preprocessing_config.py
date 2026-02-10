from typing import Literal, Set
from pydantic_settings import BaseSettings, SettingsConfigDict

class PreprocessConfig(BaseSettings):
    BATCH_SIZE: int = 8
    MODEL_NAME: str = "AITeamVN/Vietnamese_Embedding"
    PATTERN: str = "*.md"
    DESTINATION: Literal["db", "local"] = "local"
    NUM_WORKERS: int = 6
    CITIES: Set[str] = {
                            "hcm",
                            "hanoi",
                            "dalat",
                            "danang"
                        }
    AGENCIES: Set[str] = {
                                "traveloka", 
                                "vietravel", 
                                "vietnam_travel", 
                                "vntravel"
                         }