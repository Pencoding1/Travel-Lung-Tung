## Readiness update — 2026-10-19 (no primary observations)

CORE084 fixed the current-prompt clipping bug; EXP086 collector/source-binding QA is accepted offline. Native short-term CORE085 and native two-tier CORE087 each delivered a typed two-stop car plan on the same accepted main.py (d866c52f…). CORE087 proves history/full expected profile/current schema and fixture-credential absence; these are bounded engineering readiness observations, not matched H3 cells, human responses or evidence of preference effects. Earlier failed/partial runs and their unknown causes remain preserved.

The earlier CORE079/EXP078 “plan only/unproven memory” notices below describe their dated pre-run state and are superseded for current readiness by the accepted CORE084/085/087 receipts. Version5 typed scoring, source/paired controls, denominators and hypothesis endpoints are unchanged. **Primary execution remains closed until full source/data/configuration/runtime freeze is reviewed** (FREEZE088). No primary H2/H3 observation exists; no new smoke loop or retroactive criterion change is authorized by this update.

## Version 5 amendment — typed H3 scoring; execution hold remains (2026-10-18)

Codex authored this change before any primary H2/H3 observations. Version4 below is historical proposed design and is superseded for H3 scoring by `docs/project/handoffs/EXP-080/parent-h3-typed-execution-design.json`; its exact pre-amendment bytes are retained in EXP080/before-typed-amendment-EXPERIMENT_PROTOCOL.md. CORE079 native engineering evidence is partial: only disabled-memory typed scoring passed; subsequent short-term preparation returned HTTP503, so active-memory native acceptance is unproven. Do not relabel that engineering run as H3 or infer quota/auth cause from503 alone.

Primary cells use actual POST `/chat` preparation followed by POST `/generate_itinerary` scoring with the same authenticated owner/session/source. `/chat` is not a typed-plan endpoint. The common typed body fixes November1,2026,09:00–16:00+07,one day,three stops,45-minute authored visits,one traveler,car,relaxed pace,unknown budget and the same1483-record qualified source universe. Only session identity and the declared memory condition vary outside the profile-specific preparation. No venue price/hours is fabricated. Require both `grounding.source_scope` and `planning.request_constraints.source_scope`; extract selected IDs and timestamps only from actual repaired schedule.

The15 preparations +15 typed scoring requests +max3 lifecycle chats are at most33 model-generating API requests, not33 calls to `/chat`. Retain165 known CLI-attempt cap, zero retries/best-of/paid fallback, partial usage and all failure/missing cells. Lifecycle chats remain separate correctness observations. Five synthetic profile effects are descriptive; no H1/powered significance or total-token-saving claim. H2 controls/frozen inputs are unchanged.

**Execution remains closed:** complete collector source QA, active-memory native proof and reviewed full execution freeze before any primary call. New CORE079 baseline is recorded separately in EXP080; never overwrite the older EXP078 baseline or disable its source mismatch checks. This amendment is not a frozen manifest, successful experiment or permission to rerun the consumed exact-once pilot.

---

# Experimental protocol — Travel AI



Version 4, 2026-10-18, before primary runs. Version3 before native H3 design is preserved in EXPERIMENT_PROTOCOL.v3-before-h3-native-design.md. Version2 retained in EXPERIMENT_PROTOCOL.v2-20261017-before-primary-freeze.md. The user-expanded primary snapshot and qualified source-area scope supersede the historical dataset paragraph; version1 is preserved in EXPERIMENT_PROTOCOL.v1-20261015.md. No primary H2/H3 or human-study run has been executed at this amendment. Protocol prepared before the proposed primary experimental runs. This is not a results report or a public preregistration. Existing historical thesis numbers are unverified; synthetic engineering benchmarks must never replace original-dataset experiments.



## Shared controls and evidence



Freeze a manifest containing Git revision plus dirty diff hash, interpreter/package lock, model/provider exact identifier, parameters, prompt hash, dataset/route snapshot hashes, scenario IDs, hardware/OS and execution timestamp. Record all failures, retries, wall time and usage. Never silently drop failed cases or count a malformed response only after a successful retry. Use identical candidate records, information fields, request constraints and model version for paired conditions. Keep personal data separate from public evidence.



