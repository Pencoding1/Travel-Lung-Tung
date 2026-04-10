import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import computed_field

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

ENV_FILE_PATH = ROOT_DIR / ".env"

class MemgraphDB(BaseSettings):
    # Split the host and port so .env can override just the host
    MEMGRAPH_HOST: str
    MEMGRAPH_PORT: int = 7687
    MEMGRAPH_USER: str
    MEMGRAPH_PASSWORD: str

    # Dynamically build the URI based on whatever the host currently is
    @computed_field
    @property
    def memgraph_uri(self) -> str:
        return f"bolt://{self.MEMGRAPH_HOST}:{self.MEMGRAPH_PORT}"

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH), 
        env_file_encoding='utf-8',
        extra='ignore' 
    )

db_settings = MemgraphDB() #type: ignore