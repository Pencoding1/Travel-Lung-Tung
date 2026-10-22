# Collector independent review checkpoint

Date:2026-10-16. Previous phase classified PROGRESS: handoff and checkpoint policy saved; OC020/021 terminal status verified;46 collector tests independently passed.

Independent source review and direct Python probe now reject full OC021 acceptance:
- tokens={} gives five zero components and partial=False; input-only usage fabricates missing output/reasoning/cache zeros.
- text plus finish reason length gives terminal_present=True, admitting truncation as completion.
- Windows batch transport and child-only timeout cleanup require stronger evidence; these are reviewed risks, not yet independently reproduced runtime failures.

One bounded corrective pass dispatched: OC-021-R1 process26701, explicit OpenCode session ses_ebd647971ffe0i7PeA0Pab5fGH. Brief: docs/project/handoffs/OC-021/repair-brief.md. Writes limited to collector/tests/own handoff. No live calls. Original evidence retained. Poll same handle; no duplicate writer. After terminal result inspect code, run targeted tests and independent probes, then update acceptance and handoff before live experiments.

All other unfinished scope remains in NEXT_SESSION_HANDOFF.md. No successful DeepSeek experiment, rendered manuscript or live deployment claimed.
