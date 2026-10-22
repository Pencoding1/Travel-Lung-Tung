# ADR 002 — Conservative spherical prefilter and undirected NEAR_BY semantics

- Status: Accepted (live Cypher execution unverified)
- Date: 2026-10-15
- Task: OC-003
- Scope: `POI_service/app/core/utils/spatial.py` (new);
  `POI_service/app/core/infrastructure/db/repositories/memgraph.py`
  (`MemgraphPOIRepository.build_nearby_edges_for_district` and
  `get_poi_graph_payload` only)
- Supersedes: none
- Related: ADR 001 (stable POI identity), `docs/audit/ASSUMPTION_REGISTER.md` A04,
  `docs/audit/ARCHITECTURE_AS_IS.md` (spatial paragraph)

## Context

The isolated audit of `MemgraphPOIRepository.build_nearby_edges_for_district`
(`repositories/memgraph.py:181` before this change) identified four defects.
Because no POI field validates identity or coordinates until ADR 001, and no
database engine is available in this environment, the defects are established
by source inspection plus a mathematical reference, not by graph execution.

1. **Invalid longitude prefilter.** The square prefilter used the same degree
   bound for latitude and longitude:
   `abs(p1.longitude - p2.longitude) <= radius_km / 111.0`. One degree of
   longitude is `111.32 * cos(latitude)` km, so at latitude 60 a 3 km radius
   only allows ~0.0270 degrees of longitude while a genuine ~2.22 km neighbour
   can sit 0.04 degrees away. The filter therefore produced **false negatives**
   (silently dropped true neighbours). This is audit assumption A04, marked
   `False at nonzero latitude`.
2. **Same-district-only candidates.** Both `p1` and `p2` were anchored to the
   same `District`, so genuinely-close POIs across a district boundary were
   never considered.
3. **Directed edges with directed retrieval.** Edges were created as
   `(p1)-[:NEAR_BY]->(p2)` and read as `(p)-[nb:NEAR_BY]->(nearby)`, so a
   neighbour was invisible when the stored orientation did not start at `p`.
4. **Rounded distance used downstream.** The stored `distance_km` was rounded
   to two decimals; consumers then threshold on that rounded value.

Candidate generation remains `O(n^2)`; the prefilter only removes impossible
candidates. No asymptotic improvement is claimed.

## Decision

### 1. Conservative angular prefilter on a 6300 km lower-bound radius

The prefilter is a *necessary* condition only. All bounds are derived from a
lower-bound Earth radius `R_min = 6300 km`, which makes every bound looser than
the exact spherical geometry on the 6371 km sphere used by
`point.distance`. This is what guarantees **zero false negatives**.

- Latitude band half-width: `delta_lat = degrees(radius / 6300)`, capped at 180.
- Longitude half-width for a latitude band: the band reaches
  `abs(lat) + delta_lat`. If that reaches a pole (`>= 90 deg`) the bound is
  widened to 180. Otherwise
  `delta_lon = min(180, delta_lat / cos(radians(abs(lat) + delta_lat)))`.
  Using the **larger** `abs(lat)` of the two endpoints is the union of both
  per-anchor bands (the bound is monotonic in `abs(lat)`), so a pair is kept if
  either anchor would keep it.
- Dateline: longitude separation uses
  `min(abs(lon1 - lon2), 360 - abs(lon1 - lon2))`.
- No arbitrary `111` km/degree constant is used anywhere.
- Radius inputs are validated first: non-numeric, `NaN`, `+/-inf` and
  non-positive radii raise `ValueError`; no spherical math runs.

### 2. One source of truth, replicated in Cypher

`app/core/utils/spatial.py` holds the pure functions (no database/IO):

`validate_radius_km`, `latitude_delta_bound_degrees`,
`longitude_delta_bound_degrees`, `wrapped_longitude_delta_degrees`,
`haversine_km` (reference only), `pair_passes_prefilter`, and
`conservative_prefilter_cypher` (pure string construction).

