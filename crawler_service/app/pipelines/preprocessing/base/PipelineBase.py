from app.core.config.settings import ParserSettings 
from abc import ABC, abstractmethod
from typing import Optional, Set

from pyvi import ViTokenizer
from datasketch import MinHash, MinHashLSH

class BasePreprocessor(ABC):
    def __init__(self, lsh: Optional[MinHashLSH], config: Optional[ParserSettings] = None):
        self.config = config if config else ParserSettings()
        self.lsh = lsh if lsh else MinHashLSH(threshold=0.9, num_perm=128)

    def _get_shingles_vietnamese(self, text: str, n: int = 3) -> Set[str]:
        tokenize_text:str = ViTokenizer.tokenize(text.lower())
        words = tokenize_text.split()

        if len(words) < n:
            return {tokenize_text}
        
        shingles = set()

        for i in range(len(words) - n + 1):
            shingle = "".join(words[i: i+n])
            shingles.add(shingle)
        
        return shingles
    
    def _calculate_minhash(self, text:str, is_Vi: bool=True) -> MinHash:
        m = MinHash(num_perm=128)
        if is_Vi:
            shingles = self._get_shingles_vietnamese(text)
        else:
            shingles = set(text.split())
        
        for s in shingles:
            m.update(s.encode('utf-8'))

        return m

    def is_exist(self, text_content:str, text_id:str) -> bool:
        minhash = self._calculate_minhash(text_content)
        similar_docs = self.lsh.query(minhash)
        is_duplicate = len(similar_docs) != 0

        if not is_duplicate:
            doc_id = text_id
            self.lsh.insert(doc_id, minhash)
        
        return is_duplicate

    def filter_duplicated(self, text: str, text_id:str) -> str:
        if self.is_exist(text, text_id): return ""
        return text
