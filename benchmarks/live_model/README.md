# live-model paired H2 engineering collector

Stdlib-only engineering collector that drives the **OpenCode CLI** with an explicit
model and agent to produce paired H2 observations (`hybrid` vs `llm_only`) over the
frozen **synthetic** 20-scenario manifest, and exports them as `oc18.h2.v1`
records for the OC-018 evaluator.

Method/manifest version: **`oc23.live.v2`** (OC-023) for the preserved legacy path;
the revised default is the production-V2 path **`exp077.live.v1`** (EXP-077).
The hybrid arm evaluates the *production* scheduler `domains.planning.schedule`;
runs created before a version are incompatible and are rejected on resume rather
than silently mixed.

The V2 exporter writes both the unchanged conservative `h2_manifest.json` /
`h2_records.jsonl` endpoint and a scoped `h2_temporal_manifest.json` /
`h2_temporal_records.jsonl` companion (`endpoint=temporal_only`,
`endpoint_method_version=exp077.temporal.v1`). The companion recomputes only the
four temporal outcome fields; it carries the original global status/unknowns
under `global_*` fields and never claims global validity. Only exact
`cost_unknown:<known-poi-id>` reasons are excluded from temporal uncertainty;
missing hours/routes/interday origins, new/malformed reasons and structural
violations fail closed. Both endpoints are regenerated from stored logs, never
from a new model call.

This is **engineering evidence over synthetic fixtures**, not the original thesis
dataset, not an H2 confirmation and not a human study. `thesis_mode` is always
`false` for the synthetic fixtures. No personal data is used or produced.

## Transports (EXP-074)

`--transport production-v2|legacy-v1`; the default is **production-v2**.

- **production-v2** calls the already-accepted
  `ai_service.domains.providers.opencode_cli.OpenCodeCliProvider.complete` with
  `ProviderConfig` (`max_attempts=1`, `max_concurrency=1`, the validated timeout
  and explicit qualified model `opencode-go/deepseek-v4.1-flash`). The provider
  remains the sole owner of readiness, the private server, deny-only agent policy,
  native-tool rejection, cleanup, Go credential loading and the exact session
  export. The collector does **not** create V1 `OPENCODE_CONFIG_CONTENT`, call
  `capture.child_environment`, or run manual CLI/export/help/pure commands.
  `--pure` fails closed before any model call (the installed CLI has no `--pure`);
  `--session-export` is rejected because the provider owns the export.
- **legacy-v1** is the historical `opencode run --format json` capture path. It is
  retained for historical tests/resumes only, is not compatible with the installed
  CLI 2.0.32, and must be selected explicitly.

V2 evidence is a **derived structured service/provider receipt**, not a raw CLI
transcript or session export: `events/<key>.assistant.txt` (exact text),
`events/<key>.provider-receipt.json` (whitelisted metadata, closed controls/usage,
hashes and nullable totals) and `provider_failure` (constant
`code/attempts/failed_attempts/retryable`, never a raw exception body). Headers,
config, secrets, reasoning, error bodies and unknown subtrees are dropped.
Successful rows require `_provider.ok`, exact requested == observed model, a
nonblank session, `identity_source=opencode_session_export`, `finish=stop` and
`attempts=1`. Dry-run performs no resolver/capability/provider/network call.

The V2 fingerprint binds the transport version/method, the *actual* production
transport system-prompt hash, model, timeout, dataset declaration and exact
scenario selection/conditions/repetitions. Legacy fingerprints remain readable
only through explicit `--transport legacy-v1`; cross-transport or settings drift
fails before any write.

## Terminal provider-authority stop (H2091)

Production-V2 only: after a failed observation is durably appended, an **exact**
closed provider-failure code from policy `h2091.authority-stop.v1` (auth/policy/
rate/preflight/provenance-mismatch set) stops every later planned provider call.
Only `provider_failure.code` is inspected; text, exception messages and
substrings never classify a failure. The attempted failure row is retained
unchanged. Remaining planned keys are listed in `unattempted` with reason
`terminal_provider_authority_stop` and are **missing evidence**, never synthetic
observations, usage, provenance or failed-model rows. The full planned
denominator, global exports and timing companion are preserved; a run stopped
before later cells writes normal exports/summary and exits `1`. A terminal code
at the last/only cell keeps the historical exit `0` while remaining visible as
`terminal_provider_code`. Nonterminal failures (`cli_timeout`, `provider_timeout`,
malformed output, unknown codes) keep the existing no-retry per-cell behaviour.

