from typing import TYPE_CHECKING

from app.core.interfaces.repositories import AbstractUnitOfWork
from app.core.infrastructure.db.repositories.memgraph import (
    MemgraphPOIRepository, 
    MemgraphUserBehaviorRepository,
    MemgraphCategoryRepository,
    MemgraphTagRepository
)
if TYPE_CHECKING:
    # Type-only import: the actual UoW only reads ``connector.driver``. Keeping
    # the connector import out of runtime avoids loading app config/credentials
    # (``connector`` instantiates a config-bearing MemgraphConnector at import).
    from app.core.infrastructure.db.database.connector import MemgraphConnector
import logging

logger = logging.getLogger(__name__)

class MemgraphUnitOfWork(AbstractUnitOfWork):
    def __init__(self, connector: "MemgraphConnector"):
        self.connector = connector
        self.session = None
        self.tx = None
        self._entered = False
        self._exited = False

    def __enter__(self):
        if self._entered:
            # Re-entering the same UnitOfWork would reuse a possibly broken
            # transaction; the caller must build a fresh one via the factory.
            raise RuntimeError("This UnitOfWork has already been entered.")

        # 1. Late Binding & Safety Check
        if not self.connector.driver:
            logger.critical("Attempted to start a transaction, but Memgraph driver is offline.")
            raise RuntimeError("Database connection is not initialized.")

        # 2. Open the session
        self.session = self.connector.driver.session()

        # 3. Start the Transaction Boundary. If the transaction cannot be
        #    started the session must not leak.
        try:
            self.tx = self.session.begin_transaction()
        except Exception:
            self._close_session_safely()
            self.session = None
            raise

        # 4. Inject the active transaction into the repositories. ``cats`` and
        #    ``categories`` are the SAME instance so every caller shares one tx.
        self.pois = MemgraphPOIRepository(self.tx)
        self.users = MemgraphUserBehaviorRepository(self.tx)
        self.categories = MemgraphCategoryRepository(self.tx)
        self.cats = self.categories
        self.tags = MemgraphTagRepository(self.tx)

        self._entered = True
        return super().__enter__()

    def __exit__(self, exc_type, exc_val, traceback):
        if self._exited:
            # Repeated exit is a safe no-op; resources were already released.
            return False
        self._exited = True

        try:
            if exc_type is None:
                # Success path: a commit failure must surface to the caller.
                self.commit()
            else:
                # Error path: a rollback failure must never hide the original
                # exception that triggered the rollback.
                try:
                    self.rollback()
                except Exception as rollback_error:
                    logger.error(
                        "Rollback failed while propagating %s (%s).",
                        getattr(exc_type, "__name__", "error"),
                        type(rollback_error).__name__,
                    )
        finally:
            self._close_tx_safely()
            self._close_session_safely()
            self.tx = None
            self.session = None

        return False

    # ---------------------------------------------------------
    # SANITIZED CLEANUP HELPERS
    # ---------------------------------------------------------
    def _close_tx_safely(self) -> None:
        tx = self.tx
        if tx is None:
            return
        try:
            if not tx.closed():
                tx.close()
        except Exception as exc:
            logger.warning("Error closing transaction (%s).", type(exc).__name__)

    def _close_session_safely(self) -> None:
        session = self.session
        if session is None:
            return
        try:
            session.close()
        except Exception as exc:
            logger.warning("Error closing session (%s).", type(exc).__name__)

    def commit(self):
        self.tx.commit()

    def rollback(self):
        self.tx.rollback()