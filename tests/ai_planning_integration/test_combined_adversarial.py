"""Combined adversarial-family integration tests (OC-016).

Family A (insufficient/unavailable data), family B (unsupported POI details /
plan structure) and family C (out-of-scope geography) are exercised together and
the pipeline must stay honest: unknown facts are never fabricated and a
known-violating schedule is withheld rather than delivered as verified.
"""

from domains import grounding
from helpers_ai_grounding import default_handlers, evidence, make_request
from helpers_planning_integration import (
    good_llm,
    route_handler,
    run_endpoint,
    stop_plan,
)


def _handlers(candidates, enrichments, route=None):
    handlers = default_handlers(candidates=candidates, enrichments=enrichments)
    if route is not None:
        handlers["get_itinerary_route"] = route
    return handlers


def test_scope_exclusion_then_foreign_poi_is_rejected(monkeypatch):
    # Family C: poi_b is out-of-scope and excluded from synthesis.
    # Family B: the model proposes the excluded id -> unknown POI, fail closed.
    enrich = {
        "poi_a": evidence("poi_a", "In", "1 Le Loi, Quan 1, HCMC"),
        "poi_b": evidence("poi_b", "Out", "9 Nguyen Trai, Quan 5, HCMC",
                          admin={"city_id": "hcmc", "district_id": "quan_5",
                                 "city_name": "Ho Chi Minh City",
                                 "district_name": "District 5"}),
    }
    handlers = _handlers(["poi_a", "poi_b"], enrich, route_handler())
    model = stop_plan([("poi_b", 1000.0)])
    result, _ = run_endpoint(monkeypatch, handlers, good_llm(model))

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.UNKNOWN_POI
    assert result["grounding"]["excluded_scope_conflicts"] == ["poi_b"]
    assert "planning" not in result


def test_unknown_facts_are_never_fabricated(monkeypatch):
    # Family A + B: unsupported complex hours, a menu price (not a visit cost),
    # and no route evidence for a single candidate. Everything must stay unknown.
    enrich = {
        "poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC",
                          operation_time="Weekends and holidays only",
                          offers=[{"name": "Latte", "price": 45000}]),
    }
    handlers = _handlers(["poi_a"], enrich, route_handler())
    model = stop_plan([("poi_a", 1000.0)])
    result, _ = run_endpoint(monkeypatch, handlers, good_llm(model))

    assert result["status"] == "success"
    planning = result["planning"]
    assert planning["validator_status"] == "unverifiable"
    assert planning["verified"] is False
    assert planning["hours_parser"]["poi_a"]["status"] == "unsupported"
    assert planning["cost"]["status"] == "unknown"
    assert planning["cost"]["known_party_subtotal"] is None
    assert planning["route_evidence"]["coverage"] == "empty"

    # The per-stop budget remains the model's labelled estimate, not a source cost.
    stop = result["reply"]["stops"][0]
    assert stop["budget"] == 1000.0
    assert stop["budget_is_estimate"] is True
    # The menu offer price never appears as a verified visit cost.
    assert stop["poi"]["menu"][0]["price_verified"] is False


def test_known_violating_schedule_is_withheld(monkeypatch):
    # One candidate cannot satisfy an explicit minimum of two stops: the
    # validator returns `partial`, and the schedule is withheld (never delivered
    # as verified), while the proposal is preserved.
    enrich = {"poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC")}
    handlers = _handlers(["poi_a"], enrich, route_handler())
    model = stop_plan([("poi_a", 1000.0)])
    request = make_request(minimum_stops=2)
    result, _ = run_endpoint(monkeypatch, handlers, good_llm(model), request=request)

    assert result["status"] == "failed"
    assert result["error"]["code"] == grounding.INSUFFICIENT_DATA
    planning = result["planning"]
    assert planning["validator_status"] == "partial"
    assert any("schedule_withheld:partial" == lim for lim in planning["limitations"])
    assert any("minimum_stops" in u for u in planning["validation"]["unsatisfied_required"])
    # The (valid but insufficient) model proposal is still recorded.
    assert planning["initial_proposal"]["sequence"] == ["poi_a"]


def test_no_preference_claim_from_prompt_injection(monkeypatch):
    # A model proposal cannot inject a preference score; the planner only ever
    # records deterministic category weights derived from the proposed order.
    enrich = {
        "poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC",
                          operation_time="08:00-22:00"),
        "poi_b": evidence("poi_b", "B", "2 Le Loi, Quan 1, HCMC",
                          operation_time="08:00-22:00"),
    }
    handlers = _handlers(["poi_a", "poi_b"], enrich, route_handler())
    model = stop_plan([("poi_b", 1000.0), ("poi_a", 2000.0)])
    result, _ = run_endpoint(monkeypatch, handlers, good_llm(model))

    # The model order is recorded verbatim as the proposal; the repaired
    # schedule is a scheduler decision, not a model preference score.
    assert result["planning"]["initial_proposal"]["sequence"] == ["poi_b", "poi_a"]
    assert "preference_score" not in result["planning"]
    assert "preference_scores" not in result