The policy id and sorted-code hash are frozen in the V2 fingerprint, manifest and
summary; pre-policy V2 runs are incompatible on resume before provider
resolution/write. A prior summary with `stopped_early=true` refuses `--resume`
before any mutation, so fresh credentials cannot silently fill the missing cells;
a new output needs fresh reviewed design/authorization.

No primary H2 observations have been collected yet (`0`). This is a pre-H2
batch-control correction, not post-result endpoint tuning. The H3 partial cohort
remains separate; it is neither fixed nor rerun here.

A dataset is synthetic by default and is **never auto-elevated** from a path,
count or label. A separately supplied primary manifest must declare
`real_supplied_primary_snapshot`, `frozen=true`, a 64-hex payload hash, a canonical
`source_scope` selector (validated through `domains.source_gate`), an explicit
frozen review with the matching scenario-entries hash, and a boolean
`thesis_mode`. The historical 20-case / five-profile primary freeze does not
exist; this collector reports readiness only and authors no primary freeze.


## What it guarantees

- Calls the model exactly as declared: `opencode run --model <id> --agent <agent>
  --format json <prompt>` via an **argument array**. On Windows the **native
  `opencode.exe`** is preferred; `.cmd`/`.bat`/`.ps1` shims are rejected by default
  because a batch wrapper re-parses the command line through `cmd.exe` and cannot
  transport metacharacters exactly. A hard per-call timeout kills the whole process
  tree with bounded cleanup and preserved partial output. `--continue`,
  `--session`, `--share`, `--auto`, `--fork` are refused.
- Adds only a per-process `OPENCODE_CONFIG_CONTENT` that defines a unique primary
  agent with `permission {'*': 'deny'}` (no tools) and sharing disabled. The global
  config and production Gemini configuration are never read or modified.
- Persists the raw event stream and stderr for every attempt, plus the exact
  command, CLI version, duration, exit code, session id, prompt hash and source
  hashes.
- Distinguishes **requested** vs **observed** model ids. An observation is only
  admitted as live evidence when a session id and a matching observed model id are
  present; otherwise it is retained as a raw capture and reported as an explicit
  **gap**.
- **Authoritative session-export provenance (OC-033).** The real DS-004 diagnostic
  showed that a `run --format json` stream can omit the provider/model identity
  entirely. With `--session-export`, the collector additionally runs the read-only
  `opencode export <sessionID>` for **exactly the single session id observed in
  that observation** (never `--continue`/`--session`/latest/list) through the same
  bounded process-tree capture. The exported assistant message is strictly bound
  to the raw observation by session id, messageID, part ids, text and (when
  present) terminal completion, and the observed identity is
  `providerID + "/" + modelID` compared **exactly** to the requested id (no blind
  suffix match). A matching alias is **not** proof of an upstream "4.1"
  checkpoint. Any contradiction fails closed; a missing/malformed/failed export
  stays a gap and the requested model is never reported as observed. The raw
  JSONL is preserved byte-for-byte and the export is stored separately with a
  SHA256, path and source label (`OpenCode session metadata`) in
  `<key>.session-export.json` and `<key>.session-meta.json`.
- `--pure` adds only the supported `run --pure` flag (disables external plugins);
  it is never `--auto` and never relaxes permissions. The chosen provenance
  strategy and `pure` mode are bound into the frozen fingerprint, so a resume with
  a different policy refuses before any write.
- Rejects tool-use events, error events (even at exit 0), timeouts, malformed or
  truncated event streams, absent terminal completion, and unknown/mismatched
  model provenance.
- Parses provider `step_finish` usage with input/output/reasoning/cache kept
  separate. A component is aggregated only when it is present and valid in every
  step; a missing/invalid component stays unknown (never a fabricated zero), an
  explicitly supplied `0` is preserved, negative/boolean counts are rejected, and
  per-component lower bounds are reported separately. Unknown usage stays unknown;
  no character proxy. The evaluator's fixed four-stage `usage` object is left
  unknown (the aggregate cannot honestly fill it); details are preserved under
  `provider_usage`.
- Accepts only an explicit successful terminal reason (`stop`) with final-stream
  consistency. `length`, `tool-calls`, `error`, a missing reason, text after the
  terminal finish, or a trailing incomplete step never become a successful run.
- No automatic retries. Each failure is retained with a reason. Call count and
  per-call timeout are bounded.
- **Lossless, fail-closed run state.** `calls.jsonl` is written atomically after
  **every** observation, so an interruption never loses a committed observation.
  `--resume` parses the existing ledger strictly (a malformed line or duplicate
  `(scenario_id, condition, repetition)` key fails closed with nothing written),
  validates the frozen dataset/settings/model/source fingerprint in `manifest.json`
  *before any write*, and **appends** new observations while preserving the prior
  bytes exactly. A no-op resume writes nothing at all (the prior ledger and raw
  captures stay byte-for-byte identical). Existing output without `--resume`, and
  any settings/source drift, are refused. A single-writer lock (`collector.lock`,
  `O_CREAT|O_EXCL`) makes concurrent writers fail closed.
