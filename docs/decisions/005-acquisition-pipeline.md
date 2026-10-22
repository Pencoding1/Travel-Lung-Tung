# ADR 005 — Acquisition, resolution and quarantine pipeline

- Status: Accepted
- Date: 2026-10-15
- Task: OC-006 (corrective QA applied)
- Scope: `crawler_service/app/acquisition/`, `tests/acquisition/`,
  `scripts/acquisition/`, `data/acquisition/examples/`
- Supersedes: none

## Context

`docs/architecture/DATA_ACQUISITION_DESIGN.md` and
`docs/architecture/DATA_CONTRACTS.md` specify a source-authorized expansion
capability that adds POIs without inventing facts. ADR 001 made `POI.id`
immutable and required acquisition to supply stable, source-derived ids. This
ADR records the acquisition package and the corrective decisions from the
OC-006 QA pass.

## Decision

### 1. Capability package, not a new service

Acquisition lives at `crawler_service.app.acquisition`, imported as
`crawler_service.app.acquisition...` from the repository root, avoiding the
unrelated top-level `app` package of `POI_service`. The package is
standard-library only.

### 2. Typed stdlib contracts

`contracts.py` defines `RawSourceRecord`, `POICandidate`, `ResolvedPOI` and
`IngestionDecision`. Shared validators (`is_number`, `is_finite_in_range`,
`parse_utc`) treat `bool` as non-numeric and require finite, in-range
coordinates and timezone-aware timestamps. `ResolvedPOI.as_payload()` emits
`poi_categories` as full `id`/`name`/`context` objects from the closed catalog
(never a bare id list), and `operation_time` only as the original source text
with unparsed provenance when an `opening_hours` value exists.

### 3. Two real-format adapters behind a registry

- `adapters/osm.py` parses Overpass `elements` JSON and preserves original
  element indices even when non-object entries are skipped. Identities require a
  primitive in `{node, way, relation}` and a positive integer id; garbage ids
  are rejected. Only `node` records with numeric `lat`/`lon` are point venues;
  `center` and polygon/area geometry always require review.
- `adapters/wikidata.py` parses `wbgetentities` JSON. Identities must match
  `Q[1-9][0-9]*`. P625 is parsed only for value snaks whose datavalue is a
  `globecoordinate` with an Earth globe (`Q2`). Preferred ranks win over normal
  ranks; multiple non-identical live coordinates are ambiguous. Deprecated and
  non-Earth claims are **informational** notes that never block acceptance when
  a unique valid live coordinate exists. Malformed coordinate values are
  isolated to review and never crash a set/unhashable operation. Labels use
  `vi` then `en` with no invented translation.

Both adapters emit RFC 6901 JSON Pointers that address the actual parsed
document (including the Wikidata `entities/<QID>` prefix); `jsonptr` resolves
them, and tests resolve every recorded path against the raw export.

### 4. Per-entity reviewed mapping manifest

Administrative acceptance is per **source entity**, never per export file.
`sources[<source_id>].entities` whitelists each reviewed entity keyed by
`<source_type>/<entity_id>` with its own non-blank-string `reviewer`,
`evidence_reference`, `city`, `district` and `nation`. A file-level
`category_map` remains for the closed-category catalog, but a file-level
default district alone is never sufficient. An unlisted entity routes to
`entity_unreviewed` review. Conflicting actual address hints (`addr:city`,
`addr:district`, `addr:suburb`) that cannot be reconciled with the reviewed
entity route to `admin_conflict` review. `reviewer`/`evidence`/`city` must be
non-blank strings, not truthy objects.

Accepted facts record provenance with the **mapping-manifest SHA-256** and JSON
Pointers for both the administrative assignment
(`/sources/<id>/entities/<escaped key>`) and every category mapping/catalog
decision.

### 5. Exact resolution is the only acceptance

A candidate is accepted only with a non-blank source identity, point geometry,
finite in-range coordinates, a non-blank name, a mapped closed category and a
reviewed entity city/district. Invalid/non-finite coordinates and malformed
identities are rejected; missing name/coordinates, unknown category, unknown
admin, admin conflict, area/center geometry, ambiguous coordinates and
unreviewed entities route to review.

