"""OC-016-R1 focused regressions: dropped hard constraints and dimension truth.

Independently reproduced counterexamples:

* an unknown required category was silently dropped from the scenario;
* an out-of-trip meal window silently disappeared;
* explicit malformed/incomplete budget fields silently became "no budget";
* any ``partial`` report was mapped to *both* route and hours ``violated``, and a
  single-stop plan reported route ``unverifiable`` instead of ``not_applicable``.

Every check is in-process (fake MCP + fake Gemini); no live collaborator.
"""

from decimal import Decimal

from domains import planning_adapter
from helpers_ai_grounding import default_handlers, evidence, make_request
from helpers_planning_integration import good_llm, route_handler, run_endpoint, stop_plan

EVIDENCE = {"poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC")}
CATEGORIES = {"poi_a": ["cat_coffee"]}


# ---------------------------------------------------------------------------
# 1. required_categories must not be silently dropped
# ---------------------------------------------------------------------------
def test_unknown_required_category_is_preserved_not_dropped():
    request = make_request(required_categories=["missing_required"])
    inputs = planning_adapter.build_scenario(
        request, EVIDENCE, CATEGORIES, [], None)

    assert inputs.build_error is None
    assert inputs.scenario.required_categories == ("missing_required",)
    assert any("required_category_unknown:missing_required" == u
               for u in inputs.unknowns)


def test_unknown_required_category_fails_closed_end_to_end(monkeypatch):
    handlers = default_handlers(candidates=["poi_a"], enrichments=EVIDENCE)
    handlers["get_itinerary_route"] = route_handler()
    request = make_request(required_categories=["missing_required"])
    result, _ = run_endpoint(monkeypatch, handlers,
                             good_llm(stop_plan([("poi_a", 1000.0)])), request=request)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "insufficient_data"
    unsatisfied = result["planning"]["validation"]["unsatisfied_required"]
    assert any("missing_required" in item for item in unsatisfied)


# ---------------------------------------------------------------------------
# 2. meal_windows must never silently disappear
# ---------------------------------------------------------------------------
def _meal_scenario(meal):
    request = make_request(duration_days=1, meal_windows=[meal])
    return planning_adapter.build_scenario(request, EVIDENCE, CATEGORIES, [], None)


def test_out_of_trip_meal_window_is_rejected():
    inputs = _meal_scenario({"category_id": "cat_coffee",
                             "start": "2026-01-03T11:00:00+07:00",
                             "end": "2026-01-03T13:00:00+07:00"})
    assert inputs.build_error is not None
    assert inputs.build_error[0] == "invalid_request"
    assert "outside the trip" in inputs.build_error[1]


def test_naive_meal_window_is_rejected():
    inputs = _meal_scenario({"category_id": "cat_coffee",
                             "start": "2026-01-01T11:00:00",
                             "end": "2026-01-01T13:00:00"})
    assert inputs.build_error is not None
    assert inputs.build_error[0] == "invalid_request"


def test_overnight_meal_window_is_rejected():
    inputs = _meal_scenario({"category_id": "cat_coffee",
                             "start": "2026-01-01T23:00:00+07:00",
                             "end": "2026-01-02T01:00:00+07:00"})
    assert inputs.build_error is not None
    assert "overnight" in inputs.build_error[1]


def test_unknown_meal_category_is_rejected():
    inputs = _meal_scenario({"category_id": "cat_ghost",
                             "start": "2026-01-01T11:00:00+07:00",
                             "end": "2026-01-01T12:00:00+07:00"})
    assert inputs.build_error is not None
    assert "unknown_meal_category" in inputs.build_error[1]


def test_meal_outside_day_window_is_rejected():
    inputs = _meal_scenario({"category_id": "cat_coffee",
                             "start": "2026-01-01T20:00:00+07:00",
                             "end": "2026-01-01T21:00:00+07:00"})
    assert inputs.build_error is not None
    assert "outside the day window" in inputs.build_error[1]


def test_valid_in_trip_meal_window_is_preserved():
    inputs = _meal_scenario({"category_id": "cat_coffee",
                             "start": "2026-01-01T11:00:00+07:00",
                             "end": "2026-01-01T12:00:00+07:00"})
    assert inputs.build_error is None
    assert len(inputs.scenario.days[0].meal_windows) == 1
    assert inputs.scenario.days[0].meal_windows[0].category_id == "cat_coffee"