- Defaults to **dry-run**; model calls require `--execute`.

## Usage

```powershell
# dry run (production-v2 default): write the frozen plan, make no call
python benchmarks/live_model/runner.py --out .tmp-live --scenario-ids S01,S12 --repetitions 1

# bounded production-v2 run (only when explicitly authorized)
python benchmarks/live_model/runner.py --out .tmp-live --scenario-ids S01,S12 --execute --timeout 120

# historical legacy-v1 path (not compatible with the installed CLI 2.0.32)
python benchmarks/live_model/runner.py --out .tmp-live --scenario-ids S01,S12 --execute --transport legacy-v1 --session-export --pure --timeout 120

# resume: only missing keys are attempted
python benchmarks/live_model/runner.py --out .tmp-live --execute --resume
```

The default requested model is the production-V2 alias
`opencode-go/deepseek-v4.1-flash` (display name `DeepSeek V4.1 Flash`); a matching
alias is not evidence that an upstream "4.1" checkpoint was served. Pass
`--model <provider>/<model>` to change it (part of the frozen fingerprint).
`--cli-version` is ignored on production-v2 and recorded as
`cli_version_declared_ignored`; provider metadata is authoritative for executed
rows.

Outputs under `--out`:

| file | content |
|---|---|
| `manifest.json` | frozen run plan, declared denominator, transport/model/agent, dataset declaration, source hashes |
| `events/<key>.assistant.txt` | exact assistant text (production-v2) |
| `events/<key>.provider-receipt.json` | derived, whitelisted provider receipt with hashes (production-v2) |
| `events/<key>.jsonl` | raw event stream per observation (legacy-v1 only) |
| `events/<key>.stderr.txt` | raw stderr per observation (legacy-v1 only) |
| `events/<key>.session-export.json` | raw read-only `opencode export` payload (legacy-v1 with `--session-export`) |
| `events/<key>.session-meta.json` | hashed export metadata: SHA256, path, source label, bound ids (legacy-v1) |
| `events/<key>.session-export.stderr.txt` | raw stderr of the export call (legacy-v1) |
| `calls.jsonl` | one record per attempted observation, with reason and provenance |
| `h2_manifest.json` | OC-018 H2 manifest with explicit dataset identity |
| `h2_records.jsonl` | `oc18.h2.v1` records for provenance-proven observations |
| `run_manifest.json` | summary, gaps, skipped/unattempted keys, readiness (not an accepted primary study) |

## Conditions

- **llm_only** — the model returns a complete timed itinerary as strict JSON; times
  are parsed strictly and the plan is built from the model's order/instants, with
  cost/visit/travel facts taken from the scenario. Invalid JSON is a failed run and
  is never repaired.
- **hybrid** — the model returns a candidate preference order; the **production**
  scheduler `domains.planning.schedule` (the same function the application uses)
  places the candidates. The model's order is mapped to *additive category
  preference weights* on the typed scenario (documented in
  `hybrid_adapter.py`); every other scenario fact is preserved. The production
  scheduler ranks by hard-requirement coverage, then descending preference, then
  travel time, then `poi_id` — it does **not** follow the model's literal order
  and has no per-day pinning (`day_assignment` is recorded but marked
  `honored: false`). This differs from the LLM-only path (it is not the
  deterministic scheduler run in both arms).

Both paths end in the existing **independent validator**, which owns the verdict.

## Limitations

- The exact event taxonomy can vary by CLI version; every field is best-effort.
  Legacy-v1 retains the raw event file as ground truth; production-v2 retains the
  exact assistant text and a derived whitelisted provider receipt instead of a raw
  CLI transcript/export.
- The local CLI agent adds unmeasured overhead (startup, transport, formatting);
  the collector does not claim full accounting of hidden CLI overhead. Provider
  tokens from the run stream or the export's assistant message are **observed
  assistant usage**: they are not assumed to include auxiliary/title/network
  overhead, and the provider `total` is never recomputed or double-counted.
- An exported alias (`providerID + "/" + modelID`) is session metadata, not an
  upstream checkpoint guarantee; the collector never claims the alias proves a
  specific "4.1" model.
- The production scheduler can only honor the model's order through category
  preference weights; within a category, ties fall to travel time then `poi_id`.
  The model's `day_assignment` is preserved as evidence but not applied.
- Inputs are hand-authored synthetic fixtures, excluded from the original dataset.
