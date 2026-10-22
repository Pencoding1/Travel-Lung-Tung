# PRIMARY GRAPH-READY SNAPSHOT (OC-043)

Status: **graph-ready candidate artifacts** for the exact reviewed primary
snapshot. This is not an accepted graph import, not venue verification and not a
claim of current jurisdiction. The adapter is offline: it makes no graph,
network, model, Docker or API call.

## 1. Scope

The adapter lives at
`POI_service/app/core/utils/primary_snapshot.py`. It reads the frozen OC-034
primary preparation artifacts read-only, verifies every reviewed byte binding and
cross-artifact invariant, and emits payloads that the existing `POI` model and
`POIIngestionService` REST batch path already consume. No parallel importer,
service or crawler import was added to the POI service.

It is **not** a general arbitrary-hash accepter. Real mode is bound to the exact
reviewed input hashes below. A non-real fixture plan is possible only through the
isolated library test path; it always emits `dataset_class: "synthetic_fixture"`
and is refused if it targets the real destination.

## 2. Reproduce

From the repository root with `POI_service` importable:

```
.venv-mcp-validation/Scripts/python.exe -m pytest tests/primary_snapshot_adapter -q -p no:cacheprovider
```

Validation only (no write):

```
cd POI_service
..\.venv-mcp-validation\Scripts\python.exe -m app.core.utils.primary_snapshot --check --json
```

Write once, only when `data/primary_20261016/graph_ready_v2/` does not exist:

```
cd POI_service
..\.venv-mcp-validation\Scripts\python.exe -m app.core.utils.primary_snapshot --write --json
```

The CLI defaults to the reviewed destination and refuses any other real path. It
also refuses to overwrite an existing destination.

## 3. Verified inputs

All seven required artifacts plus the two read-only source manifests are hashed
before parsing or any output-directory creation.

| Artifact | Bytes | SHA256 |
|---|---:|---|
| `data/primary_20261016/hcm_pois_final.geojson` | 2,712,731 | `713b07a62cf89bd2cad9093abaad2a4c5f01e23853321764b3d66bf9f7eee43c` |
| `data/primary_20261016/prepared/prepared_pois.jsonl` | 3,253,885 | `3944987f9e1d01f38c82b4e53b387a893d42811495a74ed461ea2f39d11485ad` |
| `data/primary_20261016/prepared/lineage.jsonl` | 12,399,103 | `70247a350da90ed11599a492cc1b8a453e560c5fe42540ec2a51e6b0cbdbabe4` |
| `data/primary_20261016/prepared/identity_registry.json` | 3,777,966 | `de5594af7fc9dbf9039269b6ee5bd0989b291ea4bebdbaab37b5218730a03b65` |
| `data/primary_20261016/prepared/category_catalog.json` | 3,025 | `80491fcc75c6bda724d10973124dab77189d86bc8ea629bc1c4c1bddeae7d6cc` |
| `data/primary_20261016/prepared/duplicate_ledger.jsonl` | 387 | `c00e8774c8203a75497f34ff2894ea26673d1ac919476e7b19f87f83823bbac2` |
| `data/primary_20261016/prepared/summary.json` | 4,755 | `1b69c250842794e0bcd6942453a42af1f580eeecd5d42b84ed4a1d5f9d4d15be` |
| `data/primary_20261016/source_provenance_manifest.json` | 2,282 | `6aff7d923b94642efbcdca48e517d19b64eb1374f8e8b3bd0a7bd4bf73e49c94` |
| `data/primary_20261016/SNAPSHOT_MANIFEST.json` | 2,198 | `b69f882b41296669ee6d01c5f36c2a260685a5127d9bcb10973da62318d60402` |

The adapter additionally requires the reviewed namespace (`hcm_primary_geojson`),
provided date (`2026-10-16`), source class
(`hcm_primary_geojson_internal`), catalog version (`1e39b6e91122c6ee`),
6,368 input features, 6,367 prepared records, 14 source categories and exactly
one declared duplicate pair to agree across the summary, catalog, lineage and
registry.

