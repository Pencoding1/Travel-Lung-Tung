from typing import Optional, Type
from app.core.base.repository import BaseRepository, T

class Neo4jRepository(BaseRepository[T]):
    def __init__(self, driver, label: str, model_cls: Type[T]):
        self.driver = driver
        self.label = label
        self.model_cls = model_cls

    async def get(self, id: str) -> Optional[T]:
        query = f"MATCH (n:{self.label} {{id: $id}}) RETURN n"
        async with self.driver.session() as session:
            result = await session.run(query, id=id)
            record = await result.single()
            if record:
                node = record['n']
                # Convert Node -> Pydantic
                return self.model_cls(**dict(node))
        return None