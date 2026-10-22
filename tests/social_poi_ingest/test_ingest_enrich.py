"""Fake-transport tests: enrichment and dry-run ingestion planning."""

import json
from pathlib import Path

import pytest

from crawler_service.app.social_ingest.enrichment import (
    EnrichmentError,
    MissingApiKeyError,
    ReviewedEvidence,
    ReviewedEvidenceEnricher,
    SerpApiMapsEnricher,
    TransportNotConfigured,
)
from crawler_service.app.social_ingest.ingest import IngestError, build_ingest_plan

from helpers import reviewed_entity, run_acquisition, web_record, write_web_run


def serp_body(places):
    return json.dumps({"local_results": places}).encode("utf-8")


def test_missing_api_key_never_calls_transport():
    calls = []
    with pytest.raises(MissingApiKeyError) as exc:
        SerpApiMapsEnricher("", transport=lambda params: calls.append(params) or (200, b"{}"))
    assert exc.value.reason == "missing_api_key"
    assert calls == []


def test_paid_transport_must_be_injected():
    enricher = SerpApiMapsEnricher("secret-key")
    with pytest.raises(TransportNotConfigured):
        enricher.lookup("Cafe")
    assert "secret-key" not in repr(enricher)


@pytest.mark.parametrize(
    "status,reason", [(401, "auth_failed_401"), (403, "auth_failed_403"), (429, "rate_limited_429")]
)
def test_auth_and_rate_limit_do_not_leak_key(status, reason):
    seen = {}

    def transport(params):
        seen.update(params)
        return status, b'{"error":"nope"}'

    outcome = SerpApiMapsEnricher("secret-key", transport).lookup("Cafe")
    assert outcome.status == "error"
    assert outcome.reason == reason
    assert "secret-key" not in json.dumps(outcome.__dict__, default=str)


def test_ambiguous_exact_matches_are_not_auto_selected():
    transport = lambda params: (
        200,
        serp_body(
            [
                {
                    "title": "Cafe",
                    "address": "1 A",
                    "gps_coordinates": {"latitude": 10.1, "longitude": 106.1},
                },
                {
                    "title": "Cafe",
                    "address": "2 B",
                    "gps_coordinates": {"latitude": 10.2, "longitude": 106.2},
                },
            ]
        ),
    )
    outcome = SerpApiMapsEnricher("k", transport).lookup("Cafe")
    assert outcome.status == "ambiguous"
    assert outcome.candidate is None
    assert len(outcome.provenance) == 2


def test_missing_coordinates_and_name_mismatch_are_not_matched():
    transport = lambda params: (
        200,
        serp_body([{"title": "Cafe", "address": "1 A", "gps_coordinates": {}}]),
    )
    assert SerpApiMapsEnricher("k", transport).lookup("Cafe").status == "not_found"

    transport = lambda params: (
        200,
        serp_body(
            [{"title": "Other", "gps_coordinates": {"latitude": 1.0, "longitude": 2.0}}]
        ),
    )
    outcome = SerpApiMapsEnricher("k", transport).lookup("Cafe")
    assert outcome.status == "not_found"


def test_exact_match_records_provenance():
    transport = lambda params: (
        200,
        serp_body(
            [
                {
                    "title": "Cafe",
                    "address": "1 A",
                    "gps_coordinates": {"latitude": 10.1, "longitude": 106.1},
                }
            ]
        ),
    )
    outcome = SerpApiMapsEnricher("k", transport).lookup("Cafe")
    assert outcome.status == "matched"
    assert outcome.candidate.latitude == 10.1
    assert outcome.provenance[0]["source"] == "serpapi_google_maps"
    assert len(outcome.provenance[0]["response_sha256"]) == 64


