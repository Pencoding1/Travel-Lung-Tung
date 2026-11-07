"""Wikivoyage (CC BY-SA 4.0) profile, extractor and licence-obligation tests.

Everything here is offline. The two article fixtures are hand-written for these
tests (``fixtures/wikivoyage_hcmc_*.html``) and are *not* captures of any live
page; the fake transport never opens a socket, so no request leaves the process.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from crawler_service.app.social_ingest import cli
from crawler_service.app.social_ingest.extract import (
    extract_wikivoyage_listings,
    page_slug,
)
from crawler_service.app.social_ingest.profiles import (
    REUSE_PERMITTED,
    SourceProfile,
    gate_for_profile,
    get_profile,
    list_profiles,
    policy_allows_reuse,
)
from crawler_service.app.social_ingest.runner import collect_profile

from helpers import NOW, FakeTransport, fetcher_for, html_response, run_acquisition

FIXTURES = Path(__file__).parent / "fixtures"
PAGE_SEE_URL = "https://en.wikivoyage.org/wiki/Ho_Chi_Minh_City"
PAGE_EAT_URL = "https://en.wikivoyage.org/wiki/Ho_Chi_Minh_City/Eat"

ROBOTS = (
    "User-agent: *\n"
    "Disallow: /w/\n"
    "Disallow: /api/\n"
    "Disallow: /Special:\n"
)

FROM = dict(
    capture_sha256="b" * 64,
    capture_path="raw/wiki_ho_chi_minh_city__bbbbbbbbbbbb.html",
    fetched_at=NOW,
)


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def profile():
    return get_profile("wikivoyage_en_hcmc")


def two_page_profile():
    return replace(profile(), start_urls=(PAGE_SEE_URL, PAGE_EAT_URL))


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path: Path):
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def live_run(tmp_path):
    pages = two_page_profile()
    transport = FakeTransport(
        {
            "https://en.wikivoyage.org/robots.txt": html_response(
                ROBOTS, content_type="text/plain"
            ),
            PAGE_SEE_URL: html_response(fixture("wikivoyage_hcmc_see.html")),
            PAGE_EAT_URL: html_response(fixture("wikivoyage_hcmc_eat.html")),
        }
    )
    result = collect_profile(
        pages, tmp_path / "run", fetcher=fetcher_for(transport, ("en.wikivoyage.org",))
    )
    return pages, transport, result


# --- declared profile -------------------------------------------------------


def test_profile_declares_cc_by_sa_with_mandatory_attribution():
    declared = profile()
    assert declared.license == "CC-BY-SA-4.0"
    assert declared.reuse_status == REUSE_PERMITTED
    assert declared.attribution_required is True
    assert declared.share_alike is True
    assert "CC BY-SA 4.0" in declared.attribution_text
    assert declared.extractor == "wikivoyage_listings_v1"
    assert declared.host == "en.wikivoyage.org"
    assert declared.allow_hosts == ("en.wikivoyage.org",)
    assert declared.start_urls == (PAGE_SEE_URL,)
    # Only the plain article path is declared, never /w/ or /api/.
    assert "/wiki/" in declared.start_urls[0]
    assert all("/w/" not in url and "/api/" not in url for url in declared.start_urls)
    assert declared.name in list_profiles()


def test_profile_reuse_passes_the_gate_only_because_it_is_permitted():
    declared = profile()
    assert policy_allows_reuse(declared) is True
    assert gate_for_profile(declared) is None


def test_profile_review_evidence_exists_in_the_repository():
    declared = profile()
    assert declared.policy_evidence
    repo_root = Path(__file__).resolve().parents[2]
    for reference in declared.policy_evidence:
        assert (repo_root / reference).is_file(), reference
    assert "not permitted" not in declared.notes.lower()
    # The notes must state that the raw policy capture is still outstanding.
    assert "no raw policy capture exists yet" in declared.notes


def test_attribution_required_profile_without_notice_is_refused():
    with pytest.raises(ValueError, match="attribution_text"):
        SourceProfile(
            name="synthetic_missing_attribution",
            source_id="synthetic-missing-attribution",
            dataset="social_web_oc050_test",
            host="example.test",
            allow_hosts=("example.test",),
            start_urls=("https://example.test/poi",),
            extractor="wikivoyage_listings_v1",
            category_tags=(),
            license="CC-BY-SA-4.0",
            reuse_status=REUSE_PERMITTED,
            attribution_required=True,
            attribution_text="   ",
        )


def test_unknown_extractor_is_still_refused():
    with pytest.raises(ValueError, match="unknown extractor"):
        replace(profile(), extractor="wikivoyage_guessed_v9")


# --- extraction -------------------------------------------------------------


def see_records():
    return extract_wikivoyage_listings(
        fixture("wikivoyage_hcmc_see.html"),
        page_url=PAGE_SEE_URL,
        page_slug=page_slug(PAGE_SEE_URL),
        **FROM,
    )


def test_each_listing_is_extracted_from_its_own_block():
    result = see_records()
    assert [record.name for record in result.records] == [
        "War Remnants Museum",
        "Notre Dame Cathedral (fixture)",
        "Ben Thanh Market (fixture)",
        "Bitexco Deck (fixture)",
    ]
    first, second, third, fourth = result.records
    assert first.address_raw == "28 Vo Van Tan, District 3, Ho Chi Minh City"
    assert "Chi Minh" not in first.description
    # No block ever borrows the address or the description of its neighbour.
    assert second.address_raw is None
    assert "District 3" not in second.description
    assert third.description is None
    assert third.address_raw.startswith("Le Loi")
    assert fourth.address_raw.startswith("2 Hai Trieu")


def test_missing_address_and_description_are_flagged_not_invented():
    first, second, third, fourth = see_records().records
    assert first.issues == []
    assert second.issues == ["missing_address"]
    assert third.issues == ["missing_description"]
    assert fourth.issues == ["unstable_record_anchor"]
    assert fourth.name == "Bitexco Deck (fixture)"


def test_geo_markers_are_parsed_only_when_they_parse():
    first, second, third, fourth = see_records().records
    assert first.coordinates == (10.77917, 106.69250)  # listing-geo text form
    assert second.coordinates == (10.77972, 106.69903)  # data-lat/data-lon form
    assert third.coordinates is None  # no marker at all
    assert fourth.coordinates is None  # marker present but unparsable


def test_unparsable_marker_is_reported_as_an_extraction_error():
    result = see_records()
    assert result.errors
    error = result.errors[0]
    assert error["locator"].startswith("div.vcard[3]")
    assert "invalid_coordinates" in error["error"]
    assert "top floor" in error["error"]


def test_identity_comes_from_the_authored_anchor_not_the_index():
    slug = "wiki/ho_chi_minh_city"
    records = see_records().records
    assert records[0].record_id == f"{slug}#war-remnants-museum"
    assert records[1].record_id == f"{slug}#notre-dame-cathedral"
    assert records[2].record_id == f"{slug}#ben-thanh-market"
    assert records[3].record_id is None
    assert "unstable_record_anchor" in records[3].issues
    assert all("div.vcard[" not in (record.record_id or "") for record in records)


def test_provenance_is_attached_to_every_extracted_field():
    for record in see_records().records:
        assert record.page_url == PAGE_SEE_URL
        assert record.page_fetched_at == NOW
        assert record.page_capture_sha256 == "b" * 64
        assert record.page_capture_path == FROM["capture_path"]
        assert record.field_evidence
        for item in record.field_evidence:
            assert item["source_url"] == PAGE_SEE_URL
            assert item["fetched_at"] == NOW
            assert item["raw_sha256"] == "b" * 64
            assert item["raw_capture_path"] == FROM["capture_path"]
            assert item["locator"].startswith(record.locator)
            assert item["value"]


def test_second_article_marks_missing_name_and_keeps_address_separate():
    eat = fixture("wikivoyage_hcmc_eat.html")
    result = extract_wikivoyage_listings(
        eat,
        page_url=PAGE_EAT_URL,
        page_slug=page_slug(PAGE_EAT_URL),
        **FROM,
    )
    assert [record.name for record in result.records] == [
        "Banh Mi Huynh Hoa (fixture)",
        "Quan An Ngon (fixture)",
        None,
    ]
    assert result.records[1].address_raw is None
    assert result.records[1].coordinates == (10.77611, 106.69163)
    assert result.records[2].name is None
    assert "missing_name" in result.records[2].issues
    assert result.records[2].address_raw.startswith("99 Vo Thi Sau")


# --- export, licence obligation and the existing gate -----------------------


def test_export_carries_licence_attribution_and_the_address_gate(tmp_path):
    _, transport, result = live_run(tmp_path)
    # The fake transport is the only network surface; the declared pages are the
    # only URLs it was ever asked for.
    assert transport.calls == [
        "https://en.wikivoyage.org/robots.txt",
        PAGE_SEE_URL,
        PAGE_EAT_URL,
    ]

    export = read_json(result.export_path)
    assert export["synthetic"] is False
    source = export["source"]
    assert source["source_id"] == "wikivoyage-en-hcmc"
    assert source["license"] == "CC-BY-SA-4.0"
    assert source["reuse_status"] == "permitted"
    assert source["attribution_required"] is True
    assert source["attribution"]["share_alike"] is True
    assert source["attribution"]["source_url"] == PAGE_SEE_URL
    assert "CC BY-SA 4.0" in source["attribution"]["text"]

    for record in export["records"]:
        assert record["attribution"]["license"] == "CC-BY-SA-4.0"
        assert record["attribution"]["text"] == source["attribution"]["text"]
        assert record["attribution"]["source_url"] == record["page_url"]

    counts = result.report["counts"]
    assert counts["content_pages"] == 2
    assert counts["extracted_records"] == 7
    # r1, r5 and the unanchored r4 carry name+address+description; r4 is still
    # refused later because its identity is unstable.
    assert counts["minimum_valid"] == 3
    assert counts["missing_address"] == 2
    assert counts["missing_description"] == 1
    assert counts["missing_name"] == 1
    assert counts["unstable_identity"] == 1
    assert counts["imported"] == 0
    assert result.report["policy"]["attribution"]["share_alike"] is True
    assert any("attribution" in line for line in result.report["limitations"])

    manifest = read_json(result.manifest_path)
    assert manifest["sources"][0]["license"] == "CC-BY-SA-4.0"
    assert manifest["sources"][0]["attribution"]["text"] == source["attribution"]["text"]


def test_missing_address_stays_minimum_valid_false_without_inventing_one(tmp_path):
    _, _, result = live_run(tmp_path)
    export = read_json(result.export_path)
    by_name = {record["name"]: record for record in export["records"]}
    without_address = by_name["Notre Dame Cathedral (fixture)"]
    assert without_address["address_raw"] is None
    assert without_address["address_hints"] == {}
    assert without_address["minimum_valid"] is False
    assert "missing_address" in without_address["issues"]
    # Coordinates are present, and are explicitly NOT accepted as an address.
    assert without_address["coordinates"] == [10.77972, 106.69903]


def test_offline_replay_reproduces_the_export_byte_for_byte(tmp_path):
    pages, _, live = live_run(tmp_path)
    replay = collect_profile(pages, tmp_path / "replay", capture_index=live.index_path)
    assert replay.export_path.read_bytes() == live.export_path.read_bytes()
    assert replay.report["mode"] == "offline_replay"
    assert replay.report["counts"] == live.report["counts"]


def test_acquisition_keeps_cc_by_sa_and_quarantines_missing_address(tmp_path):
    _, _, result = live_run(tmp_path)
    out = tmp_path / "acquisition"
    run = run_acquisition(result.manifest_path, result.mapping_path, out)
    # Nothing is accepted: no entity review exists and no listing is categorised
    # yet (category assignment is a review decision for Wikivoyage sections).
    assert run.summary["totals"]["accepted"] == 0

    candidates = read_jsonl(out / "candidates.jsonl")
    assert len(candidates) == 7
    for candidate in candidates:
        assert candidate["license"] == "CC-BY-SA-4.0"
        assert "policy_unverified" not in candidate["uncertainty_codes"]

    quarantine = read_jsonl(out / "quarantine.jsonl")
    reasons = {row["source_entity_id"]: row["reason_codes"] for row in quarantine}
    missing = [
        entity_id for entity_id, codes in reasons.items() if "missing_address" in codes
    ]
    assert len(missing) == 2
    assert all(entity_id.startswith(PAGE_SEE_URL + "#") or entity_id.startswith(PAGE_EAT_URL + "#")
               for entity_id in missing)

    # The block with no authored anchor is refused outright, not quarantined.
    rejected = [
        row for row in read_jsonl(out / "decisions.jsonl") if row["outcome"] == "rejected"
    ]
    assert len(rejected) == 1
    assert rejected[0]["reason_codes"] == ["invalid_source_identity"]


def test_vietnam_travel_remains_blocked_next_to_wikivoyage():
    """Adding a permitted source must not loosen the restrictive one."""

    blocked = gate_for_profile(get_profile("vietnam_travel_hcmc7"))
    assert blocked is not None
    assert blocked.reason == "license_reuse_not_permitted"
    assert policy_allows_reuse(profile()) is True


def test_cli_list_exposes_the_attribution_obligation(capsys, monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[2])
    assert cli.main(["list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    wikivoyage = listed["wikivoyage_en_hcmc"]
    assert wikivoyage["license"] == "CC-BY-SA-4.0"
    assert wikivoyage["reuse_status"] == "permitted"
    assert wikivoyage["attribution_required"] is True
    assert wikivoyage["share_alike"] is True
    # The restrictive source keeps its own status in the same listing.
    assert listed["vietnam_travel_hcmc7"]["reuse_status"] == "not_permitted"


@pytest.mark.parametrize(
    "profile_name,expected_slug",
    [
        ("wikivoyage_en_hcmc", "Ho_Chi_Minh_City"),
        ("wikivoyage_en_danang", "Da_Nang"),
        ("wikivoyage_en_hoian", "Hoi_An"),
        ("wikivoyage_en_hue", "Hue"),
        ("wikivoyage_en_dalat", "Da_Lat"),
        ("wikivoyage_en_hanoi", "Hanoi"),
    ],
)
def test_multi_city_wikivoyage_profiles_declare_permitted_cc_by_sa(
    profile_name: str, expected_slug: str
):
    declared = get_profile(profile_name)
    assert declared.license == "CC-BY-SA-4.0"
    assert declared.reuse_status == REUSE_PERMITTED
    assert declared.attribution_required is True
    assert declared.share_alike is True
    assert "CC BY-SA 4.0" in declared.attribution_text
    assert declared.extractor == "wikivoyage_listings_v1"
    assert declared.host == "en.wikivoyage.org"
    assert declared.allow_hosts == ("en.wikivoyage.org",)
    assert declared.start_urls == (f"https://en.wikivoyage.org/wiki/{expected_slug}",)
    assert all("/w/" not in url and "/api/" not in url for url in declared.start_urls)
    assert policy_allows_reuse(declared) is True
    assert gate_for_profile(declared) is None

