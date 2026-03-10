from crawl4ai import CrawlResult
from crawl4ai.adaptive_crawler import StatisticalStrategy, EmbeddingStrategy, CrawlState
import underthesea


from typing import List

import string
import re
import logging
from app.core.config.settings import PARENT

LOGGER = logging.getLogger("StrategyLog")
PATH = PARENT / "stopwords" / "stopwords.txt"


class VNEmbeddingStrategy(EmbeddingStrategy):...
    # """
    # A subclass of EmbeddingStrategy that runs models locally 
    # via Sentence-Transformers, completely bypassing LiteLLM/OpenAI.
    # """
    
    # def __init__(self, embedding_model: Optional[str] = None, **kwargs):
    #     # Set default to your Vietnamese model
    #     model_name = embedding_model or "AITeamVN/Vietnamese_Embedding_v2"
    #     super().__init__(embedding_model=model_name, **kwargs)
        
    #     print(f"Loading local embedding model: {self.embedding_model}...")
    #     # Initialize model on CPU or GPU
    #     self.local_model = SentenceTransformer(self.embedding_model)
    #     print("Model loaded successfully.")

    # # ------------------------------------------------------------------------
    # # 1. THE CORE EMBEDDING FUNCTION (Runs in Thread)
    # # ------------------------------------------------------------------------
    # async def _get_embeddings(self, texts: List[str]) -> Any:
    #     """Generate embeddings locally without freezing the async loop."""
    #     if not texts:
    #         return np.array([])

    #     def run_inference():
    #         return self.local_model.encode(
    #             texts, 
    #             batch_size=32, 
    #             show_progress_bar=False, 
    #             convert_to_numpy=True,
    #             normalize_embeddings=True 
    #         )

    #     loop = asyncio.get_event_loop()
    #     return await loop.run_in_executor(None, run_inference)

    # # ------------------------------------------------------------------------
    # # 2. OVERRIDE: QUERY EXPANSION (Skip OpenAI)
    # # ------------------------------------------------------------------------
    # async def map_query_semantic_space(self, query: str, n_synthetic: int = 10) -> Any:
    #     """Skip LLM generation and just use the query itself."""
    #     print(f"Skipping LLM query expansion for '{query}' (Local Mode)")
        
    #     # Create dummy variations (just the original query)
    #     train_queries = [query]
    #     if n_synthetic > 0:
    #         train_queries.append(query.lower()) 
        
    #     train_embeddings = await self._get_embeddings(train_queries)
    #     self._validation_queries = [query]
        
    #     return train_embeddings, train_queries

    # # ------------------------------------------------------------------------
    # # 3. OVERRIDE: UPDATE STATE (Fixes your Traceback)
    # # ------------------------------------------------------------------------
    # async def update_state(self, state: CrawlState, new_results: List[CrawlResult]) -> None:
    #     """
    #     Modified to call self._get_embeddings() instead of utils.get_text_embeddings().
    #     """
    #     # Extract text from results
    #     new_texts = []
    #     valid_results = []
    #     for result in new_results:
    #         content = result.markdown.raw_markdown if hasattr(result, 'markdown') and result.markdown else ""
    #         if content: 
    #             new_texts.append(content[:5000])  # Limit text length
    #             valid_results.append(result)
            
    #     if not new_texts:
    #         return
            
    #     # --- CHANGE IS HERE: Use local method instead of utility ---
    #     new_embeddings = await self._get_embeddings(new_texts)
    #     # -----------------------------------------------------------

    #     # Deduplicate embeddings before adding to KB
    #     if state.kb_embeddings is None:
    #         state.kb_embeddings = new_embeddings
    #         deduplicated_indices = list(range(len(new_embeddings)))
    #     else:
    #         deduplicated_embeddings = []
    #         deduplicated_indices = []
            
    #         for i, new_emb in enumerate(new_embeddings):
    #             new_emb_normalized = new_emb / np.linalg.norm(new_emb)
    #             kb_normalized = state.kb_embeddings / np.linalg.norm(state.kb_embeddings, axis=1, keepdims=True)
    #             similarities = np.dot(kb_normalized, new_emb_normalized)
                
    #             if np.max(similarities) < self._kb_similarity_threshold:
    #                 deduplicated_embeddings.append(new_emb)
    #                 deduplicated_indices.append(i)
            
    #         if deduplicated_embeddings:
    #             state.kb_embeddings = np.vstack([state.kb_embeddings, np.array(deduplicated_embeddings)])
        
    #     for idx in deduplicated_indices:
    #         state.crawl_order.append(valid_results[idx].url)
        
    #     self._kb_embeddings_hash = None
    #     self._distance_matrix_cache = None
            
    #     if hasattr(state, 'query_embeddings') and state.query_embeddings is not None:
    #         state.coverage_shape = self.compute_coverage_shape(state.query_embeddings, 0.5)

    # # ------------------------------------------------------------------------
    # # 4. OVERRIDE: LINK SELECTION (Fixes future ranking error)
    # # ------------------------------------------------------------------------
    # def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
    #     """Calculate cosine similarity between two vectors"""
    #     dot_product = np.dot(vec1, vec2)
    #     norm_product = np.linalg.norm(vec1) * np.linalg.norm(vec2)
    #     return float(dot_product / norm_product) if norm_product != 0 else 0.0
    
    # async def select_links_for_expansion(self, candidate_links: List[Link], gaps: List[Tuple[Any, float]], kb_embeddings: Any) -> List[Tuple[Link, float]]:
    #     """
    #     Modified to call self._get_embeddings() for link scoring.
    #     """
    #     scored_links = []
    #     links_to_embed = []
    #     texts_to_embed = []
    #     link_embeddings_map = {}
        
    #     for link in candidate_links:
    #         link_text = ' '.join(filter(None, [
    #             link.text or '', 
    #             link.title or '',
    #             link.meta.get('description', '') if hasattr(link, 'meta') and link.meta else '', # type:ignore
    #             link.head_data.get('meta', {}).get('description', '') if link.head_data else ''
    #         ]))
            
    #         if not link_text.strip(): continue
            
    #         cache_key = hashlib.md5(f"{link.href}:{link_text}".encode()).hexdigest()
            
    #         if cache_key in self._link_embedding_cache:
    #             link_embeddings_map[link.href] = self._link_embedding_cache[cache_key]
    #         else:
    #             links_to_embed.append(link)
    #             texts_to_embed.append(link_text)
        
    #     if texts_to_embed:
    #         # --- CHANGE IS HERE: Use local method ---
    #         new_embeddings = await self._get_embeddings(texts_to_embed)
    #         # ----------------------------------------

    #         for link, text, embedding in zip(links_to_embed, texts_to_embed, new_embeddings):
    #             cache_key = hashlib.md5(f"{link.href}:{text}".encode()).hexdigest()
    #             self._link_embedding_cache[cache_key] = embedding
    #             link_embeddings_map[link.href] = embedding
        
    #     # ... (Rest of scoring logic remains standard) ...
    #     # Simplified scoring logic for brevity (Standard cosine logic)
    #     coverage_radius = 0.2
    #     for link in candidate_links:
    #         if link.href not in link_embeddings_map: continue
    #         link_emb = link_embeddings_map[link.href]
            
    #         score = 0.0
    #         if gaps:
    #             total_improvement = 0
    #             gaps_helped = 0
    #             for gap_point, gap_dist in gaps:
    #                 if gap_dist > coverage_radius:
    #                     dist = self._cosine_similarity(link_emb, gap_point)
    #                     if dist < gap_dist:
    #                         total_improvement += (gap_dist - dist) * 2
    #                         gaps_helped += 1
                
    #             if gaps_helped > 0:
    #                 score = total_improvement / gaps_helped

    #         scored_links.append((link, score))
            
    #     return sorted(scored_links, key=lambda x: x[1], reverse=True)


