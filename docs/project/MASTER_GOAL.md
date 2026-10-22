> **Current authority, Codex21:50 18/10/2026:** S1–S6approved; FOUR_PHASE_PLAN.md and HANDOFF_CODEX_CURRENT_2026-10-18.md govern current execution. All crawler/grow-with-user integrations deferred to phase5Finalizing. Jev/nativecore/full6367graph have bounded accepted receipts; older paragraphs saying Jev unimplemented, activeOC050, missingfullimport are historical. H1/furtherthesiswriting waitsphase4choice. OriginalSG01–SG19/AC01–AC12below remain intact; not all are achieved. Docker29.2.1server is currently reachable (EXP078 parent-docker-readonly-readiness.json), deployment itself stillunverified.

> **Cập nhật phạm vi18/10/2026:** T057 P0 ingest POI xã hội/web nguồn lấy nhanh, T058 P1 crawler HTTP/web tĩnh, T059 P2 nguồn động/chống bot chỉ nghiên cứu. Kế hoạch đã chốt: handoffs/OC-050/brief.md. Sub-agent thứ ba/cuối /root/social_poi_ingest đang giám sát OpenCode AI-box; chưa có nghiệm thu, chưa graph import. Memory T056 vẫn P2 sau bốn phase; không chờ viết luận án. Các ghi chú cũ “không có writer mới” bị thay thế bởi trạng thái này.

> Scope amendment from the user, 2026-10-18: execute FOUR_PHASE_PLAN.md in order: verify, finalize thesis-aligned code, experiments, report. Then wait for the user's choice of H1 or further thesis writing. Codex plans first (/plan workflow) and owns QA; OpenCode implements. Replace any Ollama/local-LLM intent-classification design with Jev/TypeSafe; this is not yet implemented. See JEV_INTENT_PLAN.md. Choose paid AI-box for difficult work and Go for simpler work when available; never explicit V4.0. These directions supersede conflicting older execution instructions without fabricating completion.

> Latest approved user scope18/10/2026: **S1–S6 are approved**, prioritizing user input→recommending→routing→usable result with existingOSM data, followed by experiments/report. **Phase5 is the Finalizing phase for all new mechanisms**, including grow-with-user, legacy/travel-agency/social crawling and selected future expansions. None is a phase2/experiment prerequisite. See PHASE2_SCOPE_FOR_APPROVAL_VI.md and DECISION_LOGD014. Preserve frozen manifests/unknown upstream IDs; do not invent provenance. Wait for phase4userchoice beforeH1/furtherthesis.

# /goal — TRAVEL AI: DATA EXPANSION, SYSTEM COMPLETION & THESIS VALIDATION

> Scope amendment from the user, 2026-10-16: the primary POI dataset has expanded from the historical approximately200-record description to more than1000processedPOIs. The user supplied `C:/Users/duyan/Downloads/Telegram Desktop/hcm_pois_final.geojson`. Independent inspection counts **6368Point features** (2712731bytes, SHA256713b07a62cf89bd2cad9093abaad2a4c5f01e23853321764b3d66bf9f7eee43c), preserved unchanged at `data/primary_20261016/hcm_pois_final.geojson`. Feature count is not yet a verified unique accepted graph-node count. Audit quality, identity/category/admin mappings and integration before claiming6368acceptedPOIs. Historical200figures remain historical; all SG/MT/RQ/AC requirements and controlled experiments still apply at the revised dataset scale. The32quarantined expansion records are a separate dataset.

## ROLE & MISSION

You are acting as a **Senior AI Systems Architect, Research Engineer, Data Engineer, and Software Verification Engineer** responsible for completing the Travel AI system (Travel Lung Tung / TVLT_2026).

Your mission is to research, design, implement, integrate, test, and evaluate the remaining components required to produce a functional AI-powered travel recommendation and itinerary planning system, consistent with the supplied graduation thesis proposal.

This is an **implementation and research assignment**, not merely an architectural planning exercise.

You must inspect the existing repository, verify its real implementation status, extend the existing architecture, conduct reproducible experiments, and generate evidence-backed technical and academic deliverables.

Do not assume that the claims made in existing documentation reflect the current implementation.

The primary objective is to complete the system according to the thesis scope, rather than introducing unnecessary infrastructure or unrelated features.

---

# 1. SOURCE OF TRUTH

The following documents define the initial requirements:

**Document A — Crawling Research Findings**

`bao-cao-tom-tat-findings.md`

Associated documents, if present in the repository:

- `docs/poi-crawl/khao-sat-nguon-va-ke-hoach.md`
- `docs/poi-crawl/tiktok-trich-xuat.md`
- `docs/poi-crawl/phan-loai-dia-diem.json`

**Document B — Graduation Thesis Proposal**

