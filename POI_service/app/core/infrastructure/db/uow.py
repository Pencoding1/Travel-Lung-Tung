from app.core.interfaces.repositories import AbstractUnitOfWork
from app.core.infrastructure.db.repositories.memgraph import (
    MemgraphPOIRepository, 
    MemgraphUserBehaviorRepository,
    MemgraphCategoryRepository,
    MemgraphTagRepository
)
from app.core.infrastructure.db.database.connector import MemgraphConnector
import logging

logger = logging.getLogger(__name__)

class MemgraphUnitOfWork(AbstractUnitOfWork):
    def __init__(self, connector: MemgraphConnector):
        self.connector = connector

    def __enter__(self):
        # 1. Late Binding & Safety Check
        if not self.connector.driver:
            logger.critical("Attempted to start a transaction, but Memgraph driver is offline.")
            raise RuntimeError("Database connection is not initialized.")

        # 2. Open the session
        self.session = self.connector.driver.session()
        
        # 3. Start the Transaction Boundary
        self.tx = self.session.begin_transaction()
        
        # 4. Inject the active transaction into the repositories
        self.pois = MemgraphPOIRepository(self.tx)
        self.users = MemgraphUserBehaviorRepository(self.tx)
        self.categories = MemgraphCategoryRepository(self.tx)
        self.tags = MemgraphTagRepository(self.tx)

        return super().__enter__()

    def __exit__(self, exc_type, exc_val, traceback):
        # Let the Abstract Base Class decide whether to commit or rollback
        super().__exit__(exc_type, exc_val, traceback)
        
        # Safely clean up Neo4j/Memgraph resources
        try:
            if hasattr(self, 'tx') and not self.tx.closed():
                self.tx.close()
        except Exception as e:
            logger.warning(f"Error closing transaction: {str(e)}")
            
        try:
            if hasattr(self, 'session'):
                self.session.close()
        except Exception as e:
            logger.warning(f"Error closing session: {str(e)}")

    def commit(self):
        self.tx.commit()

    def rollback(self):
        self.tx.rollback()