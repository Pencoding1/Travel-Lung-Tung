# ADR 008 — Deterministic itinerary scheduler behind an independent validator

- Status: accepted
- Date: 2026-10-15
- Task: OC-010
- Supersedes: none
- Related: `ai_service/domains/planning/`, `ai_service/domains/grounding.py`
  (read-only), `docs/experiments/EXPERIMENT_PROTOCOL.md` (E3), ADR 004,
  ADR 006

## Context

`/generate_itinerary` (ADR 004) grounds POIs and rejects unverified facts, but it
never *scheduled* them: it asked the model for stops and only checked that the
timestamps were monotonic inside the trip window. Route feasibility and
opening-hours feasibility were deliberately left `unverified`. The experiment
protocol (E3 / MT4 / H2) requires a hybrid condition with deterministic
validation and disclosed bounded heuristics, and it explicitly forbids treating
a successful solver output as proof of feasibility: "feasibility must be
independently reviewed from the snapshot".

There was no typed input/output contract, no route-evidence contract, no explicit
unknown-vs-infeasible separation, and no way to reproduce a comparison without
inventing results.

## Problem

How do we add a pure, deterministic, reproducible scheduler whose output is
re-checked by an *independent* implementation, while (a) never synthesizing a
coordinate/name/price/hours fact, (b) never substituting zero or Haversine for a
missing directed route, (c) distinguishing source uncertainty from proven
infeasibility from heuristic failure, and (d) staying stdlib-only and out of the
live request path until a separate integration task owns `main.py`?

## Decision

### 1. A stdlib-only typed contract package

`ai_service/domains/planning/contracts.py` defines frozen dataclasses for the
scenario, POIs, days, directed route edges, costs and opening windows, plus
`parse_scenario`, which is the only door into the planner. It imports no provider
SDK, database driver, HTTP client, graph client or model library.

Hard rules enforced at parse time (each raises a stable `ScenarioError.code`):

- **Ids, not facts.** Only stable `poi_id`/`category_id`/`day_id` strings are
  accepted. Coordinates and names are not part of the contract, so they cannot
  be synthesized.
- **Exact numbers.** Time is integer minutes since the Unix epoch; money and
  distance are exact `Decimal`s accepted only as integers or decimal strings.
  `bool` and `float` are rejected so binary floating point can never round a
  route sum. Instants must be timezone-aware ISO-8601 at minute resolution.
- **Explicit units/currency.** Costs carry a currency and a `per_person`/
  `per_party` unit; the trip budget must be `per_party`; currency must match the
  scenario. `per_person` is multiplied by party size exactly.
- **Unknown is not zero.** An absent `cost` is `None`; an absent `opening_windows`
  is `hours_known = False`; a missing directed edge is not in the route index.
  A legitimate free price is the explicit string `"0"`.
- **Strict rejection, not truncation.** Duplicate POI/day ids, duplicate directed
  edges, `start >= end` intervals, meal windows outside their day, unknown id
  references, naive/non-minute datetimes and over-limit candidate/day/edge/route
  counts are all rejected before scheduling.

### 2. A bounded deterministic heuristic

`ai_service/domains/planning/scheduler.py` is a pure function. Days are processed
in order; candidates are ranked by hard-requirement coverage first (required
category / required meal window), then preference weight, then directed travel
time, then POI id. A candidate is placed at the earliest feasible instant inside a
*known* opening window (waiting before opening allowed); on the final day with an
end depot a return buffer is reserved. Missing travel excludes the candidate with
an explicit `route_unknown` reason; missing hours/cost are recorded as unknown
reasons rather than being treated as satisfied. The heuristic makes **no** global
optimum or infeasibility certificate claim; a greedy miss is reported as
`heuristic_failure`, not as proof that no plan exists.

### 3. An independent validator

`ai_service/domains/planning/validator.py` is a *separate* implementation that
never calls scheduler feasibility helpers. It recomputes every timing, travel,
cost and constraint check from the raw scenario evidence plus the ordered stops:

- `arrival >= previous departure + directed travel (or depot departure + travel)`;
- positive visit interval at least the required `visit_minutes`;
- visit contained in a known opening window and inside the day window;
- return to the end depot inside the day window;
- duplicate POIs, unknown ids, budget from recomputed party cost, currency;
- required categories, meal windows and the explicit `minimum_stops`.

It reports known violations separately from unknown/unverifiable facts and
preserves refusals: a `no_plan` result stays `no_plan` and is never presented as
a zero-violation success. Forged plan cost/time fields cannot change the verdict
because every threshold comes from source data.

Statuses are therefore: `feasible` (all declared constraints known and met),
`unverifiable` (no known violation, but at least one unknown fact), `partial`
(a known violation or an unsatisfied declared requirement) and `no_plan`
(refusal). The scheduler's final status is the validator's verdict.

### 4. A frozen synthetic harness

`benchmarks/planning/scenarios.json` freezes exactly 20 hand-authored synthetic
scenarios *before* benchmarking, each with author-declared expected properties
that the scheduler never reads. They cover 1/2 days, party size, low/high
budgets, directed asymmetry, tight closing, waiting, long transfers, required
meal windows, sparse/empty/infeasible/missing-hour/missing-route/missing-price
cases and five distinct preference profiles. `benchmarks/planning/benchmark.py`
runs the scheduler *and* the independent validator on each, records raw
input/output/validation/elapsed/seed/version/file hashes, and reports aggregate
counts including refusals. It explicitly marks the LLM-only condition,
provider-token estimates and H2/H3 significance as **unavailable** — no
statistical or original-dataset claim is produced.