class VNStatistcalStrategy(StatisticalStrategy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print(PATH)
        self.stopwords = self._load_stopwords(PATH)

    def _load_stopwords(self, path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return set(line.strip().replace(' ', '_') for line in f if line.strip())
        except FileNotFoundError:
            LOGGER.warning("No stopwords list has found?")
            return set()

    def _tokenize(self, text: str) -> List[str]:
        """The main injection pipeline for Vietnamese text"""
        if not text: return []

        text = re.sub('<.*?>', '', text).strip()
        text = re.sub(r'\s+', ' ', text)
        text = underthesea.text_normalize(text)

        segmented_text = underthesea.word_tokenize(text.lower(), format="text")
        listpunctuation = string.punctuation.replace('_', '')

        for p in listpunctuation:
            segmented_text = segmented_text.replace(p, ' ') # type: ignore
           
        tokens = [t for t in segmented_text.split() if t not in self.stopwords and len(t) > 1] # type: ignore
        return tokens
    
    async def update_state(self, state: CrawlState, new_results: List[CrawlResult]) -> None:
        """Update state with new crawl results, with aggressive noise filtering"""
        
        noise_patterns = [
            (r'!\[.*?\]\(.*?\)', ''),      # Delete images
            (r'\[([^\]]+)\]\(.*?\)', r'\1'), # Keep link text, delete URL
            (r'https?://\S+|www\.\S+', ''),  # Delete raw URLs
            (r'\b(imagekit|tvlk|traveloka|asset|imageresource|dpr|vnd|jpg|png|webp)\b', ''), # Delete tech keywords
            (r'\b(tiết kiệm|khuyến mãi|khuyến_mại|coupon)\b', ''), # Delete advertise keyword
            (r'\b(close|open|lê_thị|thg|copied)', ''), # other trash keywords,
            (r'\b(bạn)', ''), # domain stopword
            (r'[^\w\sà-ỹÀ-Ỹ.,-]', ' '),    # Remove weird symbols (keep Vietnamese accents)
        ]

        for result in new_results:
            old_term_count = len(state.term_frequencies)
            
            # 1. Safely extract content
            content = ""
            try:
                if result.markdown and result.markdown.raw_markdown:
                    content = result.markdown.raw_markdown
            except AttributeError:
                pass
            
            if not content:
                continue

            # 2. CLEANING: Apply regex filters sequentially
            clean_content = content
            for pattern, replacement in noise_patterns:
                clean_content = re.sub(pattern, replacement, clean_content, flags=re.IGNORECASE)
            
            # Collapse whitespace
            clean_content = re.sub(r'\s+', ' ', clean_content).strip()
            
            # Skip if the page was just a gallery/empty wrapper
            if len(clean_content) < 50:
                continue

            # 3. Tokenize the CLEANED content
            # (Your tokenizer will now see "Bảo tàng" instead of "https://...")
            terms = self._tokenize(clean_content.lower())
            
            # 4. Update Frequencies (Standard logic)
            term_set = set()
            for term in terms:
                # Extra check: Ignore pure numbers (e.g. '16', '2024') and single chars
                if len(term) > 1 and not term.isdigit():
                    state.term_frequencies[term] += 1
                    term_set.add(term)
            
            # Update doc frequencies
            doc_id = state.total_documents
            for term in term_set:
                if term not in state.documents_with_terms:
                     state.documents_with_terms[term] = set()
                
                if doc_id not in state.documents_with_terms[term]:
                    state.document_frequencies[term] += 1
                    state.documents_with_terms[term].add(doc_id)
            
            # Track growth
            new_term_count = len(state.term_frequencies)
            state.new_terms_history.append(new_term_count - old_term_count)
            
            state.total_documents += 1
            state.crawl_order.append(result.url)