The repository imports the module and inserts the generated Cypher fragment
into its query, so the Python reference and the Cypher rule cannot drift. The
Cypher rule replicates the same `degrees`/`radians`/`cos`/`abs` math and the
same 90/180 degree caps. `point.distance` remains the **authoritative** final
radius test; the prefilter never decides an edge by itself.

### 3. Neighbouring districts, self-exclusion, deduplication, undirected edges

- `p1` is anchored to the district being rebuilt; `p2` is matched graph-wide
  (`MATCH (p2:POI)`), so neighbouring districts are included.
- Self is excluded (`p2 <> p1`).
- Matching is **not** gated on the anchor having the lower internal id. Both
  orientations are matched and the endpoints are then normalised by internal id:
  `CASE WHEN id(p1) < id(p2) THEN p1 ELSE p2 END AS a` and the symmetric `b`.
  Normalising *after* matching means a cross-district pair is selected by
  whichever district is being built, even when its only anchor has the higher
  internal id. Gating on `id(p1) < id(p2)` in the `MATCH` (the earlier defect)
  dropped such pairs.
- `WITH DISTINCT a, b` deduplicates canonical pairs across all anchors of the
  district, so each unordered pair is materialised **once per build**.
- Edges are stored **undirected** with `MERGE (a)-[r:NEAR_BY]-(b)`.
- Retrieval in `get_poi_graph_payload` is undirected:
  `OPTIONAL MATCH (p)-[nb:NEAR_BY]-(nearby:POI)`. Undirected retrieval is what
  ensures an edge is never hidden when its stored orientation starts at the
  neighbour rather than the queried `p`.

### 4. Full-precision distance

The radius threshold and the stored value both use the unrounded
`dist_meters`. `distance_km = dist_meters / 1000.0`, `distance_meters`, and the
`radius_km` used are stored. No `round(...)` is applied for filtering or
storage.

### 5. Historical edges are not deleted in this change

`build_nearby_edges_for_district` never deletes `:NEAR_BY` edges, and the POI
`update` path is untouched. Existing edges stay in place. When a POI moves, its
old `:NEAR_BY` edges become stale.

**Required snapshot/rebuild strategy (not executed here):**

1. Take a graph snapshot/backup before any spatial rebuild.
2. Rebuild the affected districts (and, for cross-district pairs, the districts
   of both endpoints) after ingestion/relocation.
3. Reconcile `:NEAR_BY` edges by recomputing them from coordinates; do not
   trust stale stored `distance_km`.
4. Verify referential integrity and current edge counts before committing.

**Cross-district pair selection is fixed, not deferred.** Because endpoints are
normalised after matching both orientations (§3), a cross-district pair is
selected by whichever district is built, regardless of which endpoint has the
smaller internal id. The earlier `id(p1) < id(p2)` gate that dropped such pairs
is removed.

**Historical stale edges remain a separate, documented concern.** When a POI
moves, its old `:NEAR_BY` edges are not deleted by this change and can be stale
until the snapshot/rebuild job above runs. Until then, callers must treat stored
`:NEAR_BY` edges as a rebuildable cache, not as a source of truth. This is a
data-lifecycle concern, independent of the (now-correct) pair selection.

## Rationale

- A conservative lower-bound radius is the simplest way to make the prefilter
  provably non-excluding while still cheap; the exact distance test is retained
  on survivors, so correctness does not depend on the prefilter's tightness.
- Keeping the math in a pure module makes it independently testable and removes
  the drift risk of duplicating constants between Python and Cypher.
- Undirected storage/retrieval plus canonical dedup removes the orientation
  defect without a data migration.

## Alternatives considered

- **Exact spherical bounding formula in Cypher only.** Rejected: cannot be
  unit-tested here (no engine) and risks Python/Cypher drift.
- **Indexed spatial search (R-tree/grid).** Out of scope for this run; would be
  the real fix for the `O(n^2)` candidate generation and is not claimed.
- **Delete stale edges during rebuild.** Rejected for this run (explicitly
  forbidden); deferred to the snapshot/rebuild strategy above.

