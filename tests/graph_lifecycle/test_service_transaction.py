"""Management-service failure paths must roll back, never commit a partial write.

The previous implementation caught DB exceptions *inside* the ``with self.uow``
block, so the UnitOfWork saw no exception and committed. These tests assert the
transaction is rolled back on any failed write and that the caller-facing
envelope is sanitized.
"""

from app.core.domain.graph_entities import Category
from app.core.services.management import CategoryManagementService
from graph_fakes import ServiceFakeRepository, ServiceFakeUnitOfWork

PAYLOAD = {"id": "cat_a", "name": "Coffee", "context": "warm vibe"}


def _service(repo):
    uow = ServiceFakeUnitOfWork(repo)
    return CategoryManagementService(uow), uow


def test_create_write_failure_rolls_back_and_is_sanitized():
    service, uow = _service(ServiceFakeRepository(fail_on="create"))

    outcome = service.create(dict(PAYLOAD))

    assert outcome["is_success"] is False
    assert outcome["error_type"] == "internal_error"
    assert "raw provider" not in outcome["payload"]["message"]
    assert uow.rollback_count == 1
    assert uow.commit_count == 0


def test_create_success_commits_exactly_once():
    repo = ServiceFakeRepository()
    service, uow = _service(repo)

    outcome = service.create(dict(PAYLOAD))

    assert outcome["is_success"] is True
    assert uow.commit_count == 1
    assert uow.rollback_count == 0
    assert len(repo.created) == 1


def test_create_conflict_does_not_commit():
    existing = Category(id="cat_a", name="Existing", context="ctx")
    repo = ServiceFakeRepository(existing=existing)
    service, uow = _service(repo)

    outcome = service.create(dict(PAYLOAD))

    assert outcome["is_success"] is False
    assert outcome["error_type"] == "conflict"
    assert repo.created == []
    assert uow.commit_count == 0
    assert uow.rollback_count == 1


def test_update_write_failure_rolls_back():
    existing = Category(id="cat_a", name="Old", context="old")
    repo = ServiceFakeRepository(existing=existing, fail_on="update")
    service, uow = _service(repo)

    outcome = service.update("cat_a", {"name": "New", "context": "new"})

    assert outcome["is_success"] is False
    assert outcome["error_type"] == "internal_error"
    assert uow.rollback_count == 1
    assert uow.commit_count == 0
    assert repo.updated == []


def test_update_not_found_does_not_commit():
    repo = ServiceFakeRepository(existing=None)
    service, uow = _service(repo)

    outcome = service.update("cat_a", {"name": "New", "context": "new"})

    assert outcome["is_success"] is False
    assert outcome["error_type"] == "not_found"
    assert uow.commit_count == 0
    assert uow.rollback_count == 1


def test_delete_write_failure_rolls_back():
    existing = Category(id="cat_a", name="Old", context="old")
    repo = ServiceFakeRepository(existing=existing, fail_on="delete")
    service, uow = _service(repo)

    outcome = service.delete("cat_a")

    assert outcome["is_success"] is False
    assert uow.rollback_count == 1
    assert uow.commit_count == 0
    assert repo.deleted == []


def test_validation_failure_never_opens_transaction():
    service, uow = _service(ServiceFakeRepository())

    outcome = service.create({"id": "cat_a", "name": "Coffee", "context": ""})

    assert outcome["is_success"] is False
    assert uow.enter_count == 0
    assert uow.commit_count == 0
    assert uow.rollback_count == 0
