"""End-to-end pipeline and CLI regression tests (all fixtures SYNTHETIC)."""

import json
import sys
from pathlib import Path

import pytest

from crawler_service.app.acquisition import cli
from crawler_service.app.acquisition.jsonptr import resolve_pointer
from crawler_service.app.acquisition.resolution import ConfigError

from acquisition_helpers import (
    coord_claim,
    default_categories,
    entities_for,
    entity_review,
    osm_node,
    osm_relation,
    osm_way,
    reviewed_source,
    run,
    wikidata_entity,
    write_manifest,
    write_mapping,
    write_osm_export,
    write_wikidata_export,
)


def read_jsonl(path: Path):
    text = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def source_entry(source_id, source_type, export_path, synthetic=True):
    return {
        "source_id": source_id,
        "source_type": source_type,
        "source_url": f"file://{Path(export_path).name}",
        "license": "ODbL-1.0" if source_type == "osm" else "CC0-1.0",
        "retrieved_at": "2026-10-15T00:00:00Z",
        "export_path": str(export_path),
        "synthetic": synthetic,
    }


def setup_run(tmp_path):
    export = write_osm_export(
        tmp_path / "osm.json",
        [
            osm_node(1, 10.0, 106.0, name="Accepted Cafe", amenity="cafe"),
            osm_node(2, 10.1, 106.1, name="Unknown Category", amenity="nightclub"),
            osm_way(3, center=(10.2, 106.2), name="Review Way", tourism="attraction"),
            osm_relation(4, name="Review Relation", tourism="attraction"),
        ],
    )
    manifest = write_manifest(tmp_path / "manifest.json", [source_entry("osm-test", "osm", export)])
    mapping = write_mapping(
        tmp_path / "mapping.json",
        default_categories(),
        {"osm-test": reviewed_source(entities=entities_for("osm/node/1", "osm/node/2"))},
    )
    return manifest, mapping, export


def test_end_to_end_dry_run_outputs_and_counts(tmp_path):
    manifest, mapping, _ = setup_run(tmp_path)
    out = tmp_path / "out"
    result = run(manifest, mapping, out)

    assert result.summary["live_ingestion"] is False
    assert result.summary["limitations"]["cross_source_equivalence"] == "unsupported"
    totals = result.summary["totals"]
    assert totals == {
        "candidates": 4, "accepted": 1, "rejected": 0, "duplicate": 0,
        "requires_review": 3, "accepted_durable": 1, "quarantine_durable": 3,
    }

    for name in ("raw", "candidates", "decisions", "accepted", "quarantine", "summary"):
        assert result.outputs[name].is_file()
    assert (out / "ledger.jsonl").is_file() and (out / "state.json").is_file()

    accepted = read_jsonl(out / "accepted.jsonl")
    assert len(accepted) == 1
    row = accepted[0]
    assert "categories" not in row
    assert row["poi_categories"] == [
        {"id": "cafe", "name": "Cafe", "context": "Coffee shops and cafes"}
    ]
    for key in ("id", "name", "latitude", "longitude", "address", "poi_categories"):
        assert key in row

    raw = read_jsonl(out / "raw.jsonl")
    assert len(raw) == 4
    assert all(len(item["sha256"]) == 64 for item in raw)
    assert all(item["collection_status"] == "obtained" for item in raw)
    assert all("source_entity_id" in item["extraction_metadata"] for item in raw)

    provenance = result.summary["provenance"]
    assert len(provenance) == 1
    only = next(iter(provenance.values()))
    assert only["mapping"]["manifest_sha256"] == result.summary["policy_hash"]


def test_json_pointers_in_output_resolve_against_raw_export(tmp_path):
    manifest, mapping, export = setup_run(tmp_path)
    out = tmp_path / "out"
    run(manifest, mapping, out)
    document = json.loads(Path(export).read_text(encoding="utf-8"))
    raw = read_jsonl(out / "raw.jsonl")
    for row in raw:
        entity_id = row["extraction_metadata"]["source_entity_id"]
        if not entity_id:
            continue
        name_pointer = row["extraction_metadata"]["field_paths"]["name"]
        assert resolve_pointer(document, name_pointer)


