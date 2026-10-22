# ADR 004 — Itinerary endpoint grounding boundary

- Status: accepted
- Date: 2026-10-15
- Task: OC-005
- Supersedes: none
- Related: `POI_service/app/api/mcp/tools.py`, `POI_service/app/core/domain/get_payload.py`

## Context

`ai_service/main.py` `/generate_itinerary` retrieved three hard-coded
categories, enriched IDs, and asked Gemini for a JSON plan. Nothing checked that
the plan referenced POIs that were actually retrieved, nothing prevented the
model from inventing names/hours/prices/addresses, and a failed or empty
retrieval still reached the model. The audit (`docs/audit/ARCHITECTURE_AS_IS.md`)
and `MASTER_GOAL.md` §3.3 explicitly separate *POI existence* from *attribute
correctness* from *freshly generated unsupported claims*.

## Problem

How do we make itinerary output grounded in retrieved graph evidence, without
rewriting the agent architecture and without overstating what can be verified
from the current MCP tools?

## Decision

Introduce a single pure grounding boundary, `ai_service/domains/grounding.py`,
and route the entire `/generate_itinerary` pipeline through it. `main.py` keeps
its role as the I/O orchestrator and the `tool_chain` observability contract.

### 1. Fail closed before the model

The candidate/enrichment pipeline is now explicit and initialized. If the
request is invalid, geography is unresolved/ambiguous, categories cannot be
discovered, candidates are empty, enrichments all fail, or all enriched POIs
contradict the requested scope, the endpoint returns a structured error with the
`tool_chain` and never calls the model. No invented fallback places.

### 2. Unique normalized exact geographic matching

Requested `current_city` and `target_district` are each resolved independently
and require a unique normalized exact match of the expected node type
(`City`/`District`). Normalization folds accents, case and whitespace and
explicitly folds the `District`/`Quan`/`Quận` alias to `quan`. This makes
"District 1", "Quan 1" and "Quận 1" equivalent while keeping `District 1`
distinct from `District 10`. Partial keyword matches, ambiguous matches,
type mismatches and unknown areas return `location_not_resolved`,
`location_ambiguous` or `location_type_mismatch` before synthesis.

Both city and district evidence are passed into `explore_pois` and recorded in
the response (`grounding.scope_evidence`).

### 3. Scope verification uses a structured contract and fails closed

Free-text address substrings are **never** used for scope: `"Quan 1"` is a
substring of `"Quan 10"`, and an address can be fabricated. Scope is decided
only from a structured `administrative_context` on the enrichment payload:

```
"administrative_context": {
  "city_id": "...", "district_id": "...",
  "city_name": "...", "district_name": "..."
}
```

All four fields must be nonblank strings. The POI is `verified` only when
`city_id`/`district_id` equal the resolved geography exactly and the names match
under the `District`/`Quan` alias normalization; otherwise it is a `conflict`.
Missing/invalid context is `unknown`. Resolver-provided parent city info on a
district match is preserved, and a district whose parent city conflicts with the
requested city is rejected.

Unknown and conflicting POIs are excluded and reported
(`excluded_scope_unknown`, `excluded_scope_conflicts`). Only the verified subset
may reach synthesis. If **no** POI verifies, the request fails closed before the
model: `scope_unverified` when context is missing/invalid, `scope_conflict` when
all candidates actively contradict the requested scope. There is no
`partially_grounded`/success substitute.

> This intentionally blocks live plans until the upstream MCP service exposes
> `administrative_context` on `get_poi_details`. A later task will implement that
> upstream field; until then the endpoint fails closed and documents the
> dependency in `grounding.upstream_dependency`.

### 4. Reconstruct facts from evidence, never copy the model

Every stop's factual fields (`name`, `latitude`, `longitude`, `address`,
`contact_info`, `menu`, `rating`, `operation_time`, categories) are rebuilt from
the `get_poi_details` evidence. Unknown POI ids, duplicate stops, empty stops,
mismatched `start_poi_id`/`end_poi_id`, non-aware or non-monotonic ISO
timestamps are rejected. All ids are validated as actual nonblank strings — an
enrichment whose returned `POI_ID` differs from the requested id is marked
`failed` in the trace and excluded (`enrichment_id_mismatch`).

