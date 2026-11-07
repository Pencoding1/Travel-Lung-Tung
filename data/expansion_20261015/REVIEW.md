# Real-source sample review — updated 2026-10-16

This directory is an expansion research sample, separate from the original approximately200-POI thesis dataset. It contains actual fetched Wikidata JSON, not synthetic fixtures. Raw file SHA256, retrieval UTC time, URL, license and HTTP outcome are in fetch_manifest.json. No graph ingestion has occurred.

| Entity | Source revision | Observed support | Decision |
|---|---|---|---|
| Q703871 — Bảo tàng Chứng tích chiến tranh | 2485330483 | Vietnamese/English labels; P31=Q2772772; Earth P625=(10.7795,106.692), declared precision0.0091445148331537 degrees; P131=Q1926820; P276=Q1854 | REQUIRES_REVIEW: coarse coordinate precision; current versus historical administrative context; category mapping against live catalog absent. Do not silently replace coordinate from a cached page. |
| Q933384 — Dinh Độc Lập | 2527489480 | Vietnamese/English labels; P31=Q2114972; Earth P625=(10.77705,106.69537), precision0.0001 degrees; P131=Q1854 | REQUIRES_REVIEW: no district claim in this raw record; venue/entrance interpretation and live category catalog pending. |

Wikidata structured data is CC0. Attribution retained voluntarily with raw sources: https://www.wikidata.org/wiki/Q703871 and https://www.wikidata.org/wiki/Q933384. No photographs or linked article text were downloaded. Claim existence is source support, not independent proof of correctness/currentness.

OSM collection: one bounded museum bounding-box request to overpass-api.de returned502. A single narrower known-way retry (186249226) also returned502. Both failures are preserved in fetch_manifest.json; neither counts as an acquired OSM record. Stop retrying this unavailable endpoint. The local graphhopper/data/hcmc-latest.osm.pbf subsequently provided an offline alternative: OC-012 extracted30 named nodes from401 matching nodes in the declared bounding box. Header evidence identifies the BBBike generator and OSM snapshot timestamp2026-03-17T23:00:00Z; download URL/time remain unknown. The derived export timestamp2026-10-15T10:52:59Z is not source freshness. See osm_local/osm_local_provenance.json and the OC-012 report.

The public Overpass usage guidance permits bounded manual queries and discourages using the shared instance as an application backend: https://dev.overpass-api.de/overpass-doc/en/preface/commons.html. OSM data licensing and service-use policy are separate. Do not switch to the editing API for this read-only acquisition workflow.

Current retained counts independently checked on2026-10-16:32 quarantined candidates (30 OSM nodes and2 Wikidata entities),0 accepted. All32 carry entity_unreviewed, unknown_category and unknown_admin. The mapping contains provisional categories but no reviewed entities, district mappings or source category mappings. The repeat run reports32 duplicates. These artifacts establish two real source families collected; graph expansion and operational live integration remain incomplete.

