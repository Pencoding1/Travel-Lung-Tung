# Travel AI continuation handoff

Checkpoint: 2026-10-16, Asia/Saigon. Workspace: E:\Project\TVLT_2026. This file is the entry point for the next session. All relative paths below are relative to this workspace.

## Instruction to the next session

Continue implementation, integration, research, experiments and thesis delivery until ALL remaining requirements in docs/project/MASTER_GOAL.md (SG01–SG19 and AC01–AC12) are satisfied with evidence. Read docs/project/EXECUTION_PROTOCOL.md and the complete BACKLOG.md; this summary does not replace their scope. Finish every unfinished task listed below and discover any additional work needed. Do not stop at plans, passing unit tests, or a working manuscript. Do not invent results or mark the overall goal complete while required evidence is missing. Progress autonomously on feasible work; disclose genuine external dependencies precisely.

After EVERY major task or critical phase, write a dated checkpoint in docs/project/checkpoints/, update this NEXT_SESSION_HANDOFF.md entry point and PROGRESS.md, and reconcile BACKLOG.md / ACCEPTANCE_TRACKER.md / EVIDENCE_REGISTER.md. Include actual changed files, independent checks and limitations, process/session ownership, failures, remaining tasks and exact next actions. Checkpoints are required after major implementation, integration, experiment, manuscript assembly/rendering and acceptance audits, and before interruption/session transfer. Record unverified work as such.

## Read first

1. This handoff, then MASTER_GOAL.md and EXECUTION_PROTOCOL.md.
2. BACKLOG.md, ACCEPTANCE_TRACKER.md, INDEPENDENT_QA.md, EVIDENCE_REGISTER.md, DECISION_LOG.md and latest PROGRESS.md entries. Earlier entries can be stale; current source/artifacts and latest verified evidence win.
3. docs/project/handoffs/OC-020/report.md and OC-021/report.md; their latest outputs are available and processes have exited.
4. docs/thesis/README.md, LEGACY_RECONSTRUCTION.md, MANUSCRIPT_ASSEMBLY_PLAN.md and docs/experiments/EXPERIMENT_PROTOCOL.md.

## User decisions already authorized

- Original thesis reference: C:\Users\duyan\Downloads\12.docx; extracted text in docs/project/THESIS_PROPOSAL_EXTRACT.txt.
- Original proposal with verbatim RQs, Chapter2 sections and18 references was lost. User asked to analyze legacy documents. Reconstruction is authorized; never claim verbatim recovery. New RQ1–4 and MT mapping are in LEGACY_RECONSTRUCTION.md.
- Hermes provider unavailable; user explicitly authorized Codex web research.
- User authorized OpenCode Go DeepSeek Flash instead of unavailable Gemini for experiments. Exact locally listed model: opencode-go/deepseek-v4.1-flash. Preserve same model/settings across comparison arms; disclose substitution. Production Gemini configuration was not changed.
- User explicitly authorized read-only access for OpenCode to installed documents SKILL.md and writing_quality.md under C:\Users\duyan\.codex\plugins\cache\openai-primary-runtime\documents\26.1013.11914\skills\documents\. Initial denied reads were retained; authorized retry succeeded in assembly.
- User requests handoffs at every big task/critical phase. Do not ask these questions again.

## Verified progress and evidence limits

