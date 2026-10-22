> New controlling direction: use FOUR_PHASE_PLAN.md and the Vietnamese interactive overview at ../reports/2026-10-18/index.html. Jev replaces the planned local intent classifier; not implemented yet. After phase4 wait for the user decision on H1 or thesis writing. This supersedes older autonomous continuation wording below.

# Travel AI progress report — 18 October 2026

Overall status: **active and incomplete**. Engineering foundations and the working thesis draft are established. Full application integration, primary experiments, the participant study and the final thesis remain unfinished. No defensible overall completion percentage is available.

## Independently verified work

- Audited the architecture, service gaps and thesis requirements; recorded the MT/RQ mapping, source-policy research and a literature matrix of 12 primary papers. Lost proposal wording is reconstructed from legacy material and is not presented as verbatim recovery.
- Preserved and audited the supplied POI file: **6,368 raw Point features**, producing **6,367 prepared candidates** after one exact feature duplicate. Stable internal IDs, category catalog, lineage, duplicate ledger and revision chronology are validated. These counts do not establish unique venues or accepted graph nodes.
- Accepted the bounded provenance foundation: all 6,367 candidates bind to their source evidence, all 6,368 input indices are accounted for, corrupt or mismatched evidence fails closed, and compact AI projections avoid copying the full raw record. Source labels are not promoted to verified current administrative areas.
- Corrected and tested backend readiness, storage/authentication isolation, ingestion identity, memory isolation, grounding, planner constraints, experiment collection and evaluation. Most of this evidence is offline or mocked; test milestones overlap and must not be added together.
- Verified a real native Memgraph engine from Windows, actual repository read queries and rollback-only application writes. The revised spatial expression was independently exercised on **1,113 real-engine cases**, with **zero false negatives and zero Python/Cypher mismatches**. Full relationship creation still requires the post-configuration application check.
- Produced and visually reviewed every page of a **33-page working thesis draft**, including figures and native equations. It is not the requested final 60–70-page thesis.
- Preserved the experiment protocol amendment before primary runs. One synthetic engineering scenario completed both model arms; it is not a primary H2/H3 result.

## Latest implementation deliveries — awaiting independent acceptance

All five previously active CLI jobs have now returned exit code 0. That establishes termination, not correctness or acceptance.

| Delivery | Current state | Next acceptance check |
|---|---|---|
| OC040 R1: opt-in model adapter | Corrective implementation delivered; executor reports 351 overlapping offline checks | Independently probe cancellation/capacity, nested tool schemas and applied settings, then bounded live checks |
| OC043: graph-ready primary snapshot | Versioned 6,367-record candidate output generated | Verify all hashes, field preservation, real-input binding and rejection behavior |
| OC045: source-snapshot discovery/retrieval | Server portion delivered, offline only | Real-engine qualification tests; then connect explicit selection to AI/planner |
| OC042: native GraphHopper | Executor reports Windows health and four car/foot routes, plus restart checks | Independently verify ownership, raw responses, endpoint access and application integration |
| OC046: relationship-property configuration | Explicit edge-property flag added to native runtime and both Compose commands | Independently inspect the change and rerun the genuine application rollback canary |

The earlier spatial rollback canary failed because relationship properties were disabled. Its failed evidence is retained. OC046 reports a fresh owned store and enabled configuration; this does not retroactively turn the failed canary into a pass.

## Prioritized remaining backlog

1. **Complete independent acceptance of the five deliveries.** Correct defects before building on them. Record the true OpenCode session IDs; OC040/OC043 reports currently use the platform chat UUID in place of executor identity.
2. **Finish real graph integration.** Pass the post-configuration application canary, validate source-qualified reads and spatial lifecycle, then perform and verify the full primary import, idempotency, persistence and concurrency. Full import has not been accepted.
3. **Finish actual AI and routing integration.** Retain the user's selected snapshot/area through routing, grounding and planning; verify real car/foot facts and the complete service flow. Native engine checks do not establish Docker deployment. Docker remains unresolved at the last verified check.
4. **Resolve data acceptance gaps.** Review current administrative boundaries, source/license/freshness and missing visit facts. The separate 32-record OSM/Wikidata expansion remains quarantined with zero accepted records. Preserve unknowns and separate real/synthetic scopes.
5. **Run the primary experiments.** Freeze and independently review the 20 paired H2 cases; run the five-profile/three-condition memory evaluation, adversarial cases and system checks. Capture all failures, matched model settings and complete or explicitly bounded usage. Auxiliary CLI costs remain unresolved; no total-token savings conclusion is justified yet.
6. **Run H1 when participants become available.** The requirement is 10–15 real consenting participants; none are currently available. Synthetic profiles cannot replace this study. Other work can continue.
7. **Finish the thesis and final audit.** Incorporate verified results, reconcile stale appendix/model labels, complete the 60–70-page manuscript, check citations and render/review every page. Audit every SG01–SG19 and AC01–AC12 requirement before declaring completion.

## Standing decisions and continuation

Use exactly **`aibox/ds/deepseek-flash`**, identified as **DeepSeek V4.1 Flash by the user**. Never use an explicitly named V4.0 route. Preserve historical raw labels and distinguish user confirmation from independent upstream attestation. Production Gemini remains the default; the CLI alternative is opt-in.

Continue all unfinished requirements autonomously. Write a dated checkpoint after every major task or critical phase and update `NEXT_SESSION_HANDOFF.md` and the applicable trackers. Never manufacture participant responses, measured results, venue verification or deployment evidence.

Detailed continuity: `NEXT_SESSION_HANDOFF.md`; complete work inventory: `BACKLOG.md`; current checkpoint: `checkpoints/2026-10-18-progress-and-review-queue.md`.
