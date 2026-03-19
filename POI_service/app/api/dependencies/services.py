from fastapi import Depends
from app.core.infrastructure.db.database.connector import MemgraphConnector, get_memgraph_connector
from app.core.infrastructure.db.uow import MemgraphUnitOfWork
from app.core.services.management import POIManagementService
from app.core.services.ingestion import POIIngestionService

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

def get_poi_ingestion_service(uow: MemgraphUnitOfWork = Depends(get_unit_of_work)):
    """Injects the UoW into the Ingestion Service."""
    return POIIngestionService(uow)