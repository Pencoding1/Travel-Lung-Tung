"""T049/AI-059 source-snapshot contract (pure, fixture-level).

These are contract tests over the real ``domains.grounding`` and
``domains.payloads`` code. They do not contact MCP, a graph or a model, and do
not prove a real source import or end-to-end deployment.
"""

import json

import pytest
from pydantic import ValidationError

from domains import grounding
from domains.payloads import ItineraryRequest

NAMESPACE = "hcm_primary_geojson"
SNAPSHOT = "a" * 64
AREA_ID = "source_area_v1:" + "b" * 64
SELECTION = {
    "dataset_namespace": NAMESPACE,
    "input_sha256": SNAPSHOT,
    "source_area_id": AREA_ID,
}

DISTRICT = {"id": "quan_1", "name": "District 1"}
CITY = {"id": "hcmc", "name": "Ho Chi Minh City"}

ADMIN_CONTEXT = {
    "city_id": "hcmc",
    "district_id": "quan_1",
    "city_name": "Ho Chi Minh City",
    "district_name": "District 1",
}


def _selection(**overrides):
    value = dict(SELECTION)
    value.update(overrides)
    return value


def _context(selection=None, **overrides):
    selection = selection or SELECTION
    value = {
        "dataset_namespace": selection["dataset_namespace"],
        "input_sha256": selection["input_sha256"],
        "source_area_id": selection["source_area_id"],
        "raw_city": "HCMC",
        "raw_area": "Go Vap",
        "source_area_label": "Go Vap, HCMC",
        "area_assignment": "qualified",
        "current_admin_status": "unverified_source_area",
        "current_boundary_uncertainty": (
            "Source-snapshot area labels are not a verified mapping to current "
            "administrative boundaries; current city/district status is unverified."
        ),
        "lineage_reference": "graph:POI.source_metadata_json#" + "c" * 64,
        "qualification": "exact_source_snapshot_tuple",
    }
    value.update(overrides)
    return value


def _evidence(selection=None, context=None, **overrides):
    payload = {
        "POI_ID": "poi_a",
        "POI_Name": "Source Cafe A",
        "POI_Address": "12 Le Loi, Go Vap, HCMC",
        "POI_Category": "Cafe",
        "latitude": 10.82,
        "longitude": 106.68,
        "POI_Description": {"insight": "quiet"},
        "POI_Contact_Info": {"website": "", "fanpage": "", "phonenumber": ""},
        "Offers": [],
        "POI_Categories": [{"id": "cat_coffee", "name": "Cafe"}],
        "administrative_context": None,
        "administrative_context_status": "unverified_source_area",
        "administrative_scope": "source_snapshot_area_only",
        "source_context": _context(selection) if context is None else context,
    }
    payload.update(overrides)
    return payload


def _request(**overrides):
    values = {
        "session_id": "sess-source",
        "current_city": "Ho Chi Minh City",
        "travel_type": "self-explore",
        "num_travelers": 2,
        "start_date": "2026-01-01",
        "duration_days": 1,
        "budget_range": "500000-1500000 VND",
        "user_description": "quiet cafes",
        "source_scope": SELECTION,
    }
    values.update(overrides)
    return ItineraryRequest(**values)


def _model_plan():
    return {
        "start_poi_id": "poi_a",
        "end_poi_id": "poi_a",
        "total_estimated_budget": 1000.0,
        "stops": [{
            "date": "2026-01-01",
            "visit_time": "2026-01-01T09:00:00+07:00",
            "end_time": "2026-01-01T11:00:00+07:00",
            "description": "model text",
            "budget": 1000.0,
            "poi": {"id": "poi_a"},
        }],
    }


# ---------------------------------------------------------------------------
# Request boundary
# ---------------------------------------------------------------------------
def test_source_request_without_target_district_is_accepted():
    request = _request()
    assert request.target_district is None
    assert request.source_scope.dataset_namespace == NAMESPACE
    assert request.source_scope.input_sha256 == SNAPSHOT
    assert request.source_scope.source_area_id == AREA_ID


def test_target_district_remains_required_without_source_scope():
    for body in ({"target_district": None}, {"target_district": "   "}):
        values = {
            "session_id": "s",
            "travel_type": "self-explore",
            "num_travelers": 2,
            "start_date": "2026-01-01",
            "duration_days": 1,
            "budget_range": "100000 VND",
            "user_description": "x",
        }
        values.update(body)
        with pytest.raises(ValidationError):
            ItineraryRequest(**values)


