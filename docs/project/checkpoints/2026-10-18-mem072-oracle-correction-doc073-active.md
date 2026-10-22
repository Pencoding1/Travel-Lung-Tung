# Checkpoint — S5 test oracle corrected; S6 docs underway

Owner/planning/QA: **Codex**, 18/10/2026. Goal remains active/incomplete.

## What changed
- User authorized one execution of the exact original MEM072 command after Hermes guard stop. Original script SHAad8b811e… unchanged, executed via Codex normal host approval. No guard changes or command renaming.
- Result `handoffs/MEM-072/qa-work/results.json`: terminal1; missing/wrong/expired bearer checks pass, initial profile creation assertion fails. **0Go/0Jev**; owned runtime stopped in finally. No rerun performed.
- Root inspected actual validator/store and ran five offline SQLite checks: absent profile has `current_version=None`; `expected_version=0` rejects creation. Omitting version creates1, stale0 conflicts, expected1 updates2. This is a **Codex QA oracle mismatch**, not a proven application bug; initial native HTTP status/body was not collected, so don't invent it.
- Corrected test `parent_memory_readiness_r1.py`, SHA474ca0c4ea7ff53e883d7d8372d30dc46b38f7693a43b879c5f049275c1590f2, preserves originals and writes separate qa-work-r1. Adds whitelisted creation HTTP/version diagnostics; no app code or criteria weakening. Same4chat/20CLI/4Jev caps. **Prepared, unexecuted, new human approval pending.** Exact prior authorization consumed.
- DOC073 dispatched to OpenCode AIboxds/deepseek-flash, process56650, ownsession ses_eb14e4c27ffePW6pvoq7Kp83FW. Fixed Codex plan/9node architecture candidate in DOC073. Writes restricted report/diagram/canonical mirrors; no applicationcalls/runtimechanges/browserwork. Codex acceptance pending.

## Next
1. If explicit R1 authorization arrives: verify same hash, execute once, inspect exact result/cleanup. Otherwise retain S5pending and continue independent S6work. No automatic rerun or alternate executor.
2. Observe DOC073 existing process/session, don't relaunch on timeout. Independently check actual content, local refs, JS syntax, architecture topology and deterministic9check/delivery hashes. Old browser sidecars are historical; no new browser/perceptual proof.
3. Fix experiment result collection (actual arrival/departure, initial+repaired plans, route/model/usage/failures) through a bounded Codex plan/OpenCode task, then freeze realistic primarycases/protocol before phase3.
4. Preserve accepted DATA068/S1–S4 evidence; no new provider/fullgraph/foot/car proof just to restate. Phase5 crawler/growwithuser deferred; H1/thesis writing awaitphase4choice.
