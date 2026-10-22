"""OC-050 T057c: conservative enrichment matching, sanitised errors, provenance.

Every test here is offline: transports are plain callables, so no network call
can happen. Fixtures are synthetic; no capture data is read.
"""

import json
from datetime import datetime, timezone

import pytest

from crawler_service.app.social_ingest.enrichment import (
    PROVENANCE_KEYS,
    STATUS_AMBIGUOUS,
    STATUS_MATCHED,
    STATUS_NOT_FOUND,
    STATUS_REVIEW_REQUIRED,
    UNKNOWN_PROVENANCE,
    ReviewedEvidence,
    ReviewedEvidenceEnricher,
    SerpApiMapsEnricher,
)

#: Doubles as a canary and a pretend key: it must never reach any output.
CANARY = "sk-CANARY-4f7d9b1e2c-not-a-real-key"
CLOCK_INSTANT = datetime(2026, 10, 18, 9, 30, tzinfo=timezone.utc)
STAMP = "2026-10-18T09:30:00+00:00"


def serp_body(places):
    return json.dumps({"local_results": places}).encode("utf-8")


def enricher(transport, *, key="test-key-not-real"):
    return SerpApiMapsEnricher(key, transport, clock=lambda: CLOCK_INSTANT)


def place(title="Cafe", address="1 A", latitude=10.1, longitude=106.1):
    payload = {"title": title, "gps_coordinates": {"latitude": latitude, "longitude": longitude}}
    if address is not None:
        payload["address"] = address
    return payload


def assert_provenance_self_describing(outcome):
    """Every recorded row names its source lineage; nothing is silently blank."""

    assert outcome.provenance, "a decided outcome must record what was seen"
    for row in outcome.provenance:
        for key in PROVENANCE_KEYS:
            assert key in row, f"provenance row missing {key!r}: {row}"
        for key in ("source", "source_url", "retrieved_at", "raw_reference"):
            value = row[key]
            assert isinstance(value, str) and value.strip(), f"{key} must not be blank"
        digest = row["response_sha256"]
        assert isinstance(digest, str) and len(digest) == 64
        int(digest, 16)  # hex only
        assert isinstance(row["selected"], bool)
        # a row must be JSON-serialisable as-is: no NaN/inf can hide in it
        json.dumps(row, allow_nan=False)


# --------------------------------------------------------------------------
# 1. Address confirmation is mandatory
# --------------------------------------------------------------------------


def test_same_name_different_address_is_not_assigned():
    transport = lambda params: (200, serp_body([place(title="Cafe", address="2 B")]))
    outcome = enricher(transport).lookup("Cafe", "1 A")

    assert outcome.status == STATUS_REVIEW_REQUIRED
    assert outcome.reason == "address_not_confirmed"
    assert outcome.candidate is None
    assert [row["match_decision"] for row in outcome.provenance] == [
        "rejected_address_mismatch"
    ]
    assert_provenance_self_describing(outcome)


def test_same_name_without_any_address_cannot_be_confirmed():
    transport = lambda params: (200, serp_body([place(address=None)]))
    outcome = enricher(transport).lookup("Cafe")

    assert outcome.status == STATUS_REVIEW_REQUIRED
    assert outcome.candidate is None
    assert outcome.provenance[0]["match_decision"] == "rejected_missing_address"
    assert_provenance_self_describing(outcome)


def test_address_match_ignores_case_and_whitespace_but_not_content():
    transport = lambda params: (200, serp_body([place(address="  1   a ")]))
    assert enricher(transport).lookup("cafe", "1 A").status == STATUS_MATCHED
    assert enricher(transport).lookup("Cafe", "1 B").status == STATUS_REVIEW_REQUIRED


def test_same_coordinates_different_addresses_are_ambiguous():
    transport = lambda params: (
        200,
        serp_body([place(address="1 A"), place(address="9 Z")]),
    )
    outcome = enricher(transport).lookup("Cafe")

    assert outcome.status == STATUS_AMBIGUOUS
    assert outcome.candidate is None
    assert_provenance_self_describing(outcome)