`12.docx`

The thesis defines the six research objectives (MT1–MT6), four research questions (RQ1–RQ4), experimental requirements, implementation scope, and expected thesis deliverables.

The existing repository is the source of truth for what has actually been implemented.

Scientific publications and official technical documentation are the sources of truth for externally verifiable research claims.

Apply the following evidence hierarchy:

1. Verified implementation behavior, tests, runtime logs, and measured results.
2. Source code, configuration, schemas, and dependency manifests.
3. Project documentation and historical findings.
4. Official documentation and peer-reviewed scientific literature.
5. Engineering assumptions and hypotheses, which must be explicitly labeled.

If these sources disagree, investigate the discrepancy rather than silently selecting the most convenient interpretation.

Treat research findings as previously observed evidence, not as guaranteed platform behavior in the current environment.

---

# 2. CORE ENGINEERING PRINCIPLES

## 2.1. Preserve the existing system

Do not rewrite the architecture unnecessarily.

The existing solution contains, according to the supplied documents:

- `crawler_service`: collection and extraction of travel data.
- `POI_service`: validation, ingestion, knowledge graph management, and spatial processing.
- `ai_service`: Intent Router, ReAct Agent, MCP tools, memory, and recommendation workflows.
- `backend_service`: supporting application and business functionality.
- Memgraph: POI knowledge graph.
- GraphHopper: route computation.
- Docker Compose: infrastructure orchestration.

Verify the actual names, directory locations, services, and implementation before making modifications.

Prefer extending existing modules through explicit interfaces and documented extension points.

## 2.2. Separate research conclusions from implementation decisions

For each major architectural choice, document:

- The problem being solved.
- Alternatives considered.
- Research evidence supporting the choice.
- Constraints of the existing architecture.
- Expected benefits and trade-offs.
- Final decision.
- Validation method.

Use Architecture Decision Records (ADRs) for significant decisions.

## 2.3. Explicit assumptions and contracts

Avoid implicit business assumptions, undocumented fallback behavior, and unexplained magic numbers.

Every important threshold, heuristic, retry policy, scoring weight, confidence threshold, and classification rule must have a documented reason.

Distinguish between configuration values, domain invariants, experimental parameters, and implementation constants.

Validate every external data boundary.

## 2.4. Evidence-driven development

Never report a feature as completed solely because source code exists.

Completion requires appropriate evidence such as automated tests, integration tests, successful executions, persisted records, reproducible results, or documented acceptance-test observations.

Never fabricate benchmark values, user-study results, citations, screenshots, or runtime logs.

## 2.5. Research integrity

Do not optimize experimental conditions only to confirm existing hypotheses.

Results that contradict the expected hypotheses must be retained and discussed.

Ensure the baseline and proposed method operate under comparable conditions.

Preserve raw measurements and experiment configurations.

## 2.6. Compliance and data governance

Use only data sources and collection methods for which access and reuse are permitted.

Prioritize official APIs, public datasets, openly licensed information, and authorized access methods.

Respect robots directives where applicable, platform terms, copyright restrictions, privacy, rate limits, and service quotas.

Do not circumvent CAPTCHA, authentication, access restrictions, or anti-bot protection.

Previously observed access to TikTok subtitles or Google Maps internal page data does not imply unrestricted authorization to collect or redistribute that data.

Do not expose cookies, credentials, API keys, private account data, or authentication tokens in reports and logs.

---

# 3. EXECUTION STRATEGY

Execute the project through the phases below.

Each phase must produce independently verifiable artifacts.

Do not implement all components simultaneously.

Before starting a phase, identify its dependencies. After completing it, verify its acceptance criteria.

If acceptance criteria fail, diagnose the failure, correct the implementation where feasible, and rerun the relevant validation.

Do not silently skip incomplete tasks.

When a task is blocked by missing authorization, credentials, human participation, unavailable infrastructure, or other external dependencies, explicitly mark it `BLOCKED`, preserve the evidence, and continue independent work.

The agent must never invent results to satisfy an acceptance criterion.

---

# PHASE 0 — REPOSITORY AUDIT & THESIS GAP ANALYSIS

## Goal

Establish an accurate understanding of the Travel AI system and identify the difference between its actual implementation and the thesis requirements.

## Tasks

1. Inspect the complete repository structure and Git status.
2. Read the existing architectural and project documents.
3. Identify the responsibilities, interfaces, dependencies, and data flows of each service.
4. Inspect Docker Compose, environment configuration, schemas, and API contracts.
5. Trace the existing travel data pipeline from crawling to ingestion, graph retrieval, and itinerary generation.
6. Inspect the current implementations of Crawl4AI, Memgraph, MCP, ReAct, GraphHopper, and memory mechanisms.
7. Identify stub implementations, incomplete integrations, undocumented assumptions, unused components, and broken workflows.
8. Map every thesis objective MT1–MT6 and RQ1–RQ4 to the actual implementation.
9. Identify previously reported experiments whose results cannot yet be reproduced.

