# Implementation roadmap

The audit reveals core correctness work before data expansion or scientific comparisons. Preserve service boundaries and historical data.

1. Establish isolated test runtime. Capture failing baseline tests for identity and geographic validation. Remove literal deployment credential and make tunneling opt-in; owner must rotate the previously exposed credential independently.
2. Preserve supplied POI IDs; reject invalid geographic inputs. Document non-destructive migration and rollback. Add conservative spatial filtering, direction/boundary tests and measured reference benchmarks; defer live graph claims until Docker is available.
3. Repair canary/background failure contracts, fresh transaction ownership and terminal SSE results. Test mixed-invalid batches, rejected writes and retries without external data changes.
4. Repair MCP category/geographic/route contracts; guard empty, ambiguous and out-of-scope candidates. Add output grounding and deterministic time/budget/route validation to the existing itinerary workflow.
5. Integrate two-tier memory with user isolation and explicit current-request precedence; complete essential itinerary persistence API only within thesis scope.
6. Research authorized sources, then implement shared acquisition contracts and two complementary adapters in crawler_service. Preserve provenance, uncertain facts and review decisions; do not bulk ingest before a graph snapshot and taxonomy review.
7. Prepare and freeze experiments: spatial comparisons, 20 planning scenarios, five memory profiles, router/tool traces, adversarial cases and genuine voluntary-study protocol. Verify at least 12 scholarly publications from primary sources in parallel with independent work.
8. When infrastructure is available, verify the full deployed workflow and execute model/routing baselines with raw outputs. Complete chapters and figures using actual results. Evaluate every global criterion and disclose remaining external blockers.

Dependencies and statuses are maintained in `docs/project/BACKLOG.md`. Passing isolated tests does not close deployment, graph integration, model evaluation or human-study requirements.