# --------------------------------------------------------------------------
# 2. Coordinates must be finite and in range
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "latitude,longitude",
    [
        (float("nan"), 106.1),
        (10.1, float("nan")),
        (float("inf"), 106.1),
        (91.0, 106.1),
        (-90.0001, 106.1),
        (10.1, 180.5),
        (10.1, -180.0001),
        ("10.1", 106.1),
        (True, 106.1),
        (None, None),
    ],
)
def test_invalid_coordinates_are_rejected_without_crashing(latitude, longitude):
    transport = lambda params: (
        200,
        serp_body([place(latitude=latitude, longitude=longitude)]),
    )
    outcome = enricher(transport).lookup("Cafe", "1 A")

    assert outcome.status == STATUS_NOT_FOUND
    assert outcome.reason == "no_candidate_with_finite_coordinates"
    assert outcome.candidate is None
    assert_provenance_self_describing(outcome)
    # a rejected row must not smuggle NaN/inf into the report
    json.dumps(outcome.provenance, allow_nan=False)


def test_missing_coordinate_block_is_rejected():
    transport = lambda params: (
        200,
        serp_body([{"title": "Cafe", "address": "1 A", "gps_coordinates": {}}]),
    )
    outcome = enricher(transport).lookup("Cafe")
    assert outcome.status == STATUS_NOT_FOUND
    assert outcome.candidate is None


# --------------------------------------------------------------------------
# 3. Transport error text never reaches the report
# --------------------------------------------------------------------------


class UrlCarryingError(OSError):
    """Mimics urllib errors whose message embeds the failing request URL."""


def _raise(exc):
    def transport(params):
        raise exc(f"HTTP failure for url: https://serpapi.com/search.json?engine=google_maps"
                  f"&api_key={CANARY} (key={params['api_key']})")

    return transport


@pytest.mark.parametrize(
    "exc,expected_reason",
    [
        (OSError, "network_error:OSError"),
        (UrlCarryingError, "network_error:UrlCarryingError"),
        (RuntimeError, "transport_error:RuntimeError"),
        (TimeoutError, "network_error:TimeoutError"),
    ],
)
def test_transport_error_reports_class_only_and_never_the_canary(exc, expected_reason):
    outcome = enricher(_raise(exc)).lookup("Cafe", "1 A")

    assert outcome.status == "error"
    assert outcome.reason == expected_reason
    assert outcome.candidate is None

    rendered = json.dumps(outcome.__dict__, default=str)
    for surface in (outcome.reason, rendered, repr(outcome), str(outcome)):
        assert CANARY not in surface
        assert "api_key" not in surface
        assert "http" not in surface.casefold().replace("http_", "")


def test_transport_contract_violations_are_reported_not_raised():
    outcome = enricher(lambda params: (200, "{}")).lookup("Cafe")
    assert outcome.reason == "transport_contract_violation:body_not_bytes"

    outcome = enricher(lambda params: ("200", b"{}")).lookup("Cafe")
    assert outcome.reason == "transport_contract_violation:status_not_int"


def test_empty_name_never_calls_the_transport():
    calls = []
    outcome = enricher(lambda params: calls.append(params) or (200, serp_body([place()]))).lookup("   ")
    assert outcome.status == STATUS_NOT_FOUND
    assert outcome.reason == "empty_name"
    assert calls == []


# --------------------------------------------------------------------------
# 4. A fully confirmed candidate is still accepted
# --------------------------------------------------------------------------


def test_valid_candidate_is_still_matched():
    transport = lambda params: (200, serp_body([place()]))
    outcome = enricher(transport).lookup("Cafe", "1 A")

    assert outcome.status == STATUS_MATCHED
    assert outcome.candidate is not None
    assert (outcome.candidate.name, outcome.candidate.address) == ("Cafe", "1 A")
    assert (outcome.candidate.latitude, outcome.candidate.longitude) == (10.1, 106.1)
    assert outcome.candidate.source == "serpapi_google_maps"
    selected = [row for row in outcome.provenance if row["selected"]]
    assert len(selected) == 1
    assert selected[0]["match_decision"] == "selected"
    assert_provenance_self_describing(outcome)


# --------------------------------------------------------------------------
# 5. Provenance: source URL, retrieval time, raw reference
# --------------------------------------------------------------------------


