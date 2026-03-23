import logging
import asyncio

from pydantic import ValidationError
from typing import List, Dict, Any, Tuple
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.interfaces.repositories import AbstractUnitOfWork
from app.core.utils.updater import SpatialUpdater
from app.core.interfaces.updater import ISpatialUpdate
from app.core.utils.broadcaster import broadcaster
from app.core.domain.graph_entities import POI

logger = logging.getLogger(__name__)

class POIIngestionService:
    def __init__(
        self, 
        uow: AbstractUnitOfWork, 
        spatial_updater: ISpatialUpdate = SpatialUpdater() # <-- Inject Strategy here
    ):
        self.uow = uow
        self.chunk_size = 500
        self.spatial_updater = spatial_updater

    def _validate_batch(self, raw_payloads: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Internal helper to separate valid POIs from invalid ones."""
        valid_pois = []
        failed_records = []

        for index, raw_data in enumerate(raw_payloads):
            try:
                poi = POI.model_validate(raw_data)
                valid_pois.append(poi.model_dump(mode="json"))
            except ValidationError as e:
                failed_records.append({
                    "index": index,
                    "name": raw_data.get("name", "Unknown"),
                    "errors": [{"field": err["loc"], "message": err["msg"]} for err in e.errors()]
                })
        return valid_pois, failed_records

    # ---------------------------------------------------------
    # 1. THE CANARY BRIDGE (For the Router)
    # ---------------------------------------------------------
    def process_canary_and_split(self, raw_payloads: List[Dict[str, Any]], limit: int = 10) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Validates and inserts the first 'limit' items synchronously.
        Returns the Unified Contract result for the Canary, AND the remaining raw payload.
        """
        canary_slice = raw_payloads[:limit]
        remaining_slice = raw_payloads[limit:]

        # We use process_ota_batch to handle the heavy lifting for the small canary
        canary_result = self.process_ota_batch(canary_slice)
        
        return canary_result, remaining_slice

    # ---------------------------------------------------------
    # 2. THE BACKGROUND WORKER (With Validation Restored)
    # ---------------------------------------------------------
    async def process_background_remainder(self, raw_payloads: List[Dict[str, Any]], job_id: str):
        """Standard batch process that validates, inserts, and emits SSE events."""
        total = len(raw_payloads)
        processed = 0

        # We must chunk the RAW data so we don't block the event loop validating 5,000 items at once
        for i in range(0, total, self.chunk_size):
            chunk_raw = raw_payloads[i : i + self.chunk_size]
            
            # STEP A: Validate the chunk!
            valid_chunk, validation_errors = self._validate_batch(chunk_raw)

            # Emit a warning if some items in this chunk were garbage
            if validation_errors:
                await broadcaster.publish(job_id, {
                    "type": "warning",
                    "message": f"{len(validation_errors)} items failed domain validation in chunk {i}.",
                    "details": validation_errors
                })

            # If the entire chunk was invalid, skip database execution entirely
            if not valid_chunk:
                processed += len(chunk_raw) # Advance the counter anyway
                continue

            # STEP B: Database Execution
            try:
                await asyncio.to_thread(self._execute_chunk_with_retry, valid_chunk)
                processed += len(chunk_raw)

                await broadcaster.publish(job_id, {
                    "type": "progress",
                    "percentage": round((processed / total) * 100, 2),
                    "message": f"Successfully processed {processed}/{total} POIs."
                })
            except Exception as e:
                logger.error(f"Background failure at index {i}: {str(e)}")
                await broadcaster.publish(job_id, {
                    "type": "error",
                    "message": f"Graph database rejected chunk starting at {i}: {str(e)}"
                })

        await broadcaster.publish(job_id, {"type": "complete", "message": "Background Ingestion complete!"})

    # ---------------------------------------------------------
    # 3. THE SYNCHRONOUS ENGINE (For the Canary or small files)
    # ---------------------------------------------------------
    def process_ota_batch(self, raw_payloads: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Synchronous orchestration. Used primarily by the Canary method now.
        Returns the Unified Service Contract.
        """
        valid_pois, validation_errors = self._validate_batch(raw_payloads)

        if not valid_pois:
            return {
                "is_success": False,
                "error_type": "unprocessable_entity",
                "payload": {"message": "No valid POIs found.", "validation_errors": validation_errors}
            }

        total_inserted = 0
        db_errors = []

        for i in range(0, len(valid_pois), self.chunk_size):
            chunk = valid_pois[i : i + self.chunk_size]
            try:
                inserted_count = self._execute_chunk_with_retry(chunk)
                total_inserted += inserted_count
            except Exception as e:
                db_errors.append({"chunk_index": i, "error": str(e)})

        # If it failed completely on the DB side
        if db_errors and total_inserted == 0:
            return {
                "is_success": False,
                "error_type": "internal_error",
                "payload": {"message": "Graph database failed to accept any records.", "database_details": db_errors}
            }

        return {
            "is_success": True,
            "payload": {
                "summary": {
                    "total_received": len(raw_payloads),
                    "successfully_inserted": total_inserted,
                    "validation_failed": len(validation_errors),
                    "database_chunk_failures": len(db_errors)
                },
                "validation_details": validation_errors,
                "database_details": db_errors
            }
        }

    # ---------------------------------------------------------
    # 4. THE TRANSACTION BOUNDARY
    # ---------------------------------------------------------
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _execute_chunk_with_retry(self, chunk: List[Dict[str, Any]]) -> int:
        with self.uow:
            self.uow.pois.batch_create(chunk)
        
        affected_districts = list(set([
            poi["address"]["district"] 
            for poi in chunk 
            if poi.get("address") and poi["address"].get("district")
        ]))
        
        if affected_districts:
            self.spatial_updater.trigger_update(
                affected_district=affected_districts,
                repository=self.uow.pois,
                # safe since the _execute_chunk() is already asyncronously run.
                background_tasks=None 
            )
        
        return len(chunk)