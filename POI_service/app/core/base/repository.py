from __future__ import annotations

from pydantic import BaseModel
from abc import ABC, abstractmethod

from typing import TYPE_CHECKING, Any, LiteralString, Type, TypeVar, Generic, List, Optional, Dict

if TYPE_CHECKING:
    # Type-only imports: these must not trigger runtime connector side effects
    # (Firebase credential lookup, Memgraph driver creation) nor require the
    # heavy third-party packages just to import the repository interfaces.
    from neo4j import Transaction
    from app.core.infrastructure.db.database.connector import FireStoreConnector

T = TypeVar('T', bound=BaseModel)

class BaseRepository(ABC, Generic[T]):
    @abstractmethod
    def get_by_id(self, id: str) -> Optional[T]:
        pass

    @abstractmethod
    def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        pass

    @abstractmethod
    def create(self, entity: T) -> T:
        pass

    @abstractmethod
    def update(self, id: str, entity: T) -> T:
        pass

    @abstractmethod
    def delete(self, id: str) -> bool:
        pass

class BaseMemgraphRepository(Generic[T]):
    def __init__(self, tx: Transaction):
        self.tx = tx

    def _execute_write(self, query: LiteralString, parameters: Optional[dict] = None) -> List[Dict[str, Any]]:
        # No session.begin_transaction() here! 
        # We just run the query on the active transaction.
        result = self.tx.run(query, parameters or {})
        return [record.data() for record in result]

    def _execute_read(self, query: LiteralString, parameters: Optional[dict] = None) -> List[Dict[str, Any]]:
        result = self.tx.run(query, parameters or {})
        return [record.data() for record in result]
        

class BaseFirebaseRepository(BaseRepository[T]):
    """
    Generic Firebase Firestore repository to handle standard CRUD operations,
    drastically reducing boilerplate database interactions in concrete entity repositories.
    """
    def __init__(self, connector: FireStoreConnector, collection_name: str, model_class: Type[T]):
        self.db = connector.db
        if self.db:
            self.collection = self.db.collection(collection_name)
        else:
            raise ConnectionRefusedError("The firebase is not properly initialized.")
        self.model_class = model_class

    def create(self, entity: T) -> T:
        # Convert Pydantic model to dictionary, handling datetime safely
        data = entity.model_dump(mode='json')
        
        # Check if the entity has an explicit 'id' attribute
        entity_id = getattr(entity, 'id', None)
        
        if entity_id:
            # Upsert using the explicit ID
            self.collection.document(entity_id).set(data)
        else:
            # Let Firestore auto-generate an ID if none exists (e.g., for some sub-documents)
            doc_ref = self.collection.document()
            data['id'] = doc_ref.id  # Sync the generated ID back to the data
            doc_ref.set(data)
            entity = self.model_class(**data) # Re-instantiate to include the generated ID
            
        return entity

    def get_by_id(self, id: str) -> Optional[T]:
        doc_ref = self.collection.document(id)
        doc:Any = doc_ref.get()
        if doc.exists:
            return self.model_class(**doc.to_dict())
        return None

    def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        # Using Firestore's native offset and limit capabilities for basic pagination
        query = self.collection.offset(skip).limit(limit)
        docs:Any = query.stream()
        
        return [self.model_class(**doc.to_dict()) for doc in docs]

    def update(self, id: str, entity: T) -> T:
        # exclude_unset=True ensures we only update fields that were explicitly modified
        data = entity.model_dump(mode='json', exclude_unset=True)
        self.collection.document(id).update(data)
        
        return entity

    def delete(self, id: str) -> bool:
        doc_ref = self.collection.document(id)
        doc: Any = doc_ref.get()
        # Firestore's delete() doesn't fail if the document doesn't exist.
        # To accurately return a boolean, we check existence first.
        if doc.get().exists:
            doc_ref.delete()
            return True
        return False