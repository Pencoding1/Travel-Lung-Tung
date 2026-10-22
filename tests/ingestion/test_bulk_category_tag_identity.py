"""OC-037 bulk-ingestion Category/Tag identity contract.

Scope and honesty boundary
--------------------------
These tests drive the **real** ``POI`` domain model (validation + JSON
serialization, exactly as ``POIIngestionService._validate_batch`` does) into the
**real** ``MemgraphPOIRepository.batch_create`` through a *recording* (spy)
transaction. They assert only the **emitted Cypher and its parameters** -- the
identity keys and the payload handed to the driver. This is deliberately NOT a
live Memgraph acceptance and makes no claim about MERGE execution, node counts
or stored graph state; the in-tree fakes cannot establish that.

``neo4j`` is a runtime import of the production repository but is absent from
the minimal ``.venv-validation``. Mirroring ``tests/graph_lifecycle/test_updater.py``
the module skips cleanly there and is executed in the validation env that
provides ``neo4j``; no package is installed.
"""

import copy
import sys
from pathlib import Path

import pytest

pytest.importorskip("neo4j")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.domain.graph_entities import POI  # noqa: E402
from app.core.infrastructure.db.repositories.memgraph import (  # noqa: E402
    MemgraphPOIRepository,
)
from crawler_service.app.primary_dataset import catalog  # noqa: E402


# The exact identity clauses the bulk path must emit -- the same contract the
# single create/update queries use.
TAG_MERGE = "MERGE (t:Tag {id: poi.tag.id})"
TAG_ON_CREATE = "ON CREATE SET t.name = poi.tag.name"
CATEGORY_MERGE = "MERGE (catNode:Category {id: cat.id})"
CATEGORY_ON_CREATE = "ON CREATE SET catNode.name = cat.name, catNode.context = cat.context"

# The ambiguous name-keyed merges the bulk path used to emit.
LEGACY_TAG_MERGE = "MERGE (t:Tag {name: poi.tag.name})"
LEGACY_CATEGORY_MERGE = "MERGE (catNode:Category {name: cat.name})"


class RecordingTransaction:
    """Spy transaction: records every ``run`` (query + parameters), returns no rows.

    It never executes Cypher; it only captures the parameterized contract the
    repository hands to the driver.
    """

    def __init__(self):
        self.calls = []

    def run(self, query, parameters=None):
        self.calls.append({"query": query, "parameters": dict(parameters or {})})
        return []


def _validated(raw):
    """Validate then serialize exactly as the ingestion service does."""
    return POI.model_validate(raw).model_dump(mode="json")


def _poi(poi_id, **overrides):
    raw = {
        "id": poi_id,
        "name": f"POI {poi_id}",
        "longitude": 106.7,
        "latitude": 10.7,
        "address": {"district": "Quan 1", "city": "Ho Chi Minh"},
    }
    raw.update(overrides)
    return raw


def _category(category_id, name="Coffee", context="Coffee shops."):
    return {"id": category_id, "name": name, "context": context}


def _run_batch(payloads):
    tx = RecordingTransaction()
    repo = MemgraphPOIRepository(tx)
    count = repo.batch_create(payloads)
    return tx, count


def _single_write_query(method, entity):
    tx = RecordingTransaction()
    repo = MemgraphPOIRepository(tx)
    if method == "create":
        repo.create(entity)
    else:
        repo.update(entity.id, entity)
    assert len(tx.calls) == 1
    return tx.calls[0]["query"]


# ---------------------------------------------------------------------------
# The bulk path keys Category/Tag by explicit id
# ---------------------------------------------------------------------------
def test_bulk_merges_tag_and_category_by_explicit_id():
    payload = [
        _validated(
            _poi(
                "poi_1",
                poi_categories=[_category("hcm_primary_geojson:source-category:coffee")],
                tag={"id": "tag_coffee", "name": "Coffee Tag"},
            )
        )
    ]

    tx, count = _run_batch(payload)

    assert count == 1
    assert len(tx.calls) == 1
    query = tx.calls[0]["query"]
    assert TAG_MERGE in query
    assert TAG_ON_CREATE in query
    assert CATEGORY_MERGE in query
    assert CATEGORY_ON_CREATE in query
    # The name-keyed identity that could collapse distinct ids is gone.
    assert LEGACY_TAG_MERGE not in query
    assert LEGACY_CATEGORY_MERGE not in query


