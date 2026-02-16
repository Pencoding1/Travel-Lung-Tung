import os

from dotenv import load_dotenv
from typing import List, Set
from pydantic_settings import BaseSettings, SettingsConfigDict
from global_config import Agency, City

load_dotenv()
class PreprocessConfig(BaseSettings):
    AGENCIES: Set[Agency] = set(Agency) 
    CITIES:   Set[City] = set(City)
    MODEL_NAME: str = os.environ['EMBEDDING_MODEL']

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")