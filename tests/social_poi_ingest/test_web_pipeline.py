"""End-to-end web_poi -> existing acquisition quality gate tests (SYNTHETIC)."""

import json
import sys
from pathlib import Path

import pytest

from crawler_service.app.acquisition.jsonptr import resolve_pointer
from crawler_service.app.acquisition.identity import stable_source_id

from helpers import (
    NOW,
    reviewed_entity,
    run_acquisition,
    web_record,
    write_web_run,
)

# T057b: a source entity id is namespaced by the canonical page URL
# ("<page-url>#<native anchor>"), so quarantine/candidate rows carry this form.
PAGE = "https://example.test/pois"
NS_A_A = f"{PAGE}#node/1#a"
NS_A_B = f"{PAGE}#node/1#b"
NS_A_C = f"{PAGE}#node/1#c"


def read_jsonl(path: Path):
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_missing_coordinates_and_policy_quarantine_but_evidence_survives(tmp_path):
    manifest, mapping, export = write_web_run(
        tmp_path,
        [
            web_record(record_id="node/1#a", coordinates=[10.78, 106.70]),
            web_record(
                record_id="node/1#b",
                name="No Coordinate Place",
                address_raw="2 Test Street, District 1",
            ),
            web_record(
                record_id="node/1#c",
                name="No Description Place",
                description=None,
                review_text=None,
                issues=["missing_description"],
            ),
        ],
        entities={
            "web_poi/https://example.test/pois#node/1#a": reviewed_entity(),
            "web_poi/https://example.test/pois#node/1#b": reviewed_entity(),
            "web_poi/https://example.test/pois#node/1#c": reviewed_entity(),
        },
    )
    out = tmp_path / "out"
    result = run_acquisition(manifest, mapping, out)
    assert result.summary["totals"] == {
        "candidates": 3,
        "accepted": 1,
        "rejected": 0,
        "duplicate": 0,
        "requires_review": 2,
        "accepted_durable": 1,
        "quarantine_durable": 2,
    }
    accepted = read_jsonl(out / "accepted.jsonl")
    assert len(accepted) == 1
    accepted_id = accepted[0]["id"]
    # T057b: the source entity id is now namespaced by the canonical page URL
    # ("<page-url>#<native anchor>"), so the derived POI id changes with it.
    assert accepted_id == stable_source_id(
        "web_poi", "https://example.test/pois#node/1#a")
    assert accepted[0]["poi_categories"][0]["id"] == "attraction"

    quarantine = read_jsonl(out / "quarantine.jsonl")
    reasons = {row["source_entity_id"]: row["reason_codes"] for row in quarantine}
    assert "missing_coordinates" in reasons[NS_A_B]
    assert "missing_description" in reasons[NS_A_C]

    # Description/review/field evidence survive both the candidate envelope and
    # the immutable raw index; pointers resolve against the export document.
    candidates = read_jsonl(out / "candidates.jsonl")
    by_entity = {row["source_entity_id"]: row for row in candidates}
    assert by_entity[NS_A_A]["description"].startswith("A synthetic narrative")
    assert by_entity[NS_A_A]["field_evidence"]
    raw = read_jsonl(out / "raw.jsonl")
    metadata = raw[0]["extraction_metadata"]
    assert metadata["field_evidence"]
    assert metadata["description"]
    document = json.loads(Path(export).read_text(encoding="utf-8"))
    for row in candidates:
        assert resolve_pointer(document, row["field_paths"]["name"]) == row["name"]
        assert resolve_pointer(document, row["field_paths"]["field_evidence"])


def test_reorder_and_new_record_keep_stable_ids(tmp_path):
    manifest, mapping, export = write_web_run(
        tmp_path,
        [web_record(record_id="node/1#a", coordinates=[10.78, 106.70])],
        entities={
            "web_poi/https://example.test/pois#node/1#a": reviewed_entity(),
            "web_poi/https://example.test/pois#node/1#b": reviewed_entity(),
        },
    )
    out = tmp_path / "out"
    run_acquisition(manifest, mapping, out)
    first_id = read_jsonl(out / "accepted.jsonl")[0]["id"]

    document = json.loads(Path(export).read_text(encoding="utf-8"))
    document["records"] = [
        web_record(
            record_id="node/1#b",
            name="New Place",
            coordinates=[10.79, 106.71],
        ),
        document["records"][0],
    ]
    Path(export).write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    run_acquisition(manifest, mapping, out)
    accepted = {row["id"] for row in read_jsonl(out / "accepted.jsonl")}
    assert first_id in accepted
    assert len(accepted) == 2
    decisions = read_jsonl(out / "decisions.jsonl")
    outcomes = {row["candidate_id"]: row["outcome"] for row in decisions}
    assert outcomes[first_id] == "duplicate"


