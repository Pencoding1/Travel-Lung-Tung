# Experimental protocol — Travel AI

Version 1, 2026-10-15. Protocol prepared before the proposed experimental runs. This is not a results report or a public preregistration. Existing historical thesis numbers are unverified; synthetic engineering benchmarks must never replace original-dataset experiments.

## Shared controls and evidence

Freeze a manifest containing Git revision plus dirty diff hash, interpreter/package lock, model/provider exact identifier, parameters, prompt hash, dataset/route snapshot hashes, scenario IDs, hardware/OS and execution timestamp. Record all failures, retries, wall time and usage. Never silently drop failed cases or count a malformed response only after a successful retry. Use identical candidate records, information fields, request constraints and model version for paired conditions. Keep personal data separate from public evidence.

Primary dataset: original approximately200 POIs in Districts1/3, HCMC, subject to an actual snapshot inventory. Expansion records live in a separately named/versioned dataset and are excluded from primary results. Administrative names correspond to the frozen dataset, not an implicit claim about current administrative boundaries. If the original dataset cannot be recovered, report the reproduction blocked and label any substitute dataset explicitly.

Every run produces machine-readable input, candidate IDs, output, tool trace, validation decisions, latency, retries and errors. Compare means/medians with counts and dispersion; report paired effects and uncertainty. Hypothesis rejection is valid. No headline improvement is required for acceptance.

## E1 — Tools, transparency and perceived trust (MT3/RQ1/H1)

System portion: exercise intent routing, no-tool chat, successful multi-tool task, ambiguous geography, empty data and tool failure. Measure route correctness against manually labelled expectations, tool success/failure, number of calls, latency and provenance coverage. An observable tool trace establishes inspectability, not trust.

Human portion: use HUMAN_STUDY_PROTOCOL.md. Compare identical answer content with and without execution trace, counterbalancing condition order across10–15 consenting participants. Do not compare two independently generated answers: content quality would confound trace visibility. Record actual participant count and missing responses. The study is blocked until recruitment/consent and executed stimuli exist; no simulated participant can satisfy H1.

## E2 — NEAR_BY correctness and measured pruning (MT2/RQ2)

Freeze coordinates, radius and distance implementation. Test radii1/3/5km; the thesis primary comparison uses the declared radius3km. Exhaustive unordered reference pairs number N(N−1)/2 for a whole dataset; an anchored district experiment uses its explicitly enumerated incident-pair universe. Do not compare unordered pair counts against N² without explaining denominator differences.

For each radius record total potential pairs, prefilter candidates, exact-distance evaluations, accepted pairs, false negatives and false positives relative to exhaustive final distance. Reduction=(1−candidate_count/potential_pairs)×100; undefined when denominator0. Compare edge sets rather than counts alone. Acceptance requires zero missed reference neighbours, including cross-district, poles, dateline, identical coordinates and either internal-ID order. Unit Haversine evidence and live Memgraph point.distance evidence are distinct.

Measure end-to-end graph latency separately from Python synthetic timing. Use five measured repetitions after one labelled warm-up, store each value, report median/range, include hardware and query/index details. Record spatial edge direction/retrieval semantics, duplicate/self edges, stale edges after moving a POI and transactional rebuild policy. Never mutate original graph before snapshot. O(n²) candidate enumeration remains quadratic even when exact-distance calls fall.

## E3 — Hybrid itinerary versus LLM-only (MT4/RQ3/H2)

Freeze at least20 scenarios before scoring. Suggested factorial: durations1/2 days × budget2 levels × pace2 levels × constraint profiles{unrestricted, early closing, long transfer, meal timing, scarce candidates}, then choose20 balanced cases with documented selection. Include feasible and deliberately infeasible cases; feasibility must be independently reviewed from the snapshot, not assumed from successful solver output. Sparse/missing facts are recorded as unverifiable constraints.

Both conditions receive identical POI evidence, route matrix, duration/budget/party constraints and exact model/settings. LLM-only selects/schedules without algorithmic repair. Hybrid uses deterministic validation and disclosed bounded heuristics. Record initial proposal and repairs separately. Three runs per scenario/condition when model access permits; preserve each response, do not select the best. Use same seed if supported and log when unavailable. Include all model and tool calls in cost and latency.

Primary: proportion of scenarios with at least one verified temporal violation. Count arrival before feasible transfer, overlapping visits and known opening-window violations using one independent validator. Report missing-hours cases separately; absence of evidence is not compliance. An infeasibility refusal is not a valid delivered plan; report refusal and delivery rates alongside violation rates to prevent refusing everything from appearing optimal. Report POI-ID grounding, budget deviation only where comparable source prices/currency/party assumptions exist, route distance/time, preference coverage and total usage as secondary outcomes.

For paired binary scenario outcomes report discordant counts and exact McNemar test; for repeated runs aggregate within scenario first or use a clustered analysis, never treat repeated runs as independent scenarios. Report paired effect and scenario-bootstrap95% interval with fixed resampling seed. H2 significance uses two-sided alpha.05, with effect direction reported; no test until actual data exist. Keep repair failures in denominator. Report compute and context overhead, not just final call tokens.

## E4 — Two-tier memory and personalization (MT5/RQ4/H3)

Use five declared synthetic profiles with distinct preferred categories and the same fixed requests/candidate dataset. Profiles are fixtures, not human participants. Conditions: memory disabled, short-term history only, short-term plus persisted long-term profile. Include at least one preference update, contradiction, deletion, session restart and unknown preference. User identity/session isolation is a mandatory correctness test.

Preferred share=number of selected stops whose explicit category intersects active preferred category IDs / number of selected stops; report undefined for empty plans, never zero success. Compare within profile and scenario. Report all five profile effects, not only pooled positive cases. Separately report constraint validity so preferences cannot improve by invalid scheduling. Evaluate retrieval correctness and stale-preference use against authored fixture truth.

Token reduction=(baseline total tokens−memory-condition total tokens)/baseline total tokens. Include summary creation/updates, profile extraction, retrieval prompts and final response; persist provider usage when available. Character/whitespace counts are proxies labelled as such and cannot support provider-token savings. Report cold-session and amortized multi-session costs separately. Fixed reduction targets from historical prose are hypotheses only.

## Adversarial suite (MT6)

A: no candidates/all enrichment failed — explicit insufficient data and no invented stops. B: unknown ID or unsupported name/address/price/hours/description — reject or reconstruct from source, with unknown fields explicit. C: out-of-scope/ambiguous district, wrong parent city and partial-name collision — fail closed before synthesis. Run mocked boundary tests now; repeat against live tools, deployed HTTP and the configured real model later. Report these evidence levels separately.

## Completion gate

Required outputs: frozen scenario/profile manifests; executable independent validators; raw logs and summaries; method/limitation narrative; human responses with consent accounting; bibliography and MT/RQ traceability. Current status: protocol READY, runs NOT EXECUTED except separately labelled engineering tests. Runtime, original snapshot, configured model access and real participants remain dependencies.
