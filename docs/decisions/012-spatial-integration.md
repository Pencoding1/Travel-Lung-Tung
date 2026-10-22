# ADR 012 — Transactional single-POI spatial integration and honest rebuild status

- Status: Accepted (live Cypher execution unverified)
- Date: 2026-10-15 (amended 2026-10-15 by OC-017-R1: fixed-radius enforcement)
- Task: OC-017, OC-017-R1
- Scope:
  - `POI_service/app/core/services/management.py` (POI mutation hooks)
  - `POI_service/app/core/services/ingestion.py` (spatial lifecycle/reporting)
  - `POI_service/app/core/utils/updater.py`
  - `POI_service/app/core/interfaces/updater.py`
  - `POI_service/app/api/rest/v1/endpoint_spatial_rebuild.py`
  - `POI_service/app/core/infrastructure/db/repositories/memgraph.py`
    (spatial radius gate + POI mutation/bulk integration)
- Supersedes: none
- Related: ADR 010 (graph lifecycle / transactional replacement),
  ADR 002 (spatial prefilter / undirected `NEAR_BY`), MT2/SG08/SG16

## Context

OC-014 added a transactional *replacement* contract
(`build_nearby_edges_for_poi`) but never connected it to the real write paths,
so the correctness was demonstrated only in isolation:

1. **Single-POI mutations never rebuilt edges.** `MemgraphPOIRepository.update`
   reconciled `LOCATE_AT` but left the POI's `:NEAR_BY` edges untouched. Moving a
   POI (or changing its coordinates) left stale edges, and a district-scoped
   rebuild could not clean an edge the POI left in its *old* district.
2. **Bulk ingestion had a dead spatial stage.** `process_background_remainder`
   computed `global_affected_districts` and then never used it; accepted changed
   POIs received no spatial coverage.
3. **The manual rebuild endpoint reported unconditionally.** It enqueued a
   background task and returned `{"status": "success", ...}` before any work ran
   and without observing the outcome.
4. **No service radius policy.** The application path had no fixed radius and no
   honest failure when stored radii were incompatible.

No live Memgraph/Docker is available in this environment, so behaviour is
established by source inspection, captured-Cypher assertions and a fake
transactional driver — **not** by live graph execution.

## Decision

### 1. Single-POI incident-edge rebuild lives in one layer: the service hooks

`POIManagementService._execute_create` and `_execute_update` call the repository
`build_nearby_edges_for_poi(poi_id, radius_km=NEARBY_RADIUS_KM_DEFAULT)`
**inside the same UnitOfWork/transaction** as the source mutation. The repository
write methods themselves do **not** rebuild, so an update is never rebuilt twice
through both layers. Every location/coordinate update (including a move out of
the previous district) replaces *all* incident `:NEAR_BY` edges, because the
delete is anchored on the POI id only and is district-independent.

Because the rebuild shares the source transaction, a downstream spatial failure
raises out of `with self.uow`, the transaction rolls back, and
`BaseManagementService` returns a sanitized `internal_error` — the source POI
mutation is never committed half-linked.

### 2. Deletion removes incidents; unrelated nodes/edges survive

`MemgraphPOIRepository.delete` remains a `DETACH DELETE p`: the node and every
incident edge (including `:NEAR_BY`) are removed, while edges between other POIs
are never matched. No explicit edge enumeration is needed.

### 3. Bulk ingestion: bounded, post-write, separate spatial stage

Ingestion writes POIs exactly as before (per-chunk transaction + bounded retry,
with fresh UoW per attempt). For each chunk whose write **commits**, the accepted
changed POI ids are then spatially rebuilt by `SpatialUpdater.rebuild_pois` in a
**separate** transaction (a fresh UoW per bounded batch, retried with a fresh
transaction per attempt). This is the "explicit bounded strategy":

- only *accepted* changed ids are rebuilt; a failed/skipped chunk is never
  scheduled (`test_failed_chunk_ids_are_not_spatially_scheduled`);
- ids are de-duplicated (`test_duplicate_accepted_ids_are_rebuilt_once`);
- ids are capped by `SPATIAL_REBUILD_MAX_POIS` and processed in
  `SPATIAL_REBUILD_BATCH_SIZE` batches; surplus coverage is reported as
  `deferred`, never silently dropped.

Because the spatial stage is a separate transaction, a spatial failure **never**
reclassifies a successful insert: `accepted`/`validation_failed`/
`database_failed` stay exact. A structured `spatial` report is merged across the
canary and background phases and attached to the terminal `complete` event; when
spatial work is incomplete the terminal `status` is downgraded from `success` to
`partial_failure` (the counts are untouched, and the POI-write contract
`is_success` remains the write outcome).

### 4. Fixed 3 km service radius for application updates

All application updates (management create/update and the ingestion spatial
stage) use the single shared `NEARBY_RADIUS_KM_DEFAULT = 3.0`, and §6 enforces
that any known stored incident radius equals it. The repository `radius_km`
parameter remains for an explicit offline/admin **migration** rebuild (via the
`migrate_*` methods); it is never selected automatically. The spatial report
carries `radius_km` for inspection.

### 5. Manual rebuild is synchronous, bounded and reports terminal outcome

`POST /management/pois/spatial-rebuild` now:

