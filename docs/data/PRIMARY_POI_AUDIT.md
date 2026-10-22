# PRIMARY POI DATASET AUDIT — hcm_pois_final.geojson (OC-032)

Status: characterisation only. No graph write, no ingestion, no dataset publication, no raw mutation.
Language: English prose, Vietnamese vocabulary preserved verbatim.
Auditor role: QA/implementation (interpretation boundary is retained by the reviewer).

---

## 1. Scope and method

This audit characterises the newly supplied primary dataset so it can later be
integrated against the existing POI service contracts. It deliberately does not
assume graph acceptance, does not invent provenance, and does not recover or
claim the original ~200-POI thesis dataset.

Reproduce with (standard library only, read-only input):

```
python data/primary_20261016/audit_primary_pois.py \
    --json-out data/primary_20261016/audit_summary.json
```

Deterministic: two consecutive runs produced byte-identical
`audit_summary.json`. The raw dataset hash was unchanged after the audit.

Evidence base:

| Artifact | Path |
|---|---|
| Reproducible audit script | `data/primary_20261016/audit_primary_pois.py` |
| Machine-readable summary | `data/primary_20261016/audit_summary.json` (SHA256 `4e47f2c817cf3e576ac33794c889c474fd73adda25c9dc91fa8239ffa124e3fb`) |
| Frozen snapshot manifest | `data/primary_20261016/SNAPSHOT_MANIFEST.json` |
| Provenance manifest | `data/primary_20261016/source_provenance_manifest.json` |

Contract references inspected read-only: `POI_service/app/core/domain/graph_entities.py`
(`POI`, `Address`, `Category`, `ContactInfo`), `POI_service/app/core/domain/get_payload.py`,
`POI_service/app/core/services/ingestion.py`, `POI_service/app/core/utils/helper.py`,
`crawler_service/app/acquisition/{identity,contracts}.py`,
`data/acquisition/examples/mapping.example.json`, `docs/project/MASTER_GOAL.md`.

---

## 2. Raw integrity

| Check | Observed | Expected (parent assertion) | Match |
|---|---|---|---|
| bytes | 2,712,731 | 2,712,731 | yes |
| SHA256 | `713b07a62cf89bd2cad9093abaad2a4c5f01e23853321764b3d66bf9f7eee43c` | same | yes |
| features | 6,368 | 6,368 | yes |
| geometry type | Point × 6,368 | Point only | yes |
| CRS | `urn:ogc:def:crs:OGC:1.3:CRS84` | — | declared |
| top-level keys | `type`, `name`, `crs`, `features` | — | — |

All six parent assertions (hash, bytes, feature count, geometry, CRS, Point-only)
are independently confirmed. The raw file was not modified.

Encoding: decodes cleanly as UTF-8; 0 features contain the replacement character
U+FFFD; 0 features contain control characters. 3,594 names, 2,668 street strings
and 58 ward strings contain non-ASCII (Vietnamese diacritics), which are genuine,
not mojibake.

---

## 3. Schema and field coverage

13 property keys per feature, present in all 6,368 features (key count is uniform):

| Property | Nonblank present | Null/absent | Notes |
|---|---|---|---|
| `name` | 6,368 | 0 | required string |
| `processed_name` | 6,367 | 1 | null at index 5369 (`Hổ`) |
| `poi_category` | 6,368 | 0 | 14-value vocabulary |
| `addr_city` | 6,368 | 0 | uniformly `HCMC` |
| `addr_district` | 6,368 | 0 | 26-value vocabulary |
| `addr_ward` | 59 | 6,309 | mostly missing |
| `addr_full` | 183 | 6,185 | mostly missing |
| `addr_house` | 2,252 | 4,116 | |
| `addr_stree` | 2,775 | 3,593 | |
| `opening_ho` | 1,055 | 5,313 | raw, heterogeneous |
| `cluster` | 6,368 | 0 | `0` × 6,366, `-1` × 2 |
| `lat` | 6,368 | 0 | numeric |
| `lon` | 6,368 | 0 | numeric |

No `id`-like property exists anywhere (no field name contains `id`). There are no
price columns, no rating columns and no route/road-network evidence columns.

---

## 4. Coordinate and geometry quality

GeoJSON geometry order is `[lon, lat]`; the properties carry explicit `lat`/`lon`.