### 6. Namespaced stable identity and fact fingerprints

`stable_source_id` is `"{source_type}:{sha256(source_type + '\\x1f' + entity_id)[:32]}"`,
independent of taxonomy, address and time. `fact_fingerprint` is a deterministic
digest of an entity's normative facts (name, aliases, coordinates, address
hints, category tags, geometry, opening-hours text) that **excludes** fetch
time, source URL, license, revision and container metadata. Duplicate/conflict
detection compares fingerprints, so adding an unrelated record or refreshing a
response never conflicts an unchanged entity; the raw-byte SHA-256 is preserved
separately as evidence.

### 7. Policy hash re-evaluation and audit history

The mapping-manifest SHA-256 is tracked as a policy hash independent of the
pipeline version. When an entity's fingerprint is unchanged but the policy hash
changed (e.g. a reviewer approves a previously quarantined entity, or a category
mapping is corrected), the candidate is **re-evaluated**: the same stable id is
kept, the resolution is updated, and the prior decision is recorded in the
decision row (`prior_outcome`, `policy_re_evaluated`) and in the entry's
`history`. True fact conflicts remain quarantined and are never silently
overwritten.

### 8. Effective synthetic labelling

Effective synthetic is `manifest.synthetic OR source.synthetic OR
review.synthetic`; all three flags must be actual booleans. Synthetic records
are excluded from `real_expansion_totals` and carry the flag in accepted and
quarantine output. A same-identity synthetic-to-real collision is isolated: the
entry keeps `synthetic=True`, is quarantined with `synthetic_real_collision`,
and its provenance is never promoted to real.

### 9. Input safety, two-phase validation and auditable ledger

Source ids are validated against a safe charset with no path separators,
reserved names or `..`; raw blobs use hashed filenames independent of the user
label. Every source payload and the full manifest/mapping are validated and
parsed into memory **before** the first write, so a malformed later source
cannot partially update a prior dataset. Existing output files that are also
inputs are rejected. A corrupt or version-mismatched `state.json` is a hard
error, never a silent reset. Raw blobs are immutable, and an append-only
`ledger.jsonl` records every run's decisions so reruns do not erase original
decisions or provenance.

### 10. No cross-source equivalence

Cross-source equivalence/merge is not implemented. Supplying an
`equivalence`/`equivalences` (or `merge`) key in the mapping manifest is a
configuration error rather than being silently ignored. Similar businesses
remain separate until an explicitly reviewed mechanism exists.

### 11. No inference of unsupported attributes

`opening_hours` is retained as original text under `operation_time` and is never
parsed into a verified schedule. No price, rating or hours default is
fabricated. Facts carry a raw content reference, JSON extraction path, license,
source URL, UTC retrieval timestamp, optional source revision and the
saved-bytes SHA-256.

## Consequences

- Positive: per-entity administrative review; deterministic idempotent output;
  immutable evidence; explicit review routing; policy changes re-evaluate
  compatibly with an audit trail; no fuzzy merging; no invented coordinates,
  districts or hours.
- Negative / risk: area/center OSM venues and any unlisted entity always require
  review, so only whitelisted point nodes accept automatically; a changed record
  stays quarantined until a reviewed update; once an entity is synthetic it never
  becomes real in the same state.
- No live ingestion, no network fetch and no graph write are performed.

## Verification

- `tests/acquisition/` (103 tests) covers per-entity admin, admin conflicts,
  provenance/pointer resolution, fact fingerprints, policy updates with audit
  history, synthetic exclusion and collisions, malformed identities/coordinates,
  invalid source ids/output overlap, malformed-second-source preservation,
  corrupt state, and a guarded `POI.model_validate` round-trip that preserves
  `poi_categories`.
- Raw run: `docs/project/handoffs/OC-006/pytest_oc006_repair.txt` → 177 passed
  (`tests/audit` 24, `tests/domain_identity` 8, `tests/ingestion` 42,
  `tests/acquisition` 103).
