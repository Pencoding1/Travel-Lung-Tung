import logging
from typing import Dict, Any, TypeVar, Generic, Optional, Protocol, Union
from pydantic import ValidationError

from abc import ABC, abstractmethod

from app.core.interfaces.repositories import AbstractUnitOfWork

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
    # ABSTRACT HOOKS
    # ---------------------------------------------------------
    
    @abstractmethod
    def _validate_payload(self, payload: Dict[str, Any]) -> T:
        pass

    @abstractmethod
    def _get_existing(self, entity_id: str) -> Optional[T]:
        pass

    @abstractmethod
    def _execute_create(self, entity: T) -> T:
        pass

    @abstractmethod
    def _execute_update(self, entity_id: str, entity: T) -> T:
        pass

    @abstractmethod
    def _execute_delete(self, entity_id: str) -> bool:
        pass

    # ---------------------------------------------------------
    # INTERNAL HELPERS (The DRY Extract)
    # ---------------------------------------------------------

    def _safe_validate(self, payload: Dict[str, Any], operation_name: str) -> Union[T, Dict[str, Any]]:
        """
        Centralized validation handler.
        Returns the instantiated Domain Model on success, or the standard error dictionary on failure.
        """
        try:
            return self._validate_payload(payload)
        except ValidationError as e:
            logger.warning(f"Validation failed during {operation_name}.")
            return {
                "is_success": False,
                "error_type": "unprocessable_entity",
                "payload": [{"field": err["loc"], "message": err["msg"]} for err in e.errors()]
            }

    # ---------------------------------------------------------
    # TEMPLATE METHODS (Public API for the Routers)
    # ---------------------------------------------------------

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Standardized Create Flow"""
        # 1. Centralized Validation
        entity_or_error = self._safe_validate(payload, "creation")
        if isinstance(entity_or_error, dict):
            return entity_or_error  # Fast-fail: Return the error dictionary immediately
            
        entity = entity_or_error # Type safely resolved to T

        # 2. Database Transaction
        with self.uow:
            try:
                entity_id = getattr(entity, 'id', None)
                
                if entity_id and self._get_existing(entity_id):
                    return {
                        "is_success": False,
                        "error_type": "conflict",
                        "payload": {"message": f"Entity with ID {entity_id} already exists."}
                    }

                created_entity = self._execute_create(entity)
                return {"is_success": True, "payload": created_entity.model_dump()}
                
            except Exception as e:
                logger.error(f"Graph transaction failed during creation: {str(e)}")
                return {
                    "is_success": False,
                    "error_type": "internal_error",
                    "payload": {"message": "Failed to write to the knowledge graph."}
                }

    def update(self, entity_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Standardized Update Flow"""
        payload['id'] = entity_id
        
        # 1. Centralized Validation
        entity_or_error = self._safe_validate(payload, f"update for {entity_id}")
        if isinstance(entity_or_error, dict):
            return entity_or_error  # Fast-fail
            
        entity = entity_or_error 

        # 2. Database Transaction
        with self.uow:
            try:
                if not self._get_existing(entity_id):
                    return {
                        "is_success": False,
                        "error_type": "not_found",
                        "payload": {"message": f"Entity with ID {entity_id} not found."}
                    }

                updated_entity = self._execute_update(entity_id, entity)
                return {"is_success": True, "payload": updated_entity.model_dump()}
                
            except Exception as e:
                logger.error(f"Graph transaction failed during update: {str(e)}")
                return {
                    "is_success": False,
                    "error_type": "internal_error",
                    "payload": {"message": "Failed to update entity in the knowledge graph."}
                }

    def delete(self, entity_id: str) -> Dict[str, Any]:
        """Standardized Delete Flow"""
        # Note: Delete typically doesn't need payload validation, just the ID check
        with self.uow:
            try:
                if not self._get_existing(entity_id):
                    return {
                        "is_success": False,
                        "error_type": "not_found",
                        "payload": {"message": f"Entity with ID {entity_id} not found."}
                    }
                    
                self._execute_delete(entity_id)
                return {
                    "is_success": True,
                    "payload": {"message": f"Entity {entity_id} successfully deleted."}
                }
                
            except Exception as e:
                logger.error(f"Graph transaction failed during deletion: {str(e)}")
                return {
                    "is_success": False,
                    "error_type": "internal_error",
                    "payload": {"message": "Failed to delete entity from the knowledge graph."}
                }