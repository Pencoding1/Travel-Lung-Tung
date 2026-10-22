"""Identity namespacing and the mandatory-address gate for ``web_poi``.

Everything here is SYNTHETIC: the exports, pages and reviewer identities are
fixtures written by this file, never captured data.

Covered:

* two hosts that both use native id ``1`` are two entities (the bug was a bare
  global id);
* a relative ``@id`` is namespaced by the page it came from and never becomes a
  bare global id;
* identity is stable across record order and across added/removed records;
* changing name/description/review keeps the entity (no name/address hashing);
* an absolute ``@id`` is kept verbatim and namespacing is idempotent, so the
  social runner export and the acquisition adapter agree on one entity;
* a record without an address is flagged/never accepted even when it has
  coordinates, on the adapter path *and* through the acquisition CLI;
* a listing page reused as every record's ``@id`` is not merged into one entity.
"""

import json
from pathlib import Path

from crawler_service.app.acquisition import cli
from crawler_service.app.acquisition.adapters.web_poi import (
    WebPOIAdapter,
    canonical_page_namespace,
    namespaced_entity_id,
)
from crawler_service.app.acquisition.contracts import ReasonCode
from crawler_service.app.acquisition.identity import sha256_bytes, stable_source_id
from crawler_service.app.social_ingest.extract import ExtractedRecord, ExtractionResult
from crawler_service.app.social_ingest.profiles import SourceProfile
from crawler_service.app.social_ingest.runner import _normalize_records, collect_profile

from acquisition_helpers import (
    default_categories,
    entity_review,
    write_json,
    write_manifest,
    write_mapping,
)

NOW = "2026-10-18T00:00:00Z"
PAGE_A = "https://example.test/pois"
PAGE_B = "https://other-source.test/pois"


# --------------------------------------------------------------------------- #
# synthetic web_poi export builders
# --------------------------------------------------------------------------- #


def evidence(field_name, value, *, page_url=PAGE_A):
    return {
        "field": field_name,
        "value": value,
        "source_url": page_url,
        "fetched_at": NOW,
        "raw_capture_path": "raw/pois.html",
        "raw_sha256": "a" * 64,
        "locator": f"/ld[0]/{field_name}",
    }


def web_record(
    record_id,
    *,
    page_url=PAGE_A,
    name="Synthetic Museum",
    address_raw="1 Test Street, District 1",
    description="Synthetic narrative used only in tests.",
    review_text=None,
    coordinates=None,
    issues=None,
):
    field_evidence = [
        evidence(field_name, value, page_url=page_url)
        for field_name, value in (
            ("name", name),
            ("address_raw", address_raw),
            ("description", description),
            ("review_text", review_text),
        )
        if value is not None
    ]
    return {
        "record_id": record_id,
        "name": name,
        "address_raw": address_raw,
        "address_hints": {"addr:full": address_raw} if address_raw else {},
        "description": description,
        "review_text": review_text,
        "category_tags": ["tourism=attraction"],
        "coordinates": coordinates,
        "opening_hours_raw": None,
        "field_evidence": field_evidence,
        "issues": list(issues or []),
        "minimum_valid": False,
        "page_url": page_url,
        "page_capture_sha256": "a" * 64,
        "page_capture_path": "raw/pois.html",
        "page_fetched_at": NOW,
        "locator": "ld[0]",
    }


def web_export(
    records,
    *,
    synthetic=True,
    license="SYNTHETIC-TEST-ONLY",
    reuse_status="permitted",
):
    return {
        "schema_version": 1,
        "synthetic": synthetic,
        "source": {
            "source_id": "synthetic-web-source",
            "profile": "synthetic_web_source",
            "source_type": "web_poi",
            "license": license,
            "reuse_status": reuse_status,
            "policy_evidence": [],
        },
        "captures": [],
        "records": records,
    }


def parse(export, *, source_url=PAGE_A):
    return WebPOIAdapter().parse(
        export,
        source_id="synthetic-web-source",
        source_url=source_url,
        license="SYNTHETIC-TEST-ONLY",
        retrieved_at=NOW,
        raw_content_reference="raw/export.json",
        raw_sha256="b" * 64,
    )


