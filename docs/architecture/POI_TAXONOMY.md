# POI taxonomy compatibility

The proposed three-level taxonomy in `docs/poi-crawl/phan-loai-dia-diem.json` is a proposal, not proof that matching graph categories exist. Existing graph `Category` nodes have id/name/context; `Tag` represents additional traits. Agent search must use category IDs returned by the graph catalog, not fabricate IDs from labels.

Keep primary type in Category, secondary experiential traits in Tag, and geometry kind in explicit acquisition metadata. An area/polygon cannot silently become an individual venue. A mapping manifest must enumerate accepted category IDs and explicit source-tag/entity mappings. Unknown mappings enter review.

Stable POI IDs are independent of taxonomy after ADR 001. Changing a category must update relationships without renaming the POI. Historical duplicates created by the old prefix rule require snapshot, reference inventory and reviewed merge mapping; no bulk migration has been executed. Test query visibility for both old IDs and newly accepted records before claiming compatibility.

Outstanding validation: inventory live Category and Tag nodes, compare proposed taxonomy, initialize approved missing categories transactionally, and execute MCP search tests. Docker availability and graph snapshot are prerequisites for live verification.