Pay particular attention to the current `POI` domain model, category and tag schemas, entity identifiers, geographic constraints, and batch ingestion behavior.

Check whether classification labels are embedded in identifiers and whether reclassification could create duplicate entities or break relationships.

## Deliverables

Create:

- `docs/audit/SYSTEM_INVENTORY.md`
- `docs/audit/ARCHITECTURE_AS_IS.md`
- `docs/audit/THESIS_GAP_MATRIX.md`
- `docs/audit/ASSUMPTION_REGISTER.md`
- `docs/audit/IMPLEMENTATION_ROADMAP.md`

The gap matrix must contain the following columns:

`Requirement ID | Thesis Section | Existing Implementation | Verified Status | Missing Work | Dependencies | Priority | Evidence | Acceptance Criteria`

Use these statuses consistently:

`VERIFIED`, `PARTIAL`, `NOT_IMPLEMENTED`, `UNVERIFIED`, `BLOCKED`.

## Acceptance Criteria

- Every MT1–MT6 objective has an explicit implementation and verification mapping.
- Every major service has been inspected.
- Existing capabilities have been distinguished from planned capabilities.
- No undocumented assertion is used as proof of implementation.
- A dependency-aware execution plan exists.

---

# PHASE 1 — RESEARCH DATA ACQUISITION & POI EXPANSION

## Goal

Identify viable data sources and design an extensible, policy-compliant data acquisition system that increases the quantity, quality, diversity, and freshness of POI information.

The solution must integrate into the existing `crawler_service`, not become a separate competing crawling platform.

## 1.1. Research data sources

Evaluate at least the following source families:

- Public tourism articles and destination guides.
- Public structured datasets and spreadsheets.
- Tourism service websites already supported by the system.
- Official tourism information portals.
- OpenStreetMap and relevant public geographic datasets.
- Permitted social-media content or authorized platform APIs.
- Other verifiable public sources that can enrich tourism POIs.

Re-examine the prior findings for TikTok subtitles, public Google Sheets, Google Maps, and travel article extraction.

Treat previous accessibility measurements as preliminary.

Do not assume that an unofficial extraction mechanism remains stable, lawful, or operational.

For each source family, evaluate:

- Accessibility and collection authorization.
- Available fields and data quality.
- Geographic coverage.
- Update frequency.
- Cost and technical complexity.
- Entity resolution requirements.
- Reliability and operational risks.
- Suitability for the thesis scope.

Build a source feasibility matrix and select a justified implementation priority.

## 1.2. Research acquisition architecture

Study and compare appropriate approaches, including:

- HTTP clients and structured parsers.
- Scrapy.
- Crawl4AI.
- Browser-based rendering.
- Official APIs.
- Schema-based extraction.
- Rule-based extraction.
- LLM-assisted structured extraction.

Do not adopt a technology simply because it is popular.

Evaluate compatibility with the existing repository, expected extraction quality, computational requirements, and maintenance overhead.

Prefer inexpensive deterministic extraction before invoking an LLM.

## 1.3. Architecture requirements

Design the acquisition pipeline using the following conceptual stages:

`Source Discovery → Fetching → Extraction → Normalization → Entity Resolution → Enrichment → Validation → Deduplication → Review → Ingestion`

These are logical responsibilities and do not necessarily require separate microservices.

The pipeline must support source-specific adapters behind shared contracts.

Use Package by Capability inside the existing service where appropriate.

Apply relevant patterns such as:

- Adapter for source-specific collection.
- Strategy for alternative extraction approaches.
- Registry for selecting source implementations.
- Factory where object construction requires configuration.
- Repository for persistence boundaries.
- Pipeline or Chain of Responsibility for validation and transformation.

Do not introduce patterns without a concrete reason.

## 1.4. Source contracts

Define explicit data contracts for:

**RawSourceRecord:** source identifier, URL, retrieval time, source type, raw content reference, collection status, and extraction metadata.

**POICandidate:** proposed name, aliases, address hints, description, candidate category, source evidence, and uncertainty metadata.

**ResolvedPOI:** canonical name, verified coordinates, administrative location, category mapping, confidence/evidence, and source references.

**IngestionDecision:** accepted, rejected, duplicate, or requires review, with reason codes.

These are conceptual requirements. Adapt them to actual domain models after inspecting the code.

Do not place unverified external data directly into trusted graph entities.

## 1.5. Extraction and enrichment

Implement deterministic parsing for structured sources where feasible.

