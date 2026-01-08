import os
import firebase_admin

from firebase_admin import credentials, firestore

from dotenv import load_dotenv
from logging import getLogger

base_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(base_dir, "../.env")
logger = getLogger(__name__)

class FireStoreConnector:
    _instance = None

    def __init__(self):
        self.firestore_db = self._connect_firestore()

    def _connect_firestore(self):
        key_path_env = os.getenv("FIREBASE_KEY_PATH")
        if not key_path_env:
            raise ValueError("FIREBASE_KEY_PATH environment variable is not set")
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        KEY_PATH = os.path.join(base_dir, "../../", key_path_env)

        try:
            if not firebase_admin._apps:
                cred = credentials.Certificate(KEY_PATH)
                firebase_admin.initialize_app(cred)
            
            db = firestore.client()
            logger.info("FIREBASE CONNECTED!")
            return db
        except Exception as e:
            logger.error(f"ERROR EXIST DURING CONNECTING TO FIREBASE: {e}")
            raise e
        