def test_provenance_names_source_url_time_and_raw_reference():
    transport = lambda params: (200, serp_body([place()]))
    outcome = enricher(transport).lookup("Cafe", "1 A")

    row = outcome.provenance[0]
    assert row["source_url"] == SerpApiMapsEnricher.endpoint
    assert row["retrieved_at"] == STAMP
    datetime.fromisoformat(row["retrieved_at"])  # timezone-aware ISO-8601
    assert row["response_sha256"] == outcome.candidate.raw_sha256
    # no raw body is persisted by this module: the gap is stated, not blank
    assert row["raw_reference"] == UNKNOWN_PROVENANCE
    assert row["raw_reference"].startswith("unknown:")


def test_provenance_records_caller_supplied_raw_reference_and_time():
    transport = lambda params: (200, serp_body([place()]))
    outcome = enricher(transport).lookup(
        "Cafe",
        "1 A",
        raw_reference="runs/2026-10-18/serpapi/cafe.json",
        retrieved_at="2026-10-18T02:05:00+07:00",
    )
    row = outcome.provenance[0]
    assert row["raw_reference"] == "runs/2026-10-18/serpapi/cafe.json"
    assert row["retrieved_at"] == "2026-10-18T02:05:00+07:00"
    assert CANARY not in json.dumps(row, default=str)


def test_every_outcome_kind_records_self_describing_provenance():
    matched = enricher(lambda p: (200, serp_body([place()]))).lookup("Cafe", "1 A")
    ambiguous = enricher(
        lambda p: (200, serp_body([place(address="1 A"), place(address="2 B")]))
    ).lookup("Cafe")
    review = enricher(lambda p: (200, serp_body([place(address="2 B")]))).lookup("Cafe", "1 A")
    rejected_coords = enricher(
        lambda p: (200, serp_body([place(latitude=float("nan"))]))
    ).lookup("Cafe", "1 A")

    for outcome in (matched, ambiguous, review, rejected_coords):
        assert_provenance_self_describing(outcome)
        for row in outcome.provenance:
            assert row["source_url"] == SerpApiMapsEnricher.endpoint
            assert row["retrieved_at"] == STAMP


# --------------------------------------------------------------------------
# 6. Reviewed-evidence path follows the same rules
# --------------------------------------------------------------------------


def reviewed(address="1 A", latitude=10.1, longitude=106.1, reference="fixtures/cafe.json"):
    return ReviewedEvidence(
        name="Cafe",
        address=address,
        latitude=latitude,
        longitude=longitude,
        reviewer="synthetic-test-reviewer",
        evidence_reference=reference,
        source_url="file://tests/social_poi_ingest/fixtures/cafe.json",
        retrieved_at="2026-10-18T02:00:00+07:00",
    )


def test_reviewed_same_name_different_address_is_not_matched():
    outcome = ReviewedEvidenceEnricher([reviewed()]).lookup("Cafe", "9 Z")
    assert outcome.status == STATUS_NOT_FOUND
    assert outcome.candidate is None
    assert outcome.provenance[0]["match_decision"] == "rejected_address_mismatch"


def test_reviewed_missing_address_requires_review():
    outcome = ReviewedEvidenceEnricher([reviewed(address="")]).lookup("Cafe")
    assert outcome.status == STATUS_REVIEW_REQUIRED
    assert outcome.candidate is None
    assert_provenance_self_describing(outcome)


def test_reviewed_invalid_coordinates_are_rejected():
    outcome = ReviewedEvidenceEnricher([reviewed(latitude=float("nan"))]).lookup("Cafe", "1 A")
    assert outcome.status == STATUS_NOT_FOUND
    assert outcome.reason == "invalid_reviewed_coordinates"
    assert outcome.candidate is None
    json.dumps(outcome.provenance, allow_nan=False)


def test_reviewed_match_keeps_source_reference_and_provenance():
    outcome = ReviewedEvidenceEnricher([reviewed()]).lookup("Cafe", "1 A")
    assert outcome.status == STATUS_MATCHED
    row = outcome.provenance[0]
    assert row["evidence_reference"] == "fixtures/cafe.json"
    assert row["raw_reference"] == "fixtures/cafe.json"
    assert row["source_url"].startswith("file://")
    assert row["reviewer"] == "synthetic-test-reviewer"
    assert_provenance_self_describing(outcome)
