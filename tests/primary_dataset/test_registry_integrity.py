"""Direct counterexample tests for the OC-034-R1 registry fixes.

These reproduce, as tested failures, the two defects an independent probe found:

1. a registry record whose record_id no longer matches its stable id / index was
   accepted on load;
2. an explicitly accepted, non-identity input revision (changed bytes, unchanged
   identities) reported no change and silently kept the old hash.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from crawler_service.app.acquisition.resolution import ConfigError
from crawler_service.app.primary_dataset.identity import (
    address_anchor,
    coord_token,
    identity_components,
    identity_key,
    name_key_for,
)
from crawler_service.app.primary_dataset.prepare import prepare_primary_dataset
from crawler_service.app.primary_dataset.registry import IdentityRegistry

from helpers import feature, read_jsonl, write_geojson


def _prepare(tmp_path, features):
    input_path = write_geojson(tmp_path / "input.geojson", features)
    out = tmp_path / "out"
    result = prepare_primary_dataset(input_path, out)
    return input_path, out, result


def _registry_doc(out: Path) -> dict:
    return json.loads((out / "identity_registry.json").read_text(encoding="utf-8"))


def _rewrite_registry(out: Path, document: dict) -> None:
    (out / "identity_registry.json").write_text(json.dumps(document), encoding="utf-8")


def _single_record_key(document: dict) -> str:
    return next(iter(document["identity_index"]))


def test_record_id_does_not_match_stable_id_is_rejected(tmp_path):
    _, out, _ = _prepare(tmp_path, [feature(name="A")])
    document = _registry_doc(out)
    stable_id = next(iter(document["records"]))
    document["records"][stable_id]["record_id"] = "r999999"
    _rewrite_registry(out, document)
    with pytest.raises(ConfigError):
        IdentityRegistry.load(out / "identity_registry.json")


def test_identity_component_mismatch_is_rejected(tmp_path):
    _, out, _ = _prepare(tmp_path, [feature(name="A")])
    document = _registry_doc(out)
    stable_id = next(iter(document["records"]))
    document["records"][stable_id]["identity"]["coordinates"] = "0.0,0.0"
    _rewrite_registry(out, document)
    with pytest.raises(ConfigError):
        IdentityRegistry.load(out / "identity_registry.json")


def test_orphan_record_is_rejected(tmp_path):
    _, out, _ = _prepare(tmp_path, [feature(name="A")])
    document = _registry_doc(out)
    document["identity_index"] = {}
    _rewrite_registry(out, document)
    with pytest.raises(ConfigError):
        IdentityRegistry.load(out / "identity_registry.json")


def test_orphan_index_entry_is_rejected(tmp_path):
    _, out, _ = _prepare(tmp_path, [feature(name="A")])
    document = _registry_doc(out)
    document["identity_index"]["phantom|key"] = "hcm_primary_geojson_internal:deadbeef"
    _rewrite_registry(out, document)
    with pytest.raises(ConfigError):
        IdentityRegistry.load(out / "identity_registry.json")


def test_duplicate_record_id_and_sequence_are_rejected(tmp_path):
    _, out, _ = _prepare(tmp_path, [feature(name="A"), feature(name="B", lat=10.6, lon=106.6)])
    document = _registry_doc(out)
    ids = list(document["records"])
    document["records"][ids[1]]["record_id"] = document["records"][ids[0]]["record_id"]
    _rewrite_registry(out, document)
    with pytest.raises(ConfigError):
        IdentityRegistry.load(out / "identity_registry.json")


def test_bool_counter_is_rejected(tmp_path):
    _, out, _ = _prepare(tmp_path, [feature(name="A")])
    document = _registry_doc(out)
    document["next_sequence"] = True
    _rewrite_registry(out, document)
    with pytest.raises(ConfigError):
        IdentityRegistry.load(out / "identity_registry.json")


def test_malformed_hash_is_rejected(tmp_path):
    _, out, _ = _prepare(tmp_path, [feature(name="A")])
    document = _registry_doc(out)
    document["input_sha256"] = "not-a-hash"
    _rewrite_registry(out, document)
    with pytest.raises(ConfigError):
        IdentityRegistry.load(out / "identity_registry.json")


def test_nonidentity_revision_requires_accept_and_then_updates_hash(tmp_path):
    # Defect 2: changed bytes with unchanged identities used to report no change.
    input_path, out, _ = _prepare(tmp_path, [feature(name="A"), feature(name="B", lat=10.6, lon=106.6)])
    registry_path = out / "identity_registry.json"
    registry = IdentityRegistry.load(registry_path)
    old_hash = registry.input_sha256

    lineage = read_jsonl(out / "lineage.jsonl")
    identities = {}
    for row in lineage:
        props = row["source"]["raw_properties"]
        key = identity_key(
            name_key_for(props), coord_token(props["lat"], props["lon"]), address_anchor(props)
        )
        identities[key] = identity_components(props)

    new_hash = "b" * 64
    with pytest.raises(ConfigError):
        registry.plan(identities, input_sha256=new_hash, accept_input_revision=False)

    plan = registry.plan(identities, input_sha256=new_hash, accept_input_revision=True)
    assert plan.changed is True
    assert registry.input_sha256 == new_hash
    assert old_hash in registry.prior_input_sha256
    # Unchanged identities keep their existing ids (no renumbering/erasure).
    assert set(plan.ids_by_identity_key) == set(identities)

    # Re-planning with the now-current hash and identical identities is a no-op.
    stable = registry.plan(identities, input_sha256=new_hash, accept_input_revision=False)
    assert stable.changed is False


def test_reorder_without_accept_preserves_every_output_byte(tmp_path):
    features = [
        feature(name="A", lat=10.5, lon=106.5),
        feature(name="B", lat=10.6, lon=106.6),
        feature(name="C", lat=10.7, lon=106.7),
    ]
    input_path = write_geojson(tmp_path / "input.geojson", features)
    out = tmp_path / "out"
    prepare_primary_dataset(input_path, out)
    before = {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()}

    reordered = write_geojson(tmp_path / "reordered.geojson", list(reversed(features)))
    with pytest.raises(ConfigError):
        prepare_primary_dataset(reordered, out)
    after = {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()}
    assert before == after  # no output mutation on a non-identity revision


def test_reorder_with_accept_preserves_ids_and_records_prior_hash(tmp_path):
    features = [
        feature(name="A", lat=10.5, lon=106.5),
        feature(name="B", lat=10.6, lon=106.6),
    ]
    input_path = write_geojson(tmp_path / "input.geojson", features)
    out = tmp_path / "out"
    first = prepare_primary_dataset(input_path, out)
    old_hash = first.summary["dataset"]["input_sha256"]
    ids_before = {row["name"]: row["id"] for row in read_jsonl(out / "prepared_pois.jsonl")}

    reordered = write_geojson(tmp_path / "reordered.geojson", list(reversed(features)))
    result = prepare_primary_dataset(reordered, out, accept_input_revision=True)
    ids_after = {row["name"]: row["id"] for row in read_jsonl(out / "prepared_pois.jsonl")}
    assert ids_before == ids_after
    assert result.revision_accepted is True

    document = json.loads((out / "identity_registry.json").read_text(encoding="utf-8"))
    assert document["input_sha256"] != old_hash
    assert old_hash in document["prior_input_sha256"]
    assert list(out.glob("identity_registry.prior-*.json"))


def test_removed_identity_is_retained_and_flagged_not_erased(tmp_path):
    input_path = write_geojson(
        tmp_path / "input.geojson",
        [feature(name="Keep"), feature(name="Drop", lat=10.6, lon=106.6)],
    )
    out = tmp_path / "out"
    prepare_primary_dataset(input_path, out)
    kept_ids = {row["id"] for row in read_jsonl(out / "prepared_pois.jsonl")}

    reduced = write_geojson(tmp_path / "reduced.geojson", [feature(name="Keep")])
    prepare_primary_dataset(reduced, out, accept_input_revision=True)

    document = json.loads((out / "identity_registry.json").read_text(encoding="utf-8"))
    retained = [rid for rid, rec in document["records"].items() if rec.get("retired")]
    assert len(document["records"]) == 2  # nothing erased
    assert len(retained) == 1
    assert {row["id"] for row in read_jsonl(out / "prepared_pois.jsonl")} < kept_ids


def _all_output_bytes(out: Path) -> dict:
    return {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()}


def _base_empty_registry(**overrides) -> dict:
    document = {
        "registry_version": 1,
        "namespace": "hcm_primary_geojson",
        "source_type": "hcm_primary_geojson_internal",
        "identity_scope": "internal_local_only",
        "cross_export_matching": "not_guaranteed",
        "input_sha256": "a" * 64,
        "prior_input_sha256": [],
        "next_sequence": 0,
        "records": {},
        "identity_index": {},
    }
    document.update(overrides)
    return document


def test_existing_registry_requires_nonnull_current_hash_even_when_empty(tmp_path):
    path = tmp_path / "identity_registry.json"
    for value in (None, "not-a-hash", ""):
        path.write_text(json.dumps(_base_empty_registry(input_sha256=value)), encoding="utf-8")
        with pytest.raises(ConfigError):
            IdentityRegistry.load(path)
    document = _base_empty_registry()
    del document["input_sha256"]
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ConfigError):
        IdentityRegistry.load(path)

    path.write_text(json.dumps(_base_empty_registry()), encoding="utf-8")
    loaded = IdentityRegistry.load(path)
    assert loaded.input_sha256 == "a" * 64
    assert loaded.records == {}


def test_bool_and_float_registry_versions_are_rejected(tmp_path):
    path = tmp_path / "identity_registry.json"
    for value in (True, 1.0, "1"):
        path.write_text(
            json.dumps(_base_empty_registry(registry_version=value)), encoding="utf-8"
        )
        with pytest.raises(ConfigError):
            IdentityRegistry.load(path)


def test_contradictory_scope_metadata_is_rejected(tmp_path):
    path = tmp_path / "identity_registry.json"
    path.write_text(
        json.dumps(_base_empty_registry(identity_scope="cross_export_trusted")),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        IdentityRegistry.load(path)
    path.write_text(
        json.dumps(_base_empty_registry(cross_export_matching="guaranteed")),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        IdentityRegistry.load(path)


def test_a_b_a_b_history_is_chronological_and_each_step_is_a_noop(tmp_path):
    features = [
        feature(name="A", lat=10.5, lon=106.5),
        feature(name="B", lat=10.6, lon=106.6),
    ]
    order_a = write_geojson(tmp_path / "a.geojson", features)
    order_b = write_geojson(tmp_path / "b.geojson", list(reversed(features)))
    out = tmp_path / "out"
    prepare_primary_dataset(order_a, out)
    first_ids = {row["name"]: row["id"] for row in read_jsonl(out / "prepared_pois.jsonl")}
    hash_a = _registry_doc(out)["input_sha256"]
    hash_b = hashlib.sha256(order_b.read_bytes()).hexdigest()

    backups = []
    for index, (path, expected_prior) in enumerate(
        [
            (order_b, [hash_a]),
            (order_a, [hash_a, hash_b]),
            (order_b, [hash_a, hash_b, hash_a]),
        ]
    ):
        before = _all_output_bytes(out)
        prior_bytes = (out / "identity_registry.json").read_bytes()
        result = prepare_primary_dataset(path, out, accept_input_revision=True)
        assert result.revision_accepted is True
        document = _registry_doc(out)
        assert document["prior_input_sha256"] == expected_prior
        assert document["input_sha256"] == (hash_b if index != 1 else hash_a)
        assert {row["name"]: row["id"] for row in read_jsonl(out / "prepared_pois.jsonl")} == first_ids
        backups.append(prior_bytes)

        reloaded = IdentityRegistry.load(out / "identity_registry.json")
        assert reloaded.input_sha256 == document["input_sha256"]
        assert reloaded.prior_input_sha256 == expected_prior

        # Reloaded and repeated with identical bytes: true byte no-op, no flag.
        stable_before = _all_output_bytes(out)
        prepare_primary_dataset(path, out)
        assert _all_output_bytes(out) == stable_before
        assert stable_before != before  # the accepted revision did change outputs

    backup_files = sorted(out.glob("identity_registry.prior-*.json"))
    assert len(backup_files) == 3
    assert len({p.name for p in backup_files}) == 3
    assert sorted(p.read_bytes() for p in backup_files) == sorted(backups)
    for backup in backup_files:
        digest = hashlib.sha256(backup.read_bytes()).hexdigest()
        assert digest in backup.name
        assert len(digest) == 64


def test_nonidentity_hours_edit_requires_flag_and_retains_ids(tmp_path):
    original = [feature(name="Hours", opening_ho="07:00-22:00")]
    edited = [feature(name="Hours", opening_ho="08:00-22:00")]
    input_path = write_geojson(tmp_path / "input.geojson", original)
    out = tmp_path / "out"
    prepare_primary_dataset(input_path, out)
    before = _all_output_bytes(out)
    old_hash = _registry_doc(out)["input_sha256"]
    old_id = read_jsonl(out / "prepared_pois.jsonl")[0]["id"]

    changed = write_geojson(tmp_path / "changed.geojson", edited)
    with pytest.raises(ConfigError):
        prepare_primary_dataset(changed, out)
    assert _all_output_bytes(out) == before

    prepare_primary_dataset(changed, out, accept_input_revision=True)
    document = _registry_doc(out)
    assert read_jsonl(out / "prepared_pois.jsonl")[0]["id"] == old_id
    assert document["input_sha256"] != old_hash
    assert document["prior_input_sha256"] == [old_hash]


def test_retired_then_reactivated_identity_keeps_its_record_and_id(tmp_path):
    both = [feature(name="Keep"), feature(name="Flap", lat=10.6, lon=106.6)]
    first = write_geojson(tmp_path / "first.geojson", both)
    out = tmp_path / "out"
    prepare_primary_dataset(first, out)
    id_by_name = {row["name"]: row["id"] for row in read_jsonl(out / "prepared_pois.jsonl")}

    reduced = write_geojson(tmp_path / "reduced.geojson", [feature(name="Keep")])
    prepare_primary_dataset(reduced, out, accept_input_revision=True)
    retired = {
        record["identity_key"]: stable_id
        for stable_id, record in _registry_doc(out)["records"].items()
        if record.get("retired")
    }
    assert len(retired) == 1
    retired_id = next(iter(retired.values()))

    prepare_primary_dataset(first, out, accept_input_revision=True)
    document = _registry_doc(out)
    assert document["records"][retired_id].get("retired") is None
    assert {row["name"]: row["id"] for row in read_jsonl(out / "prepared_pois.jsonl")} == id_by_name
    reloaded = IdentityRegistry.load(out / "identity_registry.json")
    assert reloaded.records[retired_id]["identity_key"] == next(iter(retired))
    stable = _all_output_bytes(out)
    prepare_primary_dataset(first, out)
    assert _all_output_bytes(out) == stable


def test_direct_save_rejects_payload_that_disagrees_with_state(tmp_path):
    input_path = write_geojson(tmp_path / "input.geojson", [feature(name="A")])
    out = tmp_path / "out"
    prepare_primary_dataset(input_path, out)
    before = _all_output_bytes(out)
    registry = IdentityRegistry.load(out / "identity_registry.json")

    new_hash = "c" * 64
    registry.plan(
        {key: registry.records[value]["identity"] for key, value in registry.identity_index.items()},
        input_sha256=new_hash,
        accept_input_revision=True,
    )
    with pytest.raises(ConfigError):
        registry.save(b"{}\n", accept_input_revision=True)
    assert _all_output_bytes(out) == before
    assert not list(out.glob("identity_registry.prior-*.json"))


def test_direct_save_requires_revision_flag_and_valid_prospective_state(tmp_path):
    input_path = write_geojson(tmp_path / "input.geojson", [feature(name="A")])
    out = tmp_path / "out"
    prepare_primary_dataset(input_path, out)
    before = _all_output_bytes(out)

    registry = IdentityRegistry.load(out / "identity_registry.json")
    registry.input_sha256 = "d" * 64
    with pytest.raises(ConfigError):
        registry.save(accept_input_revision=False)
    assert _all_output_bytes(out) == before

    registry = IdentityRegistry.load(out / "identity_registry.json")
    registry.next_sequence = True
    with pytest.raises(ConfigError):
        registry.save(accept_input_revision=True)
    assert _all_output_bytes(out) == before


def test_backup_collision_fails_before_any_output_mutation(tmp_path):
    input_path = write_geojson(tmp_path / "input.geojson", [feature(name="A")])
    out = tmp_path / "out"
    prepare_primary_dataset(input_path, out)
    registry_bytes = (out / "identity_registry.json").read_bytes()
    registry = IdentityRegistry.load(out / "identity_registry.json")
    collision = registry.backup_path(registry_bytes)
    collision.write_bytes(b"different evidence\n")
    before = _all_output_bytes(out)

    changed = write_geojson(
        tmp_path / "changed.geojson", [feature(name="A", opening_ho="09:00-17:00")]
    )
    with pytest.raises(ConfigError):
        prepare_primary_dataset(changed, out, accept_input_revision=True)
    assert _all_output_bytes(out) == before


def test_invalid_existing_registry_leaves_outputs_byte_unchanged(tmp_path):
    input_path = write_geojson(tmp_path / "input.geojson", [feature(name="A")])
    out = tmp_path / "out"
    prepare_primary_dataset(input_path, out)
    document = _registry_doc(out)
    document["input_sha256"] = None
    _rewrite_registry(out, document)
    before = _all_output_bytes(out)

    with pytest.raises(ConfigError):
        prepare_primary_dataset(input_path, out)
    assert _all_output_bytes(out) == before