def read_jsonl(path: Path):
    text = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# --------------------------------------------------------------------------- #
# adapter: one identity per (page namespace, native anchor)
# --------------------------------------------------------------------------- #


def test_two_hosts_using_the_same_native_id_are_two_entities():
    left = parse(web_export([web_record("1")]), source_url=PAGE_A)[0]
    right = parse(
        web_export([web_record("1", page_url=PAGE_B)]), source_url=PAGE_B
    )[0]

    assert left.source_entity_id == f"{PAGE_A}#1"
    assert right.source_entity_id == f"{PAGE_B}#1"
    assert left.source_entity_id != right.source_entity_id
    assert stable_source_id("web_poi", left.source_entity_id) != stable_source_id(
        "web_poi", right.source_entity_id
    )


def test_relative_at_id_is_namespaced_and_never_a_bare_global_id():
    candidate = parse(web_export([web_record("#poi-1")]))[0]

    assert candidate.source_entity_id == f"{PAGE_A}#poi-1"
    assert candidate.source_entity_id != "#poi-1"
    assert candidate.source_entity_id.startswith(canonical_page_namespace(PAGE_A))
    # The namespace is recorded as a resolvable pointer into the raw export.
    assert candidate.field_paths["identity_namespace"] == "/records/0/page_url"


def test_page_namespace_keeps_path_and_query_and_drops_fragment():
    assert (
        canonical_page_namespace("HTTPS://Example.TEST:443/pois?page=2#chapter-1")
        == "https://example.test/pois?page=2"
    )


def test_identity_is_stable_across_order_and_added_or_removed_records():
    records = [
        web_record("node/1#a", name="Place A"),
        web_record("node/1#b", name="Place B"),
        web_record("node/1#c", name="Place C"),
    ]
    first = {c.name: c.source_entity_id for c in parse(web_export(records))}

    reordered = {
        c.name: c.source_entity_id for c in parse(web_export(list(reversed(records))))
    }
    assert reordered == first

    added = {
        c.name: c.source_entity_id
        for c in parse(web_export(records + [web_record("node/1#d", name="Place D")]))
    }
    assert {name: added[name] for name in first} == first
    assert added["Place D"] not in first.values()

    removed = {c.name: c.source_entity_id for c in parse(web_export([records[1]]))}
    assert removed == {"Place B": first["Place B"]}


def test_name_and_review_edit_keeps_the_same_entity():
    before = parse(
        web_export(
            [
                web_record(
                    "#poi-1",
                    name="Old Name",
                    description="old description",
                    review_text="old review",
                )
            ]
        )
    )[0]
    after = parse(
        web_export(
            [
                web_record(
                    "#poi-1",
                    name="New Name",
                    description="new description",
                    review_text="new review",
                )
            ]
        )
    )[0]

    assert before.source_entity_id == after.source_entity_id == f"{PAGE_A}#poi-1"
    # Identity is not a hash of the mutable text.
    assert "Old%20Name" not in before.source_entity_id
    assert "old" not in before.source_entity_id


def test_absolute_at_id_is_kept_and_namespacing_is_idempotent():
    absolute = "https://places.example.test/place/7#main"
    candidate = parse(web_export([web_record(absolute)]))[0]

    assert candidate.source_entity_id == absolute
    # Re-parsing an already namespaced export must not add a second namespace.
    assert namespaced_entity_id(absolute, page_url=PAGE_B) == absolute


def test_listing_page_reused_as_at_id_is_flagged_not_merged():
    candidates = parse(
        web_export([web_record(PAGE_A, name="First"), web_record(PAGE_A, name="Second")])
    )

    assert len({c.source_entity_id for c in candidates}) == 1
    assert all(
        ReasonCode.INVALID_SOURCE_IDENTITY in c.uncertainty_codes for c in candidates
    )


def test_missing_address_is_flagged_even_with_coordinates():
    candidate = parse(
        web_export(
            [web_record("#poi-1", address_raw=None, coordinates=[10.78, 106.70])]
        )
    )[0]

    assert ReasonCode.MISSING_ADDRESS in candidate.uncertainty_codes
    # Coordinates are still carried as evidence; they just cannot replace the
    # address.
    assert candidate.coordinates == (10.78, 106.70)
    assert candidate.geometry_kind == "point"


