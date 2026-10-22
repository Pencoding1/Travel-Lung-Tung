> **Chỉ đạo mới ngày 18/10/2026 — ưu tiên cao nhất:** Làm việc theo `FOUR_PHASE_PLAN.md`: (1) kiểm chứng, (2) hoàn thiện mã theo đề cương, (3) thí nghiệm, (4) báo cáo. Sau giai đoạn 4 chờ người dùng quyết định H1 hoặc viết tiếp luận văn; không tự tiếp tục hai phần đó. Codex lập kế hoạch/thiết kế QA/kiểm chứng, OpenCode `aibox/ds/deepseek-flash` thực hiện mã và báo cáo. Báo cáo tiếng Việt, ngắn, tương tác, có từng mô-đun; lưu checkpoint mỗi mốc lớn. Không mở nhiều gói việc dàn trải. OC047 đang được giao duy nhất phần báo cáo, không sửa mã sản phẩm.

# AUTONOMOUS BACKLOG MANAGEMENT & GOAL-DRIVEN EXECUTION

## 1. Autonomous Operating Mode

You are not merely executing a predefined task list.

You must autonomously discover, decompose, prioritize, execute, verify, and manage all tasks necessary to satisfy the Master Goal and its acceptance criteria.

The initial phases and sub-goals are requirements, not an exhaustive task list.

You are responsible for discovering additional work through repository inspection, research, implementation, testing, integration, and thesis requirement validation.

**Do not stop simply because the initial task list has been exhausted.**

Your execution must be driven by verified goal completion, not by the number of tasks performed.

## 2. Persistent Backlog

Maintain a persistent backlog at:

`docs/project/BACKLOG.md`

Each task must contain:

| Field | Description |
|---|---|
| Task ID | Unique and stable identifier |
| Title | Concise description |
| Parent Goal | Related SG, MT, RQ, or acceptance criterion |
| Origin | Audit, Research, Implementation, Test, or Review |
| Priority | P0 / P1 / P2 / P3 |
| Status | DISCOVERED / READY / IN_PROGRESS / BLOCKED / FAILED / VERIFIED |
| Dependencies | Prerequisite task IDs |
| Description | Scope and expected work |
| Acceptance Criteria | Objectively verifiable completion conditions |
| Evidence | Files, tests, logs, or experiment results |
| Blocker | Reason preventing execution, if applicable |

The backlog must persist across execution sessions.

Do not rely solely on conversation context or agent memory.

## 3. Loop A — Autonomous Task Discovery

At the beginning of execution and after each meaningful milestone:

1. Read the Master Goal, acceptance criteria, and existing backlog.
2. Inspect relevant repository modules, documentation, experiments, and current system behavior.
3. Identify gaps between actual state and expected outcomes.
4. Convert each actionable gap into a backlog item.
5. Associate each task with its parent goal.
6. Identify dependencies.
7. Assign priority and measurable acceptance criteria.
8. Deduplicate overlapping backlog items.
9. Update the backlog.

New findings may generate additional tasks even when they were not explicitly included in the initial instruction.

Example:

A crawler integration test reveals that Vietnamese POI names cannot be reliably resolved.

Create tasks for investigating name normalization, evaluating matching strategies, building a verification dataset, implementing entity resolution, and validating its quality.

However, **do not expand beyond the approved project scope** merely because additional improvements are technically possible.

## 4. Loop B — Autonomous Task Execution

Repeatedly perform the following procedure:

1. Load all tasks with status `READY`.
2. Filter tasks whose dependencies are satisfied.
3. Select the highest-priority actionable task.
4. Inspect the code and evidence relevant to that task.
5. Research unfamiliar technologies or unresolved technical questions as necessary.
6. Design the smallest appropriate solution.
7. Implement it.
8. Execute appropriate tests.
9. Compare the observed results with the task acceptance criteria.
10. If accepted, mark `VERIFIED` and register the evidence.
11. If rejected, diagnose the failure and create corrective subtasks.
12. Update dependent task statuses.
13. Return to task selection.

Never mark a task as `VERIFIED` based only on code generation or an unexecuted test.

## 5. Loop C — Autonomous System Verification

After completing a significant functional group or phase:

1. Run available integration and end-to-end tests.
2. Re-evaluate relevant system-level acceptance criteria.
3. Check whether previous implementations remain valid.
4. Detect regressions, broken contracts, data inconsistencies, and missing requirements.
5. Convert newly discovered problems into backlog tasks.
6. Recalculate the implementation and thesis completion status.
7. Return to Loop A if new work is required.

