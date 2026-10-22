# ADR 001 — Stable POI identity and validated domain coordinates

- Status: Accepted
- Date: 2026-10-15
- Task: OC-002
- Scope: `POI_service/app/core/domain/graph_entities.py` (`POI` model only)
- Supersedes: none

## Context

The `POI` Pydantic model previously rewrote every identifier during validation.
`POI.enforce_rules` (model validator, after-mode) rebuilt an id from the primary
category, city, district, street and the current date, then:

- generated a random `uuid4` suffix when `id` was empty, and
- replaced any supplied identifier that did not already start with the freshly
  computed prefix, keeping only the old text after the last `_`
  (e.g. `poi_imported_legacy_0001` → `Cafe_Hochiminhcity_District1_Leloi_20261015_0001`).

Consequences observed in the OC-001 baseline:

- External/legacy references were not stable across validation.
- Reprocessing or re-importing the same source record produced different ids
  depending on the day, the category and the address.
- The graph model could not be treated as idempotent, and later acquisitions
  could not reference deterministic source keys.
- Coordinates (`longitude`, `latitude`) were plain `float` with no finite or
  range checks, so `NaN`, `±inf`, `|lat| > 90` and `|lon| > 180` were accepted.
- Blank `id` and blank `name` were accepted; a blank id was silently replaced
  by an uncertain generated key at the API boundary.

This decision is recorded before acquisition expansion so that new records adopt
the contract from the start.

## Decision

1. **Explicit identifiers are immutable.** A supplied `id` is preserved
   byte-for-byte through `POI(...)`, `model_dump()` and re-validation. It is
   independent of category, address, district and date. Surrounding whitespace
   is *not* stripped, because the contract is byte-identity; only leading/
   trailing-whitespace-only values are rejected.
2. **Blank identifiers are rejected, not generated.** A missing, empty or
   whitespace-only `id` raises a validation error at the trusted boundary. The
   model no longer mints identifiers. Acquisition is responsible for supplying
   stable, source-derived identifiers.
3. **No automatic renaming.** The rewrite/rename branch and the UUID generation
   path are removed from `POI`. `enforce_rules` is deleted; its only
   responsibility was id construction. Existing populated models are unchanged
   because they already carry ids.
4. **Names are trimmed safely and may not be blank.** `name` is `.strip()`ed and
   a blank result is rejected.
5. **Coordinates are finite and in range.** `latitude` must be finite and within
   `[-90, 90]`; `longitude` must be finite and within `[-180, 180]`. Endpoints
   (including `±90`, `±180`, `0`) are accepted.

## Input contract (trusted boundary)

A valid `POI` payload must satisfy:

| Field | Contract |
|---|---|
| `id` | required; non-blank after `.strip()`; stored verbatim (no trim, no rewrite) |
| `name` | required; non-blank after `.strip()`; stored trimmed |
| `latitude` | required; finite; `-90 <= latitude <= 90` |
| `longitude` | required; finite; `-180 <= longitude <= 180` |
| `address`, `contact_info`, `tag`, `operation_time`, `rating` | optional, unchanged |
| `poi_categories`, `menu` | default to empty list; unchanged |

Rejected payloads raise `pydantic.ValidationError`; no partial object is
produced and no record is written by this layer.

## Migration and rollback

This change is **non-destructive at the data layer**: it does not read, write or
rename any graph node, and it is not a data migration.

- **No live migration is performed by this change.** Existing Memgraph nodes are
  untouched.
- **Earlier duplicates require a reviewed migration after a snapshot.** Because
  the old validator rewrote ids, historical records whose ids were regenerated
  from category/address/date may already exist under more than one spelling of
  the same real-world POI. Reconciling those nodes must be a separate, reviewed
  step that:
  1. takes a graph snapshot/backup first,
  2. proposes id merges by provenance, not by fuzzy name alone,
  3. records each rename in an auditable mapping, and
  4. verifies referential integrity (edges, MEMBER_OF, NEAR_BY) before commit.
  That work is explicitly out of scope here and must not be auto-run.
- **Rollback** for this change is a source revert of
  `POI_service/app/core/domain/graph_entities.py`; it is safe because no data
  was mutated. Reverting re-enables the old rewrite behavior for newly validated
  payloads only and does not undo any already-persisted ids (there are none from
  this change).

## Consequences

- Positive: stable external references, idempotent reprocessing, deterministic
  fixtures, and rejection of uncertain identity/coordinates at the boundary.
- Negative / risk: callers that relied on auto-generated ids now receive a
  validation error. Such callers must be updated by acquisition to supply
  source-derived ids. This is the intended behavior change and is covered by
  tests.
- The `POI_service` graph repository (`repositories/memgraph.py`) constructs
  `POI(**record["poi_data"])`; records read back from the graph remain valid as
  long as they carry a non-blank id and in-range coordinates.

## Verification

- `tests/audit/test_poi_identity_and_coordinates.py` — 24/24 pass (was 18
  failing, 6 passing).
- `tests/domain_identity/test_poi_identity_contract.py` — 8 new focused tests
  pass (byte-identical id incl. whitespace, missing id rejected, no rewrite when
  address/category absent, name trimming, blank name rejected, no rename on dump).
- Raw run: `docs/project/handoffs/OC-002/pytest_oc002.txt`.
