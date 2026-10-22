"""Typed-contract, identity and fact-fingerprint tests (SYNTHETIC)."""

import math

import pytest

from crawler_service.app.acquisition.contracts import POICandidate, is_finite_in_range, is_number, parse_utc
from crawler_service.app.acquisition.identity import (
    fact_fingerprint,
    namespaced_source_hash,
    stable_source_id,
)


def candidate(**overrides):
    base = dict(
        source_type="osm",
        source_entity_id="node/1",
        geometry_kind="point",
        name="Demo",
        aliases=[],
        coordinates=(10.0, 106.0),
        address_hints={},
        category_tags=["amenity=cafe"],
        opening_hours_raw=None,
        raw_content_reference="raw/x.json",
        raw_sha256="a" * 64,
        source_url="file://x",
        license="ODbL-1.0",
        retrieved_at="2026-10-15T00:00:00Z",
        source_revision="1",
    )
    base.update(overrides)
    return POICandidate(**base)


def test_stable_id_is_deterministic_and_source_derived():
    assert stable_source_id("osm", "node/1") == stable_source_id("osm", "node/1")
    assert stable_source_id("osm", "node/1") != stable_source_id("osm", "node/2")
    assert stable_source_id("osm", "node/1") != stable_source_id("osm", "way/1")
    assert stable_source_id("osm", "node/1") != stable_source_id("wikidata", "node/1")
    assert stable_source_id("osm", "node/1").startswith("osm:")


def test_stable_id_is_independent_of_taxonomy_time_and_address():
    base = stable_source_id("wikidata", "Q100")
    assert "cafe" not in base and "district" not in base.lower()
    assert "202" not in base
    assert base == f"wikidata:{namespaced_source_hash('wikidata', 'Q100')[:32]}"


def test_bool_is_not_numeric():
    assert is_number(1) is True
    assert is_number(True) is False
    assert is_number(None) is False
    assert is_number("1") is False


@pytest.mark.parametrize(
    "value,expected",
    [
        (10.0, True), (0, True), (-90.0, True), (90.0, True),
        (90.0001, False), (-90.0001, False), (math.nan, False), (math.inf, False),
        (-math.inf, False), (True, False), (False, False), ("10", False),
    ],
)
def test_finite_range_validation(value, expected):
    assert is_finite_in_range(value, -90.0, 90.0) is expected


def test_parse_utc_requires_aware_timestamp():
    assert parse_utc("2026-10-15T00:00:00Z").tzinfo is not None
    for bad in ("2026-10-15T00:00:00", "", None):
        with pytest.raises(ValueError):
            parse_utc(bad)


def test_fact_fingerprint_ignores_container_metadata():
    a = candidate(raw_sha256="a" * 64, source_url="file://a", retrieved_at="2026-10-15T00:00:00Z", source_revision="1")
    b = candidate(raw_sha256="b" * 64, source_url="file://b", retrieved_at="2026-11-01T00:00:00Z", source_revision="99")
    assert fact_fingerprint(a) == fact_fingerprint(b)


def test_fact_fingerprint_changes_with_normative_facts():
    base = candidate()
    assert fact_fingerprint(base) != fact_fingerprint(candidate(name="Other"))
    assert fact_fingerprint(base) != fact_fingerprint(candidate(coordinates=(10.1, 106.0)))
    assert fact_fingerprint(base) != fact_fingerprint(candidate(category_tags=["tourism=attraction"]))


def test_fact_fingerprint_handles_unserializable_coordinates():
    # A malformed coordinate (list) must not raise while fingerprinting.
    assert fact_fingerprint(candidate(coordinates=([10.0], 106.0)))
