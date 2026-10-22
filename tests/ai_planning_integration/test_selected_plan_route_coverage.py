"""CORE-071: capped pair ordering + selected-plan route coverage.

Covers the two defects Codex diagnosed from the actual CORE-070 car receipt:

1. the 60-pair cap was filled from a lexicographic row prefix, so the model's
   own proposal origin had no outgoing edge and the scheduler collapsed the
   plan to a singleton ``route_unknown`` exclusion;
2. route feasibility was labelled from *candidate-pool* coverage, so a known
   selected leg stayed unverifiable only because unrelated pairs were never
   attempted.

All route payloads here are scripted in-process; no network call is made.
"""

import asyncio

import pytest

from domains import planning_adapter
from helpers_planning_integration import (
    default_handlers,
    evidence,
    good_llm,
    ok_json,
    route_handler,
    run_endpoint,
    stop_plan,
)
from helpers_ai_grounding import make_request


def _collect(handler, poi_ids, **kwargs):
    calls = []

    async def call_tool(name, args):
        calls.append((name, dict(args)))
        return handler(args)

    edges, ev = asyncio.run(
        planning_adapter.collect_route_edges(call_tool, poi_ids, **kwargs))
    return edges, ev, calls


def _pool(n):
    return [f"poi_{index:02d}" for index in range(n)]


# ---------------------------------------------------------------------------
# 1. model-proposal priority survives the cap
# ---------------------------------------------------------------------------
def test_proposal_legs_are_collected_even_when_origin_sorts_late():
    pool = _pool(18)
    # The model's first stop sorts after the lexicographic first four ids, which
    # is exactly the CORE-070 shape (first proposal id starved by the cap).
    priority = ["poi_14", "poi_02", "poi_11"]

    _, ev, calls = _collect(route_handler(), pool, priority_sequence=priority)

    assert ev.total_directed_pairs == 18 * 17
    assert len(ev.selected_pairs) == planning_adapter.MAX_ROUTE_PAIRS
    assert ev.cap_reason == planning_adapter.ROUTE_CAP_REASON
    assert ev.skipped_pairs
    assert ev.coverage == "partial"

    # Directed consecutive proposal legs, then their reverse, come first.
    assert ev.selected_pairs[:4] == [
        ("poi_14", "poi_02"), ("poi_02", "poi_11"),
        ("poi_02", "poi_14"), ("poi_11", "poi_02"),
    ]
    assert ev.priority_pairs == ev.selected_pairs[:4]
    call_pairs = [tuple(args["ordered_poi_ids"]) for _, args in calls]
    assert ("poi_14", "poi_02") in call_pairs
    assert ("poi_02", "poi_11") in call_pairs


def test_priority_does_not_change_the_legacy_uncapped_behaviour():
    _, ev, calls = _collect(route_handler(), ["p2", "p1"],
                            priority_sequence=["p1"])
    assert set(ev.selected_pairs) == {("p1", "p2"), ("p2", "p1")}
    assert ev.skipped_pairs == [] and ev.cap_reason is None
    assert ev.coverage == "complete"
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# 2. balanced origins: no lexicographic row prefix and no starved origin
# ---------------------------------------------------------------------------
def test_capped_selection_is_balanced_across_origins():
    pool = _pool(18)
    _, ev, _ = _collect(route_handler(), pool,
                        priority_sequence=["poi_14", "poi_02"])

    assert ev.origins_total == 18
    assert len(ev.origins_attempted) == 18
    # The last id is reachable as an origin, not only as a target.
    assert "poi_17" in ev.origins_attempted
    # Still bounded and still honest about what was left out.
    assert len(ev.selected_pairs) == planning_adapter.MAX_ROUTE_PAIRS
    assert ev.selected_pairs + ev.skipped_pairs
    assert len(set(ev.selected_pairs) & set(ev.skipped_pairs)) == 0


def test_small_budget_still_covers_every_origin_once():
    pool = _pool(6)
    _, ev, calls = _collect(route_handler(), pool, max_pairs=8)
    assert len(ev.selected_pairs) == 8
    assert len(ev.origins_attempted) == 6
    assert len(calls) == 8
    assert ev.coverage == "partial"


