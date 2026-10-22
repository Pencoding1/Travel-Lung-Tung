"""Deterministic source-area derivation and strict selector validation."""

import pytest
from pydantic import ValidationError

from app.core.domain.source_scope import (
    SOURCE_AREA_ID_PREFIX,
    SourceScopeMismatch,
    SourceSnapshotRef,
    SourceSnapshotSelection,
    build_source_context,
    derive_source_area,
    derive_source_area_id,
    qualify_source_record,
)
from scope_fixtures import (
    INPUT_SHA,
    NAMESPACE,
    POI_ID,
    lineage_row,
    typed_metadata,
)


def _selection(city="HCMC", area="Go Vap", namespace=NAMESPACE, sha=INPUT_SHA):
    return SourceSnapshotSelection(
        dataset_namespace=namespace,
        input_sha256=sha,
        source_area_id=derive_source_area_id(namespace, sha, city, area),
    )


def test_area_id_is_deterministic_and_labels_are_not_current_ids():
    first = derive_source_area_id(NAMESPACE, INPUT_SHA, "HCMC", "Go Vap")
    second = derive_source_area_id(NAMESPACE, INPUT_SHA, "HCMC", "Go Vap")
    assert first == second
    assert first.startswith(SOURCE_AREA_ID_PREFIX)
    assert not first.startswith(("district", "District"))


def test_equal_labels_in_different_city_namespace_or_snapshot_are_distinct():
    base = derive_source_area_id(NAMESPACE, INPUT_SHA, "HCMC", "Go Vap")
    assert base != derive_source_area_id(NAMESPACE, INPUT_SHA, "Hanoi", "Go Vap")
    assert base != derive_source_area_id("other_dataset", INPUT_SHA, "HCMC", "Go Vap")
    assert base != derive_source_area_id(NAMESPACE, "b" * 64, "HCMC", "Go Vap")


def test_exact_raw_labels_are_preserved_and_none_is_unassigned():
    metadata = typed_metadata(lineage_row(raw_city="HCMC", raw_district=None))
    identity = derive_source_area(metadata)
    assert identity.raw_city == "HCMC"
    assert identity.raw_area is None
    assert identity.area_assignment == "unassigned"
    assert identity.source_area_label == "HCMC"
    assert "None" not in identity.source_area_label


def test_context_is_compact_and_has_no_raw_blob_or_current_district():
    metadata = typed_metadata()
    identity = derive_source_area(metadata)
    context = build_source_context(identity, metadata)
    dumped = context.model_dump()
    assert dumped["raw_city"] == "HCMC"
    assert dumped["raw_area"] == "Go Vap"
    assert dumped["lineage_reference"].startswith("graph:POI.source_metadata_json#")
    assert "raw_lineage_json" not in dumped
    assert "district_id" not in dumped
    assert dumped["current_admin_status"] == "unverified_source_area"


@pytest.mark.parametrize(
    "field,value",
    [
        ("dataset_namespace", 123),
        ("dataset_namespace", "   "),
        ("input_sha256", True),
        ("input_sha256", "ABCDEF" + "0" * 58),
        ("input_sha256", "a" * 63),
    ],
)
def test_selection_rejects_non_string_boolean_and_malformed_hashes(field, value):
    payload = {
        "dataset_namespace": NAMESPACE,
        "input_sha256": INPUT_SHA,
        "source_area_id": derive_source_area_id(
            NAMESPACE, INPUT_SHA, "HCMC", "Go Vap"
        ),
    }
    payload[field] = value
    with pytest.raises(ValidationError):
        SourceSnapshotSelection.model_validate(payload)


@pytest.mark.parametrize(
    "area_id",
    [
        "district_1",
        "District:1",
        "source_area_v1:" + "A" * 64,
        "source_area_v1:" + "a" * 63,
        True,
        123,
    ],
)
def test_selection_rejects_current_and_malformed_area_ids(area_id):
    with pytest.raises(ValidationError):
        SourceSnapshotSelection(
            dataset_namespace=NAMESPACE,
            input_sha256=INPUT_SHA,
            source_area_id=area_id,
        )


def test_selection_forbids_unknown_fields():
    with pytest.raises(ValidationError):
        SourceSnapshotSelection(
            dataset_namespace=NAMESPACE,
            input_sha256=INPUT_SHA,
            source_area_id=derive_source_area_id(
                NAMESPACE, INPUT_SHA, "HCMC", "Go Vap"
            ),
            current_district_id="d1",
        )


def test_snapshot_ref_rejects_numeric_and_foreign_hashes():
    with pytest.raises(ValidationError):
        SourceSnapshotRef(dataset_namespace=NAMESPACE, input_sha256=1)
    with pytest.raises(ValidationError):
        SourceSnapshotRef(dataset_namespace=NAMESPACE, input_sha256="not-a-hash")


def test_qualification_rejects_copied_metadata_and_cache_mismatch():
    metadata = typed_metadata()
    selection = _selection()

    with pytest.raises(Exception):
        qualify_source_record("different_poi", metadata, selection)

    with pytest.raises(Exception):
        qualify_source_record(
            POI_ID,
            metadata,
            selection,
            cached_area_id=derive_source_area_id(
                NAMESPACE, INPUT_SHA, "Hanoi", "Go Vap"
            ),
            cached_namespace=NAMESPACE,
            cached_snapshot=INPUT_SHA,
        )


def test_qualification_rejects_mismatched_selection_but_accepts_uncached_old_row():
    metadata = typed_metadata()
    wrong = _selection(city="Hanoi")
    with pytest.raises(SourceScopeMismatch):
        qualify_source_record(POI_ID, metadata, wrong)

    identity = qualify_source_record(
        POI_ID,
        metadata,
        _selection(),
        cached_area_id=None,
        cached_namespace=None,
        cached_snapshot=None,
    )
    assert identity.source_area_id == _selection().source_area_id
