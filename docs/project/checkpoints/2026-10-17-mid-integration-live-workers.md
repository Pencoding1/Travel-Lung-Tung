# Mid-integration checkpoint — live writers and pending independent gates

Date: 2026-10-17, approximately20:18 Asia/Saigon. Full goal ACTIVE/INCOMPLETE. Current goal turn is PROGRESS: OC037 independently accepted; new production/revision implementation changes and cross-pipeline evidence; bounded runtime alternative inventory; H1 availability explicitly resolved as unavailable.

## Accepted this phase

OC037 terminal ses_ebba84edaffeBfAPTNF7Ch41HW: bulk Category/Tag identity now explicit ID, not display name. Parent7new tests0.65s,4category tests0.88s,21ingestion/domain0.42s pass in appropriate existing environments; query/spy evidence, not live Cypher. E059 and bulk-identity-acceptance checkpoint saved. Prior raw6368/candidate6367 snapshot and33-page working manuscript layout acceptance retained; all full scientific/deployment requirements remain open.

## Confirmed live workers — do not restart or overlap

- **OC038 process14937/session ses_eb6103739ffeZrz54I1vR7BAJ8** remains live on latest handle poll. Owns POI graph domain/projections/repository/necessary services/MCP, new tests/primary_provenance, its contract and handoff only. Typed source metadata/model/query changes are present; it has begun writing its new test suite. No report/independent acceptance yet. Budget is approximate; scope must stay bounded. No crawler/registry/data/publication writes allowed.
- **OC039 process74098/session ses_eb60f7e14ffe5hp4XbT03nAmFr** remains live on latest handle poll even though report.md exists. It continued editing/review after writing that report. Owns registry/prepare preflight/primary tests/revision contract sections and its handoff only; actual frozen data untouched. Report states39primary tests pass; acquisition139pass/1fail because OC038's new POI validator rejects legacy source_id. Do NOT treat report presence or observation timeout as terminal. Await actual handle completion, inspect final code/report and rerun independent checks.

## Exact next QA

1. Revalidate these same handles. After OC039 terminal, run .venv-validation pytest tests/primary_dataset with an isolated basetemp/no cache. Then execute docs/project/handoffs/OC-039/parent_revision_probe.py from repository root. It uses only own temporary copies and checks explicit A->B->A->B chronology, preserved IDs, three immutable backups, per-step no-op, null-hash/bool-version/scope rejection, invalid direct-save payload and frozen-byte preservation. It requires a fresh own fixture directory. Do not mislabel executor-generated outputs as independent if it happened to run this parent script first.
2. After OC038 terminal, inspect its changes/tests/report and run parent_metadata_probe.py in .venv-validation. It compares genuine frozen lineage with a self-hashed envelope missing raw geometry/properties; only genuine should pass. Review complete feature bindings and compact AI-facing evidence vs full raw storage/CRUD lineage.
3. Known cross-pipeline regression is in OC038/parent-cross-pipeline-findings.md: tests/acquisition/test_pipeline_cli.py::test_poi_round_trip_preserves_categories_if_import_safe fails because broad metadata-like regex rejects existing source_id. Preserve the legitimate legacy acquisition boundary, do not change its passing test or discard real native identity to get green. Keep new typed metadata strict and do not promote ignored legacy fields to verified provenance. After terminal review, author one bounded corrective brief collecting actual failures rather than repeated piecemeal repairs.
4. Use existing environments: .venv-validation supports tenacity but lacks neo4j; .venv-mcp-validation supports neo4j but lacks tenacity. Split appropriate suites; no installs/uv run. Restricted Windows async tests may hang; previous normal-host ingestion tests pass after interrupting restricted run. Record failures and distinguish them from contract failures.
5. Checkpoint each acceptance/rejection and refresh trackers. Do not accept fake/spy tests as live graph execution, node counts or idempotency proof.

## External state and user decisions

User explicitly confirms **no H1 participants available yet**. Keep10–15real consenting participant requirement open; do not ask the same availability question again absent changed state, fabricate results or substitute bots.

Last Docker probe still lacks Linux engine pipe. Bounded alternative inventory in runtime-check-20261017.json: WSL Ubuntu/docker-desktop exist; Ubuntu PATH resolves none of memgraph/docker/java/podman, Windows PATH lacks java/podman and repository has no GraphHopperjar. Restricted WSL inventory E_ACCESSDENIED; normal-host readonly inventory succeeded. No install/deployment/config modification and no exhaustive absence claim.

Authorized experimental model is **aibox/ds/deepseek-flash**, displayDeepSeekV4Flash; upstream4.1 not verified. Actual S01 pair is synthetic engineering evidence only. Production Gemini default remains. T051/provider-adapter-next-notes.md records a feasible explicit per-run CLI model adapter for actual runtime verification; do not keep asking for a Gemini key as the only route.

## Still mandatory

T048 fresh versioned graph-ready candidate adapter, preserving raw/prepared-v1/IDs; T049 explicit source-snapshot area retrieval/planning, so source-only records are usable without claiming current jurisdiction; T050 source-native provenance/resolution for separate32OSM/Wikidata expansion candidates; T051 actual AI provider adapter/live intent/chat checks. Then isolated accepted primary graph import/snapshot/Cypher/spatial/routes/deployment; frozen20primaryH2pairs;5profiles×3memoryconditions/full usage;3liveadversarial families; realH1study when available; final evidence-backed60–70-page thesis and every SG/AC completion audit. Do not redefine completion around local tests or the33-page working draft. Finish ALL remaining tasks and checkpoint every major phase.