- Audit, architecture inventory, thesis gap mapping, source-policy survey, acquisition design and12-paper literature matrix exist under docs/audit, docs/research and docs/architecture.
- Stable POI identity, spatial bounds, ingestion/SSE/retries, MCP grounding and routing contracts implemented and tested.
- Memory: authenticated subject/session namespaces, bounded history and locks, lease/CAS handling, optional SQLite persistence;190 independent combined AI tests at that milestone. Later AI integration suite255 passes includes overlap.
- Hybrid planner integrated into /generate_itinerary with directed route evidence, conservative unknowns, deterministic scheduling and independent validation. OC-016 R1 independently255 AI tests and126 planner tests passed. Required-category retention, day/meal constraints and cumulative budget regression fixed. These use fake providers, not real service/model results.
- Graph lifecycle and spatial mutation integration implemented. OC-017 R1 independent47 tests passed with1 optional dependency skip; direct guard probe rejects uniform5km under fixed3km policy and missing legacy radii before deletion. Explicit migration is separate. Live Cypher and concurrency remain unverified.
- Acquisition:32 actual source records (30 local OSM nodes and2 Wikidata exports), hashes/provenance in data/expansion_20261015. All32 quarantined,0 accepted. Second run32 duplicates. This is separate expansion evidence, not original thesis dataset or completed ingestion.
- Deployment: isolated docker-compose.integration.yaml, opt-in dependencies, loopback ports, JWT configuration, lockfile export/config tests. No successful runtime deployment yet.
- Offline evaluator OC-018:61 independent tests passed; corrected contradictions, planned repetitions, unknowns and paired preference denominator. Fresh synthetic smoke artifacts in docs/project/handoffs/OC-018/independent-r1-demo. Residual report labels remain misleading (see remaining tasks).
- Four draft Mermaid/SVG/PNG thesis figures exist, but visual review found layout/status issues. Refinement failed twice with OpenCode internal statement error. Not final figures.
- Vietnamese Chapters1–5, reconstructed foundations, formal definitions, bibliography and participant protocol/questionnaire drafts exist.
- NEW OC-020: editable docs/thesis/manuscript/Travel_AI_working_draft.docx exists (66,038 bytes), reproducible build_manuscript.py, input_hashes.json and assembly_report.md. Executor structural checks passed. Packaged rendering failed because soffice.exe unavailable; no PDF/page images/page count/visual QA. Figures are placeholders. DOCX is an unvalidated working artifact, not a final deliverable.
- NEW OC-021: benchmarks/live_model and tests/live_model implemented. Parent independently ran tests/live_model:46 passed in0.25s. Full code/semantic review and actual CLI execution remain pending. No live experiment performed by executor. Requested-versus-observed model provenance is explicit; missing observed ID may block exports.

Counts overlap and are engineering tests, not scientific sample sizes. Never sum them as independent observations.

## Current process state at checkpoint

- OC-020 R1 unified handle38699: polled terminal exit0. OpenCode session ses_ec095d5e7fferIUoV8O9e4yEVk. Owns manuscript and OC-020 handoff directory; now released.
- OC-021 resumed handle90500: polled terminal exit0. Session ses_ebd647971ffe0i7PeA0Pab5fGH. Owns benchmarks/live_model, tests/live_model, OC-021 handoff; now released.
- DS-001 diagnostic handle4064: explicitly interrupted after about2.5minutes without events; exit1. Earlier65969 and59913 handles disappeared and logs stayed empty. No successful DeepSeek call has been observed. Preserve logs under docs/project/handoffs/DS-001; diagnose before more retries.
- OC-017 completed; OC-018 R1 and OC-019 R1 ended with internal Failed to execute statement. Do not treat stale process IDs as live or launch duplicate writers.
- No worker was started by this handoff-writing task. Revalidate external state on resume; handles may not survive a new session.

## Remaining work in priority order

1. Review OC-021 collector beyond its46 tests. Inspect subprocess Windows quoting/timeouts, terminal event/model provenance, incomplete token fields, resume/failure denominator semantics, strict plan parsing and actual model order influence on hybrid scheduler. Verify same facts/settings across arms. Read report gaps. Run dry-run then a bounded single-scenario live pair only after acceptance. User already authorized provider use; no repeat approval needed for ordinary bounded calls. Empty logs are inconclusive, not evidence the provider is unavailable or successful. Diagnose CLI startup/provider/auth without printing secrets. Current CLI version1.18.35.
2. Resolve OC-018 residual reporting: h2.py verified_violation_rate_among_delivered actually divides by determined delivered plans (clean+violation); label/denominator must agree. cli.py H3 report still says resolved selected stops after all-selected denominator correction. Preserve unknownness and update tests/docs. Original bounded correction failed at final reporting; don't loop the same failing executor blindly. Record an explicit bounded recovery/alternative consistent with handoff skill.
3. Finish real acquisition eligibility and pipeline defects: mixed synthetic/real durable-state order/policy re-evaluation issues from OC-006; cross-source merging unsupported. Use separate fresh real-only state until fixed. Resolve entity-level administration/categories/evidence and quarantine reasons before acceptance; never force32 quarantined records into graph or label them original data.
4. Restore/verify live local stack when Docker is available. Latest docker info failed missing dockerDesktopLinuxEngine pipe. No repeated blind resets. Use isolated integration Compose and volumes; original data preserved. Build/start, readiness, import, actual MCP/ReAct/routes, moved-POI edge replacement/rollback, live point.distance vs reference, end-to-end adversarial cases. Configuration tests do not prove deployment. Assess all remaining service/UI/backend functionality against master goal rather than assuming stub components are done.
5. Obtain/verify original thesis POI/graph snapshot and dataset counts; distinguish missing data from legacy claims. Expansion cannot silently substitute for original~200POI District1/3 dataset. Freeze manifests before experiments.
6. Run all four required experiments with raw evidence: spatial reference comparisons/timing; tools/ReAct and H1 trace-visible vs identical hidden responses with10–15 actual consenting participants; H2≥20 frozen same-model/candidate/route paired scenarios; H3 five profiles with memory-disabled/short-term/two-tier conditions and actual complete provider usage. Synthetic live runs are engineering evidence only. Retain errors/refusals/unknowns/planned denominators and confidence intervals. No humans recruited or responses collected yet. Do not contact others without explicit authorization; use prepared materials and request necessary participation arrangements when needed.
7. Complete three adversarial families through actual configured model/MCP/deployed HTTP, not only mocks.
8. Finish four thesis figures. Existing01 system is too large with whitespace/stale memory labels;02 modules excessively wide;03 dataflow too tall and no_plan wording overstates infeasibility;04 experiment caption must scope McNemar toH2 and sign test toH1. Parent must inspect every final image. Avoid OpenCode PNG reads that embed huge base64 and caused internal errors.
9. Reconcile manuscript prose with latest evidence: Ch3 planner/memory diagram and Ch4 test table/status are stale. Update final editorial prose first, then rebuild DOCX with approved figures. Read actual builder to ensure source updates are incorporated (it may embed text); audit all claims/references and source hashes. Preserve reconstructed provenance and distinguish working results from historical claims.
10. Render and visually inspect every manuscript page. Packaged render_docx.py failed missing LibreOffice. Word.Application COM registration exists; it is only a possible fallback, not tested rendering. Diagnose/choose permitted fallback without claiming success or broad installs. Use bundled document runtime/skill, inspect logs, actual PDF/PNGs and page count. Final60–70-page requirement remains unmet; do not pad or invent results.
11. Complete SG01–19/AC01–12 requirement-by-requirement audit, update final handoff/runbooks/evidence/backlog, and deliver only after actual evidence supports completion. Unavoidable human/external gates must remain explicit.