def test_duplicate_day_window_is_rejected():
    request = make_request(day_windows=[
        {"date": "2026-01-01", "start": "2026-01-01T08:00:00+07:00",
         "end": "2026-01-01T10:00:00+07:00"},
        {"date": "2026-01-01", "start": "2026-01-01T12:00:00+07:00",
         "end": "2026-01-01T14:00:00+07:00"},
    ])
    inputs = planning_adapter.build_scenario(request, EVIDENCE, CATEGORIES, [], None)
    assert inputs.build_error is not None
    assert "duplicate_day_window" in inputs.build_error[1]


def test_day_window_date_timestamp_mismatch_is_rejected():
    request = make_request(day_windows=[
        {"date": "2026-01-01", "start": "2026-01-02T08:00:00+07:00",
         "end": "2026-01-02T10:00:00+07:00"},
    ])
    inputs = planning_adapter.build_scenario(request, EVIDENCE, CATEGORIES, [], None)
    assert inputs.build_error is not None
    assert "does not match" in inputs.build_error[1]


def test_valid_two_day_windows_are_retained():
    request = make_request(duration_days=2, day_windows=[
        {"date": "2026-01-01", "start": "2026-01-01T08:00:00+07:00",
         "end": "2026-01-01T20:00:00+07:00"},
        {"date": "2026-01-02", "start": "2026-01-02T10:00:00+07:00",
         "end": "2026-01-02T16:00:00+07:00"},
    ])
    inputs = planning_adapter.build_scenario(request, EVIDENCE, CATEGORIES, [], None)
    assert inputs.build_error is None
    assert len(inputs.scenario.days) == 2
    assert inputs.request_constraints["day_window_source"] == "user"
    assert not any(a.startswith("day_window:") for a in inputs.assumptions)


def test_out_of_trip_meal_detected_before_route_calls(monkeypatch):
    handlers = default_handlers(candidates=["poi_a"], enrichments=EVIDENCE)
    handlers["get_itinerary_route"] = route_handler()
    request = make_request(meal_windows=[{
        "category_id": "cat_coffee",
        "start": "2026-01-03T11:00:00+07:00",
        "end": "2026-01-03T13:00:00+07:00"}])
    result, session = run_endpoint(
        monkeypatch, handlers, good_llm(stop_plan([("poi_a", 1000.0)])), request=request)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "invalid_request"
    assert not any(call["tool"] == "get_itinerary_route" for call in session.calls)


# ---------------------------------------------------------------------------
# 3. explicit malformed/incomplete budget must fail, legacy stays unknown
# ---------------------------------------------------------------------------
def test_fatal_budget_reasons_are_classified():
    assert planning_adapter.budget_reason_is_fatal(
        "budget_amount_requires_positive_amount_and_currency")
    assert planning_adapter.budget_reason_is_fatal("invalid_budget_unit")
    assert planning_adapter.budget_reason_is_fatal("incomplete_budget_fields")
    assert not planning_adapter.budget_reason_is_fatal(
        "ambiguous_or_unsupported_budget_range_not_parsed")
    assert not planning_adapter.budget_reason_is_fatal("no_budget_supplied")


def test_incomplete_budget_fields_fail_parse():
    constraint, reason = planning_adapter.parse_budget_constraint(
        make_request(budget_currency="VND"))
    assert constraint is None
    assert reason == "incomplete_budget_fields"


def test_per_person_budget_without_party_fails():
    request = {"budget_amount": 1000, "budget_currency": "VND",
               "budget_unit": "per_person", "num_travelers": 0}
    constraint, reason = planning_adapter.parse_budget_constraint(request)
    assert constraint is None
    assert reason == "per_person_budget_requires_party_size"


def test_malformed_explicit_budget_fails_end_to_end_before_routes(monkeypatch):
    handlers = default_handlers(candidates=["poi_a"], enrichments=EVIDENCE)
    handlers["get_itinerary_route"] = route_handler()
    request = make_request(budget_amount="not-a-number", budget_currency="VND")
    result, session = run_endpoint(
        monkeypatch, handlers, good_llm(stop_plan([("poi_a", 1000.0)])), request=request)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "invalid_request"
    assert result["planning"]["budget_parse_reason"] == \
        "budget_amount_requires_positive_amount_and_currency"
    assert not any(call["tool"] == "get_itinerary_route" for call in session.calls)


