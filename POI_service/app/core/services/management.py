import json
import math

from fastapi import HTTPException, status
from typing import Dict, Any, Optional, List


from app.core.base.service import BaseManagementService
from app.core.domain.get_payload import (
    AdministrativeContext, CategoryRef, POIGetResponse, POIResult, POIDescription,
    ReviewDetail, POIContactInfo, NearbyPOI, POILite, OfferLite,
    SourceEvidenceSummary, resolve_administrative_context,
)
from app.core.domain.graph_entities import POI, Category, decode_source_metadata
from app.core.domain.source_scope import (
    CURRENT_BOUNDARY_UNCERTAINTY,
    SourceScopeError,
    SourceScopeCorruption,
    SourceSnapshotRef,
    SourceSnapshotSelection,
    build_source_context,
    derive_source_area,
    parse_source_snapshot_ref,
    parse_source_snapshot_selection,
)
from app.core.interfaces.repositories import IDocumentRepository
from app.core.utils.spatial import NEARBY_RADIUS_KM_DEFAULT

from travel_shared.exceptions import IntentedNotImplementedException


class EntityNotFoundError(ValueError):
    """Requested entity does not exist (mapped to a stable ``not_found`` code)."""


class InvalidRequestError(ValueError):
    """Caller supplied invalid arguments (mapped to ``invalid_request``)."""


