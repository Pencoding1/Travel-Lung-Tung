"""Narrow hours/price/budget policy tests (OC-016).

Only a documented narrow hours format is accepted; anything complex stays
unknown. Menu offer prices are never repurposed as admission cost; the
free-form ``budget_range`` is parsed only when unambiguous, and explicit fields
are typed/validated.
"""

from decimal import Decimal

from domains import planning_adapter
from helpers_ai_grounding import evidence, make_request, ok_json


# --- hours -----------------------------------------------------------------
def test_always_open_token_is_recognized():
    parsed = planning_adapter.parse_operation_time("24/7")
    assert parsed.status == "always_open"
    assert parsed.original == "24/7"


def test_single_daily_range_is_parsed():
    parsed = planning_adapter.parse_operation_time("08:00-18:00")
    assert parsed.status == "daily_window"
    assert (parsed.start_hm, parsed.end_hm) == ("08:00", "18:00")


def test_range_whitespace_and_single_digit_hours():
    parsed = planning_adapter.parse_operation_time("8:00 - 17:30")
    assert parsed.status == "daily_window"
    assert (parsed.start_hm, parsed.end_hm) == ("08:00", "17:30")


def test_complex_weekday_string_is_unsupported_not_open():
    parsed = planning_adapter.parse_operation_time("Mon-Fri 08:00-17:00")
    assert parsed.status == "unsupported"
    assert parsed.original == "Mon-Fri 08:00-17:00"
    assert parsed.start_hm is None


def test_overnight_and_multi_range_are_unsupported():
    assert planning_adapter.parse_operation_time("18:00-02:00").status == "unsupported"
    assert planning_adapter.parse_operation_time("08:00-12:00, 13:00-17:00").status == "unsupported"


def test_absent_hours_is_absent():
    assert planning_adapter.parse_operation_time(None).status == "absent"
    assert planning_adapter.parse_operation_time("   ").status == "absent"


# --- budget ----------------------------------------------------------------
def test_explicit_budget_fields_are_typed():
    request = make_request(budget_amount=1000000, budget_currency="vnd",
                           budget_unit="per_party")
    constraint, reason = planning_adapter.parse_budget_constraint(request)
    assert reason is None
    assert constraint.amount == Decimal("1000000")
    assert constraint.currency == "vnd"
    assert constraint.unit == "per_party"


def test_per_person_budget_is_normalized_with_party_size():
    request = make_request(budget_amount=500000, budget_currency="VND",
                           budget_unit="per_person", num_travelers=3)
    constraint, _ = planning_adapter.parse_budget_constraint(request)
    assert constraint.amount == Decimal("1500000")
    assert constraint.unit == "per_party"


def test_ambiguous_budget_range_is_not_quietly_parsed():
    # Default request budget_range is a range and carries a unit-less ambiguity.
    constraint, reason = planning_adapter.parse_budget_constraint(make_request())
    assert constraint is None
    assert "ambiguous" in reason


def test_single_amount_budget_range_is_parsed():
    request = make_request(budget_range="1000000 VND")
    constraint, reason = planning_adapter.parse_budget_constraint(request)
    assert reason is None
    assert constraint.amount == Decimal("1000000")
    assert constraint.currency == "VND"
    assert constraint.source == "budget_range"


def test_budget_amount_without_currency_is_rejected():
    request = make_request(budget_amount=1000, budget_currency=None)
    constraint, reason = planning_adapter.parse_budget_constraint(request)
    assert constraint is None
    assert "must_be_parsed" in reason or "currency" in reason


# --- price policy ----------------------------------------------------------
def test_menu_offer_price_is_not_promoted_to_visit_cost():
    ev = evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC",
                  offers=[{"name": "Coffee", "price": 25000}])
    inputs = planning_adapter.build_scenario(
        make_request(), {"poi_a": ev}, {"poi_a": ["cat_coffee"]}, [], None)
    assert inputs.build_error is None
    poi = inputs.scenario.poi("poi_a")
    assert poi.cost is None  # unknown, never the menu price
    assert inputs.cost_policy["menu_offers_repurposed"] is False
    assert inputs.cost_policy["status"] == "unknown"
