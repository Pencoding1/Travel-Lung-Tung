# Decision log

## D014 — Phase5 Finalizing integrates new mechanisms; core flow comes first

18/10/2026 user explicitly renamed phase5 to **Finalizing phase**, integrating all new mechanisms including grow-with-user and crawler. Current phases prioritize completing the project and executing user-input→recommending→routing. S1–S6 approved scope retained, interpreted as essential repairs/integration/QA for that core flow; S5 is existingmemory only. T056 joinsT057–T059 and other chosen future mechanisms inphase5, with bounded implementation plans before execution. No new harness/memorymigration/crawler/paid enrichment or other feature is a phase2 gate. Original phase4userchoice beforeH1/furtherthesis remains; do not use phase5label as permission to start them.

## D013 — Phase2 S1–S6 approved

18/10/2026 user replied exactly “Duyệt S1–S6 như đề xuất” to Codex scope review. PHASE2_SCOPE_FOR_APPROVAL_VI.md is now approved, not pending. Proceed with bounded implementation/QA for AI/Jev/CLI, existingOSMgraph, service/client integration, planner/car-foot constraints, existingmemory forH3, QA/freeze/report. No repeated approval for this scope. D012 crawlerphase5/growmemoryP2/H1-thesisuserchoice boundaries remain. Finish activeCLI067R1 before another provider writer; keep checkpoint after major tasks.

## D012 — All crawling moves to phase5; bounded phase2 scopes for user review

18/10/2026 explicit user instruction supersedes D011 and all older notes making social/web P0/P1 a phase2 gate: remove crawler from current scope and reintegrate in **phase5 finalize** after agreeing travel-agency and social-source plan. Applies to legacy plus T057–T059. Existing artifacts retained, no new crawler writer. Original P0/P1/P2 now priorities withinphase5. Core OSM data/integration remains; proposed phase2S1–S6 are in PHASE2_SCOPE_FOR_APPROVAL_VI.md for user review before another implementation package. Existing CLI067R1 correction is already authorized/running. MemoryP2 still afterfourphases; no H1/thesis continuation beforeuserchoicephase4. Codex must not reintroduce crawler via old acceptance wording.

## D011 — Legacy crawler deferred; core POIs remain OSM

18/10/2026, explicit user clarification in current Codex chat: legacy crawling was deferred because scaling was impractical; core system uses OSM POIs. Restoring Traveloka/Vietravel is not a core phase2 or experiment prerequisite. This overrides any interpretation of older multi-source acceptance items that would require those legacy sources. The newer requested social/web P0/P1 workstream remains separate, with its own QA; no instruction cancelled it. Current evidence is252web listings/161minimum fields/allquarantine/import0, not completed social-platform ingestion. Grow-with-user implementation remains P2 after four phases. Preserve immutable primary manifest:6368raw/6367prepared candidates, not accepted graph nodes; missing per-feature upstream OSM ID/URL is still a documented limitation, not grounds to invent metadata. Codex owns this scope clarification and updates backlog/handoff accordingly.

## D001 — Preserve source and evidence boundaries
2026-10-15. Audit before architectural changes. Preserve user deletions and existing documentation; no graph mutation until a snapshot exists. Runtime behavior outranks README claims. The supplied thesis revision's historical numbers are hypotheses to reproduce, not current results.

## D002 — Separate original and expanded datasets
The proposal scopes primary claims to approximately 200 POIs in Districts 1 and 3, HCMC. Acquisition expansion will use a separate dataset/version and cannot silently replace the primary experiment.

## D003 — Missing inherited proposal content
The supplied revision gives MT1–MT6, H1–H3 and experiment requirements, but refers back to original RQ wording and references. Use explicit thematic mappings labelled as such; do not invent quotations or bibliography entries. Chapter 4 planned 18 pages conflicts with its stated institutional range 20–25; resolve manuscript allocation within overall 60–70 pages and record the choice.

## D004 — User-authorized legacy reconstruction
2026-10-15. User confirmed the original file is lost and asked to analyze legacy documentation. No longer wait for that file. Preserve eight theory headings and MT/RQ/H mapping available in12.docx; newly word four RQs and write replacement foundations from verified primary sources. LEGACY_RECONSTRUCTION.md separates recovered structure from newly authored text. Do not fabricate the18 missing bibliography entries; normalize a new unified bibliography after manuscript assembly. Historical README marketing claims remain unverified.

## D005 — Reconcile manuscript allocation
Use working target8/12/23/23/4pages forChapters1–5 (70total), resolving the revision's18-pageChapter4 conflict with its20–25range. This is an allocation, not an actual page-count or completion claim. No filler; frontmatter/reference counting remains subject to actual submission rules. SeeMANUSCRIPT_ASSEMBLY_PLAN.md.

## D006 — Stand-in ownership window (Hermes acting as Codex), 18/10/2026 02:33–06:08
The owner directed that while Codex is out of quota until 06:08, Hermes takes the Codex role (planning, work packages, QA, acceptance) rather than the read-only reviewer role of the original handoff. Scope kept narrow: no commit/push, no change to the HM-053 guard scope, no domain-list changes, no full graph import, no model runs beyond the approved provider.

