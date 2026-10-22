"""Health/dependency reporting must be truthful about optional Firestore."""

import pytest

from app.core.infrastructure.db.database.connector import dependency_health

from startup_fakes import FakeFirestore, FakeMemgraph


def test_health_reports_graph_only_when_disabled(monkeypatch):
    monkeypatch.delenv("FIRESTORE_ENABLED", raising=False)
    memgraph = FakeMemgraph()
    memgraph.is_ready = True
    firestore = FakeFirestore(ready=False)

    health = dependency_health(memgraph, firestore)

    assert health["memgraph"] == {"required": True, "ready": True}
    assert health["firestore"] == {
        "required": False,
        "enabled": False,
        "ready": False,
        "status": "disabled",
    }


def test_health_never_implies_firebase_online_when_disabled(monkeypatch):
    # Even a stray ready flag cannot make a disabled dependency look online.
    monkeypatch.delenv("FIRESTORE_ENABLED", raising=False)
    firestore = FakeFirestore()
    firestore.is_ready = True

    health = dependency_health(FakeMemgraph(), firestore)

    assert health["firestore"]["enabled"] is False
    assert health["firestore"]["ready"] is False
    assert health["firestore"]["status"] == "disabled"


def test_health_reports_enabled_and_ready(monkeypatch):
    monkeypatch.setenv("FIRESTORE_ENABLED", "true")
    firestore = FakeFirestore()
    firestore.is_ready = True

    health = dependency_health(FakeMemgraph(), firestore)

    assert health["firestore"] == {
        "required": False,
        "enabled": True,
        "ready": True,
        "status": "ready",
    }


def test_health_reports_enabled_but_not_ready(monkeypatch):
    monkeypatch.setenv("FIRESTORE_ENABLED", "true")
    firestore = FakeFirestore()
    firestore.is_ready = False

    health = dependency_health(FakeMemgraph(), firestore)

    assert health["firestore"]["enabled"] is True
    assert health["firestore"]["ready"] is False
    assert health["firestore"]["status"] == "not_ready"


def test_health_reports_invalid_configuration(monkeypatch):
    monkeypatch.setenv("FIRESTORE_ENABLED", "perhaps")

    health = dependency_health(FakeMemgraph(), FakeFirestore())

    assert health["firestore"]["enabled"] is None
    assert health["firestore"]["status"] == "invalid_configuration"
    assert health["firestore"]["ready"] is False