def test_poi_round_trip_preserves_categories_if_import_safe(tmp_path):
    manifest, mapping, _ = setup_run(tmp_path)
    out = tmp_path / "out"
    run(manifest, mapping, out)
    row = read_jsonl(out / "accepted.jsonl")[0]

    poi_root = Path(__file__).resolve().parents[2] / "POI_service"
    if str(poi_root) not in sys.path:
        sys.path.insert(0, str(poi_root))
    try:
        from app.core.domain.graph_entities import POI  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"POI domain model not importable: {exc}")

    model = POI.model_validate(row)
    assert model.model_dump()["poi_categories"] == row["poi_categories"]
    assert model.poi_categories[0].id == "cafe"
    assert model.poi_categories[0].name == "Cafe"
    assert model.poi_categories[0].context


def test_duplicate_rerun_is_idempotent_and_appends_ledger(tmp_path):
    manifest, mapping, _ = setup_run(tmp_path)
    out = tmp_path / "out"
    first = run(manifest, mapping, out)
    accepted_first = read_jsonl(out / "accepted.jsonl")
    blobs_first = sorted(p.name for p in (out / "raw").iterdir())

    second = run(manifest, mapping, out)
    assert {d["outcome"] for d in read_jsonl(out / "decisions.jsonl")} == {"duplicate"}
    assert read_jsonl(out / "accepted.jsonl") == accepted_first
    assert sorted(p.name for p in (out / "raw").iterdir()) == blobs_first
    assert second.summary["totals"]["duplicate"] == second.summary["totals"]["candidates"]
    assert first.summary["run_id"] != ""

    ledger = read_jsonl(out / "ledger.jsonl")
    assert len(ledger) == 2  # append-only, previous decision not erased


def test_unchanged_entity_plus_new_entity_does_not_conflict(tmp_path):
    manifest, mapping, export = setup_run(tmp_path)
    out = tmp_path / "out"
    run(manifest, mapping, out)

    # Same policy; the export gains an unrelated new entity, so the existing
    # unchanged entity must be a duplicate, never a conflict.
    write_osm_export(
        export,
        [
            osm_node(1, 10.0, 106.0, name="Accepted Cafe", amenity="cafe"),
            osm_node(9, 10.9, 106.9, name="Newly Added Cafe", amenity="cafe"),
        ],
    )
    run(manifest, mapping, out)

    decisions = read_jsonl(out / "decisions.jsonl")
    assert not any("conflicting_update" in d["reason_codes"] for d in decisions)
    outcomes = sorted(d["outcome"] for d in decisions)
    assert outcomes == ["duplicate", "requires_review"]
    accepted_ids = {row["id"] for row in read_jsonl(out / "accepted.jsonl")}
    assert len(accepted_ids) == 1


def test_reordered_export_is_duplicate(tmp_path):
    manifest, mapping, export = setup_run(tmp_path)
    out = tmp_path / "out"
    run(manifest, mapping, out)
    ids_before = sorted(row["id"] for row in read_jsonl(out / "accepted.jsonl"))

    write_osm_export(
        export,
        [
            osm_relation(4, name="Review Relation", tourism="attraction"),
            osm_way(3, center=(10.2, 106.2), name="Review Way", tourism="attraction"),
            osm_node(2, 10.1, 106.1, name="Unknown Category", amenity="nightclub"),
            osm_node(1, 10.0, 106.0, name="Accepted Cafe", amenity="cafe"),
        ],
    )
    run(manifest, mapping, out)
    assert {d["outcome"] for d in read_jsonl(out / "decisions.jsonl")} == {"duplicate"}
    assert sorted(row["id"] for row in read_jsonl(out / "accepted.jsonl")) == ids_before