- validates the body (must be a list of non-blank string district ids),
  de-duplicates, and rejects an empty or over-limit request
  (`MAX_DISTRICTS_PER_REBUILD`) with 422;
- runs the **real** per-district work off the event loop via `asyncio.to_thread`
  and waits for the terminal report;
- returns 200 on all-success, **207 Multi-Status** on partial failure, and
  **502** when no district succeeded — never an unconditional "started" success;
- only ever exposes sanitized exception *types*, never raw provider text.
- The JWT dependency on the router is retained.

### 6. Fixed application radius is enforced; migration is a separate opt-out

The incident-radius gate reads the stored `radius_km` values **before** any
deletion and enforces the fixed application policy:

- any **known** stored radius that differs from the requested application radius
  (3 km) — whether *uniform* or *mixed* — raises
  `IncompatibleStoredRadiusError` and aborts the mutation;
- incident edges with **no** stored radius raise `UnknownStoredRadiusError`: this
  is an explicit unknown/legacy migration gate and is never treated as validated.

A uniform different radius is **no longer** accepted on the application path: the
application must never silently rebuild the shared policy at a new radius
(OC-017-R1 correction). The explicit offline/full-radius **migration** mechanism
is kept distinctly separate via `migrate_nearby_edges_for_poi` /
`migrate_nearby_edges_for_district` (concrete repository methods, never selected
by the application path), which opt out of the fixed-radius gate and may backfill
legacy radius-less edges. The gate is a read-time consistency check: it is
**not** advisory-lock based and makes **no** claim to enforce concurrency across
writers; a rejected configuration surfaces an honest failure rather than silently
flipping shared policy.

## Alternatives considered

- **Rebuild inside the repository create/update methods.** Rejected: it would
  duplicate the service-level orchestration ("rebuild twice through both
  repo/service") and would make the bulk write method implicitly heavy.
- **Run the ingestion spatial stage inside the write transaction.** Rejected: a
  spatial failure would roll back and reclassify a successful insert as a
  database failure, which the contract forbids.
- **Keep the manual endpoint asynchronous.** Rejected: no observable bounded
  job/status contract exists; a job id with no result would still report
  premature success.
- **Rebuild only by district during ingestion.** Rejected: it misses changed
  POIs whose district is not "new", and cannot express accepted changed ids
  explicitly.

## Consequences

- Positive: single-POI moves now replace incident edges atomically; bulk
  ingestion covers accepted changed POIs with honest, bounded reporting; manual
  rebuild can no longer return a false success; the service radius is fixed and
  documented.
- Negative / risk: application updates do more work (a radius read, an
  incident-edge delete and a rebuild per POI) and require incident edges to
  carry `radius_km` for the consistency check; a large ingestion request opens
  one extra UoW per committed chunk.
- Deferred: the Cypher remains unexecuted against a live graph.

## Migration and rollback

No data migration is performed here. Pre-existing `:NEAR_BY` edges that do not
carry `radius_km` are **not** ignored: under the application policy they raise
`UnknownStoredRadiusError` (an explicit unknown/legacy migration gate). A
separately authorized migration — via `migrate_nearby_edges_for_poi` /
`migrate_nearby_edges_for_district` — is required to backfill/normalise the
radius before application rebuilds; such a migration is **not run** by this task.
Existing stale/directed edges are replaced the next time their POI (or district)
is rebuilt. Rollback is a source revert of the listed files; it deletes no data.

## Verification

Evidence is labelled per test (real service/repository + captured Cypher; fake
provider HTTP vs. live graph):

- `tests/graph_lifecycle/test_spatial_integration.py` — real
  `POIManagementService` + real `MemgraphPOIRepository`/`MemgraphUnitOfWork` on a
  captured fake transaction: create rebuild, cross-district move replacement,
  uniform-incompatible and mixed-radius honest aborts (source update rolled
  back), uniform-3 km success, legacy missing-radius gate, forced rebuild failure
  rolling the source mutation back, invalid-coordinate rejection before any
  transaction, and `DETACH DELETE` incidence cleanup.
- `tests/graph_lifecycle/test_spatial_rebuild.py` — captured-Cypher gate
  ordering (rejection before any delete), the explicit-migration opt-out, and
  the single-POI rebuild contract.
- `docs/project/handoffs/OC-017/probe_radius_guard.py` — independent AST
  extraction of `_assert_consistent_incident_radius` executed against fake read
  results: uniform 5.0 vs fixed 3.0 → `IncompatibleStoredRadiusError`; mixed →
  `IncompatibleStoredRadiusError`; uniform 3.0 → OK; missing → 
  `UnknownStoredRadiusError`; explicit migration rebuild → OK.
- `tests/ingestion/test_spatial_contract.py` — accepted-id coverage, canary +
  background report merge, duplicate-id dedup, failed-chunk non-scheduling,
  accounting-vs-spatial separation (accepted counts unchanged), incompatible
  radius spatial failure preserving insert counts, updater bounding/dedup/
  sanitization.
- `tests/ingestion/test_endpoint_spatial_rebuild.py` — real router/auth/status
  mapping with a fake provider: missing/invalid token, empty/blank/oversize
  input, dedup, all-success (200), partial (207), total failure (502),
  incompatible-radius honest failure, sanitized provider error.

**Unverified:** the Cypher was not executed against a live Memgraph; no
historical migration was run. Live validation remains an explicit gap.
