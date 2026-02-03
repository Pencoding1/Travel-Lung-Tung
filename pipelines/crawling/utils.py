import os
import torch
from torch.nn.functional import cosine_similarity
from sentence_transformers import SentenceTransformer
from crawl4ai.deep_crawling.filters import ContentRelevanceFilter
from crawl4ai.utils import HeadPeekr
from typing_extensions import override

def load_js(filename="expand_script.js"):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    return ""

class BatchedEmbeddingFilter(ContentRelevanceFilter):
    def __init__(self, query, threshold, batch_size=16, model_name="all-MiniLM-L6-v2"):
        super().__init__(query, threshold)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = SentenceTransformer(model_name, device=self.device)
        self.query_embedding = self.model.encode(self.query, convert_to_tensor=True)
        self.batch_size = batch_size
        self.buffer = []
        self.scores_cache = {}

    @override
    async def apply(self, url: str) -> bool:
        head_content = await HeadPeekr.peek_html(url)
        if not head_content: return False
        doc_text = self._build_document({
            "title": HeadPeekr.get_title(head_content) or "",
            "meta": HeadPeekr.extract_meta_tags(head_content),
        })
        self.buffer.append((url, doc_text))
        if len(self.buffer) >= self.batch_size:
            await self._run_batch_inference()
        return self.scores_cache.get(url, True)

    async def _run_batch_inference(self):
        if not self.buffer: return
        urls, texts = zip(*self.buffer)
        doc_embeddings = self.model.encode(list(texts), batch_size=self.batch_size, convert_to_tensor=True)
        scores = cosine_similarity(self.query_embedding.mean(dim=0, keepdim=True), doc_embeddings)
        for url, score in zip(urls, scores):
            self.scores_cache[url] = score.item() >= self.threshold
        self.buffer.clear()

    async def flush(self):
        if self.buffer: await self._run_batch_inference()