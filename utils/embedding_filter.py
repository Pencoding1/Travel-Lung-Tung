from torch import Tensor
from torch.cuda import is_available

from sentence_transformers import SentenceTransformer, util

from typing import Optional, List, Union


class Semantic_Filter:
    def __init__(self, 
                 model: SentenceTransformer, 
                ):
        self._model = model
        self._emb_query = None

    def set_query(self, query: Union[str, List[str]]):
        """Encodes and stores the target query."""
        if not query:
            raise ValueError("Query cannot be empty or None.")
        
        raw_emb = self._model.encode(query, convert_to_tensor=True)
        self._emb_query = self._ensure_2d(raw_emb) 
    
    @staticmethod
    def _ensure_2d(emb: Tensor) -> Tensor:
        """Standardizes shape to (1, N) for consistent cosine similarity math."""
        return emb.unsqueeze(0) if emb.dim() == 1 else emb
        
    def is_relevant(self, markdown: str, threshold: float = 0.4, max_length:int = 3000) -> bool:
        if not markdown or self._model is None or self._emb_query is None:
            return False
    
        emb = self._ensure_2d(self._model.encode(markdown[:max_length], convert_to_tensor=True))
        score = util.cos_sim(self._emb_query, emb).max().item()
        return score >= threshold
    