def test_no_page_namespace_fails_closed_instead_of_emitting_a_bare_id():
    candidate = parse(
        web_export([web_record("1", page_url="")]), source_url=""
    )[0]

    assert candidate.source_entity_id == ""
    assert ReasonCode.INVALID_SOURCE_IDENTITY in candidate.uncertainty_codes


# --------------------------------------------------------------------------- #
# acquisition CLI: the gate holds for direct (non-runner) exports too
# --------------------------------------------------------------------------- #


def test_missing_address_is_never_accepted_through_the_acquisition_cli(tmp_path):
    export_path = tmp_path / "export.json"
    write_json(
        export_path,
        web_export(
            [
                web_record("1", coordinates=[10.78, 106.70]),
                web_record("2", address_raw=None, coordinates=[10.79, 106.71]),
            ]
        ),
    )
    manifest = write_manifest(
        tmp_path / "manifest.json",
        [
            {
                "source_id": "synthetic-web-source",
                "source_type": "web_poi",
                "source_url": PAGE_A,
                "license": "SYNTHETIC-TEST-ONLY",
                "retrieved_at": NOW,
                "export_path": str(export_path),
                "synthetic": True,
            }
        ],
    )
    mapping = write_mapping(
        tmp_path / "mapping.json",
        default_categories(),
        {
            "synthetic-web-source": {
                "synthetic": True,
                "districts": {},
                "category_map": {"tourism=attraction": "attraction"},
                "entities": {
                    f"web_poi/{PAGE_A}#1": entity_review(),
                    f"web_poi/{PAGE_A}#2": entity_review(),
                },
            }
        },
    )
    out = tmp_path / "out"
    code = cli.main(
        [
            "--manifest",
            str(manifest),
            "--mapping",
            str(mapping),
            "--out",
            str(out),
            "--now",
            NOW,
        ]
    )
    assert code == 0

    accepted = read_jsonl(out / "accepted.jsonl")
    quarantine = read_jsonl(out / "quarantine.jsonl")
    assert [row["id"] for row in accepted] == [
        stable_source_id("web_poi", f"{PAGE_A}#1")
    ]
    assert [row["source_entity_id"] for row in quarantine] == [f"{PAGE_A}#2"]
    assert "missing_address" in quarantine[0]["reason_codes"]


# --------------------------------------------------------------------------- #
# social runner: same rule, applied before the export is written
# --------------------------------------------------------------------------- #


def runner_profile(**overrides):
    values = dict(
        name="synthetic_jsonld_source",
        source_id="synthetic-web-source",
        dataset="social_web_identity_test",
        host="example.test",
        allow_hosts=("example.test",),
        start_urls=("https://example.test/pois",),
        extractor="jsonld_v1",
        category_tags=("schema:museum",),
        license="SYNTHETIC-TEST-ONLY",
        reuse_status="permitted",
        notes="synthetic fixture",
        max_content_urls=4,
    )
    values.update(overrides)
    return SourceProfile(**values)


def extracted(
    record_id,
    *,
    page_url="https://example.test/pois",
    name="Synthetic Museum",
    address_raw="1 Test Street, District 1",
    description="Synthetic narrative.",
    coordinates=None,
    issues=None,
):
    return ExtractedRecord(
        record_id=record_id,
        name=name,
        address_raw=address_raw,
        description=description,
        review_text=None,
        category_tags=["schema:museum"],
        coordinates=coordinates,
        opening_hours_raw=None,
        field_evidence=[evidence("name", name, page_url=page_url)],
        page_url=page_url,
        page_capture_sha256="a" * 64,
        page_capture_path="raw/pois.html",
        page_fetched_at=NOW,
        locator="ld[0]",
        issues=list(issues or []),
    )