Primary dataset: the user-supplied expanded GeoJSON, unchanged at `data/primary_20261016/hcm_pois_final.geojson`, 6368Pointfeatures/2712731bytes/SHA256`713b07a62cf89bd2cad9093abaad2a4c5f01e23853321764b3d66bf9f7eee43c`. The reviewed preparation retains6367candidates after one exact-feature duplicate, with6368sourceindices conserved and14closedsourcecategories. Candidate count is not accepted graph-node count or verified unique-venue count. Freeze the eventual accepted graph manifest separately, retain all exclusions/rejections, and state the experiment's actual candidate universe. The old approximately200-record description is historical and is not an outstanding recovery dependency. Separate32OSM/Wikidata expansion candidates remain outside primary results unless an explicitly labelled secondary study is declared.



Primary administrative selection uses an explicitly selected, frozen **source snapshot and qualified source area**, not a claim that raw labels are current City/District containment. Bind namespace/inputhash/sourceareaidentifier and candidate evidence throughout retrieval, grounding and planning; reject mismatched/conflicting current/source selections. Use the same declared mode in both arms. The model may not silently change the selected area. A current-jurisdiction request without verified current mapping must remain unknown/refused; do not improve an experiment by promoting source labels to verified current boundaries.



Raw sourceURL/license/collectiontime/freshness and all prices are unknown in the supplied snapshot; only1055rawhoursfields are nonblank. Preserve those unknowns. Any later official-source enrichment is a separately reviewed, dated, hashed fact overlay with exact POI-ID/source-feature/entity/field binding, not a retrospective change to raw/prepared-v1 data. Both arms receive precisely the same overlay. Source publication/retrieval times and museum ticket eligibility/tax/party assumptions must be explicit; retrieval today does not prove the fact was effective on every experiment date. Conflicting or contaminated source pages remain review-only. Do not infer zero prices, opening intervals or visit durations from missing values. User-authored visit lengths/arrival deadlines are scenario parameters, not measured venue facts. Sparse-data/refusal scenarios remain required, but cannot replace all ordinary feasible-plan scenarios merely to make evaluation easier.



Current explicitly selected experimental/application route: `opencode-go/deepseek-v4.1-flash`, using the accepted production OpenCodeCliProvider.complete V2 transport. Coding executor route `aibox/ds/deepseek-flash` is separate, user-confirmed V4.1, and is not silently used for experimental calls. This supersedes the previous experimental AI-box/Gemini-default wording. Never use an explicitly V4.0 route. Preserve exact assistant text, observed model/provider/session identity and normalized provider receipts; raw config, credentials, reasoning and unrelated session exports must not be persisted. The provider validates its exact session export in RAM; derived metadata is labelled as derived rather than raw export. An alias/version string does not independently attest an upstream checkpoint. Paired settings must be applied and observable, not silently ignored; unsupported settings are declared rather than guessed. Record CLI/provider/adapter versions and configuration hashes. Before H3 inference, account for all application model stages/retries/profile/summary calls and resolve or explicitly bound CLI auxiliary model-call costs; assistant-only export usage is not proof of all provider cost. Unresolved coverage prohibits a total-token-savings conclusion, while measured components can still be reported as partial evidence.



Every run produces machine-readable input, candidate IDs, output, tool trace, validation decisions, latency, retries and errors. Compare means/medians with counts and dispersion; report paired effects and uncertainty. Hypothesis rejection is valid. No headline improvement is required for acceptance.



## E1 — Tools, transparency and perceived trust (MT3/RQ1/H1)



System portion: exercise intent routing, no-tool chat, successful multi-tool task, ambiguous geography, empty data and tool failure. Measure route correctness against manually labelled expectations, tool success/failure, number of calls, latency and provenance coverage. An observable tool trace establishes inspectability, not trust.



Human portion: use HUMAN_STUDY_PROTOCOL.md. Compare identical answer content with and without execution trace, counterbalancing condition order across10–15 consenting participants. Do not compare two independently generated answers: content quality would confound trace visibility. Record actual participant count and missing responses. The study is blocked until recruitment/consent and executed stimuli exist; no simulated participant can satisfy H1.



