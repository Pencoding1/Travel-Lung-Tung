import os
import firebase_admin

from types import MemberDescriptorType
from logging import getLogger


from neo4j import GraphDatabase
from firebase_admin import credentials, firestore, _apps, initialize_app, delete_app

from app.config import settings
from app.core.repositories import memgraph


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
            
        key_path = os.getenv("FIREBASE_KEY_PATH")
        if not key_path:
            raise ValueError("FIREBASE_KEY_PATH is not set")
        
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

    def __init__(self, db_settings: settings.MemgraphDB):
        if self._initialized:
            return

        self.setting = db_settings
        try:
            self.driver = GraphDatabase.driver(
                self.setting.memgraph_uri, 
                auth=(self.setting.memgraph_user, self.setting.memgraph_password)
            )
            self.driver.verify_connectivity()
            self._initialized = True
            logger.info("MEMGRAPH CONNECTED!")
        except Exception as e:
            logger.error(f"MEMGRAPH CONNECTION ERROR: {e}")
            raise e

    def close(self):
        if hasattr(self, 'driver') and self.driver:
            self.driver.close()
            logger.info("MEMGRAPH CONNECTION CLOSED")