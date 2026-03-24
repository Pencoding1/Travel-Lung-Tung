from typing import Callable

from fastapi import Depends

from app.core.infrastructure.db.database.connector import MemgraphConnector, get_memgraph_connector
from app.core.interfaces.repositories import IDocumentRepository
from app.core.infrastructure.db.uow import MemgraphUnitOfWork
from app.core.services.management import POIManagementService
from app.core.services.ingestion import POIIngestionService

from travel_shared.exceptions import IntentedNotImplementedException

class PendingDocumentRepository(IDocumentRepository):
    def get_poi_documents(self, poi_id: str) -> dict:
        # 2. Raise the exception ONLY when the method is actually called
        # by the POIManagementService, inside its safe try/except block.
        raise IntentedNotImplementedException(
            "The Document Repository isn't implemented yet. Further development for RAG database is required."
        )


# 1. Provide the Concrete UoW
def get_unit_of_work(connector: MemgraphConnector=Depends(get_memgraph_connector)):
    """
    Instantiates the MemgraphUnitOfWork. 
    Notice how it returns the concrete class, which perfectly satisfies 
    the AbstractUnitOfWork interface expected by the service.
    """
    return MemgraphUnitOfWork(connector)

# 2. Provide the Concrete Service
def get_poi_management_service(uow: MemgraphUnitOfWork = Depends(get_unit_of_work)):
    """
    Injects the Memgraph UoW into the POIManagementService.
    """
    return POIManagementService(uow)

def get_poi_ingestion_service(connector: MemgraphConnector = Depends(get_memgraph_connector)):    
    """Injects the UoW into the Ingestion Service."""
    uow_factory: Callable[[], MemgraphUnitOfWork] = lambda: MemgraphUnitOfWork(connector)
    
    # Pass it to the parameter name defined in your POIIngestionService.__init__
    return POIIngestionService(uow_factory=uow_factory)

# Dummy class and require implement
def get_document_repository() -> IDocumentRepository:
    return PendingDocumentRepository()