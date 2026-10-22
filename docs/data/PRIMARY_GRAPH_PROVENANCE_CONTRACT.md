# PRIMARY GRAPH PROVENANCE CONTRACT (OC-038)

Status: bounded POI production-boundary extension. No preparation artifact was
regenerated and no live graph/service was called. This document defines how an
optional typed source provenance block is accepted, stored and read. It does not
claim that the primary dataset has been imported.

## 1. Optional field

The existing production model
`POI_service.app.core.domain.graph_entities.POI` gains one optional field:

```json
"source_metadata": { ... }
```

Absence (`null`/omitted) means **legacy/unspecified**, never "verified". A record
without provenance keeps its existing write/read behaviour.

`SourceMetadata` is strict (`extra="forbid"`). A misspelled key is rejected
rather than silently dropped; a top-level key that looks like provenance but is
not `source_metadata` (for example `source_metdata`) is also rejected.

## 2. Accepted shape (source-snapshot scope)

Only one scope is accepted today:

| Field | Contract |
|---|---|
| `dataset_namespace` | explicit dataset namespace (e.g. `hcm_primary_geojson`) |
| `identity_scope` | exactly `internal_local_only` |
| `cross_export_matching` | exactly `not_guaranteed` |
| `administrative_scope` | exactly `source_snapshot_area_only` |
| `input_sha256` | lowercase 64-char SHA256 of the input dataset |
| `feature_sha256` | lowercase 64-char SHA256 of the exact source feature |
| `canonical_source_index` | nonnegative integer, bools rejected |
| `duplicate_source_indices` | unique nonnegative integers; canonical index excluded |
| `internal_record_id` | nonblank internal record id (e.g. `r005494`) |
| `provided_at` | supplied date (`YYYY-MM-DD`) |
| `collection_time` | `null` (or explicit `UNKNOWN`) until genuinely known |
| `source_url` | `null` (or explicit `UNKNOWN`) until genuinely known |
| `license` | `null` (or explicit `UNKNOWN`) until genuinely known |
| `freshness` | `null` (or explicit `UNKNOWN`) until genuinely known |
| `raw_lineage_json` | canonical bounded JSON of the full lineage row |
| `raw_lineage_sha256` | SHA256 of `raw_lineage_json` |

Two distinct hash recipes are used and must not be substituted for each other:

* **Raw-lineage envelope:** `raw_lineage_sha256 = sha256(canonical_json(row))`
  where canonical JSON is sorted/compact with `ensure_ascii=False`.
* **Source feature body:** `feature_sha256 =
  sha256(json.dumps({"type": "Feature", "properties": raw_properties,
  "geometry": geometry}, sort_keys=True, ensure_ascii=False))` using the default
  (spaced) `json.dumps` separators. This mirrors the frozen preparation hash
  without importing crawler code into the POI service.

The raw lineage must include the exact full source geometry and raw properties,
identity derivation, address evidence and provenance object. The validator
requires:

* canonical JSON (sorted keys, compact separators, non-ASCII preserved);
* the stored raw-lineage hash equals the JSON bytes;
* `source.geometry` is a nonempty finite `Point` with
  `[longitude, latitude]` in range, and `source.raw_properties` is a nonempty
  object; where `lat`/`lon` appear there they must agree with the geometry;
* the recomputed source-feature hash equals `feature_sha256` (so changing raw
  properties without recomputing the feature hash is rejected);
* the raw lineage `id` equals the POI `id`;
* namespace, identity scope, cross-export matching, input hash, feature hash,
  canonical source index (strict nonnegative integer, bools rejected) and
  internal record id agree with the typed fields;
* `address.scope` equals `administrative_scope` and
  `address.current_admin_claim` is `none`;
* `provided_at` and the four unknown fields agree with the raw lineage.

Any disagreement is rejected before a repository is reached.

## 3. Storage limits and representation

Memgraph does not support nested map/list-of-map node properties. Provenance is
therefore stored as scalar properties only:

| Node property | Value |
|---|---|
| `source_metadata_json` | canonical JSON of the typed metadata (includes raw lineage) |
| `source_metadata_sha256` | SHA256 binding the stored metadata scalar |
| `administrative_scope` | `source_snapshot_area_only` when present, else null |

