"""Durable profile adapter tests (SQLite, tmpdir only)."""

import os

import pytest
from domains import memory
from domains.memory import ProfileConflict, SQLiteProfileStore, get_profile_store


def test_validate_profile_accepts_structured_authored_data():
    ok, errors, normalized = memory.validate_profile({
        "preferred_categories": {"cat_coffee": 5},
        "tags": ["quiet"],
        "budget": 500000,
        "currency": "vnd",
        "pace": "relaxed",
        "accessibility": ["wheelchair"],
    })
    assert ok, errors
    assert normalized["currency"] == "VND"
    assert normalized["pace"] == "relaxed"


def test_validate_profile_rejects_inferred_or_invalid_traits():
    ok, errors, _ = memory.validate_profile({"dietary": "vegan"})
    assert not ok
    assert any("dietary" in e for e in errors)

    ok, errors, _ = memory.validate_profile(
        {"preferred_categories": {"c": float("inf")}})
    assert not ok

    ok, errors, _ = memory.validate_profile({"budget": -1})
    assert not ok

    ok, errors, _ = memory.validate_profile({"pace": "sprint"})
    assert not ok


def test_restart_persistence(tmp_path):
    path = str(tmp_path / "profiles.db")
    first = SQLiteProfileStore(path)
    first.put("user-1", {"preferred_categories": {"cat_coffee": 3}})

    # A brand-new store instance over the same file sees the data (restart).
    second = SQLiteProfileStore(path)
    record = second.get("user-1")
    assert record is not None
    assert record["profile"]["preferred_categories"] == {"cat_coffee": 3}
    assert record["version"] == 1


def test_update_replaces_preferences_and_bumps_version(tmp_path):
    store = SQLiteProfileStore(str(tmp_path / "p.db"))
    store.put("u", {"preferred_categories": {"a": 1}})
    updated = store.put("u", {"preferred_categories": {"b": 2}},
                        expected_version=1)
    assert updated["version"] == 2
    assert store.get("u")["profile"]["preferred_categories"] == {"b": 2}


def test_version_conflict(tmp_path):
    store = SQLiteProfileStore(str(tmp_path / "p.db"))
    store.put("u", {"tags": ["x"]})
    with pytest.raises(ProfileConflict) as exc:
        store.put("u", {"tags": ["y"]}, expected_version=99)
    assert exc.value.current_version == 1


def test_delete_removes(tmp_path):
    store = SQLiteProfileStore(str(tmp_path / "p.db"))
    store.put("u", {"tags": ["x"]})
    assert store.delete("u") is True
    assert store.get("u") is None
    assert store.delete("u") is False


def test_malicious_subject_is_treated_as_data(tmp_path):
    store = SQLiteProfileStore(str(tmp_path / "p.db"))
    evil = "user'); DROP TABLE memory_profiles; --"
    store.put(evil, {"tags": ["ok"]})
    assert store.get(evil)["profile"]["tags"] == ["ok"]
    # The table still exists and other subjects are unaffected.
    store.put("normal", {"tags": ["n"]})
    assert store.get("normal")["profile"]["tags"] == ["n"]
    assert store.delete(evil) is True


def test_concurrent_expected_version_one_wins_no_lost_update(tmp_path):
    import threading

    path = str(tmp_path / "p.db")
    a = SQLiteProfileStore(path)
    b = SQLiteProfileStore(path)
    a.put("u", {"tags": ["base"]})  # version 1

    results = []
    barrier = threading.Barrier(2)

    def worker(store, tag):
        barrier.wait()
        try:
            store.put("u", {"tags": [tag]}, expected_version=1)
            results.append((tag, "ok"))
        except ProfileConflict as conflict:
            results.append((tag, "conflict", conflict.current_version))
        except Exception as exc:  # pragma: no cover - surfaced for debugging
            results.append((tag, "error", type(exc).__name__))

    threads = [threading.Thread(target=worker, args=(a, "a")),
               threading.Thread(target=worker, args=(b, "b"))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(1 for r in results if r[1] == "ok") == 1
    assert sum(1 for r in results if r[1] == "conflict") == 1
    # No lost update: the store moved to exactly version 2.
    assert a.get("u")["version"] == 2


def test_operations_close_connections(tmp_path):
    import sqlite3

    path = str(tmp_path / "p.db")
    store = SQLiteProfileStore(path)
    for _ in range(25):
        store.put("u", {"tags": ["x"]})
        store.get("u")
        store.get("missing")
    store.delete("u")
    # A subsequent writer is not blocked by leaked connections/locks.
    other = sqlite3.connect(path, timeout=1.0)
    try:
        other.execute("BEGIN IMMEDIATE")
        other.execute("ROLLBACK")
    finally:
        other.close()


def test_validate_profile_bounds_category_id_length():
    ok, errors, _ = memory.validate_profile({
        "preferred_categories": {"c" * (memory.MAX_CATEGORY_ID_CHARS + 1): 1.0}})
    assert not ok
    assert any("too long" in e for e in errors)


def test_profile_prompt_is_untrusted_delimited():
    block = memory.profile_prompt({"preferred_categories": {"cat_coffee": 5.0}})
    assert block is not None
    assert "Untrusted stored profile data" in block
    assert "<untrusted_profile>" in block or "STORED USER PROFILE" in block
    assert "ALWAYS override" in block
    assert len(block) <= memory.MAX_PROFILE_PROMPT_CHARS


def test_get_profile_store_requires_explicit_path(monkeypatch):
    monkeypatch.delenv("MEMORY_DB_PATH", raising=False)
    assert get_profile_store() is None
    monkeypatch.setenv("MEMORY_DB_PATH", str(""))
    assert get_profile_store() is None
