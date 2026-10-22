# Production integration audit and next implementation

Date: 2026-10-16. Full goal ACTIVE/INCOMPLETE; phase PROGRESS.

OC036 terminal exit 0, session ses_ebbac31b5ffeopXXQnzk9Th7F3. Parent inspected actual batch_create source and confirms category/tag MERGE keys use name whereas single paths use explicit id. Existing bulk path creates categories, so a new fine-taxonomy mapping is unnecessary for preserving the 14 observed source categories; correct the keying inconsistency first. Current POI model lacks provenance/qualified-admin fields, and prepared lineage remains sidecar-only. Null optional addresses can reach hierarchy writes. These code findings require implementation, not silent ingestion.

Audit proposals are not all accepted: fake transactions/query assertions cannot prove live Cypher semantics or graph idempotency; existing optional live tests must not be described as absent. The read-only report is an implementation inventory, not runtime evidence or an approved full design. Codex chooses explicit-ID keying, no fine-category invention, no persisted-ID migration, and a separate qualified provenance/admin stage before live import.

A fresh bounded Docker check still fails: docker info --format '{{.ServerVersion}}' exit1; dockerDesktopLinuxEngine pipe missing. No daemon/version or image build/live graph acceptance claim. Do not repeatedly restart/check without changed state.

Next bounded implementation fixes bulk category/tag keying using existing trusted path and tests, disjoint from frozen primary data. Null-address/provenance/admin scope require a following coherent write/read integration stage. General primary-registry revisions remain unaccepted per prior checkpoint; exact immutable snapshot candidates are usable. Continue all remaining full-goal tasks and checkpoint each major phase.