| Check | Count |
|---|---|
| missing geometry | 0 |
| non-Point geometry | 0 |
| wrong coordinate shape (not 2-element) | 0 |
| non-finite geometry coordinate | 0 |
| geometry coordinate out of global range | 0 |
| property `lat`/`lon` missing or non-finite | 0 |
| property `lat`/`lon` out of global range | 0 |
| geometry vs property lat/lon mismatch | 0 |
| max abs difference (geometry vs property) | 0.0 |
| outside a coarse HCMC box (informational) | 0 |

Every feature is a Point whose coordinates exactly equal the property `lat`/`lon`,
in `[lon, lat]` order, all finite and in range, all inside the coarse HCMC extent
`lat∈[10.3,11.2]`, `lon∈[106.3,107.1]`. Coordinate order and consistency are
therefore unambiguous for this file.

---

## 5. Category vocabulary (14 values)

| poi_category | count |
|---|---|
| coffee | 1,097 |
| convenience | 1,032 |
| restaurant | 1,010 |
| finance | 605 |
| lodging | 568 |
| specialty_food | 468 |
| apparel_and_gifts | 365 |
| health_and_beauty | 340 |
| retail_center | 339 |
| attractions | 238 |
| entertainment | 170 |
| fuel | 78 |
| transport | 34 |
| public_services | 24 |
| **total** | **6,368** |

These are free-form source labels. They are **not** a reviewed category catalog.
The existing `POI` model expects `poi_categories: List[Category{id,name,context}]`
drawn from a closed catalog (see MASTER_GOAL §1.6 and the acquisition
`mapping.example.json`, which maps raw tags to catalog ids). Mapping these 14
labels to catalog ids is an unreviewed step and must not be silently invented.

---

## 6. Administrative vocabulary and ambiguity

- `addr_city`: single value `HCMC` for all 6,368 records (coarse, uniform).
- `addr_district`: 26 source labels, including historical HCMC district/city
  names (`Quan 1`, `Quan 7`, `Binh Thanh`, `Phu Nhuan`, `Thu Duc`) and names
  associated with the former Binh Duong area (`Di An`90, `Thuan An`196,
  `Thu Dau Mot`125). These labels are not a verified current district catalog.
- `addr_ward`: 33values on59records, mixing ward and commune labels
  (`Phường 10`, `Phường Thảo Điền`, `Xã Trung Chánh`). Label syntax alone does
  not establish current jurisdiction or the date of the source boundary.

