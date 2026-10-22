"""Primary dataset preparation capability (OC-034).

This is a bounded, offline capability that lives *inside* the existing crawler
service. It turns the supplied primary GeoJSON into faithful, schema-validated
POI import *candidates* with persistent local identity and complete lineage.

It deliberately performs no graph writes, no network access and no live
ingestion. It never claims graph acceptance, freshness or verified venue facts.
"""

from __future__ import annotations

PREP_VERSION = "oc-034.1"

# The supplied primary source family. This namespace is used only to label the
# internal, local identities this capability mints; it is NOT an upstream id and
# does NOT imply OSM/Wikidata provenance.
PRIMARY_NAMESPACE = "hcm_primary_geojson"

# The source_type passed to the existing acquisition ``stable_source_id`` helper.
# The value is explicitly an *internal* namespace so a prepared id can never be
# mistaken for a genuine upstream (e.g. OSM) identifier.
INTERNAL_SOURCE_TYPE = "hcm_primary_geojson_internal"

# The declared provided-at date (the date the dataset was handed over). This is
# NOT a retrieval time and NOT snapshot freshness; upstream collection time,
# source URL and license remain UNKNOWN.
DEFAULT_PROVIDED_AT = "2026-10-16"

DEFAULT_INPUT = "data/primary_20261016/hcm_pois_final.geojson"
DEFAULT_OUT_DIR = "data/primary_20261016/prepared"
