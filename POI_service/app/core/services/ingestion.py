import logging
import asyncio

from pydantic import ValidationError
from typing import List, Dict, Any, Tuple, Callable, Optional
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.interfaces.repositories import AbstractUnitOfWork
from app.core.utils.updater import SpatialUpdater
from app.core.interfaces.updater import ISpatialUpdate
from app.core.utils.broadcaster import broadcaster
from app.core.utils.spatial import NEARBY_RADIUS_KM_DEFAULT
from app.core.domain.graph_entities import POI

logger = logging.getLogger(__name__)


def _terminal_status(
    total: int, accepted: int, validation_failed: int, database_failed: int
) -> str:
    """Classify a terminated batch. ``complete`` means terminated, not success."""
    if total <= 0:
        return "success"
    if accepted == 0:
        return "failed"
    if validation_failed or database_failed:
        return "partial_failure"
    return "success"


def _empty_spatial_report() -> Dict[str, Any]:
    """No accepted changed ids -> the spatial stage had nothing to rebuild."""
    return {
        "status": "skipped",
        "is_success": True,
        "radius_km": NEARBY_RADIUS_KM_DEFAULT,
        "requested": 0,
        "attempted": 0,
        "succeeded": 0,
        "failed": 0,
        "truncated": False,
        "deferred": 0,
        "errors": {},
    }


def _failed_spatial_report(poi_ids: List[str], error_type: str) -> Dict[str, Any]:
    unique: List[str] = []
    for raw in poi_ids or []:
        if isinstance(raw, str) and raw.strip() and raw not in unique:
            unique.append(raw)
    return {
        "status": "failed",
        "is_success": False,
        "radius_km": NEARBY_RADIUS_KM_DEFAULT,
        "requested": len(unique),
        "attempted": len(unique),
        "succeeded": 0,
        "failed": len(unique),
        "truncated": False,
        "deferred": 0,
        "errors": {poi_id: error_type for poi_id in unique},
    }


