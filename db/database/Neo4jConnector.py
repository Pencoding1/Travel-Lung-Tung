import os

from logging import getLogger
from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

base_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(base_dir, "../.env")
logger = getLogger(__name__)

class Neo4jConnector:
    def __init__(self):
        self.neo4j_driver = self._connect_neo4j()

    def _connect_neo4j(self):
        uri = os.getenv("NEO4J_URI")
        user = os.getenv("NEO4J_USER")
        password = os.getenv("NEO4J_PASSWORD")

        if not (uri and user and password):
            raise ValueError("NEO4J Authentication environment variable is not set")
        try:
            driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
            logger.info("Neo4j Driver Initialized (Lazy Connection)")
            return driver
        except Exception as e:
            logger.error(f"Neo4j Connection Failed: {e}")
            raise e
    
    async def verify_connection(self):
        """
        Call this manually during app startup (e.g., in FastAPI lifespan)
        to ensure the DB is actually reachable.
        """
        try:
            await self.neo4j_driver.verify_connectivity()
            logger.info("Neo4j Connectivity Verified!")
        except Exception as e:
            logger.error(f"Neo4j Connectivity Failed: {e}")
            raise e
        
    async def close(self):
        if self.neo4j_driver:
            await self.neo4j_driver.close()
            logger.info("Neo4j Driver Closed.")