## E2 — NEAR_BY correctness and measured pruning (MT2/RQ2)



Freeze coordinates, radius and distance implementation. Test radii1/3/5km; the thesis primary comparison uses the declared radius3km. Exhaustive unordered reference pairs number N(N−1)/2 for a whole dataset; an anchored area experiment uses its explicitly enumerated incident-pair universe and declares whether it is a qualified source area or a verified current district. Do not compare unordered pair counts against N² without explaining denominator differences.



For each radius record total potential pairs, prefilter candidates, exact-distance evaluations, accepted pairs, false negatives and false positives relative to exhaustive final distance. Reduction=(1−candidate_count/potential_pairs)×100; undefined when denominator0. Compare edge sets rather than counts alone. Acceptance requires zero missed reference neighbours, including cross-district, poles, dateline, identical coordinates and either internal-ID order. Unit Haversine evidence and live Memgraph point.distance evidence are distinct.



Measure end-to-end graph latency separately from Python synthetic timing. Use five measured repetitions after one labelled warm-up, store each value, report median/range, include hardware and query/index details. Record spatial edge direction/retrieval semantics, duplicate/self edges, stale edges after moving a POI and transactional rebuild policy. Never mutate original graph before snapshot. O(n²) candidate enumeration remains quadratic even when exact-distance calls fall.



## E3 — Hybrid itinerary versus LLM-only (MT4/RQ3/H2)



Freeze at least20 scenarios before scoring. Suggested factorial: durations1/2 days × budget2 levels × pace2 levels × constraint profiles{unrestricted, early closing, long transfer, meal timing, scarce candidates}, then choose20 balanced cases with documented selection. Include feasible and deliberately infeasible cases; feasibility must be independently reviewed from the snapshot, not assumed from successful solver output. Sparse/missing facts are recorded as unverifiable constraints.



Both conditions receive identical POI evidence, route matrix, duration/budget/party constraints and exact model/settings. LLM-only selects/schedules without algorithmic repair. Hybrid uses deterministic validation and disclosed bounded heuristics. Record initial proposal and repairs separately. Three runs per scenario/condition when model access permits; preserve each response, do not select the best. Use same seed if supported and log when unavailable. Include all model and tool calls in cost and latency.



Primary: proportion of scenarios with at least one verified temporal violation. Count arrival before feasible transfer, overlapping visits and known opening-window violations using one independent validator. Report missing-hours cases separately; absence of evidence is not compliance. An infeasibility refusal is not a valid delivered plan; report refusal and delivery rates alongside violation rates to prevent refusing everything from appearing optimal. Report POI-ID grounding, budget deviation only where comparable source prices/currency/party assumptions exist, route distance/time, preference coverage and total usage as secondary outcomes.



For paired binary scenario outcomes report discordant counts and exact McNemar test; for repeated runs aggregate within scenario first or use a clustered analysis, never treat repeated runs as independent scenarios. Report paired effect and scenario-bootstrap95% interval with fixed resampling seed. H2 significance uses two-sided alpha.05, with effect direction reported; no test until actual data exist. Keep repair failures in denominator. Report compute and context overhead, not just final call tokens.



### Pre-run input design and missing-fact controls (18/10/2026)



Codex design EXP076 defines20 requests P01–P20: five constraint profiles × four variants, with ten cases at each marginal level of day count (1/2), budget (300000/1000000 VND per party), pace (45/30 authored minutes per visit), and mode (car/foot). These are purposively selected combinations, not a full factorial design; do not infer isolated effects of mode, pace or budget. Eight source POIs with supported hours and112 actual directed GraphHopper edges form the main pool. A ninth exact source POI with absent hours appears only as a singleton, requiring no invented route. The empty selected-pool case is an authored stress test, not evidence the full city/source has no candidates.



Known source category IDs must be used exactly: the gifts candidate is `apparel_and_gifts`, not an invented `gifts` alias. The initial Codex design correction is retained in EXP076/parent-design-correction-1.json. Selection, source-string hours and route snapshot are frozen before any model scoring. Dates are authored counterfactual itinerary dates (1–2 November2026); projecting source daily strings onto them is not independent verification that a venue opens then. All prices remain null. No budget improvement or global-plan feasibility can be established without price evidence.



