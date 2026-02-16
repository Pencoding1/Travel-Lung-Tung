import logging 

from typing import Optional, List, Set
from abc import ABC, abstractmethod

from db.models.IngestionRecords import RawDataRecord, TransformRecord
from pipelines.preprocessing.base.PipelineBase import BasePreprocessor

from config.data_ingestion import IngestionConfig


class BaseDataIngestion(ABC):
    """
        Base class for Travel Lung Tung Data Ingestion (ETL).
        
        Workflow:
        1. Extract: Fetch data (from Crawl4AI or Local DB).
        2. Transform: Clean -> Chunk -> Embed -> Extract Graph Entities (NER).
        3. Load: Save to Vector DB (e.g., Qdrant/Chroma) and Graph DB (Neo4j).
    """

    def __init__(self, processor: Optional[BasePreprocessor]=None, config: Optional[IngestionConfig] = None) -> None:
        self.config = config if config else IngestionConfig()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.processor = processor
    
    @abstractmethod
    async def extract(self) -> Set[RawDataRecord]:
        """
        Pull raw data from the source (Web/DB/Local).
        Returns list of RawData object with 'raw_content' populated with path to markdown file.
        """
        pass

    @abstractmethod
    async def transform(self, records: Set[RawDataRecord]) -> List[TransformRecord]:
        """
        Apply cleaning, chunking, embedding, and GraphRAG extraction.
        
        Recommended sub-steps to call here:
        - _clean_data()
        - _chunk_and_embed()  <-- Vietnamese embedding here
        - _extract_graph_entities() <-- LLM based NER here
        """
        pass

    @abstractmethod
    async def load(self, records: List[TransformRecord]):
        """
        Persist the processed records to the appropriate databases.
        - Vector DB: chunks + embeddings
        - Graph DB: nodes + relationships
        """
        pass

    async def run(self):
        self.logger.info("Starting Data Ingestion Pipeline...")

        try:
            self.logger.info("STEP 1: Extracting data")
            raw_records = await self.extract()
            if not raw_records:
                self.logger.warning("No records extracted. Stopping pipeline.")
                return
            
            self.logger.info(f"STEP 2: Trasnforming {len(raw_records)} records...")
            processed_records = await self.transform(raw_records)

            valid_records = [r for r in processed_records if r.status != "failed"]
            if valid_records:
                self.logger.info(f"STEP 3: Loading {len(valid_records)} records to {self.config.DESTINATION}")
                await self.load(valid_records)
            
            self.logger.info("Pipeline completed successfully.")

        except Exception as e:
            self.logger.error(f"Critical Pipeline Failure: {str(e)}", exc_info=True)
            raise e