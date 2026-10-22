# Assumption register

| ID | Assumption or discrepancy | Evidence and validation action |
|---|---|---|
| A01 | README describes fully operational features | Contradicted by explicit crawler/vector/backend stubs; require executed tests |
| A02 | Proposal's original 200 POIs are available | No graph snapshot accessed; locate and freeze before primary experiments |
| A03 | Supplied IDs are stable | Contradicted by current-date/category rewrite in POI validation; regression test and preserve existing IDs |
| A04 | Same degree bound is valid for latitude and longitude | False at nonzero latitude; replace with conservative geographic bound and verify against exhaustive distance |
| A05 | Prompt-only POI restrictions prevent unsupported details | Unverified; enforce output boundary and adversarially test |
| A06 | Five MCP tools imply complete memory integration | False implication; inspect actual calls and write/read user profiles under controlled tests |
| A07 | Available source pages imply permission to reuse | Not established; collect explicit licenses or authorization before acquisition |
| A08 | Existing tests can safely run against data | Integration script writes mock POIs; isolate tests and snapshot before live ingestion |
| A09 | Current model can reproduce historical numbers | Not established; freeze actual model and date with raw responses |
| A10 | Supplied revised proposal contains original sections | It references omitted original content; do not invent original references or exact RQ wording |
| A11 | Chapter allocation satisfies institutional range | Chapter 4 proposes 18 pages while its range says 20–25; adjust final allocation transparently within 60–70 total |
| A12 | Route supports car, foot and bike | Tool advertises all three, active GraphHopper config only car; reject unsupported modes or configure and verify them |
