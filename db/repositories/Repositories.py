from db.repositories.base.BaseRepository import BaseRepository, T
from typing import List, Optional, Type
from google.cloud.firestore import AsyncClient


class FireStoreRepository(BaseRepository[T]):
    """
    __description__:
        Firestore Repository for handle basic CRUD operation
    __args__:
        collection_name: the name existing collection on firestore
        model_cls: the data model from db/models. For example: Trip()
    """
    def __init__(self, collection_name: str, model_cls: Type[T]):
        self.db = AsyncClient()
        self.collection = self.db.collection(collection_name)
        self.model_cls = model_cls

    async def get(self, id: str) -> Optional[T]:
        doc = await self.collection.document(id).get()
        if doc.exists:
            data = doc.to_dict()
            if data:
                data['id'] = doc.id  # Inject ID if using BaseEntity approach
                return self.model_cls(**data)
        return None
    
    async def add(self, entity: T) -> T:
        data = entity.model_dump(by_alias=True)
        await self.collection.document(entity.id).set(data)
        return entity

    async def list_all(self) -> List[T]:
        docs = self.collection.stream()
        results = []

        async for doc in docs:
            data = doc.to_dict()
            if data is not None:
                data['id'] = doc.id
                results.append(self.model_cls(**data))

        return results

    async def update(self, id: str, data: dict) -> T:
        await self.collection.document(id).update(data)
        
        result = await self.get(id)
        if result is None:
            raise ValueError(f"Document {id} not found after update")
            
        return result

    async def delete(self, id: str) -> bool:
        await self.collection.document(id).delete()
        return True
    

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
    
    # NOTE: Thêm nữa nếu cần. Ví dụ như các thao tác thêm nhánh, constaint,...