def test_source_request_rejects_extra_selector_key():
    with pytest.raises(ValidationError):
        _request(source_scope=_selection(extra="not allowed"))


@pytest.mark.parametrize("field,value", [
    ("input_sha256", "A" * 64),
    ("input_sha256", "a" * 63),
    ("input_sha256", "g" * 64),
    ("source_area_id", "quan_1"),
    ("source_area_id", "source_area_v1:" + "B" * 64),
    ("source_area_id", "district_v1:" + "b" * 64),
    ("dataset_namespace", " hcm_primary_geojson"),
    ("dataset_namespace", "hcm_primary_geojson "),
    ("dataset_namespace", "   "),
])
def test_source_request_rejects_malformed_values(field, value):
    with pytest.raises(ValidationError):
        _request(source_scope=_selection(**{field: value}))


@pytest.mark.parametrize("value", [True, 123, 1.5, ["a"], {"a": "b"}, None])
def test_source_request_rejects_coerced_or_nonobject_selection(value):
    with pytest.raises(ValidationError):
        _request(source_scope=value)


def test_source_selection_bytes_are_preserved():
    namespace = "snapshot.HCM_2026"
    request = _request(source_scope=_selection(dataset_namespace=namespace))
    assert request.source_scope.dataset_namespace == namespace
    parsed = grounding.parse_source_selection(request.source_scope)
    assert parsed.ok
    assert parsed.data == _selection(dataset_namespace=namespace)


# ---------------------------------------------------------------------------
# parse_source_selection (grounding, pure)
# ---------------------------------------------------------------------------
def test_parse_source_selection_accepts_exact_triple():
    outcome = grounding.parse_source_selection(SELECTION)
    assert outcome.ok
    assert outcome.data == SELECTION


def test_parse_source_selection_rejects_extra_key():
    assert not grounding.parse_source_selection(
        _selection(scope_mode="source")).ok


def test_parse_source_selection_rejects_nonstring_and_bool():
    for field in SELECTION:
        assert not grounding.parse_source_selection(
            _selection(**{field: True})).ok
        assert not grounding.parse_source_selection(
            _selection(**{field: 7})).ok


def test_parse_source_selection_rejects_whitespace_namespace():
    assert not grounding.parse_source_selection(
        _selection(dataset_namespace=" " + NAMESPACE)).ok
    assert not grounding.parse_source_selection(
        _selection(dataset_namespace=NAMESPACE + " ")).ok


def test_parse_source_selection_rejects_bad_hash_and_area_id():
    assert not grounding.parse_source_selection(
        _selection(input_sha256="A" * 64)).ok
    assert not grounding.parse_source_selection(
        _selection(input_sha256="a" * 63)).ok
    assert not grounding.parse_source_selection(
        _selection(source_area_id="quan_1")).ok


def test_ai_never_derives_source_area_id():
    assert not hasattr(grounding, "derive_source_area_id")
    assert not hasattr(grounding, "derive_source_area")


# ---------------------------------------------------------------------------
# poi_source_scope_status (pure predicate)
# ---------------------------------------------------------------------------
def test_poi_source_scope_status_qualified_on_exact_match():
    assert grounding.poi_source_scope_status(_evidence(), SELECTION) == "qualified"


@pytest.mark.parametrize("overrides", [
    {"source_area_id": "source_area_v1:" + "d" * 64},
    {"dataset_namespace": "other_snapshot"},
    {"input_sha256": "d" * 64},
    {"qualification": "assumed"},
    {"area_assignment": "unassigned"},
    {"current_admin_status": "verified"},
    {"source_area_label": "   "},
    {"current_boundary_uncertainty": ""},
    {"lineage_reference": None},
    {"extra_field": "not compact"},
])
def test_poi_source_scope_status_conflict_on_malformed_or_mismatched_context(overrides):
    evidence = _evidence(context=_context(**overrides))
    assert grounding.poi_source_scope_status(evidence, SELECTION) == "conflict"


def test_poi_source_scope_status_conflict_when_admin_context_present():
    evidence = _evidence(administrative_context=dict(ADMIN_CONTEXT))
    assert grounding.poi_source_scope_status(evidence, SELECTION) == "conflict"


