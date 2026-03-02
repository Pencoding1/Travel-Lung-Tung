import re
import logging

from typing import Optional, Dict

from utils.discover_strategies import VNEmbeddingStrategy, VNStatistcalStrategy

from config.discover_config import DiscoverSettings

from crawl4ai import (CrawlState, 
                    AsyncWebCrawler, 
                    BrowserConfig, 
                    CrawlStrategy,
                    CrawlResult,
                    CrawlerRunConfig,
                    LinkPreviewConfig
                    ) 
from crawl4ai.adaptive_crawler import AdaptiveCrawler, AdaptiveConfig

class ModifiedAdaptiveCrawler(AdaptiveCrawler):
    def __init__(self, 
                 crawler_run_config: Optional[CrawlerRunConfig]=None, 
                 crawler: AsyncWebCrawler | None = None, 
                 config: AdaptiveConfig | None = None, 
                 strategy: CrawlStrategy | None = None):
        
        super().__init__(crawler, config, strategy)
        self.crawler_run_config: CrawlerRunConfig = crawler_run_config if crawler_run_config else CrawlerRunConfig()

    async def _crawl_with_preview(self, url: str, query: str) -> Optional[CrawlResult]:
        """Crawl a URL with link preview enabled"""
        link_preview_config = LinkPreviewConfig(
                                                include_internal=True,
                                                include_external=False,
                                                query=query,  # For BM25 scoring
                                                concurrency=5,
                                                timeout=5,
                                                max_links=50,  # Reasonable limit
                                                verbose=False
                                            )
        if not self.crawler_run_config:
            self.crawler_run_config = CrawlerRunConfig(
                magic=True,
                delay_before_return_html=3,
                link_preview_config=link_preview_config,
                score_links=True  # Enable intrinsic scoring
            )
        else:
            self.crawler_run_config.link_preview_config = link_preview_config
            self.crawler_run_config.score_links = True
        
        try:
            result = await self.crawler.arun(url=url, config=self.crawler_run_config) #type: ignore
            
            # Extract the actual CrawlResult from the container
            if hasattr(result, '_results') and result._results: #type: ignore
                result = result._results[0] #type: ignore

            # Filter our all links do not have head_date
            if hasattr(result, 'links') and result.links: #type: ignore
                result.links['internal'] = [link for link in result.links['internal'] if link.get('head_data')] #type: ignore

            return result #type: ignore
        except Exception as e:
            print(f"Error crawling {url}: {e}")
            return None
        

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

        self.discovery_result = None
    
    async def discover(self, url:str, print_stats: bool=False) -> CrawlState:
        if self.discover_config.strategy_type == "statistical":
            strategy = VNStatistcalStrategy()
        elif self.discover_config.strategy_type == "embedding":
            pass # NOTE: Since the embedding is unusedable so we cannot implement it.

        async with AsyncWebCrawler(config=self.discover_config.get_browser_config(self.browser_config),
                                    base_directory=self.discover_config.base_directory) as crawler: # type: ignore
            adaptive = ModifiedAdaptiveCrawler(crawler=crawler, config=self.discover_config.get_adaptive_config(self.adaptive_config), strategy=strategy)
            query = self.discover_config.query if self.discover_config.query else "Find useful thing."

            result = await adaptive.digest(
                start_url=url,
                query=query,
            )

            relevant_pages = adaptive.get_relevant_content(top_k=self.discover_config.top_k)
            for page in relevant_pages:
                self.logger.info(f"- {page['url']} (score: {page['score']:.2f})")

            if self.discover_config.get_knowledge_base:
                adaptive.export_knowledge_base(self.discover_config.graph_output_path)
        
        if print_stats:
            adaptive.print_stats(detailed=True)
        
        self.discovery_result = result
        return result
    
    def is_data_valid(self, 
                      source_url, 
                      confidence_score, 
                      included_pattern: re.Pattern, 
                      excluded_pattern: re.Pattern) -> bool:
        """
            Returns True if the data should be KEPT (Valid).
            Returns False if the data should be DISCARDED (Invalid).
        """
        is_excluded = re.search(excluded_pattern, source_url.lower()) is not None
        is_included = re.search(included_pattern, source_url.lower()) is not None
        
        is_invalid_url = is_excluded and not is_included

        if is_invalid_url or confidence_score < self.discover_config.weight_threshold:
            return False
        
        return True
    
    def connected_link_filtering(self, data: CrawlState,
                                 included_pattern: re.Pattern, 
                                 excluded_pattern: re.Pattern,
                                 threshold: float = 1.0) -> Optional[Dict]:
        qualified_links = dict()
        global_confidence = data.metrics.get('confidence', 0.0)
        
        if not data.knowledge_base:
            self.logger.warning("Knowledge base is empty.")
            return None

        for source_page in data.knowledge_base:
            source_url = source_page.url

            if self.is_data_valid(source_url, 
                                  included_pattern=included_pattern, 
                                  excluded_pattern=excluded_pattern,
                                  confidence_score=global_confidence):
                internal_links = []
                links_attr = getattr(source_page, 'links', {})
                
                if isinstance(links_attr, dict):
                    internal_links = links_attr.get('internal', [])
                elif hasattr(links_attr, 'internal'):
                    internal_links = links_attr.internal
                
                found_links_on_this_page = False

                for link in internal_links:
                    if isinstance(link, dict):
                        target_url = link.get('href')
                        score = link.get('total_score')
                    else:
                        target_url = getattr(link, 'href', None)
                        score = getattr(link, 'total_score', None)
                    
                    score = score or 0.0
                    
                    if target_url:
                        is_excluded_target = target_url in self.discover_config.excluded_urls
                        is_good_score = score >= threshold
                        
                        if not is_excluded_target and is_good_score:
                            qualified_links[target_url] = score
                            found_links_on_this_page = True 
                
                if not found_links_on_this_page:
                    self.logger.warning(f"The source page: {source_url} produced no qualified links.")
                    
        if not qualified_links:
            self.logger.warning("The provided data are invalid (no links found in total). Return None.")
            return None
        
        return qualified_links
        