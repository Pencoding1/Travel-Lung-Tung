# EXP080 typed H3 collector

`runner.py` is an offline-by-default collector for the existing five synthetic
H3 profiles x three existing memory conditions x one repetition.

- `--out DIR` without `--execute` is a dry run: zero provider, HTTP, process
  or credential resolution, and it may write the unfrozen candidate manifest.
- `--execute` refuses an unfrozen manifest before backend resolution. A frozen
  run requires the Codex-authored execution design, the EXP086 before-source
  manifest, exact code/dependency hashes and independent QA. The EXP086
  baseline keeps the same 46 readonly paths as EXP080 and changes only
  `ai_service/main.py` to the accepted CORE084 hash; the EXP080 baseline stays
  immutable.
- Method: `exp080.http.memory.typed.v2`.
- Preparation and lifecycle use `POST /chat`. Primary scoring uses
  `POST /generate_itinerary` with the exact body in
  `docs/project/handoffs/EXP-080/parent-h3-typed-execution-design.json`.
- Exactly 15 preparation chats, 15 typed score requests and at most 3
  lifecycle chats are counted, 33 model-generating requests in total.
- Typed source acceptance requires both `payload.grounding.source_scope` and
  `payload.planning.request_constraints.source_scope` to equal the frozen
  source. A top-level `source_scope` is never sufficient.
- Selected POI ids and arrival/departure timestamps are read only from the
  repaired schedule; prose and grounding evidence ids are never substituted.
- There are no retries or fallbacks. HTTP503 stops dependent calls and is
  recorded as `provider_unavailable`, never inferred as quota or auth.
- Failed preparation and lifecycle requests append a sanitized
  `request_observation` ledger row with closed provider receipts, actual
  attempt counts and a fixed error enum; raw bodies and messages are never
  persisted.
- Failure evidence keeps two independent layers: the top-level business
  `error.code` (or `error_code`) and each per-call provider `error_code`.
  Both go through the static closed enum (the existing codes plus the 90
  parent-approved literals); unrecognized strings become `unknown`, never
  quota/auth. Non-string codes are omitted, not stringified.
- `calls.scoring_chats` remains as a legacy alias for typed score requests;
  `calls.typed_scoring_requests` is canonical.

The native two-tier rerun and a full execution freeze remain outstanding. No
failure cause is attributed here; the historical CORE085 per-call code was not
retained. This collector does not accept, freeze or prove the study. Synthetic
transport tests are not native model evidence.
