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

from typing import List, Dict, Optional
from pathlib import Path

from torch import Value

from app.core.config.settings import AppSettings, ExtractPipelineSetting, LoadPipelineSetting

from app.pipelines.crawling.discover.discoverer import Discoverer
from app.pipelines.crawling.detail_crawler.traveloka_crawler import TravelokaCrawler
from app.pipelines.preprocessing.preprocessing import TravelokaPreprocessor

from travel_shared.exceptions import IntentedNotImplementedException
from travel_shared.schemas import CACHE_MODE
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
    
    def _read_cache(self, file_path: Path) -> Optional[Dict]:
        if not (file_path.is_file() and file_path.exists()):
            return None
        
        try:
            raw_data = file_path.read_text(encoding="utf-8")
            return json.loads(raw_data)
        except json.JSONDecodeError:
            self.logger.error(f"Read cache failed. Invalid JSON in {file_path}")
            return None
        
    def _change_nation(self, urls:List[str]) -> List[str]:
        results = []
        
        for url in urls:
            prefixes = url.split("/")
            if prefixes[3] != "vi-vn":
                prefixes[3] = "vi-vn"
                results.append("/".join(prefixes))
            else:
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
        data_to_str = json.dumps(data)
        (self.cfg.storage_path / file_name).write_text(data_to_str, encoding="utf-8")        
    
    async def discovery(self):
        # 1. Check Cache First
        first_setting = self.cfg.load_settings[0]
        if first_setting.cache_mode == CACHE_MODE.READ:
            cache_files = list(first_setting.discover_cfg.cache_path.glob("*.json"))
            if cache_files:
                cache_files.sort()
                self.logger.info("Reading URLs from cache...")
                return self._read_cache(cache_files[0])
            self.logger.warning("Cache mode is READ but no cache files found. Proceeding with discovery.")

        # 2. Perform Discovery (Run only once)
        self.logger.info("Beginning discover phase....")
        discovery_result = await self.discoverer.discovery(
            self.url, 
            print_stats=self.cfg.DEBUG
        )

        final_result = self.discoverer.connected_link_filtering(discovery_result)
        if not final_result:        
            self.logger.warning("The discover result has no urls. Pipeline stopped.")
            return None

        # 3. Process URLs
        noise_urls = list(final_result.keys())
        urls = self._change_nation(noise_urls)
        classified_urls = self._classifier(urls) 

        # 4. Write Cache if necessary
        if first_setting.cache_mode == CACHE_MODE.WRITE and classified_urls:
            file_name = f"{int(datetime.now().timestamp())}.json"
            self._write_cache(classified_urls, first_setting.discover_cfg.cache_path, file_name)

        return classified_urls

    async def __detail_crawl(self, url:str, crawl_type:str):
        preprocessor = TravelokaPreprocessor(
            config=self.cfg.extract_settings[0], 
            lsh=None
        )
        result = None
        
        try:
            crawl_results = await self.traveloka_cralwer.crawl_with_schema(
                            url = url,
                            crawl_type=crawl_type
                        )
            if crawl_results and crawl_results.success:
                result = preprocessor.parse(
                        content=crawl_results.extracted_content,
                        crawl_type=crawl_type
                    )
            else:
                self.logger.warning(f"Crawl result isn't success or cannot crawl from the targeted url.\nCrawled Result: {crawl_results}")
                return None
        
        except IntentedNotImplementedException:
            self.logger.warning(f"Extractor for '{crawl_type}' not implemented. Failed on URL: {url}")
        except Exception as e:
            self.logger.error(f"Unexpected error while crawling {url}: {e}")

        return result
    
    async def batch_detail_crawl(self, classified_urls: Dict, service=False):
        detail_crawl_results = dict()
        
        for key, urls in classified_urls.items():
            self.logger.info(f"Is crawling for sub-domain: {key}")
            results = []
            for url in urls:
                try:
                    result = await self.__detail_crawl(url, key)
                    if result is not None:
                        results.append(result)
                except IntentedNotImplementedException:
                    self.logger.warning(f"Extractor for '{key}' not implemented. Failed on URL: {url}")
                    break
                    
                except Exception as e:
                    self.logger.error(f"Unexpected error while crawling {url}: {e}")
                    continue
            
            # Only add the key to the final dictionary if we actually successfully scraped something
            if results:
                detail_crawl_results[key] = results

        if not detail_crawl_results:
            self.logger.warning("Extracted Results are empty.")
            return
        
        if service:
            if self.cfg.STORAGE == "local":
                self.save_to_local(detail_crawl_results)        
            elif self.cfg.STORAGE == "db":
                raise IntentedNotImplementedException("Database hasn't been implemented yet.")
            else:
                raise ValueError(f"Invalid storage type: {self.cfg.STORAGE}")
        else:
            return json.dumps(detail_crawl_results)
            
    async def pipeline(self, service=False, discover: bool = True, crawl_type: Optional[str]=None):
        if not discover and not crawl_type:
            raise ValueError("If the dicover mode isn't turned on the crawl_type should be defined.")
        # ========I. Discover Phase========
        if discover:
            classified_urls = await self.discovery()
        else:
            classified_urls = None
        # ========II. Crawl Phase========
        # NOTE: the crawler now only return un-parsed result in dictionary type. Further Extraction to create parsed version are required
        # NOTE: Put it in data ingestion pipeline with preprocessing step.
        # NOTE: The discoverer seems uneffective due to only care about metadta.
        # NOTE: Already putted all loading script
        if classified_urls:
            self.logger.info("Beginning crawling phase with batch crawling....")
            return await self.batch_detail_crawl(classified_urls, service) # return json string of batch results
        else:
            self.logger.info(f"Beginning crawling phase with detail crawling\ntype:{crawl_type}....")
            if crawl_type:
                result = await self.__detail_crawl(self.url, crawl_type)
            else:
                raise ValueError("The crawling type should be defined to extract correctly.")
            return json.dumps(result, indent=4)


if __name__ == "__main__":
    from app.core.config.settings import CrawlerSetting, DiscoverSettings, ExtractorSettings, ParserSettings
    url = "https://www.traveloka.com/vi-vn/destination/area/ho-chi-minh-city-10009794"
    
    load = LoadPipelineSetting(
        crawler_cfg=CrawlerSetting(),
        extractor_cfg=ExtractorSettings(),
        discover_cfg=DiscoverSettings()
    )
    extract = ExtractPipelineSetting(
        pipeline_cfg=ParserSettings()
    )
    app_settings = AppSettings(
        load_settings=[load],
        extract_settings=[extract],
    )
    
    crawler = Crawler(app_settings, seed_url=url)
    
    # TEMPORARY WRITE CHANGE CACHE FLAG
    crawler.cfg.load_settings[0].cache_mode=CACHE_MODE.WRITE

    asyncio.run(crawler.pipeline(service=True))