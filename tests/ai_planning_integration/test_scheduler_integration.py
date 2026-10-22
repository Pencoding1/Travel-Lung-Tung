"""Endpoint-level deterministic-repair and honesty tests (OC-016).

The real ``/generate_itinerary`` pipeline runs with fake MCP payloads and a fake
Gemini. The scheduler must recompute times/order from actual route evidence and
the independent validator must decide the status. Missing facts stay unknown and
are never fabricated as zero/Haversine.
"""

from domains import planning_adapter
from helpers_ai_grounding import default_handlers, evidence, make_request
from helpers_planning_integration import (
    good_llm,
    route_handler,
    run_endpoint,
    stop_plan,
)

ADMIN = None  # default admin context from `evidence`


def _handlers(candidates, enrichments, route=None):
    handlers = default_handlers(candidates=candidates, enrichments=enrichments)
    if route is not None:
        handlers["get_itinerary_route"] = route
    return handlers


def test_overly_fast_transfer_is_repaired(monkeypatch):
    enrich = {
        "poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC",
                          operation_time="08:00-22:00"),
        "poi_b": evidence("poi_b", "B", "2 Le Loi, Quan 1, HCMC",
                          operation_time="08:00-22:00"),
    }
    handlers = _handlers(["poi_a", "poi_b"], enrich,
                         route_handler(duration_minutes=30.0))
    model = stop_plan([("poi_a", 1000.0), ("poi_b", 2000.0)])

    result, _ = run_endpoint(monkeypatch, handlers, good_llm(model))

    assert result["status"] == "success"
    planned = result["planning"]["repaired_schedule"]["days"][0]["stops"]
    assert [s["poi_id"] for s in planned] == ["poi_a", "poi_b"]
    assert planned[1]["travel_from_prev_minutes"] == 30
    # 09:00 + 60 visit + 30 travel = 10:30 (the model's 10:01 is repaired).
    assert planned[1]["arrival"] == "2026-01-01T10:30:00+07:00"
    assert result["planning"]["initial_proposal"]["sequence"] == ["poi_a", "poi_b"]


def test_closing_wait_is_respected(monkeypatch):
    enrich = {"poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC",
                                operation_time="14:00-18:00")}
    handlers = _handlers(["poi_a"], enrich, route_handler())
    model = stop_plan([("poi_a", 1000.0)], start_hour=9)

    result, _ = run_endpoint(monkeypatch, handlers, good_llm(model))

    assert result["status"] == "success"
    stop = result["planning"]["repaired_schedule"]["days"][0]["stops"][0]
    assert stop["arrival"].startswith("2026-01-01T14:00:00")
    assert result["planning"]["hours_parser"]["poi_a"]["status"] == "daily_window"
    assert result["planning"]["hours_parser"]["poi_a"]["source_text"] == "14:00-18:00"


def test_route_asymmetry_is_respected(monkeypatch):
    enrich = {
        "poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC"),
        "poi_b": evidence("poi_b", "B", "2 Le Loi, Quan 1, HCMC"),
    }

    durations = {("poi_a", "poi_b"): 10.0, ("poi_b", "poi_a"): 90.0}

    def asymmetric(args):
        from helpers_ai_grounding import ok_json
        ids = args["ordered_poi_ids"]
        return ok_json({"success": True, "distance_km": 1.0,
                        "time_minutes": durations[tuple(ids)],
                        "stops_mapped": 2,
                        "stops": [{"id": p} for p in ids]})

    handlers = _handlers(["poi_a", "poi_b"], enrich, asymmetric)
    model = stop_plan([("poi_a", 1000.0), ("poi_b", 2000.0)])
    result, _ = run_endpoint(monkeypatch, handlers, good_llm(model))

    planned = result["planning"]["repaired_schedule"]["days"][0]["stops"]
    assert [s["poi_id"] for s in planned] == ["poi_a", "poi_b"]
    assert planned[1]["travel_from_prev_minutes"] == 10
    records = {(r["from_poi_id"], r["to_poi_id"]): r["duration_minutes"]
               for r in result["planning"]["route_evidence"]["records"]}
    assert records[("poi_a", "poi_b")] == 10
    assert records[("poi_b", "poi_a")] == 90


def test_missing_route_is_unknown_not_zero(monkeypatch):
    enrich = {
        "poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC"),
        "poi_b": evidence("poi_b", "B", "2 Le Loi, Quan 1, HCMC"),
    }
    handlers = _handlers(["poi_a", "poi_b"], enrich,
                         route_handler(fail_pairs={("poi_a", "poi_b"),
                                                   ("poi_b", "poi_a")}))
    model = stop_plan([("poi_a", 1000.0), ("poi_b", 2000.0)])
    result, _ = run_endpoint(monkeypatch, handlers, good_llm(model))

    assert result["status"] == "success"
    route_evidence = result["planning"]["route_evidence"]
    assert route_evidence["failed"]
    assert all(r["duration_minutes"] is None
               for r in route_evidence["records"] if r["status"] != "success")
    assert result["planning"]["validator_status"] == "unverifiable"
    # The unreachable candidate is excluded with an explicit missing-route
    # reason, never defaulted to a zero leg.
    excluded = result["planning"]["repaired_schedule"]["excluded"]
    assert any(e["reason"].startswith("route_unknown:") for e in excluded)


