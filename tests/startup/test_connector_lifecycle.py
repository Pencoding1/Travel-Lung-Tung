"""Startup/shutdown lifecycle and connector state tests.

Everything is exercised through the real connector classes plus injected fake
SDK/loaders. No ``firebase_admin`` import, credential read, neo4j driver or
network call happens.
"""

import asyncio
import sys
from types import SimpleNamespace

import pytest

import app.core.infrastructure.db.database.connector as connector
from app.core.infrastructure.db.database.connector import (
    firestore_db,
    memgraph_db,
    shutdown_databases,
    startup_databases,
)

from startup_fakes import (
    FakeFirestore,
    FakeMemgraph,
    boom_loader,
    build_fake_sdk,
)


@pytest.fixture(autouse=True)
def _isolate_singletons():
    firestore_db._reset_state()
    yield
    firestore_db.close()
    memgraph_db.close()
    memgraph_db._reset_state()


# ---------------------------------------------------------------------------
# Graph-only default
# ---------------------------------------------------------------------------
def test_graph_only_default_never_loads_firebase(monkeypatch):
    monkeypatch.delenv("FIRESTORE_ENABLED", raising=False)
    firestore_db._sdk_loader = boom_loader
    memgraph = FakeMemgraph()

    asyncio.run(startup_databases(memgraph, firestore_db, enabled=None))

    assert memgraph.connect_calls == 1
    assert firestore_db.is_ready is False
    assert "firebase_admin" not in sys.modules

    asyncio.run(shutdown_databases(memgraph, firestore_db))
    assert memgraph.close_calls == 1


def test_disabled_connect_is_a_noop_even_when_called_directly():
    firestore_db._sdk_loader = boom_loader
    firestore_db.connect(enabled=False)
    assert firestore_db.is_ready is False
    assert "firebase_admin" not in sys.modules


# ---------------------------------------------------------------------------
# Enabled: success and cleanup
# ---------------------------------------------------------------------------
def test_enabled_true_connects_verifies_and_releases(tmp_path):
    key = tmp_path / "serviceAccountKey.json"
    key.write_text("not-a-real-key")
    sdk = build_fake_sdk()
    firestore_db._sdk_loader = lambda: sdk
    firestore_db._key_path = key
    memgraph = FakeMemgraph()

    asyncio.run(startup_databases(memgraph, firestore_db, enabled=True))

    assert firestore_db.is_ready is True
    assert memgraph.connect_calls == 1
    assert len(sdk.created) == 1
    assert "firebase_admin" not in sys.modules

    asyncio.run(shutdown_databases(memgraph, firestore_db))
    assert firestore_db.is_ready is False
    assert sdk.deleted == sdk.created


def test_enabled_init_failure_stops_startup_and_cleans_owned_app(tmp_path):
    key = tmp_path / "key.json"
    key.write_text("x")
    sdk = build_fake_sdk(client_error=RuntimeError("provider secret payload"))
    firestore_db._sdk_loader = lambda: sdk
    firestore_db._key_path = key
    memgraph = FakeMemgraph()

    with pytest.raises(RuntimeError) as excinfo:
        asyncio.run(startup_databases(memgraph, firestore_db, enabled=True))

    assert "provider secret payload" not in str(excinfo.value)
    assert firestore_db.is_ready is False
    assert len(sdk.created) == 1 and sdk.deleted == sdk.created
    assert memgraph.connect_calls == 0
    assert memgraph.close_calls == 1


def test_enabled_connectivity_failure_stops_startup_and_cleans(tmp_path):
    key = tmp_path / "key.json"
    key.write_text("x")
    sdk = build_fake_sdk(list_users_error=RuntimeError("raw connectivity text"))
    firestore_db._sdk_loader = lambda: sdk
    firestore_db._key_path = key
    memgraph = FakeMemgraph()

    with pytest.raises(RuntimeError) as excinfo:
        asyncio.run(startup_databases(memgraph, firestore_db, enabled=True))

    assert "raw connectivity text" not in str(excinfo.value)
    assert firestore_db.is_ready is False
    assert sdk.deleted == sdk.created
    assert memgraph.connect_calls == 0


