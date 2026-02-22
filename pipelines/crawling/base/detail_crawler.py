import functools

from abc import ABC, abstractmethod
from typing import Dict, Optional, List, Any, Callable, Tuple

from crawl4ai import (
    CrawlerRunConfig, 
    CrawlResult,
    DefaultMarkdownGenerator, 
    AsyncWebCrawler,
    JsonXPathExtractionStrategy,
    JsonCssExtractionStrategy,
    BrowserConfig,
)

from config.crawling_cofig import CrawlerGlobalConfig

from pipelines.crawling.Discoverer.discoverer import Discoverer
from pipelines.crawling.base.PipelineBase import BasePipelineCrawler

def run_with_hook(hook_method_name: str = "get_hook"):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            crawler = AsyncWebCrawler(config=self.cfg.browser_config)

            if hasattr(self, hook_method_name):
                hook_method = getattr(self, hook_method_name)
                hook_result = hook_method()
                if isinstance(hook_result, tuple):
                    if hook_result[0]:
                        crawler.crawler_strategy.set_hook(hook_result[1], hook_result[0]) # type: ignore
                else:
                    # TODO: handle complex hook
                    pass
                
            await crawler.start()
            try:
                kwargs['crawler'] = crawler
                result = await func(self, *args, **kwargs)
            finally:
                await crawler.close()

            return result
        return wrapper
    return decorator    

class BaseDetailCrawler(BasePipelineCrawler, ABC):
    def __init__(self,
                 cfg: Optional[CrawlerGlobalConfig] = None,
                 crawler_config: Optional[CrawlerRunConfig] = None,
                 markdown_creator: Optional[DefaultMarkdownGenerator] = None,
                 browser_config: Optional[BrowserConfig]=None, discoverer: Optional[Discoverer]=None
                ):
        
        super().__init__(config=cfg, run_config=crawler_config)
        
        if browser_config:
            self.cfg.browser_config = browser_config

        self.crawler_config = crawler_config if crawler_config else CrawlerRunConfig()
        
        if markdown_creator:
            self.crawler_config.markdown_generator = markdown_creator
        self.crawler_config.magic = True

    
    async def crawl_with_schema(self,
                                url: str | List[str], 
                                schema_css: Optional[Dict[str, Any]]=None,
                                schema_xpath: Optional[Dict[str, Any]]=None, 
                                verbose: bool = True):
        if schema_xpath:
            extraction_strategy = JsonXPathExtractionStrategy(schema_xpath, verbose=verbose)
        elif schema_css:
            extraction_strategy = JsonCssExtractionStrategy(schema_css, verbose=verbose)
        else:
            raise ValueError("Schema cannot empty. In case of LLM Extraction or no extraction provided please use crawl().")

        self.crawler_config.extraction_strategy=extraction_strategy

        results = await self.crawl(seed_url=url)

        return results

    @run_with_hook()
    async def crawl(self, seed_url: str | List[str], crawler=None) -> Optional[CrawlResult]:
        """Executes the crawler."""
        if crawler:
            if isinstance(seed_url, list):
                results = await crawler.arun_many(seed_url, config=self.crawler_config)
            elif isinstance(seed_url, str):
                results = await crawler.arun(seed_url, config=self.crawler_config)
            else:
                raise ValueError("Invalid url type. Must be str or list[str].")
        
            return results
        return None
    
    @abstractmethod
    def get_hook(self) -> Tuple[Callable, str]:
        """
            Perform a hook before go to the target page.
        """
        ...