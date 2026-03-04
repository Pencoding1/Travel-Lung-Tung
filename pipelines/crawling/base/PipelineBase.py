import logging

from abc import ABC, abstractmethod
from typing import List, Union
from concurrent.futures import ThreadPoolExecutor

from crawl4ai import CrawlResult

from config.settings import LoadPipelineSetting

# Setup Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('BaseCrawler')
ai_executor = ThreadPoolExecutor(max_workers=2)

class BasePipelineCrawling(ABC):
    def __init__(
            self,
            config: LoadPipelineSetting,
            logger=None
    ):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.cfg = config 
        self.run_config = self.cfg.crawler_cfg.run_cfg
        self.browser_cfg = self.cfg.crawler_cfg.browser_config
    
    @abstractmethod
    def get_domain_name(self) -> str:
        pass

    @abstractmethod
    async def crawl(self, url:Union[List[str], str]) -> CrawlResult:...

    