# ---------------------------------------------------------------------------
# 3. duplicate / foreign priority can never widen the pool
# ---------------------------------------------------------------------------
def test_foreign_and_duplicate_priority_never_triggers_a_foreign_call():
    pool = ["poi_a", "poi_b", "poi_c"]
    priority = ["poi_b", "ghost_x", "poi_b", 7, "", "  ", "poi_a"]

    _, ev, calls = _collect(route_handler(), pool, priority_sequence=priority)

    assert ev.priority_sequence == ["poi_b", "poi_a"]
    assert ev.priority_ignored_count == 4
    attempted_ids = {pid for pair in ev.selected_pairs for pid in pair}
    assert attempted_ids == set(pool)
    for _, args in calls:
        assert set(args["ordered_poi_ids"]) <= set(pool)


# ---------------------------------------------------------------------------
# 4. tiny cap / zero cap / failed pair stay partial with explicit gaps
# ---------------------------------------------------------------------------
def test_zero_cap_attempts_nothing_and_reports_missing_pairs():
    pool = ["poi_a", "poi_b"]
    edges, ev, calls = _collect(route_handler(), pool, max_pairs=0)

    assert edges == [] and calls == []
    assert ev.selected_pairs == []
    assert len(ev.skipped_pairs) == 2
    assert ev.coverage == "partial"
    coverage = planning_adapter.selected_plan_route_coverage(
        ["poi_a", "poi_b"], ev, transport_mode="car")
    assert coverage["coverage"] == "partial"
    assert coverage["missing_pairs"] == [["poi_a", "poi_b"]]


def test_failed_selected_leg_is_missing_not_defaulted():
    edges, ev, _ = _collect(route_handler(fail_pairs={("poi_a", "poi_b")}),
                            ["poi_a", "poi_b"])
    coverage = planning_adapter.selected_plan_route_coverage(
        ["poi_a", "poi_b"], ev, transport_mode="car")
    assert coverage["coverage"] == "partial"
    assert coverage["missing_pairs"] == [["poi_a", "poi_b"]]
    # A successful reverse edge never satisfies the required direction.
    assert coverage["successful_pairs"] == []
    assert coverage["verified"] is False


def test_malformed_numeric_payload_never_counts_as_a_leg():
    def handler(args):
        return ok_json({"success": True, "distance_km": "1.2",
                        "time_minutes": 5.0})

    _, ev, _ = _collect(handler, ["poi_a", "poi_b"])
    assert ev.coverage == "partial"
    coverage = planning_adapter.selected_plan_route_coverage(
        ["poi_a", "poi_b"], ev, transport_mode="car")
    assert coverage["coverage"] == "partial"


def test_timeout_is_recorded_and_left_missing():
    async def call_tool(_name, _args):
        await asyncio.sleep(5)

    edges, ev = asyncio.run(planning_adapter.collect_route_edges(
        call_tool, ["poi_a", "poi_b"], timeout=0.01))
    assert edges == []
    assert all(r.code == "route_timeout" for r in ev.records)
    coverage = planning_adapter.selected_plan_route_coverage(
        ["poi_a", "poi_b"], ev, transport_mode="car")
    assert coverage["coverage"] == "partial"


# ---------------------------------------------------------------------------
# 5. directions are never mirrored
# ---------------------------------------------------------------------------
def test_asymmetric_route_never_mirrors_the_reverse_direction():
    _, ev, _ = _collect(route_handler(fail_pairs={("poi_b", "poi_a")}),
                        ["poi_a", "poi_b"])
    forward = planning_adapter.selected_plan_route_coverage(
        ["poi_a", "poi_b"], ev, transport_mode="car")
    reverse = planning_adapter.selected_plan_route_coverage(
        ["poi_b", "poi_a"], ev, transport_mode="car")

    assert forward["coverage"] == "complete"
    assert forward["verified"] is True
    assert reverse["coverage"] == "partial"
    assert reverse["missing_pairs"] == [["poi_b", "poi_a"]]


