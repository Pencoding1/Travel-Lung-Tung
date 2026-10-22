# Thesis gap matrix

Source: supplied revision proposal, sections B.3/B.4 and objective tables. User confirmed original lost and authorized reconstruction; ../thesis/LEGACY_RECONSTRUCTION.md supplies explicitly newly authored RQ1–4 and subquestions, preserving objective/hypothesis mappings. No historical metric is accepted as reproduced evidence.

## Current mapping and evidence gates

| Objective | Reconstructed question | Current evidence | Remaining proof |
|---|---|---|---|
| MT1 | Foundation for all four | 12-work review; REF099 bounded citation audit with 134 structural/preservation checks | Unified thesis-wide claim/citation audit; original 18 references unavailable, reconstruction disclosed |
| MT2 | RQ2.1 lifecycle;RQ2.2 spatial correctness/pruning | DATA068 frozen6367POIs; E2093 actual engine pair equality150/150batches; TIM097 completed30measured cells; GRAPH115actual lifecycle7/7 on4syntheticPOIs/83assertions,219independentreview | Physical engine distance-call counts remain unmeasured;5km prefilter slower. Lifecycle receipt is bounded4POI,not wholegraphCRUD/concurrency; do not invent those as additional phase4 gates. |
| MT3 | RQ1.1 tool behavior;RQ1.2 trust | Jev synthetic live pilot; SYS101 actual typed HTTP/tool/provider flow and bounded adversarial study; human protocol prepared | H1: 0 participants, requires 10–15 real consenting participants; SYS101 does not prove /chat/Jev/browser integration |
| MT4 | RQ3.1 temporal violations;RQ3.2 tradeoffs | H2091 primary batch: 120 attempted, 119 provenance-complete and 1 timeout gap; route/violation analysis retained | Only 13/20 eligible matched pairs; inference blocked by incomplete coverage; unknown price/hours prevent global feasibility proof; no filling frozen missing cell |
| MT5 | RQ4.1 preference effect;RQ4.2 lifecycle/cost | Persistence/CAS/profile checks; CORE085/087 readiness; H3090 primary batch attempted | H3 only 1/15 delivered, 14 missing after timeout; no demonstrated memory effect or token savings; provider usage incomplete |
| MT6 | Cross-cutting deployment/robustness | SYS101 testedA/B/C with rawfailures retained:8supported/1inconclusive. SYS102140offline; separateSYS119liveB2 all8sourcecomparisons true,1Go,2IDs/routecomplete,191parent/206review | All3required adversarialfamilies have been tested; no naturalhallucinationrate or retrospectiveSYS101pass. Currentbrowser/fullCompose/publicdeployment unproven. DOC122report exists; userprioritizes chatbot/mapdemoUI127, not H1/writing. |

The baseline table below is historical audit evidence, not current defect status. Current acceptance is governed by ../project/ACCEPTANCE_TRACKER.md and INDEPENDENT_QA.md.

Current mapping updated by Codex 20/10/2026 against DATA068, E2-093, TIM-097,
H2-091, H3-090, SYS-101, SYS-102, SYS-119, GRAPH-115, DOC-122 and REF-099 receipts under
`docs/project/handoffs/`. These are bounded evidence statements, not a completion
claim for MT1–MT6. Raw primary outcomes remain immutable; synthetic tests are
not participant evidence. Writing/H1 awaits the user's phase4 decision; new
crawler and grow-with-user integrations belong to Finalizing phase.

## Initial source-audit baseline

| Requirement ID | Thesis Section | Existing Implementation | Verified Status | Missing Work | Dependencies | Priority | Evidence | Acceptance Criteria |
|---|---|---|---|---|---|---|---|---|
| MT1 | Ch2, §2.9 | No verified review matrix located | UNVERIFIED | 12 original publications; synthesis and bibliography | Primary publications | P2 | Proposal extract | All 12 verified and critically reviewed |
| MT2 / RQ2 | §3.2–3.5,4.4 | Graph models, canary, NEAR_BY | PARTIAL | Stable IDs, valid coordinates, prefilter repair, ingestion tests, live snapshot and benchmark | Test runtime; Docker | P0 | graph_entities.py; memgraph.py:181 | Actual graph writes and measurable correct spatial filtering |
| MT3 / RQ1 / H1 | §3.6–3.8,4.3 | Five MCP tools, intent and ReAct | PARTIAL | Contract/trace tests, grounding, runtime measurements, actual paired user study | MCP/model runtime; volunteers and consent | P1 | tools.py; ai_service/main.py | Executed system metrics plus 10–15 real participants for H1 |
| MT4 / RQ3 / H2 | §3.9–3.10,4.5 | Candidate retrieval, LLM synthesis, separate routing tool | PARTIAL | Deterministic feasibility stage, routing integration, fair baseline, 20 scenarios | Frozen graph; model; GraphHopper | P0 | ai_service/main.py:181 onward | Same model/POIs; measured violations, budgets and route metrics |
| MT5 / RQ4 / H3 | §3.8,4.6 | Process chat dictionary and disconnected preference repository | PARTIAL | Compression, persistence/retrieval integration, current constraint precedence, controlled profiles | Agent integration and persistence | P1 | domains/payloads.py; MemgraphUserBehaviorRepository | At least 4–5 profiles, memory on/off; measured tokens and alignment |
| MT6 | §3.12,4.7–4.8 | Compose and scattered scripts | PARTIAL | Reproducible deployment, three adversarial families, integrated workflow | Docker and preceding fixes | P0 | docker-compose.yaml; E002/E003 | Executed deployment and adversarial evidence |
| AC02/SG03–07 | Ch3 acquisition | Traveloka extraction and proposed taxonomy | PARTIAL | Two authorized source families, provenance, review queue, closed taxonomy, deduplication, graph bridge | Source authorization and contracts | P1 | crawler_service; docs/poi-crawl | Executed acquisition paths and quality metrics with denominators |
| AC09–12/SG17–19 | Ch1–5 and appendices | Revision outline and historical claims | UNVERIFIED | Five chapters, verified references, raw experiments, diagrams, consistency report | Measured outcomes | P2 | THESIS_PROPOSAL_EXTRACT.txt | Evidence-linked 60–70 page thesis with explicit limitations |

Historical claims requiring raw evidence: ~200 POIs; canary 120 ms; graph counts; SSE success; 300 versus 40,000 distance operations; 35% violations versus 100% feasible; budget errors under 8% versus 30–70%; 32.4% route deviation; 58% token reduction; preference share 28% to 72%. These are neither current measurements nor acceptance-test results. Arithmetic alone gives 99.25% reduction for 300/40,000, but the underlying counts remain unverified.

Original dataset scope: Districts 1 and 3, HCMC. Do not conflate source expansion with the primary comparison. User study remains blocked until real voluntary participation and authorization; prepare materials independently.
