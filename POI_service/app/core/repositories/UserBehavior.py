from typing import List, LiteralString, Optional, cast

from app.db.models.Graph_Entities import POI, UserPreference
from app.db.database.connector import MemgraphConnector
from app.core.base.repository import BaseMemgraphRepository
from app.core.interaces.repositories import IUserBehaviorRepository

class MemgraphUserBehaviorRepository(BaseMemgraphRepository[UserPreference], IUserBehaviorRepository):
    def __init__(self, connector: MemgraphConnector):
        super().__init__(connector)

    # ---------------------------------------------------------
    # STAGE 1 ROUTING ENGINE: CYPHER CLUSTERING
    # ---------------------------------------------------------
    def get_preferred_pois(self, user_id: str, city: str, province: Optional[str] = None, street: Optional[str] = None, limit: int = 10) -> List[POI]:
        """
        Traverses the graph to find POIs that match the user's PREFERS edges,
        enforcing a strict hierarchical location query (City -> Province -> Street).
        """
        city = city.strip() if city else ""
        province = province.strip() if province else None
        street = street.strip() if street else None

        if not city:
            raise ValueError("Hierarchical location query failed: 'city' is required as the base level.")
            
        if street and not province:
            raise ValueError("Hierarchical location query failed: 'province' must be provided if 'street' is queried.")
            
        if province and not city:
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
        if province:
            query_lines.append("  AND p.addr_district = $province")
            params["province"] = province
        
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
        raise NotImplementedError("Retrieve full UserPreference via the Firebase repository.")

    def get_all(self, skip: int = 0, limit: int = 100) -> List[UserPreference]:
        raise NotImplementedError("Retrieve all UserPreferences via the Firebase repository.")