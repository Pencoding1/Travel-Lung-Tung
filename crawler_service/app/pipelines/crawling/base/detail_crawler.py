import functools

from abc import ABC, abstractmethod
from typing import Optional, List, Callable, Tuple

from crawl4ai import (
    CrawlResult,
    DefaultMarkdownGenerator, 
    AsyncWebCrawler,
    JsonXPathExtractionStrategy,
    JsonCssExtractionStrategy,
)

from app.core.config.settings import LoadPipelineSetting
from app.pipelines.crawling.base.PipelineBase import BasePipelineCrawling

def run_with_hook(hook_method_name: str = "get_hook"):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            crawler = AsyncWebCrawler(config=self.cfg.crawler_cfg.browser_config)

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

class BaseDetailCrawler(BasePipelineCrawling, ABC):
    def __init__(self,
                 cfg: LoadPipelineSetting,
                 markdown_creator: Optional[DefaultMarkdownGenerator] = None,
                 use_magic=True
                ):
        super().__init__(config=cfg)
        self.cfg.crawler_cfg.run_cfg.magic = use_magic

        if markdown_creator:
            self.cfg.crawler_cfg.run_cfg.markdown_generator = markdown_creator
        
        self.cfg.crawler_cfg.run_cfg.magic = True
        self.schemas: Optional[dict] = None
    
    async def crawl_with_schema(self,
                                    url: str | List[str], 
                                    verbose: bool = True):
            if self.schemas:
                if self.schemas['type'] == "css":
                    extraction_strategy = JsonCssExtractionStrategy(self.schemas['schema'], verbose=verbose)
                elif self.schemas['type'] == "xpath":
                    extraction_strategy = JsonXPathExtractionStrategy(self.schemas['schema'], verbose=verbose)
                else:
                    raise ValueError("Invalid type of schema.")
            else:
                raise ValueError("Schema cannot empty. In case of LLM Extraction or no extraction provided please use crawl().")

            self.cfg.crawler_cfg.run_cfg.extraction_strategy = extraction_strategy
            results = await self.crawl(seed_url=url)
            return results

    @run_with_hook()
    async def crawl(self, seed_url: str | List[str], crawler=None) -> Optional[CrawlResult]:
        """Executes the crawler."""
        if crawler:
            if isinstance(seed_url, list):
                results = await crawler.arun_many(seed_url, config=self.cfg.crawler_cfg.run_cfg)
            elif isinstance(seed_url, str):
                results = await crawler.arun(seed_url, config=self.cfg.crawler_cfg.run_cfg)
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