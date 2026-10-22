from venv import logger

import hashlib
import json

from neo4j import Transaction
from typing import List, LiteralString, Optional, cast, Dict, Any

from app.core.base.repository import BaseMemgraphRepository

from app.core.utils.spatial import (
    EARTH_RADIUS_KM_LOWER_BOUND,
    NEARBY_RADIUS_KM_DEFAULT,
    conservative_prefilter_cypher,
    validate_radius_km,
)

from app.core.domain.graph_entities import (
    POI,
    UserPreference,
    Category,
    Tag,
    SourceMetadata,
    canonical_source_metadata_json,
    decode_source_metadata,
)
from app.core.domain.get_payload import (
    CategoryRef,
    OfferLite,
    POICompoundLite,
    POILite,
    SourceEvidenceSummary,
    resolve_administrative_context,
)
from app.core.domain.source_scope import (
    SourceScopeCorruption,
    SourceScopeMismatch,
    SourceSnapshotSelection,
    build_source_context,
    derive_source_area,
    qualify_source_record,
)


from app.core.interfaces.repositories import IPOIRepository
from app.core.interfaces.repositories import IUserBehaviorRepository
from shared_lib.travel_shared.exceptions import IntentedNotImplementedException
from app.core.interfaces.repositories import ICategoryRepository, ITagRepository


class IncompatibleStoredRadiusError(ValueError):
    """Stored incident ``:NEAR_BY`` radii contradict the requested policy.

    Raised *before* any edge deletion so the enclosing application mutation is
    rolled back instead of silently rebuilding the shared spatial policy at a
    different radius.
    """


class UnknownStoredRadiusError(ValueError):
    """Incident ``:NEAR_BY`` edges carry no stored radius (legacy/unknown).

    Missing radii are neither validated nor treated as compatible: they are an
    explicit migration gate. An authorized offline migration must backfill them
    before the application policy can be enforced.
    """


