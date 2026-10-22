# ADR 010 — Graph transaction lifecycle, category wiring, NEAR_BY replacement

- Status: Accepted (live Cypher execution unverified)
- Date: 2026-10-15
- Task: OC-014
- Scope:
  - `POI_service/app/core/infrastructure/db/uow.py`
  - `POI_service/app/core/infrastructure/db/repositories/memgraph.py`
    (spatial rebuild + user preference sections)
  - `POI_service/app/core/base/service.py`
  - `POI_service/app/core/interfaces/repositories.py`
  - `POI_service/app/core/utils/updater.py`
  - `POI_service/app/core/utils/spatial.py` (one constant)
- Supersedes: none
- Related: ADR 002 (spatial prefilter / undirected NEAR_BY),
  `docs/decisions/006-mcp-evidence-contract.md`, MT2/SG07–08

## Context

An isolated source audit for OC-014 found a cluster of correctness defects in the
graph write path. No Memgraph/Docker is available in this environment, so the
defects and their fixes are established by source inspection, captured-Cypher
assertions and pure reference models — **not** by live graph execution.

1. **Category wiring mismatch.** `MemgraphUnitOfWork` assigned
   `self.categories`, while `CategoryManagementService` (and the abstract
   `AbstractUnitOfWork`) used `uow.cats`. The only test that exercised the
   service injected a `FakeUnitOfWork` whose `.cats` existed, so the mismatch was
   masked.
2. **Transaction lifecycle leaks.** A failed `begin_transaction()` left the
   session open. A failing `commit()`/`rollback()` skipped the cleanup block
   entirely because `super().__exit__()` raised before the close calls.
3. **Swallowed write errors committed.** `BaseManagementService` caught DB
   exceptions *inside* `with self.uow`, returned an error dictionary, and the
   `with` block therefore committed.
4. **Stale NEAR_BY edges.** The spatial rebuild never deleted old edges, so a
   radius shrink, a moved POI or a removed POI left stale `:NEAR_BY` edges.
5. **UserPreference sync dropped work.** A single
   `UNWIND $category_list ... UNWIND $tag_list` pipeline produced zero rows when
   the category list was empty, so tag preferences were silently skipped.
6. **Dishonest background reporting.** `SpatialUpdater` printed debug text,
   logged raw provider messages and had no per-district success/failure result.

## Decision

### 1. Category wiring: `cats` is canonical, `categories` is an alias

`AbstractUnitOfWork` declares `cats`, `categories`, `tags` and `users`.
`MemgraphUnitOfWork.__enter__` assigns the category repository once and points
both `cats` and `categories` at **the same instance**, so no caller can reach a
different transaction. The alias is retained for existing callers.

### 2. UnitOfWork lifecycle is leak-free and preserves the original error

- A failed `begin_transaction()` closes the session before re-raising.
- `commit()` runs on the success path; its failure propagates.
- On the error path, a `rollback()` failure is logged (exception **type** only)
  and swallowed so the original exception that triggered the rollback still
  propagates.
- `tx.close()` / `session.close()` run in a `finally`, so they run even when
  commit/rollback raise.
- A repeated `__exit__` is a safe no-op; re-entering the same UnitOfWork is
  rejected (callers must use the factory for a fresh transaction).
- All cleanup logs are sanitized (`type(exc).__name__`, never `str(exc)`).

### 3. Management services roll back on a failed write

`BaseManagementService.create/update/delete` now perform the existence check and
the write inside `with self.uow`. A failed write is allowed to propagate out of
the block, so the UnitOfWork rolls back, and the sanitized envelope is only
built *outside* the transaction. Conflict / not-found outcomes are signalled
with an internal `_OperationOutcome` raised inside the block, so a read-only
outcome rolls back instead of committing. Validation still runs before any
transaction is opened.

### 4. NEAR_BY rebuild is a transactional *replacement*

`build_nearby_edges_for_district` now runs, in the caller's transaction:

1. read the distinct stored `radius_km` on the district's incident edges and
   reject a **mixed** configuration;
2. delete every `:NEAR_BY` edge incident to an anchor POI of the district —
   anchors with missing/invalid coordinates are still matched so their stale
   edges are cleaned;
3. re-create the valid canonical pairs (conservative prefilter, both
   orientations, full prefilter/`point.distance` precision).

Edges that do not touch an anchor of the rebuilt district (for example edges
internal to another district) are never deleted. Because steps 2 and 3 share the
transaction, a failure during 3 rolls the deletion back and the previous edges
survive.