## Consequences

- Positive: no false negatives from the prefilter (proved against exhaustive
  Haversine at 1/3/5 km), cross-district neighbours are now included,
  orientation no longer hides edges, and distances are no longer rounded away.
- Negative / risk: candidate generation is still `O(n^2)`; undirected storage
  changes edge shape (one undirected edge per pair instead of one directed).
- Deferred: historical stale-edge cleanup and live Cypher verification.

## Migration and rollback

This change is **non-destructive at the data layer**: it deletes nothing and
renames nothing. Existing directed `:NEAR_BY` edges are left as-is; retrieval
now matches them undirected, so they continue to resolve. New/updated pairs are
written undirected by the rebuilt query; the coexistence of old-directed and
new-undirected edges must be reconciled by the snapshot/rebuild job.

Rollback is a source revert of `spatial.py` and `memgraph.py`. It is safe
because no data is mutated by this change.

## Verification

- `tests/spatial/test_spatial_prefilter.py` — 33 tests: radius rejection;
  reference Haversine; angular bounds; pole and dateline handling; symmetric
  neighbours; just-inside/outside; the explicit latitude-60 / 0.04-degree
  regression; randomized exhaustive zero-false-negative checks at 1/3/5 km;
  Cypher construction/structure checks; and a functional anchored pair-selection
  regression (two districts, either internal-id ordering) proving the
  higher-id-anchor cross-district pair is retained. Raw output:
  `docs/project/handoffs/OC-003/qa_repair.txt` (and the original
  `docs/project/handoffs/OC-003/pytest_oc003.txt`).
- `benchmarks/spatial/benchmark.py` (synthetic, seed 20261015) — n=200 and
  n=1000, radii 1/3/5 km, zero false negatives. Raw JSON:
  `benchmarks/spatial/benchmark_results.json`; stdout:
  `docs/project/handoffs/OC-003/qa_repair.txt`. (An identical copy also exists
  under the git-ignored `experiments/spatial/`.)
- **Unverified:** no Memgraph/Docker was available, so the Cypher was never
  executed. The Cypher tests assert construction only and are **not** database
  integration evidence. Live validation remains a gap.

## Runtime correction — Memgraph 3.13.2 lacks `degrees`/`radians` (OC-044)

The original emitted fragment used `degrees(...)` and `radians(...)`. On the
verified owned Memgraph 3.13.2 instance those functions do not exist
(`parent-math-capabilities.json`), so the actual repository spatial rebuild
failed with `Function 'degrees' doesn't exist` and rolled back
(`parent-application-rollback-canary.json`). This was a real-engine
incompatibility, not a cosmetic query-string concern.

`conservative_prefilter_cypher` now emits the exact arithmetic equivalents,
which the same engine verified as supported (`pi()`, `cos`, `abs`,
multiplication/division):

- `degrees(x)` is emitted as `x * 180.0 / pi()`;
- `radians(x)` is emitted as `x * pi() / 180.0`.

The Python reference (`math.degrees`/`math.radians`), the 6300 km lower-bound
radius, 180-degree caps, pole fallback, dateline wrap, symmetry, conservative
slack and the authoritative full-precision `point.distance` final filter are
unchanged. No MAGE, geodesic, `111` km/degree constant or approximate cutoff was
introduced, and no caller/parameter interface changed.

A read-only real-engine gate
(`tests/memgraph_spatial_runtime/test_spatial_runtime_live.py`, evidence
`docs/project/handoffs/OC-044/evidence/live-spatial-runtime.json`) executed the
generated expression plus `point.distance` on 1113 seeded cases (HCMC, high
latitudes, poles, dateline, antipodal, near-threshold and random adversarial
pairs at 1/3/5 km). Results: 439 pairs genuinely within radius, **0 false
negatives**, 83 expected conservative false positives, and 0 Cypher/Python
reference mismatches; the graph stayed at 0 nodes/0 relationships. This verifies
the expression only, not a committed NEAR_BY rebuild, import, durability,
performance or deployment claim.