This is a historical/current administrative ambiguity. Official government
material confirms the2025merger of HCMC, Binh Duong and Ba Ria–Vung Tau into
HCMC, and the subsequent ward/commune reorganization. Therefore the three
former Binh Duong labels must not be declared outside present-day HCMC solely
from their historical names. Preserve source labels as historical area evidence;
current jurisdiction requires a dated boundary/administrative mapping. An audit
bounding box is not an administrative boundary.
[Government merger account](https://tphcm.chinhphu.vn/thanh-lap-15-co-quan-chuyen-mon-thuoc-ubnd-tphcm-10125070118092267.htm),
[official ward/commune reorganization](https://tphcm.chinhphu.vn/danh-sach-chinh-thuc-168-phuong-xa-cua-tphcm-sau-sap-xep-101250617000144317.htm).

Note (read-only): `POI_service/app/core/utils/helper.py` loads
`location_mapping.json`, but only `city_mapping.json` exists in the repository.
At runtime the city/district mapping dictionaries therefore fall back to empty,
so any ID normalisation relying on them would currently receive no mappings.
This is a pre-existing integration gap, reported, not modified.

---

## 7. Opening hours

- present for 1,055 / 6,368 records (16.6%); absent for 5,313.
- 341 distinct raw strings. Heterogeneous syntax: plain ranges (`07:30-21:30`),
  `24/7` (324 records), OSM weekday syntax (`Mo-Fr 07:30-17:00`), Vietnamese
  annotations (`Mo-Sa 09:00-17:00; PH closed "Nghỉ lễ"`), free prose
  (`Big Pig Truong Son opening hours`), and a few clearly malformed values
  (`Mo-Su 03:00-03:00`, `Mo-Sa 08:00-06:00`).

Raw text must be preserved. The `POI.operation_time` field is a free string and
can store the original text unparsed; it cannot be assumed to be machine-parsable
or current. Parsing/validating hours is a review task and must not imply freshness.

---

## 8. Prices and route evidence

No price field and no route/road-network evidence exist in the supplied schema.
`POI.menu: List[Product{id, product_name, price}]` therefore cannot be populated
from this file, and no itinerary/route claim can be grounded on it. This is a
documented completeness gap, not a defect to fabricate around.

---

## 9. Duplicate structure (nothing dropped or merged)

| Key | distinct keys | duplicate groups | extra records beyond first | max group |
|---|---|---|---|---|
| exact feature (canonical JSON) | 6,367 | 1 | 1 | 2 |
| normalized name + rounded coordinate | 6,367 | 1 | 1 | 2 |
| normalized name only | 4,369 | 312 | 1,999 | 238 |

- Exact duplicate: indices **4855** and **4859** — both `Hannah's Kitchen VN`
  at `106.689694,10.799914`, cluster 0. The two records are byte-identical
  features.
- The single normalized-name+coordinate group is the same pair.
- The 312 normalized-name-only groups (1,999 extra records) are dominated by
  legitimate multi-branch brands — e.g. `winmart` (238), `techcombank` (178),
  `pnj` (103), `bachhoaxanh` (88), `circlek` (79), `highlandscoffee` (76) — each
  at distinct coordinates. Name equality does **not** prove entity identity, and
  these are NOT duplicates to be merged.

No records were silently deduplicated or dropped. Duplicate handling is deferred
to explicit review criteria.

---

## 10. Provenance and source identifiers

- The file has **no** provenance block: top-level keys are only `type`, `name`,
  `crs`, `features`.
- **No per-feature ID / source identifier exists.** Feature IDs were absent in
  the initial samples and remain absent across all 6,368 features.
- Collection time, upstream platform/URL, license and freshness are **UNKNOWN**.
  They must not be inferred from the filename `hcm_pois_final` or from the derived
  `processed_name` field. The provided-at date is not retrieval or snapshot
  freshness.

Contrast: the sibling `data/expansion_20261015/` 32-record expansion sample DOES
record raw SHA256, retrieval UTC, URL, license and HTTP outcome in
`fetch_manifest.json`. The primary dataset does not, so provenance tracking for
the primary dataset is a **review gap**.

---

## 11. Identity and normalization proposal

Existing stable-identifier contract
(`crawler_service/app/acquisition/identity.py`):

```
stable_source_id(source_type, source_entity_id)
    = f"{source_type}:{sha256(source_type + 0x1f + source_entity_id)[:32]}"
```

Integration into that contract requires a genuine source entity id. This dataset
supplies none. Therefore:

1. **No genuine source-derived stable id can be computed** for these records. A
   value must not be minted by hashing the raw file + row index and presented as a
   cross-export stable identity.
2. **Interim derived candidate key (review only).** For dedup/review purposes the
   audit computes a namespace-prefixed derived key
   `hcm_primary_geojson:derived:<sha256(normalized_name + rounded_coord)[:32]>`.
   This is explicitly a *derived candidate identity*, is NOT a source identity,
   and is fragile if coordinates change across exports. It produced 6,367 distinct
   keys for 6,368 features; the single collision is the exact-duplicate pair
   (indices 4855/4859) and must go to collision review, never be auto-merged.
3. **Required path to a true stable id.** A reviewed source entity id (e.g. an
   upstream OSM/Wikidata id or another genuine stable key) must be supplied, then
   `stable_source_id("hcm_primary_geojson", source_entity_id)` can be used.

Normalization key (comparison only, not identity): NFKD accent fold → ASCII →
lowercase → strip non-alphanumerics. This is used only to form duplicate-review
groups; it is not an identity claim and never replaces the primary count.

---

## 12. Source-contract mapping to the existing POI schema

Incoming property → `POI_service/app/core/domain/graph_entities.py` field:

| Incoming | Target POI field | Fidelity / caution |
|---|---|---|
| `name` | `name` (required, nonblank) | trims; safe |
| `lat` / `lon` | `latitude` / `longitude` (required, finite, in range) | geometry is `[lon, lat]`; both exact and verified |
| `poi_category` | `poi_categories[].id/name/context` | 14 raw labels; **no reviewed catalog mapping yet** → would be `unknown_category` |
| `addr_city` | `address.city` (required, min 1) | uniform `HCMC`; `.title()` becomes `Hcmc` |
| `addr_district` | `address.district` (required, min 1) | 26 values incl. non-HCMC (Di An/Thuan An/Thu Dau Mot); ambiguity |
| `addr_ward` | `address.ward` (optional) | present for only 59 records |
| `addr_stree` (+`addr_house`) | `address.street_name` (optional) | `Address` has no full/queue field; house+street must be combined by policy |
| `addr_full` | (no direct field) | keep as provenance/address hint only |
| `opening_ho` | `operation_time` (optional str) | store raw, unparsed; do not imply freshness |
| `processed_name` | (none) / normalization key | derived; not a schema field |
| `cluster` | (none) | metadata only |
| — | `address.nation` | default `Vietnam` |
| — | `contact_info`, `tag`, `rating`, `menu`, `id` | not supplied by this file |

Contract-behaviour notes (from `ingestion.py`): batch validation uses
`POI.model_validate`; a record without a nonblank `id` fails validation and would
be counted `validation_failed`, not accepted. Because these records currently carry
no id and no reviewed category mapping, none would be structurally ingestible
as-is without a reviewed integration step.

---

## 13. Structural validity vs review-needed (explicit criteria)

Structurally valid requires ALL of: Point geometry with 2 finite in-range
coordinates; property `lat`/`lon` present, finite, in range and exactly equal to
the geometry; nonblank required strings `name`, `processed_name`, `poi_category`,
`addr_city`, `addr_district`.

| Classification | Count |
|---|---|
| structurally valid | 6,367 |
| review needed | 1 |
| reason: `missing_required:processed_name` | 1 (index 5369, `Hổ`) |

Optional-field absence (hours, prices, ward, house, full address) is a
*completeness gap*, not a structural failure, and is not counted here.

These are **not** accepted POIs, not graph nodes, and not proof that the original
~200-POI dataset was recovered. "Structurally valid" only means the record passes
the explicit mechanical criteria above.

---

## 14. Prospective test / experiment split and performance reference

Prospective only — not executed in this task; no H1/H2/H3 result is asserted.

- Deterministic split, suitable for the full 6,368 scale: derive a split index
  from a fixed-seed hash over the derived candidate key (e.g. first 8 hex digits
  mod 100) so the split is reproducible without a stateful RNG and never depends
  on row order.
- Default reserve: hold out a labelled `test` partition and keep the remainder as
  `experiment`; every emitted sample must be explicitly labelled `sample` and
  must never overwrite the primary feature count of 6,368.
- Keep the primary 6,368-feature dataset strictly separate from the 32-record
  `data/expansion_20261015/` expansion source in all splits and manifests.
- Performance reference for exhaustive spatial work at this scale:
  `C(6368,2) = 6,368 × 6,367 / 2 = 20,272,528` unordered pairs. This is the
  reference cost of an exhaustive pairwise pass that an optimised bounding-box /
  Haversine prefilter is expected to reduce; actual measured counts, runtime and
  hardware must be recorded before any performance claim.

---

## 15. Action list (review gaps)

1. Obtain a genuine stable source identifier (or authorise the documented derived
   candidate key with explicit review) before any graph integration.
2. Review and map the 14 `poi_category` labels onto the closed category catalog;
   unknown labels must not be invented.
3. Resolve the administrative ambiguity (non-HCMC `Di An`/`Thuan An`/
   `Thu Dau Mot` under a blanket `HCMC` city) against an authorised source.
4. Decide policy for `addr_full` and house+street combination into
   `address.street_name`.
5. Decide whether the exact-duplicate pair (indices 4855/4859) is merged,
   quarantined, or retained, under explicit criteria — never silently.
6. Define a parse/validation policy for the 341 raw opening-hours strings; store
   raw text and never present it as current.
7. Supply provenance (source, URL, license, retrieval UTC) for the primary
   dataset, matching what `data/expansion_20261015/` already records.

---

## 16. Facts, inferences, and gaps

**Facts (observed):** raw hash/bytes/feature count match parent assertions; all
Point geometry; exact geometry/property coordinate equality; 14 categories; 26
districts; 1 city value; 1,055 records with hours; no ids, no prices, no route
evidence, no provenance block; 1 exact-duplicate pair; 312 normalized-name
collision groups; 1 record missing `processed_name`.

**Inferences (labelled):** the district vocabulary suggests the dataset may span
into Binh Duong province despite the blanket `HCMC` label; the normalized-name
groups are consistent with multi-branch brands rather than duplicates. Both are
hypotheses requiring review, not conclusions.

**Gaps:** provenance, genuine source ids, category catalog mapping, administrative
resolution, hours semantics, price/route absence, and the `location_mapping.json`
helper mismatch.

**Explicit non-claims:** the 6,368 features are not asserted to be accepted graph
nodes, unique entities, or the recovered original ~200-POI dataset; no collection
time, license, OSM origin or freshness is inferred; no experiment result is
produced here.
