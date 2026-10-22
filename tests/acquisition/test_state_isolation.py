"""State-isolation regression tests for OC-026 (all fixtures SYNTHETIC).

These tests pin the explicit dataset/synthetic scope policy: a state directory
is bound to exactly one immutable scope, cross-scope reruns are rejected before
any byte is written in either order, mixed manifests are a scope violation, and
legacy/scope-less state fails closed. Every rejection is verified against the
full byte/hash snapshot of the output tree, not just summary counts.
"""

import hashlib
import json
from pathlib import Path

import pytest

from crawler_service.app.acquisition.resolution import ConfigError
from crawler_service.app.acquisition.pipeline import StateStore

from acquisition_helpers import (
    default_categories,
    entities_for,
    reviewed_source,
    run,
    osm_node,
    write_manifest,
    write_mapping,
    write_osm_export,
)

NOW = "2026-10-15T00:00:00Z"


def read_jsonl(path: Path):
    text = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def snapshot(root: Path):
    root = Path(root)
    hashes = {}
    if not root.exists():
        return hashes
    for path in sorted(root.rglob("*")):
        if path.is_file():
            hashes[str(path.relative_to(root))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return hashes


def source_entry(source_id, source_type, export_path, synthetic):
    return {
        "source_id": source_id,
        "source_type": source_type,
        "source_url": f"file://{Path(export_path).name}",
        "license": "ODbL-1.0" if source_type == "osm" else "CC0-1.0",
        "retrieved_at": "2026-10-15T00:00:00Z",
        "export_path": str(export_path),
        "synthetic": synthetic,
    }


def build(tmp_path, name, *, synthetic, dataset=None, entity_id=1, entity_name="Cafe"):
    export = write_osm_export(
        tmp_path / f"{name}.json",
        [osm_node(entity_id, 10.0, 106.0, name=entity_name, amenity="cafe")],
        synthetic=synthetic,
    )
    doc = {"manifest_version": 1, "synthetic": synthetic, "sources": [source_entry(name, "osm", export, synthetic)]}
    if dataset is not None:
        doc["dataset"] = dataset
    manifest_path = tmp_path / f"{name}.manifest.json"
    manifest_path.write_text(json.dumps(doc), encoding="utf-8")
    mapping = write_mapping(
        tmp_path / f"{name}.mapping.json",
        default_categories(),
        {name: reviewed_source(entities=entities_for(f"osm/node/{entity_id}"), synthetic=synthetic)},
    )
    return manifest_path, mapping


# --- both classification orders are rejected before any mutation ---------------


def test_synthetic_then_real_rerun_is_rejected_without_mutation(tmp_path):
    syn_m, syn_map = build(tmp_path, "syn", synthetic=True)
    out = tmp_path / "out"
    run(syn_m, syn_map, out)
    before = snapshot(out)

    real_m, real_map = build(tmp_path, "real", synthetic=False, entity_id=1)
    with pytest.raises(ConfigError):
        run(real_m, real_map, out)
    assert snapshot(out) == before
    assert read_jsonl(out / "accepted.jsonl")[0]["synthetic"] is True


def test_real_then_synthetic_rerun_is_rejected_without_mutation(tmp_path):
    real_m, real_map = build(tmp_path, "real", synthetic=False)
    out = tmp_path / "out"
    run(real_m, real_map, out)
    assert read_jsonl(out / "accepted.jsonl")[0]["synthetic"] is False
    before = snapshot(out)

    syn_m, syn_map = build(tmp_path, "syn", synthetic=True, entity_id=1)
    with pytest.raises(ConfigError):
        run(syn_m, syn_map, out)
    assert snapshot(out) == before
    assert read_jsonl(out / "accepted.jsonl")[0]["synthetic"] is False


def test_each_scope_uses_its_own_fresh_directory(tmp_path):
    real_m, real_map = build(tmp_path, "real", synthetic=False)
    syn_m, syn_map = build(tmp_path, "syn", synthetic=True)
    real_out = tmp_path / "real_out"
    syn_out = tmp_path / "syn_out"

    run(real_m, real_map, real_out)
    run(syn_m, syn_map, syn_out)

    assert json.loads((real_out / "state.json").read_text())["scope"] == "default::real"
    assert json.loads((syn_out / "state.json").read_text())["scope"] == "default::synthetic"
    assert read_jsonl(real_out / "accepted.jsonl")[0]["synthetic"] is False
    assert read_jsonl(syn_out / "accepted.jsonl")[0]["synthetic"] is True
    assert read_jsonl(real_out / "accepted.jsonl")[0]["id"] == read_jsonl(syn_out / "accepted.jsonl")[0]["id"]


# --- dataset dimension of the scope -------------------------------------------


def test_dataset_scope_mismatch_is_rejected(tmp_path):
    a_m, a_map = build(tmp_path, "a", synthetic=True, dataset="dsA")
    out = tmp_path / "out"
    run(a_m, a_map, out)
    before = snapshot(out)

    b_m, b_map = build(tmp_path, "b", synthetic=True, dataset="dsB")
    with pytest.raises(ConfigError):
        run(b_m, b_map, out)
    assert snapshot(out) == before


# --- mixed manifests -----------------------------------------------------------


def test_mixed_manifest_is_a_scope_violation(tmp_path):
    syn = write_osm_export(tmp_path / "syn.json", [osm_node(1, 10.0, 106.0, name="S", amenity="cafe")], synthetic=True)
    real = write_osm_export(tmp_path / "real.json", [osm_node(2, 10.1, 106.1, name="R", amenity="cafe")], synthetic=False)
    manifest = write_manifest(
        tmp_path / "m.json",
        [source_entry("osm-syn", "osm", syn, True), source_entry("osm-real", "osm", real, False)],
        synthetic=False,
    )
    mapping = write_mapping(
        tmp_path / "map.json",
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


# --- top / source / review effective classification ---------------------------


@pytest.mark.parametrize(
    "top,source,review",
    [
        (True, False, False),   # top-level manifest flag
        (False, True, False),   # source-level flag
        (False, False, True),   # mapping-review flag
    ],
)
def test_effective_synthetic_from_each_flag_is_isolated(tmp_path, top, source, review):
    export = write_osm_export(
        tmp_path / "osm.json",
        [osm_node(1, 10.0, 106.0, name="Cafe", amenity="cafe")],
        synthetic=source,
    )
    manifest = write_manifest(
        tmp_path / "m.json", [source_entry("osm-test", "osm", export, source)], synthetic=top
    )
    mapping = write_mapping(
        tmp_path / "map.json",
        default_categories(),
        {"osm-test": reviewed_source(entities=entities_for("osm/node/1"), synthetic=review)},
    )
    out = tmp_path / "out"
    run(manifest, mapping, out)
    assert read_jsonl(out / "accepted.jsonl")[0]["synthetic"] is True
    assert json.loads((out / "state.json").read_text())["scope"] == "default::synthetic"
    before = snapshot(out)

    real_m, real_map = build(tmp_path, "real", synthetic=False)
    with pytest.raises(ConfigError):
        run(real_m, real_map, out)
    assert snapshot(out) == before


# --- synthetic inputs never count toward real expansion totals -----------------


def test_synthetic_run_reports_zero_real_expansion(tmp_path):
    syn_m, syn_map = build(tmp_path, "syn", synthetic=True)
    result = run(syn_m, syn_map, tmp_path / "out")
    assert result.summary["synthetic"] is True
    assert result.summary["totals"]["accepted"] == 1
    assert result.summary["real_expansion_totals"] == {"accepted": 0, "candidates": 0}


# --- within one scope: changed facts vs compatible policy re-evaluation --------


def test_changed_facts_within_scope_quarantines_without_promotion(tmp_path):
    m, mapping = build(tmp_path, "osm", synthetic=True)
    export = tmp_path / "osm.json"
    out = tmp_path / "out"
    run(m, mapping, out)
    entry_before = json.loads((out / "state.json").read_text())["entries"]

    write_osm_export(export, [osm_node(1, 10.99, 106.99, name="Moved", amenity="cafe")], synthetic=True)
    run(m, mapping, out)

    assert read_jsonl(out / "accepted.jsonl") == []
    quarantine = read_jsonl(out / "quarantine.jsonl")
    assert any("conflicting_update" in row["reason_codes"] for row in quarantine)
    # Prior accepted facts and history are preserved, classification unchanged.
    entry_after = json.loads((out / "state.json").read_text())["entries"]
    assert set(entry_after) == set(entry_before)
    key = next(iter(entry_after))
    assert entry_after[key]["history"][0]["outcome"] == "accepted"
    assert entry_after[key]["synthetic"] is True


def test_compatible_policy_change_reevaluates_in_scope(tmp_path):
    export = write_osm_export(
        tmp_path / "osm.json", [osm_node(1, 10.0, 106.0, name="Cafe", amenity="cafe")], synthetic=True
    )
    manifest = write_manifest(
        tmp_path / "m.json", [source_entry("osm-test", "osm", export, True)], synthetic=True
    )
    out = tmp_path / "out"

    mapping_a = write_mapping(
        tmp_path / "a.json", default_categories(), {"osm-test": reviewed_source(entities=entities_for("osm/node/1"))}
    )
    run(manifest, mapping_a, out)
    id_before = read_jsonl(out / "accepted.jsonl")[0]["id"]

    mapping_b = write_mapping(
        tmp_path / "b.json",
        default_categories(),
        {"osm-test": reviewed_source(category_map={"amenity=cafe": "attraction"}, entities=entities_for("osm/node/1"))},
    )
    run(manifest, mapping_b, out)
    accepted = read_jsonl(out / "accepted.jsonl")
    assert accepted[0]["id"] == id_before
    assert accepted[0]["synthetic"] is True
    assert accepted[0]["poi_categories"][0]["id"] == "attraction"
    assert json.loads((out / "state.json").read_text())["scope"] == "default::synthetic"
    assert any(
        "policy_re_evaluated" in d["reason_codes"] for d in read_jsonl(out / "decisions.jsonl")
    )


# --- idempotence ---------------------------------------------------------------


def test_same_scope_rerun_is_idempotent_and_keeps_scope(tmp_path):
    m, mapping = build(tmp_path, "osm", synthetic=True)
    out = tmp_path / "out"
    first = run(m, mapping, out)
    accepted_first = read_jsonl(out / "accepted.jsonl")
    scope_first = json.loads((out / "state.json").read_text())["scope"]

    second = run(m, mapping, out)
    assert read_jsonl(out / "accepted.jsonl") == accepted_first
    assert {d["outcome"] for d in read_jsonl(out / "decisions.jsonl")} == {"duplicate"}
    assert json.loads((out / "state.json").read_text())["scope"] == scope_first
    assert first.summary["scope"] == second.summary["scope"]


# --- legacy / unknown / mixed state fails closed -------------------------------


@pytest.mark.parametrize(
    "legacy",
    [
        {"pipeline_version": 2, "entries": {}},
        {"pipeline_version": 3, "entries": {}},
        {"pipeline_version": 3, "scope": "default::mixed", "entries": {}},
        {"pipeline_version": 3, "scope": "", "entries": {}},
    ],
)
def test_legacy_or_unknown_state_fails_closed(tmp_path, legacy):
    m, mapping = build(tmp_path, "osm", synthetic=True)
    out = tmp_path / "out"
    run(m, mapping, out)
    (out / "state.json").write_text(json.dumps(legacy), encoding="utf-8")
    before = snapshot(out)

    with pytest.raises(ConfigError):
        run(m, mapping, out)
    assert snapshot(out) == before  # existing dataset never rewritten automatically


# --- invalid later source leaves every output byte unchanged -------------------


def test_invalid_later_source_writes_nothing(tmp_path):
    good = write_osm_export(tmp_path / "good.json", [osm_node(1, 10.0, 106.0, name="N", amenity="cafe")], synthetic=True)
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    manifest = write_manifest(
        tmp_path / "m.json",
        [source_entry("osm-good", "osm", good, True), source_entry("osm-bad", "osm", bad, True)],
        synthetic=True,
    )
    mapping = write_mapping(
        tmp_path / "map.json", default_categories(), {"osm-good": reviewed_source(entities=entities_for("osm/node/1"))}
    )
    out = tmp_path / "out"
    with pytest.raises(ConfigError):
        run(manifest, mapping, out)
    assert not out.exists()


# --- cross-source merge stays honestly unsupported -----------------------------


def test_cross_source_merge_remains_unsupported(tmp_path):
    m, _ = build(tmp_path, "osm", synthetic=True)
    mapping = {
        "mapping_version": 1,
        "categories": default_categories(),
        "sources": {"osm": reviewed_source(entities=entities_for("osm/node/1"))},
        "equivalences": [{"a": "osm:1", "b": "wikidata:Q1"}],
    }
    path = tmp_path / "equiv.json"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    with pytest.raises(ConfigError):
        run(m, path, tmp_path / "out")
    assert not (tmp_path / "out").exists()


# --- OC-026-R1: per-entry scope consistency on load ----------------------------


def _write_state(out, doc):
    path = Path(out) / "state.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _accepted_entry(stable_id, synthetic, resolved_id=None):
    return {
        "stable_id": stable_id,
        "status": "accepted",
        "synthetic": synthetic,
        "resolved": {"id": resolved_id or stable_id},
    }


@pytest.mark.parametrize(
    "scope,entry_synthetic",
    [
        ("default::real", True),       # real declared / synthetic entry
        ("default::synthetic", False),  # synthetic declared / real entry
    ],
)
def test_direct_state_store_rejects_contradictory_entry(tmp_path, scope, entry_synthetic):
    path = _write_state(
        tmp_path,
        {
            "pipeline_version": 3,
            "scope": scope,
            "entries": {"x": _accepted_entry("x", entry_synthetic)},
        },
    )
    with pytest.raises(ConfigError):
        StateStore(path, scope=scope)


@pytest.mark.parametrize("bad", ["missing", "false", "true", 0, 1, []])
def test_state_entry_requires_explicit_bool_synthetic(tmp_path, bad):
    entry = {"stable_id": "x", "status": "rejected"}
    if bad != "missing":
        entry["synthetic"] = bad
    path = _write_state(
        tmp_path,
        {"pipeline_version": 3, "scope": "default::synthetic", "entries": {"x": entry}},
    )
    with pytest.raises(ConfigError):
        StateStore(path, scope="default::synthetic")


@pytest.mark.parametrize(
    "scope",
    ["", "default", "default::maybe", "default::real::extra", "::real", "default::", "default::Synthetic"],
)
def test_malformed_scope_token_fails_closed(tmp_path, scope):
    path = _write_state(tmp_path, {"pipeline_version": 3, "scope": scope, "entries": {}})
    with pytest.raises(ConfigError):
        StateStore(path, scope="default::synthetic")


def test_malformed_accepted_entry_fails_closed(tmp_path):
    path = _write_state(
        tmp_path,
        {
            "pipeline_version": 3,
            "scope": "default::synthetic",
            "entries": {"x": {"stable_id": "x", "status": "accepted", "synthetic": True}},
        },
    )
    with pytest.raises(ConfigError):
        StateStore(path, scope="default::synthetic")


def test_homogeneous_v3_empty_and_valid_state_loads(tmp_path):
    empty = _write_state(tmp_path, {"pipeline_version": 3, "scope": "default::real", "entries": {}})
    store = StateStore(empty, scope="default::real")
    assert store.entries == {}

    valid = _write_state(
        tmp_path,
        {
            "pipeline_version": 3,
            "scope": "default::real",
            "entries": {"a": _accepted_entry("a", False), "b": _accepted_entry("b", False)},
        },
    )
    assert set(StateStore(valid, scope="default::real").entries) == {"a", "b"}


def test_full_pipeline_rejects_contradictory_untouched_entry(tmp_path):
    m, mapping = build(tmp_path, "osm", synthetic=True)
    out = tmp_path / "out"
    run(m, mapping, out)
    doc = json.loads((out / "state.json").read_text(encoding="utf-8"))
    existing_key = next(iter(doc["entries"]))
    doc["entries"]["ghost::entry"] = _accepted_entry("ghost::entry", False)
    _write_state(out, doc)
    before = snapshot(out)

    with pytest.raises(ConfigError):
        run(m, mapping, out)
    # The untouched contradictory entry rejects the whole run; no byte changes.
    assert snapshot(out) == before
    assert existing_key in json.loads((out / "state.json").read_text(encoding="utf-8"))["entries"]


def test_full_pipeline_rejects_flipped_existing_entry_without_touching_bytes(tmp_path):
    m, mapping = build(tmp_path, "osm", synthetic=True)
    out = tmp_path / "out"
    run(m, mapping, out)
    doc = json.loads((out / "state.json").read_text(encoding="utf-8"))
    key = next(iter(doc["entries"]))
    doc["entries"][key]["synthetic"] = False  # contradicts default::synthetic
    _write_state(out, doc)
    before = snapshot(out)

    with pytest.raises(ConfigError):
        run(m, mapping, out)
    assert snapshot(out) == before

