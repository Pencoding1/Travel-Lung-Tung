# ADR 011 — Planner integration into `/generate_itinerary`

- Status: accepted
- Date: 2026-10-15
- Task: OC-016
- Supersedes: none
- Related: `ai_service/domains/planning_adapter.py` (new),
  `ai_service/domains/planning/` (OC-010), ADR 004, ADR 008,
  `docs/project/handoffs/OC-016/`

## Context

ADR 004 grounds and reconstructs every factual field of `/generate_itinerary`
from MCP evidence, but never *scheduled* it: route and opening-hours feasibility
were left `unverified` and the model's timestamps were trusted once monotonic.
ADR 008 delivered a pure deterministic scheduler plus an independently
implemented validator, but deliberately left integration to a later owner
("not yet wired into `main.py`").

The MT4 hybrid condition requires the real request path to (a) build a typed
scenario from verified evidence only, (b) collect real directed route evidence,
(c) let the scheduler recompute times/order, and (d) let the independent
validator decide the final status. It also forbids presenting a mock success as
live evidence, fabricating facts, or promoting prices/budgets into source costs.

## Decision

### 1. One adapter, no invented facts

`ai_service/domains/planning_adapter.py` is the only bridge between grounding
evidence and the planner. It:

- parses request constraints into typed values (`parse_budget_constraint`,
  `parse_operation_time`, `build_scenario`);
- collects directed route edges from the **real** MCP tool
  (`collect_route_edges`);
- renders the validator/scheduler output to JSON-safe summaries.

It imports only `domains.grounding` and the stdlib-only planning package; it
performs no network/model/DB I/O itself and receives the MCP session as an
async `call_tool` seam.

### 2. Grounding fail-closed sequence is unchanged

`/generate_itinerary` still runs the exact OC-004/OC-005 sequence
(`resolve → categories → explore → enrich → scope → synthesis → grounding
reconstruction`). Unknown/mismatched POI ids, out-of-scope POIs, ambiguous
geography, malformed model JSON and invalid/naive/non-monotonic times are
rejected *before* planning. Only then is a typed scenario built from the
verified POI subset.

### 3. Model proposal is a preference input, not a schedule

The validated model plan is recorded verbatim as `planning.initial_proposal` and
used only to derive deterministic per-category preference weights (earlier
proposed stop ⇒ higher weight). The scheduler recomputes actual arrival/
departure times, order and budget; the independent validator
(`domains.planning.validator`) determines the final status. No preference score
is claimed from prompt content alone.

### 4. Real directed route evidence, bounded and disclosed

For every directed candidate pair the adapter calls the real
`get_itinerary_route` tool with the **actual** argument names
(`ordered_poi_ids`, `vehicle="car"`). It parses `success`, `distance_km`,
`time_minutes`, `stops_mapped`, and — when present — validates that the returned
ordered stop ids equal the requested pair.

- `time_minutes`→ raw seconds (integer) → `ceil` minutes; `distance_km` → integer
  meters with an exact reconciling decimal string. Raw seconds/meters are kept on
  the edge for provenance and the round-up is disclosed.
- A missing/failed/unknown pair is **never** substituted with `0` or a Haversine
  estimate; it is absent from the route index and recorded as
  `route_unknown`/failure.
- The pair pool is explicit: `selected_pairs`, `attempted_pairs`,
  `skipped_pairs`, `cap_reason` and `coverage` are all exposed; the cap
  (`MAX_ROUTE_PAIRS`) is disclosed and never silent. Collection is bounded by a
  concurrency semaphore, a per-call timeout, and no retry.

### 5. Narrow hours and price policy

- Opening hours are parsed **only** for an explicit `24/7` token or a single
  daily `HH:MM-HH:MM` range. Weekday lists, holidays, multiple ranges and
  overnight spans are `unsupported` ⇒ hours unknown (never "always open"). The
  original text and parser status are retained (`planning.hours_parser`).
- A `get_poi_details` menu/offer price is **not** an admission/visit cost and is
  never promoted. The current tool exposes no explicit planning cost, so every
  POI cost stays `None` (unknown); `planning.cost` reports
  `menu_offers_repurposed: false` and `model_budget_promoted_to_source_cost:
  false`.
- Dates are interpreted in Vietnam time (UTC+07:00).

### 6. Explicit constraints, disclosed assumptions

Request constraints are typed and validated: optional explicit
`day_windows`, `budget_amount`/`budget_currency`/`budget_unit`, `minimum_stops`,
`maximum_stops`, `visit_minutes`, `required_categories` and `meal_windows`. The
free-form `budget_range` is parsed only when it is a single unambiguous
`<amount> <CUR>` token; ranges are rejected rather than guessed. When no day
window or visit duration is supplied, a default is applied **only** as a
recorded planning assumption, never as a POI fact or user statement.

