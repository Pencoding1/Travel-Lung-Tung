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


class _OperationOutcome(Exception):
    """Internal control-flow signal carrying a read-only outcome envelope.

    Raised *inside* the UnitOfWork so conflict/not-found outcomes roll the
    transaction back instead of committing, then caught outside and returned as
    the caller-facing dictionary. It never escapes this module.
    """

    def __init__(self, envelope: Dict[str, Any]):
        super().__init__("operation outcome")
        self.envelope = envelope


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
        """Standardized Create Flow.

        Validation runs before the transaction. Any write failure is allowed to
        propagate out of the ``with`` block so the UnitOfWork rolls the
        transaction back; the sanitized envelope is only built *outside* the
        transaction, so a swallowed DB error can never be committed.
        """
        # 1. Centralized Validation (no transaction opened yet)
        entity_or_error = self._safe_validate(payload, "creation")
        if isinstance(entity_or_error, dict):
            return entity_or_error  # Fast-fail: Return the error dictionary immediately

        entity = entity_or_error  # Type safely resolved to T

        # 2. Database Transaction
        try:
            with self.uow:
                entity_id = getattr(entity, 'id', None)

                if entity_id and self._get_existing(entity_id):
                    raise _OperationOutcome({
                        "is_success": False,
                        "error_type": "conflict",
                        "payload": {"message": f"Entity with ID {entity_id} already exists."}
                    })

                created_entity = self._execute_create(entity)
                envelope = {"is_success": True, "payload": created_entity.model_dump()}
        except _OperationOutcome as outcome:
            return outcome.envelope
        except Exception as e:
            logger.error("Graph transaction failed during creation (%s).", type(e).__name__)
            return {
                "is_success": False,
                "error_type": "internal_error",
                "payload": {"message": "Failed to write to the knowledge graph."}
            }

        # Reached only after a successful commit.
        return envelope

    def update(self, entity_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Standardized Update Flow (rolls back on a failed write)."""
        payload['id'] = entity_id

        # 1. Centralized Validation (no transaction opened yet)
        entity_or_error = self._safe_validate(payload, f"update for {entity_id}")
        if isinstance(entity_or_error, dict):
            return entity_or_error  # Fast-fail

        entity = entity_or_error

        # 2. Database Transaction
        try:
            with self.uow:
                if not self._get_existing(entity_id):
                    raise _OperationOutcome({
                        "is_success": False,
                        "error_type": "not_found",
                        "payload": {"message": f"Entity with ID {entity_id} not found."}
                    })

                updated_entity = self._execute_update(entity_id, entity)
                envelope = {"is_success": True, "payload": updated_entity.model_dump()}
        except _OperationOutcome as outcome:
            return outcome.envelope
        except Exception as e:
            logger.error("Graph transaction failed during update (%s).", type(e).__name__)
            return {
                "is_success": False,
                "error_type": "internal_error",
                "payload": {"message": "Failed to update entity in the knowledge graph."}
            }

        return envelope

    def delete(self, entity_id: str) -> Dict[str, Any]:
        """Standardized Delete Flow (rolls back on a failed write)."""
        # Note: Delete typically doesn't need payload validation, just the ID check
        try:
            with self.uow:
                if not self._get_existing(entity_id):
                    raise _OperationOutcome({
                        "is_success": False,
                        "error_type": "not_found",
                        "payload": {"message": f"Entity with ID {entity_id} not found."}
                    })

                self._execute_delete(entity_id)
                envelope = {
                    "is_success": True,
                    "payload": {"message": f"Entity {entity_id} successfully deleted."}
                }
        except _OperationOutcome as outcome:
            return outcome.envelope
        except Exception as e:
            logger.error("Graph transaction failed during deletion (%s).", type(e).__name__)
            return {
                "is_success": False,
                "error_type": "internal_error",
                "payload": {"message": "Failed to delete entity from the knowledge graph."}
            }

        return envelope