Use LLM extraction only when the content structure is sufficiently complex to justify it.

For audio-derived text, preserve the original transcript and timestamp references.

Do not automatically correct uncertain Vietnamese place names without corroborating evidence.

Implement geographic entity resolution using licensed geographic data, authorized geocoding services, or other reliable location sources.

Differentiate:

- Exact POI matches.
- Probable matches.
- Ambiguous matches.
- Unresolved candidates.
- Spatial areas versus individual venues.

Ambiguous and unresolved candidates must enter a review queue rather than being promoted to confirmed POIs.

## 1.6. Taxonomy and graph compatibility

Inspect the proposed three-level classification scheme in `phan-loai-dia-diem.json`.

Validate whether the proposed taxonomy is compatible with existing graph entities and agent search contracts.

Determine whether classification should be represented through Category, Tag, spatial shape, or a combination.

Use a closed list of accepted category identifiers.

Unknown categories must not be silently invented.

Investigate identifier stability and referential integrity before modifying existing taxonomy rules.

If changing category labels changes entity IDs, design a safe migration strategy or a stable identifier mechanism supported by the current architecture.

## 1.7. Deduplication and provenance

Design POI deduplication using combinations of:

- Canonical names.
- Name aliases.
- Geographic distance.
- Administrative area.
- Address similarity.
- Source-specific identifiers.
- Supporting evidence.

Do not merge distinct businesses solely because they have similar names and nearby coordinates.

Maintain provenance for every imported fact.

Record where a fact came from, when it was retrieved, and how it was verified.

Preserve conflicting information rather than silently overwriting it.

Support reprocessing and idempotent ingestion.

## 1.8. Data quality evaluation

Design an evaluation dataset through reproducible sampling and manual verification.

Measure at minimum:

- Extraction precision and recall where ground truth is available.
- Geographic resolution success rate.
- Category classification accuracy.
- Duplicate detection precision and recall.
- Proportion requiring manual review.
- Ingestion acceptance rate.
- Provenance completeness.
- Processing latency and cost.

Clearly define numerator, denominator, sample size, and labeling procedure for every metric.

Do not substitute LLM-generated labels for independent ground truth without acknowledging the resulting bias.

## Deliverables

Create:

- `docs/research/DATA_SOURCE_SURVEY.md`
- `docs/architecture/DATA_ACQUISITION_DESIGN.md`
- `docs/architecture/POI_TAXONOMY.md`
- `docs/architecture/DATA_CONTRACTS.md`
- `docs/decisions/` containing relevant ADRs.
- A functioning and tested implementation in the existing service.
- Data quality evaluation scripts and evidence.
- Operational documentation.

## Acceptance Criteria

- At least two complementary source families have working, policy-compliant acquisition paths.
- Source adapters conform to shared contracts.
- Collected data is traceable to its origins.
- Unresolved POIs cannot silently enter the trusted knowledge graph.
- Duplicate ingestion is idempotent.
- The resulting POIs satisfy domain validation.
- Source acquisition failures do not corrupt existing data.
- The implementation uses existing service boundaries wherever feasible.

---

# PHASE 2 — GRAPH INGESTION & SPATIAL KNOWLEDGE VALIDATION

## Goal

Integrate expanded POI data into Memgraph and verify the consistency, performance, and geographic accuracy of the graph.

## Tasks

1. Inspect the current graph schema, including the seven node types and seven relationship types described in the thesis.
2. Validate Category, Tag, District, Street, POI, and other existing entity relationships.
3. Verify the `/ingestion/batch` contract and current canary behavior.
4. Test both successful and failed batch ingestion.
5. Verify transaction semantics and partial-failure behavior.
6. Verify SSE progress reporting.
7. Implement safe taxonomy initialization or migration where necessary.
8. Ensure newly collected POIs can be queried through existing MCP tools.
9. Recompute or update spatial relationships safely after new POI ingestion.
10. Preserve the current dataset and create a reproducible experimental snapshot before modifying graph data.

## Spatial evaluation

Re-examine the NEAR_BY algorithm.

Verify:

- Bounding-box candidate filtering.
- Correct Haversine distance computation.
- Geographic units and coordinate order.
- Boundary cases.
- Distance threshold behavior.
- Graph edge consistency.
- Computational complexity and measured performance.

Pay particular attention to the longitude approximation in the thesis: longitude degrees must account for latitude when used as a spatial prefilter. A mathematically invalid bounding box must not silently exclude nearby POIs.

Evaluate the 3 km radius and, where feasible, compare alternative radii of 1 km and 5 km.

Report candidate counts, exact distance computations, graph edge counts, execution time, and hardware conditions.

## Deliverables

