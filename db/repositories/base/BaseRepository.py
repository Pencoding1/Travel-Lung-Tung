from abc import ABC, abstractmethod
from typing import TypeVar, Generic, List, Optional, Any
from db.models.base.BaseEntity import BaseEntity

T = TypeVar('T', bound=BaseEntity)


class BaseRepository(ABC, Generic[T]): 
    
    @abstractmethod
    def get(self, id: str) -> Optional[T]:...

    @abstractmethod
    def list_all(self) -> List[T]:...

    @abstractmethod
    def add(self, entity: T) -> T:...

    @abstractmethod
    def update(self, id: str, data: dict) -> T:...

    @abstractmethod
    def delete(self, id: str) -> bool:...
    