def test_review_only_change_does_not_conflict_and_keeps_raw_revisions(tmp_path):
    manifest, mapping, export = write_web_run(
        tmp_path,
        [web_record(record_id="node/1#a", coordinates=[10.78, 106.70], review_text="old review")],
        entities={"web_poi/https://example.test/pois#node/1#a": reviewed_entity()},
    )
    out = tmp_path / "out"
    run_acquisition(manifest, mapping, out)
    first_id = read_jsonl(out / "accepted.jsonl")[0]["id"]
    blobs_before = sorted(path.name for path in (out / "raw").iterdir())

    document = json.loads(Path(export).read_text(encoding="utf-8"))
    document["records"][0]["review_text"] = "new review"
    Path(export).write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    run_acquisition(manifest, mapping, out)

    assert read_jsonl(out / "accepted.jsonl")[0]["id"] == first_id
    assert {row["outcome"] for row in read_jsonl(out / "decisions.jsonl")} == {"duplicate"}
    blobs_after = sorted(path.name for path in (out / "raw").iterdir())
    assert len(blobs_after) == len(blobs_before) + 1  # both raw revisions retained
    assert blobs_before[0] in blobs_after


def test_name_or_address_change_conflicts_without_new_identity(tmp_path):
    manifest, mapping, export = write_web_run(
        tmp_path,
        [web_record(record_id="node/1#a", coordinates=[10.78, 106.70])],
        entities={"web_poi/https://example.test/pois#node/1#a": reviewed_entity()},
    )
    out = tmp_path / "out"
    run_acquisition(manifest, mapping, out)
    first_id = read_jsonl(out / "accepted.jsonl")[0]["id"]

    document = json.loads(Path(export).read_text(encoding="utf-8"))
    document["records"][0]["name"] = "Renamed Place"
    Path(export).write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    run_acquisition(manifest, mapping, out)

    quarantine = read_jsonl(out / "quarantine.jsonl")
    assert quarantine[0]["candidate_id"] == first_id
    assert "conflicting_update" in quarantine[0]["reason_codes"]
    assert read_jsonl(out / "accepted.jsonl") == []


def test_real_unknown_license_is_policy_quarantined_even_with_review(tmp_path):
    manifest, mapping, _ = write_web_run(
        tmp_path,
        [web_record(record_id="node/1#a", coordinates=[10.78, 106.70])],
        synthetic=False,
        license="UNKNOWN",
        reuse_status="not_permitted",
        entities={"web_poi/https://example.test/pois#node/1#a": reviewed_entity()},
    )
    out = tmp_path / "out"
    result = run_acquisition(manifest, mapping, out)
    assert result.summary["totals"]["accepted"] == 0
    assert result.summary["totals"]["requires_review"] == 1
    assert "policy_unverified" in read_jsonl(out / "quarantine.jsonl")[0]["reason_codes"]


def test_unstable_identity_is_rejected_not_indexed(tmp_path):
    manifest, mapping, _ = write_web_run(
        tmp_path,
        [
            web_record(
                record_id=None,
                coordinates=[10.78, 106.70],
                issues=["unstable_record_anchor"],
            )
        ],
        entities={},
    )
    result = run_acquisition(manifest, mapping, tmp_path / "out")
    assert result.summary["totals"]["accepted"] == 0
    assert result.summary["totals"]["rejected"] == 1
    decisions = read_jsonl(tmp_path / "out" / "decisions.jsonl")
    assert decisions[0]["reason_codes"] == ["invalid_source_identity"]


def test_accepted_payload_roundtrips_through_poi_model(tmp_path):
    manifest, mapping, _ = write_web_run(
        tmp_path,
        [web_record(record_id="node/1#a", coordinates=[10.78, 106.70])],
        entities={"web_poi/https://example.test/pois#node/1#a": reviewed_entity()},
    )
    out = tmp_path / "out"
    run_acquisition(manifest, mapping, out)
    row = read_jsonl(out / "accepted.jsonl")[0]

    poi_root = Path(__file__).resolve().parents[2] / "POI_service"
    if str(poi_root) not in sys.path:
        sys.path.insert(0, str(poi_root))
    try:
        from app.core.domain.graph_entities import POI  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"POI domain model not importable: {exc}")
    model = POI.model_validate(row)
    assert model.id == row["id"]
    assert model.poi_categories[0].id == "attraction"
    assert model.address is not None and model.address.city == "Ho Chi Minh City"


def test_web_export_malformed_evidence_fails_before_writing(tmp_path):
    manifest, mapping, export = write_web_run(
        tmp_path,
        [web_record(record_id="node/1#a", coordinates=[10.78, 106.70])],
        entities={"web_poi/https://example.test/pois#node/1#a": reviewed_entity()},
    )
    document = json.loads(Path(export).read_text(encoding="utf-8"))
    document["records"][0]["field_evidence"] = [{"field": "name"}]  # missing provenance keys
    Path(export).write_text(json.dumps(document), encoding="utf-8")
    out = tmp_path / "out"
    from crawler_service.app.acquisition.resolution import ConfigError

    with pytest.raises(ConfigError):
        run_acquisition(manifest, mapping, out)
    assert not out.exists()