def test_provider_error_is_recorded_and_never_crashes(monkeypatch):
    enrich = {
        "poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC"),
        "poi_b": evidence("poi_b", "B", "2 Le Loi, Quan 1, HCMC"),
    }
    handlers = _handlers(["poi_a", "poi_b"], enrich, route_handler(provider_error=True))
    model = stop_plan([("poi_a", 1000.0), ("poi_b", 2000.0)])
    result, _ = run_endpoint(monkeypatch, handlers, good_llm(model))

    assert result["status"] in ("success", "failed")
    route_evidence = result["planning"]["route_evidence"]
    assert route_evidence["failed"]
    assert all("code" in f for f in route_evidence["failed"])


def test_complex_hours_stay_unknown(monkeypatch):
    enrich = {"poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC",
                                operation_time="Mon-Fri 08:00-17:00")}
    handlers = _handlers(["poi_a"], enrich, route_handler())
    model = stop_plan([("poi_a", 1000.0)])
    result, _ = run_endpoint(monkeypatch, handlers, good_llm(model))

    assert result["status"] == "success"
    planning = result["planning"]
    assert planning["hours_parser"]["poi_a"]["status"] == "unsupported"
    assert planning["hours_parser"]["poi_a"]["source_text"] == "Mon-Fri 08:00-17:00"
    assert any("hours_unknown:poi_a" in u for u in planning["source_unknowns"])
    assert result["grounding"]["opening_hours_feasibility"] == "unverifiable"


def test_known_hours_and_complete_route_are_flagged_verified(monkeypatch):
    enrich = {
        "poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC",
                          operation_time="08:00-22:00"),
        "poi_b": evidence("poi_b", "B", "2 Le Loi, Quan 1, HCMC",
                          operation_time="08:00-22:00"),
    }
    handlers = _handlers(["poi_a", "poi_b"], enrich, route_handler())
    model = stop_plan([("poi_a", 1000.0), ("poi_b", 2000.0)])
    result, _ = run_endpoint(monkeypatch, handlers, good_llm(model))

    assert result["grounding"]["opening_hours_feasibility"] == "verified"
    assert result["grounding"]["route_feasibility"] == "verified"


def test_party_and_currency_constraints_flow(monkeypatch):
    enrich = {"poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC")}
    handlers = _handlers(["poi_a"], enrich, route_handler())
    model = stop_plan([("poi_a", 1000.0)])
    request = make_request(budget_amount=120000, budget_currency="VND",
                           budget_unit="per_person", num_travelers=4)
    result, _ = run_endpoint(monkeypatch, handlers, good_llm(model), request=request)

    constraints = result["planning"]["request_constraints"]
    assert constraints["party_size"] == 4
    assert constraints["currency"] == "VND"
    assert result["planning"]["budget_constraint"]["amount"] == "480000"
    assert result["planning"]["budget_constraint"]["unit"] == "per_party"


def test_foreign_poi_never_reaches_the_scenario(monkeypatch):
    enrich = {"poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC")}
    handlers = _handlers(["poi_a"], enrich, route_handler())
    model = stop_plan([("poi_ghost", 1000.0)])
    result, _ = run_endpoint(monkeypatch, handlers, good_llm(model))

    assert result["status"] == "failed"
    assert result["error"]["code"] == "unknown_poi"
    assert "planning" not in result


def test_zero_pois_fail_closed(monkeypatch):
    handlers = default_handlers(candidates=[])
    result, _ = run_endpoint(monkeypatch, handlers, good_llm(stop_plan([])))

    assert result["status"] == "failed"
    assert result["error"]["code"] == "insufficient_data"


def test_route_calls_are_bounded(monkeypatch):
    ids = [f"poi_{i}" for i in range(9)]
    enrich = {pid: evidence(pid, pid, f"{i} Le Loi, Quan 1, HCMC")
              for i, pid in enumerate(ids)}
    calls = {"n": 0}
    base = route_handler()

    def counting(args):
        calls["n"] += 1
        return base(args)

    handlers = _handlers(ids, enrich, counting)
    model = stop_plan([(ids[0], 1000.0)])
    result, _ = run_endpoint(monkeypatch, handlers, good_llm(model))

    assert calls["n"] <= planning_adapter.MAX_ROUTE_PAIRS
    assert result["planning"]["route_evidence"]["attempted"] <= planning_adapter.MAX_ROUTE_PAIRS
    assert result["planning"]["route_evidence"]["cap_reason"] == planning_adapter.ROUTE_CAP_REASON


def test_deterministic_repair(monkeypatch):
    enrich = {
        "poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC",
                          operation_time="08:00-22:00"),
        "poi_b": evidence("poi_b", "B", "2 Le Loi, Quan 1, HCMC",
                          operation_time="08:00-22:00"),
    }
    model = stop_plan([("poi_a", 1000.0), ("poi_b", 2000.0)])
    first, _ = run_endpoint(monkeypatch, _handlers(["poi_a", "poi_b"], enrich,
                                                   route_handler(duration_minutes=20.0)),
                            good_llm(model))
    second, _ = run_endpoint(monkeypatch, _handlers(["poi_a", "poi_b"], enrich,
                                                    route_handler(duration_minutes=20.0)),
                             good_llm(model))

    assert (first["planning"]["repaired_schedule"]["days"]
            == second["planning"]["repaired_schedule"]["days"])
    assert first["planning"]["validator_status"] == second["planning"]["validator_status"]
