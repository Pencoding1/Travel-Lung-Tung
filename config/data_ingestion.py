from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict

class IngestionConfig(BaseSettings):
    BATCH_SIZE: int = 32
    DATA_SOURCE: Literal["db", "local"] = "local"
    MODEL_NAME: str = "AITeamVN/Vietnamese_Embedding"
    