def test_runner_namespaces_identity_per_page_and_requires_address():
    profile = runner_profile()
    extraction = ExtractionResult(
        records=[
            extracted("pois#chapter-1"),
            extracted("pois#chapter-1", page_url="https://example.test/pois/page-2"),
            extracted("pois#chapter-1", address_raw=None, coordinates=(10.7, 106.7)),
        ],
        errors=[],
    )

    records, counts = _normalize_records(profile, extraction)

    assert records[0]["record_id"] == "https://example.test/pois#pois#chapter-1"
    assert (
        records[1]["record_id"]
        == "https://example.test/pois/page-2#pois#chapter-1"
    )
    assert records[0]["record_id"] != records[1]["record_id"]
    # Re-applying the namespace to an already namespaced id is a no-op, so the
    # export can be re-parsed without prefixing twice.
    assert (
        namespaced_entity_id(records[0]["record_id"], page_url="https://other.test/x")
        == records[0]["record_id"]
    )
    assert records[0]["minimum_valid"] is True
    assert records[2]["minimum_valid"] is False
    assert "missing_address" in records[2]["issues"]
    assert records[2]["coordinates"] == [10.7, 106.7]
    assert counts["missing_address"] == 1
    assert counts["minimum_valid"] == 2


JSONLD_PAGE = """
<main>
<script type="application/ld+json">
{"@context": "https://schema.org", "@graph": [
  {"@type": "Museum", "@id": "https://example.test/place/7",
   "name": "Museum Seven", "description": "Narrative seven.",
   "address": {"streetAddress": "7 C Street", "addressLocality": "District 1"}},
  {"@type": "Museum", "@id": "#poi-1",
   "name": "Museum Anchor", "description": "Narrative anchor.",
   "address": {"streetAddress": "8 D Street", "addressLocality": "District 1"}},
  {"@type": "Museum", "@id": "#poi-2",
   "name": "Museum Coordinates Only", "description": "Narrative without address.",
   "geo": {"latitude": 10.78, "longitude": 106.70}}
]}
</script>
</main>
"""


def seed_capture(tmp_path, *, page_url, body):
    """Write one exact-byte capture plus a verified offline index."""

    seed = tmp_path / "seed"
    raw_dir = seed / "raw"
    raw_dir.mkdir(parents=True)
    payload = body.encode("utf-8")
    digest = sha256_bytes(payload)
    name = f"pois__{digest[:12]}.html"
    (raw_dir / name).write_bytes(payload)
    index_path = seed / "capture_index.json"
    write_json(
        index_path,
        {
            "schema_version": 1,
            "profile": "synthetic_jsonld_source",
            "entries": [
                {
                    "kind": "content",
                    "url": page_url,
                    "final_url": page_url,
                    "status": 200,
                    "content_type": "text/html; charset=utf-8",
                    "fetched_at": NOW,
                    "elapsed_ms": 1,
                    "bytes": len(payload),
                    "sha256": digest,
                    "redirect_chain": [],
                    "attempts": 1,
                    "file": f"raw/{name}",
                }
            ],
        },
    )
    return index_path


def test_runner_export_and_adapter_agree_and_never_accept_missing_address(tmp_path):
    profile = runner_profile()
    index_path = seed_capture(
        tmp_path, page_url="https://example.test/pois", body=JSONLD_PAGE
    )

    result = collect_profile(
        profile, tmp_path / "out", capture_index=index_path, synthetic=True
    )
    assert result.report["counts"]["imported"] == 0
    assert result.report["counts"]["minimum_valid"] == 2
    assert result.report["counts"]["missing_address"] == 1

    export = json.loads(Path(result.export_path).read_text(encoding="utf-8"))
    ids = {record["name"]: record["record_id"] for record in export["records"]}
    page = "https://example.test/pois"
    assert ids["Museum Seven"] == "https://example.test/place/7"
    assert ids["Museum Anchor"] == f"{page}#poi-1"
    assert ids["Museum Coordinates Only"] == f"{page}#poi-2"

    # Re-parsing the export through the adapter reproduces the same identities
    # (namespacing is applied exactly once) and keeps the address gate closed.
    candidates = parse(export, source_url=page)
    assert [c.source_entity_id for c in candidates] == [
        ids[record["name"]] for record in export["records"]
    ]
    by_name = {c.name: c for c in candidates}
    assert ReasonCode.MISSING_ADDRESS in by_name[
        "Museum Coordinates Only"
    ].uncertainty_codes
    assert ReasonCode.MISSING_ADDRESS not in by_name["Museum Anchor"].uncertainty_codes
