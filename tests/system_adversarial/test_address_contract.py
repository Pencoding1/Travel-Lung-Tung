"""SYS102 address-instrument contract (OFFLINE, synthetic, no I/O).

The instrument under test is the shared pure helper used by both comparison
functions.  Addresses are built with the *real production* construction
(``domains.grounding._reconstruct_source_address``) so the structured branch is
covered by the same shape production delivers, not by an authored mock.

Legacy flat-string fixtures remain valid through the documented compatibility
branch in ``qa_runtime.compare_source_address``; they are synthetic evidence and
are not proof that production address objects were tested.
"""

import copy
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "ai_service")]

from domains import grounding  # noqa: E402 - production construction in tests only
from benchmarks.system_adversarial import qa_runtime as q  # noqa: E402
from benchmarks.system_adversarial import runner as r  # noqa: E402

COMPARE_FUNCTIONS = (q.compare_delivered_fields, r.compare_injected_fields)


def fixture(source="Evidence street"):
    """One delivered stop whose address object is produced by production code."""
    evidence = {"p": {"name": "Evidence venue", "address": source,
                      "operation_time": None}}
    address = grounding._reconstruct_source_address(
        {"POI_Address": source}, [], "synthetic")
    payload = {"reply": {"stops": [
        {"poi": {"id": "p", "name": "Evidence venue", "address": address,
                 "operation_time": None},
         "description": grounding.NEUTRAL_DESCRIPTION,
         "description_grounded": False}]}}
    return payload, evidence


def test_production_construction_shape_is_source_snapshot_mode():
    address = grounding._reconstruct_source_address(
        {"POI_Address": "Evidence street"}, [], "synthetic")
    assert address == {"street_name": "Evidence street", "ward": None,
                       "district": None, "city": None, "nation": None}


@pytest.mark.parametrize("compare", COMPARE_FUNCTIONS)
@pytest.mark.parametrize("source", ["Evidence street", "  Evidence street  ",
                                    None, "   "])
def test_actual_production_address_matches_source_and_preserves_unknowns(
        compare, source):
    payload, evidence = fixture(source)
    checks = compare(payload, evidence)
    assert checks["address"] is True
    assert checks["all_stops_covered"] is True
    assert all(checks.values())


@pytest.mark.parametrize("compare", COMPARE_FUNCTIONS)
@pytest.mark.parametrize("mutation", [
    lambda a: a.update(street_name="Wrong street"),
    lambda a: a.update(city="Invented city"),
    lambda a: a.update(district="Invented district"),
    lambda a: a.update(ward="Invented ward"),
    lambda a: a.update(nation="Invented nation"),
    lambda a: a.pop("city"),
    lambda a: a.update(extra={"address": "SYS098 authored address, not source truth"}),
    lambda a: a.update(street_name=12),
])
def test_invented_or_malformed_structured_address_is_rejected(
        compare, mutation):
    payload, evidence = fixture()
    mutation(payload["reply"]["stops"][0]["poi"]["address"])
    assert compare(payload, evidence)["address"] is False


@pytest.mark.parametrize("compare", COMPARE_FUNCTIONS)
def test_missing_source_address_evidence_is_not_proven_unknown(compare):
    payload, evidence = fixture(None)
    evidence["p"].pop("address")
    assert compare(payload, evidence)["address"] is False


@pytest.mark.parametrize("compare", COMPARE_FUNCTIONS)
def test_bad_first_address_not_erased_by_good_last(compare):
    payload, evidence = fixture()
    later = copy.deepcopy(payload["reply"]["stops"][0])
    later["poi"]["id"] = "later"
    evidence["later"] = copy.deepcopy(evidence["p"])
    payload["reply"]["stops"][0]["poi"]["address"]["city"] = "Invented"
    payload["reply"]["stops"].append(later)
    assert compare(payload, evidence)["address"] is False