def _as_finite(value: Any) -> Optional[float]:
    """Coerce ``value`` to a finite float, rejecting bools/non-numerics/NaN."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _finite_nonnegative(value: Any) -> Optional[float]:
    number = _as_finite(value)
    if number is None or number < 0:
        return None
    return number


def _finite_in_range(value: Any, low: float, high: float) -> Optional[float]:
    number = _as_finite(value)
    if number is None or not (low <= number <= high):
        return None
    return number

class POIManagementService(BaseManagementService[POI]):
    """
    Concrete implementation of the management flow strictly for POIs.
    """

    def _validate_payload(self, payload: Dict[str, Any]) -> POI:
        return POI.model_validate(payload)

    def _get_existing(self, entity_id: str) -> Optional[POI]:
        return self.uow.pois.get_by_id(entity_id)

    def _execute_create(self, entity: POI) -> POI:
        created = self.uow.pois.create(entity)
        # Same transaction as the source write: a downstream spatial failure
        # rolls the freshly created POI back instead of leaving it half-linked.
        self._rebuild_incident_edges(getattr(entity, "id", None))
        return created

    def _execute_update(self, entity_id: str, entity: POI) -> POI:
        updated = self.uow.pois.update(entity_id, entity)
        # A location/coordinate update (including a move out of the previous
        # district) replaces *all* incident :NEAR_BY edges in this same
        # transaction, so a spatial failure rolls the source mutation back.
        self._rebuild_incident_edges(entity_id)
        return updated

    def _execute_delete(self, entity_id: str) -> bool:
        # ``delete`` is a DETACH DELETE: the node and every incident edge
        # (including :NEAR_BY) are removed while unrelated nodes/edges survive.
        return self.uow.pois.delete(entity_id)

    def _rebuild_incident_edges(self, entity_id: Optional[str]) -> None:
        """Replace the incident ``:NEAR_BY`` edges of one POI at the fixed radius.

        The application path always uses the single shared service radius
        (:data:`NEARBY_RADIUS_KM_DEFAULT`, 3 km); the repository still exposes the
        custom-radius variant for explicit offline/admin rebuilds. Incompatible
        stored radii make the repository raise, which aborts the enclosing
        transaction (honest failure) rather than silently flipping shared policy.
        """
        if not isinstance(entity_id, str) or not entity_id.strip():
            return
        self.uow.pois.build_nearby_edges_for_poi(
            entity_id, radius_km=NEARBY_RADIUS_KM_DEFAULT
        )
    
    def get_poi(self, id: str) -> Optional[POI]:
        return self._get_existing(id)

    def get_all(self, skip: int = 0, limit: int = 20) -> List[Dict[str, Any]]:
        with self.uow:
            pois = self.uow.pois.get_all(skip=skip, limit=limit)
            return [json.loads(poi.model_dump_json()) for poi in pois]

    # -------------------------------------------------------------------
    # NEW: HIERARCHICAL DISCOVERY METHODS
    # -------------------------------------------------------------------
    
    def get_all_cities(self) -> List[Dict[str, str]]:
        with self.uow:
            return self.uow.pois.get_all_cities()

    def get_districts_by_city(self, city_id: str) -> List[Dict[str, str]]:
        with self.uow:
            return self.uow.pois.get_districts_by_city(city_id)

    def get_streets_by_district(self, district_id: str) -> List[Dict[str, str]]:
        with self.uow:
            return self.uow.pois.get_streets_by_district(district_id)

    def get_available_categories(self) -> List[Dict[str, str]]:
        """Retrieves all valid category IDs and names for the Agent."""
        with self.uow:
            return self.uow.pois.get_all_categories()
            
    # -------------------------------------------------------------------
    # EXPLORATION METHODS (Strict ID Based & Context-Window Optimized)
    # -------------------------------------------------------------------

    def explore_by_city_id(self, city_id: str, skip: int = 0, limit: int = 15) -> List[Dict[str, Any]]:
        with self.uow:
            pois = self.uow.pois.get_by_city_id_lite(city_id, skip=skip, limit=limit)
            return [poi.model_dump() for poi in pois]

    def explore_by_district_id(self, district_id: str, skip: int = 0, limit: int = 15) -> List[Dict[str, Any]]:
        with self.uow:
            pois = self.uow.pois.get_by_district_id_lite(district_id, skip=skip, limit=limit)
            return [poi.model_dump() for poi in pois]

    def explore_by_street_id(self, street_id: str, skip: int = 0, limit: int = 15) -> List[Dict[str, Any]]:
        with self.uow:
            pois = self.uow.pois.get_by_street_id_lite(street_id, skip=skip, limit=limit)
            return [poi.model_dump() for poi in pois]

    def explore_by_category(self, category_id: str, skip: int = 0, limit: int = 15) -> List[Dict[str, Any]]:
        with self.uow:
            pois = self.uow.pois.get_by_category_id_lite(category_id, skip=skip, limit=limit)
            return [poi.model_dump() for poi in pois]

    def explore_by_product(self, product_keyword: str, skip: int = 0, limit: int = 15) -> List[Dict[str, Any]]:
        with self.uow:
            pois = self.uow.pois.get_by_offered_products_lite(product_keyword, skip=skip, limit=limit)
            return [poi.model_dump() for poi in pois]

    def explore_compound(
        self,
        *,
        city_id: Optional[str] = None,
        district_id: Optional[str] = None,
        street_id: Optional[str] = None,
        category_id: Optional[str] = None,
        product_keyword: Optional[str] = None,
        limit: int = 15,
        offset: int = 0,
        source_scope: Optional[Any] = None,
    ) -> Any:
        """Validate and run a conjunctive exact-id exploration.

        Current mode keeps its list return shape. Supplying ``source_scope``
        switches explicitly to source mode and returns an envelope with a scan
        report, so truncation/corruption is never hidden.
        """
        if source_scope is not None:
            return self.explore_source_scope_compound(
                city_id=city_id,
                district_id=district_id,
                street_id=street_id,
                category_id=category_id,
                product_keyword=product_keyword,
                limit=limit,
                offset=offset,
                source_scope=source_scope,
            )

        (
            city_id,
            district_id,
            street_id,
            category_id,
            product_keyword,
            limit,
            offset,
        ) = self._validate_explore_arguments(
            city_id=city_id,
            district_id=district_id,
            street_id=street_id,
            category_id=category_id,
            product_keyword=product_keyword,
            limit=limit,
            offset=offset,
        )

        with self.uow:
            pois = self.uow.pois.get_compound_explore_lite(
                city_id=city_id,
                district_id=district_id,
                street_id=street_id,
                category_id=category_id,
                product_keyword=product_keyword,
                limit=limit,
                offset=offset,
            )
            return [poi.model_dump() for poi in pois]

    def _validate_explore_arguments(
        self,
        *,
        city_id: Optional[str],
        district_id: Optional[str],
        street_id: Optional[str],
        category_id: Optional[str],
        product_keyword: Optional[str],
        limit: int,
        offset: int,
        require_criterion: bool = True,
    ):
        def _clean(value: Optional[str], label: str) -> Optional[str]:
            if value is None:
                return None
            if not isinstance(value, str):
                raise InvalidRequestError(f"'{label}' must be a string identifier")
            cleaned = value.strip()
            return cleaned or None

        city_id = _clean(city_id, "city_id")
        district_id = _clean(district_id, "district_id")
        street_id = _clean(street_id, "street_id")
        category_id = _clean(category_id, "category_id")
        product_keyword = _clean(product_keyword, "product_keyword")

        if require_criterion and not any(
            (city_id, district_id, street_id, category_id, product_keyword)
        ):
            raise InvalidRequestError("At least one search criterion is required")

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise InvalidRequestError("'limit' must be an integer")
        if not (1 <= limit <= 100):
            raise InvalidRequestError("'limit' must be between 1 and 100")

        if isinstance(offset, bool) or not isinstance(offset, int):
            raise InvalidRequestError("'offset' must be an integer")
        if offset < 0:
            raise InvalidRequestError("'offset' must be nonnegative")

        return (
            city_id,
            district_id,
            street_id,
            category_id,
            product_keyword,
            limit,
            offset,
        )

    def explore_source_scope_compound(
        self,
        *,
        source_scope: Any,
        city_id: Optional[str] = None,
        district_id: Optional[str] = None,
        street_id: Optional[str] = None,
        category_id: Optional[str] = None,
        product_keyword: Optional[str] = None,
        limit: int = 15,
        offset: int = 0,
    ) -> Dict[str, Any]:
        try:
            selection = parse_source_snapshot_selection(source_scope)
        except SourceScopeError as exc:
            raise InvalidRequestError(str(exc)) from exc

        # Conflict is rejected before the repository is entered or any query is
        # built. A source-snapshot request is never mixed with current
        # city/district/street containment.
        for label, value in (
            ("city_id", city_id),
            ("district_id", district_id),
            ("street_id", street_id),
        ):
            if value is not None:
                raise InvalidRequestError(
                    f"'{label}' cannot be combined with explicit source_scope"
                )

        (
            city_id,
            district_id,
            street_id,
            category_id,
            product_keyword,
            limit,
            offset,
        ) = self._validate_explore_arguments(
            city_id=None,
            district_id=None,
            street_id=None,
            category_id=category_id,
            product_keyword=product_keyword,
            limit=limit,
            offset=offset,
            require_criterion=False,
        )

        with self.uow:
            pois, scan = self.uow.pois.get_compound_explore_source(
                selection,
                city_id=None,
                district_id=None,
                street_id=None,
                category_id=category_id,
                product_keyword=product_keyword,
                limit=limit,
                offset=offset,
            )
            report = dict(scan or {})
            report["current_boundary_uncertainty"] = CURRENT_BOUNDARY_UNCERTAINTY
            return {
                "source_scope": selection.model_dump(mode="json"),
                "source_scan": report,
                "results": [poi.model_dump(mode="json") for poi in pois],
            }

    def _scan_source_records(
        self,
        page_size: int = 500,
        max_records: int = 100000,
    ) -> Dict[str, Any]:
        rows: List[Dict[str, Any]] = []
        scanned = 0
        truncated = False
        exhausted = False
        after_id: Optional[str] = None

        while True:
            remaining = max_records - scanned
            if remaining <= 0:
                truncated = True
                break
            page = self.uow.pois.iter_source_scope_records(
                after_id=after_id, limit=min(page_size, remaining)
            )
            if not page:
                exhausted = True
                break
            rows.extend(page)
            scanned += len(page)
            last_id = page[-1].get("id")
            if isinstance(last_id, str) and last_id.strip():
                after_id = last_id
            if len(page) < min(page_size, remaining):
                exhausted = True
                break
            if after_id is None:
                truncated = True
                break

        return {
            "rows": rows,
            "scanned": scanned,
            "truncated": truncated,
            "exhausted": exhausted,
        }

    def list_source_snapshots(self) -> Dict[str, Any]:
        with self.uow:
            scan = self._scan_source_records()

        snapshots: Dict[tuple, Dict[str, Any]] = {}
        corrupt = 0
        for row in scan["rows"]:
            metadata, status = decode_source_metadata(
                row.get("source_metadata_json"),
                row.get("source_metadata_sha256"),
            )
            if metadata is None:
                corrupt += 1
                continue
            try:
                metadata.assert_bound_to_poi(row.get("id"))
                identity = derive_source_area(metadata)
            except (ValueError, SourceScopeError):
                corrupt += 1
                continue
            key = (identity.dataset_namespace, identity.input_sha256)
            entry = snapshots.setdefault(
                key,
                {
                    "dataset_namespace": identity.dataset_namespace,
                    "input_sha256": identity.input_sha256,
                    "valid_record_count": 0,
                    "source_area_ids": set(),
                },
            )
            entry["valid_record_count"] += 1
            entry["source_area_ids"].add(identity.source_area_id)

        items = []
        for entry in snapshots.values():
            items.append(
                {
                    "dataset_namespace": entry["dataset_namespace"],
                    "input_sha256": entry["input_sha256"],
                    "valid_record_count": entry["valid_record_count"],
                    "source_area_count": len(entry["source_area_ids"]),
                    "current_boundary_uncertainty": (
                        CURRENT_BOUNDARY_UNCERTAINTY
                    ),
                }
            )
        items.sort(key=lambda item: (item["dataset_namespace"], item["input_sha256"]))
        return {
            "snapshots": items,
            "scan": {
                "scanned_record_count": scan["scanned"],
                "excluded_corrupt_count": corrupt,
                "scan_complete": not scan["truncated"],
                "scan_exhausted": scan["exhausted"],
                "truncated": scan["truncated"],
            },
        }

    def list_source_areas(self, source_snapshot: Any) -> Dict[str, Any]:
        try:
            snapshot = parse_source_snapshot_ref(source_snapshot)
        except SourceScopeError as exc:
            raise InvalidRequestError(str(exc)) from exc

        with self.uow:
            scan = self._scan_source_records()

        areas: Dict[str, Dict[str, Any]] = {}
        corrupt = 0
        for row in scan["rows"]:
            metadata, status = decode_source_metadata(
                row.get("source_metadata_json"),
                row.get("source_metadata_sha256"),
            )
            if metadata is None:
                corrupt += 1
                continue
            try:
                metadata.assert_bound_to_poi(row.get("id"))
                identity = derive_source_area(metadata)
            except (ValueError, SourceScopeError):
                corrupt += 1
                continue
            if (
                identity.dataset_namespace != snapshot.dataset_namespace
                or identity.input_sha256 != snapshot.input_sha256
            ):
                continue
            entry = areas.setdefault(
                identity.source_area_id,
                {
                    "source_area_id": identity.source_area_id,
                    "raw_city": identity.raw_city,
                    "raw_area": identity.raw_area,
                    "source_area_label": identity.source_area_label,
                    "area_assignment": identity.area_assignment,
                    "valid_record_count": 0,
                },
            )
            entry["valid_record_count"] += 1

        items = sorted(
            areas.values(),
            key=lambda item: (
                item["raw_city"] or "",
                item["raw_area"] or "",
                item["source_area_id"],
            ),
        )
        for item in items:
            item["current_boundary_uncertainty"] = CURRENT_BOUNDARY_UNCERTAINTY
        return {
            "dataset_namespace": snapshot.dataset_namespace,
            "input_sha256": snapshot.input_sha256,
            "source_areas": items,
            "scan": {
                "scanned_record_count": scan["scanned"],
                "excluded_corrupt_count": corrupt,
                "scan_complete": not scan["truncated"],
                "scan_exhausted": scan["exhausted"],
                "truncated": scan["truncated"],
            },
        }

    # -------------------------------------------------------------------
    # DEEP RETRIEVAL METHOD (Full Details & Graph Data)
    # -------------------------------------------------------------------

    def get_agentic_poi_details(self, poi_id: str, doc_repo: 'IDocumentRepository') -> POIGetResponse:
        # 1. Graph RAG Retrieval
        with self.uow:
            graph_data = self.uow.pois.get_poi_graph_payload(id=poi_id, radius_km=3.0, limit=5)

        if not graph_data:
            raise EntityNotFoundError(
                f"POI with ID '{poi_id}' not found in the Knowledge Graph."
            )

        # The returned identity must be exactly the requested one; a mismatched
        # node is reported as not found rather than relabelled.
        returned_id = graph_data.get("POI_ID")
        if not isinstance(returned_id, str) or returned_id != poi_id:
            raise EntityNotFoundError(
                f"POI with ID '{poi_id}' not found in the Knowledge Graph."
            )

        # 2. Document RAG Retrieval (Circuit Breaker). When the repository is
        #    unimplemented or fails, the description is explicitly unavailable
        #    and the rating is null -- never an invented 0.
        doc_status = "available"
        doc_data: Dict[str, Any] = {}
        try:
            candidate = doc_repo.get_poi_documents(poi_id=poi_id)
            if not isinstance(candidate, dict):
                raise ValueError("document repository returned a non-object payload")
            doc_data = candidate
        except IntentedNotImplementedException:
            doc_status = "unavailable"
        except Exception:
            doc_status = "unavailable"

        missing: List[str] = []

        if doc_status == "available":
            insight = doc_data.get("insight") or ""
            seo_article = doc_data.get("seo_article") or ""
            raw_review = doc_data.get("review")
            review_map = raw_review if isinstance(raw_review, dict) else {}
            rating = _finite_nonnegative(review_map.get("rating"))
            review_text = review_map.get("review")
            review_text = review_text if isinstance(review_text, str) else ""
        else:
            insight = ""
            seo_article = ""
            rating = None
            review_text = ""
            missing.append("description")
            missing.append("rating")

        description = POIDescription(
            insight=insight,
            seo_article=seo_article,
            review=ReviewDetail(rating=rating, review=review_text),
            status=doc_status,
        )

        contact = graph_data.get("POI_Contact_Info")
        contact = contact if isinstance(contact, dict) else {}
        contact_info = POIContactInfo(
            website=contact.get("website") or "",
            fanpage=contact.get("fanpage") or "",
            phonenumber=contact.get("phonenumber") or "",
        )
        if not any((contact_info.website, contact_info.fanpage, contact_info.phonenumber)):
            missing.append("contact_info")

        # 3. Map the Offers safely: a missing name stays null and a missing
        #    price stays null; a "free" 0.0 is never fabricated.
        offers_list: List[OfferLite] = []
        for offer in graph_data.get("Offers") or []:
            if not isinstance(offer, dict):
                continue
            raw_name = offer.get("name")
            safe_name = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else None
            safe_price = _finite_nonnegative(offer.get("price"))
            if safe_name is None and safe_price is None:
                continue
            offers_list.append(OfferLite(name=safe_name, price=safe_price))

        # 4. Map the NEAR_BY list safely. A missing distance is null, not 0.
        nearby_list: List[NearbyPOI] = []
        for n in graph_data.get("NEAR_BY") or []:
            if not isinstance(n, dict):
                continue
            nearby_id = n.get("POI_ID")
            if not isinstance(nearby_id, str) or not nearby_id.strip():
                continue
            raw_addr = n.get("POI_Address")
            nearby_list.append(
                NearbyPOI(
                    poi=POILite(
                        id=nearby_id,
                        name=n.get("POI_Name") or "",
                        full_address=raw_addr if isinstance(raw_addr, str) and raw_addr.strip() else "Address not specified",
                    ),
                    distance=_finite_nonnegative(n.get("distance")),
                )
            )

        # 5. Defensively cast coordinates to finite in-range floats.
        safe_lat = _finite_in_range(graph_data.get("latitude"), -90.0, 90.0)
        safe_lng = _finite_in_range(graph_data.get("longitude"), -180.0, 180.0)
        if safe_lat is None:
            missing.append("latitude")
        if safe_lng is None:
            missing.append("longitude")

        # 6. Preserve explicit category ids (and the legacy display name).
        category_refs: List[CategoryRef] = []
        for c in graph_data.get("POI_Categories") or []:
            if not isinstance(c, dict):
                continue
            cat_id = c.get("id")
            cat_name = c.get("name")
            if cat_id is None and cat_name is None:
                continue
            category_refs.append(
                CategoryRef(id=cat_id, name=cat_name, context=c.get("context"))
            )
        if not category_refs:
            missing.append("poi_categories")

        operation_time = graph_data.get("operation_time")
        if not (isinstance(operation_time, str) and operation_time.strip()):
            operation_time = None
            missing.append("operation_time")

        address = graph_data.get("POI_Address")
        if not (isinstance(address, str) and address.strip()):
            address = None
            missing.append("address")

        # 7. Resolve parent geography from actual relationship chains, unless the
        #    record is a source-snapshot area claim. That qualification is a
        #    display/source claim only: it must never be promoted to a
        #    present-day administrative hierarchy.
        source_metadata, source_metadata_status = decode_source_metadata(
            graph_data.get("source_metadata_json"),
            graph_data.get("source_metadata_sha256"),
        )
        if source_metadata is not None:
            try:
                # Self-consistent hashes are not enough: the lineage must
                # actually belong to the POI returned by the graph.
                source_metadata.assert_bound_to_poi(returned_id)
            except ValueError:
                source_metadata = None
                source_metadata_status = "corrupt"

        stored_scope = graph_data.get("administrative_scope")
        if source_metadata is not None:
            administrative_scope = source_metadata.administrative_scope
        elif stored_scope == "source_snapshot_area_only":
            administrative_scope = stored_scope
        else:
            administrative_scope = None

        if source_metadata_status == "corrupt":
            context, context_status = None, "provenance_corrupt"
            missing.append("source_metadata")
        elif administrative_scope == "source_snapshot_area_only":
            context, context_status = None, "unverified_source_area"
            missing.append("current_administrative_context")
        else:
            context, context_status = resolve_administrative_context(
                graph_data.get("administrative_context_chains")
            )
        administrative_context = (
            AdministrativeContext(**context) if context else None
        )
        source_evidence = (
            SourceEvidenceSummary.from_metadata(source_metadata)
            if source_metadata is not None
            else None
        )
        source_context = None
        if source_metadata is not None and source_metadata_status == "valid":
            try:
                source_context = build_source_context(
                    derive_source_area(source_metadata), source_metadata
                )
            except (ValueError, SourceScopeError):
                source_metadata_status = "corrupt"
                source_evidence = None
                administrative_scope = None
                context, context_status = None, "provenance_corrupt"
                if "source_metadata" not in missing:
                    missing.append("source_metadata")

        # 8. Construct Final Payload
        result = POIResult(
            POI_ID=returned_id,
            POI_Name=graph_data.get("POI_Name") or "",
            POI_Address=address,
            POI_Category=graph_data.get("POI_Category"),
            latitude=safe_lat,
            longitude=safe_lng,
            operation_time=operation_time,
            POI_Description=description,
            POI_Contact_Info=contact_info,
            Offers=offers_list,
            NEAR_BY=nearby_list,
            administrative_context=administrative_context,
            administrative_context_status=context_status,
            source_metadata=source_evidence,
            source_metadata_status=source_metadata_status,
            source_context=source_context,
            administrative_scope=administrative_scope,
            POI_Categories=category_refs,
            missing_data=missing,
        )

        return POIGetResponse(success=True, result=result)

    def search_location_id(self, keyword: str) -> List[Dict[str, str]]:
        with self.uow:
            return self.uow.pois.search_location_id(keyword)


class CategoryManagementService(BaseManagementService[Category]):

    def _validate_payload(self, payload: Dict[str, Any]) -> Category:
        return Category.model_validate(payload)
    
    def _get_existing(self, entity_id: str) -> Category | None:
        return self.uow.cats.get_by_id(entity_id)
    
    def _execute_create(self, entity: Category) -> Category:
        return self.uow.cats.create(entity)
    
    def _execute_update(self, entity_id: str, entity: Category) -> Category:
        return self.uow.cats.update(entity_id, entity)

    def _execute_delete(self, entity_id: str) -> bool:
        return self.uow.cats.delete(entity_id)