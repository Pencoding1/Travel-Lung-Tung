"""Acceptance tests for the OC-034 primary dataset preparation capability."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from crawler_service.app.acquisition.resolution import ConfigError
from crawler_service.app.primary_dataset import PREP_VERSION
from crawler_service.app.primary_dataset.catalog import CATALOG, CATALOG_VERSION, catalog_payload
from crawler_service.app.primary_dataset.prepare import (
    LEGACY_ADMIN_FLAG,
    prepare_primary_dataset,
)
from crawler_service.app.primary_dataset.validation import load_poi_model

from helpers import MISSING, REAL_INPUT, feature, read_jsonl, write_geojson


def run_prep(tmp_path: Path, features, **kwargs):
    input_path = write_geojson(tmp_path / "input.geojson", features)
    out = tmp_path / "out"
    result = prepare_primary_dataset(input_path, out, **kwargs)
    return result, out


def test_closed_catalog_is_the_14_observed_labels():
    assert len(CATALOG) == 14
    labels = {row["source_label"] for row in CATALOG}
    assert "coffee" in labels and "restaurant" in labels
    assert catalog_payload("coffee")["id"].startswith("hcm_primary_geojson:source-category:")
    assert catalog_payload("nightclub") is None
    assert len(CATALOG_VERSION) == 16


def test_poi_import_bootstrap_is_isolated_from_other_app_namespaces():
    poi = load_poi_model()
    assert poi.__module__ == "app.core.domain.graph_entities"
    module_file = (getattr(poi, "__module__", "") and __import__("sys").modules[poi.__module__].__file__) or ""
    assert "POI_service" in module_file.replace("\\", "/")


def test_unknown_category_is_quarantined_without_invention(tmp_path):
    result, out = run_prep(tmp_path, [feature(category="nightclub")])
    assert result.summary["counts"]["prepared"] == 0
    assert result.summary["counts"]["quarantine"] == 1
    quarantine = read_jsonl(out / "quarantine.jsonl")
    assert "unknown_source_category" in quarantine[0]["reason_codes"]
    assert read_jsonl(out / "prepared_pois.jsonl") == []


def test_missing_and_invalid_coordinates_are_quarantined(tmp_path):
    features = [
        feature(name="NoGeometry", geometry=MISSING),
        feature(name="BadLon", lon=200.0),
        feature(name="Good", lat=10.5, lon=106.5),
    ]
    result, out = run_prep(tmp_path, features)
    assert result.summary["counts"]["prepared"] == 1
    assert result.summary["counts"]["quarantine"] == 2
    reasons = {r for row in read_jsonl(out / "quarantine.jsonl") for r in row["reason_codes"]}
    assert reasons & {"missing_geometry", "missing_or_invalid_coordinates"}


def test_non_point_geometry_is_quarantined_even_with_valid_coordinates(tmp_path):
    polygon = {"type": "Polygon", "coordinates": [[[106.5, 10.5], [106.6, 10.5], [106.5, 10.5]]]}
    result, out = run_prep(tmp_path, [feature(name="Area", geometry=polygon)])
    assert result.summary["counts"]["prepared"] == 0
    assert result.summary["counts"]["quarantine"] == 1
    assert "unsupported_geometry_kind" in read_jsonl(out / "quarantine.jsonl")[0]["reason_codes"]


def test_same_name_brand_at_different_locations_is_distinct(tmp_path):
    features = [
        feature(name="Highlands Coffee", lat=10.5, lon=106.5),
        feature(name="Highlands Coffee", lat=10.6, lon=106.6),
    ]
    result, out = run_prep(tmp_path, features)
    prepared = read_jsonl(out / "prepared_pois.jsonl")
    assert result.summary["counts"]["prepared"] == 2
    assert len({row["id"] for row in prepared}) == 2


def test_null_processed_name_falls_back_to_raw_name(tmp_path):
    features = [feature(name="Hổ", processed_name="", lat=10.786938, lon=106.7084339)]
    result, out = run_prep(tmp_path, features)
    prepared = read_jsonl(out / "prepared_pois.jsonl")
    assert prepared[0]["name"] == "Hổ"
    lineage = read_jsonl(out / "lineage.jsonl")[0]
    assert lineage["identity"]["name_source"] == "raw_name_fallback"
    assert lineage["identity"]["raw_name"] == "Hổ"
    assert lineage["identity"]["processed_name"] == ""
    assert result.summary["counts"]["quarantine"] == 0


def test_exact_duplicate_pair_collapses_with_both_indices(tmp_path):
    twin = feature(name="Hannah's Kitchen VN", lat=10.799914, lon=106.689694)
    features = [feature(name="Other"), dict(twin), dict(twin)]
    result, out = run_prep(tmp_path, features)
    assert result.summary["counts"]["input_features"] == 3
    assert result.summary["counts"]["exact_duplicate_extra"] == 1
    assert result.summary["counts"]["candidate_features"] == 2
    assert result.summary["counts"]["prepared"] == 2
    ledger = read_jsonl(out / "duplicate_ledger.jsonl")
    assert len(ledger) == 1
    assert ledger[0]["canonical_source_index"] == 1
    assert ledger[0]["duplicate_source_index"] == 2
    assert ledger[0]["reason"] == "byte_equivalent_canonical_feature"


def test_identity_collision_fails_closed(tmp_path):
    # Same identity fields but not byte-equivalent (different hours) -> distinct
    # features claiming the same identity must be refused, never merged.
    a = feature(name="Twin Cafe", opening_ho="07:00-22:00")
    b = feature(name="Twin Cafe", opening_ho="08:00-22:00")
    assert a != b
    input_path = write_geojson(tmp_path / "input.geojson", [a, b])
    with pytest.raises(ConfigError):
        prepare_primary_dataset(input_path, tmp_path / "out")


def test_hours_are_kept_raw_and_prices_unknown(tmp_path):
    features = [feature(opening_ho='Mo-Fr 07:30-17:00; PH closed "Nghỉ lễ"')]
    result, out = run_prep(tmp_path, features)
    payload = read_jsonl(out / "prepared_pois.jsonl")[0]
    assert payload["operation_time"] == 'Mo-Fr 07:30-17:00; PH closed "Nghỉ lễ"'
    assert payload["menu"] == []
    assert payload["rating"] is None
    assert payload["contact_info"] is None
    lineage = read_jsonl(out / "lineage.jsonl")[0]
    assert lineage["operation_time"]["parse_status"] == "unparsed_source_text"
    assert lineage["price"]["status"] == "unknown"


def test_legacy_admin_is_flagged_not_reinvented(tmp_path):
    features = [feature(name="Legacy", district="Thu Dau Mot")]
    result, out = run_prep(tmp_path, features)
    payload = read_jsonl(out / "prepared_pois.jsonl")[0]
    assert payload["address"]["district"] == "Thu Dau Mot"
    lineage = read_jsonl(out / "lineage.jsonl")[0]
    assert lineage["review_flags"] == [LEGACY_ADMIN_FLAG]
    assert lineage["address"]["current_admin_claim"] == "none"
    assert result.summary["prepared_review_flags"][LEGACY_ADMIN_FLAG] == 1


def test_rerun_with_same_input_and_registry_is_a_byte_noop(tmp_path):
    features = [feature(name="A"), feature(name="B", lat=10.6, lon=106.6)]
    input_path = write_geojson(tmp_path / "input.geojson", features)
    out = tmp_path / "out"
    prepare_primary_dataset(input_path, out)
    before = {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()}
    second = prepare_primary_dataset(input_path, out)
    after = {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()}
    assert before == after
    assert second.summary["counts"]["prepared"] == 2


def test_reordered_input_keeps_stable_ids(tmp_path):
    features = [
        feature(name="A", lat=10.5, lon=106.5),
        feature(name="B", lat=10.6, lon=106.6),
        feature(name="C", lat=10.7, lon=106.7),
    ]
    input_path = write_geojson(tmp_path / "input.geojson", features)
    out = tmp_path / "out"
    prepare_primary_dataset(input_path, out)
    ids_before = {row["name"]: row["id"] for row in read_jsonl(out / "prepared_pois.jsonl")}

    reordered = write_geojson(tmp_path / "reordered.geojson", list(reversed(features)))
    prepare_primary_dataset(reordered, out, accept_input_revision=True)
    ids_after = {row["name"]: row["id"] for row in read_jsonl(out / "prepared_pois.jsonl")}
    assert ids_before == ids_after


def test_identity_field_change_requires_explicit_review(tmp_path):
    input_path = write_geojson(tmp_path / "input.geojson", [feature(name="Original")])
    out = tmp_path / "out"
    prepare_primary_dataset(input_path, out)
    prepared_before = (out / "prepared_pois.jsonl").read_bytes()
    registry_before = (out / "identity_registry.json").read_bytes()

    changed = write_geojson(tmp_path / "changed.geojson", [feature(name="Renamed")])
    with pytest.raises(ConfigError):
        prepare_primary_dataset(changed, out)
    assert (out / "prepared_pois.jsonl").read_bytes() == prepared_before
    assert (out / "identity_registry.json").read_bytes() == registry_before

    prepare_primary_dataset(changed, out, accept_input_revision=True)
    assert (out / "prepared_pois.jsonl").read_bytes() != prepared_before
    backups = list(out.glob("identity_registry.prior-*.json"))
    assert backups and backups[0].read_bytes() == registry_before


def test_foreign_namespace_registry_fails_closed_before_write(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    foreign = {
        "registry_version": 1,
        "namespace": "some_other_dataset",
        "source_type": "hcm_primary_geojson_internal",
        "next_sequence": 0,
        "records": {},
        "identity_index": {},
    }
    (out / "identity_registry.json").write_text(json.dumps(foreign), encoding="utf-8")
    input_path = write_geojson(tmp_path / "input.geojson", [feature()])
    with pytest.raises(ConfigError):
        prepare_primary_dataset(input_path, out)
    assert not (out / "prepared_pois.jsonl").exists()
    assert not (out / "summary.json").exists()


def test_tampered_registry_index_fails_closed(tmp_path):
    input_path = write_geojson(tmp_path / "input.geojson", [feature(name="A")])
    out = tmp_path / "out"
    prepare_primary_dataset(input_path, out)
    registry_path = out / "identity_registry.json"
    document = json.loads(registry_path.read_text(encoding="utf-8"))
    document["identity_index"] = {"bogus|key": "hcm_primary_geojson_internal:doesnotexist"}
    registry_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ConfigError):
        prepare_primary_dataset(input_path, out)


def test_poi_model_validates_every_prepared_payload(tmp_path):
    features = [
        feature(name="Cafe", category="coffee"),
        feature(name="Bank", category="finance", lat=10.6, lon=106.6),
    ]
    result, out = run_prep(tmp_path, features)
    poi = load_poi_model()
    prepared = read_jsonl(out / "prepared_pois.jsonl")
    assert len(prepared) == 2
    for row in prepared:
        model = poi.model_validate(row)
        assert model.id and model.name
        assert model.poi_categories and model.poi_categories[0].context


@pytest.mark.skipif(not REAL_INPUT.is_file(), reason="primary dataset not present")
def test_full_primary_dataset_is_conserved_and_lineaged(tmp_path):
    before_hash = hashlib.sha256(REAL_INPUT.read_bytes()).hexdigest()
    result = prepare_primary_dataset(REAL_INPUT, tmp_path / "out")
    out = tmp_path / "out"
    assert hashlib.sha256(REAL_INPUT.read_bytes()).hexdigest() == before_hash

    counts = result.summary["counts"]
    assert counts["input_features"] == 6368
    assert counts["exact_duplicate_extra"] == 1
    assert counts["candidate_features"] == 6367
    assert counts["prepared"] == 6367
    assert counts["quarantine"] == 0
    assert counts["prepared_review_required"] == 411
    assert result.summary["sumcheck"]["prepared_plus_quarantine_equals_candidates"]
    assert result.summary["sumcheck"]["candidates_plus_duplicate_extra_equals_input"]

    ledger = read_jsonl(out / "duplicate_ledger.jsonl")
    assert len(ledger) == 1
    assert ledger[0]["canonical_source_index"] == 4855
    assert ledger[0]["duplicate_source_index"] == 4859

    lineage = read_jsonl(out / "lineage.jsonl")
    prepared = read_jsonl(out / "prepared_pois.jsonl")
    assert len(lineage) == counts["prepared"] == len(prepared)
    assert len({row["id"] for row in prepared}) == len(prepared)
    assert {row["id"] for row in lineage} == {row["id"] for row in prepared}
    canonical_indices = {row["source"]["canonical_source_index"] for row in lineage}
    assert len(canonical_indices) == 6367
    assert 4855 in canonical_indices and 4859 not in canonical_indices

    poi = load_poi_model()
    for row in prepared:
        model = poi.model_validate(row)
        assert model.poi_categories
    assert len({row["poi_categories"][0]["id"] for row in prepared}) == 14

    assert result.summary["status"] == "prepared/schema-validated candidates"
    assert result.summary["prep_version"] == PREP_VERSION
