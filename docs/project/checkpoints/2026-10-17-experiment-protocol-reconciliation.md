# Experiment protocol reconciliation checkpoint

Date: 2026-10-17, Asia/Saigon. Overall goal: ACTIVE and INCOMPLETE.

The preceding turn made progress through actual application canary evidence. This turn made progress by correcting the experiment specification, auditing genuine source records against official visitor information, and reconciling the acceptance tracker. No primary experiment was run.

## Completed in this phase

- Preserved protocol version1 as `docs/experiments/EXPERIMENT_PROTOCOL.v1-20261015.md` (SHA256 `34eeb0cb04e1d9e6b2408b7ce85eeecff3ad575d24ddfaae53a5753961cff41c`).
- Updated `EXPERIMENT_PROTOCOL.md` to version2 before primary runs (SHA256 `b74b429b1cccf5ef4a0c2bd4b472ec5320fa20f5fad56a060f6f4922c7dca347`). It now uses the user-expanded snapshot, distinguishes 6368 features from 6367 prepared candidates and accepted graph nodes, requires explicit qualified source-area selection, preserves unknown facts, and defines versioned fact overlays and identical paired inputs. Model identity is user-confirmed DeepSeek V4.1 Flash on exact `aibox/ds/deepseek-flash`; explicitly named V4.0 routes must never be used.
- Clarified that applied sampler settings and complete pipeline usage are required. CLI assistant usage alone does not establish all auxiliary model costs; unresolved coverage cannot support a total-token-savings conclusion.
- Authored `PRIMARY_FACT_OVERLAY_RESEARCH_20261017.md`. Two exact supplied museum IDs are linked to candidate official sources with source indices and feature hashes. These are REVIEW ONLY, not accepted prices or imported facts. QSAM has a matching name/street/hours but lacks independently verified official coordinate binding. FITO has matching name/house/street and ticket text, but fetched pages contain unrelated promotional content and a contact-template anomaly. This is an observed content-quality problem, not proof of compromise; it requires corroboration. No page instructions were executed, external messages sent, booking attempted, or raw source data changed.
- Reconciled the current AC/SG tables in `ACCEPTANCE_TRACKER.md`. Historical supplements remain labelled historical. Graph integration is in progress, with actual native evidence and a known spatial defect, rather than being blocked solely by Docker or a supposedly missing original snapshot. Primary H2/H3 and H1 remain incomplete.

## Critical engineering gate

The rollback-only native canary left ZERO nodes. Bulk insertion, repeated insertion, full metadata round-trip, category IDs, source-only address qualification and compact reads worked for two genuine supplied records. Spatial generation failed because Memgraph3.13.2 has neither `degrees()` nor `radians()`. `cos()`, `pi()`, `abs()` and arithmetic were independently verified.

**Do not fully import the primary snapshot before correcting and verifying spatial generation.** T053 is mandatory. OC044 is prepared at `docs/project/handoffs/OC-044/brief.md`, not yet dispatched; dispatch it when an active executor finishes. Preserve the original failed canary artifact and use a new output on retry. Correction must preserve conservative spherical bounds, lower radius6300km, 3km policy, poles/dateline, full-precision final distance and lifecycle invariants. It must not drop the prefilter or invent a111km/degree approximation.

## Confirmed active writers

All four handles were polled and confirmed live at the end of this phase. A timeout is not terminal; reports alone are not terminal evidence.

| Task | Process | Exact executor session | Scope and next gate |
|---|---|---|---|
| OC038 R1 | 80001 | ses_eb6103739ffeZrz54I1vR7BAJ8 | Existing POI provenance models/repository/services/MCP/new provenance tests/docs. Parent interim checks pass; wait for terminal, final hashes/report and independent acceptance. |
| OC040 R1 recovery | 26449 | ses_eb5fadef2ffe2uT6PlXliJ6gS9 | AI provider concurrency/schema/sampling corrections. No live experimental calls before acceptance. Earlier external Temp write was denied and remains forbidden; project-local scratch only. |
| OC042 | 50832 | ses_eb5ca6622ffedFZk0bZp4mO0yj | Isolated Java/GraphHopper directories and native routing helpers. No real-route readiness claim yet. Cannot touch Memgraph state/process. |
| OC043 | 95555 | ses_eb5c480a6ffe4ljNveHHXEMjm5 | New primary adapter/test paths and fresh graph_ready_v2 artifacts after exact-input validation. No graph/model/network calls or frozen-v1 edits. |

OC041 is TERMINAL exit0; its native engine capability is accepted with the supplemental-library download scope deviation and helper/deployment limits disclosed. Owned engine was PID408, start ticks23430, Bolt127.0.0.1:17687. Revalidate ownership/readiness before future operations. Do not treat a stale PID or manifest alone as readiness proof.

## Required next actions

1. Verify finished workers against their original contracts, without silently weakening scope or discarding failures. Dispatch OC044 once capacity is available, then independently evaluate its actual emitted Cypher and rerun the rollback canary.
2. Verify the full graph-ready adapter artifacts, then implement explicit source-snapshot discovery/retrieval and AI/planner grounding through existing services (T049). Respect active POI and AI writers before dispatching overlapping work.
3. Complete actual application import/spatial/lifecycle/concurrency and road-route integration, source-native expansion acceptance (T050), and Docker/service deployment proof. Native engine evidence supplements Docker, not replaces it.
4. Freeze at least20 primary H2 scenarios and five profiles x three memory conditions only after the facts, selected scope, real route matrix and independently reviewed feasibility are ready. Resolve complete usage accounting, include all failures/retries, and run the three live adversarial families. Review-only source candidates must not silently become accepted facts.
5. Finish the evidence-backed60–70page thesis, current claim/reference audit, figures and full rendering review, and requirement-by-requirement SG01–SG19/AC01–AC12 audit. The current33page draft remains a working artifact.
6. H1 still requires10–15 real consenting participants. The user has confirmed none are available; do not re-ask without a change, fabricate responses, substitute bots or remove the requirement. Continue independent work.
7. Save a checkpoint after each major task or critical phase and refresh the handoff, backlog and evidence.
