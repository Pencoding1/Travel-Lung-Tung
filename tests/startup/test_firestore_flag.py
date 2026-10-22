"""Strict ``FIRESTORE_ENABLED`` parsing (graph-only is the default)."""

import pytest

from app.core.infrastructure.db.database.connector import (
    FIRESTORE_ENABLED_ENV,
    firestore_enabled,
    parse_firestore_enabled,
)

TRUE_SPELLINGS = ["true", "TRUE", "True", "1", "yes", "YES", "on", "ON", " true "]
FALSE_SPELLINGS = ["false", "FALSE", "False", "0", "no", "NO", "off", "OFF", " false "]


@pytest.mark.parametrize("raw", TRUE_SPELLINGS)
def test_documented_true_spellings_enable_firestore(raw):
    assert parse_firestore_enabled(raw) is True


@pytest.mark.parametrize("raw", FALSE_SPELLINGS)
def test_documented_false_spellings_keep_graph_only(raw):
    assert parse_firestore_enabled(raw) is False


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_absent_or_blank_is_graph_only(raw):
    assert parse_firestore_enabled(raw) is False


@pytest.mark.parametrize("raw", ["maybe", "2", "enabled", "truee", "nope"])
def test_invalid_values_are_rejected_not_silently_disabled(raw):
    with pytest.raises(ValueError):
        parse_firestore_enabled(raw)


def test_firestore_enabled_reads_process_environment(monkeypatch):
    monkeypatch.setenv(FIRESTORE_ENABLED_ENV, "on")
    assert firestore_enabled() is True
    monkeypatch.setenv(FIRESTORE_ENABLED_ENV, "off")
    assert firestore_enabled() is False
    monkeypatch.delenv(FIRESTORE_ENABLED_ENV, raising=False)
    assert firestore_enabled() is False