def test_graph_failure_cleans_already_initialized_firestore(tmp_path):
    key = tmp_path / "key.json"
    key.write_text("x")
    sdk = build_fake_sdk()
    firestore_db._sdk_loader = lambda: sdk
    firestore_db._key_path = key
    memgraph = FakeMemgraph(fail=True)

    with pytest.raises(RuntimeError) as excinfo:
        asyncio.run(startup_databases(memgraph, firestore_db, enabled=True))

    assert "graph boom with provider detail" not in str(excinfo.value)
    assert firestore_db.is_ready is False
    assert sdk.deleted == sdk.created
    assert memgraph.connect_calls == 1
    assert memgraph.close_calls == 1


def test_invalid_flag_is_rejected_before_any_connection(monkeypatch):
    monkeypatch.setenv("FIRESTORE_ENABLED", "maybe")
    memgraph = FakeMemgraph()
    firestore = FakeFirestore()

    with pytest.raises(ValueError):
        asyncio.run(startup_databases(memgraph, firestore, enabled=None))

    assert memgraph.connect_calls == 0
    assert firestore.connect_calls == 0


# ---------------------------------------------------------------------------
# Shutdown robustness
# ---------------------------------------------------------------------------
def test_shutdown_closes_firestore_even_if_graph_close_raises():
    memgraph = FakeMemgraph(close_fail=True)
    firestore = FakeFirestore()

    with pytest.raises(RuntimeError):
        asyncio.run(shutdown_databases(memgraph, firestore))

    assert firestore.close_calls == 1


def test_firestore_close_does_not_delete_foreign_application():
    foreign = SimpleNamespace(name="[EXTERNAL]")
    sdk = build_fake_sdk(existing_apps={"[EXTERNAL]": foreign})
    firestore_db._sdk_loader = lambda: sdk

    firestore_db.connect(enabled=True)

    assert firestore_db.is_ready is True
    assert sdk.created == []  # an existing app was reused, not created by us

    firestore_db.close()

    assert sdk.deleted == []  # and it must not be deleted
    assert sdk._apps == {"[EXTERNAL]": foreign}


# ---------------------------------------------------------------------------
# Reconnect / repeated close
# ---------------------------------------------------------------------------
def test_firestore_connect_close_connect_reuse(tmp_path):
    key = tmp_path / "key.json"
    key.write_text("x")
    sdks = [build_fake_sdk(), build_fake_sdk()]
    iterator = iter(sdks)
    firestore_db._sdk_loader = lambda: next(iterator)
    firestore_db._key_path = key

    firestore_db.connect(enabled=True)
    assert firestore_db.is_ready is True
    firestore_db.close()
    assert firestore_db.is_ready is False

    firestore_db.close()  # repeated close is a no-op

    firestore_db.connect(enabled=True)
    assert firestore_db.is_ready is True
    firestore_db.close()

    assert sdks[0].deleted == sdks[0].created
    assert sdks[1].deleted == sdks[1].created


def test_memgraph_connect_close_connect_cycle(monkeypatch):
    drivers = []

    class FakeDriver:
        def __init__(self):
            self.verified = 0
            self.closed = 0

        def verify_connectivity(self):
            self.verified += 1

        def close(self):
            self.closed += 1

    class FakeGraphDatabase:
        @staticmethod
        def driver(uri, auth):
            driver = FakeDriver()
            drivers.append(driver)
            return driver

    monkeypatch.setattr(connector, "GraphDatabase", FakeGraphDatabase)
    memgraph_db._reset_state()

    asyncio.run(memgraph_db.connect())
    assert memgraph_db.is_ready is True

    memgraph_db.close()
    assert memgraph_db.driver is None
    assert memgraph_db.is_ready is False
    assert drivers[0].closed == 1

    memgraph_db.close()  # repeated close is a no-op
    assert drivers[0].closed == 1

    asyncio.run(memgraph_db.connect())
    assert memgraph_db.is_ready is True
    assert len(drivers) == 2

    memgraph_db.close()
    assert drivers[1].closed == 1
