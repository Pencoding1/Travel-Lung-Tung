"""UnitOfWork transaction-lifecycle and cleanup guarantees."""

import pytest

from app.core.infrastructure.db.uow import MemgraphUnitOfWork
from graph_fakes import FakeConnector, RecordingDriver, RecordingSession, RecordingTransaction


def _uow(tx=None, session=None):
    tx = tx or RecordingTransaction()
    session = session or RecordingSession(tx)
    driver = RecordingDriver(session)
    return MemgraphUnitOfWork(FakeConnector(driver)), tx, session


def test_missing_driver_fails_before_any_session():
    uow = MemgraphUnitOfWork(FakeConnector(None))
    with pytest.raises(RuntimeError):
        with uow:
            pass


def test_failed_begin_transaction_closes_session():
    session = RecordingSession(RuntimeError("begin boom"))
    driver = RecordingDriver(session)
    uow = MemgraphUnitOfWork(FakeConnector(driver))

    with pytest.raises(RuntimeError):
        with uow:
            pass

    assert session.begin_calls == 1
    assert session.close_calls == 1


def test_success_commits_once_and_closes_resources():
    uow, tx, session = _uow()
    with uow:
        pass

    assert tx.commit_calls == 1
    assert tx.rollback_calls == 0
    assert tx.close_calls == 1
    assert session.close_calls == 1


def test_commit_failure_still_closes_tx_and_session():
    tx = RecordingTransaction(commit_error=RuntimeError("commit boom"))
    uow, _tx, session = _uow(tx=tx)

    with pytest.raises(RuntimeError):
        with uow:
            pass

    assert tx.commit_calls == 1
    assert tx.close_calls == 1
    assert session.close_calls == 1


def test_rollback_failure_preserves_original_exception_and_cleans_up():
    tx = RecordingTransaction(rollback_error=RuntimeError("rollback boom"))
    uow, _tx, session = _uow(tx=tx)

    with pytest.raises(ValueError, match="original failure"):
        with uow:
            raise ValueError("original failure")

    assert tx.rollback_calls == 1
    assert tx.close_calls == 1
    assert session.close_calls == 1


def test_repeated_exit_is_safe_and_commits_once():
    uow, tx, session = _uow()
    uow.__enter__()
    assert uow.__exit__(None, None, None) is False
    # Second exit must not re-commit nor raise.
    assert uow.__exit__(None, None, None) is False

    assert tx.commit_calls == 1
    assert tx.close_calls == 1
    assert session.close_calls == 1


def test_reentry_of_same_uow_is_rejected():
    uow, _tx, _session = _uow()
    uow.__enter__()
    uow.__exit__(None, None, None)
    with pytest.raises(RuntimeError):
        uow.__enter__()
