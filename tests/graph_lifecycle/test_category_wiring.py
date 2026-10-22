"""Category wiring is proven through the REAL UnitOfWork, not a fake ``.cats``.

The source audit for OC-014 found two independent problems: the concrete
UnitOfWork exposed ``categories`` while the services used ``cats``, and the
existing tests injected ``FakeUnitOfWork.cats`` which hid the mismatch. These
tests drive ``CategoryManagementService`` through ``MemgraphUnitOfWork`` backed
by a captured (fake) transaction, so the wiring itself is under test.
"""

from app.core.infrastructure.db.repositories.memgraph import MemgraphCategoryRepository
from app.core.infrastructure.db.uow import MemgraphUnitOfWork
from app.core.interfaces.repositories import AbstractUnitOfWork
from app.core.services.management import CategoryManagementService
from graph_fakes import FakeConnector, RecordingDriver, RecordingSession, RecordingTransaction


def _real_uow(responses=None):
    tx = RecordingTransaction(responses)
    session = RecordingSession(tx)
    driver = RecordingDriver(session)
    return MemgraphUnitOfWork(FakeConnector(driver)), tx, session


def test_abstract_unit_of_work_declares_cats_and_categories():
    assert "cats" in AbstractUnitOfWork.__annotations__
    assert "categories" in AbstractUnitOfWork.__annotations__


def test_cats_and_categories_are_the_same_instance():
    uow, _tx, _session = _real_uow()
    with uow:
        assert isinstance(uow.cats, MemgraphCategoryRepository)
        assert uow.cats is uow.categories


def test_category_service_create_through_real_uow():
    # call 0: get_by_id (no existing), call 1: CREATE returns the node.
    uow, tx, _session = _real_uow(
        [
            [],
            [{"c": {"id": "cat_a", "name": "Coffee", "context": "warm vibe"}}],
        ]
    )
    service = CategoryManagementService(uow)

    outcome = service.create({"id": "cat_a", "name": "Coffee", "context": "warm vibe"})

    assert outcome["is_success"] is True
    assert outcome["payload"]["context"] == "warm vibe"
    # The real repository issued the CREATE on the real transaction.
    assert "CREATE (c:Category" in tx.calls[1]["query"]
    assert tx.commit_calls == 1


def test_category_service_update_through_real_uow():
    existing = {"c": {"id": "cat_a", "name": "Coffee", "context": "old"}}
    updated = {"c": {"id": "cat_a", "name": "Coffee", "context": "new"}}
    uow, tx, _session = _real_uow([[existing], [updated]])
    service = CategoryManagementService(uow)

    outcome = service.update("cat_a", {"name": "Coffee", "context": "new"})

    assert outcome["is_success"] is True
    assert outcome["payload"]["context"] == "new"
    assert "SET c.name = $name" in tx.calls[1]["query"]
    assert tx.commit_calls == 1