def test_poi_source_scope_status_conflict_when_source_only_status_is_wrong():
    for field, value in (
        ("administrative_context_status", "resolved"),
        ("administrative_scope", None),
        ("administrative_scope", "administrative"),
    ):
        evidence = _evidence(**{field: value})
        assert grounding.poi_source_scope_status(evidence, SELECTION) == "conflict"


def test_poi_source_scope_status_unknown_when_context_missing_or_not_object():
    assert grounding.poi_source_scope_status(
        _evidence(source_context=None), SELECTION) == "unknown"
    assert grounding.poi_source_scope_status(
        _evidence(source_context="not an object"), SELECTION) == "unknown"
    assert grounding.poi_source_scope_status({}, SELECTION) == "unknown"


def test_poi_source_scope_status_requires_raw_labels_for_qualified_assignment():
    for field in ("raw_city", "raw_area"):
        evidence = _evidence(context=_context(**{field: None}))
        assert grounding.poi_source_scope_status(evidence, SELECTION) == "conflict"


def test_poi_source_scope_status_does_not_trust_cached_flags_or_labels_alone():
    evidence = _evidence(source_context=None)
    evidence["administrative_scope"] = "source_snapshot_area_only"
    evidence["administrative_context_status"] = "unverified_source_area"
    assert grounding.poi_source_scope_status(evidence, SELECTION) == "unknown"


# ---------------------------------------------------------------------------
# Cross-contract negatives
# ---------------------------------------------------------------------------
def test_poi_scope_status_ignores_source_context():
    assert grounding.poi_scope_status(_evidence(), DISTRICT, CITY) == "unknown"


def test_administrative_record_never_qualifies_as_source():
    admin_only = {
        "POI_ID": "poi_admin",
        "administrative_context": dict(ADMIN_CONTEXT),
        "administrative_context_status": "resolved",
    }
    assert grounding.poi_source_scope_status(admin_only, SELECTION) == "unknown"


# ---------------------------------------------------------------------------
# Prompt / plan evidence composition
# ---------------------------------------------------------------------------
def test_compact_source_prompt_fact_omits_provenance_and_admin():
    fact = grounding.compact_source_prompt_fact(_evidence())
    text = json.dumps(fact)
    assert fact["POI_ID"] == "poi_a"
    assert fact["source_area_label"] == "Go Vap, HCMC"
    for forbidden in ("lineage_reference", "source_metadata", "raw_lineage",
                      "administrative_context", SNAPSHOT, AREA_ID):
        assert forbidden not in text


def test_source_plan_stop_has_null_current_admin_and_compact_source_claim():
    result = grounding.validate_and_reconstruct_plan(
        _model_plan(), {"poi_a": _evidence()}, None, None,
        "2026-01-01", 1, source_selection=SELECTION)
    assert result.ok
    poi = result.stops[0]["poi"]
    assert poi["address"]["district"] is None
    assert poi["address"]["city"] is None
    assert poi["current_admin_status"] == "unverified_source_area"
    claim = poi["source_snapshot_area"]
    assert claim["source_area_id"] == AREA_ID
    assert claim["qualification"] == "exact_source_snapshot_tuple"
    assert "lineage_reference" not in claim
    assert result.scope_verifications == ["qualified_source_snapshot_area"]
    assert "stops[0].address.district" in result.missing_data
    assert "stops[0].address.city" in result.missing_data


def test_source_plan_rejects_stop_with_mismatched_source_context():
    evidence = _evidence(context=_context(
        source_area_id="source_area_v1:" + "d" * 64))
    result = grounding.validate_and_reconstruct_plan(
        _model_plan(), {"poi_a": evidence}, None, None,
        "2026-01-01", 1, source_selection=SELECTION)
    assert not result.ok
    assert result.code == grounding.SCOPE_CONFLICT


def test_source_plan_rejects_non_source_record():
    evidence = {
        "POI_ID": "poi_a",
        "administrative_context": dict(ADMIN_CONTEXT),
        "administrative_context_status": "resolved",
    }
    result = grounding.validate_and_reconstruct_plan(
        _model_plan(), {"poi_a": evidence}, None, None,
        "2026-01-01", 1, source_selection=SELECTION)
    assert not result.ok
    assert result.code == grounding.SCOPE_CONFLICT
