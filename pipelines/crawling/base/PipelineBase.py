import os
import logging
import json

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union
from concurrent.futures import ThreadPoolExecutor

from crawl4ai import CrawlerRunConfig, CrawlResult
from models.embeddings.model_loader import SharedModel

from utils.embedding_filter import Semantic_Filter
from config.crawling_cofig import CrawlerGlobalConfig

# Setup Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('BaseCrawler')
ai_executor = ThreadPoolExecutor(max_workers=2)

class BasePipelineCrawler(ABC):
    def __init__(
            self,
            config: Optional[CrawlerGlobalConfig]=None,
            run_config: Optional[CrawlerRunConfig]=None,
            logger=None
    ):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.cfg = config if config else CrawlerGlobalConfig()
        self.run_config = run_config
        self.results_data = []
        self.browser_cfg = self.cfg.browser_config
        
        if self.cfg.use_embedding:
            model = SharedModel.get_model(model_name=os.environ["EMBEDDING_MODEL"])
            self.semantic_filter = Semantic_Filter(model=model)
        self.local_storage = os.environ.get("LOCAL_STORAGE", "./data")
    
    @abstractmethod
    def get_domain_name(self) -> str:
        pass

    def _generate_filename(self, stt: Any, ext: str) -> str:
        place = getattr(self, 'place_name', 'unknown').lower().replace(" ", "_")
        topic = getattr(self, 'topic_keyword', 'general_scan')
        domain = self.get_domain_name()
        lang = getattr(self, 'lang_code', 'vi')
        return f"{place}_{topic}_{domain}_{lang}_{stt}.{ext}"

    def _generate_list_filename(self) -> str:
        place = getattr(self, 'place_name', 'unknown').lower().replace(" ", "_")
        topic = getattr(self, 'topic_keyword', 'general_scan')
        domain = self.get_domain_name()
        lang = getattr(self, 'lang_code', 'vi')
        return f"{place}_{topic}_{domain}_{lang}_List.json"

    def _save_item_to_disk(self, data: Dict):
        domain = self.get_domain_name()
        place = getattr(self, 'place_name', 'general')
        path = os.path.join(self.local_storage, domain, place)
        os.makedirs(path, exist_ok=True)

        stt = len(self.results_data) + 1
        filename_md = self._generate_filename(stt, "md")
        file_path = os.path.join(path, filename_md)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(data['content'])

        meta = {
            "stt": stt,
            "filename": filename_md,
            "url": data.get("url"),
            "source": domain,
            "local_path": file_path
        }
        self.results_data.append(meta)
        logger.info(f"Saved: {filename_md}")

    def save_item(self, data: Dict):
        if self.cfg.store_destination == "local":
            self._save_item_to_disk(data)
        else:
            self._save_to_db(data)

    def _save_to_db(self, data: Dict): ...

    def save_metadata_json(self, output_folder: str):
        if not self.results_data:
            self.logger.warning("No data to save to JSON list.")
            return

        domain = self.get_domain_name()
        place = getattr(self, 'place_name', 'general')
        path = os.path.join(output_folder, domain, place)
        os.makedirs(path, exist_ok=True)

        json_filename = self._generate_list_filename()
        json_path = os.path.join(path, json_filename)

        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(self.results_data, f, ensure_ascii=False, indent=4)
            self.logger.info(f" Saved List JSON: {json_path}")
        except Exception as e:
            self.logger.error(f"Failed to save JSON list: {e}")

    @abstractmethod
    async def crawl(self, url:Union[List[str], str]) -> CrawlResult:...

    