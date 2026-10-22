# Explicit source-snapshot area selection

Status: parent architecture decision for T048/T049, not an implemented or live-verified capability. The current metadata prototype must first pass its independent corrective gate.

Implementation status (OC-045, server portion only): the POI
domain/repository/service/MCP path now implements explicit typed source-snapshot
selection, deterministic qualified source-area ids, bounded discovery, flat
derived selector cache properties on all three writes, fail-closed read
qualification and truthful scan/truncation/corruption reporting. The detailed
recipe and surface are in `docs/data/SOURCE_SNAPSHOT_SELECTION_CONTRACT.md`.
This does **not** include a live graph run, a primary import, AI/planner
selected-scope retention, deployment, full T049 completion or any present-day
administrative/venue/route claim.

The supplied GeoJSON's city/area labels are usable as **source labels**, but are not a verified dated mapping of current administrative boundaries. Keeping them outside ordinary current City/District containment protects the grounding contract. It must not make all6367candidate records permanently unusable by the system.

Use an explicit request scope consisting of dataset namespace, input snapshot SHA256 and a source-area identifier. The server derives a source-area identifier deterministically from the exact qualified tuple(namespace,snapshot,raw city,raw area); it is not a current District ID. Return human-readable raw labels and qualification alongside it. Reuse existing ingestion/MCP/services rather than introducing a competing importer or service. Flat scalar POI properties derived from validated lineage can support indexed source-area grouping/filtering without requiring new ordinary administrative nodes or relationships.

Provide discovery/selection through existing tools: list available source snapshots and their qualified source areas, then retrieve candidates for a chosen snapshot/area/category. Parameters remain bound values, never query fragments. A returned record must match the selected namespace/snapshot/area evidence. Unknown/foreign/mismatched selectors fail closed. Stored provenance corruption is not a legacy/current scope. Current city/district requests keep their existing distinct path; source-only records cannot become current containment from labels or requested IDs.

The AI/planner may use source-only candidates only when the request explicitly selects that source-snapshot mode. Bind grounding to the returned qualified evidence and preserve `unverified_source_area` for current administration. Do not fill ordinary current context with invented IDs or silently let the model change the user's scope. Reject conflicting current/source selections. A user-facing explanation should describe the available source labels and current-boundary uncertainty; it should not expose implementation details. Frozen experiments can explicitly declare this mode in their manifests, using the same facts/constraints for both arms.

Keep full raw lineage in storage/full audit CRUD and compact evidence in AI-facing output. A versioned graph-ready adapter must preserve the6367existing IDs,14source category IDs and6368source-index conservation while binding genuine frozen lineage and the one duplicate entry. Preserve raw/prepared-v1 artifacts even if a later output schema changes. Unknown prices/hours/freshness remain unknown; source-scope matching is not venue verification or route/itinerary feasibility.

T050 separately extends provenance for genuine OSM/Wikidata native identifiers and raw-reference/field-path formats; do not relabel them as primary local registry identities. Also preserve real/synthetic dataset class through the trusted write boundary: an explicit synthetic record must not silently enter a real graph merely because an extra field was ignored. Existing model-level compatibility tests need not be weakened; enforce the selected graph/run scope before writes and retain separate manifests/volumes. This is required before source expansion acceptance, not a claim that the current prototype already provides it.
