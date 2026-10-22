# Acceptance tracker

**Latest scope override18/10/2026:** all legacy/social/web/travelagencycrawler work is **DEFERRED_TO_PHASE5**, not a phase2/experiment gate. CoreOSM only. D012 and PHASE2_SCOPE_FOR_APPROVAL_VI.md supersede older acquisition completion wording as current phase2 requirements. Six proposed core scopes await user review before new implementation. Historical findings remain evidence, not a reason to restore deferred scope.

Updated 2026-10-18 (through E103/RT064 bounded integration; phase2 current focus; dated supplements below remain historical). Completion gate NOT PASSED. Full wording: MASTER_GOAL.md. Source/fake integration evidence never implies deployed operation.

Current E106/E107: CLI067R1 code/nativefakeprovider transport accepted bounded (root189tests/20faultcases/54native+9argvchecks); realAIbox service integration stillpending. S1–S6 approved, coreuserinput→recommending→routing prioritized; phase5Finalizing includes new mechanisms T056–T059/T050newsourceacceptance. Coreprimarysnapshot import/lineage remainsS2. BothCLI067handles terminal; noactiveproviderwriter.

| Criterion | Status | Evidence and remaining action |
|---|---|---|
| AC01 Architecture audit | VERIFIED source audit | Five audit artifacts; baseline/current changes distinguished |
| AC02 Two acquisition families | VERIFIED bounded local-source path | Actual30OSM+2Wikidata processed with provenance; offlineOSM timestamp/download caveats; not coverage or freshness validation |
| AC03 POI quality/quarantine | PARTIAL | Supplied6368features ->6367frozenpreparedcandidates, allsourceindices/IDs locallychecked; registrychronologyaccepted. Separate32OSM/WDcandidates remainquarantined. Venuequality/sourcefacts/currentadmin/native-sourcegraphacceptance pending |
| AC04 Graph ingestion/spatial consistency | PARTIAL | Real2POI rollback canaries verify shipped spatial correction, edge properties/radius, provenance and source MCP. Earlier degrees/radians/edge-property failures resolved at bounded gate. Full6367import/concurrency/durability/performance remain; stored-edge counting correction E085 must hold in future density experiments |
| AC05 Agent/itinerary end-to-end | PARTIAL | AI059 request→realgraph/inprocessMCP→AI/scheduler/validator→realrouting→repairedsourceplan sixstagecanary passes with controlled model, frozenhashunchanged/rollback0/0. T051 actualexport/isolation/liveprovider, fullsnapshot/client/HTTPdeployment remain unverified |
| AC06 Twelve publications | VERIFIED bounded review |12primary-source matrix/synthesis; reconstructedChapter2foundations inworkingdraft, finalreference/claimaudit remains |
| AC07 Four experiments/real study | PARTIAL preparation | Protocolv2 reflects suppliedsnapshot; S01livepair is syntheticengineering only. Primary20H2cases/5x3memoryconditions/manifests/runs notcomplete;0humanresponses, participantsunavailable |
| AC08 Three adversarial families | PARTIAL | MockedAIboundary tests; live model/tools/deployed HTTP pending |
| AC09 Traceability | PARTIAL | MT1–6mapped; user-authorized reconstructedRQ1–4 documented; finalmetrics missing |
| AC10 Manuscript/artifacts | IN_PROGRESS |33pageworkingDOCX/nativeOMML/fourfigures/all-pageslayoutreview accepted; AppendixDstatus stale; substantive60–70pagefinalthesis/results/fullcurrentclaimaudit pending |
| AC11 Evidence integrity | IN_PROGRESS | Historicalclaims excluded; independentQA reveals residualdefects; finalclaimaudit remains |
| AC12 Scope separation | PARTIAL | Frozenprimary6367candidates/32recordexpansion/syntheticfixtures separate; fixedrealbinding24tests and acquisition152regressions pass. Social reusegate141tests+6probes verified locally. Source-native/trustedgraphdatasetclass boundary, actual newcapture/T050 andlegacymigration remain pending |

## Mandatory sub-goal audit

