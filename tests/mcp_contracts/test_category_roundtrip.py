"""Category context must persist and round-trip through create/update."""

import pytest
from pydantic import ValidationError

from app.core.domain.graph_entities import Category
from app.core.infrastructure.db.repositories.memgraph import MemgraphCategoryRepository
from app.core.services.management import CategoryManagementService
from mcp_fakes import FakeCategoryRepository, FakeTransaction, FakeUnitOfWork


def test_repository_create_persists_and_returns_context():
    tx = FakeTransaction([{"c": {"id": "cat_a", "name": "Coffee", "context": "warm vibe"}}])
    repo = MemgraphCategoryRepository(tx)
    entity = Category(id="cat_a", name="Coffee", context="warm vibe")

    created = repo.create(entity)

    call = tx.calls[0]
    assert "context: $context" in call["query"]
    assert call["parameters"] == {"id": "cat_a", "name": "Coffee", "context": "warm vibe"}
    assert created.context == "warm vibe"


def test_repository_update_persists_and_returns_context():
    tx = FakeTransaction([{"c": {"id": "cat_a", "name": "Coffee 2", "context": "new context"}}])
    repo = MemgraphCategoryRepository(tx)
    entity = Category(id="cat_a", name="Coffee 2", context="new context")

    updated = repo.update("cat_a", entity)

    call = tx.calls[0]
    assert "c.context = $context" in call["query"]
    assert call["parameters"]["context"] == "new context"
    assert updated.context == "new context"


def test_domain_rejects_empty_context_instead_of_falling_back():
    with pytest.raises(ValidationError):
        Category(id="cat_a", name="Coffee", context="   ")


def test_service_create_round_trips_context():
    uow = FakeUnitOfWork(cat_repo=FakeCategoryRepository())
    service = CategoryManagementService(uow)

    outcome = service.create({"id": "cat_a", "name": "Coffee", "context": "warm vibe"})

    assert outcome["is_success"] is True
    assert outcome["payload"]["context"] == "warm vibe"
    assert uow.cats.created[0].context == "warm vibe"


def test_service_create_rejects_blank_context_without_writing():
    uow = FakeUnitOfWork(cat_repo=FakeCategoryRepository())
    service = CategoryManagementService(uow)

    outcome = service.create({"id": "cat_a", "name": "Coffee", "context": ""})

    assert outcome["is_success"] is False
    assert uow.cats.created == []
