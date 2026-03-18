from app.core.interfaces.repositories import AbstractUnitOfWork
from app.core.infrastructure.db.repositories.memgraph import (
    MemgraphPOIRepository, 
    MemgraphUserBehaviorRepository,
    MemgraphCategoryRepository,
    MemgraphTagRepository
)
from app.core.infrastructure.db.database.connector import MemgraphConnector

class MemgraphUnitOfWork(AbstractUnitOfWork):
    def __init__(self, connector: MemgraphConnector):
        # We hold the connector/driver here, but don't open sessions yet.
        self.driver = connector.driver

    def __enter__(self):
        # 1. Open the session
        self.session = self.driver.session()
        
        # 2. START THE TRANSACTION BOUNDARY
        self.tx = self.session.begin_transaction()
        
        # 3. Inject the active transaction into the repositories
        self.pois = MemgraphPOIRepository(self.tx)
        self.users = MemgraphUserBehaviorRepository(self.tx)
        self.categories = MemgraphCategoryRepository(self.tx)
        self.tags = MemgraphTagRepository(self.tx)

        return super().__enter__()

    def __exit__(self, exc_type, exc_val, traceback):
        # The base __exit__ calls commit() if no exc_type, else rollback()
        super().__exit__(exc_type, exc_val, traceback)
        
        # Clean up resources safely
        if not self.tx.closed():
            self.tx.close()
        self.session.close()

    def commit(self):
        self.tx.commit()

    def rollback(self):
        self.tx.rollback()