def test_reviewed_evidence_enricher_requires_exact_reviewed_match():
    enricher = ReviewedEvidenceEnricher(
        [
            ReviewedEvidence(
                name="Place",
                address="1 A",
                latitude=10.0,
                longitude=106.0,
                reviewer="synthetic-test-reviewer",
                evidence_reference="tests/social_poi_ingest/fixture.json",
            )
        ]
    )
    assert enricher.lookup("Place", "1 A").status == "matched"
    assert enricher.lookup("Place", "9 Z").status == "not_found"
    with pytest.raises(EnrichmentError):
        ReviewedEvidenceEnricher([])


def _accepted_run(tmp_path):
    manifest, mapping, _ = write_web_run(
        tmp_path,
        [web_record(record_id="node/1#a", coordinates=[10.78, 106.70], review_text="review")],
        entities={"web_poi/https://example.test/pois#node/1#a": reviewed_entity()},
    )
    out = tmp_path / "acquisition"
    run_acquisition(manifest, mapping, out)
    return out


def test_ingest_plan_is_dry_run_by_default_and_preserves_evidence(tmp_path):
    out = _accepted_run(tmp_path)
    plan = build_ingest_plan(
        out / "accepted.jsonl",
        out / "candidates.jsonl",
        tmp_path / "plan",
        dataset="social_web_oc050_test",
        synthetic=True,
    )
    assert plan["dry_run"] is True
    assert plan["counts"]["imported"] == 0
    assert plan["counts"]["payload_rows"] == 1
    rows = [
        json.loads(line)
        for line in (tmp_path / "plan" / "ingestion_payload.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["id"]
    assert "description" not in rows[0]  # POI payload unchanged
    sidecar = [
        json.loads(line)
        for line in (tmp_path / "plan" / "ingestion_evidence.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert sidecar[0]["evidence"]["description"].startswith("A synthetic narrative")
    assert sidecar[0]["evidence"]["field_evidence"]


def test_fake_canary_422_reports_failure_and_imported_zero(tmp_path):
    out = _accepted_run(tmp_path)
    plan = build_ingest_plan(
        out / "accepted.jsonl",
        out / "candidates.jsonl",
        tmp_path / "plan",
        dataset="social_web_oc050_test",
        synthetic=True,
        dry_run=False,
        opt_in=True,
        transport=lambda payloads: (422, b'{"error":"canary failed"}'),
    )
    assert plan["transport_result"]["status"] == "failed"
    assert plan["transport_result"]["reason"] == "canary_rejected_422"
    assert plan["transport_result"]["imported"] == 0
    assert plan["counts"]["imported"] == 0


def test_fake_network_failure_and_unverified_success_never_claim_import(tmp_path):
    out = _accepted_run(tmp_path)

    def network_failure(payloads):
        raise OSError("connection reset")

    plan = build_ingest_plan(
        out / "accepted.jsonl",
        out / "candidates.jsonl",
        tmp_path / "plan_a",
        dataset="social_web_oc050_test",
        synthetic=True,
        dry_run=False,
        opt_in=True,
        transport=network_failure,
    )
    assert plan["transport_result"]["imported"] == 0
    assert "network_error" in plan["transport_result"]["reason"]

    plan = build_ingest_plan(
        out / "accepted.jsonl",
        out / "candidates.jsonl",
        tmp_path / "plan_b",
        dataset="social_web_oc050_test",
        synthetic=True,
        dry_run=False,
        opt_in=True,
        transport=lambda payloads: (200, b'{"ok":true}'),
    )
    assert plan["transport_result"]["status"] == "unverified"
    assert plan["transport_result"]["imported"] == 0


def test_live_submit_requires_explicit_opt_in_and_transport(tmp_path):
    out = _accepted_run(tmp_path)
    with pytest.raises(IngestError):
        build_ingest_plan(
            out / "accepted.jsonl",
            out / "candidates.jsonl",
            tmp_path / "plan",
            dataset="social_web_oc050_test",
            synthetic=True,
            dry_run=False,
            opt_in=False,
            transport=lambda payloads: (200, b"{}"),
        )
