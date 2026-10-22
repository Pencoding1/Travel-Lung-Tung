# Source-snapshot selection contract (server portion, T049)

Status: implemented and unit/fixture-verified in the POI repository/service/MCP
path by OC-045. This is **not** a live graph acceptance, primary import, AI
retention or full T049 completion.

## 1. Explicit mode

Source mode is active **only** when the caller supplies the typed
`source_scope` object. It is never inferred from a label, a POI id, or an id
prefix. Current city/district/street discovery keeps its existing meaning.

```json
{
  "dataset_namespace": "hcm_primary_geojson",
  "input_sha256": "<64 lowercase hex>",
  "source_area_id": "source_area_v1:<64 lowercase hex>"
}
```

Unknown fields, numeric/boolean values, uppercase or malformed input hashes,
current District/City ids and ids without the `source_area_v1:` prefix are
rejected. Supplying `source_scope` together with `city_id`, `district_id` or
`street_id` is rejected before any query is built.

## 2. Authoritative `source_area_id` recipe

Inputs are the exact validated source lineage values:

* `dataset_namespace` — `SourceMetadata.dataset_namespace`
* `input_sha256` — `SourceMetadata.input_sha256`
* `raw_city` — `metadata.parsed_lineage()["address"]["raw_city"]`
* `raw_area` — `metadata.parsed_lineage()["address"]["raw_district"]`

Canonical material is UTF-8 JSON with sorted keys, compact separators
(`(',', ':')`) and non-ASCII labels preserved:

```json
{"dataset_namespace":"...","input_sha256":"...","raw_area":"Go Vap","raw_city":"HCMC","schema":"source_area_scope_v1"}
```

`source_area_id = "source_area_v1:" + sha256(canonical_material_utf8)`.

Consequences:

* Equal `Go Vap` labels in different cities, namespaces or snapshots produce
  different selectors.
* A missing/blank label is stored as `null` in the material. The result is an
  explicitly **unassigned** source area; no current name or fallback label is
  invented. `raw_city`/`raw_area` are returned exactly as stored (or `null`).
* The label combination is never normalised into a current `District` id.

## 3. Persisted flat scalars

All three existing write paths (`batch_create`, `create`, `update`) derive these
properties from the already-validated `SourceMetadata` lineage, not from client
top-level fields:

* `source_area_id`
* `source_dataset_namespace`
* `source_snapshot_sha256`

The existing canonical `source_metadata_json`, `source_metadata_sha256` and
`administrative_scope` bytes are unchanged. A legitimate write without
`source_metadata` writes all six selector/provenance scalars as `null`, clearing
stale claims.

The cache is an index hint only. It is never proof of scope: reads decode stored
metadata/SHA, bind the actual POI id, recompute the area and compare any cached
selector. Existing records written before this cache existed remain discoverable
because discovery and source retrieval also qualify records whose cache is
absent.

## 4. Service/MCP surface

The existing `explore_pois` MCP tool (and `POIManagementService`) exposes:

* `source_discovery="snapshots"` — list `dataset_namespace`, `input_sha256`,
  valid record count, source-area count, corrupt exclusions and scan status.
* `source_discovery="source_areas"` with
  `source_snapshot={"dataset_namespace","input_sha256"}` — list each qualified
  area's stable selector, exact raw labels, readable label, assignment state,
  valid record count and current-boundary uncertainty.
* `source_scope={...}` — retrieve only records that qualify for the exact
  snapshot/area, optionally with the existing category/product filters, `limit`
  (1..100) and `offset`.

Discovery is bounded keyset scanning (page 500, hard scan cap 100000, well above
the 6367 supplied records). Results explicitly carry `scan_complete` (no cap
abort), `scan_exhausted` (reached the end of the candidate set) and `truncated`;
corrupt records are counted and excluded. Source retrieval reports
`scanned_record_count`, `matched_record_count`, `excluded_corrupt_count`,
`excluded_scope_mismatch_count`, `scan_complete`, `scan_exhausted` and
`truncated`.

## 5. Fail-closed reads and output

A source record matches only when all of the following hold:

1. stored `source_metadata_json` decodes to a valid `SourceMetadata` and its SHA
   matches `source_metadata_sha256`;
2. the raw lineage id equals the actual POI id returned by the graph;
3. the recomputed `(namespace, input_sha256, raw_city, raw_area)` area equals the
   requested selector;
4. if any cached selector property exists, all three cached values equal the
   recomputed values.

Otherwise the record is excluded and counted (`provenance_corrupt` semantics at
detail level). Scalar properties alone never create a match. Default/current
exploration excludes every record carrying source metadata, a cached selector or
`administrative_scope = source_snapshot_area_only`; detail by explicit POI id may
still disclose the qualified source evidence.

MCP results return a compact `source_context` (namespace, input SHA, source area
id, exact raw labels, readable label, assignment, `unverified_source_area`,
uncertainty text, lineage reference and qualification). They never return the
raw lineage blob, arbitrary Cypher APIs or a current District id.

## 6. Limits and remaining gates

* No durable full-snapshot import or migration is accepted. Parent canaries use
  two genuine records inside one rollback-only transaction; all final graphs
  return to zero nodes/relationships. The 6367 candidates are not claimed imported.
* AI059 now carries strict optional `source_scope` through the itinerary request,
  candidate/enrichment filtering, initial reconstruction and repaired scheduler
  output. Source mode skips current-administration resolution and supports a
  bounded unfiltered source query even with an empty global category catalog.
  Malformed selectors fail at the HTTP boundary; unknown/foreign evidence never
  falls back into current administrative verification.
* Parent `AI-059/parent-real-scope-canary-r1.json` verifies six stages through
  real Memgraph, registered in-process MCP, AI/scheduler/validator and real
  GraphHopper HTTP, with a controlled fake model. The scheduler adds a second
  source stop; final scope/missing-data metadata covers both delivered stops,
  while initial-proposal metadata remains separately identified. Frozen hashes
  stay unchanged. Runtime MCP1.26.0 matches the project lock; this is not evidence
  of deployment, HTTP MCP, live-model quality or full-snapshot performance.
* No source-snapshot record is present-day administrative containment, a
  verified venue, a route/itinerary feasibility claim, or source-native identity.
* Client discovery/selector supply, full-snapshot integration, live provider,
  HTTP MCP/deployment and scale/concurrency/durability remain separate gates.