def _source_metadata_parameters(record: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize typed provenance into scalar node properties.

    Memgraph properties cannot be nested maps, so the full evidence is stored as
    deterministic JSON text plus a binding hash. Missing provenance explicitly
    writes ``None`` so a repeated upsert removes stale trust instead of keeping
    an older source claim.
    """
    metadata = record.get("source_metadata")
    if metadata is None:
        return {
            "source_metadata_json": None,
            "source_metadata_sha256": None,
            "administrative_scope": None,
            "source_area_id": None,
            "source_dataset_namespace": None,
            "source_snapshot_sha256": None,
        }
    if isinstance(metadata, SourceMetadata):
        parsed = metadata
    elif isinstance(metadata, dict):
        parsed = SourceMetadata.model_validate(metadata)
    elif isinstance(metadata, str):
        parsed = SourceMetadata.model_validate(json.loads(metadata))
    else:
        raise ValueError("source_metadata must be a typed object, JSON string or null.")

    record_id = record.get("id")
    if isinstance(record_id, str) and record_id.strip():
        parsed.assert_bound_to_poi(record_id)
    area = derive_source_area(parsed)
    canonical = canonical_source_metadata_json(parsed)
    return {
        "source_metadata_json": canonical,
        "source_metadata_sha256": hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest(),
        "administrative_scope": parsed.administrative_scope,
        "source_area_id": area.source_area_id,
        "source_dataset_namespace": area.dataset_namespace,
        "source_snapshot_sha256": area.input_sha256,
    }


def _batch_parameters(poi_batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return parameters without ever mutating the caller's batch.

    Provenance-free batches are forwarded by identity (the existing contract).
    Only records that actually carry ``source_metadata`` are copied and enriched
    with the scalar fields, leaving the caller's objects untouched.
    """
    if not any(
        isinstance(record, dict) and record.get("source_metadata") is not None
        for record in poi_batch
    ):
        return poi_batch

    prepared: List[Dict[str, Any]] = []
    for record in poi_batch:
        if not isinstance(record, dict) or record.get("source_metadata") is None:
            prepared.append(record)
            continue
        copy = dict(record)
        copy.update(_source_metadata_parameters(record))
        prepared.append(copy)
    return prepared


class MemgraphUserBehaviorRepository(BaseMemgraphRepository[UserPreference], IUserBehaviorRepository):
    def __init__(self, tx: Transaction):
        # Pass the transaction up to the base class
        super().__init__(tx)

    # ---------------------------------------------------------
    # STAGE 1 ROUTING ENGINE: CYPHER CLUSTERING
    # ---------------------------------------------------------
    def get_preferred_pois(self, user_id: str, city: str, district: Optional[str] = None, street: Optional[str] = None, limit: int = 10) -> List[POI]:
        """
        Traverses the graph to find POIs that match the user's PREFERS edges,
        enforcing a strict hierarchical location query (City -> Province -> Street).
        """
        city = city.strip() if city else ""
        district = district.strip() if district else None
        street = street.strip() if street else None

        if not city:
            raise ValueError("Hierarchical location query failed: 'city' is required as the base level.")
            
        if street and not district:
            raise ValueError("Hierarchical location query failed: 'province' must be provided if 'street' is queried.")
            
        if district and not city:
            raise ValueError("Hierarchical location query failed: 'city' must be provided if 'province' is queried.")
        
        query_lines = [
            "MATCH (u:User {id: $user_id})-[pref:PREFERS]->(trait)",
            "MATCH (trait)<-[:HAS_CATEGORY | :HAS_TAG]-(p:POI)",
            "WHERE p.addr_city = $city",
            # Current-jurisdiction selection only. Source-snapshot claims and
            # records with incomplete/corrupt provenance evidence are excluded;
            # absent provenance keeps the legacy behavior.
            "  AND p.source_metadata_json IS NULL",
            "  AND p.administrative_scope IS NULL",
        ]
        
        params = {
            "user_id": user_id,
            "city": city,
            "limit": limit
        }

        # Dynamically append hierarchical WHERE clauses
        if district:
            query_lines.append("  AND p.addr_district = $province")
            params["province"] = district
        
        if street:
            query_lines.append("  AND p.addr_street = $street")
            params["street"] = street

        # Finalize the algorithm and projection
        query_lines.extend([
            "WITH p, sum(pref.weight) AS match_score",
            "ORDER BY match_score DESC",
            "LIMIT $limit",
            "OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(all_c:Category)",
            "OPTIONAL MATCH (p)-[:HAS_TAG]->(t:Tag)",
            "RETURN p {",
            "    .id, .name, .longitude, .latitude, .operation_time, .rating, .menu,",
            "    address: {street_name: p.addr_street, ward: p.addr_ward, district: p.addr_district, city: p.addr_city, nation: p.addr_nation},",
            "    source_metadata: p.source_metadata_json,",
            "    contact_info: {phone_number: p.contact_phone, fanpage: p.contact_fanpage, website: p.contact_website},",
            "    poi_categories: collect(DISTINCT all_c { .id, .name, .context }),",
            "    tag: head(collect(DISTINCT t { .id, .name }))",
            "} AS poi_data"
        ])
        
        query = cast(LiteralString, "\n".join(query_lines))
        records = self._execute_read(query, params)
        
        return [POI(**record["poi_data"]) for record in records if record.get("poi_data")]

    def get_routing_candidates(self, user_id: str, city: str, province: Optional[str] = None, street: Optional[str] = None, limit: int = 50) -> List[POI]:
        """
        Advanced Stage 1 Pipeline Method.
        Funnels down to the physically possible POIs for the LLM to score.
        """
        # NOTE: Once your POI model includes specific properties for budget_tier or 
        # is_accessible, you must add them to the dynamic Cypher query above:
        # e.g., query_lines.append("  AND p.budget_tier = u.budget_level")
        # e.g., query_lines.append("  AND (u.requires_accessibility = False OR p.is_accessible = True)")
        
        return self.get_preferred_pois(user_id, city, province, street, limit)

    def set_preference(self, user_id: str, category_id: str, weight: float) -> None:
        """Draws a single weighted edge between a user and a category."""
        query = """
        MERGE (u:User {id: $user_id})
        WITH u
        MATCH (c:Category {id: $category_id})
        MERGE (u)-[r:PREFERS]->(c)
        SET r.weight = $weight
        """
        self._execute_write(query, {"user_id": user_id, "category_id": category_id, "weight": weight})

    # ---------------------------------------------------------
    # BASIC CRUD (SHADOW NODE MANAGEMENT)
    # ---------------------------------------------------------
    _PREFERENCE_LABELS = frozenset({"Category", "Tag"})

    def create(self, entity: UserPreference) -> UserPreference:
        """Sync a full ``UserPreference`` into the graph.

        The profile sync is expressed as **independent parameterized writes
        executed in the caller's single transaction**:

        1. merge the ``User`` shadow node and hard constraints,
        2. delete every obsolete ``:PREFERS`` edge (so an empty list means
           "clear this side of the profile"),
        3. re-draw the category edges,
        4. re-draw the tag edges.

        Because the steps are independent, an empty ``category_weights`` list no
        longer aborts the query before the tag edges are written (the previous
        single ``UNWIND $category_list ... UNWIND $tag_list`` pipeline dropped all
        later work whenever the first list was empty).
        """
        user_data = entity.model_dump(mode='json')

        self._execute_write(
            """
            MERGE (u:User {id: $user_id})
            SET u.budget_level = $budget_level,
                u.travel_pace = $travel_pace,
                u.requires_accessibility = $requires_accessibility
            """,
            {
                "user_id": entity.user_id,
                "budget_level": user_data.get("budget_level"),
                "travel_pace": user_data.get("travel_pace"),
                "requires_accessibility": entity.requires_accessibility,
            },
        )

        self._execute_write(
            """
            MATCH (u:User {id: $user_id})
            OPTIONAL MATCH (u)-[old_pref:PREFERS]->()
            DELETE old_pref
            """,
            {"user_id": entity.user_id},
        )

        self._write_preference_edges(
            entity.user_id,
            "Category",
            [{"id": k, "weight": v} for k, v in entity.category_weights.items()],
        )
        self._write_preference_edges(
            entity.user_id,
            "Tag",
            [{"id": k, "weight": v} for k, v in entity.tag_weights.items()],
        )
        return entity

    def _write_preference_edges(self, user_id: str, node_label: str, items: List[Dict[str, Any]]) -> None:
        """Draw ``:PREFERS`` edges to ``node_label`` nodes with the given weights.

        ``node_label`` is restricted to a two-value allow-list, so it is the only
        interpolated token and cannot carry caller input. An empty ``items`` list
        runs the query harmlessly and leaves other preference types untouched.
        """
        if node_label not in self._PREFERENCE_LABELS:
            raise ValueError(f"Unsupported preference label: {node_label!r}")
        query = f"""
        MATCH (u:User {{id: $user_id}})
        UNWIND $items AS item
        MATCH (n:{node_label} {{id: item.id}})
        MERGE (u)-[r:PREFERS]->(n)
        SET r.weight = item.weight
        """
        self._execute_write(query, {"user_id": user_id, "items": items})

    def update(self, id: str, entity: UserPreference) -> UserPreference:
        if entity.user_id != id:
            raise ValueError(
                "UserPreference update id must match the payload user_id "
                f"({id!r} != {entity.user_id!r})."
            )
        return self.create(entity)

    def delete(self, id: str) -> bool:
        query = """
        MATCH (u:User {id: $id})
        DETACH DELETE u
        RETURN count(u) AS deleted_count
        """
        result = self._execute_write(query, {"id": id})
        return result[0]["deleted_count"] > 0

    def get_by_id(self, id: str) -> Optional[UserPreference]:
        raise IntentedNotImplementedException("Retrieve full UserPreference via the Firebase repository.")

    def get_all(self, skip: int = 0, limit: int = 100) -> List[UserPreference]:
        raise IntentedNotImplementedException("Retrieve all UserPreferences via the Firebase repository.")
    
    from typing import List, Optional


class MemgraphPOIRepository(BaseMemgraphRepository[POI], IPOIRepository):
    def __init__(self, tx: 'Transaction'):
        super().__init__(tx)
    
    # ---------------------------------------------------------
    # BATCH CREATE (Highly Optimized for Ingestion)
    # ---------------------------------------------------------
    def build_nearby_edges_for_district(
        self,
        district_id: str,
        radius_km: float = NEARBY_RADIUS_KM_DEFAULT,
        *,
        enforce_fixed_radius: bool = True,
    ) -> int:
        """Replace the ``:NEAR_BY`` edges incident to a district, transactionally.

        Three steps run against the caller's active transaction:

        1. gate the stored incident radius against the requested policy (see
           below) -- this runs **before** any deletion;
        2. delete every ``:NEAR_BY`` edge incident to an anchor POI of the
           district -- anchors with missing/invalid coordinates are still
           matched here so their stale edges are cleaned;
        3. re-create the valid canonical pairs (conservative prefilter, both
           orientations, full-precision distance).

        Because steps 2 and 3 share one transaction, a failure between them
        rolls the deletion back and the previous edges survive. Edges that do
        not touch an anchor of this district (for example edges internal to
        another district) are never deleted.

        Radius policy: ``radius_km`` defaults to the shared global
        :data:`NEARBY_RADIUS_KM_DEFAULT` (3 km) and is the **fixed application
        radius**. With ``enforce_fixed_radius=True`` (the application default)
        every *known* stored radius must equal ``radius_km``; a uniform or mixed
        different configuration is rejected (``IncompatibleStoredRadiusError``)
        and edges without a stored radius are rejected as an explicit unknown
        migration gate (``UnknownStoredRadiusError``). Nothing is deleted on a
        rejected policy.

        ``enforce_fixed_radius=False`` is the explicit offline/**migration**
        policy: the incident edges are owned and replaced wholesale, so a
        uniform different radius is a legitimate full rebuild and legacy
        radius-less edges may be backfilled. A *mixed* known configuration is
        still rejected as inconsistent. This mode is never chosen automatically
        by the application path; use :meth:`migrate_nearby_edges_for_district`.
        See ``docs/decisions/012-spatial-integration.md``.
        """
        radius_km = validate_radius_km(radius_km)
        self._assert_consistent_incident_radius(
            "MATCH (d:District {id: $district_id})<-[:IN_DISTRICT*0..1]-()<-[:LOCATE_AT]-(anchor:POI)",
            {"district_id": district_id},
            radius_km,
            f"district {district_id!r}",
            enforce_fixed_radius=enforce_fixed_radius,
        )
        self._delete_incident_nearby_edges(
            "MATCH (d:District {id: $district_id})<-[:IN_DISTRICT*0..1]-()<-[:LOCATE_AT]-(anchor:POI)",
            {"district_id": district_id},
        )
        return self._rebuild_nearby_edges(
            "MATCH (d:District {id: $district_id})<-[:IN_DISTRICT*0..1]-()<-[:LOCATE_AT]-(p1:POI)",
            {"district_id": district_id},
            radius_km,
        )

    def migrate_nearby_edges_for_district(
        self, district_id: str, radius_km: float = NEARBY_RADIUS_KM_DEFAULT
    ) -> int:
        """Explicit offline/migration district rebuild (never auto-selected).

        Distinctly separate from the application path: it opts out of the fixed
        application radius gate because it is authorized to replace the shared
        policy wholesale (and may backfill legacy radius-less edges).
        """
        return self.build_nearby_edges_for_district(
            district_id, radius_km, enforce_fixed_radius=False
        )

    def build_nearby_edges_for_poi(
        self,
        poi_id: str,
        radius_km: float = NEARBY_RADIUS_KM_DEFAULT,
        *,
        enforce_fixed_radius: bool = True,
    ) -> int:
        """Explicit single-POI rebuild of incident ``:NEAR_BY`` edges.

        Required when an anchor moves out of its district: a district-scoped
        rebuild cannot clean the edges the moved POI left in its *old* district.
        This method deletes every edge incident to the POI and rebuilds its
        canonical pairs in one transaction, independent of district membership,
        so a downstream rebuild failure rolls the source mutation back.

        This is the method the application POI create/update path and the bulk
        ingestion spatial stage call; both always pass the single shared service
        radius (:data:`NEARBY_RADIUS_KM_DEFAULT`, 3 km) with the default
        ``enforce_fixed_radius=True``.

        Radius policy: the incident-radius gate is a read-time consistency check
        against the fixed application radius -- it is **not** advisory-lock based
        and makes **no** claim to enforce concurrency across writers. Under the
        application policy a known stored radius that differs from ``radius_km``
        (uniform or mixed) raises ``IncompatibleStoredRadiusError`` and legacy
        edges with no stored radius raise ``UnknownStoredRadiusError``; both run
        before any deletion so the mutation is rolled back honestly rather than
        silently flipping shared policy. The explicit offline/migration opt-out
        is :meth:`migrate_nearby_edges_for_poi`, never selected automatically.
        """
        radius_km = validate_radius_km(radius_km)
        self._assert_consistent_incident_radius(
            "MATCH (anchor:POI {id: $poi_id})",
            {"poi_id": poi_id},
            radius_km,
            f"POI {poi_id!r}",
            enforce_fixed_radius=enforce_fixed_radius,
        )
        self._delete_incident_nearby_edges(
            "MATCH (anchor:POI {id: $poi_id})",
            {"poi_id": poi_id},
        )
        return self._rebuild_nearby_edges(
            "MATCH (p1:POI {id: $poi_id})",
            {"poi_id": poi_id},
            radius_km,
        )

    def migrate_nearby_edges_for_poi(
        self, poi_id: str, radius_km: float = NEARBY_RADIUS_KM_DEFAULT
    ) -> int:
        """Explicit offline/migration single-POI rebuild (never auto-selected).

        Distinctly separate from the application path: it opts out of the fixed
        application radius gate because it is authorized to replace the shared
        policy wholesale (and may backfill legacy radius-less edges).
        """
        return self.build_nearby_edges_for_poi(
            poi_id, radius_km, enforce_fixed_radius=False
        )

    def _assert_consistent_incident_radius(
        self,
        anchor_match: str,
        params: Dict[str, Any],
        expected_radius_km: float,
        label: str,
        *,
        enforce_fixed_radius: bool = True,
    ) -> None:
        """Gate a rebuild on the stored incident radius policy, before deletion.

        ``enforce_fixed_radius=True`` (the application policy): every *known*
        stored radius must equal ``expected_radius_km``. Any known different
        radius -- uniform or mixed -- raises :class:`IncompatibleStoredRadiusError`.
        Edges with no stored radius raise :class:`UnknownStoredRadiusError` (an
        explicit unknown migration gate, never treated as validated).

        ``enforce_fixed_radius=False`` (explicit offline/migration policy): the
        incident edges are owned and replaced wholesale, so a uniform different
        radius is legitimate; only a *mixed* known configuration is rejected as
        inconsistent.
        """
        query = f"""
        {anchor_match}
        MATCH (anchor)-[r:NEAR_BY]-(:POI)
        RETURN DISTINCT r.radius_km AS radius_km
        """
        records = self._execute_read(cast(LiteralString, query), params)

        known = set()
        unknown = 0
        for record in records:
            value = record.get("radius_km")
            if value is None:
                unknown += 1
            else:
                known.add(value)

        if not enforce_fixed_radius:
            if len(known) > 1:
                raise IncompatibleStoredRadiusError(
                    "Inconsistent NEAR_BY radius configuration for "
                    f"{label}: found {sorted(known)}. Use one shared radius for "
                    "a migration rebuild."
                )
            return

        incompatible = {value for value in known if value != expected_radius_km}
        if incompatible:
            raise IncompatibleStoredRadiusError(
                "Stored NEAR_BY radius configuration for "
                f"{label} is incompatible with the fixed application radius "
                f"{expected_radius_km} km: found {sorted(known)}. An explicit "
                "offline radius migration is required to change the shared "
                "policy; the application will not silently flip it."
            )
        if unknown:
            raise UnknownStoredRadiusError(
                "Incident NEAR_BY edges for "
                f"{label} have no stored radius ({unknown} unknown/legacy edge "
                "group(s)); this is not validated. Run an explicit offline "
                "migration to backfill the radius before application rebuilds."
            )

    def _delete_incident_nearby_edges(self, anchor_match: str, params: Dict[str, Any]) -> int:
        """Delete every ``:NEAR_BY`` edge incident to any matched anchor."""
        query = f"""
        {anchor_match}
        MATCH (anchor)-[r:NEAR_BY]-(:POI)
        WITH DISTINCT r
        WITH collect(r) AS stale_edges
        WITH size(stale_edges) AS deleted_edges, stale_edges
        FOREACH (rel IN stale_edges | DELETE rel)
        RETURN deleted_edges
        """
        records = self._execute_write(cast(LiteralString, query), params)
        if records and len(records) > 0:
            return records[0].get("deleted_edges", 0)
        return 0

    def _rebuild_nearby_edges(self, anchor_match: str, params: Dict[str, Any], radius_km: float) -> int:
        """Merge canonical near pairs anchored on the matched ``p1`` nodes.

        Undirected canonical semantics (see ``docs/decisions/002-spatial-filter.md``):
        ``p2`` is matched graph-wide so cross-district pairs are included,
        matching is not gated on the anchor id, endpoints are normalised after
        matching both orientations, and the full-precision distance drives the
        final radius test.
        """
        prefilter = conservative_prefilter_cypher()

        query = f"""
        {anchor_match}
        WHERE p1.latitude IS NOT NULL AND p1.longitude IS NOT NULL

        CALL {{
            WITH p1
            MATCH (p2:POI)
            WHERE p2 <> p1
              AND p2.latitude IS NOT NULL
              AND p2.longitude IS NOT NULL
              AND {prefilter}
            WITH CASE WHEN id(p1) < id(p2) THEN p1 ELSE p2 END AS a,
                 CASE WHEN id(p1) < id(p2) THEN p2 ELSE p1 END AS b
            RETURN a, b
        }}
        WITH DISTINCT a, b
        WITH a, b, point.distance(
            point({{latitude: a.latitude, longitude: a.longitude}}),
            point({{latitude: b.latitude, longitude: b.longitude}})
        ) AS dist_meters
        WHERE dist_meters <= $radius_km * 1000.0
        MERGE (a)-[r:NEAR_BY]-(b)
        SET r.distance_km = dist_meters / 1000.0,
            r.distance_meters = dist_meters,
            r.radius_km = $radius_km
        RETURN count(r) AS created_edges
        """

        parameters = dict(params)
        parameters.update({
            "radius_km": radius_km,
            "earth_radius_lower_bound_km": EARTH_RADIUS_KM_LOWER_BOUND,
        })

        try:
            records = self._execute_write(cast(LiteralString, query), parameters)

            if records and len(records) > 0:
                return records[0].get("created_edges", 0)
            return 0

        except Exception as e:
            # Sanitized: never log the raw provider/DB error text.
            logger.error(
                "Graph Database Error while rebuilding NEAR_BY (%s).",
                type(e).__name__,
            )
            raise

    def batch_create(self, poi_batch: list[dict]) -> int:
        query = """
        UNWIND $batch AS poi

        // 1. Flatten Address safely. A missing address never reaches a
        //    null-keyed spatial MERGE.
        WITH poi,
             CASE WHEN poi.address IS NULL THEN [] ELSE [
                 poi.address.street_name,
                 poi.address.ward,
                 poi.address.district,
                 poi.address.city,
                 poi.address.nation
             ] END AS addr_parts
        WITH poi, [part IN addr_parts WHERE part IS NOT NULL AND part <> ""] AS valid_parts
        WITH poi,
             (poi.address IS NOT NULL
              AND coalesce(poi.administrative_scope, '') <> 'source_snapshot_area_only')
                 AS build_current_hierarchy,
             CASE WHEN size(valid_parts) = 0 THEN null
                  ELSE reduce(s = head(valid_parts), x IN tail(valid_parts) | s + ", " + x)
             END AS full_addr

        // 2. Defensively Merge Core POI (Removed Dict/List properties)
        MERGE (p:POI {id: poi.id})
        SET p += {
            name: poi.name,
            longitude: poi.longitude,
            latitude: poi.latitude,
            operation_time: poi.operation_time,
            full_address: full_addr,
            contact_phone: poi.contact_info.phone_number,
            contact_website: poi.contact_info.website,
            // Scalar provenance only: canonical JSON + binding hash + scope.
            // Missing metadata writes null, removing any stale source claim.
            source_metadata_json: poi.source_metadata_json,
            source_metadata_sha256: poi.source_metadata_sha256,
            administrative_scope: poi.administrative_scope,
            source_area_id: poi.source_area_id,
            source_dataset_namespace: poi.source_dataset_namespace,
            source_snapshot_sha256: poi.source_snapshot_sha256
        }

        // 2b. Any previous ordinary location link is stale after this upsert.
        //     A source-only/null-address record therefore cannot keep an old
        //     current hierarchy.
        WITH p, poi, build_current_hierarchy
        OPTIONAL MATCH (p)-[old_loc:LOCATE_AT]->()
        DELETE old_loc
        WITH DISTINCT p, poi, build_current_hierarchy

        // 3. Build the ordinary current hierarchy only when the record carries a
        //    real address AND is not a source-snapshot area claim.
        FOREACH (ignoreMe IN CASE WHEN build_current_hierarchy THEN [1] ELSE [] END |
            MERGE (n:Nation {id: toLower(trim(poi.address.nation))})
            ON CREATE SET n.name = trim(poi.address.nation)

            MERGE (c:City {id: toLower(trim(poi.address.city)) + "_" + toLower(trim(poi.address.nation))})
            ON CREATE SET c.name = trim(poi.address.city), c.nation = trim(poi.address.nation)
            MERGE (c)-[:IN_NATION]->(n)

            MERGE (d:District {id: toLower(trim(poi.address.district)) + "_" + toLower(trim(poi.address.city))})
            ON CREATE SET d.name = trim(poi.address.district), d.city = trim(poi.address.city)
            MERGE (d)-[:IN_CITY]->(c)

            // 4. Conditional LOCATE_AT fallback using strict IDs
            FOREACH (street IN CASE WHEN poi.address.street_name IS NOT NULL AND trim(poi.address.street_name) <> "" THEN [1] ELSE [] END |
                MERGE (s:Street {id: toLower(trim(poi.address.street_name)) + "_" + toLower(trim(poi.address.district))})
                ON CREATE SET s.name = trim(poi.address.street_name), s.district = trim(poi.address.district)
                MERGE (s)-[:IN_DISTRICT]->(d)
                MERGE (p)-[:LOCATE_AT]->(s)
            )
            FOREACH (streetless IN CASE WHEN poi.address.street_name IS NULL OR trim(poi.address.street_name) = "" THEN [1] ELSE [] END |
                MERGE (p)-[:LOCATE_AT]->(d)
            )
        )

        // 4b. Clear stale flat address shortcuts so city/district-scoped legacy
        //     retrieval can never admit a source-only or addressless record.
        FOREACH (ignoreMe IN CASE WHEN NOT build_current_hierarchy THEN [1] ELSE [] END |
            SET p.addr_city = null, p.addr_district = null, p.addr_street = null,
                p.addr_ward = null, p.addr_nation = null
        )

        // 6. Tags (Using FOREACH as a null-safe conditional)
        // Identity is the explicit, source-supplied id (matching single
        // create/update): a label that shares a display name but carries a
        // different id stays a distinct node, and an existing id keeps its
        // stored name (ON CREATE only -- no overwrite).
        FOREACH (ignoreMe IN CASE WHEN poi.tag IS NOT NULL THEN [1] ELSE [] END |
            MERGE (t:Tag {id: poi.tag.id})
            ON CREATE SET t.name = poi.tag.name
            MERGE (p)-[:HAS_TAG]->(t)
        )

        // 7. Categories
        // Identity is the explicit, source-supplied id (matching single
        // create/update); display name/context are written only the first
        // time the id is seen (ON CREATE only -- no overwrite).
        FOREACH (cat IN CASE WHEN poi.poi_categories IS NOT NULL THEN poi.poi_categories ELSE [] END |
            MERGE (catNode:Category {id: cat.id})
            ON CREATE SET catNode.name = cat.name, catNode.context = cat.context
            MERGE (p)-[:HAS_CATEGORY]->(catNode)
        )
        
       // 8. Menu Products (NEW: Unrolling list of dicts into linked Nodes)
        FOREACH (product IN CASE WHEN poi.menu IS NOT NULL THEN poi.menu ELSE [] END |
            MERGE (prod:Product {id: product.id})
            ON CREATE SET prod.canonical_name = product.product_name
            
            // Draw the edge and put the price on the edge!
            MERGE (p)-[r:OFFER]->(prod)
            SET r.price = product.price,
                r.shop_specific_name = product.product_name
        )
        """
        # Ensure we use the active transaction from the UoW. Provenance-free
        # batches are forwarded by identity; only metadata-bearing records are
        # copied, so the caller payload is never mutated.
        self._execute_write(query, {"batch": _batch_parameters(poi_batch)})
        return len(poi_batch)

    # ---------------------------------------------------------
    # SINGLE CREATE
    # ---------------------------------------------------------
    def create(self, entity: POI) -> POI:
        query = """
        WITH $poi AS poi,
             CASE WHEN $poi.address IS NULL THEN [] ELSE [
                 $poi.address.street_name,
                 $poi.address.ward,
                 $poi.address.district,
                 $poi.address.city,
                 $poi.address.nation
             ] END AS addr_parts
        WITH poi, [part IN addr_parts WHERE part IS NOT NULL AND part <> ""] AS valid_parts
        WITH poi,
             (poi.address IS NOT NULL
              AND coalesce(poi.administrative_scope, '') <> 'source_snapshot_area_only')
                 AS build_current_hierarchy,
             CASE WHEN size(valid_parts) = 0 THEN null
                  ELSE reduce(s = head(valid_parts), x IN tail(valid_parts) | s + ", " + x)
             END AS full_addr

        // 1. Create the core POI node (Removed direct menu assignment!)
        MERGE (p:POI {id: poi.id})
        SET p += {
            name: poi.name,
            longitude: poi.longitude,
            latitude: poi.latitude,
            operation_time: poi.operation_time,
            rating: poi.rating, // This is now safe because we json.dumped it in Python
            full_address: full_addr,
            contact_phone: poi.contact_info.phone_number,
            contact_fanpage: poi.contact_info.fanpage,
            contact_website: poi.contact_info.website,
            source_metadata_json: poi.source_metadata_json,
            source_metadata_sha256: poi.source_metadata_sha256,
            administrative_scope: poi.administrative_scope,
            source_area_id: poi.source_area_id,
            source_dataset_namespace: poi.source_dataset_namespace,
            source_snapshot_sha256: poi.source_snapshot_sha256
        }

        // 2. Sever any stale ordinary location link before rebuilding.
        WITH p, poi, build_current_hierarchy
        OPTIONAL MATCH (p)-[old_loc:LOCATE_AT]->()
        DELETE old_loc
        WITH DISTINCT p, poi, build_current_hierarchy

        // 3. Establish Spatial Hierarchy only for a genuine current address.
        FOREACH (ignoreMe IN CASE WHEN build_current_hierarchy THEN [1] ELSE [] END |
            MERGE (n:Nation {id: toLower(trim(poi.address.nation))})
            ON CREATE SET n.name = trim(poi.address.nation)

            MERGE (c:City {id: toLower(trim(poi.address.city)) + "_" + toLower(trim(poi.address.nation))})
            ON CREATE SET c.name = trim(poi.address.city), c.nation = trim(poi.address.nation)
            MERGE (c)-[:IN_NATION]->(n)

            MERGE (d:District {id: toLower(trim(poi.address.district)) + "_" + toLower(trim(poi.address.city))})
            ON CREATE SET d.name = trim(poi.address.district), d.city = trim(poi.address.city)
            MERGE (d)-[:IN_CITY]->(c)

            FOREACH (street IN CASE WHEN poi.address.street_name IS NOT NULL AND trim(poi.address.street_name) <> "" THEN [1] ELSE [] END |
                MERGE (s:Street {id: toLower(trim(poi.address.street_name)) + "_" + toLower(trim(poi.address.district))})
                ON CREATE SET s.name = trim(poi.address.street_name), s.district = trim(poi.address.district)
                MERGE (s)-[:IN_DISTRICT]->(d)
                MERGE (p)-[:LOCATE_AT]->(s)
            )
            FOREACH (streetless IN CASE WHEN poi.address.street_name IS NULL OR trim(poi.address.street_name) = "" THEN [1] ELSE [] END |
                MERGE (p)-[:LOCATE_AT]->(d)
            )
        )

        FOREACH (ignoreMe IN CASE WHEN NOT build_current_hierarchy THEN [1] ELSE [] END |
            SET p.addr_city = null, p.addr_district = null, p.addr_street = null,
                p.addr_ward = null, p.addr_nation = null
        )
        
        // 4. Establish Tag Relationship
        WITH p, poi
        FOREACH (ignoreMe IN CASE WHEN poi.tag IS NOT NULL THEN [1] ELSE [] END |
            MERGE (t:Tag {id: poi.tag.id})
            ON CREATE SET t.name = poi.tag.name
            MERGE (p)-[:HAS_TAG]->(t)
        )

        // 5. Establish Category Relationships. FOREACH keeps the POI row alive
        //    when the category list is empty (an empty list must not drop it).
        WITH p, poi
        FOREACH (cat IN CASE WHEN poi.poi_categories IS NOT NULL THEN poi.poi_categories ELSE [] END |
            MERGE (catNode:Category {id: cat.id})
            ON CREATE SET catNode.name = cat.name, catNode.context = cat.context
            MERGE (p)-[:HAS_CATEGORY]->(catNode)
        )
        
        // 6. Menu Products (UPDATED: [:OFFER] relationship with price property)
        FOREACH (product IN CASE WHEN poi.menu IS NOT NULL THEN poi.menu ELSE [] END |
            MERGE (prod:Product {id: product.id})
            ON CREATE SET prod.product_name = product.product_name
            
            // Create the specific OFFER relationship and assign the price to the edge
            MERGE (p)-[r:OFFER]->(prod)
            SET r.price = product.price
        )
        """
        payload = entity.model_dump(mode='json')
        payload.update(_source_metadata_parameters(payload))
        self._execute_write(query, {"poi": payload})
        return entity

    # ---------------------------------------------------------
    # READ OPERATIONS
    # ---------------------------------------------------------
    def get_by_id(self, id: str) -> Optional[POI]:
        query = """
        MATCH (p:POI {id: $id})
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(c:Category)
        OPTIONAL MATCH (p)-[:HAS_TAG]->(t:Tag)
        
        RETURN p {
            .id, .name, .longitude, .latitude, .operation_time, .rating, .menu,
            full_address: p.full_address,
            source_metadata: p.source_metadata_json,
            contact_info: {phone_number: p.contact_phone, fanpage: p.contact_fanpage, website: p.contact_website},
            poi_categories: collect(DISTINCT c { .id, .name, .context }),
            tag: head(collect(DISTINCT t { .id, .name }))
        } AS poi_data
        """
        records = self._execute_read(query, {"id": id})
        if not records or not records[0].get("poi_data"):
            return None
        return POI(**records[0]["poi_data"])

    def get_all(self, skip: int = 0, limit: int = 100) -> List[POI]:
        query = """
        MATCH (p:POI)
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(c:Category)
        OPTIONAL MATCH (p)-[:HAS_TAG]->(t:Tag)
        
        RETURN p {
            .id, .name, .longitude, .latitude, .operation_time, .rating, .menu,
            full_address: p.full_address,
            source_metadata: p.source_metadata_json,
            contact_info: {phone_number: p.contact_phone, fanpage: p.contact_fanpage, website: p.contact_website},
            poi_categories: collect(DISTINCT c { .id, .name, .context }),
            tag: head(collect(DISTINCT t { .id, .name }))
        } AS poi_data
        SKIP $skip LIMIT $limit
        """
        records = self._execute_read(query, {"skip": skip, "limit": limit})
        return [POI(**record["poi_data"]) for record in records if record.get("poi_data")]

    # ---------------------------------------------------------
    # UPDATE
    # ---------------------------------------------------------
    def update(self, id: str, entity: POI) -> POI:
        query = """
        WITH $poi AS poi,
             CASE WHEN $poi.address IS NULL THEN [] ELSE [
                 $poi.address.street_name,
                 $poi.address.ward,
                 $poi.address.district,
                 $poi.address.city,
                 $poi.address.nation
             ] END AS addr_parts
        WITH poi, [part IN addr_parts WHERE part IS NOT NULL AND part <> ""] AS valid_parts
        WITH poi,
             (poi.address IS NOT NULL
              AND coalesce(poi.administrative_scope, '') <> 'source_snapshot_area_only')
                 AS build_current_hierarchy,
             CASE WHEN size(valid_parts) = 0 THEN null
                  ELSE reduce(s = head(valid_parts), x IN tail(valid_parts) | s + ", " + x)
             END AS full_addr

        MATCH (p:POI {id: $id})

        // 1. Update core properties
        SET p += {
            name: poi.name,
            longitude: poi.longitude,
            latitude: poi.latitude,
            operation_time: poi.operation_time,
            rating: poi.rating,
            menu: poi.menu,
            full_address: full_addr,
            contact_phone: poi.contact_info.phone_number,
            contact_fanpage: poi.contact_info.fanpage,
            contact_website: poi.contact_info.website,
            source_metadata_json: poi.source_metadata_json,
            source_metadata_sha256: poi.source_metadata_sha256,
            administrative_scope: poi.administrative_scope,
            source_area_id: poi.source_area_id,
            source_dataset_namespace: poi.source_dataset_namespace,
            source_snapshot_sha256: poi.source_snapshot_sha256
        }

        // 2. Reconcile Spatial Information: always sever old connection. This
        //    is what removes a previous current hierarchy when the record
        //    transitions to a source-only area or a null address.
        WITH p, poi, build_current_hierarchy
        OPTIONAL MATCH (p)-[old_loc:LOCATE_AT]->()
        DELETE old_loc
        WITH DISTINCT p, poi, build_current_hierarchy

        // 3. Rebuild Spatial Hierarchy only for a genuine current address.
        FOREACH (ignoreMe IN CASE WHEN build_current_hierarchy THEN [1] ELSE [] END |
            MERGE (n:Nation {id: toLower(trim(poi.address.nation))})
            ON CREATE SET n.name = trim(poi.address.nation)

            MERGE (c:City {id: toLower(trim(poi.address.city)) + "_" + toLower(trim(poi.address.nation))})
            ON CREATE SET c.name = trim(poi.address.city), c.nation = trim(poi.address.nation)
            MERGE (c)-[:IN_NATION]->(n)

            MERGE (d:District {id: toLower(trim(poi.address.district)) + "_" + toLower(trim(poi.address.city))})
            ON CREATE SET d.name = trim(poi.address.district), d.city = trim(poi.address.city)
            MERGE (d)-[:IN_CITY]->(c)

            FOREACH (street IN CASE WHEN poi.address.street_name IS NOT NULL AND trim(poi.address.street_name) <> "" THEN [1] ELSE [] END |
                MERGE (s:Street {id: toLower(trim(poi.address.street_name)) + "_" + toLower(trim(poi.address.district))})
                ON CREATE SET s.name = trim(poi.address.street_name), s.district = trim(poi.address.district)
                MERGE (s)-[:IN_DISTRICT]->(d)
                MERGE (p)-[:LOCATE_AT]->(s)
            )
            FOREACH (streetless IN CASE WHEN poi.address.street_name IS NULL OR trim(poi.address.street_name) = "" THEN [1] ELSE [] END |
                MERGE (p)-[:LOCATE_AT]->(d)
            )
        )

        FOREACH (ignoreMe IN CASE WHEN NOT build_current_hierarchy THEN [1] ELSE [] END |
            SET p.addr_city = null, p.addr_district = null, p.addr_street = null,
                p.addr_ward = null, p.addr_nation = null
        )

        // 4. Reconcile Tag
        WITH p, poi
        OPTIONAL MATCH (p)-[old_t:HAS_TAG]->()
        DELETE old_t
        WITH DISTINCT p, poi
        FOREACH (ignoreMe IN CASE WHEN poi.tag IS NOT NULL THEN [1] ELSE [] END |
            MERGE (t:Tag {id: poi.tag.id})
            ON CREATE SET t.name = poi.tag.name
            MERGE (p)-[:HAS_TAG]->(t)
        )

        // 5. Reconcile Categories. FOREACH keeps the outer POI row alive when
        //    the category list is empty (all old edges were just deleted).
        WITH p, poi
        OPTIONAL MATCH (p)-[old_c:HAS_CATEGORY]->()
        DELETE old_c
        WITH DISTINCT p, poi
        FOREACH (cat IN CASE WHEN poi.poi_categories IS NOT NULL THEN poi.poi_categories ELSE [] END |
            MERGE (catNode:Category {id: cat.id})
            ON CREATE SET catNode.name = cat.name, catNode.context = cat.context
            MERGE (p)-[:HAS_CATEGORY]->(catNode)
        )

        RETURN p.id AS id
        """
        # Safely dump complex types using mode='json'
        payload = entity.model_dump(mode='json')
        payload.update(_source_metadata_parameters(payload))
        self._execute_write(query, {"id": id, "poi": payload})
        return entity

    # ---------------------------------------------------------
    # DELETE
    # ---------------------------------------------------------
    def delete(self, id: str) -> bool:
        query = """
        MATCH (p:POI {id: $id})
        // DETACH DELETE removes the node AND all incoming/outgoing relationships
        DETACH DELETE p
        RETURN count(p) AS deleted_count
        """
        result = self._execute_write(query, {"id": id})
        return result[0]["deleted_count"] > 0
        
    # ---------------------------------------------------------
    # SPECIFIC BEHAVIORS
    # ---------------------------------------------------------
    def get_by_city(self, city_name: str, skip: int = 0, limit: int = 100) -> List[POI]:
        query = """
        // 1. Anchor on the City node to drastically reduce the search space
        MATCH (city:City {name: $city})
        
        // 2. Traverse outward to find the POIs (*0..1 handles the District fallback gracefully)
        MATCH (city)<-[:IN_CITY]-(:District)<-[:IN_DISTRICT*0..1]-(loc)<-[:LOCATE_AT]-(p:POI)
        
        // 3. Fetch optional entity details
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(c:Category)
        OPTIONAL MATCH (p)-[:HAS_TAG]->(t:Tag)
        
        RETURN p {
            .id, .name, .longitude, .latitude, .operation_time, .rating, .menu,
            full_address: p.full_address,
            source_metadata: p.source_metadata_json,
            contact_info: {
                phone_number: p.contact_phone, 
                fanpage: p.contact_fanpage, 
                website: p.contact_website
            },
            poi_categories: collect(DISTINCT c { .id, .name, .context }),
            tag: head(collect(DISTINCT t { .id, .name }))
        } AS poi_data
        SKIP $skip LIMIT $limit
        """
        records = self._execute_read(query, {"city": city_name, "skip": skip, "limit": limit})
        return [POI(**record["poi_data"]) for record in records if record.get("poi_data")]
        
    def get_by_category_id(self, category_id: str) -> List[POI]:
        query = """
        // Anchor on the specific Category and traverse inward to find matching POIs
        MATCH (target_c:Category {id: $category_id})<-[:HAS_CATEGORY]-(p:POI)
        
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(all_c:Category)
        OPTIONAL MATCH (p)-[:HAS_TAG]->(t:Tag)
        
        RETURN p {
            .id, .name, .longitude, .latitude, .operation_time, .rating, .menu,
            full_address: p.full_address,
            source_metadata: p.source_metadata_json,
            contact_info: {
                phone_number: p.contact_phone,
                fanpage: p.contact_fanpage,
                website: p.contact_website
            },
            poi_categories: collect(DISTINCT all_c { .id, .name, .context }),
            tag: head(collect(DISTINCT t { .id, .name }))
        } AS poi_data
        """
        records = self._execute_read(query, {"category_id": category_id})
        return [POI(**record["poi_data"]) for record in records if record.get("poi_data")]    

    def get_poi_graph_payload(self, id: str, radius_km: float = 3.0, limit: int = 5) -> Optional[Dict[str, Any]]:
        """
        Retrieves the exact graph context, including latitude, longitude and the
        POI's structured ``administrative_context``.

        The admin context is gathered from the actual relationships -- both the
        direct ``(p)-[:LOCATE_AT]->(district)-[:IN_CITY]->(city)`` shape and the
        street-mediated ``(p)-[:LOCATE_AT]->(street)-[:IN_DISTRICT]->(district)->
        [:IN_CITY]->(city)`` shape -- and returned as raw chains. Resolution
        (including contradiction detection) happens in
        ``resolve_administrative_context``, so the first arbitrary chain is
        never selected.
        """
        query = """
        MATCH (p:POI {id: $id})

        // 1. Fetch Categories (with explicit ids) and Offers
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(cat:Category)
        WITH p, collect(DISTINCT cat { .id, .name, .context }) AS categories
        OPTIONAL MATCH (p)-[o:OFFER]->(:Product)
        WITH p, categories,
             collect(DISTINCT {name: o.shop_specific_name, price: o.price}) AS menu

        // 2. Gather parent-chain candidates from the direct district shape.
        OPTIONAL MATCH (p)-[:LOCATE_AT]->(d1:District)-[:IN_CITY]->(city1:City)
        WITH p, categories, menu,
             collect(DISTINCT {
                 district_id: d1.id, district_name: d1.name,
                 city_id: city1.id, city_name: city1.name
             }) AS ctx_direct

        // 3. Gather parent-chain candidates from the street-mediated shape.
        OPTIONAL MATCH (p)-[:LOCATE_AT]->(:Street)-[:IN_DISTRICT]->(d2:District)-[:IN_CITY]->(city2:City)
        WITH p, categories, menu, ctx_direct,
             collect(DISTINCT {
                 district_id: d2.id, district_name: d2.name,
                 city_id: city2.id, city_name: city2.name
             }) AS ctx_street
        WITH p, categories, menu,
             [x IN (ctx_direct + ctx_street)
                WHERE x.district_id IS NOT NULL OR x.city_id IS NOT NULL] AS admin_chains

        // 4. Fetch Pre-calculated Nearby POIs. NEAR_BY is stored undirected, so
        //    retrieval must be undirected too; this prevents an edge from being
        //    hidden when the stored orientation starts at the neighbouring node.
        OPTIONAL MATCH (p)-[nb:NEAR_BY]-(nearby:POI)
        WHERE nb.distance_km <= $radius_km

        WITH p, categories, menu, admin_chains, nearby, nb
        ORDER BY nb.distance_km ASC

        WITH p, categories, menu, admin_chains,
             collect(DISTINCT CASE WHEN nearby IS NOT NULL THEN {
                 POI_ID: nearby.id,
                 POI_Name: nearby.name,
                 POI_Address: nearby.full_address,
                 distance: nb.distance_km
             } ELSE null END)[0..$limit] AS nearby_list

        RETURN {
            POI_ID: p.id,
            POI_Name: p.name,
            POI_Address: p.full_address,
            POI_Category: CASE WHEN size(categories) > 0 THEN categories[0].name ELSE null END,
            POI_Categories: categories,
            operation_time: p.operation_time,
            latitude: p.latitude,
            longitude: p.longitude,
            source_metadata_json: p.source_metadata_json,
            source_metadata_sha256: p.source_metadata_sha256,
            administrative_scope: p.administrative_scope,
            POI_Contact_Info: {
                phonenumber: p.contact_phone,
                fanpage: p.contact_fanpage,
                website: p.contact_website
            },
            Offers: menu,
            NEAR_BY: [n IN nearby_list WHERE n IS NOT NULL],
            administrative_context_chains: admin_chains
        } AS graph_result
        """

        records = self._execute_read(query, {"id": id, "radius_km": radius_km, "limit": limit})

        if not records or not records[0].get("graph_result"):
            return None

        return records[0]["graph_result"]

    def get_by_city_lite(self, city_name: str, skip: int = 0, limit: int = 15) -> List[POILite]:
        query = """
        MATCH (c:City {name: $city})<-[:IN_CITY]-(:District)<-[:IN_DISTRICT*0..1]-()<-[:LOCATE_AT]-(p:POI)
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(cat:Category)
        OPTIONAL MATCH (p)-[r:OFFER]->(:Product)
        
        RETURN p {
            .id, 
            .name, 
            .operation_time,
            full_address: p.full_address,
            categories: [x IN collect(DISTINCT cat) WHERE x IS NOT NULL | x.name],
            offers: [x IN collect(DISTINCT {n: r.shop_specific_name, p: r.price}) WHERE x.n IS NOT NULL | x.n + " (" + toString(x.p) + ")"]
        } AS poi_data
        SKIP $skip LIMIT $limit
        """
        records = self._execute_read(query, {"city": city_name, "skip": skip, "limit": limit})
        return [POILite(**record["poi_data"]) for record in records if record.get("poi_data")]

    def get_by_district_lite(self, district_name: str, skip: int = 0, limit: int = 15) -> List[POILite]:
        query = """
        MATCH (d:District {name: $district_name})<-[:IN_DISTRICT*0..1]-()<-[:LOCATE_AT]-(p:POI)
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(cat:Category)
        OPTIONAL MATCH (p)-[r:OFFER]->(:Product)
        
        RETURN p {
            .id, .name, .operation_time,
            full_address: p.full_address,
            categories: [x IN collect(DISTINCT cat) WHERE x IS NOT NULL | x.name],
            offers: [x IN collect(DISTINCT {n: r.shop_specific_name, p: r.price}) WHERE x.n IS NOT NULL | x.n + " (" + toString(x.p) + ")"]
        } AS poi_data
        SKIP $skip LIMIT $limit
        """
        records = self._execute_read(query, {"district_name": district_name, "skip": skip, "limit": limit})
        return [POILite(**record["poi_data"]) for record in records if record.get("poi_data")]

    def get_by_street_lite(self, street_name: str, skip: int = 0, limit: int = 15) -> List[POILite]:
        """Upgraded to use the strict Street nodes defined in your batch_create."""
        query = """
        MATCH (s:Street)
        WHERE toLower(s.name) CONTAINS toLower($street_name)
        MATCH (s)<-[:LOCATE_AT]-(p:POI)
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(cat:Category)
        
        RETURN p {
            .id, .name, .operation_time,
            full_address: p.full_address,
            categories: [x IN collect(DISTINCT cat) WHERE x IS NOT NULL | x.name]
        } AS poi_data
        SKIP $skip LIMIT $limit
        """
        records = self._execute_read(query, {"street_name": street_name, "skip": skip, "limit": limit})
        return [POILite(**record["poi_data"]) for record in records if record.get("poi_data")]

    # ---------------------------------------------------------
    # NEW: HIERARCHICAL DISCOVERY (For Agent Drill-Down)
    # ---------------------------------------------------------
    def get_all_cities(self) -> List[Dict[str, str]]:
        """Returns all cities that actually contain POIs."""
        query = """
        MATCH (c:City)
        // Safety check: Only return cities that have actual POIs connected downstream
        WHERE EXISTS { MATCH (c)<-[:IN_CITY]-(:District)<-[:IN_DISTRICT*0..1]-()<-[:LOCATE_AT]-(:POI) }
        RETURN c.id AS id, c.name AS name
        ORDER BY c.name ASC
        """
        records = self._execute_read(query)
        return [{"id": r["id"], "name": r["name"]} for r in records if r.get("id")]

    def get_districts_by_city(self, city_id: str) -> List[Dict[str, str]]:
        """Returns all districts within a specific city_id."""
        query = """
        MATCH (d:District)-[:IN_CITY]->(c:City {id: $city_id})
        WHERE EXISTS { MATCH (d)<-[:IN_DISTRICT*0..1]-()<-[:LOCATE_AT]-(:POI) }
        RETURN d.id AS id, d.name AS name
        ORDER BY d.name ASC
        """
        records = self._execute_read(query, {"city_id": city_id})
        return [{"id": r["id"], "name": r["name"]} for r in records if r.get("id")]

    def get_streets_by_district(self, district_id: str) -> List[Dict[str, str]]:
        """Returns all streets within a specific district_id."""
        query = """
        MATCH (s:Street)-[:IN_DISTRICT]->(d:District {id: $district_id})
        WHERE EXISTS { MATCH (s)<-[:LOCATE_AT]-(:POI) }
        RETURN s.id AS id, s.name AS name
        ORDER BY s.name ASC
        """
        records = self._execute_read(query, {"district_id": district_id})
        return [{"id": r["id"], "name": r["name"]} for r in records if r.get("id")]

    # ---------------------------------------------------------
    # STRICT ID-BASED EXPLORATION ("Lite" Payload)
    # ---------------------------------------------------------
    def get_by_city_id_lite(self, city_id: str, skip: int = 0, limit: int = 15) -> List[POILite]:
        query = """
        // Anchor firmly on the ID, not the string name
        MATCH (c:City {id: $city_id})<-[:IN_CITY]-(:District)<-[:IN_DISTRICT*0..1]-()<-[:LOCATE_AT]-(p:POI)
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(cat:Category)
        OPTIONAL MATCH (p)-[r:OFFER]->(:Product)
        
        RETURN p {
            .id, .name, .operation_time,
            full_address: p.full_address,
            categories: [x IN collect(DISTINCT cat) WHERE x IS NOT NULL | x.name],
            offers: [x IN collect(DISTINCT {n: r.shop_specific_name, p: r.price}) WHERE x.n IS NOT NULL | x.n + " (" + toString(x.p) + ")"]
        } AS poi_data
        SKIP $skip LIMIT $limit
        """
        records = self._execute_read(query, {"city_id": city_id, "skip": skip, "limit": limit})
        return [POILite(**record["poi_data"]) for record in records if record.get("poi_data")]

    def get_by_district_id_lite(self, district_id: str, skip: int = 0, limit: int = 15) -> List[POILite]:
        query = """
        MATCH (d:District {id: $district_id})<-[:IN_DISTRICT*0..1]-()<-[:LOCATE_AT]-(p:POI)
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(cat:Category)
        OPTIONAL MATCH (p)-[r:OFFER]->(:Product)
        
        RETURN p {
            .id, .name, .operation_time,
            full_address: p.full_address,
            categories: [x IN collect(DISTINCT cat) WHERE x IS NOT NULL | x.name],
            offers: [x IN collect(DISTINCT {n: r.shop_specific_name, p: r.price}) WHERE x.n IS NOT NULL | x.n + " (" + toString(x.p) + ")"]
        } AS poi_data
        SKIP $skip LIMIT $limit
        """
        records = self._execute_read(query, {"district_id": district_id, "skip": skip, "limit": limit})
        return [POILite(**record["poi_data"]) for record in records if record.get("poi_data")]

    def get_by_street_id_lite(self, street_id: str, skip: int = 0, limit: int = 15) -> List[POILite]:
        query = """
        MATCH (s:Street {id: $street_id})<-[:LOCATE_AT]-(p:POI)
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(cat:Category)
        OPTIONAL MATCH (p)-[r:OFFER]->(:Product)
        
        RETURN p {
            .id, .name, .operation_time,
            full_address: p.full_address,
            categories: [x IN collect(DISTINCT cat) WHERE x IS NOT NULL | x.name],
            offers: [x IN collect(DISTINCT {n: r.shop_specific_name, p: r.price}) WHERE x.n IS NOT NULL | x.n + " (" + toString(x.p) + ")"]
        } AS poi_data
        SKIP $skip LIMIT $limit
        """
        records = self._execute_read(query, {"street_id": street_id, "skip": skip, "limit": limit})
        return [POILite(**record["poi_data"]) for record in records if record.get("poi_data")]

    def get_by_offered_products_lite(self, product_keyword: str, skip: int = 0, limit: int = 15) -> List[POILite]:
        query = """
        MATCH (p:POI)-[r:OFFER]->(prod:Product)
        WHERE toLower(prod.canonical_name) CONTAINS toLower($product_keyword)
           OR toLower(r.shop_specific_name) CONTAINS toLower($product_keyword)
           
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(cat:Category)
        
        RETURN p {
            .id, .name, .operation_time,
            full_address: p.full_address,
            categories: [x IN collect(DISTINCT cat) WHERE x IS NOT NULL | x.name],
            offers: [r.shop_specific_name + " (" + toString(r.price) + ")"]
        } AS poi_data
        SKIP $skip LIMIT $limit
        """
        records = self._execute_read(query, {"product_keyword": product_keyword, "skip": skip, "limit": limit})
        return [POILite(**record["poi_data"]) for record in records if record.get("poi_data")]

    def get_all_categories(self) -> List[Dict[str, str]]:
        query = """
        MATCH (c:Category)
        WHERE EXISTS { MATCH (:POI)-[:HAS_CATEGORY]->(c) } 
        RETURN c.id AS id, c.name AS name
        ORDER BY c.name ASC
        """
        records = self._execute_read(query)
        return [{"id": r["id"], "name": r["name"]} for r in records if r.get("id")]

    def get_by_category_id_lite(self, category_id: str, skip: int = 0, limit: int = 100) -> List[POILite]:
        query = """
        MATCH (target_c:Category {id: $category_id})<-[:HAS_CATEGORY]-(p:POI)
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(all_c:Category)
        OPTIONAL MATCH (p)-[r:OFFER]->(:Product)
        
        RETURN p {
            .id, .name, .operation_time,
            full_address: p.full_address,
            categories: [cat IN collect(DISTINCT all_c) WHERE cat IS NOT NULL | cat.name],
            offers: [x IN collect(DISTINCT {n: r.shop_specific_name, p: r.price}) WHERE x.n IS NOT NULL | x.n + " (" + toString(x.p) + ")"]
        } AS poi_data
        SKIP $skip LIMIT $limit
        """
        records = self._execute_read(query, {"category_id": category_id, "skip": skip, "limit": limit})
        return [POILite(**record["poi_data"]) for record in records if record.get("poi_data")]

    # ---------------------------------------------------------
    # CONJUNCTIVE EXACT-ID EXPLORATION (compound)
    # ---------------------------------------------------------
    def _compound_from_record(self, record: Dict[str, Any]) -> Optional[POICompoundLite]:
        poi_id = record.get("id")
        if not isinstance(poi_id, str) or not poi_id.strip():
            return None

        source_metadata, source_metadata_status = decode_source_metadata(
            record.get("source_metadata_json"),
            record.get("source_metadata_sha256"),
        )
        if source_metadata is not None:
            try:
                source_metadata.assert_bound_to_poi(poi_id)
            except ValueError:
                source_metadata = None
                source_metadata_status = "corrupt"

        stored_scope = record.get("administrative_scope")
        if source_metadata is not None:
            administrative_scope = source_metadata.administrative_scope
        elif stored_scope == "source_snapshot_area_only":
            administrative_scope = stored_scope
        else:
            administrative_scope = None

        if source_metadata_status == "corrupt":
            context, context_status = None, "provenance_corrupt"
        elif administrative_scope == "source_snapshot_area_only":
            context, context_status = None, "unverified_source_area"
        else:
            context, context_status = resolve_administrative_context(
                record.get("administrative_context_chains")
            )
        source_evidence = (
            SourceEvidenceSummary.from_metadata(source_metadata)
            if source_metadata is not None
            else None
        )

        categories = [
            CategoryRef(
                id=c.get("id"),
                name=c.get("name"),
                context=c.get("context"),
            )
            for c in (record.get("categories") or [])
            if isinstance(c, dict)
            and (c.get("id") is not None or c.get("name") is not None)
        ]

        offers: List[OfferLite] = []
        for raw_offer in record.get("offers") or []:
            if not isinstance(raw_offer, dict):
                continue
            name = raw_offer.get("name")
            price = raw_offer.get("price")
            if name is None and price is None:
                continue
            offers.append(OfferLite(name=name, price=price))

        return POICompoundLite(
            id=poi_id,
            name=record.get("name"),
            full_address=record.get("full_address"),
            operation_time=record.get("operation_time"),
            categories=categories,
            offers=offers,
            administrative_context=context,
            administrative_context_status=context_status,
            source_metadata=source_evidence,
            source_metadata_status=source_metadata_status,
            administrative_scope=administrative_scope,
        )

    def _compound_from_source_record(
        self,
        record: Dict[str, Any],
        selection: SourceSnapshotSelection,
    ) -> Optional[POICompoundLite]:
        poi_id = record.get("id")
        if not isinstance(poi_id, str) or not poi_id.strip():
            raise SourceScopeCorruption("record has no usable POI id.")

        source_metadata, source_metadata_status = decode_source_metadata(
            record.get("source_metadata_json"),
            record.get("source_metadata_sha256"),
        )
        if source_metadata is None:
            raise SourceScopeCorruption(
                f"source metadata is {source_metadata_status}, not valid."
            )

        identity = qualify_source_record(
            poi_id,
            source_metadata,
            selection,
            cached_area_id=record.get("source_area_id"),
            cached_namespace=record.get("source_dataset_namespace"),
            cached_snapshot=record.get("source_snapshot_sha256"),
        )

        categories = [
            CategoryRef(
                id=c.get("id"),
                name=c.get("name"),
                context=c.get("context"),
            )
            for c in (record.get("categories") or [])
            if isinstance(c, dict)
            and (c.get("id") is not None or c.get("name") is not None)
        ]

        offers: List[OfferLite] = []
        for raw_offer in record.get("offers") or []:
            if not isinstance(raw_offer, dict):
                continue
            name = raw_offer.get("name")
            price = raw_offer.get("price")
            if name is None and price is None:
                continue
            offers.append(OfferLite(name=name, price=price))

        return POICompoundLite(
            id=poi_id,
            name=record.get("name"),
            full_address=record.get("full_address"),
            operation_time=record.get("operation_time"),
            categories=categories,
            offers=offers,
            administrative_context=None,
            administrative_context_status="unverified_source_area",
            source_metadata=SourceEvidenceSummary.from_metadata(source_metadata),
            source_metadata_status="valid",
            source_context=build_source_context(identity, source_metadata),
            administrative_scope=source_metadata.administrative_scope,
        )

    def get_compound_explore_lite(
        self,
        city_id: Optional[str] = None,
        district_id: Optional[str] = None,
        street_id: Optional[str] = None,
        category_id: Optional[str] = None,
        product_keyword: Optional[str] = None,
        limit: int = 15,
        offset: int = 0,
    ) -> List[POICompoundLite]:
        """Apply every supplied exact id conjunctively *before* the limit.

        Correctness properties (see docs/decisions/006-mcp-evidence-contract.md):

        * ``city_id`` / ``district_id`` / ``street_id`` / ``category_id`` are
          matched exactly. ``category_id`` is never translated to a display
          name, so ``cat_a`` and a substring ``cat`` cannot collide.
        * ``product_keyword`` is only ever used as a bound parameter against a
          textual field; it is never interpolated into the query.
        * If a supplied ``district_id`` does not belong to the supplied
          ``city_id`` no POI can satisfy both EXISTS clauses, so the result is
          empty rather than silently ignoring one constraint.
        * ``WITH DISTINCT p`` + ``ORDER BY p.id`` gives a deterministic,
          duplicate-free page; ``SKIP``/``LIMIT`` are applied on that page, so no
          arbitrary over-fetch can drop valid matches before filtering.
        """
        query = """
        MATCH (p:POI)
        WHERE ($city_id IS NULL OR
                 EXISTS { MATCH (p)-[:LOCATE_AT]->(:District)-[:IN_CITY]->(:City {id: $city_id}) }
              OR EXISTS { MATCH (p)-[:LOCATE_AT]->(:Street)-[:IN_DISTRICT]->(:District)-[:IN_CITY]->(:City {id: $city_id}) })
          AND ($district_id IS NULL OR
                 EXISTS { MATCH (p)-[:LOCATE_AT]->(:District {id: $district_id}) }
              OR EXISTS { MATCH (p)-[:LOCATE_AT]->(:Street)-[:IN_DISTRICT]->(:District {id: $district_id}) })
          AND ($street_id IS NULL OR
                 EXISTS { MATCH (p)-[:LOCATE_AT]->(:Street {id: $street_id}) })
          AND ($category_id IS NULL OR
                 EXISTS { MATCH (p)-[:HAS_CATEGORY]->(:Category {id: $category_id}) })
          AND ($product_keyword IS NULL OR
                 EXISTS { MATCH (p)-[ro:OFFER]->(prod:Product)
                          WHERE toLower(COALESCE(prod.canonical_name, '')) CONTAINS toLower($product_keyword)
                             OR toLower(COALESCE(ro.shop_specific_name, '')) CONTAINS toLower($product_keyword) })
          // Default/current exploration excludes every provenance-bearing record:
          // valid source-only records are not present-day containment, and a
          // corrupt qualification cannot be promoted to current context.
          AND p.source_metadata_json IS NULL
          AND p.source_area_id IS NULL
          AND coalesce(p.administrative_scope, '') <> 'source_snapshot_area_only'

        WITH DISTINCT p
        ORDER BY p.id
        SKIP $offset LIMIT $limit

        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(cat:Category)
        WITH p, collect(DISTINCT cat { .id, .name, .context }) AS categories
        OPTIONAL MATCH (p)-[o:OFFER]->(:Product)
        WITH p, categories,
             collect(DISTINCT {name: o.shop_specific_name, price: o.price}) AS offers

        OPTIONAL MATCH (p)-[:LOCATE_AT]->(d1:District)-[:IN_CITY]->(city1:City)
        WITH p, categories, offers,
             collect(DISTINCT {
                 district_id: d1.id, district_name: d1.name,
                 city_id: city1.id, city_name: city1.name
             }) AS ctx_direct
        OPTIONAL MATCH (p)-[:LOCATE_AT]->(:Street)-[:IN_DISTRICT]->(d2:District)-[:IN_CITY]->(city2:City)
        WITH p, categories, offers, ctx_direct,
             collect(DISTINCT {
                 district_id: d2.id, district_name: d2.name,
                 city_id: city2.id, city_name: city2.name
             }) AS ctx_street
        WITH p, categories, offers,
             [x IN (ctx_direct + ctx_street)
                WHERE x.district_id IS NOT NULL OR x.city_id IS NOT NULL] AS admin_chains

        RETURN p.id AS id,
               p.name AS name,
               p.operation_time AS operation_time,
               p.full_address AS full_address,
               p.source_metadata_json AS source_metadata_json,
               p.source_metadata_sha256 AS source_metadata_sha256,
               p.administrative_scope AS administrative_scope,
               categories AS categories,
               offers AS offers,
               admin_chains AS administrative_context_chains
        """

        parameters = {
            "city_id": city_id,
            "district_id": district_id,
            "street_id": street_id,
            "category_id": category_id,
            "product_keyword": product_keyword,
            "limit": limit,
            "offset": offset,
        }
        records = self._execute_read(query, parameters)

        results: List[POICompoundLite] = []
        for record in records:
            mapped = self._compound_from_record(record)
            if mapped is not None:
                results.append(mapped)
        return results

    def get_compound_explore_source(
        self,
        selection: SourceSnapshotSelection,
        city_id: Optional[str] = None,
        district_id: Optional[str] = None,
        street_id: Optional[str] = None,
        category_id: Optional[str] = None,
        product_keyword: Optional[str] = None,
        limit: int = 15,
        offset: int = 0,
    ) -> tuple[List[POICompoundLite], Dict[str, Any]]:
        """Explicit source mode with fail-closed qualification and a scan report."""
        area_ids = selection.area_ids
        if len(area_ids) == 1:
            selector_clause = """
                 (p.source_area_id = $source_area_id
                  AND p.source_dataset_namespace = $dataset_namespace
                  AND p.source_snapshot_sha256 = $input_sha256)
              OR p.source_area_id IS NULL
            """
            selector_parameters = {"source_area_id": area_ids[0]}
        else:
            # One bounded, parameterized union over the concrete selected ids:
            # the scan loop and SKIP/LIMIT stay global, never per area.
            selector_clause = """
                 (p.source_area_id IN $source_area_ids
                  AND p.source_dataset_namespace = $dataset_namespace
                  AND p.source_snapshot_sha256 = $input_sha256)
              OR p.source_area_id IS NULL
            """
            selector_parameters = {"source_area_ids": list(area_ids)}

        query = f"""
        MATCH (p:POI)
        WHERE p.source_metadata_json IS NOT NULL
          AND ($city_id IS NULL OR
                 EXISTS {{ MATCH (p)-[:LOCATE_AT]->(:District)-[:IN_CITY]->(:City {{id: $city_id}}) }}
              OR EXISTS {{ MATCH (p)-[:LOCATE_AT]->(:Street)-[:IN_DISTRICT]->(:District)-[:IN_CITY]->(:City {{id: $city_id}}) }})
          AND ($district_id IS NULL OR
                 EXISTS {{ MATCH (p)-[:LOCATE_AT]->(:District {{id: $district_id}}) }}
              OR EXISTS {{ MATCH (p)-[:LOCATE_AT]->(:Street)-[:IN_DISTRICT]->(:District {{id: $district_id}}) }})
          AND ($street_id IS NULL OR
                 EXISTS {{ MATCH (p)-[:LOCATE_AT]->(:Street {{id: $street_id}}) }})
          AND ($category_id IS NULL OR
                 EXISTS {{ MATCH (p)-[:HAS_CATEGORY]->(:Category {{id: $category_id}}) }})
          AND ($product_keyword IS NULL OR
                 EXISTS {{ MATCH (p)-[ro:OFFER]->(prod:Product)
                          WHERE toLower(COALESCE(prod.canonical_name, '')) CONTAINS toLower($product_keyword)
                             OR toLower(COALESCE(ro.shop_specific_name, '')) CONTAINS toLower($product_keyword) }})
          // Fully-cached matching selectors are a fast path; records written
          // before the flat cache existed are re-qualified in Python. A cached
          // selector for another area is never trusted or returned.
          AND ({selector_clause})
          AND ($after_id IS NULL OR p.id > $after_id)

        WITH DISTINCT p
        ORDER BY p.id
        LIMIT $page_size

        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(cat:Category)
        WITH p, collect(DISTINCT cat {{ .id, .name, .context }}) AS categories
        OPTIONAL MATCH (p)-[o:OFFER]->(:Product)
        WITH p, categories,
             collect(DISTINCT {{name: o.shop_specific_name, price: o.price}}) AS offers

        RETURN p.id AS id,
               p.name AS name,
               p.operation_time AS operation_time,
               p.full_address AS full_address,
               p.source_metadata_json AS source_metadata_json,
               p.source_metadata_sha256 AS source_metadata_sha256,
               p.administrative_scope AS administrative_scope,
               p.source_area_id AS source_area_id,
               p.source_dataset_namespace AS source_dataset_namespace,
               p.source_snapshot_sha256 AS source_snapshot_sha256,
               categories AS categories,
               offers AS offers
        """

        page_size = 250
        max_records_scanned = 100000
        target = offset + limit
        matched: List[POICompoundLite] = []
        scanned = 0
        excluded_corrupt = 0
        excluded_mismatch = 0
        truncated = False
        exhausted = False
        after_id: Optional[str] = None

        while True:
            remaining = max_records_scanned - scanned
            if remaining <= 0:
                truncated = True
                break
            current_page = min(page_size, remaining)
            records = self._execute_read(
                query,
                {
                    **selector_parameters,
                    "dataset_namespace": selection.dataset_namespace,
                    "input_sha256": selection.input_sha256,
                    "city_id": city_id,
                    "district_id": district_id,
                    "street_id": street_id,
                    "category_id": category_id,
                    "product_keyword": product_keyword,
                    "after_id": after_id,
                    "page_size": current_page,
                },
            )
            if not records:
                exhausted = True
                break

            for record in records:
                scanned += 1
                record_id = record.get("id")
                if isinstance(record_id, str) and record_id.strip():
                    after_id = record_id
                try:
                    mapped = self._compound_from_source_record(record, selection)
                except SourceScopeMismatch:
                    excluded_mismatch += 1
                    continue
                except SourceScopeCorruption:
                    excluded_corrupt += 1
                    continue
                if mapped is not None:
                    matched.append(mapped)

            if len(matched) >= target:
                break
            if len(records) < current_page:
                exhausted = True
                break
            if after_id is None:
                truncated = True
                break

        page = matched[offset : offset + limit]
        report = {
            "scanned_record_count": scanned,
            "matched_record_count": len(matched),
            "excluded_corrupt_count": excluded_corrupt,
            "excluded_scope_mismatch_count": excluded_mismatch,
            "scan_complete": not truncated,
            "scan_exhausted": exhausted,
            "truncated": truncated,
        }
        return page, report

    def iter_source_scope_records(
        self,
        after_id: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        query = """
        MATCH (p:POI)
        WHERE p.source_metadata_json IS NOT NULL
          AND ($after_id IS NULL OR p.id > $after_id)
        RETURN p.id AS id,
               p.source_metadata_json AS source_metadata_json,
               p.source_metadata_sha256 AS source_metadata_sha256,
               p.administrative_scope AS administrative_scope,
               p.source_area_id AS source_area_id,
               p.source_dataset_namespace AS source_dataset_namespace,
               p.source_snapshot_sha256 AS source_snapshot_sha256
        ORDER BY p.id
        LIMIT $limit
        """
        return self._execute_read(
            query, {"after_id": after_id, "limit": limit}
        )

    def search_location_id(self, keyword: str, limit: int = 15) -> List[Dict[str, str]]:
        """Resolve English/Vietnamese names to strict Graph IDs plus parents.

        For a ``District`` match the parent ``city_id``/``city_name`` are
        returned; for a ``Street`` match both the parent ``district_id``/
        ``district_name`` and ``city_id``/``city_name`` are returned. The result
        order is deterministic and bounded, and no automatic choice is made
        between candidates.
        """
        query = """
        WITH toLower(trim($keyword)) AS kw,
             replace(toLower(trim($keyword)), 'district', 'quan') AS kw_vn

        MATCH (n) WHERE (n:City OR n:District OR n:Street)
        AND (toLower(n.name) CONTAINS kw OR toLower(n.name) CONTAINS kw_vn)

        OPTIONAL MATCH (n)-[:IN_CITY]->(direct_city:City)
        OPTIONAL MATCH (n)-[:IN_DISTRICT]->(mid_district:District)-[:IN_CITY]->(via_city:City)

        WITH labels(n)[0] AS type, n.id AS id, n.name AS name,
             direct_city, mid_district, via_city

        RETURN type AS type,
               id AS id,
               name AS name,
               mid_district.id AS district_id,
               mid_district.name AS district_name,
               COALESCE(via_city.id, direct_city.id) AS city_id,
               COALESCE(via_city.name, direct_city.name) AS city_name
        ORDER BY type ASC, name ASC, id ASC
        LIMIT $limit
        """
        records = self._execute_read(query, {"keyword": keyword, "limit": limit})
        results: List[Dict[str, str]] = []
        for record in records:
            if not record.get("id"):
                continue
            results.append(
                {
                    "type": record.get("type"),
                    "id": record.get("id"),
                    "name": record.get("name"),
                    "district_id": record.get("district_id"),
                    "district_name": record.get("district_name"),
                    "city_id": record.get("city_id"),
                    "city_name": record.get("city_name"),
                }
            )
        return results


class MemgraphCategoryRepository(BaseMemgraphRepository[Category], ICategoryRepository):
    def __init__(self, tx):
        super().__init__(tx)

    def _map_dict_to_entity(self, data: Dict[str, Any], node_key: str = "c") -> Category:
        node_props = data.get(node_key, {})
        return Category(id=node_props.get("id"), name=node_props.get("name"), context=node_props.get("context"))

    def get_by_name(self, name: str) -> Optional[Category]:
        query = "MATCH (c:Category {name: $name}) RETURN c"
        results = self._execute_read(query, {"name": name})
        if not results:
            return None
        return self._map_dict_to_entity(results[0], "c")

    def create(self, entity: Category) -> Category:
        query = (
            "CREATE (c:Category {id: $id, name: $name, context: $context}) RETURN c"
        )
        # ``context`` is a required, validated, nonblank domain field; it is
        # persisted verbatim so the created node round-trips the same context.
        results = self._execute_write(
            query,
            {"id": entity.id, "name": entity.name, "context": entity.context},
        )
        if not results:
            raise RuntimeError(f"Failed to create Category: {entity.name}")
        return self._map_dict_to_entity(results[0], "c")

    def get_by_id(self, id: str) -> Optional[Category]:
        query = "MATCH (c:Category {id: $id}) RETURN c"
        results = self._execute_read(query, {"id": id})
        if not results:
            return None
        return self._map_dict_to_entity(results[0], "c")

    def get_all(self, skip: int = 0, limit: int = 100) -> List[Category]:
        query = """
        MATCH (c:Category) 
        RETURN c 
        SKIP $skip LIMIT $limit
        """
        results = self._execute_read(query, {"skip": skip, "limit": limit})
        return [self._map_dict_to_entity(record, "c") for record in results]

    def update(self, id: str, entity: Category) -> Category:
        query = """
        MATCH (c:Category {id: $id})
        SET c.name = $name, c.context = $context
        RETURN c
        """
        # We use 'id' from the parameter to find the node, and update properties
        # from the 'entity'. ``context`` must round-trip (domain requires it to
        # be nonblank), so it is written together with the name.
        results = self._execute_write(
            query,
            {"id": id, "name": entity.name, "context": entity.context},
        )
        if not results:
            raise ValueError(f"Category with id {id} not found for update.")
        return self._map_dict_to_entity(results[0], "c")

    def delete(self, id: str) -> bool:
        query = """
        MATCH (c:Category {id: $id})
        DETACH DELETE c
        RETURN count(c) AS deleted_count
        """
        results = self._execute_write(query, {"id": id})
        return results[0].get("deleted_count", 0) > 0


class MemgraphTagRepository(BaseMemgraphRepository[Tag], ITagRepository):
    def __init__(self, tx):
        super().__init__(tx)

    def _map_dict_to_entity(self, data: Dict[str, Any], node_key: str = "t") -> Tag:
        node_props = data.get(node_key, {})
        return Tag(id=node_props.get("id"), name=node_props.get("name"))

    def get_by_name(self, name: str) -> Optional[Tag]:
        query = "MATCH (t:Tag {name: $name}) RETURN t"
        results = self._execute_read(query, {"name": name})
        if not results:
            return None
        return self._map_dict_to_entity(results[0], "t")


    def create(self, entity: Tag) -> Tag:
        query = "CREATE (t:Tag {id: $id, name: $name}) RETURN t"
        results = self._execute_write(query, {"id": entity.id, "name": entity.name})
        if not results:
            raise RuntimeError(f"Failed to create Tag: {entity.name}")
        return self._map_dict_to_entity(results[0], "t")

    def get_by_id(self, id: str) -> Optional[Tag]:
        query = "MATCH (t:Tag {id: $id}) RETURN t"
        results = self._execute_read(query, {"id": id})
        if not results:
            return None
        return self._map_dict_to_entity(results[0], "t")

    def get_all(self, skip: int = 0, limit: int = 100) -> List[Tag]:
        query = """
        MATCH (t:Tag) 
        RETURN t 
        SKIP $skip LIMIT $limit
        """
        results = self._execute_read(query, {"skip": skip, "limit": limit})
        return [self._map_dict_to_entity(record, "t") for record in results]

    def update(self, id: str, entity: Tag) -> Tag:
        query = """
        MATCH (t:Tag {id: $id})
        SET t.name = $name
        RETURN t
        """
        results = self._execute_write(query, {"id": id, "name": entity.name})
        if not results:
            raise ValueError(f"Tag with id {id} not found for update.")
        return self._map_dict_to_entity(results[0], "t")

    def delete(self, id: str) -> bool:
        query = """
        MATCH (t:Tag {id: $id})
        DETACH DELETE t
        RETURN count(t) AS deleted_count
        """
        results = self._execute_write(query, {"id": id})
        return results[0].get("deleted_count", 0) > 0