### 5. Integration contract (not yet wired)

This task does not touch `main.py`. A later owner integrates as follows:

1. `parse_scenario(raw)` where `raw` is built from grounded evidence only: POI
   ids/category ids from MCP, `visit_minutes`/`cost`/`opening_windows` from
   `get_poi_details` (absent when unknown), and a directed `route_edges` matrix
   from `get_itinerary_route` with `transport_mode` and `provenance`. Never build
   an edge from a name or a Haversine distance.
2. `plan = schedule(scenario)`.
3. `report = validate(scenario, plan)`.
4. Return `plan` only when `report.status == "feasible"`; otherwise surface the
   status, `unknown_reasons`, `unsatisfied_required` and `excluded` reasons and
   fail closed exactly as ADR 004 does.

## Repair (v2) — corrective QA

An independent review rejected the first validator submission. The following
original requirements are now enforced, without changing the frozen v1 manifest
semantics (only no-plan *reason* strings changed; see the manifest
``version_history``):

1. **Structural validation is mandatory.** The validator no longer trusts
   ``status``/``sequence``. It checks a matching ``scenario_id``, unique day ids
   in declared chronological order, no undeclared day, per-day ``max_stops`` and
   the canonical stop count/sequence recomputed from the day stops. It iterates
   **scenario** days (not just plan days) so an omitted day cannot hide an
   unmet meal window or depot obligation. An empty itinerary can never be
   ``feasible``; a declared ``no_plan`` that still contains stops is fully
   checked (``no_plan_with_stops``) rather than bypassed.
2. **Overlap enforcement is independent of route knowledge.** ``arrival >=
   previous departure`` is always enforced; when the directed edge is known the
   stronger ``arrival >= departure + travel`` applies, and a missing edge is
   reported separately as unknown. If the sum of the *known* costs alone already
   exceeds the budget, that is a known ``budget_exceeded`` violation even when
   another cost is unknown. Cost/budget currency and unit are re-checked from
   the source dataclasses.
3. **Explicit multi-day overnight semantics.** The last scheduled stop of a day
   is carried as the origin for the next day; an empty day leaves the origin
   unchanged. A missing interday transfer excludes the candidate / stays
   unknown — never zero or a teleport. A same-id transfer is a known zero only
   when the ids actually match. Start/end depots are not bypassed by empty
   leading/final days: the depot is carried as the origin until a stop is placed,
   and the required end-depot return is repaired (trailing stops dropped) if it
   would not fit the day window.
4. **Parse-time envelope.** Day windows must be chronological and
   non-overlapping and the declared ``date`` must match the day-window start
   date. A scenario-level ``transport_mode``, if declared, must match every edge
   (per-leg modes are the explicit default otherwise). Durations are integer
   minutes: ``raw_duration_seconds`` is accepted and rounded **up** by
   ``ceil_minutes_from_seconds`` (never down); an explicit ``duration_minutes``
   must equal that ceiling, and ``raw_distance_meters`` must reconcile with
   ``distance_km``. Integration must disclose the round-up; raw seconds/meters
   are preserved on the edge for provenance. The validator now also returns a
   recomputed **distance** total alongside travel time, including outbound,
   interday and return legs.
5. **Honest no-plan taxonomy.** ``impossible_constraints`` was removed. When no
   formal infeasibility proof exists the reason is ``no_verified_plan`` (or
   ``heuristic_no_plan``-equivalent) or ``search_limit`` when the iteration bound
   was reached; ``infeasible_bounds`` is used only when every candidate was
   excluded by a *known* single-stop bound (budget/opening/day window), which is
   a formal single-stop proof. All missing-route reasons are preserved on the
   refusal instead of being discarded by the validator's no-plan path.

## Alternatives considered

- **Let the model schedule and validate post-hoc.** Rejected: E3 forbids treating
  solver success as feasibility and the model cannot supply a directed route
  matrix.
- **One class that schedules and validates.** Rejected: the same defects would
  validate themselves; the protocol requires one independent validator.
- **Substitute Haversine/zero for a missing edge.** Rejected: it fabricates
  evidence. Missing edges are excluded/unknown.
- **Treat absent cost/hours as zero/open.** Rejected: indistinguishable from a
  real value; both stay unknown and block `feasible`.
- **Silently cap candidates/days.** Rejected: required facts would be dropped;
  over-limit inputs are rejected instead.
- **Claim infeasibility when greedy fails.** Rejected: only reported as
  `heuristic_failure`/`impossible_constraints` with no optimum claim.

## Consequences

- Positive: a reproducible, dependency-free planning core with an independently
  re-verifiable output, honest unknown-vs-infeasible separation and a frozen
  engineering harness. `parse_scenario` makes unsafe inputs unrepresentable.
- Trade-off: because missing hours/cost cannot yield `feasible`, callers must
  supply explicit hours and prices (including `"0"`) to obtain a `feasible`
  verdict; otherwise the result is `unverifiable` by design.
- Evidence boundary: all 20 scenarios are synthetic and excluded from the
  original thesis dataset. No model, network, graph or database call is made.
  No H2/H3 statistic is computed (see `docs/project/handoffs/OC-010/`).
