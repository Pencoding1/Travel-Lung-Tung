"""UserPreference sync must not let an empty list drop later writes.

The previous single pipeline ``UNWIND $category_list ... UNWIND $tag_list``
produced zero rows as soon as the category list was empty, silently discarding
the tag edges. The fix uses independent parameterized writes inside the same
transaction; these tests assert every write runs and that empty lists mean
"clear this side of the profile".
"""

import pytest

from app.core.domain.graph_entities import UserPreference
from app.core.infrastructure.db.repositories.memgraph import MemgraphUserBehaviorRepository
from graph_fakes import RecordingTransaction


def _repo():
    tx = RecordingTransaction()
    return MemgraphUserBehaviorRepository(tx), tx


def test_empty_categories_still_writes_tags():
    repo, tx = _repo()
    entity = UserPreference(
        user_id="u1", category_weights={}, tag_weights={"tag_a": 0.5}
    )

    repo.create(entity)

    assert len(tx.calls) == 4
    merge, clear, categories, tags = tx.calls
    assert "MERGE (u:User {id: $user_id})" in merge["query"]
    assert "DELETE old_pref" in clear["query"]
    assert categories["parameters"]["items"] == []
    assert "MATCH (n:Category" in categories["query"]
    assert tags["parameters"]["items"] == [{"id": "tag_a", "weight": 0.5}]
    assert "MATCH (n:Tag" in tags["query"]


def test_empty_tags_still_writes_categories():
    repo, tx = _repo()
    entity = UserPreference(
        user_id="u1", category_weights={"cat_a": 0.25}, tag_weights={}
    )

    repo.create(entity)

    assert len(tx.calls) == 4
    categories = tx.calls[2]
    tags = tx.calls[3]
    assert categories["parameters"]["items"] == [{"id": "cat_a", "weight": 0.25}]
    assert tags["parameters"]["items"] == []


def test_replacing_profile_clears_obsolete_prefers():
    repo, tx = _repo()
    entity = UserPreference(user_id="u1", category_weights={"cat_a": 1.0})

    repo.create(entity)

    assert any("DELETE old_pref" in call["query"] for call in tx.calls)


def test_update_id_must_match_payload_user_id():
    repo, _tx = _repo()
    entity = UserPreference(user_id="u1", category_weights={"cat_a": 1.0})

    with pytest.raises(ValueError):
        repo.update("someone_else", entity)


def test_update_with_matching_id_syncs():
    repo, tx = _repo()
    entity = UserPreference(user_id="u1", tag_weights={"tag_a": 1.0})

    repo.update("u1", entity)

    assert len(tx.calls) == 4
