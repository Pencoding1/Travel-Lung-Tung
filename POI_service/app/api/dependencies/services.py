from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from fastapi import Depends

from app.core.interfaces.repositories import IDocumentRepository
from app.core.services.ingestion import POIIngestionService

from travel_shared.exceptions import IntentedNotImplementedException

if TYPE_CHECKING:
    from app.core.infrastructure.db.database.connector import MemgraphConnector
    from app.core.infrastructure.db.uow import MemgraphUnitOfWork


def get_memgraph_connector() -> "MemgraphConnector":
    """Lazy accessor for the Memgraph connector singleton.

    Imported inside the function so that importing this dependency module does
    not pull in the concrete database connector, its pydantic settings reader
    (which requires ``MEMGRAPH_*`` environment variables) or Firebase/neo4j.
    """
    from app.core.infrastructure.db.database.connector import (
        get_memgraph_connector as _get_memgraph_connector,
    )

    return _get_memgraph_connector()


class PendingDocumentRepository(IDocumentRepository):
    def get_poi_documents(self, poi_id: str) -> dict:
        # Raise the exception ONLY when the method is actually called
        # by the POIManagementService, inside its safe try/except block.
        raise IntentedNotImplementedException(
            "The Document Repository isn't implemented yet. Further development for RAG database is required."
        )


# 1. Provide the Concrete UoW
def get_unit_of_work(
    connector: "MemgraphConnector" = Depends(get_memgraph_connector),
) -> "MemgraphUnitOfWork":
    """
    Instantiates the MemgraphUnitOfWork.
    Notice how it returns the concrete class, which perfectly satisfies
    the AbstractUnitOfWork interface expected by the service.
    """
    from app.core.infrastructure.db.uow import MemgraphUnitOfWork

    return MemgraphUnitOfWork(connector)


# 2. Provide the Concrete Service
def get_poi_management_service(
    uow: "MemgraphUnitOfWork" = Depends(get_unit_of_work),
):
    """
    Injects the Memgraph UoW into the POIManagementService.
    """
    from app.core.services.management import POIManagementService

    return POIManagementService(uow)


def get_poi_ingestion_service(
    connector: "MemgraphConnector" = Depends(get_memgraph_connector),
):
    """Injects the UoW factory into the Ingestion Service."""
    from app.core.infrastructure.db.uow import MemgraphUnitOfWork

    uow_factory: Callable[[], "MemgraphUnitOfWork"] = (
        lambda: MemgraphUnitOfWork(connector)
    )

    # Pass it to the parameter name defined in POIIngestionService.__init__
    return POIIngestionService(uow_factory=uow_factory)


# Dummy class and require implement
def get_document_repository() -> IDocumentRepository:
    return PendingDocumentRepository()