- **Ratings:** the generic `POI_Description.review.rating` (Document-RAG
  fallback `0.0`) is never promoted to a named provider. Only explicit
  `rating_sources[provider]` entries for supported providers
  (`google_maps`, `tripadvisor`) with positive finite values are emitted;
  otherwise `rating` is `null` and listed in `missing_data`.
- **Coordinates:** present-but-nonfinite or out-of-range lat/lon make the whole
  enrichment unusable and it is rejected rather than propagated.
- **Offers:** a zero/absent price is set to `null` and never labelled verified
  (`price_verified: false`); no provenance is assumed.
- **Opening hours:** included only when the evidence explicitly has
  `operation_time`; otherwise `null` + `missing_data`. Feasibility stays
  `operation_time_feasibility: "unverified"`.

Model stop descriptions are removed and replaced with neutral selection text
(`description_grounded: false`); the free text is not presented as grounded.

### 5. Trip window, budgets and identity

- Stop date/time must lie within `[start_date, start_date + duration_days)` in
  the destination timezone (`+07:00`, declared Vietnam scope); end times may not
  extend past the trip. Visit intervals must be positive and non-overlapping.
- Negative or non-finite stop/total budgets are rejected (`budget_invalid`). The
  server reconciles `total_estimated_budget` to the sum of stop estimates and
  rejects a mismatch beyond tolerance. Budgets remain estimates, never prices.
- The model's `id`/`uid` are ignored. The server generates the itinerary id and
  binds `uid` to the supplied request context (`session_id`), or `null` if none;
  no identity is guessed from the model.

### 6. Honest feasibility reporting

Aware ISO timestamps and per-stop visit intervals are validated, but
`route_feasibility` and `opening_hours_feasibility` are reported
`"unverified"` until GraphHopper and opening-hours data are actually integrated.
The pipeline does not assert full hybrid completion.

### 7. Determinism and operational hygiene

Category and candidate selection sorts the valid unique ids before applying the
caps, so the selected subset is invariant to MCP response ordering. An invalid
parsed explore result marks the tool trace `failed`; an invalid model response
shape marks the synthesis trace `failed` and returns a sanitized structured
error (no processing state left behind, no internal exception). `prompt.json` is
loaded relative to `Path(__file__)`, and the synthesis call uses the configured
`GEMINI_MODEL`. The broad endpoint handler logs only the exception type (never
`repr(e)`). Tests inject fakes through module-level collaborator seams
(`open_mcp_session`, `gemini_chat_completion`) rather than faking the imported
`mcp`/`httpx` modules.

## Alternatives considered

- **Prompt engineering only.** Rejected: instructions cannot prove grounding or
  temporal feasibility (`MASTER_GOAL.md` §3.3).
- **Hard-code categories / accept first fuzzy match.** Rejected: invents IDs and
  silently mislabels geography; the original defect.
- **Resolve geography by substring/CONTAINS.** Rejected: `District 1` is a
  substring of `District 10`, and CONTAINS is what the tool already does; exact
  normalized matching is required.
- **Assume all district-scoped POIs are same-city.** Rejected: the enrichment
  payload lacks structured parent context, so this would be unsupported. Such
  candidates are excluded and, if none verify, the request fails closed.
- **Trust free-text address substrings for scope.** Rejected: substrings match
  the wrong district (`Quan 1` inside `Quan 10`) and are fabricable. Replaced by
  the required `administrative_context` contract.
- **Adopt the model's `id`/`uid`.** Rejected: identity must not be guessed from
  the model; the server assigns it.

## Consequences

- Positive: grounded plans, explicit error codes, observable `tool_chain`,
  no unsupported factual claims, no raw tracebacks, deterministic selection.
- Trade-off: **live itinerary generation is blocked until the upstream MCP
  service exposes `administrative_context`** on `get_poi_details`. Until then the
  endpoint fails closed with `scope_unverified`/`scope_conflict` rather than
  producing a plausible-but-ungrounded plan. This is intended; a later task
  implements the upstream contract.
- Known limitation: the accepted contract shape (`administrative_context` with
  `city_id`/`district_id`/`city_name`/`district_name`) is an interface this
  client now requires; it must be honored by the POI service.
- No live graph/model/database calls were made; all evidence is mocked contract
  evidence (see `docs/project/handoffs/OC-005/`).