Practical limits enforced by the model:

* `raw_lineage_json` ≤ 64 KiB UTF-8;
* canonical metadata (envelope plus raw lineage) ≤ 72 KiB UTF-8.

Records exceeding the limit are rejected at the trusted boundary. The write path
never mutates the caller payload; only metadata-bearing records are copied for
parameter construction.

## 4. Source-snapshot area is not current jurisdiction

When `administrative_scope == "source_snapshot_area_only"`, the address strings
are **display/source claims only**. The production writes therefore:

* do not create ordinary current `Nation/City/District/Street` nodes;
* do not create `IN_NATION`, `IN_CITY`, `IN_DISTRICT` or `LOCATE_AT` chains from
  those strings;
* clear stale flat `addr_city`/`addr_district`/`addr_street`/`addr_ward`/
  `addr_nation` shortcuts;
* remove any previous `LOCATE_AT` link on create/update/batch upsert, so a record
  transitioning from a current address to a source-only area (or to a null
  address) cannot keep an old hierarchy.

The raw source address remains available in `full_address` and the raw lineage.
The qualification is exposed as `administrative_scope` (and `source_metadata`).

## 5. Null address / null contact safety

`address` and `contact_info` remain optional. The three production writes
(`batch_create`, `create`, `update`) compute hierarchy ids only inside a guarded
block that requires a non-null address and a non-source-only scope. A null
address can never reach a null-keyed `MERGE` of `Nation`, `City`, `District` or
`Street`. Empty category/tag lists do not drop the outer POI row.

## 6. Read projections

* `get_poi_graph_payload` returns the stored scalar provenance and scope.
* `get_agentic_poi_details` decodes metadata safely and **binds it to the POI id
  actually returned by the graph**. A self-consistent hash carried by a
  different POI id is treated as corrupt. Valid source-only evidence forces
  `administrative_context = null` and
  `administrative_context_status = "unverified_source_area"` even if a stale
  chain is present. Corrupt stored or mis-bound metadata returns
  `source_metadata_status = "corrupt"` and
  `administrative_context_status = "provenance_corrupt"`; it is never returned
  as trusted.
* `get_compound_explore_lite` applies the same id-binding rule and exposes
  `source_metadata_status` / `administrative_scope`.
* AI-facing details/compound carry a compact typed
  `SourceEvidenceSummary` (namespace, source hashes, index/scope/unknowns,
  lineage hash and a stored-property reference). The full raw lineage blob is
  **not** repeated into model output.
* Full CRUD reads (`get_by_id`/`get_all`) retain the full typed
  `SourceMetadata`, including `raw_lineage_json`, for audit/traceability.
* Provenance-free records omit the new keys from the emitted payload, preserving
  the previous read shape. Missing metadata is always `missing`, never an
  implicit trust upgrade.

City/district-scoped retrieval continues to use genuine graph chains or the flat
`addr_*` shortcuts in `get_preferred_pois`. `get_preferred_pois` (and its
`get_routing_candidates` delegation) now selects **current jurisdiction only**:
records with `source_metadata_json` or `administrative_scope` present are
excluded, so source-only and incomplete/corrupt provenance cannot be admitted by
the legacy shortcuts. Provenance-free legacy records keep the previous behavior,
and the returned typed record still projects any stored metadata rather than
silently reducing it to "unspecified".

## 7. Unknowns / explicit non-claims

* No current jurisdiction, dated administrative mapping or boundary
  containment is claimed for source-snapshot records.
* Collection time, source URL, license and freshness are unknown and are not
  inferred from the filename or derived names.
* No prepared/raw/lineage file was regenerated or modified by OC-038.
* No live Memgraph acceptance, node count or idempotency proof is claimed. The
  tests capture emitted Cypher/parameters and use the real models; they are not a
  live graph run.

## 8. Next step (separate review)

A separate adapter should read the frozen `prepared_pois.jsonl` and
`lineage.jsonl` read-only, construct `source_metadata` from each lineage row
(including duplicate source indices from the duplicate ledger), and send the
result through the existing validated ingestion path. That adapter is not part
of OC-038.
