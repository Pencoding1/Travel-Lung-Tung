from sentence_transformers import SentenceTransformer
import threading

class SharedModel:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_model(cls, model_name):
        with cls._lock:
            if cls._instance is None:
                print(f"Loading AI Model: {model_name} (This should happen only once)...")
                cls._instance = SentenceTransformer(model_name)
        return cls._instance