def test_bulk_keying_matches_single_create_and_update():
    entity = POI.model_validate(
        _poi(
            "poi_1",
            poi_categories=[_category("hcm_primary_geojson:source-category:coffee")],
            tag={"id": "tag_coffee", "name": "Coffee Tag"},
        )
    )
    bulk_query = _run_batch([entity.model_dump(mode="json")])[0].calls[0]["query"]
    create_query = _single_write_query("create", entity)
    update_query = _single_write_query("update", entity)

    for clause in (TAG_MERGE, TAG_ON_CREATE, CATEGORY_MERGE, CATEGORY_ON_CREATE):
        assert clause in bulk_query
        assert clause in create_query
        assert clause in update_query


# ---------------------------------------------------------------------------
# Identical name / different id must not collapse; identical id / different name
# ---------------------------------------------------------------------------
def test_same_display_name_different_ids_remain_distinct():
    first = _category("hcm_primary_geojson:source-category:coffee", name="Coffee")
    second = _category("hcm_primary_geojson:source-category:coffee_import", name="Coffee")
    payload = [_validated(_poi("poi_1", poi_categories=[first, second]))]

    tx, _ = _run_batch(payload)

    emitted = tx.calls[0]["parameters"]["batch"][0]["poi_categories"]
    assert [c["name"] for c in emitted] == ["Coffee", "Coffee"]
    assert [c["id"] for c in emitted] == [first["id"], second["id"]]
    # Because the emitted identity is the id, the two same-named records cannot
    # be folded into one node.
    assert CATEGORY_MERGE in tx.calls[0]["query"]


def test_same_id_different_name_does_not_overwrite_stored_display():
    renamed = _category(
        "hcm_primary_geojson:source-category:coffee",
        name="Espresso Bar",
        context="A newer spelling of the same identity.",
    )
    payload = [
        _validated(
            _poi(
                "poi_1",
                poi_categories=[renamed],
                tag={"id": "tag_coffee", "name": "Renamed Tag"},
            )
        )
    ]

    tx, _ = _run_batch(payload)

    query = tx.calls[0]["query"]
    assert CATEGORY_MERGE in query and CATEGORY_ON_CREATE in query
    assert TAG_MERGE in query and TAG_ON_CREATE in query
    # Nothing overwrites a stored node unconditionally: display name/context are
    # ON CREATE only (single-write semantics), so an existing id keeps its name.
    bare_sets = [
        line.strip()
        for line in query.splitlines()
        if line.strip().startswith(("SET t.", "SET catNode."))
    ]
    assert bare_sets == []


# ---------------------------------------------------------------------------
# Absent tag / empty categories never reach a null-keyed or name-keyed MERGE
# ---------------------------------------------------------------------------
def test_absent_tag_and_empty_categories_keep_null_safe_guards():
    payload = [_validated(_poi("poi_1"))]

    tx, count = _run_batch(payload)

    assert count == 1
    query = tx.calls[0]["query"]
    assert "CASE WHEN poi.tag IS NOT NULL THEN [1] ELSE [] END" in query
    assert (
        "CASE WHEN poi.poi_categories IS NOT NULL THEN poi.poi_categories ELSE [] END"
        in query
    )
    assert LEGACY_TAG_MERGE not in query
    assert LEGACY_CATEGORY_MERGE not in query
    emitted = tx.calls[0]["parameters"]["batch"][0]
    assert emitted["tag"] is None
    assert emitted["poi_categories"] == []


# ---------------------------------------------------------------------------
# Source-category ids survive validation/serialization and the query parameters
# ---------------------------------------------------------------------------
def test_closed_source_category_ids_pass_through_unchanged():
    assert len(catalog.CATALOG) == 14
    categories = [
        {"id": row["id"], "name": row["name"], "context": row["context"]}
        for row in catalog.CATALOG
    ]
    payload = [_validated(_poi("poi_1", poi_categories=categories))]

    tx, _ = _run_batch(payload)

    emitted = tx.calls[0]["parameters"]["batch"][0]["poi_categories"]
    assert emitted == categories
    assert emitted[0]["id"].startswith("hcm_primary_geojson:source-category:")


# ---------------------------------------------------------------------------
# Caller payload is forwarded, never mutated
# ---------------------------------------------------------------------------
def test_batch_create_does_not_mutate_caller_payload():
    payload = [
        _validated(
            _poi(
                "poi_1",
                poi_categories=[_category("hcm_primary_geojson:source-category:coffee")],
                tag={"id": "tag_coffee", "name": "Coffee Tag"},
            )
        )
    ]
    snapshot = copy.deepcopy(payload)

    tx, _ = _run_batch(payload)

    assert payload == snapshot
    # The exact caller list is handed to the transaction (no rewrite/rebuild).
    assert tx.calls[0]["parameters"]["batch"] is payload