## Execution conventions

Apply C:\Users\duyan\.codex\skills\agent-handoff\SKILL.md and opencode-executor\SKILL.md. Codex owns reasoning, QA and final prose; substantive coding/artifact execution goes to external OpenCode. User authorized Codex research after Hermes failure. No native subagents/new chats as silent substitutes. One writer per path, explicit session reuse, never --continue/latest. Follow bounded-recovery rules; do not bypass denied access. Host escalation may be needed for CLI logging. Task setup, direct verification and final editorial documentation are permitted Codex work.

CLI message precedes --file (array argument). Capture JSON events to files. NEVER raw-print entire OpenCode logs: they can contain huge base64 images. Parse only concise type/text/error/status metadata. Exit0 alone is insufficient; inspect artifacts and independent checks. Do not print credentials, full composed configuration, auth files or secret-bearing diffs.

Preserve user deletions Architecture_Note.md and TODO.md; dirty/untracked worktree is intentional. No git reset/clean/revert or unrequested commits. Original .venv is broken and preserved. Use .venv-validation, .venv-ai-validation, .venv-mcp-validation, .venv-acquisition-validation as appropriate. AI and planner tests have duplicate module basenames: run separately unless import mode is deliberately handled. Sandbox async tests may need normal approved execution; never count a hang as a pass.

Example independent checks from repository root:

```powershell
.\.venv-validation\Scripts\python.exe -m pytest tests/live_model -q --basetemp .qa-tmp-live-review -p no:cacheprovider
.\.venv-validation\Scripts\python.exe -m pytest tests/evaluation -q --basetemp .qa-tmp-eval-review -p no:cacheprovider
.\.venv-mcp-validation\Scripts\python.exe -m pytest tests/graph_lifecycle -q --basetemp .qa-tmp-graph-review -p no:cacheprovider
.\.venv-validation\Scripts\python.exe benchmarks/live_model/runner.py --out docs/project/handoffs/OC-021/next-dry-run --scenario-ids S01 --repetitions 1
```

Use new output directories to preserve prior evidence. Inspect tests/files before broad reruns.

Documents bundled Python: C:\Users\duyan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe. Bundled Node: corresponding dependencies\node\bin\node.exe. Documents skill root has render_docx.py; earlier scripts/render_docx.py path was stale. Initial OC-020 artifact marker already ran exactly once; don't claim it needs repeating for an unchanged read-only inspection. Apply skill guidance to new edits.

## Scientific integrity

Historical numbers (120ms,200POIs/4districts/45streets/3categories/180products,300/40000distances99.25%,35%vs100%feasibility,budget<8%vs30–70%,route32.4%,tokens58%,preferences28→72%) are unverified legacy claims. Do not use them as newly measured findings. Null results are valid. Missing routes/hours/prices remain unknown; heuristic no-plan does not prove infeasibility. Never manufacture participants, data freshness, model usage, citations, accepted records, successful deployments or rendered pages.

