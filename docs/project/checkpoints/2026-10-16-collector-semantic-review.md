# Collector semantic review findings

Date:2026-10-16. Read plans.py, runner.py and export.py after OC021-R1 terminal exit. Two remaining limitations prevent scientific acceptance:

1. Hybrid schedule_from_order is a separate scheduler implementation. It follows model ordering and applies routes/opening/day/budget checks, but is not the production planner's required-category/preference/meal-aware scheduler. Independent validation does not make a different algorithm representative of the application. A diagnostic call is permissible; thesis H2 needs integration with the actual evaluated pipeline or an explicitly justified protocol revision approved before study, not an unnoticed substitute.
2. Resume data preservation: runner reads existing calls only into a boolean-key map, accumulates only new observations, then atomically rewrites calls.jsonl and h2_records.jsonl from the new list. Source review indicates completed structured evidence can disappear on resume even while raw event files survive. Reproduce in an isolated fake-event fixture before any resume on real evidence. Do not use --resume on preserved runs until corrected.

A bounded fresh S01 diagnostic pair (2calls,30seconds each) is running as process29276 under approved host permissions. Exact requested model opencode-go/deepseek-v4.1-flash; output docs/project/handoffs/OC-021/live-diagnostic-s01. This tests transport/provider availability only; no thesis claim. Preserve its outcome, including missing provenance. OC02245278 remains active.

Diagnostic terminal result: process29276 exit0 for collector orchestration, but BOTH model attempts timed out (~30.52s/~30.53s), childexit1, empty stdout/stderr, no session provenance. attempted2, exportedrecords0, gaps2. This is a failed provider/transport diagnostic, not a successful model experiment. Bounded host cleanup worked for these attempts. Preserve fresh directory; do not retry blindly or interpret orchestrationexit0 as model success.
