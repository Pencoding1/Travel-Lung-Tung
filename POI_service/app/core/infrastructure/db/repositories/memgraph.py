from neo4j import Transaction
from typing import List, LiteralString, Optional, cast, Dict, Any

from app.core.base.repository import BaseMemgraphRepository

from app.core.domain.graph_entities import POI, UserPreference, Category, Tag

from app.core.interfaces.repositories import IPOIRepository
from app.core.interfaces.repositories import IUserBehaviorRepository
from shared_lib.travel_shared.exceptions import IntentedNotImplementedException
from app.core.interfaces.repositories import ICategoryRepository, ITagRepository



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
            "WHERE p.addr_city = $city"
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
    def create(self, entity: UserPreference) -> UserPreference:
        """
        Takes the full Pydantic UserPreference object and syncs it into Memgraph.
        This handles drawing all multiple PREFERS edges in a single transaction.
        """
        query = """
        // 1. Create or Update the User Shadow Node and its hard constraints
        MERGE (u:User {id: $user.user_id})
        SET u.budget_level = $user.budget_level,
            u.travel_pace = $user.travel_pace,
            u.requires_accessibility = $user.requires_accessibility
            
        // 2. Clear old preferences to ensure a clean sync with Firebase
        WITH u
        OPTIONAL MATCH (u)-[old_pref:PREFERS]->()
        DELETE old_pref
        
        // 3. Re-draw Category preference edges
        WITH u
        UNWIND $category_list AS cat
        MATCH (c:Category {id: cat.id})
        MERGE (u)-[rc:PREFERS]->(c)
        SET rc.weight = cat.weight
        
        // 4. Re-draw Tag preference edges
        WITH u
        UNWIND $tag_list AS tag
        MATCH (t:Tag {id: tag.id})
        MERGE (u)-[rt:PREFERS]->(t)
        SET rt.weight = tag.weight
        """
        
        cat_list = [{"id": k, "weight": v} for k, v in entity.category_weights.items()]
        tag_list = [{"id": k, "weight": v} for k, v in entity.tag_weights.items()]
        
        self._execute_write(query, {
            "user": entity.model_dump(mode='json'),
            "category_list": cat_list,
            "tag_list": tag_list
        })
        return entity

    def update(self, id: str, entity: UserPreference) -> UserPreference:
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
    def batch_create(self, poi_batch: list[dict]) -> int:
        query = """
        UNWIND $batch AS poi

        // 1. Flatten Address: Filter out nulls/empty strings and join with commas
        WITH poi, [
            poi.address.street_name, 
            poi.address.ward, 
            poi.address.district, 
            poi.address.city, 
            poi.address.nation
        ] AS addr_parts
        WITH poi, [part IN addr_parts WHERE part IS NOT NULL AND part <> ""] AS valid_parts
        WITH poi, reduce(s = head(valid_parts), x IN tail(valid_parts) | s + ", " + x) AS full_addr

        // 2. Defensively Merge Core POI
        MERGE (p:POI {id: poi.id})
        SET p += {
            name: poi.name,
            longitude: poi.longitude,
            latitude: poi.latitude,
            operation_time: poi.operation_time,
            full_address: full_addr,
            contact_phone: poi.contact_info.phone_number,
            contact_website: poi.contact_info.website
        }

        // 3. Generate Deterministic Spatial IDs (Lowercased and Trimmed)
        WITH p, poi, full_addr,
             toLower(trim(poi.address.nation)) AS n_id,
             toLower(trim(poi.address.city)) + "_" + toLower(trim(poi.address.nation)) AS c_id,
             toLower(trim(poi.address.district)) + "_" + toLower(trim(poi.address.city)) AS d_id,
             toLower(trim(poi.address.street_name)) + "_" + toLower(trim(poi.address.district)) AS s_id

        // 4. Establish Spatial Hierarchy using the Strict IDs
        MERGE (n:Nation {id: n_id})
        ON CREATE SET n.name = trim(poi.address.nation)

        MERGE (c:City {id: c_id})
        ON CREATE SET c.name = trim(poi.address.city), c.nation = trim(poi.address.nation)
        MERGE (c)-[:IN_NATION]->(n)

        MERGE (d:District {id: d_id})
        ON CREATE SET d.name = trim(poi.address.district), d.city = trim(poi.address.city)
        MERGE (d)-[:IN_CITY]->(c)

        // 5. Conditional LOCATE_AT Fallback using Strict IDs
        CALL {
            WITH p, poi, d, s_id
            WITH p, poi, d, s_id WHERE poi.address.street_name IS NOT NULL AND trim(poi.address.street_name) <> ""
            MERGE (s:Street {id: s_id})
            ON CREATE SET s.name = trim(poi.address.street_name), s.district = trim(poi.address.district)
            MERGE (s)-[:IN_DISTRICT]->(d)
            MERGE (p)-[:LOCATE_AT]->(s)
        }
        CALL {
            WITH p, poi, d
            WITH p, poi, d WHERE poi.address.street_name IS NULL OR trim(poi.address.street_name) = ""
            MERGE (p)-[:LOCATE_AT]->(d)
        }

        // 5. Tags (Using FOREACH as a null-safe conditional)
        FOREACH (ignoreMe IN CASE WHEN poi.tag IS NOT NULL THEN [1] ELSE [] END |
            MERGE (t:Tag {name: poi.tag.name}) // Merge on Name to avoid duplicates
            ON CREATE SET t.id = poi.tag.id
            MERGE (p)-[:HAS_TAG]->(t)
        )

        // 6. Categories (FOREACH handles the list naturally without UNWINDing)
        FOREACH (cat IN poi.poi_categories |
            MERGE (catNode:Category {name: cat.name}) // Merge on Name to avoid duplicates
            ON CREATE SET catNode.id = cat.id, catNode.context = cat.context
            MERGE (p)-[:HAS_CATEGORY]->(catNode)
        )
        """
        # Ensure we use the active transaction from the UoW
        self._execute_write(query, {"batch": poi_batch})
        return len(poi_batch)

    # ---------------------------------------------------------
    # SINGLE CREATE
    # ---------------------------------------------------------
    def create(self, entity: POI) -> POI:
        query = """
        WITH $poi AS poi, [
            $poi.address.street_name, 
            $poi.address.ward, 
            $poi.address.district, 
            $poi.address.city, 
            $poi.address.nation
        ] AS addr_parts
        WITH poi, [part IN addr_parts WHERE part IS NOT NULL AND part <> ""] AS valid_parts
        WITH poi, reduce(s = head(valid_parts), x IN tail(valid_parts) | s + ", " + x) AS full_addr

        // 1. Create the core POI node
        MERGE (p:POI {id: poi.id})
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
            contact_website: poi.contact_info.website
        }

        // 2. Establish Spatial Hierarchy
        MERGE (n:Nation {name: poi.address.nation})
        MERGE (c:City {name: poi.address.city, nation: poi.address.nation})
        MERGE (c)-[:IN_NATION]->(n)
        MERGE (d:District {name: poi.address.district, city: poi.address.city})
        MERGE (d)-[:IN_CITY]->(c)

        // 3. Generate Deterministic Spatial IDs (Lowercased and Trimmed)
        WITH p, poi, full_addr,
             toLower(trim(poi.address.nation)) AS n_id,
             toLower(trim(poi.address.city)) + "_" + toLower(trim(poi.address.nation)) AS c_id,
             toLower(trim(poi.address.district)) + "_" + toLower(trim(poi.address.city)) AS d_id,
             toLower(trim(poi.address.street_name)) + "_" + toLower(trim(poi.address.district)) AS s_id

        // 4. Establish Spatial Hierarchy using the Strict IDs
        MERGE (n:Nation {id: n_id})
        ON CREATE SET n.name = trim(poi.address.nation)

        MERGE (c:City {id: c_id})
        ON CREATE SET c.name = trim(poi.address.city), c.nation = trim(poi.address.nation)
        MERGE (c)-[:IN_NATION]->(n)

        MERGE (d:District {id: d_id})
        ON CREATE SET d.name = trim(poi.address.district), d.city = trim(poi.address.city)
        MERGE (d)-[:IN_CITY]->(c)

        // 5. Conditional LOCATE_AT Fallback using Strict IDs
        CALL {
            WITH p, poi, d, s_id
            WITH p, poi, d, s_id WHERE poi.address.street_name IS NOT NULL AND trim(poi.address.street_name) <> ""
            MERGE (s:Street {id: s_id})
            ON CREATE SET s.name = trim(poi.address.street_name), s.district = trim(poi.address.district)
            MERGE (s)-[:IN_DISTRICT]->(d)
            MERGE (p)-[:LOCATE_AT]->(s)
        }
        CALL {
            WITH p, poi, d
            WITH p, poi, d WHERE poi.address.street_name IS NULL OR trim(poi.address.street_name) = ""
            MERGE (p)-[:LOCATE_AT]->(d)
        }
        
        // 4. Establish Tag Relationship
        WITH p, poi
        FOREACH (ignoreMe IN CASE WHEN poi.tag IS NOT NULL THEN [1] ELSE [] END |
            MERGE (t:Tag {id: poi.tag.id})
            ON CREATE SET t.name = poi.tag.name
            MERGE (p)-[:HAS_TAG]->(t)
        )

        // 5. Establish Category Relationships
        WITH p, poi
        UNWIND poi.poi_categories AS cat
        MERGE (catNode:Category {id: cat.id})
        ON CREATE SET catNode.name = cat.name, catNode.context = cat.context
        MERGE (p)-[:HAS_CATEGORY]->(catNode)

        RETURN p.id AS id
        """
        self._execute_write(query, {"poi": entity.model_dump(mode='json')})
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
        WITH $poi AS poi, [
            $poi.address.street_name, 
            $poi.address.ward, 
            $poi.address.district, 
            $poi.address.city, 
            $poi.address.nation
        ] AS addr_parts
        WITH poi, [part IN addr_parts WHERE part IS NOT NULL AND part <> ""] AS valid_parts
        WITH poi, reduce(s = head(valid_parts), x IN tail(valid_parts) | s + ", " + x) AS full_addr

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
            contact_website: poi.contact_info.website
        }

        // 2. Reconcile Spatial Information: Sever old connection
        WITH p, poi
        OPTIONAL MATCH (p)-[old_loc:LOCATE_AT]->()
        DELETE old_loc

        // 3. Rebuild Spatial Hierarchy
        WITH p, poi
        MERGE (n:Nation {name: poi.address.nation})
        MERGE (c:City {name: poi.address.city, nation: poi.address.nation})
        MERGE (c)-[:IN_NATION]->(n)
        MERGE (d:District {name: poi.address.district, city: poi.address.city})
        MERGE (d)-[:IN_CITY]->(c)

        // 4. Conditional LOCATE_AT Fallback
        CALL {
            WITH p, poi, d
            WITH p, poi, d WHERE poi.address.street_name IS NOT NULL AND poi.address.street_name <> ""
            MERGE (s:Street {name: poi.address.street_name, district: poi.address.district})
            MERGE (s)-[:IN_DISTRICT]->(d)
            MERGE (p)-[:LOCATE_AT]->(s)
        }
        CALL {
            WITH p, poi, d
            WITH p, poi, d WHERE poi.address.street_name IS NULL OR poi.address.street_name = ""
            MERGE (p)-[:LOCATE_AT]->(d)
        }

        // 5. Reconcile Tag
        WITH p, poi
        OPTIONAL MATCH (p)-[old_t:HAS_TAG]->()
        DELETE old_t
        WITH p, poi
        FOREACH (ignoreMe IN CASE WHEN poi.tag IS NOT NULL THEN [1] ELSE [] END |
            MERGE (t:Tag {id: poi.tag.id})
            ON CREATE SET t.name = poi.tag.name
            MERGE (p)-[:HAS_TAG]->(t)
        )

        // 6. Reconcile Categories
        WITH p, poi
        OPTIONAL MATCH (p)-[old_c:HAS_CATEGORY]->()
        DELETE old_c
        WITH p, poi
        UNWIND poi.poi_categories AS cat
        MERGE (catNode:Category {id: cat.id})
        ON CREATE SET catNode.name = cat.name, catNode.context = cat.context
        MERGE (p)-[:HAS_CATEGORY]->(catNode)

        RETURN p.id AS id
        """
        # Safely dump complex types using mode='json'
        self._execute_write(query, {"id": id, "poi": entity.model_dump(mode='json')})
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
        Executes a fast spatial heuristic in Memgraph.
        1 degree of latitude/longitude is roughly 111 kilometers.
        We use the Pythagorean theorem on coordinates for a highly performant 2D distance calculation.
        """
        query = """
        // 1. Anchor on the target POI
        MATCH (p:POI {id: $id})
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(c:Category)
        
        // Use head(collect()) to prevent Cartesian explosion
        WITH p, head(collect(c)) AS primary_category 
        
        // 2. Safe Optional Match for Nearby
        OPTIONAL MATCH (nearby:POI)
        WHERE nearby.id <> p.id
          AND nearby.latitude IS NOT NULL 
          AND nearby.longitude IS NOT NULL
          AND abs(nearby.latitude - p.latitude) <= ($radius_km / 111.0)
          AND abs(nearby.longitude - p.longitude) <= ($radius_km / 111.0)
          
        // 3. Calculate distance, filter, AND order in a single, continuous WITH block
        WITH p, primary_category, nearby,
             sqrt( (p.latitude - nearby.latitude)^2 + (p.longitude - nearby.longitude)^2 ) * 111.0 AS dist_km
        WHERE nearby IS NULL OR dist_km <= $radius_km
        ORDER BY dist_km ASC
        
        // 4. Collect safely
        WITH p, primary_category, collect(
            CASE WHEN nearby IS NOT NULL THEN {
                POI_ID: nearby.id,
                POI_Name: nearby.name,
                POI_Address: nearby.full_address,
                POI_Category: head([(nearby)-[:HAS_CATEGORY]->(nc:Category) | nc.name]),
                distance: round(dist_km * 100) / 100.0
            } ELSE null END
        )[0..$limit] AS nearby_list
        
        // 5. Return the mapped dictionary
        RETURN {
            POI_ID: p.id,
            POI_Name: p.name,
            POI_Address: p.full_address,
            POI_Category: CASE WHEN primary_category IS NOT NULL THEN primary_category.name ELSE "Uncategorized" END,
            POI_Contact_Info: {
                website: p.contact_website,
                fanpage: p.contact_fanpage,
                phonenumber: p.contact_phone
            },
            NEAR_BY: [n IN nearby_list WHERE n IS NOT NULL]
        } AS graph_result
        """
        
        records = self._execute_read(query, {
            "id": id, 
            "radius_km": radius_km, 
            "limit": limit
        })
        
        if not records or not records[0].get("graph_result"):
            return None
            
        return records[0]["graph_result"]


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
        query = "CREATE (c:Category {id: $id, name: $name}) RETURN c"
        results = self._execute_write(query, {"id": entity.id, "name": entity.name})
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
        SET c.name = $name
        RETURN c
        """
        # We use 'id' from the parameter to find the node, and update properties from the 'entity'
        results = self._execute_write(query, {"id": id, "name": entity.name})
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