## Latest override: collector review checkpoint 2026-10-16

Read checkpoints/2026-10-16-collector-review.md before continuing. OC021 failed independent usage/completion probes despite46 passing tests. R1 now running handle26701/session ses_ebd647971ffe0i7PeA0Pab5fGH; its source paths are owned until terminal. Missing token components become falsezeros; length finish inferredcomplete. Windows wrapper timeout/quoting also needs verification. Do not accept or launch live collector until correction is independently reviewed. This supersedes earlier statement that no worker is active.

## Latest editorial checkpoint 2026-10-16

See checkpoints/2026-10-16-thesis-reconciliation.md. Chapter3/4 source prose updated to current verified evidence. IMPORTANT: manuscript builder embeds prose and will not automatically incorporate these Markdown changes; existing DOCX is stale relative to source. Reconcile builder before rebuilding; then render/inspect. OC021-R1 handle26701 confirmed live during checkpoint.

## Latest active ownership 2026-10-16

OC022 manuscript fidelity/rendering process45278/session ses_ebd4c19a2ffeaDi1W6zSCvmGtD now owns manuscript directory. Read checkpoints/2026-10-16-manuscript-fidelity-dispatch.md and its brief. OC021-R1 process26701 remains active separately. Verify terminal state before touching either scope; no duplicate workers. Full requirements and prior user authorizations above remain in force.

## Acquisition review reconciliation 2026-10-16

Read checkpoints/2026-10-16-acquisition-reconciliation.md. REVIEW.md corrected to actual30OSM+2Wikidata retained candidates,0accepted; all32 missing reviewed entity/admin/category mapping. No acceptance or graph import occurred. OC021-R1 and OC022 remain active as last polled.

## Latest collector verification 2026-10-16

OC021-R1 is terminal exit0. Read checkpoints/2026-10-16-collector-r1-verification.md:64pass/1sandbox cleanup failure;8capture tests pass under approved normal host permissions; direct token/completion probes fixed. No universal timeout guarantee or live evidence claimed. Further semantic review required before live acceptance. OC02245278 remains last-confirmed live.

## Collector semantic gate 2026-10-16

Read checkpoints/2026-10-16-collector-semantic-review.md. Separate hybrid scheduler is not representative of production planner; resume appears to overwrite prior structured records. Do not use resume on real evidence. Fresh diagnosticS01 pair process29276 running (2calls30s each), transport only. OC02245278 still active. These limits supersede any broad collector acceptance.

S01 diagnostic29276 finished: both calls timed out after~30.5s, empty event/stderr files,0exportedrecords/2gaps. CLI orchestrationexit0 is not model success. Evidence under OC021/live-diagnostic-s01; further provider diagnosis required before additional runs.

## Confirmed resume failure 2026-10-16

Read checkpoints/2026-10-16-resume-evidence-loss.md and new T036. Fake-only no-op resume erased prior calls.jsonl to0bytes. Production scheduler alignment and lossless evidence continuation are required before scientific collector acceptance. No real diagnostic evidence was modified.

## Latest rendering checkpoint 2026-10-16

OC022 exited0; real28page render exists. Parent reviewed01/02/14/28 only; blue title rule, stale unrendered note and stale evidence appendix require correction. See checkpoints/2026-10-16-first-render-review.md. Inspect remaining24pages before consolidated repair. OC023 process4957 owns collector/tests for evidence preservation and production scheduler integration; no livecalls.

## Latest full visual review 2026-10-16

All28OC022pages inspected; consolidated corrections dispatched as OC022R1process13739/session ses_ebd4c19a2ffeaDi1W6zSCvmGtD. See checkpoints/2026-10-16-full-render-review.md and repairbrief. Manuscript paths owned until terminal. OC0234957 handlemissing/reportexists; independent QA not yet performed. Chapter2/5 editorial sourcesupdated; source-driven build must propagate. No fullgoalcompletionclaim.

## Latest run-plan gate 2026-10-16

OC02383tests and no-op preservation pass independently, but changedscenarioselectionaccepted; R1process35345/session ses_ebd4514bcffeiLCKAmmlXtKolO nowownscollector/tests. See checkpoints/2026-10-16-run-plan-compatibility.md. OC022R1process13739stilllive,ownsmanuscript. No fullscientificacceptance orliveproviderresult.

## Latest active work and acceptance 2026-10-16