def _merge_spatial(*reports: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Aggregate the spatial reports of every ingestion phase for one job."""
    valid = [report for report in reports if isinstance(report, dict)]
    if not valid:
        return None

    requested = sum(int(report.get("requested", 0) or 0) for report in valid)
    attempted = sum(int(report.get("attempted", 0) or 0) for report in valid)
    succeeded = sum(int(report.get("succeeded", 0) or 0) for report in valid)
    failed = sum(int(report.get("failed", 0) or 0) for report in valid)
    deferred = sum(int(report.get("deferred", 0) or 0) for report in valid)
    truncated = any(bool(report.get("truncated")) for report in valid)

    errors: Dict[str, str] = {}
    for report in valid:
        for poi_id, error_type in (report.get("errors") or {}).items():
            errors[poi_id] = error_type

    if requested == 0:
        status, is_success = "skipped", True
    elif failed == 0 and not truncated:
        status, is_success = "success", True
    elif succeeded == 0:
        status, is_success = "failed", False
    else:
        status, is_success = "partial_failure", False

    return {
        "status": status,
        "is_success": is_success,
        "radius_km": valid[0].get("radius_km", NEARBY_RADIUS_KM_DEFAULT),
        "requested": requested,
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": failed,
        "truncated": truncated,
        "deferred": deferred,
        "errors": errors,
    }


def _combine_status(status: str, spatial: Optional[Dict[str, Any]]) -> str:
    """Downgrade an otherwise-successful write status when spatial work failed.

    POI-write accounting (accepted/validation_failed/database_failed) is never
    rewritten; only the terminal ``status`` becomes honest about the separate
    spatial stage.
    """
    if status != "success" or not isinstance(spatial, dict):
        return status
    return status if spatial.get("is_success") else "partial_failure"


def _canary_totals(canary_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalise the canary result into cumulative counts for the whole batch."""
    if not canary_result:
        return {
            "total_received": 0,
            "accepted": 0,
            "validation_failed": 0,
            "database_failed": 0,
            "failed_indices": [],
            "spatial": None,
        }
    payload = canary_result.get("payload") or {}
    summary = payload.get("summary") or {}
    return {
        "total_received": summary.get("total_received", 0),
        "accepted": summary.get("accepted", summary.get("successfully_inserted", 0)),
        "validation_failed": summary.get("validation_failed", 0),
        "database_failed": summary.get("database_failed", 0),
        "failed_indices": list(payload.get("failed_indices", [])),
        "spatial": payload.get("spatial"),
    }


class POIIngestionService:
    def __init__(
        self,
        # Inject a FACTORY function that knows how to create your UoW
        uow_factory: Callable[[], AbstractUnitOfWork],
        spatial_updater: ISpatialUpdate = SpatialUpdater(),
    ):
        self.uow_factory = uow_factory
        self.chunk_size = 500
        self.spatial_updater = spatial_updater

    def _validate_batch(
        self, raw_payloads: List[Any], start_index: int = 0
    ) -> Tuple[List[Dict[str, Any]], List[int], List[Dict[str, Any]]]:
        """Separate valid POIs from invalid ones.

        Returns ``(valid_pois, valid_indices, failures)`` where ``valid_indices``
        maps each valid entry back to its position in the original payload and
        ``failures`` carry the original index. Non-dict records (``None``, lists,
        scalars) are reported as validation errors instead of raising.
        """
        valid_pois: List[Dict[str, Any]] = []
        valid_indices: List[int] = []
        failed_records: List[Dict[str, Any]] = []

        for offset, raw_data in enumerate(raw_payloads):
            index = start_index + offset

            if not isinstance(raw_data, dict):
                failed_records.append({
                    "index": index,
                    "name": "Unknown",
                    "errors": [{
                        "field": [],
                        "message": "Record must be a JSON object.",
                    }],
                })
                continue

            try:
                poi = POI.model_validate(raw_data)
            except ValidationError as e:
                raw_name = raw_data.get("name")
                failed_records.append({
                    "index": index,
                    "name": raw_name if isinstance(raw_name, str) else "Unknown",
                    "errors": [
                        {"field": list(err["loc"]), "message": err["msg"]}
                        for err in e.errors()
                    ],
                })
                continue

            valid_pois.append(poi.model_dump(mode="json"))
            valid_indices.append(index)

        return valid_pois, valid_indices, failed_records

    # ---------------------------------------------------------
    # 1. THE CANARY BRIDGE (For the Router)
    # ---------------------------------------------------------
    def process_canary_and_split(
        self, raw_payloads: List[Dict[str, Any]], limit: int = 10
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Validates and inserts the first 'limit' items synchronously.
        Returns the Unified Contract result for the Canary, AND the remaining raw payload.
        """
        canary_slice = raw_payloads[:limit]
        remaining_slice = raw_payloads[limit:]

        canary_result = self.process_ota_batch(canary_slice)

        return canary_result, remaining_slice

    # ---------------------------------------------------------
    # 2. THE BACKGROUND WORKER (With Validation Restored)
    # ---------------------------------------------------------
    async def process_background_remainder(
        self,
        raw_payloads: List[Dict[str, Any]],
        job_id: str,
        canary_result: Optional[Dict[str, Any]] = None,
        start_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Validate/insert the remainder and emit SSE events.

        The terminal event reports the **entire submitted batch**, not just the
        background slice: the optional ``canary_result`` (and ``start_index``,
        the original offset of the first remaining record) are merged in so a
        partial canary is never hidden by a successful remainder.
        """
        base = _canary_totals(canary_result)
        if start_index is None:
            start_index = base["total_received"]

        bg_total = len(raw_payloads)
        grand_total = base["total_received"] + bg_total
        base_accepted = base["accepted"]

        accepted = 0
        validation_failed = 0
        database_failed = 0
        failed_indices: List[int] = list(base["failed_indices"])
        # Per-chunk spatial reports. A chunk's accepted changed ids are rebuilt
        # right after its write commits, so a failed chunk is never scheduled and
        # every accepted id is covered within the bounded batch strategy.
        spatial_reports: List[Dict[str, Any]] = []

        # We must chunk the RAW data so we don't block the event loop validating 5,000 items at once
        for i in range(0, bg_total, self.chunk_size):
            chunk_raw = raw_payloads[i : i + self.chunk_size]

            # STEP A: Validate the chunk, keeping original payload indices.
            valid_chunk, valid_indices, validation_errors = self._validate_batch(
                chunk_raw, start_index=start_index + i
            )

            # Emit a warning if some items in this chunk were garbage
            if validation_errors:
                validation_failed += len(validation_errors)
                failed_indices.extend(err["index"] for err in validation_errors)
                await broadcaster.publish(job_id, {
                    "type": "warning",
                    "message": f"{len(validation_errors)} items failed domain validation in chunk {i}.",
                    "details": validation_errors,
                })

            # If the entire chunk was invalid, skip database execution entirely
            if not valid_chunk:
                continue

            # STEP B: Database Execution
            try:
                await asyncio.to_thread(self._execute_chunk_with_retry, valid_chunk)
            except Exception as e:
                database_failed += len(valid_chunk)
                failed_indices.extend(valid_indices)
                logger.error(
                    "Background database failure in chunk starting at %s: %s",
                    i,
                    type(e).__name__,
                )
                await broadcaster.publish(job_id, {
                    "type": "error",
                    "message": f"Graph database rejected chunk starting at {i} after retries.",
                    "failed_indices": valid_indices,
                })
                continue

            accepted += len(valid_chunk)
            chunk_ids = [
                poi["id"] for poi in valid_chunk
                if isinstance(poi.get("id"), str) and poi["id"].strip()
            ]
            # STEP C: Spatial stage for this chunk, in its own transaction(s).
            # A spatial failure is reported honestly and never reclassifies the
            # committed writes.
            spatial_reports.append(
                await asyncio.to_thread(self._run_spatial_rebuild, chunk_ids)
            )
            processed = base_accepted + accepted + validation_failed + database_failed
            await broadcaster.publish(job_id, {
                "type": "progress",
                "percentage": round((processed / grand_total) * 100, 2) if grand_total else 100.0,
                "message": f"Successfully processed {processed}/{grand_total} POIs.",
            })

        bg_spatial = (
            _merge_spatial(*spatial_reports) if spatial_reports else _empty_spatial_report()
        )
        spatial_report = _merge_spatial(base.get("spatial"), bg_spatial)

        total_accepted = base_accepted + accepted
        total_validation_failed = base["validation_failed"] + validation_failed
        total_database_failed = base["database_failed"] + database_failed
        status = _terminal_status(
            grand_total, total_accepted, total_validation_failed, total_database_failed
        )
        status = _combine_status(status, spatial_report)
        counts = {
            "total_received": grand_total,
            "processed": total_accepted + total_validation_failed + total_database_failed,
            "accepted": total_accepted,
            "successfully_inserted": total_accepted,
            "validation_failed": total_validation_failed,
            "database_failed": total_database_failed,
        }
        await broadcaster.publish(job_id, {
            "type": "complete",
            "status": status,
            "message": "Background ingestion complete.",
            "counts": counts,
            "failed_indices": sorted(set(failed_indices)),
            "spatial": spatial_report,
        })
        return counts

    # ---------------------------------------------------------
    # 3. THE SYNCHRONOUS ENGINE (For the Canary or small files)
    # ---------------------------------------------------------
    def process_ota_batch(self, raw_payloads: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Synchronous orchestration. Used primarily by the Canary method now.
        Returns the Unified Service Contract.
        """
        valid_pois, valid_indices, validation_errors = self._validate_batch(raw_payloads)
        total = len(raw_payloads)
        validation_failed = len(validation_errors)

        if not valid_pois:
            return {
                "is_success": False,
                "error_type": "unprocessable_entity",
                "payload": {
                    "status": "failed",
                    "message": "No valid POIs found.",
                    "summary": {
                        "total_received": total,
                        "processed": total,
                        "accepted": 0,
                        "successfully_inserted": 0,
                        "validation_failed": validation_failed,
                        "database_failed": 0,
                    },
                    "validation_details": validation_errors,
                    "failed_indices": [err["index"] for err in validation_errors],
                    "spatial": _empty_spatial_report(),
                },
            }

        accepted = 0
        database_failed = 0
        db_errors = []
        failed_indices = [err["index"] for err in validation_errors]
        spatial_reports: List[Dict[str, Any]] = []

        for i in range(0, len(valid_pois), self.chunk_size):
            chunk = valid_pois[i : i + self.chunk_size]
            chunk_indices = valid_indices[i : i + self.chunk_size]
            try:
                accepted += self._execute_chunk_with_retry(chunk)
            except Exception as e:
                database_failed += len(chunk)
                failed_indices.extend(chunk_indices)
                logger.error(
                    "Synchronous database failure in chunk starting at %s: %s",
                    i,
                    type(e).__name__,
                )
                # Keep the exception type only; never leak raw tracebacks/messages.
                db_errors.append({"chunk_index": i, "error_type": type(e).__name__})
                continue
            chunk_ids = [
                poi["id"] for poi in chunk
                if isinstance(poi.get("id"), str) and poi["id"].strip()
            ]
            spatial_reports.append(self._run_spatial_rebuild(chunk_ids))

        # Spatial stage runs after the writes, in its own transaction(s): a
        # spatial failure is reported separately and never turns an accepted
        # insert into a database failure.
        spatial_report = (
            _merge_spatial(*spatial_reports) if spatial_reports else _empty_spatial_report()
        )

        counts = {
            "total_received": total,
            "processed": accepted + validation_failed + database_failed,
            "accepted": accepted,
            "successfully_inserted": accepted,
            "validation_failed": validation_failed,
            "database_failed": database_failed,
        }
        status = _terminal_status(total, accepted, validation_failed, database_failed)
        status = _combine_status(status, spatial_report)

        # If it failed completely on the DB side
        if accepted == 0 and database_failed:
            return {
                "is_success": False,
                "error_type": "database_unavailable",
                "payload": {
                    "status": "failed",
                    "message": "Graph database failed to accept any records.",
                    "summary": counts,
                    "validation_details": validation_errors,
                    "database_details": db_errors,
                    "failed_indices": sorted(set(failed_indices)),
                    "spatial": spatial_report,
                },
            }

        # Partial synchronous success stays compatible (is_success True) while
        # exposing the partial failure explicitly through status/counts. The
        # top-level ``is_success`` reflects the POI write contract; the separate
        # ``spatial`` report carries the spatial outcome.
        return {
            "is_success": True,
            "payload": {
                "status": status,
                "summary": counts,
                "validation_details": validation_errors,
                "database_details": db_errors,
                "failed_indices": sorted(set(failed_indices)),
                "spatial": spatial_report,
            },
        }

    def _run_spatial_rebuild(self, poi_ids: List[str]) -> Dict[str, Any]:
        """Run the bounded post-write spatial stage for accepted changed ids.

        Never raises: an unexpected updater failure becomes an explicit failed
        spatial report (sanitized) rather than aborting ingestion.
        """
        unique: List[str] = []
        seen = set()
        for raw in poi_ids:
            if not isinstance(raw, str):
                continue
            cleaned = raw.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            unique.append(cleaned)

        if not unique:
            return _empty_spatial_report()

        try:
            return self.spatial_updater.rebuild_pois(unique, self.uow_factory)
        except Exception as exc:
            logger.error(
                "Spatial rebuild stage failed after writes committed (%s).",
                type(exc).__name__,
            )
            return _failed_spatial_report(unique, type(exc).__name__)

    # ---------------------------------------------------------
    # 3b. CANARY-ONLY TERMINAL EVENT
    # ---------------------------------------------------------
    async def finalize_canary_job(
        self, job_id: str, canary_result: Dict[str, Any]
    ) -> None:
        """Emit a terminal ``complete`` event for a canary with no remainder.

        The endpoint registers the job *before* running the canary, so a client
        that opens the SSE stream afterwards still receives this buffered event.
        """
        payload = canary_result.get("payload", {}) or {}
        spatial_report = payload.get("spatial") or _empty_spatial_report()
        await broadcaster.publish(job_id, {
            "type": "complete",
            "status": _combine_status(payload.get("status", "success"), spatial_report),
            "message": "Canary ingestion complete (no background remainder).",
            "counts": payload.get("summary", {}),
            "failed_indices": payload.get("failed_indices", []),
            "spatial": spatial_report,
        })

    # ---------------------------------------------------------
    # 4. THE TRANSACTION BOUNDARY
    # ---------------------------------------------------------
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _execute_chunk_with_retry(self, chunk: List[Dict[str, Any]]) -> int:
        # A fresh unit of work (and therefore a fresh transaction) is created for
        # every attempt, so a retry never reuses a broken/closed transaction.
        uow = self.uow_factory()
        with uow:
            uow.pois.batch_create(chunk)
        return len(chunk)