**Radius policy.** `NEARBY_RADIUS_KM_DEFAULT = 3.0` in
`app/core/utils/spatial.py` is the shared global radius. Edges incident to the
rebuilt district are owned by the rebuild and replaced wholesale, so a *uniform*
different radius is a legitimate full rebuild. A **mixed** set of stored radii is
an inconsistent configuration (a previous partial or different-radius build) and
is rejected with `ValueError` rather than silently flipping shared edges.
Callers must rebuild all affected districts with one shared radius.

### 5. Moved anchor: explicit POI-id rebuild (integration pending)

A district-scoped rebuild cannot clean the edges a moved POI left behind in its
*old* district. A documented new repository method,
`build_nearby_edges_for_poi(poi_id, radius_km)`, deletes the POI's incident edges
and rebuilds its canonical pairs independent of district membership. Adding it
to `IPOIRepository` is the only contract change; **live integration and the
old+new affected-district orchestration are pending and not claimed solved by
current district rebuilds alone.**

Note on existing behaviour (inspected, unchanged): the POI `update` graph-address
path deletes and rebuilds only `:LOCATE_AT`; it does **not** touch `:NEAR_BY`.
Moving a POI therefore inherently leaves stale `:NEAR_BY` edges until a rebuild
runs. Never assume "delete all graph `:NEAR_BY`" is allowed.

### 6. UserPreference sync uses independent writes

`MemgraphUserBehaviorRepository.create` performs four independent parameterized
writes in the same transaction: merge the user node; delete obsolete `:PREFERS`
edges (so an empty list clears that side); write category edges; write tag
edges. The label interpolation is restricted to a `{"Category", "Tag"}`
allow-list. `update` requires the payload `user_id` to match the `id` argument.

### 7. Spatial updater reports honestly per district

`SpatialUpdater` returns a report
`{is_success, total_edges, succeeded, failed}`. Each district is rebuilt in its
own fresh UnitOfWork/transaction, so the operation is **not atomic across
districts**; the report states exactly which districts succeeded and failed.
Raw provider/driver text is never logged or returned; only exception types.

## Alternatives considered

- **Keep the single UNWIND pipeline and guard with `FOREACH`.** Rejected:
  `FOREACH(CASE WHEN ...)` would work but the brief explicitly asked for
  independent parameterized writes, which is simpler to reason about.
- **Delete stale edges only for valid-coordinate anchors.** Rejected: stale edges
  of now-invalid anchors must also be removed, so the delete matches anchors
  without a coordinate predicate.
- **Reject any stored radius different from the requested one.** Rejected: it
  would forbid a legitimate uniform radius change (full rebuild). Only a *mixed*
  configuration is inconsistent.
- **Make the updater atomic across districts.** Rejected: it would require one
  transaction spanning all districts; the brief requires per-district reporting
  and honest non-atomic semantics.

## Consequences

- Positive: category services and the concrete UnitOfWork agree; no transaction
  or session leaks; failed writes can no longer be committed; stale NEAR_BY
  edges are cleaned transactionally; empty preference lists no longer drop the
  other list; background rebuild results are truthful.
- Negative / risk: `build_nearby_edges_for_district` now performs a read
  (radius-consistency check) plus a delete before the rebuild, so it does more
  work per call and requires the incident edges to carry `radius_km`.
- Deferred: live Cypher execution and the moved-anchor old+new district
  orchestration remain unverified.

## Migration and rollback

No data migration is performed here. Existing directed/rounded `:NEAR_BY` edges
are replaced the next time their district (or POI) is rebuilt; until then they
remain stale-but-readable (see ADR 002). Rollback is a source revert of the
listed files; it deletes no data by itself.

## Verification

`tests/graph_lifecycle/` (34 passed, 1 skipped in `.venv-mcp-validation`; the
skipped module is the updater test, which needs `tenacity` and runs in
`.venv-validation`, 4 passed). Evidence types are labelled per test:

- **Real UnitOfWork + fake driver/transaction** — category alias/wiring and all
  transaction-lifecycle error paths.
- **Captured Cypher (never executed)** — spatial delete-then-rebuild ordering,
  scoping, prefilter/canonical/full-precision assertions, preference writes.
- **Pure reference model** — moved / removed / radius-shrink /
  cross-district-higher-anchor pair selection.

Raw logs: `docs/project/handoffs/OC-014/pytest_oc014_*.txt`.

**Unverified:** the Cypher was not executed against a live Memgraph; no
historical migration was run. Live validation remains an explicit gap.