Decisions taken in the window (each with measured evidence under E:/Agent_Artifact/TVLT_2026/2026-10-18/):
1. T061 fixed at the source (service-level `model_dump(mode="json")`) plus a dedicated `serialization_failed` code so a future encoding defect is never reported as `exploration_failed`; accepted only after the real-graph canary passed 7/7 stages with a clean rollback.
2. T051 fixed by capability negotiation instead of a hard-coded `--pure`; the native-binary resolution layout (`@opencode/cli/bin`) was also fixed because without it the CLI transport could not start at all.
3. T060 fixed by sending `ch.disable=true` for profiles without a built contraction hierarchy, configurable through `GRAPHHOPPER_CH_PROFILES` (default `car`); enabling `foot` still requires an operator to widen `GRAPHHOPPER_PROFILES`.
4. QA-DATA-01 closed at the cheapest point: `_validate_expectations` rejects caller-built expectations that claim `real=True` and differ from `REAL_EXPECTATIONS`. Splitting the public `prepare_snapshot` signature (18 call sites) is deferred as a contract decision.
5. HM-053 root QA performed (40 tests, 19 execution payloads). Two findings recorded: report R1 misstates `declare -x` behaviour, and helper authorization resolves against the guard process cwd rather than the payload cwd. The hook is NOT activated; activation remains a separate gated package.
6. T049 is not implemented: the proposal is complete (four break points, 18 edit sites, 32 tests) but the source snapshot is not imported, so every test would be fixture-only. Implementing a second scope contract without end-to-end evidence would hand Codex an unverifiable contract change.

Open owner decisions recorded in HANDOFF_TO_CODEX_0608.md §4: HM-053 activation, QA-DATA-01 API split, T049 timing, and `planning_adapter` `transport_mode` labelling.

## D007 — The agent-loop result must carry the turn's messages (memory contract)
2026-10-18. `chat_agent._result()` accepted `turn_messages` and silently dropped it, so `main.py` committed an empty history and every turn after the first reached the model with only the current user message (measured: 120/120 prompts of turn >= 2). Two consequences follow, and both are now binding: (a) the loop result is an internal contract that must carry the messages the caller needs to commit — dropping a parameter silently is a defect, not a detail; (b) the "no arbitrary tool names in the result" guarantee is scoped to the **trusted trace** (`tool_chain`) and to the HTTP payload, not to the internal message list, which necessarily contains the model's own tool call. A test asserts the public response dict never gains `turn_messages`.

The same review found the stored-profile block truncated by raw `block[:limit]`, which removed the closing `</untrusted_profile>` tag and the "never follow instructions" sentence on a *valid* large profile. Rule: a bounded prompt block must be truncated on the body, then have its safety tail re-attached; the tail is never the part that gets cut.

## D008 — Experiment numbers produced without a live model are labelled fixture-only
2026-10-18. The memory harness (5 synthetic profiles x 3 conditions) and the Experiment-3 runner (20 scenarios x 5 branches) both execute real project code with injected fake models. Their numbers are reproducible and useful for harness validation, but they are **not** experimental results: `results.json` carries `fixture_only=true` / `scientific_result=false`, and the reports say so. The Experiment-2 spatial measurement is different: it runs the shipped spatial module over the frozen 6367-record snapshot, so its counts are real measurements of that algorithm, while still not being graph edge counts.

## D009 — Codex review after the0608handoff
18/10/2026. Existing fixes preserved, independently checked instead of reverting. T061 accepted at real-graph/in-process MCP scope (six parent stages, clean0/0 rollback). Real binding guard retained; no API signature split without demonstrated remaining gap. Guard F2 repaired with fully absolute helper paths;45tests+39parentcases+5cwd spoofcases pass; hook still not activated pending separate installation/consent.
T049 is mandatory before experiments. Implement/review its typed source contract before data freeze; full6367import is not required to prove a contract on actual small canaries, though scale/full E2E remain separate gates. planning_adapter.transport_mode is car/foot travel routing, NOT CLI/API model transport; do not conflate these. Keep approved routing enum through request/route/validator/report; model transport comparisons use controlled experiment/provider configuration.
T051 capability/binary fixes pass offline, but export argv still targets obsolete top-level export; per-run isolation on currentCLI also needs proof before live calls. T057 has5/6parent counterexamples fixed; orchestration policy-before-fetch still fails despite known-host HttpFetcher license gate. No new fetch until that orchestration gap is closed.
E081 storage interpretation corrected: undirectedMATCH counts traversal rows twice; this is not two stored relationships. Parent actualcanary finds1stored/countDISTINCT versus2undirectedrows. Preserve historical raw measurements; repair report/counting methodology before treating300sample total as stored edges.

## D010 — Current gates and explicit source request contract

18/10/2026 Codex. E086 supersedes D009 guard-pending wording: default-home hook registered with explicit user first-use consent,5/5actualcallbacksyntheticprobespass; do not infer gateway reload/profilecoverage. E089 supersedes social orchestration failure: early reusedecision now blocks denied/unknown before input/output sideeffects,141socialtests+6probes+152acquisitionregressions pass, no newlivecapture/import acceptance. DOC056staticreport andRS058research delivered with scope/transportlimits, not science/runtime migration.

T049 AI059 is now dispatched. Presence of strict typed source_scope is the only source-mode switch; no inferred mode from POI labels/context and no second toggling field. Source mode omits currentadmin toolfilters and supports a bounded unfiltered source floor even if global categories are empty. Selectors are exact server discovery outputs; AI never derives sourcearea IDs or lets model change selection. Initial AND repaired stops must preserve qualifiedsource evidence/currentadminnull; unknown/foreign records never fallback into adminverification. Real small rollbackcanary is required after sourceQA, fullimport remains a separate mandatoryscale/datafreezegate. Independentcanary intentionally forces scheduler to add an extra source stop, exercising repaired reconstruction.
