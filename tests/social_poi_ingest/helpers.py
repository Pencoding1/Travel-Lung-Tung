"""SYNTHETIC test builders for the OC-050 web ingestion pipeline.

Nothing here is real captured data. The ``synthetic`` flag is explicit in every
export, and reviewer identities are test fixtures, never claimed as real people.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from crawler_service.app.acquisition.pipeline import run_pipeline
from crawler_service.app.social_ingest.fetch import (
    Capture,
    FetchPolicy,
    HttpFetcher,
    TransportResponse,
)

NOW = "2026-10-18T00:00:00Z"


def synthetic_profile(**overrides: Any):
    from crawler_service.app.social_ingest.profiles import SourceProfile

    values = {
        "name": "synthetic_test_source",
        "source_id": "synthetic-test-source",
        "dataset": "social_web_oc050_test",
        "host": "example.test",
        "allow_hosts": ("example.test",),
        "start_urls": ("https://example.test/pois",),
        "extractor": "html_chapters_v1",
        "category_tags": ("tourism=attraction",),
        "license": "SYNTHETIC-TEST-ONLY",
        "reuse_status": "permitted",
        "notes": "synthetic fixture",
    }
    values.update(overrides)
    return SourceProfile(**values)


def evidence(
    field_name: str,
    value: Optional[str],
    *,
    page_url: str = "https://example.test/pois",
    capture_sha: str = "a" * 64,
    capture_path: str = "raw/page.html",
) -> Dict[str, Any]:
    return {
        "field": field_name,
        "value": value,
        "source_url": page_url,
        "fetched_at": NOW,
        "raw_capture_path": capture_path,
        "raw_sha256": capture_sha,
        "locator": f"/section[{field_name}]",
    }


def web_record(
    record_id: Optional[str] = "node/137#chapter-1",
    name: Optional[str] = "Synthetic Museum",
    address_raw: Optional[str] = "1 Test Street, District 1, Ho Chi Minh City",
    description: Optional[str] = "A synthetic narrative used only in tests.",
    review_text: Optional[str] = None,
    coordinates: Optional[List[float]] = None,
    category_tags: Optional[List[str]] = None,
    issues: Optional[List[str]] = None,
) -> Dict[str, Any]:
    field_evidence = [
        item
        for item in (
            evidence("name", name),
            evidence("address_raw", address_raw),
            evidence("description", description),
            evidence("review_text", review_text),
        )
        if item["value"] is not None
    ]
    return {
        "record_id": record_id,
        "name": name,
        "address_raw": address_raw,
        "address_hints": {"addr:full": address_raw} if address_raw else {},
        "description": description,
        "review_text": review_text,
        "category_tags": category_tags or ["tourism=attraction"],
        "coordinates": coordinates,
        "opening_hours_raw": None,
        "field_evidence": field_evidence,
        "issues": list(issues or []),
        "minimum_valid": bool(name and (address_raw or coordinates) and (description or review_text)),
        "page_url": "https://example.test/pois",
        "page_capture_sha256": "a" * 64,
        "page_capture_path": "raw/page.html",
        "page_fetched_at": NOW,
        "locator": "section.ac-chapter[0]#chapter-1",
    }


def web_export(
    records: List[Dict[str, Any]],
    *,
    synthetic: bool = True,
    license: str = "SYNTHETIC-TEST-ONLY",
    reuse_status: str = "permitted",
) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "synthetic": bool(synthetic),
        "source": {
            "source_id": "synthetic-test-source",
            "profile": "synthetic_test_source",
            "source_type": "web_poi",
            "license": license,
            "reuse_status": reuse_status,
            "policy_evidence": [],
        },
        "captures": [],
        "records": records,
    }


def write_json(path: Path, value: Any) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def write_web_run(
    directory: Path,
    records: List[Dict[str, Any]],
    *,
    synthetic: bool = True,
    license: str = "SYNTHETIC-TEST-ONLY",
    reuse_status: str = "permitted",
    entities: Optional[Dict[str, Dict[str, Any]]] = None,
    dataset: str = "social_web_oc050_test",
) -> tuple[Path, Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    export = write_json(
        directory / "export.json",
        web_export(
            records, synthetic=synthetic, license=license, reuse_status=reuse_status
        ),
    )
    manifest = write_json(
        directory / "manifest.json",
        {
            "manifest_version": 1,
            "dataset": dataset,
            "synthetic": synthetic,
            "sources": [
                {
                    "source_id": "synthetic-test-source",
                    "source_type": "web_poi",
                    "source_url": "https://example.test/pois",
                    "license": license,
                    "retrieved_at": NOW,
                    "export_path": export.name,
                    "synthetic": synthetic,
                }
            ],
        },
    )
    mapping = write_json(
        directory / "mapping.json",
        {
            "mapping_version": 1,
            "categories": [
                {"id": "attraction", "name": "Attraction", "context": "Test"},
                {"id": "museum", "name": "Museum", "context": "Test"},
            ],
            "sources": {
                "synthetic-test-source": {
                    "synthetic": synthetic,
                    "districts": {},
                    "category_map": {"tourism=attraction": "attraction"},
                    "entities": entities or {},
                }
            },
        },
    )
    return manifest, mapping, export


def reviewed_entity(
    reviewer: str = "synthetic-test-reviewer",
    evidence_reference: str = "tests/social_poi_ingest/synthetic-fixture.json",
    city: str = "Ho Chi Minh City",
    district: str = "District 1",
) -> Dict[str, str]:
    return {
        "reviewer": reviewer,
        "evidence_reference": evidence_reference,
        "city": city,
        "district": district,
        "nation": "Vietnam",
    }


def run_acquisition(manifest: Path, mapping: Path, out: Path):
    return run_pipeline(manifest, mapping, out, now=NOW, dry_run=True)


class FakeTransport:
    """Deterministic response map; no socket is ever opened."""

    def __init__(self, responses: Dict[str, Any]) -> None:
        self.responses = responses
        self.calls: List[str] = []

    def __call__(self, url: str, timeout: float, headers: Dict[str, str]) -> TransportResponse:
        self.calls.append(url)
        value = self.responses.get(url)
        if value is None:
            raise AssertionError(f"unexpected URL in fake transport: {url}")
        if isinstance(value, Exception):
            raise value
        return value


def html_response(body: str | bytes, status: int = 200, content_type: str = "text/html; charset=utf-8") -> TransportResponse:
    payload = body.encode("utf-8") if isinstance(body, str) else body
    return TransportResponse(status=status, headers={"content-type": content_type}, body=payload)


def fetcher_for(transport: FakeTransport, hosts: Sequence[str] = ("example.test",)) -> HttpFetcher:
    return HttpFetcher(
        FetchPolicy(
            allow_hosts=tuple(hosts),
            timeout_seconds=1.0,
            max_bytes=100_000,
            max_redirects=2,
            retries=0,
            min_interval_seconds=0.0,
        ),
        transport=transport,
        resolver=lambda host, port: ["93.184.216.34"],
        clock=lambda: 0.0,
        sleep=lambda seconds: None,
        wall_clock=lambda: NOW,
    )
