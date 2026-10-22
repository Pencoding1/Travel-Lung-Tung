import logging
from typing import Any, Dict, List, Optional, Callable

from fastapi import BackgroundTasks
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.base.service import AbstractUnitOfWork
from app.core.interfaces.updater import ISpatialUpdate
from app.core.utils.spatial import NEARBY_RADIUS_KM_DEFAULT, validate_radius_km

logger = logging.getLogger(__name__)

#: Explicit bound on the number of POIs spatially rebuilt by a single
#: application/ingestion call. Bulk ingestion accepts arbitrarily large payloads
#: but the spatial stage must stay bounded: when the accepted changed-id set
#: exceeds this cap, the first ``SPATIAL_REBUILD_MAX_POIS`` ids are rebuilt and
#: the remainder is reported as ``deferred`` (never silently dropped).
SPATIAL_REBUILD_MAX_POIS = 1000

#: One fresh UnitOfWork/transaction is opened per bounded batch of POIs, so the
#: transaction size is independent of the request size.
SPATIAL_REBUILD_BATCH_SIZE = 100


def _normalize_poi_ids(poi_ids: Optional[List[str]]) -> List[str]:
    """Return non-blank, de-duplicated POI ids preserving first-seen order."""
    normalized: List[str] = []
    seen = set()
    for raw in poi_ids or []:
        if not isinstance(raw, str):
            continue
        cleaned = raw.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


class SpatialUpdater(ISpatialUpdate):
    """Per-scope spatial rebuild orchestration.

    Two scopes are supported:

    * **district** (:meth:`trigger_update`) -- each district is rebuilt in its
      own UnitOfWork/transaction, so the rebuild is **not atomic across
      districts**; the report states which districts succeeded and failed.
    * **POI ids** (:meth:`rebuild_pois`) -- the bulk-ingestion stage. Each bounded
      batch of accepted changed POI ids is rebuilt in its own fresh
      UnitOfWork/transaction (retried with a fresh transaction per attempt).
      This runs *after* the POI writes are committed, so a spatial failure is
      reported separately and never reclassifies a successful insert.

    Raw provider/driver text is never logged or returned; only exception types.
    """

    def trigger_update(self,
                       affected_districts: List[str],
                       uow_factory: Callable[[], AbstractUnitOfWork],
                       background_tasks: Optional[BackgroundTasks] = None) -> Optional[Dict[str, object]]:
        if not background_tasks:
            # No background queue: run synchronously and return the real report
            # so the caller can observe the outcome (never a blanket success).
            logger.warning("No BackgroundTasks provided. Spatial update will run synchronously.")
            return self._execute_update(affected_districts, uow_factory)

        background_tasks.add_task(self._execute_update, affected_districts, uow_factory)
        return None

    def _execute_update(self, districts: List[str], uow_factory: Callable[[], AbstractUnitOfWork]) -> Dict[str, object]:
        succeeded: Dict[str, int] = {}
        failed: Dict[str, str] = {}
        total_edges = 0

        for district_id in _normalize_poi_ids(districts):
            try:
                edges = self._build_district_with_retry(district_id, uow_factory)
            except Exception as exc:
                # Honest per-district failure. Sanitized: log the exception
                # type only, never the raw provider/driver message.
                failed[str(district_id)] = type(exc).__name__
                logger.error(
                    "Spatial rebuild permanently failed for district %s (%s).",
                    district_id,
                    type(exc).__name__,
                )
                continue
            succeeded[str(district_id)] = edges
            total_edges += edges

        report: Dict[str, object] = {
            "is_success": not failed,
            "total_edges": total_edges,
            "succeeded": succeeded,
            "failed": failed,
        }
        if failed:
            logger.warning(
                "Spatial rebuild finished with %d failed district(s); %d succeeded.",
                len(failed),
                len(succeeded),
            )
        else:
            logger.info(
                "Spatial rebuild complete: %d new edges across %d district(s).",
                total_edges,
                len(succeeded),
            )
        return report

    def rebuild_pois(self,
                     poi_ids: List[str],
                     uow_factory: Callable[[], AbstractUnitOfWork],
                     *,
                     radius_km: float = NEARBY_RADIUS_KM_DEFAULT,
                     max_pois: int = SPATIAL_REBUILD_MAX_POIS,
                     batch_size: int = SPATIAL_REBUILD_BATCH_SIZE) -> Dict[str, Any]:
        """Rebuild the incident ``:NEAR_BY`` edges of accepted changed POI ids.

        The ids are de-duplicated, bounded by ``max_pois`` (the surplus is
        reported as ``deferred``) and processed in ``batch_size`` batches. Each
        batch runs in its own fresh UnitOfWork with bounded retries, so no batch
        ever reuses a closed transaction and the work stays bounded.

        The returned report is honest: ``is_success`` is ``False`` when any id
        failed or coverage was truncated, and ``errors`` maps failed ids to a
        sanitized exception type (never raw provider text).
        """
        radius_km = validate_radius_km(radius_km)
        unique_ids = _normalize_poi_ids(poi_ids)
        requested = len(unique_ids)

        truncated = False
        deferred = 0
        if max_pois is not None and requested > max_pois:
            deferred = requested - max_pois
            unique_ids = unique_ids[:max_pois]
            truncated = True

        succeeded = 0
        failed: Dict[str, str] = {}
        batch_limit = max(1, int(batch_size))

        for start in range(0, len(unique_ids), batch_limit):
            batch = unique_ids[start:start + batch_limit]
            try:
                self._build_pois_with_retry(batch, uow_factory, radius_km)
            except Exception as exc:
                for poi_id in batch:
                    failed[poi_id] = type(exc).__name__
                logger.error(
                    "Spatial rebuild permanently failed for a batch of %d POI(s) (%s).",
                    len(batch),
                    type(exc).__name__,
                )
                continue
            succeeded += len(batch)

        attempted = len(unique_ids)
        if requested == 0:
            status = "skipped"
            is_success = True
        elif failed or truncated:
            status = "failed" if succeeded == 0 else "partial_failure"
            is_success = False
        else:
            status = "success"
            is_success = True

        report: Dict[str, Any] = {
            "status": status,
            "is_success": is_success,
            "radius_km": radius_km,
            "requested": requested,
            "attempted": attempted,
            "succeeded": succeeded,
            "failed": len(failed),
            "truncated": truncated,
            "deferred": deferred,
            "errors": failed,
        }
        if not is_success:
            logger.warning(
                "Spatial POI rebuild incomplete: %d/%d rebuilt, %d failed, %d deferred.",
                succeeded,
                attempted,
                len(failed),
                deferred,
            )
        return report

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
    def _build_district_with_retry(self, district_id: str, uow_factory: Callable[[], AbstractUnitOfWork]) -> int:
        # A fresh UnitOfWork (and therefore a fresh transaction) is created on
        # every attempt, so a retry never reuses a broken/closed transaction.
        uow = uow_factory()
        with uow:
            return uow.pois.build_nearby_edges_for_district(
                district_id, radius_km=NEARBY_RADIUS_KM_DEFAULT
            )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
    def _build_pois_with_retry(self,
                               poi_ids: List[str],
                               uow_factory: Callable[[], AbstractUnitOfWork],
                               radius_km: float) -> int:
        # A fresh UnitOfWork per attempt: the whole batch (delete + rebuild per
        # id) is one transaction, so a mid-batch failure rolls back cleanly and
        # the retry starts from a healthy transaction.
        uow = uow_factory()
        with uow:
            for poi_id in poi_ids:
                uow.pois.build_nearby_edges_for_poi(poi_id, radius_km=radius_km)
        return len(poi_ids)
