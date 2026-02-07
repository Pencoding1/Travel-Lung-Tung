import os
import torch
from typing import List
from sentence_transformers import SentenceTransformer, util
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer

def load_js(filename="expand_script.js"):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    return ""

# Dành cho Vietravel
def filter_location(filename="filter_location.js"):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def create_best_first_strategy(
    keywords: List[str],
    max_depth: int = 4,
    max_pages: int = 1000,
    weight: float = 0.8
) -> BestFirstCrawlingStrategy:
    if not keywords:
        keywords = ["du lịch", "kham pha", "review"]

    scorer = KeywordRelevanceScorer(
        keywords=keywords,
        weight=weight
    )

    return BestFirstCrawlingStrategy(
        max_depth=max_depth,
        max_pages=max_pages,
        url_scorer=scorer
    )

_model = None
_query_embedding = None

def init_semantic_filter(
    query: str,
    model_name: str = "AITeamVN/Vietnamese_Embedding_v2"
):
    global _model, _query_embedding

    device = "cuda" if torch.cuda.is_available() else "cpu"
    _model = SentenceTransformer(model_name, device=device)

    emb = _model.encode(query, convert_to_tensor=True)
    if emb.dim() == 1:
        emb = emb.unsqueeze(0)

    _query_embedding = emb


def is_relevant(markdown: str, threshold: float = 0.4) -> bool:
    if not markdown or _model is None or _query_embedding is None:
        return False

    emb = _model.encode(markdown[:3000], convert_to_tensor=True)
    if emb.dim() == 1:
        emb = emb.unsqueeze(0)

    score = util.cos_sim(_query_embedding, emb).item()
    return score >= threshold
