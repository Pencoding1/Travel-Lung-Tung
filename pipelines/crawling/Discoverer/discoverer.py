import re
import json
import logging

from pathlib import Path
from typing import Optional

from utils.discover_strategies import VNEmbeddingStrategy, VNStatistcalStrategy

from config.discover_config import DiscoverSettings

import networkx as nx

from crawl4ai import CrawlState, AsyncWebCrawler, BrowserConfig
from crawl4ai.adaptive_crawler import AdaptiveCrawler, AdaptiveConfig

class Discoverer:
    def __init__(self, 
                 discover_config: Optional[DiscoverSettings]=None,
                 adaptive_config: Optional[AdaptiveConfig]=None,
                 browser_config: Optional[BrowserConfig]=None):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.browser_config = browser_config
        self.adaptive_config = adaptive_config
        self.discover_config = discover_config if discover_config else DiscoverSettings()
        self.discover_config.ensure_paths()
    
    async def discover(self, url:str) -> CrawlState:
        if self.discover_config.strategy_type == "statistical":
            strategy = VNStatistcalStrategy()
        elif self.discover_config.strategy_type == "embedding":
            pass # NOTE: Since the embedding is unusedable so we cannot implement it.

        async with AsyncWebCrawler(config=self.discover_config.get_browser_config(self.browser_config),
                                    base_directory=self.discover_config.base_directory) as crawler: # type: ignore
            adaptive = AdaptiveCrawler(crawler, config=self.discover_config.get_adaptive_config(self.adaptive_config), strategy=strategy)
            query = self.discover_config.query if self.discover_config.query else "Nothing happend yeah"

            result = await adaptive.digest(
                start_url=url,
                query=query,
            )

            relevant_pages = adaptive.get_relevant_content(top_k=self.discover_config.top_k)
            for page in relevant_pages:
                self.logger.info(f"- {page['url']} (score: {page['score']:.2f})")

            if self.discover_config.get_knowledge_base:
                adaptive.export_knowledge_base(self.discover_config.graph_output_path)
                
        return result

    def filtering_by_content(self, included_pattern:re.Pattern, excluded_pattern: re.Pattern) -> nx.DiGraph:
        """
        Filters the raw graph data based on content rules (HCM specific, exclude list, scores).
        Returns a NetworkX DiGraph object instead of plotting.
        """
        # Resolve defaults from Settings if not provided
        G = nx.DiGraph()
        if isinstance(self.discover_config.graph_output_path, str):
            self.discover_config.graph_output_path = Path(self.discover_config.graph_output_path)
        if not self.discover_config.graph_output_path.exists():
            self.logger.error(f"Graph file not found at: {self.discover_config.graph_output_path}")
            return G

        self.logger.info(f"Filtering content from {self.discover_config.graph_output_path} with threshold {self.discover_config.weight_threshold}...")

        with open(self.discover_config.graph_output_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                source_url = data.get('url', '')
                
                # Enforce HCM location relevance
                if not re.search(included_pattern, source_url.lower()) or re.search(excluded_pattern, source_url.lower()):
                    continue

                # --- 2. Source Node Confidence Filtering ---
                crawl_weight = data.get('crawl_metadata', {}).get('confidence_at_crawl', 0.0)
                
                if crawl_weight < self.discover_config.weight_threshold:
                    continue

                # Title Processing (Traveloka specific clean-up)
                source_meta = data.get('metadata', {})
                prefix = "https://traveloka.com/vi-vn/"
                if source_url.startswith(prefix):
                    source_title = source_url[len(prefix):].strip('/').replace('-', ' ')
                else:
                    source_title = source_meta.get('title') or source_url

                # Add Valid Source Node
                G.add_node(source_url, 
                           label=source_title, 
                           confidence=crawl_weight,
                           type="source")

                # --- 3. Edge/Link Filtering ---
                links = data.get('links', {}).get('internal', [])
                for link in links:
                    target_url = link.get('href')
                    
                    # Check against Excluded List (from Settings)
                    if not target_url or target_url in self.discover_config.excluded_urls:
                        continue
                    
                    relevance_score = link.get('contextual_score') or 0.0
                    
                    # Filter weak links
                    if relevance_score < self.discover_config.weight_threshold:
                        continue
                    
                    # Prepare Target Node Label
                    raw_label = link.get('title') or link.get('text')
                    target_label = raw_label if raw_label and raw_label != "Unknown" else target_url
                    
                    # Add Target Node if not exists (or update attributes)
                    if target_url not in G:
                        G.add_node(target_url, label=target_label, type="target")
                    
                    # Add Edge with weight
                    G.add_edge(source_url, target_url, weight=relevance_score)

        self.logger.info(f"Filtering complete. Graph contains {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
        return G
    

if __name__ == "__main__":
    import asyncio
    import shutil
    
    # 1. DEFINE TEST SETTINGS
    # We use a temporary directory for the test output to avoid messing up your real data
    TEST_DIR = Path("./test_output_env")
    TEST_GRAPH_PATH = TEST_DIR / "test_knowledge_graph.json"
    
    # Ensure clean state
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)
    TEST_DIR.mkdir(parents=True, exist_ok=True)

    async def run_full_pipeline_test():
        print("\n" + "="*60)
        print("🚀 STARTING FULL PIPELINE TEST (Real Crawl -> Graph)")
        print("="*60)

        # --- STEP 1: CONFIGURATION ---
        print("[1/4] Configuring Discoverer for Test Mode...")
        
        # Override settings for a "Micro-Crawl"
        # We limit max_pages to 3 to ensure the test finishes in <10 seconds
        test_settings = DiscoverSettings(
            base_directory=TEST_DIR / "cache",
            graph_output_path=TEST_GRAPH_PATH,
            stats_file=TEST_DIR / "stats.txt",
            weight_threshold=0.1,  # Lower threshold to ensure we get *some* data for the test
            strategy_type="statistical",
            query="Find interesting activities and locations in Ho Chi Minh City"
        )
        
        # Custom Adaptive Config to stop it from running wild
        test_adaptive_config = AdaptiveConfig(
            max_pages=3,       # HARD LIMIT: Only crawl 3 pages max
            max_depth=1,       # HARD LIMIT: Do not go deep
            confidence_threshold=0.5
        )

        discoverer = Discoverer(
            discover_config=test_settings,
            adaptive_config=test_adaptive_config
        )

        # --- STEP 2: DISCOVERY (THE CRAWL) ---
        start_url = "https://www.traveloka.com/vi-vn/destination/area/ho-chi-minh-city-10009794"
        print(f"[2/4] crawling target: {start_url}")
        print("      (This may take 10-20 seconds depending on network...)")
        
        try:
            # Run the actual crawl
            await discoverer.discover(start_url)
            print("      ✅ Crawl finished.")
        except Exception as e:
            print(f"      ❌ Crawl failed: {e}")
            return

        # Check if file exists
        if not TEST_GRAPH_PATH.exists():
            print("      ❌ Error: Graph file was not created!")
            return
        
        file_size = TEST_GRAPH_PATH.stat().st_size
        print(f"      ✅ Graph file created at: {TEST_GRAPH_PATH} ({file_size} bytes)")

        # --- STEP 3: FILTERING & GRAPH FORMULATION ---
        print("[3/4] Building Graph from Crawled Data...")
        
        # Define regex for Ho Chi Minh City
        include_pattern = re.compile(r'(ho-chi-minh|hcm|sai-gon|saigon|tphcm)', re.IGNORECASE)
        # Define regex to exclude purely functional pages
        exclude_pattern = re.compile(r'/(login|register|forgot-password|promotion|partnership)/', re.IGNORECASE)

        # Run the filtering logic
        G = discoverer.filtering_by_content(include_pattern, exclude_pattern)

        # --- STEP 4: VERIFICATION ---
        print("[4/4] Verifying Results...")
        
        node_count = G.number_of_nodes()
        edge_count = G.number_of_edges()
        
        print("\n" + "-"*40)
        print(f"📊 FINAL GRAPH: {node_count} Nodes | {edge_count} Edges")
        print("-" * 40)

        if node_count > 0:
            print("✅ TEST PASSED: Graph was successfully built from real web data.")
            
            # Print first 3 nodes as a sample
            print("\nSample Nodes:")
            for i, (node, attrs) in enumerate(list(G.nodes(data=True))[:3]):
                print(f"  {i+1}. {attrs.get('label', 'No Label')} ({node})")
        else:
            print("⚠️  TEST WARNING: Graph is empty.")
            print("   Possible reasons:")
            print("   1. The crawler got blocked (check logs).")
            print("   2. The Regex pattern didn't match any crawled URLs.")
            print("   3. The 'weight_threshold' is too high for the crawled data.")

    # Run the test
    asyncio.run(run_full_pipeline_test())

    # TODO: FIX TESTING PROCESS