Independent finite-state review, without importing the production scheduler/validator, must retain witnesses for feasible source-relative timing and complete dominance-state exhaustion for impossible request constraints. This is input review, not model performance. Multi-day convention follows the existing production contract (decision008): carry the previous last POI as the next day origin, preserve it through empty days and charge its directed inbound route after the new day start. This is not a hotel/accommodation or traffic model; the actual matrix supplies each leg. An initial independent-daily-origin assumption in Codex review was corrected before scoring and retained in EXP076/parent-design-correction-2.json.



The existing H2 exporter conservatively treats any unknown fact, including price, as incomplete temporal absence evidence. Keep its original fields and all-case denominator: a known violation remains observable; a non-violation accompanied by unknown facts stays inconclusive in that output. Do not silently map null to false or promote global feasibility. The planned timing-only companion exp077.temporal.v1 supplies the E3 temporal endpoint after independent QA/code freeze; it excludes only exact cost_unknown reasons for known source/selected IDs from time uncertainty. It reuses the existing validator report, preserves unknown hours/routes/structural uncertainty and known bad timing, and is reported beside the original conservative global endpoint. Its code/rules must be frozen before the first primary call. Temporal absence is not global feasibility, budget compliance or venue freshness. No post-result criterion change is permitted to obtain significance.



The planned repetition count is3 per scenario/condition (120 reserved H2 observations). Use one fixed order, max_attempts1 and no best-of selection. Partial/quota/timeout runs retain the full planned denominator and can resume only unattempted keys under the identical fingerprint. Provider controls/seed that are not supported or observed remain unset/unknown for both arms; the scenario seed is not claimed to control provider sampling. Unknown auxiliary usage prohibits total-cost/token-savings conclusions.



## E4 — Two-tier memory and personalization (MT5/RQ4/H3)



Use five declared synthetic profiles with distinct preferred categories and the same fixed requests/candidate dataset. Profiles are fixtures, not human participants. Conditions: memory disabled, short-term history only, short-term plus persisted long-term profile. Include at least one preference update, contradiction, deletion, session restart and unknown preference. User identity/session isolation is a mandatory correctness test.



Preferred share=number of selected stops whose explicit category intersects active preferred category IDs / number of selected stops; report undefined for empty plans, never zero success. Compare within profile and scenario. Report all five profile effects, not only pooled positive cases. Separately report constraint validity so preferences cannot improve by invalid scheduling. Evaluate retrieval correctness and stale-preference use against authored fixture truth.



Token reduction=(baseline total tokens−memory-condition total tokens)/baseline total tokens. Include summary creation/updates, profile extraction, retrieval prompts and final response; persist provider usage when available. Character/whitespace counts are proxies labelled as such and cannot support provider-token savings. Report cold-session and amortized multi-session costs separately. Fixed reduction targets from historical prose are hypotheses only.



### Planned native H3 implementation, before any primary calls

The definitive execution design is EXP078/parent-h3-execution-design.json; it remains unaccepted/unfrozen until code QA. It uses the actual native `/chat` API and production memory, retrieval, planner and provider. The five profiles are synthetic fixture preferences; authenticated subjects use a temporary test issuer and isolated SQLite. This does not verify a deployed identity provider or autonomous preference extraction/grow-with-user.

The fixed candidate universe is all1483 prepared records in the qualified HCMC/Quan1 source area. The earlier8candidate profile draft was unfrozen and is not the native study universe. Five active categories have271coffee/266restaurant/97specialty_food/99entertainment/74apparel_and_gifts source records. These are source categories, not independently current venue facts. Freeze category truth and the exact source selector/hash. Production retrieval is unchanged: tool/model-exposed subsets may differ as part of the memory intervention. Common candidate_id/route_id/prompt_information_id bind the source universe, road-map/routing policy and base request; they must not be described as byte-identical actual model exposures or identical selected route legs. Actual retrieved IDs, source evidence and routes are retained separately. Interpret effects as end-to-end memory-configuration effects, not storage alone. H2's stricter identical paired-facts rule remains unchanged.

