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

    @classmethod
    def from_process_env(cls) -> "MemgraphDB":
        """Explicit settings from the process environment only.

        ``_env_file=None`` disables the class-level ``.env`` source for this
        instance; the default ``MemgraphDB()`` behaviour (and the operator
        contract) is unchanged. No value is logged by this method.
        """
        return cls(_env_file=None)  # type: ignore[call-arg]


# Explicit process-only selector. Absence keeps the historical .env-file
# behaviour; ``process_only`` disables the class-level .env source for this
# process. Any other value fails before either factory could load a file.
DB_SETTINGS_SOURCE_ENV = "POI_DB_SETTINGS_SOURCE"
DB_SETTINGS_SOURCE_LEGACY = "legacy_env_file"
DB_SETTINGS_SOURCE_PROCESS_ONLY = "process_only"
DB_SETTINGS_SOURCES = (
    DB_SETTINGS_SOURCE_LEGACY,
    DB_SETTINGS_SOURCE_PROCESS_ONLY,
)
INVALID_DB_SETTINGS_SOURCE = "invalid_db_settings_source"


def select_db_settings(source, process_factory, legacy_factory):
    """Choose the settings factory without touching a file on invalid input."""
    if source is None or source == "":
        return legacy_factory()
    if source not in DB_SETTINGS_SOURCES:
        raise ValueError(INVALID_DB_SETTINGS_SOURCE)
    if source == DB_SETTINGS_SOURCE_PROCESS_ONLY:
        return process_factory()
    return legacy_factory()


db_settings = select_db_settings(
    os.environ.get(DB_SETTINGS_SOURCE_ENV),
    MemgraphDB.from_process_env,
    MemgraphDB,
)  # type: ignore[assignment]