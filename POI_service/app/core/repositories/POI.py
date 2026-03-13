from typing import List, Optional

from app.db.models.Graph_Entities import POI
from app.core.interaces.repositories import IPOIRepository
from app.core.base.repository import BaseMemgraphRepository

class MemgraphPOIRepository(BaseMemgraphRepository[POI], IPOIRepository):
    
    def create(self, entity: POI) -> POI:
        query = """
        // 1. Create/Merge the core POI node and flatten Value Objects
        MERGE (p:POI {id: $poi.id})
        SET p += {
            name: $poi.name,
            longitude: $poi.longitude,
            latitude: $poi.latitude,
            operation_time: $poi.operation_time,
            rating: $poi.rating,
            menu: $poi.menu,
            
            addr_street: $poi.address.street_name,
            addr_ward: $poi.address.ward,
            addr_district: $poi.address.district,
            addr_city: $poi.address.city,
            addr_nation: $poi.address.nation,
            
            contact_phone: $poi.contact_info.phone_number,
            contact_fanpage: $poi.contact_info.fanpage,
            contact_website: $poi.contact_info.website
        }
        
        // 2. Establish Tag Relationship
        WITH p
        MERGE (t:Tag {id: $poi.tag.id})
        ON CREATE SET t.name = $poi.tag.name
        MERGE (p)-[:HAS_TAG]->(t)
        
        // 3. Establish Category Relationships
        WITH p
        UNWIND $poi.poi_categories AS cat
        MERGE (c:Category {id: cat.id})
        ON CREATE SET c.name = cat.name, c.context = cat.context
        MERGE (p)-[:HAS_CATEGORY]->(c)
        
        RETURN p.id AS id
        """
        self._execute_write(query, {"poi": entity.model_dump()})
        return entity

    # ---------------------------------------------------------
    # READ
    # ---------------------------------------------------------
    def get_by_id(self, id: str) -> Optional[POI]:
        query = """
        MATCH (p:POI {id: $id})
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(c:Category)
        OPTIONAL MATCH (p)-[:HAS_TAG]->(t:Tag)
        
        RETURN p {
            .id, .name, .longitude, .latitude, .operation_time, .rating, .menu,
            address: {street_name: p.addr_street, ward: p.addr_ward, district: p.addr_district, city: p.addr_city, nation: p.addr_nation},
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
            address: {street_name: p.addr_street, ward: p.addr_ward, district: p.addr_district, city: p.addr_city, nation: p.addr_nation},
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
        MATCH (p:POI {id: $id})
        
        // 1. Update all flattened properties
        SET p += {
            name: $poi.name,
            longitude: $poi.longitude,
            latitude: $poi.latitude,
            operation_time: $poi.operation_time,
            rating: $poi.rating,
            menu: $poi.menu,
            addr_street: $poi.address.street_name,
            addr_ward: $poi.address.ward,
            addr_district: $poi.address.district,
            addr_city: $poi.address.city,
            addr_nation: $poi.address.nation,
            contact_phone: $poi.contact_info.phone_number,
            contact_fanpage: $poi.contact_info.fanpage,
            contact_website: $poi.contact_info.website
        }
        
        // 2. Reconcile Tag: Delete old relationship, set new one
        WITH p
        OPTIONAL MATCH (p)-[old_t:HAS_TAG]->()
        DELETE old_t
        WITH p
        MERGE (t:Tag {id: $poi.tag.id})
        ON CREATE SET t.name = $poi.tag.name
        MERGE (p)-[:HAS_TAG]->(t)
        
        // 3. Reconcile Categories: Delete old relationships, set new ones
        WITH p
        OPTIONAL MATCH (p)-[old_c:HAS_CATEGORY]->()
        DELETE old_c
        WITH p
        UNWIND $poi.poi_categories AS cat
        MERGE (c:Category {id: cat.id})
        ON CREATE SET c.name = cat.name, c.context = cat.context
        MERGE (p)-[:HAS_CATEGORY]->(c)
        
        RETURN p.id AS id
        """
        self._execute_write(query, {"id": id, "poi": entity.model_dump()})
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
        # Return True if at least one node was deleted
        return result[0]["deleted_count"] > 0
        
    # Implement specific declarative behaviors defined in POIRepository interface
    def get_by_city(self, city_name: str, skip: int = 0, limit: int = 100) -> List[POI]:
        query = """
        MATCH (p:POI {addr_city: $city})
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(c:Category)
        OPTIONAL MATCH (p)-[:HAS_TAG]->(t:Tag)
        
        RETURN p {
            .id, .name, .longitude, .latitude, .operation_time, .rating, .menu,
            address: {street_name: p.addr_street, ward: p.addr_ward, district: p.addr_district, city: p.addr_city, nation: p.addr_nation},
            contact_info: {phone_number: p.contact_phone, fanpage: p.contact_fanpage, website: p.contact_website},
            poi_categories: collect(DISTINCT c { .id, .name, .context }),
            tag: head(collect(DISTINCT t { .id, .name }))
        } AS poi_data
        SKIP $skip LIMIT $limit
        """
        records = self._execute_read(query, {"city": city_name, "skip": skip, "limit": limit})
        return [POI(**record["poi_data"]) for record in records if record.get("poi_data")]
        
    def get_by_category_id(self, category_id: str) -> List[POI]:
        query = """
        // 1. Anchor on the specific Category and traverse inward to find matching POIs
        MATCH (target_c:Category {id: $category_id})<-[:HAS_CATEGORY]-(p:POI)
        
        // 2. Traverse outward from those POIs to collect ALL their categories and tags
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(all_c:Category)
        OPTIONAL MATCH (p)-[:HAS_TAG]->(t:Tag)
        
        // 3. Execute the Map Projection
        RETURN p {
            .id, .name, .longitude, .latitude, .operation_time, .rating, .menu,
            address: {
                street_name: p.addr_street, 
                ward: p.addr_ward, 
                district: p.addr_district, 
                city: p.addr_city, 
                nation: p.addr_nation
            },
            contact_info: {
                phone_number: p.contact_phone,
                fanpage: p.contact_fanpage,
                website: p.contact_website
            },
            // Group the full list of categories for the POI entity
            poi_categories: collect(DISTINCT all_c { .id, .name, .context }),
            tag: head(collect(DISTINCT t { .id, .name }))
        } AS poi_data
        """
        
        records = self._execute_read(query, {"category_id": category_id})
        
        # Parse the raw nested dictionaries back into Pydantic POI models
        return [POI(**record["poi_data"]) for record in records if record.get("poi_data")]