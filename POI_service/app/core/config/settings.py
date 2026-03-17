from pydantic_settings import BaseSettings

class MemgraphDB(BaseSettings):
    memgraph_uri: str = "bolt:localhost:7687"
    memgraph_user: str
    memgraph_password: str

    class Config:
        env_file = ".env"