| Sub-goal | State | Authoritative evidence / missing proof |
|---|---|---|
| SG01 Audit | VERIFIED | docs/audit, baseline and currentQA corrections |
| SG02 MT/RQ map | VERIFIED reconstructed requirements | THESIS_GAP_MATRIX andLEGACY_RECONSTRUCTION; user authorized new wording from legacy evidence |
| SG03 Source research | VERIFIED | DATA_SOURCE_SURVEY; primarypolicies |
| SG04 Acquisition design | VERIFIED | DATA_ACQUISITION_DESIGN, DATA_CONTRACTS, taxonomy |
| SG05 Collection/extraction | VERIFIED bounded path | Real32candidate local-source run, hashes; no coverage claim |
| SG06 Normalization/resolution/dedup | PARTIAL |152acquisitionregressions and141socialtests locally pass;6parentidentity/enrichment/policyprobes pass. Perentity review/capturequality needed; no newsource imported |
| SG07 Graph integration | IN_PROGRESS | Nativeengine/application/sourceMCP bounded realgraph rollback canaries pass. Fullprimary6367import, AIselectedscope/T049, native-sourceacceptance, durability/concurrency stillpending. Docker notsolepath |
| SG08 Graph/spatial correctness | PARTIAL | Shipped realNEAR_BY/radius/propertycanaries pass after compatibilityfix. E085 proves1stored vs2undirectedrows on2POI, rejects older storageinterpretation. Fullsampledistinctcount/density/performance/concurrency pending |
| SG09 MCP/router/ReAct/graphretrieval | PARTIAL | ActualinprocessMCP sourceflow throughAI059 controlledmodelcanary verified. Jev offline522+23rootprobes và APIpilot30/30HTTP200 accepted bounded; holdout15auto9correct/0wrong/6clarify. Productionpolicy/realmodelReAct/HTTP/fullsnapshot/clientintegration remainpending |
| SG10 Hybridplanner/routes | PARTIAL |162grounding/126planner tests pass on lockedMCP1.26.0; actualsourceplan canary addssecondstop with correctscope/finalmetadata, routingrealHTTP. RT064car/foot actual2POI/4HTTPcanary verified, mode/source scope retained and rollback0/0. Fullsnapshot/liveprovider/client/HTTPintegration pending |
| SG11 Memory | PARTIAL |110memoryoffline tests verify historycommit/profiletail repairs;19/19fixtureharness not science/token saving. RS058P2research delivered, implementation deferred after4phases; realmodel evaluation missing |
| SG12 Literature | VERIFIED bounded review |12primaryworks criticallyreviewed |
| SG13 Fourexperiments | PARTIAL | Protocolv2/amendment beforeprimaryruns, evaluators/collectors/engineeringpair; actualprimarycasefreeze/completeusage/humanresults stillmissing |
| SG14 Adversarial | PARTIAL | Mockedthreefamilies; livepending |
| SG15 Humanstudy | BLOCKED participants/consent | Protocolready;0actualresponses |
| SG16 Deployment | PARTIAL | Backendpackaging/offlineexports/Composeconfig accepted locally; nativeMemgraphcapabilityverifiedwithscope/helperlimits. Nativepatchedroutingactive, Dockerbuild/start/fullserviceintegration pending |
| SG17 Chapters1–5 | IN_PROGRESS | Workingchapters/33pageDOCXrenderreview; final60–70pages/currentresults/reconciledappendix andcompleteall-pageQA missing |
| SG18 Claim/referenceaudit | PARTIAL | Sourceversions/limitationschecked; finalresultsnotavailable |
| SG19 Handoff/evidenceregister | IN_PROGRESS | Livingregister andhandoff; finalstateunstable |

Blocked sub-goals do not mean the overall goal is blocked: actionable implementation and QA continue. Test counts overlap; none is a scientific sample size.

## Current evidence supplement — 2026-10-16

AC04/SG08: OC-017 R1 mocked mutation/radius integration verified independently (47 tests plus direct guard probe); live graph and concurrency still unverified. AC07/SG13: OC-018 R1 has61 passing evaluator tests and independent regenerated synthetic demo, with residual metric-label ambiguity documented in INDEPENDENT_QA; no scientific outcomes. AC10/SG17: reconstructed foundations now exist for Chapter2, but manuscript assembly produced no DOCX because external skill reads were denied; specific read-only authorization requested. Figure refinement hit recurring internal execution failure and remains partial. User-authorized DeepSeek Go substitution is being checked, not yet proven available; Gemini-key absence no longer the requested provider gate.

## Current acceptance reconciliation — 2026-10-16

- AC04/SG08: mutation/radius contract correction independently47tests/directprobe verified; still PARTIAL until livegraph/concurrency checks.
- AC05/SG10:255AI+126planner mock integration verified; livepipeline unavailable, remains PARTIAL.
- AC07/SG13: evaluator61tests; collector83tests andno-op evidence preservation verified, but scenario-selection compatibility R1active; realDeepSeek diagnostic2timeouts/0records. No scientificexperiment completion.
- AC10/SG17: source-driven DOCX andreal28page render exist; all28pages parent-inspected with correctivefindings; R1active. ReconstructedChapter2foundations now included. Finalmanuscriptnotcomplete.
- AC11: updated E031–E037 record knownfailures andlimits; collector compatibility andmetriclabeling remainopen.
- T034/T036 remain IN_PROGRESS, notverified. T035 remains IN_PROGRESS withrenderingprogress andvisualcorrectiongate. T033 remainspartialreporting. All other masterrequirements retainfullscope.

## Evaluator reporting local gate 2026-10-16

T033offlineevaluatorreportingcriteria nowverified atfixturelevel:67independenttests andfreshsyntheticreport,explicitdenominators/coverage/bounds. This closesreportedlabeldefects,notSG13actualexperiments. T034/T036collectorlocalcontract96testsaccepted;liveproviderunavailableinboundeddiagnostics,scientificgateopen. T03527pageworkingdraftrenderfullyreviewed;fullthesis/figures/resultsstillincomplete.

## 2026-10-16 current review supplement