A phase may be reopened if later verification demonstrates that its acceptance criteria are no longer satisfied.

## 6. Dynamic Task Dependency Management

Maintain a dependency graph of backlog tasks.

A task becomes `READY` only when its prerequisites are verified and necessary permissions or resources are available.

If a task is blocked, record the reason and continue with other independent tasks.

Avoid circular dependencies.

If a dependency cycle is found, refactor task decomposition or document the architectural issue.

Do not attempt to solve a blocked task repeatedly without a meaningful change in conditions.

## 7. Scope and Priority Control

All discovered tasks must be classified as one of:

- `MANDATORY`: necessary for an approved goal or acceptance criterion.
- `SUPPORTING`: necessary to complete a mandatory task.
- `OPTIONAL`: improvement not required to complete the Master Goal.
- `OUT_OF_SCOPE`: unrelated to the approved goal.

Only `MANDATORY` and justified `SUPPORTING` tasks are automatically eligible for execution.

Record optional improvements separately without allowing them to delay essential completion.

Prioritize P0 correctness and validity issues before optional development.

## 8. Failure Handling and Retry Policy

For a failed task:

1. Capture the failure and supporting evidence.
2. Identify the likely root cause.
3. Determine whether a correction can be attempted safely.
4. Create corrective subtasks where necessary.
5. Retry only when a specific change or diagnostic hypothesis justifies it.
6. Escalate persistent failures as `BLOCKED` or `FAILED` with a clear explanation.

Never repeat the same failed operation indefinitely.

Introduce bounded retry counts for individual operations and investigate recurring failures rather than blindly retrying.

The overall execution loop may continue with independent work even when individual tasks are blocked.

## 9. Progress and Evidence Tracking

Keep these files synchronized:

- `BACKLOG.md`: current and discovered work.
- `PROGRESS.md`: current execution status.
- `ACCEPTANCE_TRACKER.md`: requirement-level completion.
- `EVIDENCE_REGISTER.md`: verified evidence.
- `DECISION_LOG.md`: engineering and research decisions.
- `FINAL_HANDOFF.md`: completion status and unresolved work.

Every verified task must include evidence.

Every incomplete mandatory task must have an explicit remaining action or blocker.

## 10. Completion Gate

After each system validation cycle, evaluate:

- Are all mandatory sub-goals satisfied?
- Are all global acceptance criteria verified?
- Are there any READY or IN_PROGRESS mandatory tasks?
- Are there unresolved failures affecting required functionality?
- Are there any unverified scientific claims?
- Have all changes passed relevant regression tests?
- Is the thesis requirement matrix consistent with actual evidence?

If any required condition fails, create or update the relevant backlog tasks and continue execution.

Declare `COMPLETE` only when the mandatory goals and acceptance criteria are evidence-verified.

If external dependencies prevent completion, declare `BLOCKED` or `PARTIALLY_COMPLETE` and produce a handoff. Never treat an empty actionable backlog as proof that all goals have been met.

## 11. Session Continuity

At the start of every new session:

1. Read the Master Goal.
2. Read `BACKLOG.md`, `PROGRESS.md`, and `ACCEPTANCE_TRACKER.md`.
3. Reconcile task statuses with actual repository state.
4. Identify the next unblocked high-priority task.
5. Resume execution.

At the end of every execution session, persist sufficient context for another agent to continue without relying on the previous conversation.

## 12. Mandatory Execution Directive

**You must operate as an autonomous, goal-driven research and implementation agent, continuously discovering and resolving tasks until the approved Master Goal is satisfied or all remaining mandatory work is explicitly blocked.**

Do not stop after planning.

Do not stop after implementation.

Do not stop after passing unit tests.

Do not stop after the initial backlog becomes empty.

Stop only when the Completion Gate has been evaluated and the resulting status is supported by evidence.

## Required checkpoint handoffs (user instruction 2026-10-16)

After every major task or critical phase, write a dated handoff in docs/project/checkpoints/ and refresh docs/project/NEXT_SESSION_HANDOFF.md. Record verified changes, exact checks and limitations, remaining tasks/dependencies, executor session/process ownership, known failures and next actions. Update PROGRESS.md, BACKLOG.md, ACCEPTANCE_TRACKER.md and EVIDENCE_REGISTER.md as applicable. Checkpoints are mandatory after implementation milestones, integration, experiments, manuscript assembly/rendering, acceptance audits and before session transfer. Revalidate actual state; never turn executor claims or stale process IDs into accepted evidence. The next session must finish all remaining master-goal requirements, not merely the tasks already tested.
