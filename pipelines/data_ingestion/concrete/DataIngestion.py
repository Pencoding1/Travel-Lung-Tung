"""
Docstring for pipelines.data_ingestion.base.PipelineBase

We choose ELT pipeline as base pipeline for Data Ingestion pipeline because we need transform documents into
suitable structure for graph and vector database. Including:

- Cleaning Process: remove header, footer, copyright, unrelated or meaningless part can exist in crawled docs.
- Extraction Process: extract parts within the webpage such as comment or review in Website about a tour.
- Data Classification: classify difference context document into difference type to create metadata, improving indexing process.
- Deduplication & Filtering: remove unrelated docs or duplicated docs. Applying PII for personal privacy.
- RAG process:
    + Chunking: split documents into several chunks using markdown structure based strategy before embedding the text.
    + Embedding: use vietnamese embedding model to embed the chunks
    + Indexing and storage: # TODO write this part
- GraphRAG process:
    + NER: for extracting entities
    + Relationship extraction: using LLM to read and identify the connection between entities.
    + # TODO add more here
"""

import os
import json
import logging

from pathlib import Path
from dotenv import load_dotenv
from typing import Optional, List, Set

from config.data_ingestion import IngestionConfig
from config.global_config import CITY_CONFIGS, GLOBAL_CRAWL_SETTINGS

from db.models.IngestionRecords import RawDataRecord, TransformRecord, GraphOutput

from pipelines.preprocessing.preprocessing import (TravelokaPreprocessor, 
                                                   VNTravelPreprocessor, 
                                                   VietravelPreprocessor, 
                                                   VietnamTravelPreprocessor
                                                    )

from pipelines.data_ingestion.base.PipelineBase import BaseDataIngestion

from pipelines.crawling.crawl import run_crawler


load_dotenv()

class TravelokaIngestion(BaseDataIngestion):
    global CITY_CONFIGS, GLOBAL_CRAWL_SETTINGS
    
    def __init__(self, config: Optional[IngestionConfig]=None, processor: Optional[TravelokaPreprocessor]=None) -> None:
        processor = processor if processor else TravelokaPreprocessor()
        super().__init__(config=config, processor=processor)
        self.logger = logging.getLogger(name="TravelokaIngestion")
        self.lsh_keys: Set[str] = set()
        self.error_files_count = 0
    
    def _batch_filter(self):
        ...

    def _local_extracting(self) -> Set[RawDataRecord]:
        results = set()
        path = Path(self.config.OUTPUT_PATH)

        if not path or not path.exists():
            self.logger.warning(f"Storage path {path} does not exist.")
            return results
        

        all_paths = list(path.rglob("*.json"))
        for file_path in all_paths:
            data = RawDataRecord(
                raw_content=str(file_path),
                metadata={"file_path": str(file_path)},
                status="pending"
            )
            try:
                with open(file_path, 'r', encoding="utf-8") as f:
                    file_content = json.load(f)
                    
                    data.raw_content = file_content.get("local_path", "empty_path") 
                    data.status = "success"
            except Exception as e:
                self.logger.error(f"Error occurred during extracting at file {data.source_id}: {e}")
                data.status = "failed"
                data.error_log = str(e)
                self.error_files_count += 1
            
            results.add(data)
        
        if self._all_files_corrupted(len(all_paths)):
            return set()
        
        return results
    
    def _all_files_corrupted(self, num_records:int) -> bool:
        """Only accept 30% of files are corrupted or unqualified"""
        if num_records == 0:
            self.logger.error("No records have found.")
            return True
        
        are_corrupted = 1 - round(self.error_files_count/num_records, 4) < self.config.ACCEPTED_THRESHOLD
        self.error_files_count = 0
        if are_corrupted:
            self.logger.error("All or most files are corrupted or unqualified.")

        return are_corrupted
    
    #TODO: Add when crawl and store in database completed
    def _db_extracting(self)-> Set[RawDataRecord]:...

    async def extract(self) -> Set[RawDataRecord]:
        storage_type = os.getenv("STORAGE", "local").lower()
        results: Set[RawDataRecord] = set()

        await run_crawler(store_location=storage_type) #type: ignore

        if storage_type == "local":
            extracted_result = self._local_extracting()
            results = extracted_result if extracted_result else set()
        
        elif storage_type == "db":
            extracted_result = self._db_extracting() 
            results = extracted_result if extracted_result else set()
        else:
            self.logger.warning(f"Storage type '{storage_type}' is not supported.")
            
        return results
    
    async def transform(self, records: List[RawDataRecord]) -> List[TransformRecord]:
        results: List[TransformRecord] = list()
        if not records:
            self.logger.warning("The Extraction Records are EMPTY or most file are corrupted. Double check the previous pipeline.")
            return []

        # preprocessing step
        for record in records:
            if record.status == "success":
                try:
                    text = Path(record.raw_content).read_text()
                    clenned_text = self.processor.process_text(text, record.source_id) # type: ignore
                    results.append(
                        TransformRecord(clean_text=clenned_text,
                                        status="success")
                    )
                except Exception as e:
                    self.logger.warning(f"There is an error occured during cleaning process: {e}")
                    results.append(
                        TransformRecord(clean_text="Corrupted", 
                                        status="failed", 
                                        error_log=str(e))
                    )
                    self.error_files_count += 1        
        
        if self._all_files_corrupted(len(results)):
            return []
        
        return results