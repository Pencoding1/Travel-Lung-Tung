import os
import asyncio
import logging
import firebase_admin
from pathlib import Path

from neo4j import GraphDatabase
from firebase_admin import credentials, firestore, _apps, initialize_app, delete_app, auth
from app.core.config.settings import MemgraphDB, db_settings

logger = logging.getLogger(__name__)

class FireStoreConnector:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FireStoreConnector, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        # FAST INIT: Just declare the variables. No network calls!
        self.db = None
            
    def connect(self):
        """The heavy lifting. Call this explicitly during app startup."""
        if self._initialized:
            return

        root_dir = Path(__file__).resolve().parents[4] 
        key_path = root_dir / "secrets" / "serviceAccountKey.json"

        try:
            if not _apps:
                if not key_path.exists():
                    logger.error(f"Firebase key missing at: {key_path}")
                    raise FileNotFoundError("Missing serviceAccountKey.json")
                
                cred = credentials.Certificate(str(key_path))
                initialize_app(cred)
            
            self.db = firestore.client()
            self._initialized = True
            logger.info("Firebase/Firestore connected successfully.")
        except Exception as e:
            logger.error(f"Firebase connection error: {e}")
            raise e

    def verify_connectivity(self) -> bool:
        if not self._initialized:
            return False
        try:
            auth.list_users(max_results=1)
            return True
        except Exception as e:
            logger.error(f"Firebase connectivity check failed: {str(e)}")
            return False

    def close(self):
        if _apps:
            for app_name in list(_apps.keys()):
                delete_app(_apps[app_name])
            logger.info("Firebase connection closed.")


class MemgraphConnector:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(MemgraphConnector, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, settings: MemgraphDB):
        # FAST INIT: Store settings, but do NOT connect yet.
        self.setting = settings
        self.driver = None

    async def connect(self):
        if self._initialized:
            return

        self.driver = GraphDatabase.driver(
            self.setting.memgraph_uri, 
            auth=(self.setting.MEMGRAPH_USER, self.setting.MEMGRAPH_PASSWORD)
        )
        
        retries = 10  # INCREASED FROM 5
        while retries > 0:
            try:
                self.driver.verify_connectivity()
                self._initialized = True
                logger.info("Successfully connected to Memgraph.")
                break
            except Exception as e:
                # If it's an Auth error, we should fail immediately, not retry
                if "unauthorized" in str(e).lower() or "auth" in str(e).lower():
                    logger.critical(f"Memgraph Authentication Failed: {str(e)}")
                    raise e
                    
                retries -= 1
                logger.warning(f"Memgraph not ready at {self.setting.MEMGRAPH_HOST}. Retrying... ({retries} left)")
                if retries == 0:
                    logger.error("Failed to connect to Memgraph after 50 seconds.")
                    raise e
                await asyncio.sleep(5) # INCREASED FROM 3

    def close(self):
        if hasattr(self, 'driver') and self.driver:
            self.driver.close()
            logger.info("Memgraph connection closed.")

# ---------------------------------------------------------
# MODULE EXPORTS (These are now instant and 100% safe to import anywhere)
# ---------------------------------------------------------
firestore_db = FireStoreConnector()
memgraph_db = MemgraphConnector(db_settings)

def get_memgraph_connector() -> MemgraphConnector:
    return memgraph_db

def get_firestore_connector() -> FireStoreConnector:
    return firestore_db