def test_policy_update_category_change_keeps_stable_id(tmp_path):
    manifest, mapping, _ = setup_run(tmp_path)
    out = tmp_path / "out"
    run(manifest, mapping, out)
    id_before = read_jsonl(out / "accepted.jsonl")[0]["id"]

    mapping2 = write_mapping(
        tmp_path / "mapping2.json",
        default_categories(),
        {
            "osm-test": reviewed_source(
                category_map={"amenity=cafe": "attraction", "tourism=attraction": "attraction"},
                entities=entities_for("osm/node/1", "osm/node/2"),
            )
        },
    )
    run(manifest, mapping2, out)
    accepted = read_jsonl(out / "accepted.jsonl")
    assert len(accepted) == 1
    assert accepted[0]["id"] == id_before  # same stable id
    assert accepted[0]["poi_categories"][0]["id"] == "attraction"

    decisions = read_jsonl(out / "decisions.jsonl")
    updated = [
        d for d in decisions
        if d["candidate_id"] == id_before and "policy_re_evaluated" in d["reason_codes"]
    ]
    assert updated and updated[0]["prior_outcome"] == "accepted"
    assert updated[0]["outcome"] == "accepted"

    state = json.loads((out / "state.json").read_text(encoding="utf-8"))
    entry = state["entries"][id_before]
    assert len(entry["history"]) == 2
    assert entry["history"][0]["category_ids"] == ["cafe"]
    assert entry["history"][1]["category_ids"] == ["attraction"]


def test_reviewer_approval_after_quarantine(tmp_path):
    export = write_osm_export(tmp_path / "osm.json", [osm_node(1, 10.0, 106.0, name="Cafe", amenity="cafe")])
    manifest = write_manifest(tmp_path / "manifest.json", [source_entry("osm-test", "osm", export)])
    out = tmp_path / "out"

    mapping_a = write_mapping(
        tmp_path / "mapping_a.json", default_categories(), {"osm-test": reviewed_source()}
    )
    run(manifest, mapping_a, out)
    assert read_jsonl(out / "accepted.jsonl") == []
    assert any("entity_unreviewed" in d["reason_codes"] for d in read_jsonl(out / "quarantine.jsonl"))

    mapping_b = write_mapping(
        tmp_path / "mapping_b.json",
        default_categories(),
        {"osm-test": reviewed_source(entities=entities_for("osm/node/1"))},
    )
    run(manifest, mapping_b, out)
    accepted = read_jsonl(out / "accepted.jsonl")
    assert len(accepted) == 1
    updated = [d for d in read_jsonl(out / "decisions.jsonl") if "policy_re_evaluated" in d["reason_codes"]]
    assert updated[0]["prior_outcome"] == "requires_review"
    assert updated[0]["outcome"] == "accepted"


def test_conflicting_source_update_is_quarantined(tmp_path):
    manifest, mapping, export = setup_run(tmp_path)
    out = tmp_path / "out"
    run(manifest, mapping, out)
    assert read_jsonl(out / "accepted.jsonl")

    write_osm_export(
        export,
        [
            osm_node(1, 10.99, 106.99, name="Moved Cafe", amenity="cafe"),
            osm_node(2, 10.1, 106.1, name="Unknown Category", amenity="nightclub"),
        ],
    )
    run(manifest, mapping, out)
    quarantine = read_jsonl(out / "quarantine.jsonl")
    assert any("conflicting_update" in row["reason_codes"] for row in quarantine)
    assert read_jsonl(out / "accepted.jsonl") == []


def test_malformed_second_source_preserves_existing_artifacts(tmp_path):
    manifest, mapping, export = setup_run(tmp_path)
    out = tmp_path / "out"
    run(manifest, mapping, out)
    accepted_before = (out / "accepted.jsonl").read_bytes()
    state_before = (out / "state.json").read_bytes()
    blobs_before = sorted(p.name for p in (out / "raw").iterdir())

    bad_export = tmp_path / "bad.json"
    bad_export.write_text("{not valid json", encoding="utf-8")
    manifest_bad = write_manifest(
        tmp_path / "manifest.json",
        [source_entry("osm-test", "osm", export), source_entry("osm-bad", "osm", bad_export)],
    )
    with pytest.raises(ConfigError):
        run(manifest_bad, mapping, out)

    assert (out / "accepted.jsonl").read_bytes() == accepted_before
    assert (out / "state.json").read_bytes() == state_before
    assert sorted(p.name for p in (out / "raw").iterdir()) == blobs_before


