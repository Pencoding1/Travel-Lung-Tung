"""
    The crawling module for crawl valuable information with given seed url. The pipeline is:
    - Discoverer discovers high related links through validate metadata content using Statistical Strategy (the Embedding Stratergy haven't implemented yet.)
    - After discovering process, discoverer only keeps qualified link which is remove noise link (because Statistical Strategy cannot determine home link is qualified or not)
    - In the end the Detail Crawler receives qualified links and starting scrape the content then store the data in structured json file or database. For testing, json file will
    be priotired.
"""
import json
import asyncio
import logging

from datetime import datetime

from typing import List, Dict

from config.settings import *

from pipelines.crawling.discover.discoverer import Discoverer
from config.exceptions import IntentedNotImplementedException
from pipelines.crawling.detail_crawler.traveloka_crawler import TravelokaCrawler
from pipelines.preprocessing.preprocessing import TravelokaPreprocessor

class Crawler:
    def __init__(self, cfg: AppSettings,
                 seed_url: str,
                 ) -> None:
        
        self.cfg = cfg

        # Dang test tren browser profile co san
        self.cfg.load_settings[0].crawler_cfg.run_cfg.magic = False
        
        self.discoverer = Discoverer(cfg.load_settings[0])
        self.traveloka_cralwer = TravelokaCrawler(cfg.load_settings[0])
        self.url = seed_url
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def _write_cache(self, data: Dict, path:Path, file_name:str) -> Path:
        path.mkdir(exist_ok=True)
        json_data = json.dumps(data)
        cache_file = path / file_name
        cache_file.write_text(json_data)
        return path / file_name
    
    def _read_cache(self, file_path:Path) -> Optional[Dict]:
        if file_path.is_file() and file_path.exists():
            raw_data =file_path.read_text()
        try:
            data = json.loads(raw_data)
            return data
        except json.JSONDecodeError:
            self.logger.error("Write cache fail.")
            return None
        
    def _change_nation(self, urls:List[str]) -> List[str]:
        results = []
        
        for url in urls:
            prefixes = url.split("/")
            if prefixes[3] != "vi-vn":
                prefixes[3] = "vi-vn"
                results.append("/".join(prefixes))
            results.append(url)

        return results
    
    def _classifier(self, urls:List[str]) -> Dict[str, List[str]]:
        # the schema should be placed inside the config but with demo only I put it here.
        # TODO: place the url schema inside setting. 
        TRAVELOKA_URL_SCHEMA = {
            "hotel": [],
            "destinations": [],
            "activities": [],
            "explore": []
        }

        for url in urls:
            prefixes = url.split("/")
            if prefixes[4] in TRAVELOKA_URL_SCHEMA.keys():
                TRAVELOKA_URL_SCHEMA[prefixes[4]].append(url)
        
        return TRAVELOKA_URL_SCHEMA

    async def save_to_database(self):
        raise NotImplementedError("The database hasn't been implemented yet.")

    def save_to_local(self, data: Dict, file_name:str="Crawled_Results.json"):
        data_to_str = json.dumps(data, indent=4, ensure_ascii=False)
        (self.cfg.storage_path / file_name).write_text(data_to_str, encoding="utf-8")        
        
    async def pipeline(self):
        # ========I. Discover Phase========
        self.logger.info("Beginning discover phase....")

        # TODO: this still uses the first load_setting. If run crawl for many domains it will be a bug since the crawler always crawl at the Traveloka.
        if self.cfg.load_settings[0].cache_mode == CACHE_MODE.READ:
               cache_file = list((self.cfg.load_settings[0].discover_cfg.cache_path).glob("*.json"))
               cache_file.sort()
               classified_urls = self._read_cache(cache_file[0])
        else:
            if self.cfg.DEBUG:
                discovery_result = await self.discoverer \
                                        .discovery(self.url,
                                                  print_stats=True)
            else:
                discovery_result  = await self.discoverer \
                                         .discovery(self.url)

            final_result = self.discoverer.connected_link_filtering(discovery_result)
            if not final_result:        
                self.logger.warning("The discover result has no urls.")
                return

            noise_urls = list(final_result.keys())

            urls = self._change_nation(noise_urls)
            classified_urls = self._classifier(urls) # {"sub_domain" (this one is used to determine the crawl_type): url}
            if self.cfg.load_settings[0].cache_mode == CACHE_MODE.WRITE:
                    self._write_cache(classified_urls, self.cfg.load_settings[0].discover_cfg.cache_path, f"{int(datetime.now().timestamp())}.json") # type: ignore
        
        if not classified_urls:
            self.logger.warning("Discovery found nothing. Stop the pipeline.")
            return
    
        # ========II. Crawl Phase========
        # NOTE: the crawler now only return un-parsed result in dictionary type. Further Extraction to create parsed version are required
        # NOTE: Put it in data ingestion pipeline with preprocessing step.
        # NOTE: The discoverer seems uneffective due to only care about metadta.
        # NOTE: Already putted all loading script
        self.logger.info("Beginning crawling phase....")

        preprocessor = TravelokaPreprocessor(
            config=self.cfg.extract_settings[0], 
            lsh=None
        )
        
        detail_crawl_results = dict()
        for key, value in classified_urls.items():
            self.logger.info(f"Is crawling for {key}")
            try:
                results = []
                for url in value:
                    crawl_results = await self.traveloka_cralwer.crawl_with_schema(
                        url = url,
                        crawl_type=key
                    )
                    if crawl_results and crawl_results.success:
                        result = preprocessor.parse(
                                content=crawl_results.extracted_content,
                                crawl_type=key
                        )
                        #result = json.loads(crawl_results.extracted_content) \
                        #                    if crawl_results.extracted_content else None
                        if result is not None:
                            results.append(result)
                detail_crawl_results[key] = results
            except IntentedNotImplementedException:
                self.logger.warning(f"The extractor for {key} hasn't been implemented yet. Skipping this sub-domain.")
                continue

        if not detail_crawl_results:
            self.logger.warning("Extracted Results are empty.")
            return
        
        if self.cfg.STORAGE == "local":
            self.save_to_local(detail_crawl_results)        
        elif self.cfg.STORAGE == "db":
            raise IntentedNotImplementedException("Database hasn't been implemented yet.")
        else:
            raise ValueError("Invalid storage type.")



if __name__ == "__main__":
    url = "https://www.traveloka.com/vi-vn/destination/area/ho-chi-minh-city-10009794"
    
    load = LoadPipelineSetting(
        crawler_cfg=CrawlerSetting(),
        extractor_cfg=ExtractorSettings(),
        discover_cfg=DiscoverSettings()
    )
    extract = ExtractPipelineSetting(
        pipeline_cfg=IngestionSettings()
    )
    app_settings = AppSettings(
        load_settings=[load],
        extract_settings=[extract],
    )
    
    crawler = Crawler(app_settings, seed_url=url)
    
    # TEMPORARY WRITE CHANGE CACHE FLAG
    crawler.cfg.load_settings[0].cache_mode=CACHE_MODE.WRITE

    asyncio.run(crawler.pipeline())