def test_legacy_ambiguous_budget_remains_disclosed_unknown(monkeypatch):
    handlers = default_handlers(candidates=["poi_a"], enrichments=EVIDENCE)
    handlers["get_itinerary_route"] = route_handler()
    result, _ = run_endpoint(
        monkeypatch, handlers, good_llm(stop_plan([("poi_a", 1000.0)])),
        request=make_request())  # default "500000-1500000 VND" range

    assert result["status"] == "success"
    assert result["planning"]["budget_constraint"] is None
    assert result["planning"]["budget_parse_reason"] == \
        "ambiguous_or_unsupported_budget_range_not_parsed"


# ---------------------------------------------------------------------------
# 4. dimension-specific feasibility (no cross-poisoning, no vacuous verified)
# ---------------------------------------------------------------------------
def test_unrelated_requirement_does_not_poison_route_or_hours(monkeypatch):
    enrich = {"poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC",
                                operation_time="08:00-22:00")}
    handlers = default_handlers(candidates=["poi_a"], enrichments=enrich)
    handlers["get_itinerary_route"] = route_handler()
    request = make_request(required_categories=["missing_required"])
    result, _ = run_endpoint(
        monkeypatch, handlers, good_llm(stop_plan([("poi_a", 1000.0)])), request=request)

    assert result["planning"]["validator_status"] == "partial"
    assert result["grounding"]["route_feasibility"] != "violated"
    assert result["grounding"]["opening_hours_feasibility"] != "violated"
    # Required-category failure is not a route or hours violation code.
    codes = {v["code"] for v in result["planning"]["validation"]["known_violations"]}
    assert "travel_infeasible" not in codes
    assert "opening_violation" not in codes


def test_single_stop_route_is_not_applicable(monkeypatch):
    handlers = default_handlers(candidates=["poi_a"], enrichments=EVIDENCE)
    handlers["get_itinerary_route"] = route_handler()
    result, _ = run_endpoint(
        monkeypatch, handlers, good_llm(stop_plan([("poi_a", 1000.0)])))

    assert result["grounding"]["route_feasibility"] == "not_applicable"
    assert result["planning"]["validation"]["stop_count"] == 1


def test_no_plan_is_never_verified(monkeypatch):
    # A tiny explicit day window cannot fit any visit -> scheduler refuses.
    enrich = {"poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC")}
    handlers = default_handlers(candidates=["poi_a"], enrichments=enrich)
    handlers["get_itinerary_route"] = route_handler()
    request = make_request(day_windows=[{
        "date": "2026-01-01", "start": "2026-01-01T09:00:00+07:00",
        "end": "2026-01-01T09:01:00+07:00"}])
    result, _ = run_endpoint(
        monkeypatch, handlers, good_llm(stop_plan([("poi_a", 1000.0)])), request=request)

    assert result["status"] == "failed"
    assert result["planning"]["validator_status"] == "no_plan"
    assert result["planning"]["verified"] is False
    assert result["grounding"]["route_feasibility"] == "unknown"
    assert result["grounding"]["opening_hours_feasibility"] == "unknown"


# ---------------------------------------------------------------------------
# 5. verified must disclose conditional-on-assumptions semantics
# ---------------------------------------------------------------------------
def test_verified_discloses_conditional_assumptions(monkeypatch):
    handlers = default_handlers(candidates=["poi_a"], enrichments=EVIDENCE)
    handlers["get_itinerary_route"] = route_handler()
    result, _ = run_endpoint(
        monkeypatch, handlers, good_llm(stop_plan([("poi_a", 1000.0)])))

    planning = result["planning"]
    assert result["status"] == "success"  # guarded: a proposal was delivered
    assert planning["verified"] is False   # not all facts known (cost unknown)
    assert planning["verified_conditionally_on_assumptions"] is False
    assert planning["facts_fully_known"] is False
    assert planning["assumptions"]              # default day window/visit disclosed
    assert "status=success" in planning["status_semantics"]
