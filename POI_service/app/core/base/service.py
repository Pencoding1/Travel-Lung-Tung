import logging
from typing import Dict, Any, TypeVar, Generic, Optional, Protocol
from abc import ABC, abstractmethod

from app.core.interfaces.repositories import AbstractUnitOfWork
from app.core.exceptions import DomainValidationException, ResourceNotFoundException

logger = logging.getLogger(__name__)

class IdentifiableDomainModel(Protocol):
    @property
    def id(self) -> Optional[str]: ...
    def model_dump(self) -> Dict[str, Any]: ...

T = TypeVar('T', bound=IdentifiableDomainModel)


class BaseManagementService(ABC, Generic[T]):
    """
    Abstract Base Class for Command Handlers.
    Enforces the Sequence Flow: Validate -> UoW -> Check -> Execute
    """
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    # ---------------------------------------------------------
    # ABSTRACT HOOKS (To be implemented by subclasses)
    # ---------------------------------------------------------

    @abstractmethod
    def _validate_payload(self, payload: Dict[str, Any]) -> T:
        """Validates the raw dictionary and returns a Pydantic Domain Model."""
        pass

    @abstractmethod
    def _get_existing(self, entity_id: str) -> Optional[T]:
        """Fetches the entity using the appropriate repository (for existence checks)."""
        pass

    @abstractmethod
    def _execute_create(self, entity: T) -> T:
        """Executes the repository create operation."""
        pass

    @abstractmethod
    def _execute_update(self, entity_id: str, entity: T) -> T:
        """Executes the repository update operation."""
        pass

    @abstractmethod
    def _execute_delete(self, entity_id: str) -> bool:
        """Executes the repository delete operation."""
        pass

    # ---------------------------------------------------------
    # TEMPLATE METHODS (Public API for the Routers)
    # ---------------------------------------------------------

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Standardized Create Flow"""
        try:
            entity = self._validate_payload(payload)
        except ValueError as e:
            logger.error(f"Validation failed during creation: {str(e)}")
            raise DomainValidationException(f"Invalid data: {str(e)}")

        with self.uow:
            try:
                entity_id = entity.id 
                
                if entity_id is not None and self._get_existing(entity_id):
                    raise DomainValidationException(f"Entity with ID {entity_id} already exists.")

                created_entity = self._execute_create(entity)
                return created_entity.model_dump()
                
            except DomainValidationException:
                raise 
            except Exception as e:
                logger.error(f"Graph transaction failed during creation: {str(e)}")
                raise DomainValidationException(f"Failed to persist entity: {str(e)}")

    def update(self, entity_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Standardized Update Flow"""
        payload['id'] = entity_id
        
        try:
            entity = self._validate_payload(payload)
        except ValueError as e:
            logger.error(f"Validation failed during update: {str(e)}")
            raise DomainValidationException(f"Invalid update data: {str(e)}")

        with self.uow:
            try:
                # 1. Strict Existence Check
                if not self._get_existing(entity_id):
                    raise ResourceNotFoundException(f"Entity with ID {entity_id} not found.")

                # 2. Execute
                updated_entity = self._execute_update(entity_id, entity)
                return updated_entity.model_dump()
                
            except ResourceNotFoundException:
                raise
            except Exception as e:
                logger.error(f"Graph transaction failed during update: {str(e)}")
                raise DomainValidationException(f"Failed to update entity: {str(e)}")

    def delete(self, entity_id: str) -> bool:
        """Standardized Delete Flow"""
        with self.uow:
            try:
                # 1. Strict Existence Check
                if not self._get_existing(entity_id):
                    raise ResourceNotFoundException(f"Entity with ID {entity_id} not found.")
                    
                # 2. Execute
                success = self._execute_delete(entity_id)
                return success
                
            except ResourceNotFoundException:
                raise
            except Exception as e:
                logger.error(f"Graph transaction failed during deletion: {str(e)}")
                raise DomainValidationException(f"Failed to delete entity: {str(e)}")