- Verified graph schema documentation.
- Ingestion integration tests.
- Geographic correctness tests.
- Data migration and rollback procedure.
- Reproducible dataset snapshot.
- Spatial benchmark results.

## Acceptance Criteria

- Existing graph records remain valid.
- New POIs are retrievable by the existing system.
- Category and Tag relationships are correct.
- Duplicate entities are controlled.
- Spatial filtering does not introduce false negatives within the tested radius.
- Batch failures are observable and recoverable.
- Spatial performance claims are supported by measurements.

---

# PHASE 3 — AI AGENT SYSTEM INTEGRATION & COMPLETION

## Goal

Verify and complete the core AI functionality required by the thesis, using the expanded POI knowledge graph.

Do not replace the existing agent architecture unless a verified architectural deficiency requires it.

## 3.1. Intent Router and ReAct

Inspect the current intent classification logic, model configuration, tool selection, and execution limits.

Verify the distinction between CHITCHAT and TRAVEL requests.

Measure routing accuracy, tool invocation correctness, latency, loop termination, and failure handling.

Verify the configured maximum number of ReAct steps and document why the chosen limit is appropriate.

## 3.2. MCP

Inspect the MCP tool server and the five standardized tools described in the thesis.

Verify tool contracts, input validation, output consistency, error handling, and tool-chain trace generation.

Check whether new POI categories and enriched metadata are accessible through existing tool interfaces.

Prevent tools from returning unverified records as authoritative facts.

## 3.3. Graph RAG and hallucination control

Define precisely what is meant by factual grounding.

Separate:

- Existence of a POI in the graph.
- Correctness of its attributes.
- Freshness of its information.
- Correctness of the itinerary.
- Unsupported claims generated by the LLM.

Implement appropriate validation at the output boundary.

An itinerary containing only POIs from the graph is not sufficient evidence that all generated details are factually correct.

## 3.4. Hybrid recommendation — Pipeline Vi Vu

Inspect the actual four-stage recommendation pipeline.

Verify candidate retrieval, preference-based scoring, heuristic selection, itinerary construction, and route evaluation.

Ensure the planning engine uses verified POI data.

Inspect opening-hours constraints, visit durations, budget estimates, and travel times.

Do not confuse straight-line geographic distance with road-network travel time.

## 3.5. GraphHopper

Verify the running GraphHopper configuration and route data coverage.

Test routing between representative POIs.

Record unavailable routes, failed requests, unreasonable travel-time estimates, and fallback behavior.

## 3.6. Two-tier agent memory

Inspect Working Memory and Long-term Profile Memory.

Verify memory compression, preference persistence, retrieval, and their actual influence on recommendations.

Document privacy boundaries and avoid retaining unnecessary personal data.

Verify that stored preferences are not confused with explicit current-user constraints.

## 3.7. Backend and application workflows

Inspect `backend_service` and frontend dependencies relevant to the thesis demonstration.

Complete missing functionality required for the core use cases.

Explicitly distinguish essential thesis functionality from optional production features.

Avoid expanding scope into unrelated commercial application requirements.

## Deliverables

- Updated agent architecture documentation.
- Tested MCP tool contracts.
- End-to-end itinerary generation tests.
- Memory integration tests.
- Routing validation evidence.
- Verified core application workflows.

## Acceptance Criteria

- Travel requests can produce itineraries using verified graph data.
- Tool invocations and execution failures are observable.
- The agent does not silently substitute invented POIs when data is insufficient.
- Route constraints are validated.
- Memory behavior is reproducibly testable.
- Core thesis workflows function end to end.

---

# PHASE 4 — ACADEMIC LITERATURE REVIEW

## Goal

Complete the scientific literature survey required for thesis objective MT1.

Research at least 12 verifiable publications specifically relevant to the Travel AI research questions.

## Research domains

Include work on:

1. LLM-based travel recommendation and itinerary planning.
2. POI recommendation and spatial Knowledge Graphs.
3. Graph RAG and geographically grounded language generation.
4. Multi-agent and tool-augmented LLM systems.
5. Long-term agent memory and personalization.
6. Evaluation methodologies for travel planners and conversational AI.

Use reputable sources such as ACM Digital Library, IEEE Xplore, ACL Anthology, Springer, scholarly conference proceedings, and relevant preprints.

Clearly label papers that have not undergone peer review.

Verify publication titles, authors, years, venues, and identifiers against original publications.

Do not treat unverified bibliography placeholders in the thesis proposal as real references.

## Literature synthesis

For each paper, extract:

- Research problem.
- Dataset and evaluation setting.
- Proposed methodology.
- Experimental results.
- Limitations.
- Relevance to Travel AI.
- Implications for design decisions.

Build a comparison matrix and identify gaps supported by the literature.

Do not claim research novelty solely because a particular architectural combination has not appeared in the papers reviewed.