# ---------------------------------------------------------------------------
# 6. selected-plan coverage vs candidate-pool coverage / singleton
# ---------------------------------------------------------------------------
def test_selected_legs_can_verify_while_the_unrelated_pool_stays_partial():
    _, ev, _ = _collect(route_handler(), _pool(18))
    assert ev.coverage == "partial"          # capped pool is partial
    coverage = planning_adapter.selected_plan_route_coverage(
        ["poi_14", "poi_02"], ev, transport_mode="car")
    assert coverage["candidate_pool_coverage"] == "partial"
    assert coverage["required_pairs"] == [["poi_14", "poi_02"]]
    assert coverage["coverage"] == "complete"
    assert coverage["verified"] is True


def test_single_stop_is_not_applicable_not_vacuously_verified():
    coverage = planning_adapter.selected_plan_route_coverage(
        ["poi_a"], planning_adapter.RouteEvidence(), transport_mode="car")
    assert coverage["coverage"] == "not_applicable"
    assert coverage["verified"] is False
    assert coverage["required_pairs"] == []


def test_declared_depot_legs_are_required_too():
    _, ev, _ = _collect(route_handler(), ["poi_a", "poi_b"])
    coverage = planning_adapter.selected_plan_route_coverage(
        ["poi_a"], ev, transport_mode="car", start_depot_id="poi_b")
    assert coverage["required_pairs"] == [["poi_b", "poi_a"]]
    assert coverage["coverage"] == "complete"


def test_wrong_transport_mode_evidence_is_not_accepted():
    coverage = planning_adapter.selected_plan_route_coverage(
        ["poi_a", "poi_b"],
        planning_adapter.RouteEvidence(
            transport_mode="foot",
            records=[planning_adapter.RouteRecord(
                "poi_a", "poi_b", "success", transport_mode="foot")]),
        transport_mode="car")
    assert coverage["coverage"] == "partial"


# ---------------------------------------------------------------------------
# 7. end-to-end: 2 delivered stops verified while the pool is partial
# ---------------------------------------------------------------------------
def test_two_stop_plan_is_verified_while_pool_coverage_is_partial(monkeypatch):
    enrich = {
        "poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC",
                          operation_time="08:00-22:00"),
        "poi_b": evidence("poi_b", "B", "2 Le Loi, Quan 1, HCMC",
                          operation_time="08:00-22:00"),
        # Third candidate is unroutable *and* cannot open inside the day window,
        # so the scheduler deterministically delivers poi_a + poi_b only.
        "poi_c": evidence("poi_c", "C", "3 Le Loi, Quan 1, HCMC",
                          operation_time="01:00-02:00"),
    }
    handlers = default_handlers(candidates=["poi_a", "poi_b", "poi_c"],
                               enrichments=enrich)
    handlers["get_itinerary_route"] = route_handler(fail_pairs={
        ("poi_a", "poi_c"), ("poi_c", "poi_a"),
        ("poi_b", "poi_c"), ("poi_c", "poi_b"),
    })
    request = make_request(minimum_stops=2, maximum_stops=2)
    model = stop_plan([("poi_a", 1000.0), ("poi_b", 2000.0)])
    result, _ = run_endpoint(monkeypatch, handlers, good_llm(model), request=request)

    assert result["status"] == "success"
    planning = result["planning"]
    selected = planning["selected_plan_route"]
    assert selected["scope"] == "selected_plan"
    assert selected["transport_mode"] == "car"
    assert selected["coverage"] == "complete"
    assert selected["required_pairs"] == [["poi_a", "poi_b"]]
    assert selected["candidate_pool_coverage"] == "partial"
    # The capped pool question keeps its own honest, separate answer.
    assert planning["route_evidence"]["coverage_scope"] == "candidate_pool"
    assert planning["route_evidence"]["failed"]
    assert result["grounding"]["route_feasibility"] == "verified"
    assert result["grounding"]["route_coverage_scope"] == "selected_plan"
    assert result["grounding"]["candidate_pool_route_coverage"] == "partial"


def test_invalid_transport_mode_fails_before_any_route_call():
    calls = []

    async def call_tool(name, args):
        calls.append((name, dict(args)))
        return ok_json({"success": True})

    with pytest.raises(ValueError):
        asyncio.run(planning_adapter.collect_route_edges(
            call_tool, ["poi_a", "poi_b"], transport_mode="boat"))
    assert calls == []


# ---------------------------------------------------------------------------
# 8. multi-day schedules: per-day legs only, no invented cross-day edge
# ---------------------------------------------------------------------------
def _evidence_from(pairs, mode="car"):
    return planning_adapter.RouteEvidence(
        transport_mode=mode,
        records=[planning_adapter.RouteRecord(a, b, "success", transport_mode=mode)
                 for a, b in pairs])


