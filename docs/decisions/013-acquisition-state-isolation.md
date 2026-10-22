# ADR 013 — Acquisition state isolation (dataset/synthetic scope)

- Status: Accepted
- Date: 2026-10-16
- Task: OC-026 (corrective; supersedes the OC-006 §8 behaviour)
- Scope: `crawler_service/app/acquisition/`, `tests/acquisition/`
- Supersedes: none
- Related: ADR 005 (acquisition pipeline), `docs/architecture/DATA_ACQUISITION_DESIGN.md`

## Context

ADR 005 §8 labelled effective synthetic as `manifest.synthetic OR source.synthetic
OR review.synthetic` and isolated a *synthetic-to-real* same-identity collision.
The OC-006 QA pass left a one-sided defect: the collision guard only fired for
`entry.synthetic == True and not effective_synthetic` (synthetic → real). The
reverse order (real → synthetic) fell through to the fact-fingerprint and policy
branches, so a synthetic record could inherit a prior **real** acceptance, be
counted as a duplicate, or be silently re-evaluated while the old real
`synthetic=False` flag was kept. Synthetic data could therefore contaminate real
accepted output.

The design contract is explicit: "Keep original thesis dataset separate from
expansion." A synthetic/real distinction that can be silently merged inside one
state directory is unsound regardless of which order it happens in.

## Decision

### 1. One immutable dataset/synthetic scope per state directory

Every acquisition manifest declares a `dataset` identity (optional, default
`default`, validated as a safe token). The run's classification is the effective
synthetic flag of its sources:

- all sources effective-synthetic → `synthetic`;
- no source effective-synthetic → `real`.

The **scope** is the canonical token `"{dataset}::{synthetic|real}"`. The state
file records this scope when it is created and it never changes. Synthetic and
real records can never share durable identity state in one directory, so no
promotion, demotion, duplicate-collapse or re-evaluation can cross the boundary.

### 2. Preflight rejection before any output mutation

The whole manifest, mapping and every source payload are parsed and the scope is
derived **before** the output directory is created and before the state file is
opened. If an existing `state.json` is bound to a different scope — in either
direction — the run is a hard `ConfigError`; the user chooses a fresh directory
or the matching scope. No raw blob, ledger line, JSONL output or state byte is
written on a scope violation. This is stricter than flipping a flag or silently
recording a collision duplicate.

### 3. Mixed manifests are a scope violation

A manifest that mixes synthetic and real sources is rejected outright rather than
being partitioned into one shared directory. Partitioned namespaces were
considered (separate state partitions and export separation) but rejected: the
exported `POI.id` is the source-derived stable id required to be immutable by ADR
001, so two scopes sharing one id would collide at graph ingestion. Strict
separation into separate runs/directories is the only representation that keeps
one stable id owned by exactly one classification.

### 4. Symmetric in-scope collision guard (defence in depth)

Within a run, if an existing durable entry's classification ever differs from the
incoming effective classification, the record is quarantined with
`synthetic_real_collision`, `resolved_id` is never emitted, and the prior facts,
provenance, status and history are left untouched. The guard is symmetric
(`entry.synthetic != effective_synthetic`), so neither order can promote or
demote. Policy re-evaluation now persists `effective_synthetic` and only runs
after the classification guard, so the old flag is never silently retained.

### 5. Legacy and unknown state fails closed

The state format is versioned at `pipeline_version = 3`. A legacy
version-mismatched, scope-less or otherwise unknown `state.json` raises
`ConfigError` and is never rewritten or reset automatically. Read-only migration
plan for existing datasets: with a backup/check, inspect each `state.json`,
confirm its single classification from the recorded entries, then re-run in a
fresh directory bound to the correct explicit scope (or add the scope token by a
reviewed, backed-up, offline edit). Migration is never run against real state by
the pipeline.

### 6. Per-entry scope consistency on load (OC-026-R1 correction)

Declaring a scope is not enough: a `state.json` could declare one classification
while carrying an entry of the other, and a stale/untouched contradictory entry
would still leak into the accepted summary. On load, `StateStore` now strictly
parses the scope (exact `<dataset>::<synthetic|real>`, canonical dataset, unknown
classification rejected) and validates **every** entry, whether or not this run
touches it:

- `synthetic` must be present and an actual `bool` (`type(x) is bool`), never a
  string/int and never coerced with `bool(...)`; a missing, non-boolean or
  scope-contradicting flag raises `ConfigError`;
- `stable_id` must be a non-blank string and `status` must be a known outcome;
- an `accepted` entry must carry a `resolved` object with a non-blank string
  `id`, so a malformed accepted payload can never be emitted into `summary.json`
  or `accepted.jsonl`.

Empty new state is valid; a homogeneous, version-matched v3 state continues
idempotently. Unknown/legacy state remains fail-closed and is never reset.
Validation happens before `out_dir.mkdir`, so a contradictory entry preserves
every existing output byte.

## Consequences

- Positive: synthetic and real records can never share durable identity or
  inherit each other's acceptance; both ordering directions and changed policy
  are safe; mixed contamination is impossible by construction; failures are
  fail-closed and preflight, leaving originals byte-identical.
- Negative / risk: an existing `state.json` without a scope must be migrated
  manually (fail closed); a mixed manifest must be split into separate runs; each
  dataset/synthetic scope needs its own output directory.
- No live ingestion, network access or graph write is involved.

## Verification

- `tests/acquisition/test_state_isolation.py` (37 tests) covers both
  classification orders, the dataset scope dimension, mixed-manifest rejection,
  effective classification from the top/source/review flags, zero real expansion
  when synthetic, changed facts within a scope, compatible policy re-evaluation,
  idempotence, legacy/unknown/mixed state fail-closed, invalid later source with
  no writes, cross-source-merge honesty, and per-entry scope consistency
  (contradictory/missing/non-boolean flags, malformed scope tokens, malformed
  accepted entries, direct `StateStore` and full-pipeline probes). Rejections
  compare the full byte/hash snapshot of the output tree, not only summary
  counts.
- `tests/acquisition/test_pipeline_cli.py` updated for strict separation.
- Raw run: `docs/project/handoffs/OC-026/pytest_oc026_repair1.txt` → 234 passed
  (`tests/acquisition` 140). Raw CLI demo:
  `docs/project/handoffs/OC-026/cli_demo.txt`.