## 4. Validation gate

Before any output directory is created or written, the adapter rejects:

* missing, truncated or hash-mismatched inputs;
* duplicate JSON keys, non-finite numbers, invalid UTF-8 or malformed JSONL;
* duplicate or conflicting prepared/lineage/registry ids and identity keys;
* contradictory lineage `source` body, geometry, properties, feature hash,
  input hash, namespace, provided date, category or address evidence;
* out-of-range, boolean, duplicate or orphan canonical source indices;
* registry record id/sequence/identity/index disagreements and bad id derivation;
* source-index coverage that is not exactly the 6,368 input indices, each once
  (6,367 canonical records plus index `4859` as the declared duplicate of `4855`);
* duplicate-ledger rows whose hash or indices contradict the source bodies;
* any `POI.model_validate` failure after metadata construction.

The adapter does not repair coordinates, names, categories, prices or addresses,
and it does not mint ids or revisions. Existing frozen-v1 data is not replaced.

## 5. Outputs and hashes

Generated at `data/primary_20261016/graph_ready_v2/`:

| Artifact | Bytes | SHA256 | Records |
|---|---:|---|---:|
| `prepared_pois.jsonl` | 20,189,659 | `37340a8021ca7e8b37efc1053718c4c87879f95fa9937d8c53e1a0218f080dd1` | 6,367 |
| `manifest.json` | 4,867 | `b496f94214f8ae9482333bbb60a403ce92f932b1e467bffdd49ce40e9d641f71` | — |
| `checksums.sha256` | 166 | `90af14f1bf4726ef3f4e59d9b263eb16e2a2c2aad04b837c3149d1c05350471b` | — |

`checksums.sha256` contains the hashes of `prepared_pois.jsonl` and
`manifest.json`. Outputs are sorted by exact stable POI id, canonical compact
UTF-8 JSONL with LF newlines. The manifest contains stable facts only; it has no
runtime timestamp and no nondeterministic output hash.

Each output line is the original prepared payload with every existing field value
unchanged plus a typed `source_metadata` block carrying:

* the canonical compact full lineage row and its SHA256;
* the source feature hash (spaced `json.dumps` recipe over
  `type`/`properties`/`geometry`) and input hash;
* namespace, provided date, canonical source index and duplicate indices;
* `internal_local_only`, `not_guaranteed` cross-export matching and
  `source_snapshot_area_only`;
* `null` collection time, source URL, license and freshness.

## 6. Source-index conservation

| Accounting | Count |
|---|---:|
| Input Point features | 6,368 |
| Canonical prepared records | 6,367 |
| Declared duplicate extra (`4859` of `4855`) | 1 |
| Source indices covered exactly once | 6,368 |
| Categories | 14 |
| Prepared review-required flags | 411 |

The duplicate ledger binds both raw bodies and the canonical lineage row to the
same exact feature hash
`92f553352abbf6d43900fa5fd75c336101dfbbca7088d597643e03a6f8695e9d`.

## 7. Explicit non-claims and limits

* These are candidate artifacts, **not accepted graph nodes**, verified venues,
  routes, primary H2/H3 results or full-goal completion.
* No graph, live ingestion, network, model, Docker or API call occurred.
* No input raw/prepared/lineage/registry/catalog/ledger file was modified.
* Source administrative labels are source-snapshot area claims only; no current
  City/District mapping, boundary containment or freshness is claimed.
* Collection time, source URL, license and freshness remain `UNKNOWN`.
* The reviewer-owned OC-038 R1 acceptance remains an independent prerequisite
  before any live import. This adapter did not edit OC-038 files or claim final
  R1 acceptance.
* Future real/synthetic dataset-family expansion is a separate write boundary
  (`T050`). This adapter does not claim general dataset-class enforcement from an
  extra payload field.
* The adapter intentionally does not implement T049 catalogue tooling or a
  live-integration contract.
