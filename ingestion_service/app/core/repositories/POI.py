from typing import List, Optional

from app.db.models.Graph_Entities import POI
from app.core.interaces.repositories import IPOIRepository
from app.core.base.repository import BaseMemgraphRepository

class MemgraphPOIRepository(BaseMemgraphRepository[POI], IPOIRepository):
    
    def get_by_id(self, id: str) -> Optional[POI]:
        # Cypher Map Projection formats the return to match the Pydantic schema
        query = """
        MATCH (p:POI {id: $id})
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(c:Category)
        OPTIONAL MATCH (p)-[:HAS_TAG]->(t:Tag)
        
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
            poi_categories: collect(DISTINCT c { .id, .name, .context }),
            tag: head(collect(DISTINCT t { .id, .name }))
        } AS poi_data
        """
        records = self._execute_read(query, {"id": id})
        
        if not records or not records[0].get("poi_data"):
            return None
            
        # Pydantic automatically parses the nested dictionary into Address and ContactInfo objects
        return POI(**records[0]["poi_data"])

    def create(self, entity: POI) -> POI:
        query = """
        // 1. Merge the main POI node and flatten Value Objects into properties
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
        
        // 2. Handle Tags
        WITH p
        MERGE (t:Tag {id: $poi.tag.id})
        SET t.name = $poi.tag.name
        MERGE (p)-[:HAS_TAG]->(t)
        
        // 3. Handle Categories (Unwind list of categories)
        WITH p
        UNWIND $poi.poi_categories AS cat
        MERGE (c:Category {id: cat.id})
        SET c.name = cat.name, c.context = cat.context
        MERGE (p)-[:HAS_CATEGORY]->(c)
        
        RETURN p.id AS id
        """
        
        # Pydantic's model_dump() cleanly converts the object into a dictionary for the Neo4j driver
        self._execute_write(query, {"poi": entity.model_dump()})
        return entity

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

    # Implement other abstract methods (update, delete, etc.) following the same pattern...