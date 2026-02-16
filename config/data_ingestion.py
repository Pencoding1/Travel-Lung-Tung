import os

from dotenv import load_dotenv
from typing import Literal, Set

from global_config import Agency, City

from pydantic_settings import BaseSettings, SettingsConfigDict
load_dotenv()

class IngestionConfig(BaseSettings):
    BATCH_SIZE: int = 32
    DATA_SOURCE: Literal["db", "local"] = "local"
    AGENCIES: Set[Agency] = set(Agency) 
    CITIES:   Set[City] = set(City)
    MODEL_NAME: str = os.environ['EMBEDDING_MODEL']
    DESTINATION: Literal["local", "vector", "graph"] = "local"
    OUTPUT_PATH: str = "" if  DESTINATION != "local" else os.getenv("LOCAL_STORAGE", "./data")
    ACCEPTED_THRESHOLD: float = 0.7

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