@pytest.mark.parametrize("bad_id", ["../evil", "a/b", "a\\b", "c:name", "CON", "", ".."])
def test_invalid_source_id_is_rejected(tmp_path, bad_id):
    export = write_osm_export(tmp_path / "osm.json", [osm_node(1, 10.0, 106.0, name="N")])
    manifest = write_manifest(tmp_path / "manifest.json", [source_entry(bad_id, "osm", export)])
    mapping = write_mapping(tmp_path / "m.json", default_categories(), {"osm-test": reviewed_source()})
    with pytest.raises(ConfigError):
        run(manifest, mapping, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_export_inside_output_directory_is_rejected(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    export = write_osm_export(out / "osm.json", [osm_node(1, 10.0, 106.0, name="N")])
    manifest = write_manifest(tmp_path / "manifest.json", [source_entry("osm-test", "osm", export)])
    mapping = write_mapping(tmp_path / "m.json", default_categories(), {"osm-test": reviewed_source()})
    with pytest.raises(ConfigError):
        run(manifest, mapping, out)


def test_corrupt_state_errors_instead_of_resetting(tmp_path):
    manifest, mapping, _ = setup_run(tmp_path)
    out = tmp_path / "out"
    run(manifest, mapping, out)
    (out / "state.json").write_text(
        json.dumps({"pipeline_version": 999, "entries": {}}), encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        run(manifest, mapping, out)


def test_invalid_mapping_configuration_produces_no_output(tmp_path):
    export = write_osm_export(tmp_path / "osm.json", [osm_node(1, 10.0, 106.0, name="N", amenity="cafe")])
    manifest = write_manifest(tmp_path / "manifest.json", [source_entry("osm-test", "osm", export)])
    mapping = write_mapping(
        tmp_path / "mapping.json",
        default_categories(),
        {"osm-test": reviewed_source(category_map={"amenity=cafe": "ghost"})},
    )
    out = tmp_path / "out"
    with pytest.raises(ConfigError):
        run(manifest, mapping, out)
    assert not out.exists()


def test_top_level_synthetic_excludes_real_counts(tmp_path):
    export = write_osm_export(tmp_path / "osm.json", [osm_node(1, 10.0, 106.0, name="N", amenity="cafe")])
    manifest = write_manifest(
        tmp_path / "manifest.json", [source_entry("osm-test", "osm", export, synthetic=False)], synthetic=True
    )
    mapping = write_mapping(
        tmp_path / "m.json",
        default_categories(),
        {"osm-test": reviewed_source(entities=entities_for("osm/node/1"), synthetic=False)},
    )
    out = tmp_path / "out"
    result = run(manifest, mapping, out)
    assert result.summary["synthetic"] is True
    assert result.summary["totals"]["accepted"] == 1
    assert result.summary["real_expansion_totals"]["accepted"] == 0
    assert read_jsonl(out / "accepted.jsonl")[0]["synthetic"] is True


def test_mixed_synthetic_and_real_totals(tmp_path):
    # Strict dataset/synthetic separation: a manifest mixing synthetic and real
    # sources is a scope violation and must not create a shared state directory.
    syn = write_osm_export(tmp_path / "syn.json", [osm_node(1, 10.0, 106.0, name="S", amenity="cafe")], synthetic=True)
    real = write_osm_export(tmp_path / "real.json", [osm_node(2, 10.1, 106.1, name="R", amenity="cafe")], synthetic=False)
    manifest = write_manifest(
        tmp_path / "manifest.json",
        [source_entry("osm-syn", "osm", syn, synthetic=True), source_entry("osm-real", "osm", real, synthetic=False)],
        synthetic=False,
    )
    mapping = write_mapping(
        tmp_path / "m.json",
        default_categories(),
        {
            "osm-syn": reviewed_source(entities=entities_for("osm/node/1")),
            "osm-real": reviewed_source(entities=entities_for("osm/node/2")),
        },
    )
    out = tmp_path / "out"
    with pytest.raises(ConfigError):
        run(manifest, mapping, out)
    assert not out.exists()


def test_synthetic_to_real_collision_is_isolated(tmp_path):
    syn = write_osm_export(tmp_path / "syn.json", [osm_node(1, 10.0, 106.0, name="S", amenity="cafe")], synthetic=True)
    real = write_osm_export(tmp_path / "real.json", [osm_node(1, 10.0, 106.0, name="S", amenity="cafe")], synthetic=False)
    out = tmp_path / "out"

    manifest_syn = write_manifest(tmp_path / "msyn.json", [source_entry("osm-syn", "osm", syn, synthetic=True)], synthetic=False)
    mapping_syn = write_mapping(
        tmp_path / "msyn_map.json", default_categories(), {"osm-syn": reviewed_source(entities=entities_for("osm/node/1"))}
    )
    run(manifest_syn, mapping_syn, out)
    assert read_jsonl(out / "accepted.jsonl")[0]["synthetic"] is True

    manifest_real = write_manifest(tmp_path / "mreal.json", [source_entry("osm-real", "osm", real, synthetic=False)], synthetic=False)
    mapping_real = write_mapping(
        tmp_path / "mreal_map.json", default_categories(), {"osm-real": reviewed_source(entities=entities_for("osm/node/1"))}
    )
    accepted_before = (out / "accepted.jsonl").read_bytes()
    state_before = (out / "state.json").read_bytes()
    with pytest.raises(ConfigError):
        run(manifest_real, mapping_real, out)
    # The scope mismatch is rejected before any mutation of the synthetic state.
    assert (out / "accepted.jsonl").read_bytes() == accepted_before
    assert (out / "state.json").read_bytes() == state_before
    assert read_jsonl(out / "accepted.jsonl")[0]["synthetic"] is True


def test_malformed_coordinates_are_reviewed_not_crash(tmp_path):
    export = write_wikidata_export(
        tmp_path / "wd.json",
        [wikidata_entity("Q1", labels={"en": "Bad Coord"}, p31=["Q33506"], coordinates=[coord_claim([10.0], {"x": 1})])],
    )
    manifest = write_manifest(tmp_path / "manifest.json", [source_entry("wikidata-test", "wikidata", export)])
    mapping = write_mapping(
        tmp_path / "m.json",
        default_categories(),
        {"wikidata-test": reviewed_source(category_map={"P31=Q33506": "museum"}, entities=entities_for("wikidata/Q1"))},
    )
    result = run(manifest, mapping, tmp_path / "out")
    assert result.summary["totals"]["accepted"] == 0
    assert result.summary["totals"]["requires_review"] == 1


def test_stable_id_survives_taxonomy_change(tmp_path):
    export = write_osm_export(tmp_path / "osm.json", [osm_node(1, 10.0, 106.0, name="Cafe", amenity="cafe")])
    manifest = write_manifest(tmp_path / "manifest.json", [source_entry("osm-test", "osm", export)])
    mapping_a = write_mapping(
        tmp_path / "a.json", default_categories(), {"osm-test": reviewed_source(entities=entities_for("osm/node/1"))}
    )
    mapping_b = write_mapping(
        tmp_path / "b.json",
        default_categories(),
        {"osm-test": reviewed_source(category_map={"amenity=cafe": "attraction"}, entities=entities_for("osm/node/1"))},
    )
    out_a, out_b = tmp_path / "out_a", tmp_path / "out_b"
    run(manifest, mapping_a, out_a)
    run(manifest, mapping_b, out_b)
    assert read_jsonl(out_a / "accepted.jsonl")[0]["id"] == read_jsonl(out_b / "accepted.jsonl")[0]["id"]
    assert read_jsonl(out_a / "accepted.jsonl")[0]["poi_categories"][0]["id"] == "cafe"
    assert read_jsonl(out_b / "accepted.jsonl")[0]["poi_categories"][0]["id"] == "attraction"


def test_cli_returns_zero_and_reports_totals(tmp_path, capsys):
    manifest, mapping, _ = setup_run(tmp_path)
    out = tmp_path / "out"
    code = cli.main(["--manifest", str(manifest), "--mapping", str(mapping), "--out", str(out), "--now", "2026-10-15T00:00:00Z"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok" and payload["totals"]["accepted"] == 1


def test_cli_returns_two_on_invalid_configuration(tmp_path, capsys):
    manifest, mapping, _ = setup_run(tmp_path)
    mapping = write_mapping(
        tmp_path / "bad.json", default_categories(), {"osm-test": reviewed_source(category_map={"amenity=cafe": "ghost"})}
    )
    out = tmp_path / "out"
    code = cli.main(["--manifest", str(manifest), "--mapping", str(mapping), "--out", str(out)])
    assert code == 2
    assert not out.exists()