def test_two_day_schedule_needs_no_cross_day_edge():
    days = [("d1", ["a", "b"]), ("d2", ["c", "d"])]
    coverage = planning_adapter.selected_plan_day_route_coverage(
        days, _evidence_from([("a", "b"), ("c", "d")]), transport_mode="car")

    assert coverage["coverage"] == "complete"
    assert coverage["verified"] is True
    assert coverage["required_pairs"] == [["a", "b"], ["c", "d"]]
    assert ["b", "c"] not in coverage["required_pairs"]
    assert coverage["cross_day_legs_invented"] is False
    assert coverage["day_count"] == 2
    assert [d["coverage"] for d in coverage["days"]] == ["complete", "complete"]


def test_each_day_requires_its_own_declared_depot_legs():
    days = [("d1", ["a", "b"]), ("d2", ["c", "d"])]
    covered = [("s", "a"), ("a", "b"), ("s", "c"), ("c", "d"), ("d", "t")]

    coverage = planning_adapter.selected_plan_day_route_coverage(
        days, _evidence_from(covered), transport_mode="car",
        start_depot_id="s", end_depot_id="t")

    assert coverage["days"][0]["required_pairs"] == [
        ["s", "a"], ["a", "b"], ["b", "t"]]
    assert coverage["days"][1]["required_pairs"] == [
        ["s", "c"], ["c", "d"], ["d", "t"]]
    # A missing daily return leg is not covered by the global last leg.
    assert coverage["coverage"] == "partial"
    assert coverage["verified"] is False
    assert coverage["missing_pairs"] == [["b", "t"]]
    assert coverage["successful_pairs"] == [["s", "a"], ["a", "b"],
                                            ["s", "c"], ["c", "d"], ["d", "t"]]


def test_empty_day_contributes_no_leg():
    days = [("d1", ["a", "b"]), ("d2", [])]
    coverage = planning_adapter.selected_plan_day_route_coverage(
        days, _evidence_from([("a", "b")]), transport_mode="car")

    assert coverage["coverage"] == "complete"
    assert coverage["required_pairs"] == [["a", "b"]]
    assert coverage["days"][1]["required_pairs"] == []
    assert coverage["days"][1]["coverage"] == "empty"


def test_one_day_wrapper_matches_the_daily_helper():
    evidence_obj = _evidence_from([("a", "b")])
    wrapper = planning_adapter.selected_plan_route_coverage(
        ["a", "b"], evidence_obj, transport_mode="car")
    daily = planning_adapter.selected_plan_day_route_coverage(
        [("d1", ["a", "b"])], evidence_obj, transport_mode="car")
    assert wrapper["coverage"] == daily["coverage"] == "complete"
    assert wrapper["required_pairs"] == daily["required_pairs"] == [["a", "b"]]


def test_multi_day_plan_does_not_require_a_cross_day_route(monkeypatch):
    enrich = {
        "poi_a": evidence("poi_a", "A", "1 Le Loi, Quan 1, HCMC",
                          operation_time="08:00-22:00"),
        "poi_b": evidence("poi_b", "B", "2 Le Loi, Quan 1, HCMC",
                          operation_time="08:00-22:00"),
    }
    handlers = default_handlers(candidates=["poi_a", "poi_b"], enrichments=enrich)
    handlers["get_itinerary_route"] = route_handler()
    request = make_request(duration_days=2, maximum_stops=1)
    model = stop_plan([("poi_a", 1000.0)])
    result, _ = run_endpoint(monkeypatch, handlers, good_llm(model), request=request)

    assert result["status"] == "success"
    selected = result["planning"]["selected_plan_route"]
    assert selected["daily_legs"] is True
    assert selected["day_count"] == 2
    # At most one stop per day means no within-day leg and (with no declared
    # depot) no leg at all: a flattened id list would have invented one.
    assert all(len(day["stop_ids"]) <= 1 for day in selected["days"])
    assert selected["required_pairs"] == []
    assert selected["coverage"] == "not_applicable"
    assert result["grounding"]["route_feasibility"] in (
        "not_applicable", "verified")

