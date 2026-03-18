# app/services/ingestion.py
import logging
from typing import List, Dict, Any, Tuple
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.interfaces.repositories import AbstractUnitOfWork
from app.core.domain.graph_entities import POI

logger = logging.getLogger(__name__)

class POIIngestionService:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow
        self.chunk_size = 500  # Optimal chunk size for Memgraph UNWIND

    def process_ota_batch(self, raw_payloads: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Orchestrates the validation and chunked ingestion of bulk POI data.
        Returns a summary of successes and failures.
        """
        valid_pois = []
        failed_records = []

        # 1. Strict Domain Validation Filter
        for index, raw_data in enumerate(raw_payloads):
            try:
                # Let Pydantic enforce all mapping rules and clean the strings
                poi = POI.model_validate(raw_data)
                valid_pois.append(poi.model_dump())
            except ValueError as e:
                failed_records.append({
                    "index": index,
                    "name": raw_data.get("name", "Unknown"),
                    "error": str(e)
                })

        if not valid_pois:
            logger.warning("Entire batch failed domain validation.")
            return {"inserted": 0, "failed": len(failed_records), "errors": failed_records}

        # 2. Chunking and Database Execution
        total_inserted = 0
        
        # Slice the massive array into chunks of 500
        for i in range(0, len(valid_pois), self.chunk_size):
            chunk = valid_pois[i : i + self.chunk_size]
            try:
                inserted_count = self._execute_chunk_with_retry(chunk)
                total_inserted += inserted_count
                logger.info(f"Successfully ingested chunk: {i} to {i + len(chunk)}")
            except Exception as e:
                logger.error(f"Failed to ingest chunk {i}. Error: {str(e)}")

        return {
            "inserted": total_inserted,
            "failed": len(failed_records),
            "validation_errors": failed_records
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _execute_chunk_with_retry(self, chunk: List[Dict[str, Any]]) -> int:
        """
        Executes a single chunk via the UoW. If a transient graph lock occurs, 
        tenacity will automatically wait and retry this method up to 3 times.
        """
        with self.uow:
            return self.uow.pois.batch_create(chunk)