AC03/AC12 and SG06: OC026R1 acquisition classification/state invariant accepted locally140independenttests; no accepted dataset/live ingestion and no legacy state migration.
AC05/backend: OC02734independenttests pass, but storage failure/readiness counterexample rejected acceptance; bounded R1process6785 active. AC10:27page draft fully inspected at OC022R1 gate, latest Chapter4source newer; figures still partial and native equations incomplete. AC07 remains preparation only: DeepSeek2timeouts/0validrecords; no H1participants/H2/H3realresults. E040–E042 and NEXT_SESSION_HANDOFF.md supersede earlier stale milestone wording.

Latest backend gate E043 supersedes E041/R1-active wording: OC027R1 terminal,42independenttests pass; missing-schema readiness probe still mutates schema and returns ready, so AC05 backend remains PARTIAL. No confirmed active writer; next bounded follow-up must prove non-mutating health. Full live/data/model/human/manuscript completion gates remain unmet.

E044 supersedes the OC027 readiness rejection: OC028 local backend draft/readiness contract accepted52independenttests4.15s. AC05 and SG16 remain PARTIAL until actual live integration; packaging/wiring OC030 active. Figures OC029 active, manuscript source/figures/equations/render/full results still pending.

E045 accepts backend packaging/isolated config only:40deploymenttests, actual offline lockedexports and quietCompose validation. AC05/SG16 remain PARTIAL with no live build/start. E046 transport-only third diagnostic45.575stimeout0events, distinct from original2S01timeouts; no scientific sample added. OC029R1 figures pending parentQA; native equations/current-source DOCX rebuilding still feasible and required.
`nCurrent 2026-10-16 reconciliation: AC03/SG06 exact frozen primary preparation has6367 actual-model-valid candidates, all6368features accounted,169tests and two byte-identical reruns. General registry revision capability partial (null hash and prior-revision return defects). AC04/SG07 live import unfulfilled; bulk identity/provenance/admin stages pending, DockerLinuxpipe still absent. AC10 now33-page working DOCX with native math/four figures/all-page layout review accepted, not final60–70page thesis. AC07 actual S01 synthetic engineering pair exists (2records), no controlled primaryH2/H3/humans; supersedes older no-live-call statements.
`n2026-10-17 user confirms no H1 participants available yet. AC07/H1 remains an explicit external dependency: real10–15consentingvolunteers, no fabricated/synthetic substitution. This does not block independent implementation/model experiments or waive the study.



2026-10-18 superseding E070 update: AC04/AC05/AC11 and SG07/SG08/SG16 gain real application evidence for2genuinePOI repository writes/qualified reads/NEAR_BY properties/radius consistency with clean rollback. Earlier disabled-edge-property application failure is preserved and resolved by verified explicit configuration. These broader AC/SG requirements remain incomplete pending full ingestion/service/concurrency/durability/performance/deployment. T053/T054 accepted only at this bounded compatibility/configuration gate. Four-phase/H1 decision control remains unchanged.

2026-10-18 E071 stand-in window (Hermes acting as Codex, 02:33–06:08). AC04/SG08 advance: T061 date-serialization defect fixed at the service boundary (both `selection`/`poi` dumps use mode=json) plus a distinct `serialization_failed` code so an encoding defect is never reported as `exploration_failed`; real-graph canary on Memgraph 3.13.2 passes 7/7 stages with clean rollback (nodes 0 relationships 0 before and after), still in-process FastMCP, no HTTP transport, no Docker. AC03/SG06/AC11: QA-DATA-01 was proven by execution (caller-built expectations returned real=True for a 3-feature dataset) and closed with a `real_binding_mismatch` guard that fires before any file read; the reviewed real path still validates 6367 records with unchanged prepared_sha256. AC05: T051 `--pure` now capability-negotiated (installed CLI v2.0.32 advertises none) and the native-binary resolution for the `@opencode/cli/bin` npm layout was fixed, so the CLI transport can start; no live model call was made. T060: engine re-measured (car 200, foot 400 with "available CH profiles: [car]", foot+ch.disable=true 200) and the tool now sends ch.disable for profiles without CH via GRAPHHOPPER_CH_PROFILES; no straight-line fallback; 6 new contract tests. T057: fetch byte-bound before read on both success and error paths, real DNS pinning via a pinned dialer with default proxies disabled, license gate rejecting before any request; entity identity namespaced by canonical page URL; enrichment requires name+address+finite in-range coordinates and no longer echoes transport text; suites 56→109 and 140→152 passed after the fixture migration performed by the parent. AC07/Experiment 2 gains measured spatial results on the frozen 6367-record snapshot: 20,266,161 unordered pairs, 0 false negatives at 1/3/5 km, candidate work cut 95.5%/78.5%/59.3% (graph-engine edge counts still unmeasured). T062/HM-053 root QA completed: 40/40 package tests and a 19-payload execution matrix pass; two findings recorded (report R1 misstates `declare -x`; helper authorization resolves against the guard process cwd rather than the payload cwd). Remaining PARTIAL/BLOCKED unchanged: full 6367 import (AC04/SG07), source-scope contract in the AI planner (AC05), Docker end-to-end and durability (AC01/AC09), H1 human study (AC07 external dependency), and hook activation (gated, not installed).