There are15primary cells (five profiles × three conditions × one repetition). Rotate condition order by profile. Each condition has a fresh authenticated subject/session: disabled bypasses both memories; short-term has an actual preparation conversation but no durable profile; two-tier has the same preparation plus an explicitly supplied persistent profile through the real CRUD API. Same prep template includes both the Vietnamese category label and exact active source category ID across conditions; the same generic scoring request/date/window/car mode/source selector explicitly states relaxed pace. Thus the durable profile adds no previously unavailable category specificity or pace; retained context/representation is the memory intervention. Run prep immediately before scoring. Count all15preparation and15scoring requests in stage cost/latency accounting; failed setup is not fabricated history or a dropped scoring cell.

After primary cells, at most3actual chats test M1two-tier preference update/contradiction, owned-service restart with durable updated profile and cleared short history, and explicit deletion/clear with unknown preference. Keep these correctness checks separate from15primary preferred-share outcomes; unknown preference is not zero-success personalization. Maximum33chat requests,165known CLI attempts,33Jev requests, no retries/best-of or paid fallback. Reserve request attempts before sending; quota/auth/provider failure leaves full planned denominator and unattempted rows explicit. An interrupted run without its RAM issuer is a new declared batch if restarted, never replacement of failed observations.

Use actual repaired_schedule IDs/timestamps and source category truth, not prose extraction or another model to recover a plan. Missing structured plan/unknown ID/unproven identity remains nondelivery/unknown. Measure input context with safe exact-session export flags in RAM only; persist no raw transport export/config/reasoning/auth secret. Partial observed usage does not establish total billing or token reduction; include setup and lifecycle components explicitly and report the missing coverage. Five profile effects are descriptive, not a participant sample or powered significance result.

## Adversarial suite (MT6)



A: no candidates/all enrichment failed — explicit insufficient data and no invented stops. B: unknown ID or unsupported name/address/price/hours/description — reject or reconstruct from source, with unknown fields explicit. C: out-of-scope/ambiguous district, wrong parent city and partial-name collision — fail closed before synthesis. Run mocked boundary tests now; repeat against live tools, deployed HTTP and the configured real model later. Report these evidence levels separately.



## Completion gate



Required outputs: frozen scenario/profile manifests; executable independent validators; raw logs and summaries; method/limitation narrative; human responses with consent accounting; bibliography and MT/RQ traceability. Current status: protocol AMENDED BEFORE PRIMARY RUNS. S1–S5 native readiness and the V2 collector have bounded Codex acceptance (DATA068/CORE069–071/MEM072R1/EXP074); actual graph6367POI, real car/foot routes and existing-memory isolation/restart proof are available. Scenario/profile execution manifests, independent source-binding review and code/data/config freeze remain unfinished. H2/H3 primary outcomes do not yet exist; H1 has no participants. Historical synthetic runs are separate engineering evidence. Phase5 mechanisms and H1/thesis-writing must follow the user's phase gates.



### Execution hold discovered before primary calls —18/10/2026, Codex

The planned native H3 `/chat` scoring contract is not implemented: source audit EXP078/parent-native-api-contract-audit.json proves `/chat` does not return `planning.repaired_schedule`, while `/generate_itinerary` returns typed schedules but currently does not read WORKING_MEMORY. This was an incorrect assumption in the Codex-authored EXP078 plan, not evidence of H3 outcomes. No primary H2/H3 calls have occurred. Actual H3 execution is prohibited until the missing existing-memory/typed-itinerary integration is implemented and independently accepted, the scoring endpoint/common typed controls are amended explicitly before the first primary call, the collector is adapted and code/config/source bindings are freshly frozen. CORE079/prepared-plan.md is a plan only, not delivered behavior. Do not substitute retrieved source_evidence_ids for selected stops, parse prose to invent a plan, mutate frozen H2 inputs, or call fake-backend success native evidence. Current version4 wording above is preserved as the proposed pre-run design; this notice closes its execution gate and does not declare a revised study frozen.