## Deliverables

- Literature review matrix with at least 12 verified papers.
- Bibliographic records and stable publication links.
- Theoretical foundation notes.
- Research-gap analysis.
- Chapter 2 draft or revision aligned with the thesis.

## Acceptance Criteria

- All references can be verified.
- All numerical claims are linked to their original evidence.
- Comparisons are analytically balanced.
- The discussion includes limitations and counterevidence.
- Thesis claims are clearly distinguished from hypotheses.

---

# PHASE 5 — EXPERIMENTAL DESIGN & EXECUTION

## Goal

Complete and rerun the experiments required by Chapter 4 under transparent and reproducible conditions.

Create an experiment registry containing datasets, seeds, configurations, baselines, raw outputs, and evaluation scripts.

Freeze the primary experimental dataset and configuration before final comparisons.

Expanded POI coverage may be evaluated separately as an additional experiment, but it must not silently replace the original thesis scope.

## EXPERIMENT 1 — Multi-agent interaction and perceived trust

Evaluate Intent Router correctness, ReAct execution, response latency, and tool-chain behavior.

Prepare a within-subject user study comparing interfaces with and without visible `tool_chain`.

Target 10–15 voluntary participants.

Counterbalance presentation order.

Use a documented Likert scale for perceived trust and satisfaction.

Prepare questionnaire forms, consent information, and anonymized response templates.

Apply an appropriate paired statistical analysis such as the Wilcoxon signed-rank test where justified.

Participation and responses must be genuine. The agent must not simulate human subjects or fabricate survey results.

If participants are not available, mark this part incomplete and explain the effect on RQ1/H1.

## EXPERIMENT 2 — Spatial Knowledge Graph and grounding

Evaluate NEAR_BY filtering correctness and performance.

Compare optimized candidate filtering against exhaustive pairwise distance calculation.

Measure actual operations and runtime.

Evaluate graph-grounding correctness independently of text generation quality.

Resolve inconsistencies in previously reported percentages by recalculating them from the raw counts.

## EXPERIMENT 3 — Hybrid itinerary recommendation

Prepare at least 20 reproducible test scenarios representing varying travel durations, budgets, categories, POI counts, and time constraints.

Compare:

- The proposed hybrid planning method.
- A pure LLM baseline using the same model and retrieved POI candidates.
- Straight-line distance-based route estimates where relevant.

Keep model version, available POIs, scenario definitions, and evaluation rules comparable.

The primary methodological difference between the proposed planner and pure LLM baseline should be the presence or absence of the tested heuristic mechanism.

Measure constraint violations, budget error, route feasibility, and relevant planning metrics.

Record full sample sizes and error distributions.

## EXPERIMENT 4 — Agent memory and personalization

Evaluate short-term context retention and long-term personalization.

Preserve the thesis's eight-turn example as an illustrative case if reproducible.

Extend the experiment to at least four or five distinct synthetic user profiles with different documented travel preferences and constraints.

These profiles are test scenarios, not real participant records.

Compare behavior with and without long-term memory under controlled conditions.

Measure token consumption, preference alignment, consistency, and inappropriate preference carryover.

Do not claim personalization effectiveness based on a single example.

## ADVERSARIAL EVALUATION

Test at least the following cases:

**Case A — Empty or insufficient POI candidates:** The system must communicate data limitations instead of inventing places.

**Case B — Unsupported POI details:** Check generated opening hours, prices, addresses, and descriptions against retrieved evidence.

**Case C — Out-of-scope request:** Test requests for areas outside the supported dataset and verify that the system does not misrepresent nearby records as requested destinations.

Document all failures.

Report confidence intervals, descriptive statistics, or inferential tests when suitable for the sample size and experimental design.

Do not automatically describe results as statistically significant without an appropriate test.

## Deliverables

- Experiment protocols.
- Reproducible scenarios and datasets.
- Baseline configurations.
- Evaluation scripts.
- Raw measurement results.
- Statistical analysis.
- Chapter 4 results and discussion.

## Acceptance Criteria

- Each RQ/H has an explicit evaluation protocol.
- Experimental configurations are reproducible.
- Baselines are fair and documented.
- The three adversarial test families have executed.
- Failed cases are retained.
- Human-study results are never fabricated.
- Conclusions reflect measured evidence.

---

# PHASE 6 — SYSTEM VERIFICATION & THESIS COMPLETION

## Goal

Complete the remaining required thesis deliverables and verify the full Travel AI system.

## 6.1. System verification

Build and validate the Docker Compose environment.

Run unit, integration, contract, and end-to-end tests where applicable.

Verify the complete workflow:

`Acquisition → POI Validation → Graph Ingestion → MCP Retrieval → Agent Reasoning → Itinerary Planning → User Response`

