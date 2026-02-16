
from abc import ABC, abstractmethod
from typing import Dict, Optional, Union, List, Any

from crawl4ai import (
    CrawlerRunConfig, 
    DefaultMarkdownGenerator, 
    AsyncWebCrawler,
    BrowserConfig
)

from config.crawling_cofig import CrawlerGlobalConfig
from pipelines.crawling.base.PipelineBase import BasePipelineCrawler

class baseDetailCrawler(BasePipelineCrawler, ABC):
    def __init__(self,
                 cfg: Optional[CrawlerGlobalConfig] = None,
                 crawler_config: Optional[CrawlerRunConfig] = None,
                 markdown_creator: Optional[DefaultMarkdownGenerator] = None,
                 browser_config: Optional[BrowserConfig]=None,
                ):
        
        super().__init__(config=cfg, run_config=crawler_config)
        
        if browser_config:
            self.cfg.browser_config = browser_config

        self.crawler_config = crawler_config if crawler_config else CrawlerRunConfig()
        
        if markdown_creator:
            self.crawler_config.markdown_generator = markdown_creator
        self.crawler_config.magic = True
    
    @abstractmethod
    def init_js(
            self, 
            use_default_script:bool=True, 
            excluded_xpath: Union[str, List[str], None] = None, 
            dynamic_extraction_params: Optional[Dict[str, Any]] = None
        ) -> List[str]:...
    
    async def crawl(self, url: Union[List[str], str]):
        """Executes the crawler."""
        script = self.init_js()
        
        if script:
            self.crawler_config.js_code = script
            self.crawler_config.js_only = False 

        async with AsyncWebCrawler(config=self.cfg.browser_config) as crawler:
            if isinstance(url, list):
                results = await crawler.arun_many(url, config=self.crawler_config)
            elif isinstance(url, str):
                results = await crawler.arun(url, config=self.crawler_config)
            else:
                raise ValueError("Invalid url type. Must be str or list[str].")

        return results