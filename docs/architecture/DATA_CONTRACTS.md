# Acquisition data contracts

Contract version 1. Requirements precede implementation; test results must be linked separately.

| Contract | Required fields and invariants |
|---|---|
| RawSourceRecord | source_type, source_id, source_url, retrieved_at (UTC-aware), license, raw_content_reference, sha256, collection_status, extraction_metadata |
| POICandidate | source identity, name, aliases, address hints, proposed category, original field evidence, uncertainty/reason codes; optional finite coordinates; source geometry kind |
| ResolvedPOI | stable canonical ID, canonical name, finite coordinates with evidence, reviewed administrative location, closed category IDs, fact-level provenance; resolution status exact/probable/ambiguous/unresolved; point venue versus area |
| IngestionDecision | candidate ID, accepted/rejected/duplicate/requires_review, reason codes, resolved ID if any, timestamp and evidence references |

Never map probable/ambiguous/unresolved to trusted POI automatically. Existing explicit POI IDs remain immutable. Source-derived IDs use a namespaced stable encoding/hash of source type and source entity ID; never category, mutable address or retrieval date. Missing source identity is rejected. Repeating the same source record produces the same ID and a duplicate/unchanged decision rather than a new entity. Similar nearby businesses remain separate until reviewed.

Unsupported attributes remain null/missing. Preserve source transcript/time anchors if authorized transcript imports are added. Do not infer opening hours, prices or corrected names. Every imported fact points to a raw record and extraction path; conflicting updates require review. Domain-schema acceptance is necessary but not sufficient for evidence acceptance.
