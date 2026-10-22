# ADR 006 — MCP tool evidence contract (grounded geography, exact search, honest missing facts)

- Status: accepted
- Date: 2026-10-15
- Task: OC-007
- Supersedes: none
- Related: `POI_service/app/api/mcp/tools.py`,
  `POI_service/app/core/services/management.py`,
  `POI_service/app/core/domain/get_payload.py`,
  `POI_service/app/core/infrastructure/db/repositories/memgraph.py`,
  `docs/decisions/004-itinerary-grounding.md`

## Context

ADR 004 made the AI itinerary endpoint fail closed unless `get_poi_details`
exposes a structured `administrative_context`. The POI MCP tools did not:
`get_poi_details` had no parent geography, `explore_pois` did a *geography-first
then substring* category filter against a hard over-fetch (`FETCH_LIMIT = 200`),
`get_available_categories` returned `success=true` with no `categories` list when
empty, `search_location_id` returned ids without parent context, `Category`
create/update dropped `context`, and `get_itinerary_route` leaked tracebacks,
hard-coded the GraphHopper URL, resolved each stop in a nested UoW scope, and
fabricated zero distances. The audit found these were validated only against AI
mocks, not against the real tool contracts.

## Problem

How do we repair the real POI MCP tool contracts so that (a) grounded geography is
real, (b) exploration is exact and conjunctive, (c) missing facts are reported
truthfully, and (d) the module can be tested without a database — while keeping
tool names and the JSON envelope compatible and preserving the spatial code owned
by another task?

## Decision

### 1. One lazy, injectable collaborator factory

`tools.py` no longer imports the concrete `MemgraphUnitOfWork`/connector/
`POIManagementService` at module import time. A single `_uow_factory` (default
`_default_uow_factory`, which performs the concrete imports *inside* the
function) is injectable through `set_uow_factory`. Importing `tools` therefore
never opens a connection, reads `MEMGRAPH_*`/`.env` credentials, or imports
`neo4j`/`firebase_admin`. Tests inject a fake UnitOfWork; they do **not** patch
`sys.modules`. A subprocess test asserts the import stays clean.

### 2. Structured `administrative_context` from real relationships

`get_poi_graph_payload` gathers parent chains from both supported graph shapes:

- `(p)-[:LOCATE_AT]->(district)-[:IN_CITY]->(city)`
- `(p)-[:LOCATE_AT]->(street)-[:IN_DISTRICT]->(district)-[:IN_CITY]->(city)`

It returns the raw, de-duplicated chains. `resolve_administrative_context`
(pure) resolves them to `{city_id, district_id, city_name, district_name}` only
when exactly one distinct, complete chain exists. Zero chains → `missing`;
incomplete chains → `incomplete`; contradictory chains → `ambiguous` and a
**null** context (never the first arbitrary chain). Nothing is inferred from the
free-form address or from the requested ids. `POIResult` exposes both the context
and `administrative_context_status`, plus explicit `POI_Categories` ids,
`operation_time` and `missing_data`. `get_poi_details` returns the requested id
exactly or `not_found`.

### 3. Exact, conjunctive exploration before the limit

A new repository method `get_compound_explore_lite` applies every supplied
`city_id`/`district_id`/`street_id`/`category_id` conjunctively via exact-id
`EXISTS` matches, and only then applies `WITH DISTINCT p ORDER BY p.id SKIP
$offset LIMIT $limit`. Category ids are never rewritten to display names (the
old `replace("cat_", "")` substring match is gone), `product_keyword` is a bound
parameter against a textual field only, and the arbitrary `FETCH_LIMIT = 200`
over-fetch is removed. A `district_id` that does not belong to the supplied
`city_id` cannot satisfy both clauses, so inconsistent geography returns empty.
`limit` is bounded to `1..100` and `offset >= 0`; bad inputs raise
`invalid_request`. The lite contract carries structured category ids and the
resolved `administrative_context`.

### 4. Location resolution returns candidates with parent context

`search_location_id` returns the matched node's `id`/`type`/`name` plus parent
`city_id`/`city_name` (for a District) and parent `district_id`/`district_name`
plus `city_id`/`city_name` (for a Street), in a deterministic order with a
bounded limit. It returns candidates only; no automatic choice is made.

### 5. Honest missing facts, never fabricated values

- Document RAG unimplemented/failure → `POIDescription.status = "unavailable"`,
  null rating and empty text; never a fallback `0.0` rating.
- Offers keep a missing name/price as `null` (no "Unnamed Product", no free
  `0.0`); prices are validated finite and nonnegative.
- Distances are `null` when missing, never `0`.
- `Category` create/update persist and round-trip the required nonblank
  `context`; there is no empty fallback that would violate the domain.
- Tool errors use stable sanitized codes (`invalid_request`, `not_found`,
  `stops_unresolved`, `route_failed`, `no_route`, ...) with no tracebacks or raw
  provider messages. Empty `categories`/`matches`/`results` are always `[]` with
  `success=true`.

### 6. Routing contract

`get_itinerary_route` reads `GRAPHHOPPER_URL` via `os.getenv` only (no `.env`)
and accepts the profiles in `GRAPHHOPPER_PROFILES`, defaulting to `car` to match
`graphhopper/data/config.yml` (which enables only `car`). All ordered ids are
resolved in **one** fresh UnitOfWork scope; a missing id or coordinate aborts the
whole request with the failing ids and makes **no** HTTP call. Zero coordinates
are accepted; coordinates must be finite and in range. `point` parameters are
passed as a tuple list so httpx encodes them correctly. `distance`/`time` are
parsed defensively and returned unrounded as `distance_km`/`time_minutes`;
`stops_mapped` equals the requested count in order. HTTP failure, empty or
malformed payloads return an explicit error and never a fabricated route. Tests
use an injected `httpx.MockTransport` client factory.

## Alternatives considered

- **Keep the geography-priority + substring category filter.** Rejected: it
  over-fetches 200 rows, silently drops valid matches, and collapses `cat_a` into
  a display-name substring.
- **Infer `administrative_context` from the free-form address or requested ids.**
  Rejected: substrings are ambiguous/fabricable and requested ids are not
  evidence (ADR 004).
- **Resolve the first parent chain.** Rejected: contradictory chains must surface
  as unresolved, not silently pick one.
- **Import the concrete UoW at module top-level and patch `sys.modules` in
  tests.** Rejected: import must have no DB/credential side effects, and module
  faking hides real wiring defects.
- **Fabricate `0.0` for missing price/distance/rating.** Rejected: it is
  indistinguishable from a real value at the consumer.

## Consequences

- Positive: the AI's `administrative_context` dependency is now actually exposed
  by `get_poi_details`, so live scope verification can succeed; exploration is
  exact and deterministic; missing facts are truthful; the module is testable
  without a database.
- Trade-off: `explore_pois` and `get_itinerary_route` output shapes changed where
  the brief mandates it (`results` are structured lite items; route returns
  `distance_km`/`time_minutes`). No in-repo consumer relied on the old route keys.
- Evidence boundary: query behaviour is verified by **static query inspection**
  and **fake-transaction mapping**, and tool behaviour by **in-process calls plus
  real MCP registration/schema**. No live Memgraph, GraphHopper, model or network
  call is claimed (see `docs/project/handoffs/OC-007/`).