Central register nowE031–E037; trackercurrent supplement. OC024process99050 ownsevaluatorreporting scope; OC023R1process35345 ownscollector/tests; OC022R1process13739 ownsmanuscript. See checkpoints/2026-10-16-acceptance-report-integrity.md andtaskbriefs. Pollspecific handles, don'tduplicatewriters. AllthreeawaitindependentQA; fullgoalstillincomplete.

## Collector local gate accepted 2026-10-16

OC023R1terminal;96independenttests anddirectdriftprobe pass. See checkpoints/2026-10-16-collector-local-acceptance.md,E038. Collectorpathsreleased. Localcontractacceptedonly;DeepSeekdiagnosticsstill2timeouts/0records. OC022R1process13739 andOC02499050remainlastconfirmedlive;confirmterminalbeforeQA. Fullgoalnotcomplete.

OC022R1nowterminal; corrected27pagerender exists. Parentinspected01/02/19/27 only,remaining23needvisualQA. See collector-local-acceptance checkpointterminal supplement. OC02499050stilllive. Manuscriptscopereleased; do notclaimcompletevisualgate.

## Corrected manuscript full review 2026-10-16

All27OC022R1pagesparent-reviewed;readable/noobservedclipping,title/table/questionnairefixesverified. Workingdraftonly;nativeequations,figures,currentexperimentprose andfullscientificresultsstillmissing. See checkpoints/2026-10-16-corrected-manuscript-review.md (artifacthash). OC02499050stilllive;collectorlocalgate96passaccepted,provider2timeouts/0records.

## Current figures recovery 2026-10-16

OC025process27027ownsdocs/thesis/figures/ andownhandoff, freshtext-onlyboundedalternativeafterblockedOC019session. See checkpoints/2026-10-16-figure-recovery.md. NoPNGreadbyexecutor;parentQArequiredbeforeinsertion. OC02499050stilllastconfirmedlive. Manuscript27pageworkingdraftfullyvisuallyreviewed,fullscientificscopeunfinished.

## Latest evaluator acceptance 2026-10-16

OC024terminalexit0;67independenttests/freshdemoacceptedoffline/reportingscope. E039/checkpoints/2026-10-16-evaluator-reporting-acceptance.md. Evaluatorpathsreleased. Primarydatasetpathquestionpending (repohasnoprimaryexport). OC02527027stilllastconfirmedlive,ownsfigures. NextfigureQA,sourceexperimentstatusrefresh,remaininglive/data/humanrequirements.

## Latest acquisition scope and thesis prose 2026-10-16

OC026process14865ownsacquisitionmodule/tests/ADR013/ownhandoff;OC02527027ownsfigures. Chapter4sourceupdated67evaluator/96collector and2DeepSeektimeouts;existingDOCXpredatesupdate. See checkpoints/2026-10-16-acquisition-isolation-dispatch.md. Rebuild/rerenderafterremainingfigure/equationtasks. Noactualdataedited;datasetpathquestionpending.

## Latest figure acceptance gate 2026-10-16

OC025originalterminalbutall4PNGsparent-reviewed/rejectedforsmalltext/relationshiperrors. R1process57595ownsfigures. See checkpoints/2026-10-16-figure-independent-correction.md. OC02614865lastconfirmedlive,ownsacquisition. Do notinsertfiguresorclaimfinalthesis;remainingfullscopeabove.

## Latest core backend scope 2026-10-16

MASTER_GOAL3.7missingbackendworkflowT037nowOC027process35165ownsbackend/tests/backend_workflows/ADR014/ownhandoff. See checkpoints/2026-10-16-backend-core-workflow.md. OC02614865ownsacquisition;OC025R157595ownsfigures;bothlastconfirmedlive. Nooverlap;verifyterminal/QA beforeacceptance. Fullgoalactive/incomplete.

## Current acquisition consistency gate 2026-10-16

OC026originalterminal121independenttestspassbutcontradictoryv3stateaccepted;R1process35669nowownsacquisition/tests/ADR013. See checkpoints/2026-10-16-acquisition-state-consistency.md. OC025R157595ownsfigures;OC02735165ownsbackend;bothlastconfirmedlive. Actualdatasetsunchanged. Fullremaininggoalpreserved.

## Current architecture evidence 2026-10-16

ARCHITECTURE_AS_IS.mdnowcurrentrepairedscope,oldinventorytableexplicitbaseline. OpenCodeGocredentialregistered(read-onlyauthlist),butprovideroperationunverified;2timeoutsnotmissingentryproof. See checkpoints/2026-10-16-current-architecture.md. OC026R135669/OC025R157595/OC02735165alllastconfirmedlive;don'tduplicatewriters. Fullremaininggoalaboveunchanged.