### 7. Honest statuses and withholding

`planning.validator_status` is the validator's verdict. Known-violating
(`partial`) schedules and refusals (`no_plan`) are **withheld**: the endpoint
fails closed (`insufficient_data`) with the reasons and the proposal preserved.
`feasible`/`unverifiable` proposals are delivered with `planning.verified` and
limitation fields; a `success` is therefore never a bare, unqualified claim.
Real provider usage is surfaced when present and stays `None` otherwise.

### 8. Corrective fix: cumulative budget

The scheduler's budget check summed only completed prior days, so stops already
placed on the in-progress day were invisible. Two 60-per-party stops under a 100
per-party budget were both admitted, producing a `partial`/`budget_exceeded`
plan although a single valid stop exists. The check now sums prior days **and**
the current day's stops before adding a candidate
(`domains/planning/scheduler.py`, `_known_stop_cost`). Unknown costs remain
unknown and are skipped (never zero), so a known subtotal still bounds later
candidates.

## Alternatives considered

- **Trust the model schedule and only re-timestamp.** Rejected: not
  independently validated and cannot incorporate real route evidence.
- **Substitute `0`/Haversine for missing pairs.** Rejected: fabricates evidence.
- **Parse `budget_range` ranges or offers as costs.** Rejected: ambiguous /
  not the same semantic; would promote estimates to facts.
- **Deliver a `partial` schedule as "success".** Rejected: known violations must
  not be presented as verified.

## Consequences

- The live path now uses the OC-010 scheduler + independent validator. Because
  the current tools expose no admission cost and only coarse hours, most live
  plans will be `unverifiable` by design — an honest result, not a failure.
- Assertion changes in the retained suite are limited to the OC-016 response
  contract (`route_feasibility`/`opening_hours_feasibility` now reflect the
  validator) plus additive `get_itinerary_route` fakes; all grounding assertions
  are preserved.
- `docs/decisions/008-deterministic-planning.md` §5 ("not yet wired") is now
  realized by this ADR.

## Repair (R1) — dropped hard constraints and dimension truth

An independent review reproduced four integration defects. The bounded
correction (OC-016-R1) changes only the adapter, the integration block, tests
and docs; the scheduler keeps only the OC-016 cumulative-budget fix.

1. **Unknown required categories are no longer dropped.** `required_categories`
   entries that no verified POI can satisfy are carried into the scenario so the
   independent validator reports them `unsatisfied_required` (a preserved
   impossibility); the endpoint then fails closed rather than delivering an
   unconstrained substitute. `_resolve_required_categories`.
2. **Meal windows are validated, never silently discarded.** A meal on a date
   outside the trip, a naive/overnight/inverted interval, an out-of-day-window
   meal or an unknown meal category is rejected (`invalid_request`); accepted
   meals are attached to their day. Explicit `day_windows` reject duplicates,
   out-of-trip dates and date/timestamp mismatches. `validate_constraints`
   performs these checks **before** any `get_itinerary_route` call, and
   `build_scenario` reuses the same helpers so the typed payload and adapter
   defenses agree.
3. **Explicit malformed/incomplete budget fails closed.** `budget_amount`
   without a valid amount/currency or `budget_unit`, an invalid unit, an
   unknown per-person party size, or currency/unit supplied without an amount
   are fatal (`FATAL_BUDGET_REASONS`); only an absent or legacy
   free-form/ambiguous `budget_range` remains a disclosed unknown
   (`LEGACY_UNKNOWN_BUDGET_REASONS`).
4. **Dimension-specific feasibility.** `route_feasibility` is `violated` only
   for the route violation codes, `not_applicable` when the schedule has no
   inter-stop leg (a single stop), `verified` only when the required directed
   edges are complete, else `unverifiable`; `opening_hours_feasibility` is
   `violated` only for `opening_violation`. An unrelated required-category/budget
   failure no longer poisons either dimension, and `no_plan`/empty is `unknown`
   (never a vacuous `verified`).
5. **Qualified verification.** `planning.verified` is the validator's `feasible`
   verdict; `planning.verified_conditionally_on_assumptions` is true only when
   that verdict holds and disclosed assumptions (default day window / visit
   policy) were used, and `planning.facts_fully_known` is true only with no
   assumptions and no source unknowns. Top-level `status: "success"` is retained
   for compatibility and means only "a grounded proposal was delivered"; the
   qualifier fields (and `planning.status_semantics`) carry the feasibility
   claim.
6. **Strict route-payload binding.** A present `stops` field that is empty,
   not a list, or contains non-object/blank-id entries is a `malformed_stops`
   failure; absence of the field remains accepted for upstream compatibility.
   When present, the ordered ids must equal the requested pair.
