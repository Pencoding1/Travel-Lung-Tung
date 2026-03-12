from pydantic import BaseModel
from abc import ABC, abstractmethod

from typing import LiteralString, TypeVar, Generic, List, Optional

from app.db.database.connector import MemgraphConnector

T = TypeVar('T', bound=BaseModel)

class BaseRepository(Generic[T], ABC):
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

class BaseMemgraphRepository(BaseRepository[T]):
    def __init__(self, connector: MemgraphConnector):
        self.driver = connector.driver

    def _execute_read(self, query: LiteralString, parameters: Optional[dict] = None) -> List[dict]:
        """Helper to execute read transactions and return raw dictionaries."""
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def _execute_write(self, query: LiteralString, parameters: Optional[dict]  = None) -> List[dict]:
        """Helper to execute write transactions."""
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]