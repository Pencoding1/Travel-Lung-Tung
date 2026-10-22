"""DEMO-152 multi-area source selector contracts (synthetic, no engine)."""

import json

import pytest

pytest.importorskip("neo4j")

from app.core.domain.source_scope import (
    SourceSnapshotSelection,
    derive_source_area_id,
)
from app.core.infrastructure.db.repositories.memgraph import MemgraphPOIRepository
from domains import grounding, source_gate
from domains.payloads import SourceScopeSelection
from scope_fixtures import INPUT_SHA, NAMESPACE, graph_record, lineage_row

NS = NAMESPACE
HASH = INPUT_SHA
AREA_A = derive_source_area_id(NS, HASH, "HCMC", "Go Vap")
AREA_B = derive_source_area_id(NS, HASH, "Hanoi", "Hoan Kiem")
AREA_C = derive_source_area_id(NS, HASH, "HCMC", "District 1")

MODELS = (SourceScopeSelection, SourceSnapshotSelection)


def single(area=AREA_A):
    return {"dataset_namespace": NS, "input_sha256": HASH, "source_area_id": area}


def multi(ids=None):
    return {"dataset_namespace": NS, "input_sha256": HASH,
            "source_area_ids": list(ids if ids is not None else [AREA_B, AREA_A])}


class FakeRecord:
    def __init__(self, data):
        self._data = dict(data)

    def data(self):
        return dict(self._data)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getitem__(self, key):
        return self._data[key]


class RecordingTransaction:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])

    def run(self, query, parameters=None):
        self.calls.append({"query": query, "parameters": dict(parameters or {})})
        batch = self.responses.pop(0) if self.responses else []
        return [FakeRecord(row) for row in batch]


def test_single_shape_stays_legacy_and_multi_is_sorted():
    expected_single = single()
    for model in MODELS:
        assert model.model_validate(single()).model_dump() == expected_single
        assert json.loads(model.model_validate(single()).model_dump_json()) == \
            expected_single
    assert grounding.parse_source_selection(single()).data == expected_single

    expected_multi = multi([AREA_A, AREA_B])
    for model in MODELS:
        dump = model.model_validate(multi()).model_dump()
        assert dump == expected_multi
        assert "source_area_id" not in dump
    assert grounding.parse_source_selection(multi()).data == expected_multi


def test_both_or_absent_or_duplicate_selectors_fail_closed():
    bad = [
        {**multi(), "source_area_id": AREA_A},
        {"dataset_namespace": NS, "input_sha256": HASH},
        multi([]),
        multi([AREA_A, AREA_A]),
        multi(["*"]),
        {**multi(), "source_area_ids": (AREA_A, AREA_B)},
        {**multi(), "source_area_ids": [AREA_A, 123]},
    ]
    for value in bad:
        for model in MODELS:
            with pytest.raises(Exception):
                model.model_validate(value)
        assert not grounding.parse_source_selection(value).ok


def test_gate_canonical_equality_and_membership_filter():
    gate = source_gate.ScopeGate(source_selection=multi(), transport_mode="car")

    class Tool:
        def __init__(self, payload):
            self.isError = False
            self.content = [type("Text", (), {"text": json.dumps(payload)})()]

    def evidence(area):
        context = {
            "dataset_namespace": NS, "input_sha256": HASH,
            "source_area_id": area, "raw_city": "QA", "raw_area": "QA",
            "source_area_label": "QA, QA", "area_assignment": "qualified",
            "current_admin_status": "unverified_source_area",
            "current_boundary_uncertainty": "fixture",
            "lineage_reference": "graph:POI.source_metadata_json#" + "e" * 64,
            "qualification": "exact_source_snapshot_tuple",
        }
        return {"id": "poi_" + area[-4:], "POI_ID": "poi_" + area[-4:],
                "source_context": context, "administrative_context": None,
                "administrative_context_status": "unverified_source_area",
                "administrative_scope": "source_snapshot_area_only"}

    accepted = gate.prepare("explore_pois", {"source_scope": multi([AREA_A, AREA_B])})
    assert accepted.ok and accepted.args["source_scope"] == multi([AREA_A, AREA_B])
    assert not gate.prepare(
        "explore_pois", {"source_scope": multi([AREA_A])}).ok

    reply = gate.filter_result(
        "explore_pois", {"source_scope": multi()},
        Tool({"success": True, "source_scope": multi(),
              "results": [evidence(AREA_A), evidence(AREA_C)]}))
    payload = json.loads(reply.content[0].text)
    assert [item["source_context"]["source_area_id"]
            for item in payload["results"]] == [AREA_A]
    assert payload["filtered_out_of_scope"] == 1


def test_repository_parameterized_union_keeps_global_page():
    matching_a = graph_record(cached=False)
    matching_b = graph_record(
        "poi_hanoi",
        row=lineage_row(poi_id="poi_hanoi", raw_city="Hanoi",
                        raw_district="Hoan Kiem"),
    )
    foreign = graph_record(
        "poi_foreign",
        row=lineage_row(poi_id="poi_foreign", raw_city="HCMC",
                        raw_district="District 1"),
    )
    tx = RecordingTransaction(responses=[[matching_a, matching_b, foreign]])
    repo = MemgraphPOIRepository(tx)
    selection = SourceSnapshotSelection.model_validate(multi([AREA_B, AREA_A]))

    results, report = repo.get_compound_explore_source(selection, limit=5, offset=0)

    assert sorted(poi.id for poi in results) == [matching_a["id"], "poi_hanoi"]
    query = tx.calls[0]["query"]
    assert "p.source_area_id IN $source_area_ids" in query
    assert tx.calls[0]["parameters"]["source_area_ids"] == sorted([AREA_A, AREA_B])
    assert "LIMIT $page_size" in query
    assert report["matched_record_count"] == 2
