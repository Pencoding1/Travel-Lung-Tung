"""OC-043 acceptance tests for the primary graph-ready adapter."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

import pytest

from app.core.domain.graph_entities import POI
from app.core.utils.primary_snapshot import (
    CHECKSUMS_FILENAME,
    MANIFEST_FILENAME,
    PREPARED_FILENAME,
    REAL_EXPECTATIONS,
    REAL_OUTPUT_DIR,
    REPO_ROOT,
    SnapshotError,
    prepare_snapshot,
    write_plan,
)
from fixtures import (
    FIXTURE_NAMES,
    build_fixture,
    new_scratch_dir,
    read_json,
    refresh_binding,
    rewrite_jsonl,
)


def _rejected(plan_callable) -> str:
    with pytest.raises(SnapshotError) as excinfo:
        plan_callable()
    return excinfo.value.code


def _mutate_fixture(label: str, mutate):
    fixture = build_fixture(new_scratch_dir(label))
    key = mutate(fixture)
    return fixture if key is None else refresh_binding(fixture, key)


def test_real_snapshot_cli_check_passes():
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.core.utils.primary_snapshot",
            "--check",
            "--json",
        ],
        cwd=REPO_ROOT / "POI_service",
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["status"] == "validated"
    assert summary["real"] is True
    assert summary["dataset_class"] == "real_supplied_primary_snapshot"
    assert summary["records"] == 6367
    manifest = summary["manifest"]
    assert manifest["counts"]["input_features"] == 6368
    assert manifest["counts"]["prepared_records"] == 6367
    assert manifest["index_accounting"]["canonical_source_indices"] == 6367
    assert manifest["index_accounting"]["duplicate_source_indices"] == [4859]
    assert manifest["index_accounting"]["covered_source_indices"] == 6368
    assert manifest["index_accounting"]["each_source_index_exactly_once"] is True
    assert manifest["unknowns"] == {
        "collection_time": "UNKNOWN",
        "source_url": "UNKNOWN",
        "license": "UNKNOWN",
        "freshness": "UNKNOWN",
    }
    assert manifest["real_supplied_primary_dataset"] is True
    assert manifest["general_dataset_class_enforcement"] is False
    assert manifest["future_real_synthetic_expansion_write_boundary"] == "T050"


def test_real_plan_preserves_fields_and_validates_every_model(real_plan):
    prepared_path = (
        REPO_ROOT / "data" / "primary_20261016" / "prepared" / "prepared_pois.jsonl"
    )
    prepared = {}
    with prepared_path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            prepared[row["id"]] = row

    assert len(real_plan.records) == 6367
    assert set(record["id"] for record in real_plan.records) == set(prepared)
    duplicate_bound = []
    for record in real_plan.records:
        original = prepared[record["id"]]
        preserved = {key: value for key, value in record.items() if key != "source_metadata"}
        assert preserved == original

        poi = POI.model_validate(record)
        assert poi.source_metadata is not None
        poi.source_metadata.assert_bound_to_poi(record["id"])
        assert poi.source_metadata.input_sha256 == REAL_EXPECTATIONS.files["geojson"].sha256
        assert poi.source_metadata.dataset_namespace == "hcm_primary_geojson"
        assert poi.source_metadata.administrative_scope == "source_snapshot_area_only"
        assert poi.source_metadata.identity_scope == "internal_local_only"
        assert poi.source_metadata.cross_export_matching == "not_guaranteed"
        assert poi.source_metadata.provided_at.isoformat() == "2026-10-16"
        assert poi.source_metadata.collection_time is None
        assert poi.source_metadata.source_url is None
        assert poi.source_metadata.license is None
        assert poi.source_metadata.freshness is None
        if poi.source_metadata.duplicate_source_indices:
            duplicate_bound.append(
                (
                    record["id"],
                    poi.source_metadata.canonical_source_index,
                    poi.source_metadata.duplicate_source_indices,
                )
            )

    assert duplicate_bound == [
        (
            "hcm_primary_geojson_internal:d814b63761322ec0ec055f2e536cf9be",
            4855,
            [4859],
        )
    ]
    assert real_plan.manifest["counts"]["prepared_review_required"] == 411
    assert real_plan.manifest["counts"]["model_validated_records"] == 6367


def test_real_artifact_if_present_matches_plan(real_plan):
    if not REAL_OUTPUT_DIR.is_dir():
        pytest.skip("real graph_ready_v2 artifact has not been generated yet")

    prepared_bytes = (REAL_OUTPUT_DIR / PREPARED_FILENAME).read_bytes()
    manifest_bytes = (REAL_OUTPUT_DIR / MANIFEST_FILENAME).read_bytes()
    checksums_bytes = (REAL_OUTPUT_DIR / CHECKSUMS_FILENAME).read_bytes()

    assert prepared_bytes == real_plan.prepared_bytes
    assert manifest_bytes == real_plan.manifest_bytes
    assert checksums_bytes == real_plan.checksums_bytes

    expected_checksums = {}
    for line in checksums_bytes.decode("utf-8").splitlines():
        digest, name = line.split("  ", 1)
        expected_checksums[name] = digest
    assert expected_checksums[PREPARED_FILENAME] == real_plan.manifest["outputs"][
        PREPARED_FILENAME
    ]["sha256"]
    assert expected_checksums[MANIFEST_FILENAME] == hashlib.sha256(
        real_plan.manifest_bytes
    ).hexdigest()

    lines = prepared_bytes.decode("utf-8").splitlines()
    assert len(lines) == 6367
    for line in lines:
        POI.model_validate(json.loads(line))


def test_real_input_hashes_are_unchanged(real_plan):
    for name, binding in REAL_EXPECTATIONS.files.items():
        path = REPO_ROOT / binding.relative
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == binding.sha256, name


def test_reordered_lineage_joins_by_stable_id():
    fixture = build_fixture(new_scratch_dir("reorder"))
    baseline = prepare_snapshot(fixture.root, fixture.expectations)

    path = fixture.root / FIXTURE_NAMES["lineage"]
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rewrite_jsonl(path, list(reversed(rows)))
    reordered = prepare_snapshot(
        fixture.root, refresh_binding(fixture, "lineage").expectations
    )

    assert reordered.prepared_bytes == baseline.prepared_bytes
    assert reordered.records == baseline.records


def test_full_snapshot_is_deterministic_in_memory(real_plan):
    fresh = prepare_snapshot(REPO_ROOT, REAL_EXPECTATIONS)
    assert fresh.prepared_bytes == real_plan.prepared_bytes
    assert fresh.manifest_bytes == real_plan.manifest_bytes
    assert fresh.checksums_bytes == real_plan.checksums_bytes
    assert fresh.manifest["outputs"][PREPARED_FILENAME]["sha256"] == real_plan.manifest[
        "outputs"
    ][PREPARED_FILENAME]["sha256"]


def test_two_fresh_outputs_are_byte_deterministic():
    first = build_fixture(new_scratch_dir("determinism-a"))
    second = build_fixture(new_scratch_dir("determinism-b"))
    first_plan = prepare_snapshot(first.root, first.expectations)
    second_plan = prepare_snapshot(second.root, second.expectations)

    assert first_plan.prepared_bytes == second_plan.prepared_bytes
    assert first_plan.manifest_bytes == second_plan.manifest_bytes
    assert first_plan.checksums_bytes == second_plan.checksums_bytes
    assert first_plan.manifest["real_supplied_primary_dataset"] is False
    assert first_plan.manifest["synthetic_fixture"] is True
    assert first_plan.manifest["dataset_class"] == "synthetic_fixture"

    out_a = new_scratch_dir("output-a") / "graph_ready"
    out_b = new_scratch_dir("output-b") / "graph_ready"
    write_plan(first_plan, out_a)
    write_plan(second_plan, out_b)
    for name in (PREPARED_FILENAME, MANIFEST_FILENAME, CHECKSUMS_FILENAME):
        assert (out_a / name).read_bytes() == (out_b / name).read_bytes()


def test_existing_destination_is_never_modified():
    fixture = build_fixture(new_scratch_dir("existing-destination"))
    plan = prepare_snapshot(fixture.root, fixture.expectations)
    destination = new_scratch_dir("existing-output")
    sentinel = destination / "keep.txt"
    sentinel.write_bytes(b"do-not-touch")
    before = sorted((path.name, path.read_bytes()) for path in destination.iterdir())

    with pytest.raises(SnapshotError) as excinfo:
        write_plan(plan, destination)
    assert excinfo.value.code == "output_exists"
    after = sorted((path.name, path.read_bytes()) for path in destination.iterdir())
    assert after == before


def test_synthetic_plan_cannot_write_the_real_destination():
    fixture = build_fixture(new_scratch_dir("real-destination-guard"))
    plan = prepare_snapshot(fixture.root, fixture.expectations)
    existed = REAL_OUTPUT_DIR.exists()
    with pytest.raises(SnapshotError) as excinfo:
        write_plan(plan, REAL_OUTPUT_DIR)
    assert excinfo.value.code == "output_not_allowed"
    assert REAL_OUTPUT_DIR.exists() is existed


def test_rejects_bad_input_hash_before_any_write():
    fixture = build_fixture(new_scratch_dir("bad-hash"))
    geojson = fixture.root / FIXTURE_NAMES["geojson"]
    mutated = bytearray(geojson.read_bytes())
    mutated[-1] = mutated[-1] ^ 0xFF
    geojson.write_bytes(bytes(mutated))
    destination = new_scratch_dir("bad-hash-output") / "never"
    assert _rejected(
        lambda: prepare_snapshot(fixture.root, fixture.expectations)
    ) == "input_hash_mismatch"
    assert not destination.exists()


def test_rejects_duplicate_json_keys():
    fixture = build_fixture(new_scratch_dir("duplicate-json-key"))
    path = fixture.root / FIXTURE_NAMES["prepared"]
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0][:-1] + ',"id":"duplicate"}'
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    fixture = refresh_binding(fixture, "prepared")
    assert _rejected(lambda: prepare_snapshot(fixture.root, fixture.expectations)) in {
        "invalid_json",
        "invalid_jsonl",
    }


def test_rejects_nonfinite_json():
    fixture = build_fixture(new_scratch_dir("nonfinite"))
    path = fixture.root / FIXTURE_NAMES["prepared"]
    lines = path.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[0])
    row["latitude"] = float("inf")
    lines[0] = json.dumps(row, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    fixture = refresh_binding(fixture, "prepared")
    assert _rejected(lambda: prepare_snapshot(fixture.root, fixture.expectations)) in {
        "non_finite_json",
        "invalid_json",
    }


def test_rejects_source_body_contradiction():
    fixture = build_fixture(new_scratch_dir("source-body"))

    def mutate(current):
        path = current.root / FIXTURE_NAMES["lineage"]
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        rows[0]["source"]["raw_properties"]["name"] = "Tampered"
        rewrite_jsonl(path, rows)
        return "lineage"

    fixture = _mutate_fixture("source-body-mutate", mutate)
    assert _rejected(lambda: prepare_snapshot(fixture.root, fixture.expectations)) == "invalid_lineage"


def test_rejects_source_index_contradiction():
    fixture = build_fixture(new_scratch_dir("source-index"))

    def mutate(current):
        path = current.root / FIXTURE_NAMES["lineage"]
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        rows[0]["source"]["canonical_source_index"] = 2
        rewrite_jsonl(path, rows)
        return "lineage"

    fixture = _mutate_fixture("source-index-mutate", mutate)
    assert _rejected(lambda: prepare_snapshot(fixture.root, fixture.expectations)) == "invalid_lineage"


def test_rejects_category_contradiction():
    fixture = build_fixture(new_scratch_dir("category"))

    def mutate(current):
        path = current.root / FIXTURE_NAMES["prepared"]
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        rows[0]["poi_categories"][0] = {
            "id": "hcm_primary_geojson:source-category:attractions",
            "name": "Attractions",
            "context": "Visitor attractions as labelled by the primary GeoJSON source.",
        }
        rewrite_jsonl(path, rows)
        return "prepared"

    fixture = _mutate_fixture("category-mutate", mutate)
    assert _rejected(lambda: prepare_snapshot(fixture.root, fixture.expectations)) in {
        "invalid_prepared",
        "invalid_lineage",
    }


def test_rejects_registry_id_contradiction():
    fixture = build_fixture(new_scratch_dir("registry-id"))

    def mutate(current):
        path = current.root / FIXTURE_NAMES["registry"]
        registry = read_json(path)
        first_id = sorted(registry["records"])[0]
        registry["records"][first_id]["record_id"] = "r999999"
        from fixtures import _write_json

        _write_json(path, registry)
        return "registry"

    fixture = _mutate_fixture("registry-id-mutate", mutate)
    assert _rejected(lambda: prepare_snapshot(fixture.root, fixture.expectations)) == "invalid_registry"


def test_rejects_duplicate_ledger_contradiction():
    fixture = build_fixture(new_scratch_dir("ledger"))

    def mutate(current):
        path = current.root / FIXTURE_NAMES["ledger"]
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        rows[0]["duplicate_source_index"] = 1
        rewrite_jsonl(path, rows)
        return "ledger"

    fixture = _mutate_fixture("ledger-mutate", mutate)
    assert _rejected(lambda: prepare_snapshot(fixture.root, fixture.expectations)) == "invalid_ledger"


def test_rejects_missing_registry_record():
    fixture = build_fixture(new_scratch_dir("registry-missing"))

    def mutate(current):
        path = current.root / FIXTURE_NAMES["registry"]
        registry = read_json(path)
        first_id = sorted(registry["records"])[0]
        record = registry["records"].pop(first_id)
        registry["identity_index"].pop(record["identity_key"])
        from fixtures import _write_json

        _write_json(path, registry)
        return "registry"

    fixture = _mutate_fixture("registry-missing-mutate", mutate)
    assert _rejected(lambda: prepare_snapshot(fixture.root, fixture.expectations)) == "invalid_registry"


def test_caller_inputs_are_immutable():
    fixture = build_fixture(new_scratch_dir("immutability"))
    before = {
        key: (fixture.root / name).read_bytes()
        for key, name in FIXTURE_NAMES.items()
    }
    prepare_snapshot(fixture.root, fixture.expectations)
    after = {
        key: (fixture.root / name).read_bytes()
        for key, name in FIXTURE_NAMES.items()
    }
    assert after == before


def test_production_ingestion_batch_route_accepts_the_payloads(real_plan):
    pytest.importorskip("tenacity")
    from app.core.services.ingestion import POIIngestionService

    service = POIIngestionService(uow_factory=lambda: None)
    valid, indices, failures = service._validate_batch(list(real_plan.records))
    assert failures == []
    assert indices == list(range(6367))
    assert len(valid) == 6367
