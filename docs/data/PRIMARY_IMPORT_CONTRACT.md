# PRIMARY POI IMPORT CONTRACT (OC-034)

Status: prepared/schema-validated **candidates** only. No graph write, no live
ingestion, no network call, no dataset publication, no raw mutation.
Language: English prose, Vietnamese data preserved verbatim.

This contract describes the bounded preparation capability added under
`crawler_service/app/primary_dataset/`. It consumes the immutable primary
GeoJSON audited in OC-032 and emits local import candidates with persistent
internal identity and complete lineage.

---

## 1. Reproduce

```
.venv-validation/Scripts/python.exe -m crawler_service.app.primary_dataset.cli \
    --input data/primary_20261016/hcm_pois_final.geojson \
    --out   data/primary_20261016/prepared
```

The CLI never contacts the network and never writes to the graph. A re-run with
the same input and registry is a byte no-op.

## 2. Artifacts and hashes

| Artifact | SHA256 |
|---|---|
| input `hcm_pois_final.geojson` (2,712,731 bytes, 6,368 features) | `713b07a62cf89bd2cad9093abaad2a4c5f01e23853321764b3d66bf9f7eee43c` |
| `data/primary_20261016/prepared/prepared_pois.jsonl` | `3944987f9e1d01f38c82b4e53b387a893d42811495a74ed461ea2f39d11485ad` |
| `data/primary_20261016/prepared/lineage.jsonl` | `70247a350da90ed11599a492cc1b8a453e560c5fe42540ec2a51e6b0cbdbabe4` |
| `data/primary_20261016/prepared/quarantine.jsonl` (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `data/primary_20261016/prepared/duplicate_ledger.jsonl` | `c00e8774c8203a75497f34ff2894ea26673d1ac919476e7b19f87f83823bbac2` |
| `data/primary_20261016/prepared/category_catalog.json` | `80491fcc75c6bda724d10973124dab77189d86bc8ea629bc1c4c1bddeae7d6cc` |
| `data/primary_20261016/prepared/identity_registry.json` | `de5594af7fc9dbf9039269b6ee5bd0989b291ea4bebdbaab37b5218730a03b65` |
| `data/primary_20261016/prepared/summary.json` | `1b69c250842794e0bcd6942453a42af1f580eeecd5d42b84ed4a1d5f9d4d15be` |

Counts (from `summary.json`):

| Metric | Value |
|---|---|
| input features | 6,368 |
| byte-equivalent canonical duplicate extras collapsed | 1 |
| candidate features (distinct exact feature encodings) | 6,367 |
| prepared records | 6,367 |
| quarantine records | 0 |
| prepared, review-required (legacy admin labels) | 411 |

Sumchecks: `prepared + quarantine == candidate_features` and
`candidate_features + duplicate_extra == input_features` are both true. The
input hash is unchanged after preparation.

## 3. Candidate payload contract

Each line of `prepared_pois.jsonl` is a POI payload validated with the **actual**
production model `POI_service.app.core.domain.graph_entities.POI` (via
`primary_dataset.validation`, isolated from other `app` namespaces). No
hand-copied parallel schema exists.

Fields:

* `id` — internal canonical id (see §4). Never blank.
* `name` — `processed_name` when nonblank, else raw `name` verbatim.
* `latitude` / `longitude` — finite, in range; equal to the property `lat`/`lon`
  and the Point geometry (which is `[lon, lat]`).
* `poi_categories` — exactly one closed-catalog category (see §5).
* `address` — source-snapshot area only (see §6).
* `operation_time` — the raw `opening_ho` string, unparsed, or `null`.
* `menu` — `[]`; `rating` — `null`; `contact_info` — `null`; `tag` — `null`.

There are no price, rating or route fields in the source, so none is populated;
an unknown visit cost stays unknown rather than becoming `0`.

## 4. Internal identity contract

No genuine upstream identifier exists in the source. The capability therefore
mints clearly-labelled **internal** ids:

```
id = stable_source_id("hcm_primary_geojson_internal", "rNNNNNN")
   = "hcm_primary_geojson_internal:<sha256(...)[:32]>"
```

* The local `record_id` (`rNNNNNN`) lives in the persistent registry
  `identity_registry.json`; assignment is deterministic and sorted by the strict
  identity key, so a re-run or a reordered input keeps the same ids.
* The strict identity key is `namespace | normalized_name | exact_coords |
  source_address_anchor`. Same brand at different coordinates is distinct.
* Collisions and silent reidentification fail closed: two distinct features
  claiming one identity key, a changed identity field set, or a foreign/tampered
  registry all raise before any byte is written.
* `identity_scope = internal_local_only` and
  `cross_export_matching = not_guaranteed` are recorded in the registry, the
  lineage and the summary. Prepared ids are NOT OSM/Wikidata ids and are NOT a
  raw-hash-plus-row-index cross-export identity.
* Registry integrity is validated on load: every record is checked against the
  whole reverse/index relation, record ids must match
  `stable_source_id(INTERNAL_SOURCE_TYPE, record_id)`, sequences/ids must be
  unique, counters must be real integers (booleans/float versions rejected),
  hashes must be well-formed and identity components must reproduce the stored
  identity key. A persisted registry must carry a non-null current
  `input_sha256`, even when it has no records, and its `identity_scope` /
  `cross_export_matching` metadata must be exactly
  `internal_local_only` / `not_guaranteed`; contradictory metadata is rejected
  rather than treated as trusted. This is internal consistency checking, not
  authenticated tamper protection.

### 4.1 Revisions, reorders and no-ops

* Same bytes + same registry → the run is a **byte no-op**; ids and outputs are
  unchanged.
* **Any changed source bytes** — reordering, a non-identity field edit such as
  opening hours, or an identity change — is a *new revision* and must be run with
  the explicit `--accept-input-revision` flag. Without it the run fails closed
  before any output mutation.
* `prior_input_sha256` is an **ordered chronological list of superseded
  revisions**, not a set of unique hashes. Repeats and a return to earlier source
  bytes are legitimate (`A → B → A → B` is valid), so the list is never collapsed,
  sorted or rewritten. Each entry must still be a well-formed SHA256.
* On an accepted revision the registry updates the current `input_sha256`,
  appends the superseded hash to the chronological history, and writes immutable
  previous-registry evidence named by the **full content digest** of the prior
  registry: `identity_registry.prior-<prior_registry_sha256>.json`. Because the
  digest covers the whole prior registry (history included), repeated source
  hashes with different registry state cannot collide, overwrite or discard
  earlier evidence. Existing backups are retained with no automatic cleanup.
* **Changed identity fields** also require the explicit flag. New identities are
  assigned new ids; removed identities are retained (flagged `retired`) rather
  than erased; reactivated identities keep their existing record and id;
  unchanged identities keep their existing ids. There is no silent rename,
  renumbering or history replacement.
* The prospective registry state and the exact save payload are validated, and
  backup collisions and the required revision flag are preflighted, before any
  pipeline output is mutated. A supplied payload that disagrees with the
  validated in-memory state is rejected. This is a **fail-before-write
  consistency contract**; it is not a claim of full filesystem crash
  transactionality or concurrent-writer safety.

## 5. Category catalog contract

`category_catalog.json` is a closed catalog of exactly the **14** observed
source labels (`CATALOG_VERSION` is bound into every lineage row). Each id is
namespaced (`hcm_primary_geojson:source-category:<label>`) and each context
describes the source label only. An unobserved label is quarantined as
`unknown_source_category`; no finer category, rating, price or tag is invented.

## 6. Address / administrative scope contract

The payload `address` carries the SOURCE-snapshot area labels verbatim
(`addr_city` = `HCMC`, `addr_district`, optional `addr_ward`, combined
house+street as `street_name`). This is explicitly:
`address.scope = source_snapshot_area_only`, `current_admin_claim = none`.

The existing POI `Address` schema cannot express a qualified legacy area that may
fall under a different present-day jurisdiction. Legacy source labels (`Di An`,
`Thuan An`, `Thu Dau Mot`) are therefore preserved verbatim and flagged
`legacy_admin_qualification_unresolved` (411 records) rather than being silently
declared inside or outside modern HCMC. No dated current ward is assigned and no
legislative boundary containment is claimed from the coordinate bounding box.

## 7. Lineage contract

`lineage.jsonl` binds every prepared id to:

* the source input path, SHA256 and the canonical source feature index;
* the exact feature hash, geometry, cluster and the full raw properties;
* the identity derivation (namespace, key components, `name_source`);
* the catalog version and source category label;
* the raw address fields and the source-snapshot scope;
* the raw opening-hours string with `parse_status = unparsed_source_text`;
* price `status = unknown`;
* provenance: `provided_at` known, while `collection_time`, `source_url`,
  `license` and `freshness` remain `UNKNOWN`.

The lineage is a sidecar artifact; it is NOT claimed to be persisted in any
graph. A later storage/ingestion extension is required to carry it into the
graph.

## 8. Explicit non-claims

* These records are NOT accepted graph nodes, NOT verified venues, NOT fresh
  data, and do NOT carry genuine upstream/source identifiers.
* Provenance (collection time, source URL, license, freshness) is unknown and is
  not inferred from the filename or `processed_name`.
* The 312 normalized-name-only groups are multi-branch brands, not duplicates;
  only the one byte-equivalent pair (indices 4855/4859) is collapsed.

## 9. Semantic gap and next integration step

Gap: the graph has no qualified-admin representation, and the 14 source category
ids are not mapped to live graph `Category` nodes.

Next step: supply an authorised, dated administrative mapping (or a graph-side
qualified-admin field) plus a reviewed mapping of the 14 source category ids onto
live graph `Category` ids, then add a storage/ingestion extension that carries
this sidecar lineage into the graph.
