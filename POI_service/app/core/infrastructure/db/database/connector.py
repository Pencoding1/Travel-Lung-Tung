import os
import time
import firebase_admin

from pathlib import Path
from logging import getLogger


from neo4j import GraphDatabase
from firebase_admin import credentials, firestore, _apps, initialize_app, delete_app

from app.core.config.settings import MemgraphDB, db_settings


base_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(base_dir, "../.env")
logger = getLogger(__name__)

class FireStoreConnector:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FireStoreConnector, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        key_path = Path(__file__).parent.parent.parent.parent.parent / "secrets/serviceAccountKey.json"
        try:
            if not _apps:
                cred = credentials.Certificate(key_path)
                initialize_app(cred)
            
            self.db = firestore.client()
            self._initialized = True
            logger.info("FIREBASE CONNECTED!")
        except Exception as e:
            logger.error(f"FIREBASE CONNECTION ERROR: {e}")
            raise e

    def close(self):
        if _apps:
            for app in list(_apps.values()):
                delete_app(app)
            logger.info("FIREBASE CONNECTION CLOSED")


class MemgraphConnector:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(MemgraphConnector, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_settings: MemgraphDB):
        if self._initialized:
            return

        self.setting = db_settings
        print(self.setting.memgraph_uri)
        self.driver = GraphDatabase.driver(
            self.setting.memgraph_uri, 
            auth=(self.setting.MEMGRAPH_USER, self.setting.MEMGRAPH_PASSWORD)
        )
        retries = 5
        while retries > 0:
            try:
                self.driver.verify_connectivity()
                self._initialized = True
                logger.info("Successfully connected to Memgraph!")
                break
            except Exception as e:
                print(f"DEBUG: Connecting to {db_settings.MEMGRAPH_HOST} on port {db_settings.MEMGRAPH_PORT}")
                retries -= 1
                logger.warning(f"⏳ Memgraph network not ready. Retrying in 3 seconds... ({retries} left)")
                if retries == 0:
                    logger.error("Failed to connect to Memgraph after multiple attempts.")
                    raise e
                time.sleep(3)


    def close(self):
        if hasattr(self, 'driver') and self.driver:
            self.driver.close()
            logger.info("MEMGRAPH CONNECTION CLOSED")



firestore_db = FireStoreConnector()
print(f"DEBUG: Connecting to {db_settings.MEMGRAPH_HOST} on port {db_settings.MEMGRAPH_PORT}")
memgraph_db  = MemgraphConnector(db_settings=db_settings)


def get_memgraph_connector() -> MemgraphConnector:
    """FastAPI Dependency to yield the active database connector."""
    return memgraph_db

def get_firestore_connector() -> FireStoreConnector:
    return firestore_db