Inspect performance, configuration reproducibility, application errors, and essential security limitations.

Document the precise model and software versions used in final experiments.

Do not claim production readiness without evidence.

## 6.2. Thesis documentation

Complete the five chapters according to the supplied outline:

**Chapter 1:** Introduction, objectives, scope, research questions, and thesis structure.

**Chapter 2:** Theoretical foundations, verified literature review, research gaps, and proposed solution.

**Chapter 3:** System architecture, knowledge graph, acquisition, ingestion, spatial processing, MCP, agent reasoning, memory, recommendation, routing, formal definitions, parameters, and risks.

**Chapter 4:** Experimental environment, datasets, reproducible protocols, quantitative and qualitative results, adversarial evaluation, and discussion.

**Chapter 5:** Conclusions mapped to MT1–MT6, scientific and engineering contributions, limitations, future work, and recommendations.

The thesis must clearly distinguish historical results, reproduced measurements, newly obtained results, and unverified statements.

Use scientific academic writing.

Preserve accepted discipline-specific terminology.

Avoid unsupported generalizations.

## 6.3. Diagrams and supporting materials

Create architecture diagrams, module diagrams, data-flow diagrams, and experimental workflow diagrams using Mermaid source definitions.

Where final thesis figures are required, render those diagrams into suitable image formats.

Do not use decorative ASCII diagrams.

Prepare supplementary documentation sufficient for a reviewer to understand and reproduce the system.

## 6.4. Thesis compliance verification

Review the final thesis against the approved proposal.

Check consistency of:

- Project naming.
- Research objectives and hypotheses.
- Architecture descriptions.
- Dataset scope.
- Model versions.
- Experimental sample sizes.
- Reported metrics.
- Citations.
- Figure and table numbering.
- Final conclusions.

Retain the expected thesis length and institutional structure specified in the proposal.

Do not fill pages with repetitive or unverifiable technical descriptions merely to satisfy the page count.

## Deliverables

- Complete technical documentation.
- Updated thesis manuscript.
- Verified references.
- Experiment appendices.
- Mermaid diagram sources and rendered figures.
- Deployment instructions.
- Final compliance and evidence report.

## Acceptance Criteria

- All six research objectives are addressed explicitly.
- Each completed objective has verifiable evidence.
- Outstanding requirements are disclosed.
- The manuscript does not contain fabricated findings.
- Deployment and core workflows have been validated.
- The final report is consistent with the source code and experiments.

---

# 4. AGENT WORKING PROTOCOL

The agent must maintain the following files throughout execution:

`docs/project/PROGRESS.md`

Contains the current phase, completed tasks, open issues, blockers, and next steps.

`docs/project/DECISION_LOG.md`

Contains significant technical and methodological decisions, evidence, and alternatives.

`docs/project/EVIDENCE_REGISTER.md`

Maps every completed requirement to source files, tests, experiment outputs, and supporting references.

`docs/project/ACCEPTANCE_TRACKER.md`

Contains the status of every phase and acceptance criterion.

`docs/project/FINAL_HANDOFF.md`

Contains a reproducible summary of the final architecture, implementation, experiment outcomes, remaining limitations, and handoff instructions.

At the end of each phase:

1. Run the appropriate tests.
2. Examine the actual results.
3. Update the acceptance tracker.
4. Record evidence references.
5. Repair failures within the authorized scope.
6. Rerun failed validation.
7. Document unresolved blockers.
8. Continue to the next independent task.

Do not claim that a test passed when it was not executed.

Do not silently change evaluation requirements to make an implementation appear successful.

Do not overwrite the existing project data or destroy historical experiments.

Use focused, reviewable commits where repository permissions allow.

---

# 5. PRIORITIZATION RULES

Use the following priority ordering:

**P0 — Critical correctness and research validity**

Broken integration contracts, invalid POI records, incorrect geographic calculations, corrupted data, unsupported scientific claims, non-reproducible core experiments, and missing fundamental thesis objectives.

**P1 — Core implementation**

Reliable data acquisition, knowledge graph integration, functioning agent workflows, routing, and memory mechanisms necessary for the thesis.

**P2 — Experimental completion**

Benchmark refinement, literature synthesis, comparative evaluation, user-study preparation and analysis, and adversarial evaluation.

**P3 — Optional improvements**

Broader geographic coverage, additional source adapters, expensive extraction methods, production scaling, and features not required by the thesis.

Never prioritize collecting a large number of POIs over ensuring that the collected records are correct and usable.

Do not delay essential thesis validation indefinitely to pursue optional improvements.

---

# 6. FINAL SUB-GOAL LIST

The mission consists of the following mandatory sub-goals.

- [ ] SG01 — Audit the repository and verify the actual system implementation.
- [ ] SG02 — Map all thesis requirements MT1–MT6 and RQ1–RQ4 to technical and research deliverables.
- [ ] SG03 — Research suitable and authorized POI data acquisition sources.
- [ ] SG04 — Design an extensible acquisition architecture compatible with `crawler_service`.
- [ ] SG05 — Implement and test source collection and structured extraction.
- [ ] SG06 — Implement POI normalization, classification, geographic resolution, provenance, and deduplication.
- [ ] SG07 — Integrate verified POIs into the existing knowledge graph.
- [ ] SG08 — Validate graph schema, ingestion correctness, and NEAR_BY calculations.
- [ ] SG09 — Verify and complete MCP, Intent Router, ReAct, and Graph RAG functionality.
- [ ] SG10 — Verify the hybrid planning pipeline and GraphHopper integration.
- [ ] SG11 — Verify and evaluate working memory and long-term memory.
- [ ] SG12 — Complete the literature review with at least 12 verified relevant publications.
- [ ] SG13 — Design and execute the four thesis experiments.
- [ ] SG14 — Execute all three adversarial evaluation families.
- [ ] SG15 — Prepare and conduct the required real-user study when participants are available and authorized.
- [ ] SG16 — Verify system deployment and end-to-end workflows.
- [ ] SG17 — Complete and revise Chapters 1–5 and supporting appendices.
- [ ] SG18 — Verify all references, quantitative results, research claims, and thesis requirements.
- [ ] SG19 — Produce the final system handoff and evidence register.

---

# 7. GLOBAL ACCEPTANCE CRITERIA

The overall mission can be marked `COMPLETE` only when all mandatory criteria below are satisfied.

**AC01 — Architecture:** The actual implementation has been audited, documented, and verified.

**AC02 — Acquisition:** At least two complementary authorized source families have functioning acquisition implementations, and collected records retain provenance.

**AC03 — POI Quality:** Imported POIs satisfy schema and geographic requirements. Ambiguous records are reviewed or quarantined rather than silently accepted.

**AC04 — Graph Integration:** Ingestion and graph relationships work, duplicate writes are controlled, and spatial consistency is tested.

**AC05 — Agent Functionality:** The existing core MCP, ReAct, Graph RAG, memory, and itinerary workflows operate end to end.

**AC06 — Literature:** At least 12 relevant scholarly publications have been verified and critically reviewed.

**AC07 — Experimental Validity:** All four required experiment families have reproducible methods and recorded outcomes. The user-study requirement is satisfied only by actual voluntary participant data.

**AC08 — Adversarial Evaluation:** All three prescribed categories have been tested, with failures explicitly recorded.

**AC09 — Traceability:** Every thesis objective and major quantitative claim maps to inspectable evidence.

**AC10 — Documentation:** The completed thesis, technical documentation, diagrams, experiment results, and handoff materials are consistent.

**AC11 — Integrity:** No fabricated results, citations, runtime claims, or simulated human responses are presented as genuine evidence.

**AC12 — Scope Control:** The implemented solution remains aligned with the approved thesis and preserves the distinction between the original proof-of-concept dataset and any expanded dataset.

---

# 8. MANDATORY VERIFICATION LOOP

For every sub-goal:

`Inspect → Research → Design → Implement → Test → Evaluate → Document → Review`

If the acceptance criteria are not satisfied, repeat the appropriate stages after diagnosing the failure.

Continue until every sub-goal reaches one of these explicit states:

- `VERIFIED`: completed and supported by evidence.
- `BLOCKED`: cannot be completed without a specific external dependency or human action.
- `FAILED`: attempted but acceptance criteria remain unsatisfied, with diagnostic evidence.

`BLOCKED` and `FAILED` must never be presented as `COMPLETE`.

The agent must not stop merely after generating a plan, producing architectural documents, or writing implementation code.

It must perform available verification and complete all feasible independent tasks.

If execution constraints prevent full completion, generate a precise handoff identifying what remains, why it remains, the evidence gathered, and the next concrete actions. Do not conceal incomplete work.

---

# 9. INITIAL EXECUTION INSTRUCTION

Begin immediately with PHASE 0.

Read both supplied documents and inspect the existing repository.

Produce the system inventory, thesis gap matrix, and prioritized implementation roadmap before making major architectural changes.

After the audit, proceed to the highest-priority unblocked work.

Do not request confirmation for ordinary implementation details that can be determined from existing code, tests, documentation, or reliable research.

Request authorization only when necessary for external accounts, purchases, irreversible actions, meaningful scope changes, sensitive data, or human-subject research.

The final objective is a **functional, evidence-verified Travel AI system and an academically defensible graduation thesis**, not merely a convincing demonstration.
